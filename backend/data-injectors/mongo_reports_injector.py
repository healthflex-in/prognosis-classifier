#!/usr/bin/env python3
"""
MongoDB Reports Injector for LangChain
Fetches clinical reports from MongoDB with FirstAssessment filtering and date matching.
Only streams FirstAssessment data and tests done at that date (or closest match).
"""

import os
import json
from typing import List, Optional, Dict, Any, Tuple
from pathlib import Path
from datetime import datetime, timedelta

# LangChain imports
try:
    from langchain_core.documents import Document
except ImportError:
    # Fallback if langchain not installed
    class Document:
        def __init__(self, page_content: str, metadata: Dict = None):
            self.page_content = page_content
            self.metadata = metadata or {}

# Load environment variables
try:
    from dotenv import load_dotenv
    # Try backend/.env first, then root .env as fallback
    backend_env = Path(__file__).parent.parent / ".env"
    root_env = Path(__file__).parent.parent.parent / ".env"
    if backend_env.exists():
        load_dotenv(backend_env)
    elif root_env.exists():
        load_dotenv(root_env)
    else:
        # Try loading from current directory or system env
        load_dotenv()
except ImportError:
    pass

# Import MongoDB loader and VALD transformer
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
from load_reports_from_mongo import MongoReportsLoader


