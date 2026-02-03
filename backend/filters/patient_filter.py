#!/usr/bin/env python3
"""
Patient Filter
Filters patients based on criteria: FirstAssessment, within 4-5 months, has diagnosis.
Uses data injectors to fetch data from MongoDB.
"""

import sys
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

# Import data injectors
import importlib.util
data_injectors_dir = backend_dir / "data-injectors"

def load_module_from_path(module_name, file_path):
    """Load a module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

mongo_injector_module = load_module_from_path(
    "mongo_reports_injector", 
    data_injectors_dir / "mongo_reports_injector.py"
)
MongoReportsInjector = mongo_injector_module.MongoReportsInjector


class PatientFilter:
    """Filter patients based on clinical criteria."""
    
    def __init__(self, months_back: Optional[int] = 5, current_date: Optional[datetime] = None):
        """
        Initialize the patient filter.
        
        Args:
            months_back: Number of months to look back (None means no date limit - all patients)
            current_date: Current date for filtering (default: today)
        """
        self.months_back = months_back
        self.current_date = current_date or datetime.now()
        if months_back is None:
            # No date limit - process all patients regardless of date
            self.cutoff_date = None
            self.cutoff_timestamp = None
        else:
            self.cutoff_date = self.current_date - timedelta(days=months_back * 30)
            self.cutoff_timestamp = int(self.cutoff_date.timestamp() * 1000)
    
    def get_filtered_patients(self, patient_ids: Optional[List[str]] = None, update_progress: bool = False) -> List[Dict[str, Any]]:
        """
        Filter patients based on criteria:
        1. Has FirstAssessment = True
        2. FirstAssessment within specified months (default 4-5 months)
        3. Has Provisional Diagnosis
        
        Args:
            patient_ids: Optional list of patient IDs to filter. If None, will need to be provided differently.
            update_progress: Whether to update progress tracker
        
        Returns:
            List of eligible patient records with diagnosis and complaints
        """
        eligible_records = []
        
        injector = MongoReportsInjector()
        
        try:
            # If patient_ids provided, filter those
            if patient_ids:
                total = len(patient_ids)
                for idx, patient_id in enumerate(patient_ids, 1):
                    try:
                        # Show progress every 10 patients or at milestones
                        if idx % 10 == 0 or idx == 1 or idx == total:
                            print(f"   Processing patient {idx}/{total}...", end='\r')
                            if update_progress:
                                try:
                                    from api.progress_tracker import set_progress
                                    set_progress("running", idx, total, message=f"Filtering patient {idx}/{total}...")
                                except Exception:
                                    pass
                        
                        # Load patient data using injector
                        # Note: patient_id is used as stance_id too
                        docs = injector.load_data(patient_id, stance_id=patient_id, max_days_range=7)
                        
                        # Find FirstAssessment document
                        first_assessment_doc = next(
                            (doc for doc in docs if doc.metadata.get('record_type') == 'first_assessment'),
                            None
                        )
                        
                        if first_assessment_doc:
                            record_data = self._process_patient_record(
                                first_assessment_doc, 
                                patient_id,
                                injector.loader
                            )
                            
                            if record_data:
                                eligible_records.append(record_data)
                    except Exception as e:
                        # Only print errors for first few or every 100th to avoid spam
                        if idx <= 5 or idx % 100 == 0:
                            print(f"⚠️  Error processing patient {patient_id}: {e}")
                        continue
                
                print()  # New line after progress
            
            # If no patient_ids provided, we'd need to list all patients first
            # For now, return empty list with a note
            if not patient_ids:
                print("ℹ️  No patient IDs provided. Use list_patients() first to get patient IDs.")
        
        finally:
            injector.close()
        
        return eligible_records
    
    def _process_patient_record(
        self, 
        first_assessment_doc: Any, 
        patient_id: str,
        loader: Any
    ) -> Optional[Dict[str, Any]]:
        """
        Process a single patient record to check if it meets filter criteria.
        
        Args:
            first_assessment_doc: Document from MongoReportsInjector
            patient_id: Patient ID
            loader: MongoReportsLoader instance for getting patient name
        
        Returns:
            Dictionary with patient info if eligible, None otherwise
        """
        import json
        
        # Parse the document content
        try:
            record = json.loads(first_assessment_doc.page_content)
        except:
            record = first_assessment_doc.page_content if isinstance(first_assessment_doc.page_content, dict) else {}
        
        # Criterion 1: First Assessment (already filtered by injector)
        if not record.get('isFirstAssessment'):
            return None
        
        # Criterion 2: Within specified months (skip if months_back is None - no date limit)
        if self.cutoff_timestamp is not None:
            # Check event_start_time or createdAt
            ts = None
            if record.get('event_start_time'):
                ts = int(record['event_start_time'])
            elif record.get('createdAt'):
                ts_val = record['createdAt']
                if isinstance(ts_val, dict):
                    ts = int(ts_val.get('$numberLong', 0))
                elif isinstance(ts_val, (int, float)):
                    ts = int(ts_val)
            
            if not ts or ts < self.cutoff_timestamp:
                return None
        
        # Criterion 3: Provisional Diagnosis exists
        diag = record.get('diagnosis', '')
        if not diag:
            # Try to get from raw_data if available
            raw_data = record.get('raw_data', {})
            if raw_data:
                records = raw_data.get('records', {})
                diag = records.get('provisionalDiagnosis', {}).get('diagnosis', '').strip()
        
        if not diag:
            return None
        
        # Get chief complaints
        complaints = record.get('chief_complaints', '')
        if not complaints:
            raw_data = record.get('raw_data', {})
            if raw_data:
                records = raw_data.get('records', {})
                complaints = records.get('clinicalDetails', {}).get('chiefComplaints', '')
        
        # Get patient name from metadata first
        patient_name = first_assessment_doc.metadata.get('patient_name')
        
        # If not in metadata or is None/empty/Unknown, try to get from loader directly
        if not patient_name or patient_name == 'Unknown' or patient_name == '':
            try:
                patient_info, _ = loader.get_patient_reports(patient_id)
                if patient_info:
                    patient_name = patient_info.get('patient_name')
                    # If still None or empty, check if we can get it from the document directly
                    if not patient_name or patient_name == 'Unknown':
                        # Try to get from the raw document if available
                        try:
                            from bson import ObjectId
                            collection = loader.db['structured-user-reports']
                            query_id = ObjectId(patient_id) if len(patient_id) == 24 else patient_id
                            patient_doc = collection.find_one({'patient_id': query_id})
                            if patient_doc:
                                patient_name = patient_doc.get('patient_name', 'Unknown')
                        except:
                            pass
            except Exception as e:
                print(f"   ⚠️  Could not fetch patient name: {e}")
        
        # Final fallback
        if not patient_name or patient_name == '':
            patient_name = 'Unknown'
        
        return {
            "patient_id": patient_id,
            "patient_name": patient_name,
            "diagnosis": diag,
            "complaints": complaints,
            "date": datetime.fromtimestamp(ts / 1000).strftime('%Y-%m-%d'),
            "timestamp": ts,
            "first_assessment_data": record
        }
    
    def list_all_patients(self, limit: Optional[int] = None, update_progress: bool = False) -> List[str]:
        """
        List all patient IDs from MongoDB.
        
        Args:
            limit: Maximum number of patients to return (None or 0 means all patients)
            update_progress: Whether to update progress tracker
        
        Returns:
            List of patient IDs
        """
        injector = MongoReportsInjector()
        patient_ids = []
        
        try:
            # Define progress callback if needed
            def progress_callback(current: int, total: int):
                if update_progress:
                    try:
                        from api.progress_tracker import set_progress
                        set_progress("running", current, total, message=f"Listing patients from MongoDB... ({current}/{total})")
                    except Exception:
                        pass
            
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("running", 0, 0, message="Listing patients from MongoDB...")
                except Exception:
                    pass
            
            # Use the loader's list_patients method with progress callback
            patients = injector.loader.list_patients(limit=limit, progress_callback=progress_callback if update_progress else None)
            patient_ids = [str(p.get('_id')) for p in patients if p.get('_id')]
            
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("running", len(patient_ids), len(patient_ids), message=f"Found {len(patient_ids)} patients. Filtering...")
                except Exception:
                    pass
        except Exception as e:
            print(f"⚠️  Error listing patients: {e}")
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("error", 0, 0, error=str(e), message="Error listing patients")
                except Exception:
                    pass
        finally:
            injector.close()
        
        return patient_ids
    
    def filter_all_patients(self, limit: Optional[int] = None, update_progress: bool = False) -> List[Dict[str, Any]]:
        """
        Filter all patients in the database.
        
        Args:
            limit: Maximum number of patients to check (None or 0 means all patients)
            update_progress: Whether to update progress tracker
        
        Returns:
            List of eligible patient records
        """
        if limit is None or limit == 0:
            print(f"📋 Listing ALL patients (no limit)...")
        else:
            print(f"📋 Listing patients (limit: {limit})...")
        
        try:
            patient_ids = self.list_all_patients(limit=limit, update_progress=update_progress)
        except Exception as e:
            print(f"❌ Error listing patients: {e}")
            import traceback
            traceback.print_exc()
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("error", 0, 0, error=str(e), message="Error listing patients")
                except Exception:
                    pass
            return []
        
        if not patient_ids:
            print("⚠️  No patients found")
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("completed", 0, 0, message="No patients found")
                except Exception:
                    pass
            return []
        
        print(f"🔍 Filtering {len(patient_ids)} patients...")
        if self.cutoff_date:
            print(f"   Cutoff date: {self.cutoff_date.strftime('%Y-%m-%d')}")
            print(f"   Criteria: FirstAssessment within last {self.months_back} months with diagnosis")
        else:
            print(f"   Criteria: FirstAssessment with diagnosis (no date limit - all patients)")
        
        if update_progress:
            try:
                from api.progress_tracker import set_progress
                set_progress("running", 0, len(patient_ids), message=f"Filtering {len(patient_ids)} patients...")
            except Exception:
                pass
        
        print(f"   Processing patients in batches...")
        eligible = self.get_filtered_patients(patient_ids, update_progress=update_progress)
        
        print(f"✅ Found {len(eligible)} eligible patients")
        if update_progress:
            try:
                from api.progress_tracker import set_progress
                set_progress("running", len(eligible), len(eligible), message=f"Found {len(eligible)} eligible patients. Starting classification...")
            except Exception:
                pass
        
        return eligible


# Example usage
if __name__ == "__main__":
    import sys
    
    # Initialize filter (default: 5 months back from today)
    filter_agent = PatientFilter(months_back=5)
    
    if len(sys.argv) > 1:
        # Filter specific patient IDs
        patient_ids = sys.argv[1:]
        print(f"🔍 Filtering specific patients: {patient_ids}")
        results = filter_agent.get_filtered_patients(patient_ids)
    else:
        # Filter all patients
        limit = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 100
        results = filter_agent.filter_all_patients(limit=limit)
    
    print(f"\n✅ Found {len(results)} eligible patients:\n")
    for record in results:
        print(f"Patient: {record['patient_name']} ({record['patient_id']})")
        print(f"  Diagnosis: {record['diagnosis']}")
        print(f"  Date: {record['date']}")
        print(f"  Complaints: {record['complaints'][:100]}..." if len(record.get('complaints', '')) > 100 else f"  Complaints: {record.get('complaints', 'N/A')}")
        print()
