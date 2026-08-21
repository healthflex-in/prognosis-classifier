"""
API routes for MongoDB change stream listener.
Controls automatic patient classification on data changes.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

from services.change_stream_listener import (
    get_listener,
    start_listener,
    stop_listener,
    ChangeStreamListener
)

router = APIRouter()


class ChangeStreamStatus(BaseModel):
    """Status of the change stream listener."""
    is_running: bool
    stats: Dict[str, Any]
    collections_watched: list


@router.post("/change-stream/start")
async def start_change_stream():
    """
    Start the MongoDB change stream listener.
    
    This will automatically classify patients when their data changes
    in the monitored collections.
    """
    try:
        listener = start_listener()
        return {
            "status": "started",
            "message": "Change stream listener started successfully",
            "is_running": listener.is_running,
            "collections_watched": listener.collections_to_watch
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to start change stream: {str(e)}")


@router.post("/change-stream/stop")
async def stop_change_stream():
    """
    Stop the MongoDB change stream listener.
    """
    try:
        stop_listener()
        return {
            "status": "stopped",
            "message": "Change stream listener stopped successfully"
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to stop change stream: {str(e)}")


@router.get("/change-stream/status")
async def get_change_stream_status():
    """
    Get the current status of the change stream listener.
    """
    try:
        listener = get_listener()
        
        if not listener:
            return {
                "is_running": False,
                "message": "Change stream listener not initialized",
                "stats": {},
                "collections_watched": []
            }
        
        stats = listener.get_stats()
        return {
            "is_running": listener.is_running,
            "stats": stats,
            "collections_watched": listener.collections_to_watch
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to get status: {str(e)}")


@router.post("/change-stream/classify-patient/{patient_id}")
async def classify_single_patient(patient_id: str):
    """
    Manually trigger classification for a single patient.
    
    This is useful for testing or manually re-classifying a patient
    without waiting for a change stream event.
    """
    try:
        from services.change_stream_listener import ChangeStreamListener
        from load_reports_from_mongo import MongoReportsLoader
        from LLM.classification.triage_agent import TriageAgent
        import os
        
        # Initialize components
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI")
        db_name = os.getenv("MONGO_DB", "stance-dashboard")
        
        loader = MongoReportsLoader(mongo_uri=mongo_uri, db_name=db_name)
        agent = TriageAgent()
        
        # Load patient data
        patient_info, clinical_data = loader.get_patient_reports(patient_id)
        
        if not patient_info or not clinical_data:
            raise HTTPException(
                status_code=404,
                detail=f"Patient {patient_id} not found or has no data"
            )
        
        # Find first assessment
        first_assessment = None
        for record in clinical_data:
            if record.get('isFirstAssessment') is True:
                first_assessment = record
                break
        
        if not first_assessment:
            raise HTTPException(
                status_code=400,
                detail=f"Patient {patient_id} has no first assessment"
            )
        
        # Extract data
        diagnosis = first_assessment.get('diagnosis', '')
        complaints = first_assessment.get('chief_complaints', '')
        assessment_date = first_assessment.get('date')
        patient_name = patient_info.get('patient_name', 'Unknown')
        
        # Classify
        classification = agent.classify_patient(
            patient_id=patient_id,
            diagnosis=diagnosis,
            complaints=complaints,
            assessment_date=assessment_date,
            patient_name=patient_name,
            full_patient_record=first_assessment
        )
        
        if not classification:
            raise HTTPException(
                status_code=500,
                detail="Classification failed"
            )
        
        # Save to MongoDB
        from pymongo import MongoClient
        from bson import ObjectId
        from datetime import datetime
        
        client = MongoClient(
            mongo_uri,
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
        db = client[db_name]
        collection = db["classification"]
        
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
        
        filter_doc = {'patient_id': patient_id_for_query}
        update_doc = {'$set': classification_dict, '$setOnInsert': {'created_at': datetime.utcnow()}}
        
        collection.update_one(filter_doc, update_doc, upsert=True)
        
        client.close()
        loader.close()
        
        # Extract classification fields for response
        extracted = classification.extracted_fields
        canonical_label = extracted.provisional_diagnosis.canonical_label if extracted.provisional_diagnosis else "Unclear"
        
        return {
            "status": "success",
            "message": f"Patient {patient_id} classified successfully",
            "patient_id": str(patient_id),  # Convert to string for JSON response
            "patient_name": patient_name,
            "classification": {
                "canonical_label": canonical_label,
                "primary_joint": extracted.joint_mapping.primary_joint if extracted.joint_mapping else "Unclear",
                "clinical_stage": extracted.clinical_stage.stage if extracted.clinical_stage else "Unclear"
            }
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to classify patient: {str(e)}"
        )
