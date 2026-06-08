#!/usr/bin/env python3
"""
Load clinical reports directly from MongoDB in the new format.
Replaces the JSON file-based approach.
"""

import os
import json
from pymongo import MongoClient
from datetime import datetime
from typing import Dict, List, Tuple, Optional


class MongoReportsLoader:
    """Load and transform reports from MongoDB."""
    
    def __init__(self, mongo_uri: str = None, db_name: str = None):
        """
        Initialize MongoDB connection.
        
        Args:
            mongo_uri: MongoDB connection string (default from env or localhost)
            db_name: Database name (default from env or 'stance-dashboard')
        """
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
        self.db_name = db_name or os.getenv("MONGO_DB", "stance-dashboard")
        self.client = None
        self.db = None
        self.connect()
    
    def connect(self):
        """Connect to MongoDB."""
        try:
            # Disable SSL verification for self-signed certificates
            self.client = MongoClient(
                self.mongo_uri,
                tlsAllowInvalidCertificates=True,
                tlsAllowInvalidHostnames=True,
                serverSelectionTimeoutMS=30000,  # 30 seconds to find a server
                connectTimeoutMS=30000,  # 30 seconds to connect
                socketTimeoutMS=60000,  # 60 seconds for socket operations
                retryWrites=True,
                retryReads=True,
                maxPoolSize=50,
                minPoolSize=10,
            )
            self.db = self.client[self.db_name]
            # Test connection
            self.db.command('ping')
            print(f"✅ Connected to MongoDB: {self.db_name}")
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            raise
    
    def get_patient_reports(self, patient_id: str) -> Tuple[Dict, List[Dict]]:
        """
        Get patient data and reports from MongoDB view.
        
        Args:
            patient_id: Patient ID to fetch (as string or ObjectId)
        
        Returns:
            Tuple of (patient_info, clinical_records)
        """
        try:
            from bson import ObjectId
            
            # Query the structured-user-reports view
            collection = self.db['structured-user-reports']
            
            # Try to convert patient_id to ObjectId if it looks like one
            query_id = patient_id
            if len(patient_id) == 24:  # ObjectId length
                try:
                    query_id = ObjectId(patient_id)
                except:
                    pass
            
            # Find the patient document
            patient_doc = collection.find_one({'patient_id': query_id})
            
            if not patient_doc:
                print(f"⚠️  No reports found for patient: {patient_id}")
                return None, []
            
            # Extract patient info
            # Get patient_name, handling None, empty string, or missing field
            patient_name = patient_doc.get('patient_name')
            if not patient_name or (isinstance(patient_name, str) and patient_name.strip() == ''):
                patient_name = 'Unknown'
            
            patient_info = {
                'patient_id': str(patient_doc.get('patient_id', patient_id)),
                'patient_name': patient_name,
                'patient_seq_no': patient_doc.get('patient_seq_no', '')
            }
            
            # Get reports array
            reports = patient_doc.get('reports', [])
            
            # Transform reports to clinical data format
            clinical_data = self._transform_reports(reports)
            
            return patient_info, clinical_data
        
        except Exception as e:
            print(f"❌ Error fetching patient reports: {e}")
            import traceback
            traceback.print_exc()
            return None, []
    
    def _transform_reports(self, reports: List[Dict]) -> List[Dict]:
        """
        Transform MongoDB reports to clinical data format.
        
        Args:
            reports: List of report documents from MongoDB
        
        Returns:
            List of transformed clinical records
        """
        transformed = []
        
        for report in reports:
            # Convert ObjectId fields to strings
            report = self._convert_objectids(report)
            
            # Extract event time
            event_start_time = report.get('event_start_time', 0)
            if event_start_time:
                date_obj = datetime.fromtimestamp(event_start_time / 1000)
                date_str = date_obj.strftime("%Y-%m-%d")
            else:
                date_str = "unknown"
            
            # Extract clinical records
            records = report.get('records', {})
            clinical_details = records.get('clinicalDetails', {})
            objective = records.get('objectiveAssessment', {})
            subjective = records.get('subjectiveAssessment', {})
            diagnosis = records.get('provisionalDiagnosis', {})
            goals = records.get('objectiveGoals', [])
            recommendations = records.get('recommendations', [])
            
            # Extract objective tests
            tests = objective.get('tests', []) if isinstance(objective.get('tests'), list) else []
            
            # Create transformed record
            transformed_record = {
                'date': date_str,
                'seqNo': report.get('seqNo', ''),
                'isFirstAssessment': report.get('isFirstAssessment', False),
                'event_start_time': event_start_time,
                'consultant': report.get('consultant_name', ''),
                'specialization': report.get('specialization', ''),
                
                # Clinical details
                'chief_complaints': clinical_details.get('chiefComplaints', ''),
                'client_history': clinical_details.get('clientHistory', ''),
                'duration': clinical_details.get('duration', ''),
                'body_chart': clinical_details.get('bodyChart', ''),
                
                # Assessment
                'assessment': subjective.get('assessment', ''),
                'objective_tests': tests,
                'diagnosis': diagnosis.get('diagnosis', ''),
                
                # Goals and recommendations
                'objective_goals': goals,
                'recommendations': recommendations,
                
                # Notes
                'notes': f"{subjective.get('assessment', '')}\n\nDiagnosis: {diagnosis.get('diagnosis', '')}",
                
                # Raw data
                'raw_data': report
            }
            
            transformed.append(transformed_record)
        
        # Sort by date
        transformed.sort(key=lambda x: x['date'])
        
        # Mark first assessment
        if transformed:
            transformed[0]['isFirstAssessment'] = True
        
        return transformed
    
    def _convert_objectids(self, obj):
        """Recursively convert MongoDB ObjectId to string."""
        from bson import ObjectId
        
        if isinstance(obj, ObjectId):
            return str(obj)
        elif isinstance(obj, dict):
            return {k: self._convert_objectids(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_objectids(item) for item in obj]
        else:
            return obj
    
    def list_patients(self, limit: Optional[int] = None, progress_callback=None) -> List[Dict]:
        """
        List available patients from the view.
        
        Args:
            limit: Number of patients to return (None or 0 means all patients)
            progress_callback: Optional callback function(current, total) to report progress
        
        Returns:
            List of patient summaries
        """
        try:
            collection = self.db['structured-user-reports']
            
            # Get total count first (for progress tracking)
            total_count = None
            if limit is None or limit == 0:
                # Count all documents (this is fast with MongoDB)
                try:
                    total_count = collection.count_documents({})
                    if progress_callback:
                        progress_callback(0, total_count)
                except Exception as e:
                    print(f"   ⚠️  Could not get total count: {e}")
            else:
                total_count = limit
            
            # Use projection to only fetch necessary fields (much faster)
            projection = {
                'patient_id': 1,
                'patient_name': 1,
                'patient_seq_no': 1,
                'reports': 1
            }
            
            # Get patients from the view using cursor with batching
            # Use batch_size to control how many documents MongoDB returns per batch
            cursor = collection.find({}, projection).batch_size(1000)
            
            if limit is not None and limit > 0:
                cursor = cursor.limit(limit)
            
            # Process in batches to avoid memory issues
            summaries = []
            count = 0
            
            print(f"   Fetching patients from MongoDB...")
            for patient in cursor:
                count += 1
                if count % 100 == 0:
                    print(f"   Processed {count}{f'/{total_count}' if total_count else ''} patients...", end='\r')
                    if progress_callback and total_count:
                        progress_callback(count, total_count)
                
                summaries.append({
                    '_id': patient.get('patient_id'),
                    'patient_name': patient.get('patient_name'),
                    'patient_seq_no': patient.get('patient_seq_no'),
                    'report_count': len(patient.get('reports', [])),
                    'latest_report': max([r.get('event_start_time', 0) for r in patient.get('reports', [])], default=0)
                })
            
            # Final progress update
            if progress_callback and total_count:
                progress_callback(count, total_count)
            
            print(f"   ✅ Fetched {count} patients total")
            return summaries
        
        except Exception as e:
            print(f"❌ Error listing patients: {e}")
            return []
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            print("✅ MongoDB connection closed")


# Example usage
if __name__ == "__main__":
    loader = MongoReportsLoader()
    
    # List available patients
    print("\n👥 Available Patients:")
    patients = loader.list_patients(5)
    for patient in patients:
        print(f"  - {patient['patient_name']} ({patient['patient_seq_no']}): {patient['report_count']} reports")
        print(f"    ID: {patient['_id']}")
    
    # Load specific patient
    if patients:
        patient_id = str(patients[0]['_id'])
        print(f"\n📋 Loading reports for: {patients[0]['patient_name']}")
        patient_info, clinical_data = loader.get_patient_reports(patient_id)
        
        if patient_info:
            print(f"✓ Patient: {patient_info['patient_name']}")
            print(f"✓ Reports: {len(clinical_data)}")
            if clinical_data:
                print(f"✓ First report date: {clinical_data[0]['date']}")
                print(f"✓ Chief complaint: {clinical_data[0]['chief_complaints'][:100]}...")
                print(f"✓ Diagnosis: {clinical_data[0]['diagnosis']}")
    
    loader.close()

#!/usr/bin/env python3
"""
Load clinical reports directly from MongoDB in the new format.
Replaces the JSON file-based approach.
"""

import os
import json
from pymongo import MongoClient
from datetime import datetime
from typing import Dict, List, Tuple, Optional


class MongoReportsLoader:
    """Load and transform reports from MongoDB."""
    
    def __init__(self, mongo_uri: str = None, db_name: str = None):
        """
        Initialize MongoDB connection.
        
        Args:
            mongo_uri: MongoDB connection string (default from env or localhost)
            db_name: Database name (default from env or 'stance-dashboard')
        """
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
        self.db_name = db_name or os.getenv("MONGO_DB", "stance-dashboard")
        self.client = None
        self.db = None
        self.connect()
    
    def connect(self):
        """Connect to MongoDB."""
        try:
            # Disable SSL verification for self-signed certificates
            self.client = MongoClient(
                self.mongo_uri,
                tlsAllowInvalidCertificates=True,
                tlsAllowInvalidHostnames=True,
                serverSelectionTimeoutMS=30000,  # 30 seconds to find a server
                connectTimeoutMS=30000,  # 30 seconds to connect
                socketTimeoutMS=60000,  # 60 seconds for socket operations
                retryWrites=True,
                retryReads=True,
                maxPoolSize=50,
                minPoolSize=10,
            )
            self.db = self.client[self.db_name]
            # Test connection
            self.db.command('ping')
            print(f"✅ Connected to MongoDB: {self.db_name}")
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            raise
    
    def get_patient_reports(self, patient_id: str) -> Tuple[Dict, List[Dict]]:
        """
        Get patient data and reports from MongoDB view.
        
        Args:
            patient_id: Patient ID to fetch (as string or ObjectId)
        
        Returns:
            Tuple of (patient_info, clinical_records)
        """
        try:
            from bson import ObjectId
            
            # Query the structured-user-reports view
            collection = self.db['structured-user-reports']
            
            # Try to convert patient_id to ObjectId if it looks like one
            query_id = patient_id
            if len(patient_id) == 24:  # ObjectId length
                try:
                    query_id = ObjectId(patient_id)
                except:
                    pass
            
            # Find the patient document
            patient_doc = collection.find_one({'patient_id': query_id})
            
            if not patient_doc:
                print(f"⚠️  No reports found for patient: {patient_id}")
                return None, []
            
            # Extract patient info
            # Get patient_name, handling None, empty string, or missing field
            patient_name = patient_doc.get('patient_name')
            if not patient_name or (isinstance(patient_name, str) and patient_name.strip() == ''):
                patient_name = 'Unknown'
            
            patient_info = {
                'patient_id': str(patient_doc.get('patient_id', patient_id)),
                'patient_name': patient_name,
                'patient_seq_no': patient_doc.get('patient_seq_no', '')
            }
            
            # Get reports array
            reports = patient_doc.get('reports', [])
            
            # Transform reports to clinical data format
            clinical_data = self._transform_reports(reports)
            
            return patient_info, clinical_data
        
        except Exception as e:
            print(f"❌ Error fetching patient reports: {e}")
            import traceback
            traceback.print_exc()
            return None, []
    
    def _transform_reports(self, reports: List[Dict]) -> List[Dict]:
        """
        Transform MongoDB reports to clinical data format.
        
        Args:
            reports: List of report documents from MongoDB
        
        Returns:
            List of transformed clinical records
        """
        transformed = []
        
        for report in reports:
            # Convert ObjectId fields to strings
            report = self._convert_objectids(report)
            
            # Extract event time
            event_start_time = report.get('event_start_time', 0)
            if event_start_time:
                date_obj = datetime.fromtimestamp(event_start_time / 1000)
                date_str = date_obj.strftime("%Y-%m-%d")
            else:
                date_str = "unknown"
            
            # Extract clinical records
            records = report.get('records', {})
            clinical_details = records.get('clinicalDetails', {})
            objective = records.get('objectiveAssessment', {})
            subjective = records.get('subjectiveAssessment', {})
            diagnosis = records.get('provisionalDiagnosis', {})
            goals = records.get('objectiveGoals', [])
            recommendations = records.get('recommendations', [])
            
            # Extract objective tests
            tests = objective.get('tests', []) if isinstance(objective.get('tests'), list) else []
            
            # Create transformed record
            transformed_record = {
                'date': date_str,
                'seqNo': report.get('seqNo', ''),
                'isFirstAssessment': report.get('isFirstAssessment', False),
                'event_start_time': event_start_time,
                'consultant': report.get('consultant_name', ''),
                'specialization': report.get('specialization', ''),
                
                # Clinical details
                'chief_complaints': clinical_details.get('chiefComplaints', ''),
                'client_history': clinical_details.get('clientHistory', ''),
                'duration': clinical_details.get('duration', ''),
                'body_chart': clinical_details.get('bodyChart', ''),
                
                # Assessment
                'assessment': subjective.get('assessment', ''),
                'objective_tests': tests,
                'diagnosis': diagnosis.get('diagnosis', ''),
                
                # Goals and recommendations
                'objective_goals': goals,
                'recommendations': recommendations,
                
                # Notes
                'notes': f"{subjective.get('assessment', '')}\n\nDiagnosis: {diagnosis.get('diagnosis', '')}",
                
                # Raw data
                'raw_data': report
            }
            
            transformed.append(transformed_record)
        
        # Sort by date
        transformed.sort(key=lambda x: x['date'])
        
        # Mark first assessment
        if transformed:
            transformed[0]['isFirstAssessment'] = True
        
        return transformed
    
    def _convert_objectids(self, obj):
        """Recursively convert MongoDB ObjectId to string."""
        from bson import ObjectId
        
        if isinstance(obj, ObjectId):
            return str(obj)
        elif isinstance(obj, dict):
            return {k: self._convert_objectids(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._convert_objectids(item) for item in obj]
        else:
            return obj
    
    def list_patients(self, limit: Optional[int] = None, progress_callback=None) -> List[Dict]:
        """
        List available patients from the view.
        
        Args:
            limit: Number of patients to return (None or 0 means all patients)
            progress_callback: Optional callback function(current, total) to report progress
        
        Returns:
            List of patient summaries
        """
        try:
            collection = self.db['structured-user-reports']
            
            # Get total count first (for progress tracking)
            total_count = None
            if limit is None or limit == 0:
                # Count all documents (this is fast with MongoDB)
                try:
                    total_count = collection.count_documents({})
                    if progress_callback:
                        progress_callback(0, total_count)
                except Exception as e:
                    print(f"   ⚠️  Could not get total count: {e}")
            else:
                total_count = limit
            
            # Use projection to only fetch necessary fields (much faster)
            projection = {
                'patient_id': 1,
                'patient_name': 1,
                'patient_seq_no': 1,
                'reports': 1
            }
            
            # Get patients from the view using cursor with batching
            # Use batch_size to control how many documents MongoDB returns per batch
            cursor = collection.find({}, projection).batch_size(1000)
            
            if limit is not None and limit > 0:
                cursor = cursor.limit(limit)
            
            # Process in batches to avoid memory issues
            summaries = []
            count = 0
            
            print(f"   Fetching patients from MongoDB...")
            for patient in cursor:
                count += 1
                if count % 100 == 0:
                    print(f"   Processed {count}{f'/{total_count}' if total_count else ''} patients...", end='\r')
                    if progress_callback and total_count:
                        progress_callback(count, total_count)
                
                summaries.append({
                    '_id': patient.get('patient_id'),
                    'patient_name': patient.get('patient_name'),
                    'patient_seq_no': patient.get('patient_seq_no'),
                    'report_count': len(patient.get('reports', [])),
                    'latest_report': max([r.get('event_start_time', 0) for r in patient.get('reports', [])], default=0)
                })
            
            # Final progress update
            if progress_callback and total_count:
                progress_callback(count, total_count)
            
            print(f"   ✅ Fetched {count} patients total")
            return summaries
        
        except Exception as e:
            print(f"❌ Error listing patients: {e}")
            return []
    
    def close(self):
        """Close MongoDB connection."""
        if self.client:
            self.client.close()
            print("✅ MongoDB connection closed")


# Example usage
if __name__ == "__main__":
    loader = MongoReportsLoader()
    
    # List available patients
    print("\n👥 Available Patients:")
    patients = loader.list_patients(5)
    for patient in patients:
        print(f"  - {patient['patient_name']} ({patient['patient_seq_no']}): {patient['report_count']} reports")
        print(f"    ID: {patient['_id']}")
    
    # Load specific patient
    if patients:
        patient_id = str(patients[0]['_id'])
        print(f"\n📋 Loading reports for: {patients[0]['patient_name']}")
        patient_info, clinical_data = loader.get_patient_reports(patient_id)
        
        if patient_info:
            print(f"✓ Patient: {patient_info['patient_name']}")
            print(f"✓ Reports: {len(clinical_data)}")
            if clinical_data:
                print(f"✓ First report date: {clinical_data[0]['date']}")
                print(f"✓ Chief complaint: {clinical_data[0]['chief_complaints'][:100]}...")
                print(f"✓ Diagnosis: {clinical_data[0]['diagnosis']}")
    
    loader.close()
