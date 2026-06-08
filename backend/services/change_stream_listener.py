#!/usr/bin/env python3
"""
MongoDB Change Stream Listener for automatic patient classification.

Listens for changes in patient data and automatically runs classification
for the affected patient(s), updating the classification collection.
"""

import os
import sys
import threading
import time
from typing import Optional, Dict, Any, List
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient
from pymongo.errors import OperationFailure, PyMongoError
from bson import ObjectId

# Add backend to path
backend_dir = Path(__file__).parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

# Load environment variables
try:
    from dotenv import load_dotenv
    backend_env = backend_dir / ".env"
    root_env = backend_dir.parent / ".env"
    if backend_env.exists():
        load_dotenv(backend_env)
    elif root_env.exists():
        load_dotenv(root_env)
    else:
        load_dotenv()
except ImportError:
    pass

from LLM.prognosis.prognosis_agent import ClinicalPrognosisAgent
from LLM.prognosis.push_prognosis_to_mongo import save_to_mongo, build_patient_data_from_reports


class ChangeStreamListener:
    """
    MongoDB Change Stream Listener for automatic patient classification.
    
    Listens for changes in patient data collections and automatically
    triggers classification for affected patients.
    """
    
    def __init__(
        self,
        mongo_uri: Optional[str] = None,
        db_name: Optional[str] = None,
        collections_to_watch: Optional[List[str]] = None
    ):
        """
        Initialize the change stream listener.
        
        Args:
            mongo_uri: MongoDB connection string (defaults to env var)
            db_name: Database name (defaults to env var or 'stance-dashboard')
            collections_to_watch: List of collection names to watch. If None, watches
                                 'structured-user-reports' and common report collections
        """
        self.mongo_uri = mongo_uri or os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        if not self.mongo_uri:
            raise ValueError("MongoDB URI not provided and MONGO_URI env var not set")
        
        self.db_name = db_name or os.getenv("MONGO_DB", "stance-dashboard")
        self.client: Optional[MongoClient] = None
        self.db = None
        self.is_running = False
        self.listener_thread: Optional[threading.Thread] = None
        self.stop_event = threading.Event()
        
        # Collections to watch - try view first, then fallback to common collections
        if collections_to_watch is None:
            # Try to watch the view, but also watch underlying collections if view doesn't support change streams
            self.collections_to_watch = [
                'structured-user-reports',  # View (may not support change streams)
                'user-reports',             # Common underlying collection
                'reports',                  # Alternative collection name
                'assessments'               # Another possible collection
            ]
        else:
            self.collections_to_watch = collections_to_watch
        
        # Initialize prognosis agent — listener now generates prognosis docs (not triage)
        self.prognosis_agent = ClinicalPrognosisAgent()
        
        # Track processed changes to avoid duplicates
        self.processed_changes: Dict[str, float] = {}  # {patient_id: timestamp}
        self.change_debounce_seconds = 5  # Wait 5 seconds before processing same patient again
        
        # Statistics
        self.stats = {
            'total_changes': 0,
            'processed_patients': 0,
            'failed_classifications': 0,
            'started_at': None,
            'last_change_at': None
        }
    
    def connect(self):
        """Connect to MongoDB."""
        try:
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
            print(f"✅ Change stream listener connected to MongoDB: {self.db_name}")
        except Exception as e:
            print(f"❌ MongoDB connection failed: {e}")
            raise
    
    def _extract_patient_id_from_change(self, change_doc: Dict[str, Any]) -> Optional[str]:
        """
        Extract patient_id from a change document.
        
        Args:
            change_doc: MongoDB change stream document
            
        Returns:
            Patient ID as string, or None if not found
        """
        try:
            # Get the document from the change
            full_document = change_doc.get('fullDocument')
            document_key = change_doc.get('documentKey', {})
            
            # Try different ways to extract patient_id
            patient_id = None
            
            # Method 1: From fullDocument — try every known patient-reference field.
            # For the `reports` collection the patient is in `patient` (ObjectId ref → users._id).
            # Never fall back to fullDocument._id — that's the document's own id, not a patient id.
            if full_document:
                for k in ('patient_id', 'patient', 'patientId', 'user_id', 'userId'):
                    v = full_document.get(k)
                    if v:
                        patient_id = v
                        break

            # Method 2: From updateDescription (for partial-update events with no fullDocument)
            if not patient_id:
                update_desc = change_doc.get('updateDescription', {})
                updated_fields = update_desc.get('updatedFields', {}) or {}
                for k in ('patient_id', 'patient', 'patientId'):
                    if k in updated_fields and updated_fields[k]:
                        patient_id = updated_fields[k]
                        break
            
            # Convert ObjectId to string
            if isinstance(patient_id, ObjectId):
                patient_id = str(patient_id)
            elif patient_id:
                patient_id = str(patient_id)
            
            return patient_id if patient_id else None
            
        except Exception as e:
            print(f"⚠️  Error extracting patient_id from change: {e}")
            return None
    
    def _should_process_change(self, patient_id: str) -> bool:
        """
        Check if a change should be processed (debounce logic).
        
        Args:
            patient_id: Patient ID to check
            
        Returns:
            True if should process, False if should skip (debounced)
        """
        if not patient_id:
            return False
        
        current_time = time.time()
        last_processed = self.processed_changes.get(patient_id, 0)
        
        # If enough time has passed since last processing, allow it
        if current_time - last_processed >= self.change_debounce_seconds:
            self.processed_changes[patient_id] = current_time
            # Clean up old entries (older than 1 hour)
            cutoff_time = current_time - 3600
            self.processed_changes = {
                pid: ts for pid, ts in self.processed_changes.items()
                if ts > cutoff_time
            }
            return True
        
        return False
    
    def _classify_patient_from_change(self, patient_id: str):
        """
        Generate a prognosis for a patient based on a change event.
        Reads the patient's first-assessment report directly from `reports` so
        we can reach patients the structured-user-reports view filters out.
        """
        try:
            print(f"🔄 Processing change for patient: {patient_id}")

            # Build the agent input from the first-assessment report + VALD.
            # Shared with the prognosis queue worker so every path is identical.
            patient_data = build_patient_data_from_reports(self.db, patient_id)
            if not patient_data:
                print(f"⚠️  No usable first-assessment report for {patient_id}, skipping")
                return
            patient_name = patient_data["patient_name"]

            analysis = self.prognosis_agent.analyze_patient_prognosis(patient_data)
            save_to_mongo(self.db, patient_data["patient_id"], analysis)
            self.stats['processed_patients'] += 1
            print(f"✅ Prognosis saved for {patient_id} ({patient_name}): "
                  f"T{analysis.probability_tier.tier} — {analysis.provisional_diagnosis[:60]}")

        except Exception as e:
            self.stats['failed_classifications'] += 1
            print(f"❌ Error generating prognosis for {patient_id}: {e}")
            import traceback
            traceback.print_exc()
    
    def _save_classification_to_mongo(self, classification):
        """
        Save a single classification to MongoDB.
        
        Args:
            classification: TriageClassification object
        """
        try:
            from pymongo import UpdateOne
            from bson import ObjectId
            
            # Get MongoDB collection
            mongo_db = self.client[self.db_name]
            collection = mongo_db["classification"]
            
            # Convert to dict
            classification_dict = classification.model_dump(exclude_none=False, mode='json')
            patient_id = classification_dict.get('patient_id', '')
            
            # Convert patient_id to ObjectId
            try:
                if isinstance(patient_id, str) and len(patient_id) == 24:
                    patient_id_obj = ObjectId(patient_id)
                elif isinstance(patient_id, ObjectId):
                    patient_id_obj = patient_id
                else:
                    patient_id_obj = ObjectId(patient_id)
                
                # Store as ObjectId in document
                classification_dict['patient_id'] = patient_id_obj
                patient_id_for_query = patient_id_obj
            except (ValueError, TypeError):
                print(f"⚠️  Warning: patient_id '{patient_id}' is not a valid ObjectId, storing as string")
                patient_id_for_query = patient_id
            
            classification_dict['updated_at'] = datetime.utcnow()
            
            # Upsert by patient_id
            filter_doc = {'patient_id': patient_id_for_query}
            update_doc = {'$set': classification_dict, '$setOnInsert': {'created_at': datetime.utcnow()}}
            
            collection.update_one(filter_doc, update_doc, upsert=True)
            
        except Exception as e:
            print(f"❌ Error saving classification to MongoDB: {e}")
            raise
    
    def _watch_collection(self, collection_name: str):
        """
        Watch a specific collection for changes.
        
        Args:
            collection_name: Name of collection to watch
        """
        try:
            collection = self.db[collection_name]
            
            # Try to watch the collection
            # Note: Change streams may not work on views, so we'll catch that error
            change_stream = collection.watch(
                [{'$match': {'operationType': {'$in': ['insert', 'update', 'replace']}}}],
                full_document='updateLookup'
            )
            
            print(f"👂 Listening for changes in collection: {collection_name}")
            
            for change in change_stream:
                if self.stop_event.is_set():
                    break
                
                self.stats['total_changes'] += 1
                self.stats['last_change_at'] = datetime.utcnow()
                
                # Extract patient_id
                patient_id = self._extract_patient_id_from_change(change)
                
                if patient_id and self._should_process_change(patient_id):
                    # Process in a separate thread to avoid blocking
                    thread = threading.Thread(
                        target=self._classify_patient_from_change,
                        args=(patient_id,),
                        daemon=True
                    )
                    thread.start()
                
        except OperationFailure as e:
            if 'change streams' in str(e).lower() or 'view' in str(e).lower():
                print(f"⚠️  Collection '{collection_name}' does not support change streams (likely a view), skipping...")
            else:
                print(f"❌ Error watching collection '{collection_name}': {e}")
        except PyMongoError as e:
            print(f"❌ MongoDB error watching '{collection_name}': {e}")
        except Exception as e:
            print(f"❌ Unexpected error watching '{collection_name}': {e}")
            import traceback
            traceback.print_exc()
    
    def _listener_worker(self):
        """Main worker thread that watches all collections."""
        print("🚀 Change stream listener started")
        self.stats['started_at'] = datetime.utcnow()
        
        # Get list of actual collections (exclude views)
        available_collections = self.db.list_collection_names()
        
        # Try to watch each collection
        watched_count = 0
        for collection_name in self.collections_to_watch:
            if self.stop_event.is_set():
                break
            
            try:
                # Check if collection exists
                if collection_name in available_collections:
                    # Try to watch - this will fail silently for views
                    try:
                        # Test if change streams are supported
                        test_stream = self.db[collection_name].watch([], max_await_time_ms=100)
                        test_stream.close()
                        
                        # If we get here, change streams are supported
                        watched_count += 1
                        # Watch in a separate thread so we can watch multiple collections
                        watch_thread = threading.Thread(
                            target=self._watch_collection,
                            args=(collection_name,),
                            daemon=True
                        )
                        watch_thread.start()
                        print(f"✅ Started watching collection: {collection_name}")
                    except OperationFailure as e:
                        if 'change streams' in str(e).lower() or 'view' in str(e).lower():
                            print(f"⚠️  Collection '{collection_name}' does not support change streams (likely a view), skipping...")
                        else:
                            print(f"⚠️  Cannot watch collection '{collection_name}': {e}")
                    except Exception as e:
                        print(f"⚠️  Error testing collection '{collection_name}': {e}")
                else:
                    print(f"⚠️  Collection '{collection_name}' not found, skipping...")
            except Exception as e:
                print(f"⚠️  Error checking collection '{collection_name}': {e}")
                continue
        
        if watched_count == 0:
            print("⚠️  No collections could be watched. Make sure:")
            print("   1. The collections exist in the database")
            print("   2. The collections are not views (views don't support change streams)")
            print("   3. You have proper MongoDB permissions for change streams")
            print("   4. MongoDB replica set is configured (change streams require replica set)")
        else:
            print(f"✅ Successfully watching {watched_count} collection(s)")
        
        # Keep the main thread alive
        while not self.stop_event.is_set():
            time.sleep(1)
        
        print("🛑 Change stream listener stopped")
    
    def start(self):
        """Start the change stream listener in a background thread."""
        if self.is_running:
            print("⚠️  Change stream listener is already running")
            return
        
        if not self.client:
            self.connect()
        
        self.is_running = True
        self.stop_event.clear()
        
        self.listener_thread = threading.Thread(target=self._listener_worker, daemon=True)
        self.listener_thread.start()
        
        print("✅ Change stream listener started in background")
    
    def stop(self):
        """Stop the change stream listener."""
        if not self.is_running:
            print("⚠️  Change stream listener is not running")
            return
        
        self.is_running = False
        self.stop_event.set()
        
        if self.listener_thread:
            self.listener_thread.join(timeout=5)
        
        print("✅ Change stream listener stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get listener statistics."""
        return {
            **self.stats,
            'is_running': self.is_running,
            'collections_watched': self.collections_to_watch
        }
    
    def close(self):
        """Close MongoDB connections."""
        self.stop()
        if self.mongo_loader:
            self.mongo_loader.close()
        if self.client:
            self.client.close()
        print("✅ Change stream listener closed")


# Global instance
_listener_instance: Optional[ChangeStreamListener] = None


def get_listener() -> Optional[ChangeStreamListener]:
    """Get the global change stream listener instance."""
    return _listener_instance


def start_listener() -> ChangeStreamListener:
    """Start the global change stream listener."""
    global _listener_instance
    
    if _listener_instance and _listener_instance.is_running:
        return _listener_instance
    
    _listener_instance = ChangeStreamListener()
    _listener_instance.start()
    return _listener_instance


def stop_listener():
    """Stop the global change stream listener."""
    global _listener_instance
    
    if _listener_instance:
        _listener_instance.stop()


# Example usage
if __name__ == "__main__":
    listener = ChangeStreamListener()
    
    try:
        listener.start()
        print("Change stream listener running. Press Ctrl+C to stop...")
        
        # Keep running
        while True:
            time.sleep(1)
            stats = listener.get_stats()
            if stats['total_changes'] > 0:
                print(f"\n📊 Stats: {stats['total_changes']} changes, "
                      f"{stats['processed_patients']} processed, "
                      f"{stats['failed_classifications']} failed")
    
    except KeyboardInterrupt:
        print("\n🛑 Stopping listener...")
        listener.stop()
        listener.close()