class MongoReportsInjector:
    """
    LangChain-compatible data injector for MongoDB clinical reports.
    Filters for FirstAssessment=true and matches tests to that date.
    """
    
    def __init__(self, mongo_uri: Optional[str] = None, db_name: Optional[str] = None):
        """
        Initialize MongoDB reports injector.
        
        Args:
            mongo_uri: MongoDB connection string (defaults to env var)
            db_name: Database name (defaults to env var or 'stance-dashboard')
        """
        self.loader = MongoReportsLoader(mongo_uri=mongo_uri, db_name=db_name)
    
    def _find_closest_date(self, target_date: datetime, date_list: List[datetime], 
                          max_days_range: int = 7) -> Optional[datetime]:
        """
        Find the closest date in date_list to target_date within max_days_range.
        
        Args:
            target_date: The target date to match
            date_list: List of dates to search
            max_days_range: Maximum days difference allowed (default: 7)
            
        Returns:
            Closest date within range, or None if no match found
        """
        if not date_list:
            return None
        
        closest_date = None
        min_diff = float('inf')
        
        for date in date_list:
            diff = abs((date - target_date).days)
            if diff <= max_days_range and diff < min_diff:
                min_diff = diff
                closest_date = date
        
        return closest_date
    
    def _extract_vald_session_dates(self, vald_records: List[Dict]) -> List[datetime]:
        """
        Extract all session dates from VALD exercise data.
        Uses the same logic as VALDTransformer._extract_session_dates_from_exercise.
        
        Args:
            vald_records: List of VALD records from VALDTransformer
        
        Returns:
            List of datetime objects from VALD sessions
        """
        session_dates = []
        
        for record in vald_records:
            exercises = record.get('exercises', {})
            
            # Get record date from lastRecordedUtc as fallback
            record_date = None
            if 'last_recorded_utc' in record:
                utc_value = record['last_recorded_utc']
                if isinstance(utc_value, str):
                    record_date = utc_value[:10]  # Extract YYYY-MM-DD
                elif hasattr(utc_value, 'strftime'):  # datetime object
                    record_date = utc_value.strftime('%Y-%m-%d')
                else:
                    record_date = str(utc_value)[:10] if len(str(utc_value)) >= 10 else None
            
            # Extract dates from all exercise categories
            for category in ['forceFrame', 'forceDeck', 'dynamo']:
                for exercise_key, exercise_data in exercises.get(category, {}).items():
                    if isinstance(exercise_data, dict):
                        data = exercise_data.get('data', {})
                        
                        # Use same extraction logic as VALDTransformer
                        dates = self._extract_session_dates_from_exercise_data(data)
                        
                        # If no dates found, use lastRecordedUtc as fallback
                        if not dates and record_date:
                            dates = {record_date}
                        
                        # Convert to datetime objects
                        for date_str in dates:
                            date_part = date_str[:10] if len(date_str) >= 10 else date_str
                            try:
                                dt = datetime.strptime(date_part, '%Y-%m-%d')
                                if dt not in session_dates:
                                    session_dates.append(dt)
                            except ValueError:
                                continue
        
        return sorted(session_dates)
    
    def _extract_session_dates_from_exercise_data(self, data: Dict) -> set:
        """
        Extract session dates from exercise data structure.
        Matches the logic in VALDTransformer._extract_session_dates_from_exercise.
        """
        dates = set()
        
        if not isinstance(data, dict):
            return dates
        
        # Recursively search for x_axis_entities
        def extract_dates_recursive(obj):
            found_dates = []
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == 'x_axis_entities' and isinstance(value, list):
                        for item in value:
                            if isinstance(item, str) and len(item) >= 10:
                                # Check if it looks like a date (YYYY-MM-DD format)
                                if item[4] == '-' and item[7] == '-':
                                    found_dates.append(item[:10])
                    else:
                        found_dates.extend(extract_dates_recursive(value))
            elif isinstance(obj, list):
                for item in obj:
                    found_dates.extend(extract_dates_recursive(item))
            return found_dates
        
        # Extract from x_axis_entities
        date_strings = extract_dates_recursive(data)
        dates.update(date_strings)
        
        # Also check sessionDates field
        if 'sessionDates' in data and isinstance(data['sessionDates'], list):
            for date_str in data['sessionDates']:
                if isinstance(date_str, str) and len(date_str) >= 10:
                    dates.add(date_str[:10])
        
        return dates
    
    def load_data(self, patient_id: str, stance_id: str = None, max_days_range: int = 7) -> List[Document]:
        """
        Load clinical reports for a patient, filtering for FirstAssessment and matching VALD tests.
        
        Args:
            patient_id: Patient ID to fetch
            stance_id: Stance ID for VALD data (if None, will try to extract from patient_id)
            max_days_range: Maximum days difference allowed for VALD test date matching (default: 7)
            
        Returns:
            List of Document objects containing filtered clinical data:
            - Document 1: First Assessment
            - Document 2: VALD tests matching FirstAssessment date (if any)
        """
        # Fetch patient reports
        patient_info, clinical_data = self.loader.get_patient_reports(patient_id)
        
        if not patient_info or not clinical_data:
            return []
        
        # Find FirstAssessment record
        first_assessment = None
        for record in clinical_data:
            if record.get('isFirstAssessment') is True:
                first_assessment = record
                break
        
        if not first_assessment:
            # No first assessment found
            return []
        
        # Extract first assessment date
        first_assessment_date = None
        if first_assessment.get('event_start_time'):
            first_assessment_date = datetime.fromtimestamp(
                first_assessment['event_start_time'] / 1000
            )
        elif first_assessment.get('date'):
            try:
                first_assessment_date = datetime.strptime(
                    first_assessment['date'], '%Y-%m-%d'
                )
            except ValueError:
                pass
        
        if not first_assessment_date:
            # Cannot determine date, return only first assessment
            documents = []
            content = json.dumps(first_assessment, indent=2, default=str)
            metadata = {
                'source': 'mongo_reports',
                'patient_id': str(patient_info.get('patient_id')),
                'patient_name': patient_info.get('patient_name'),
                'record_type': 'first_assessment',
                'date': first_assessment.get('date'),
                'seqNo': first_assessment.get('seqNo')
            }
            documents.append(Document(page_content=content, metadata=metadata))
            return documents
        
        # Create documents - only FirstAssessment (VALD data removed from pipeline)
        documents = []
        
        # Document 1: First Assessment
        content = json.dumps(first_assessment, indent=2, default=str)
        # Get patient name, defaulting to "Unknown" if not available
        patient_name = patient_info.get('patient_name') if patient_info else None
        if not patient_name:
            patient_name = "Unknown"
        metadata = {
            'source': 'mongo_reports',
            'patient_id': str(patient_info.get('patient_id')) if patient_info else str(patient_id),
            'patient_name': patient_name,
            'patient_seq_no': patient_info.get('patient_seq_no') if patient_info else '',
            'record_type': 'first_assessment',
            'date': first_assessment.get('date'),
            'event_start_time': first_assessment.get('event_start_time'),
            'seqNo': first_assessment.get('seqNo'),
            'first_assessment_date': first_assessment_date.strftime('%Y-%m-%d') if first_assessment_date else None
        }
        documents.append(Document(page_content=content, metadata=metadata))
        
        return documents
    
    def load_data_stream(self, patient_id: str, stance_id: str = None, max_days_range: int = 7):
        """
        Stream clinical reports as Documents (generator).
        
        Args:
            patient_id: Patient ID to fetch
            stance_id: Stance ID for VALD data (optional)
            max_days_range: Maximum days difference allowed for VALD test date matching
            
        Yields:
            Document objects containing filtered clinical data
        """
        documents = self.load_data(patient_id, stance_id, max_days_range)
        
        for doc in documents:
            yield doc
    
    def close(self):
        """Close MongoDB connection."""
        if self.loader:
            self.loader.close()


# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python mongo_reports_injector.py <patient_id> [max_days_range]")
        sys.exit(1)
    
    patient_id = sys.argv[1]
    max_days_range = int(sys.argv[2]) if len(sys.argv) > 2 else 7
    
    injector = MongoReportsInjector()
    documents = injector.load_data(patient_id, max_days_range)
    
    print(f"\n✅ Loaded {len(documents)} document(s) for patient ID: {patient_id}")
    
    for i, doc in enumerate(documents):
        print(f"\n--- Document {i+1} ---")
        print(f"Type: {doc.metadata.get('record_type')}")
        print(f"Metadata: {doc.metadata}")
        print(f"Content preview: {doc.page_content[:300]}...")
    
    injector.close()
