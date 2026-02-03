#!/usr/bin/env python3
"""
Fetch matches from MongoDB and transform to VALD format for a specific patient.
Replaces the file-based approach with direct MongoDB queries.
"""

import json
import os
from typing import Dict, List, Any, Optional
from pymongo import MongoClient
from pathlib import Path

# Load .env file explicitly - try backend/.env first, then root .env
from dotenv import load_dotenv
backend_env = Path(__file__).parent / "backend" / ".env"
root_env = Path(__file__).parent / ".env"
if backend_env.exists():
    load_dotenv(backend_env)
elif root_env.exists():
    load_dotenv(root_env)
else:
    load_dotenv()  # Try system env or current dir


class VALDTransformer:
    """Fetch and transform VALD data from MongoDB matches collection."""
    
    def __init__(self, mongo_uri: str = None, db_name: str = None):
        """
        Initialize MongoDB connection.
        
        Args:
            mongo_uri: MongoDB connection string
            db_name: Database name (default: 'stance-dashboard')
        """
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
        self.db_name = db_name or os.getenv("MONGO_DB", "stance-dashboard")
        self.client = None
        self.db = None
        self.connect()
    
    def connect(self):
        """Connect to MongoDB."""
        try:
            self.client = MongoClient(
                self.mongo_uri,
                tlsAllowInvalidCertificates=True,
                tlsAllowInvalidHostnames=True
            )
            self.db = self.client[self.db_name]
            # Test connection
            self.db.command('ping')
            print(f"✅ Connected to MongoDB: {self.db_name}")
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            raise
    
    def fetch_matches_for_patient(self, stance_id: str) -> List[Dict[str, Any]]:
        """
        Fetch match records for a specific patient from MongoDB.
        Tries multiple field name variations to find the correct one.
        
        Args:
            stance_id: The patient's stance ID
        
        Returns:
            List of match documents
        """
        try:
            collection = self.db['matches']
            
            # Try multiple field name variations
            field_variations = [
                'stanceId',      # camelCase (most common)
                'stance_id',     # snake_case
                'stanceID',      # mixed case
                'StanceId',      # PascalCase
                'user_id',       # alternative field name
                'userId',        # alternative camelCase
            ]
            
            matches = []
            used_field = None
            
            for field in field_variations:
                query = {field: stance_id}
                matches = list(collection.find(query))
                if matches:
                    used_field = field
                    print(f"✓ Found matches using field '{field}'")
                    break
            
            if not matches:
                # If no exact match, try regex search (case-insensitive)
                print(f"⚠️  No exact match found. Trying case-insensitive search...")
                for field in field_variations:
                    try:
                        query = {field: {'$regex': f'^{stance_id}$', '$options': 'i'}}
                        matches = list(collection.find(query))
                        if matches:
                            used_field = field
                            print(f"✓ Found matches using case-insensitive search on '{field}'")
                            break
                    except:
                        continue
            
            if matches:
                print(f"✓ Fetched {len(matches)} match records for stance ID: {stance_id} (using field: {used_field})")
            else:
                print(f"⚠️  No VALD data found for stance ID: {stance_id}")
                print(f"   This is normal - not all patients have VALD test data in the matches collection")
                print(f"   The triage agent will classify without VALD metrics (phenotype will be 'None')")
            
            return matches
        
        except Exception as e:
            print(f"❌ Error fetching matches from MongoDB: {e}")
            import traceback
            traceback.print_exc()
            return []
    
    def transform_matches_to_vald(self, matches: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Transform matches JSON into VALD input format.
        
        Args:
            matches: List of match documents from MongoDB
        
        Returns:
            List of VALD records with extracted force frame data
        """
        
        vald_records = []
        
        for match in matches:
            # Extract basic info
            stance_id = match.get('stanceId')
            full_name = match.get('stanceFullName', 'Unknown')
            vald_ids = match.get('associatedValdId', [])
            vald_id = vald_ids[0] if vald_ids else None
            
            # Extract force frame data if available
            saved_response = match.get('savedResponse', {})
            data = saved_response.get('data', {})
            
            # Create VALD record
            vald_record = {
                '_id': match.get('_id'),
                'user_id': stance_id,
                'name': full_name,
                'vald_id': vald_id,
                'date_of_birth': match.get('dateOfBirth'),
                'sex': match.get('sex'),
                'last_recorded_utc': match.get('lastRecordedUtc'),
                'is_active': match.get('isActive'),
                'created_at': match.get('createdAt'),
                'updated_at': match.get('updatedAt'),
                'exercises': {
                    'forceFrame': {},
                    'forceDeck': {},
                    'dynamo': {}
                }
            }
            
            # Process force frame exercises
            force_frame_data = data.get('forceFrame', {})
            if force_frame_data:
                for exercise_key, exercise_data in force_frame_data.items():
                    # Skip non-exercise keys
                    if exercise_key in ['dynamo', 'forceDeck']:
                        continue
                    
                    # Exercise data is directly in the exercise object (not wrapped in 'data' key)
                    exercise_record = {
                        'exercise_name': exercise_key,
                        'data': exercise_data  # Store the metrics directly
                    }
                    
                    vald_record['exercises']['forceFrame'][exercise_key] = exercise_record
            
            # Process forceDeck exercises
            force_deck_data = data.get('forceDeck', {})
            if force_deck_data:
                for exercise_key, exercise_data in force_deck_data.items():
                    exercise_record = {
                        'exercise_name': exercise_key,
                        'data': exercise_data
                    }
                    vald_record['exercises']['forceDeck'][exercise_key] = exercise_record
            
            # Process dynamo exercises
            dynamo_data = data.get('dynamo', {})
            if dynamo_data:
                for exercise_key, exercise_data in dynamo_data.items():
                    exercise_record = {
                        'exercise_name': exercise_key,
                        'data': exercise_data
                    }
                    vald_record['exercises']['dynamo'][exercise_key] = exercise_record
            
            vald_records.append(vald_record)
        
        return vald_records
    
    def get_vald_data_for_patient(self, stance_id: str) -> List[Dict[str, Any]]:
        """
        Fetch and transform VALD data for a specific patient in one call.
        
        Args:
            stance_id: The patient's stance ID
        
        Returns:
            List of VALD records for this patient
        """
        print(f"\n📂 Fetching VALD data from MongoDB for stance ID: {stance_id}...")
        
        # Fetch matches from MongoDB
        matches = self.fetch_matches_for_patient(stance_id)
        
        if not matches:
            print(f"⚠️  No matches found for stance ID: {stance_id}")
            return []
        
        # Transform to VALD format
        print(f"🔄 Transforming {len(matches)} matches to VALD format...")
        vald_records = self.transform_matches_to_vald(matches)
        
        # Generate summary
        self._generate_summary(vald_records)
        
        return vald_records
    
    def _generate_summary(self, vald_records: List[Dict[str, Any]]):
        """Generate summary statistics of VALD data with session dates."""
        
        print(f"\n📊 VALD Data Summary:")
        print(f"━" * 80)
        
        total_records = len(vald_records)
        active_records = sum(1 for r in vald_records if r.get('is_active'))
        records_with_force_frame = sum(1 for r in vald_records if r['exercises']['forceFrame'])
        records_with_force_deck = sum(1 for r in vald_records if r['exercises']['forceDeck'])
        records_with_dynamo = sum(1 for r in vald_records if r['exercises']['dynamo'])
        
        print(f"Total Records: {total_records}")
        print(f"Active Records: {active_records}")
        print(f"Records with Force Frame Data: {records_with_force_frame}")
        print(f"Records with Force Deck Data: {records_with_force_deck}")
        print(f"Records with Dynamo Data: {records_with_dynamo}")
        
        # Exercise distribution by category with session dates
        exercise_counts = {'forceFrame': {}, 'forceDeck': {}, 'dynamo': {}}
        
        for record in vald_records:
            # Get record date from lastRecordedUtc as fallback when dates are not explicitly given
            record_date = None
            if 'last_recorded_utc' in record:
                utc_value = record['last_recorded_utc']
                if isinstance(utc_value, str):
                    record_date = utc_value[:10]  # Extract YYYY-MM-DD
                elif hasattr(utc_value, 'strftime'):  # datetime object
                    record_date = utc_value.strftime('%Y-%m-%d')
                else:
                    # Try to convert to string and extract
                    record_date = str(utc_value)[:10]
            
            for category in ['forceFrame', 'forceDeck', 'dynamo']:
                for exercise_key, exercise_data in record['exercises'][category].items():
                    if exercise_key not in exercise_counts[category]:
                        exercise_counts[category][exercise_key] = {'count': 0, 'dates': set()}
                    
                    exercise_counts[category][exercise_key]['count'] += 1
                    
                    # Extract session dates
                    data = exercise_data.get('data', {})
                    dates = self._extract_session_dates_from_exercise(data)
                    
                    # If no dates found explicitly in the data, use lastRecordedUtc as fallback
                    if not dates and record_date:
                        dates = {record_date}
                    
                    exercise_counts[category][exercise_key]['dates'].update(dates)
        
        # Print distribution for each category
        for category in ['forceFrame', 'forceDeck', 'dynamo']:
            if exercise_counts[category]:
                print(f"\n{category} Exercise Distribution:")
                for exercise, info in sorted(exercise_counts[category].items(), key=lambda x: x[1]['count'], reverse=True):
                    dates_list = sorted(list(info['dates']))
                    dates_str = ", ".join(dates_list) if dates_list else "No dates found"
                    print(f"  - {exercise}: {info['count']} records")
                    print(f"    Sessions: {dates_str}")
        
        print(f"━" * 80)
    
    def _extract_session_dates_from_exercise(self, data: Dict) -> set:
        """Extract session dates from exercise data."""
        dates = set()
        
        if not isinstance(data, dict):
            return dates
        
        # Look for sessionDates key
        if 'sessionDates' in data and isinstance(data['sessionDates'], list):
            for date_str in data['sessionDates']:
                date_part = date_str[:10] if len(date_str) >= 10 else date_str
                dates.add(date_part)
        
        # Look for x_axis_entities in graph data (recursive search)
        def extract_dates_recursive(obj):
            found_dates = []
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == 'x_axis_entities' and isinstance(value, list):
                        # Only extract valid date strings (YYYY-MM-DD format or ISO format)
                        for item in value:
                            if isinstance(item, str):
                                # Check if it looks like a date (starts with YYYY-MM-DD or YYYY-MM-DDTHH:MM)
                                if len(item) >= 10 and item[4] == '-' and item[7] == '-':
                                    found_dates.append(item)
                    else:
                        found_dates.extend(extract_dates_recursive(value))
            elif isinstance(obj, list):
                for item in obj:
                    found_dates.extend(extract_dates_recursive(item))
            return found_dates
        
        x_axis_dates = extract_dates_recursive(data)
        for date_str in x_axis_dates:
            date_part = date_str[:10] if len(date_str) >= 10 else date_str
            dates.add(date_part)
        
        return dates
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            print("✅ MongoDB connection closed")


# Example usage
if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python fetch_and_transform_vald.py <stance_id>")
        sys.exit(1)
    
    stance_id = sys.argv[1]
    
    transformer = VALDTransformer()
    vald_data = transformer.get_vald_data_for_patient(stance_id)
    
    if vald_data:
        print(f"\n✨ Successfully fetched and transformed VALD data for {stance_id}")
        print(f"📊 Total VALD records: {len(vald_data)}")
    else:
        print(f"❌ No VALD data found for {stance_id}")
    
    transformer.close()
