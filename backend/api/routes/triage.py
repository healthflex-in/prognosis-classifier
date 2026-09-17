"""
Triage agent endpoint to trigger classification pipeline.
"""
from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import Optional
from pydantic import BaseModel
import sys
from pathlib import Path

# Add parent directories to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

router = APIRouter()


class TriageRunRequest(BaseModel):
    months_back: Optional[int] = None  # None means no date limit - all patients
    limit: Optional[int] = None  # None or 0 means all patients
    patient_ids: Optional[list[str]] = None


class TriageRunResponse(BaseModel):
    status: str
    message: str
    classifications_count: Optional[int] = None


def run_triage_agent(months_back: int = 5, limit: Optional[int] = None, patient_ids: Optional[list[str]] = None):
    """
    Background task to run the triage agent.
    """
    try:
        from LLM.classification.triage_agent import TriageAgent
        from api.progress_tracker import set_progress, reset_progress

        # Reset progress before starting
        reset_progress()
        set_progress("running", 0, 0, message="Starting triage...")
        
        agent = TriageAgent()
        
        # Run with progress tracking enabled (classifications are written directly to MongoDB)
        if patient_ids:
            classifications = agent.run_triage_pipeline(
                patient_ids=patient_ids, 
                update_progress=True,
            )
        else:
            classifications = agent.run_triage_pipeline(
                months_back=months_back, 
                limit=limit, 
                update_progress=True,
            )
        
        return {
            "status": "success",
            "classifications_count": len(classifications) if classifications else 0
        }
    except Exception as e:
        print(f"❌ Error running triage agent: {e}")
        import traceback
        traceback.print_exc()
        # Update progress with error
        try:
            from api.progress_tracker import set_progress
            set_progress("error", 0, 0, error=str(e))
        except Exception:
            pass
        return {
            "status": "error",
            "error": str(e)
        }


@router.post("/triage/run", response_model=TriageRunResponse)
async def run_triage(
    request: TriageRunRequest,
    background_tasks: BackgroundTasks
):
    """
    Trigger the triage agent to classify patients.
    This runs in the background and updates the classification JSON file.
    """
    try:
        # Add the triage agent run to background tasks
        # If limit is 0 or not provided, convert to None to mean "all patients"
        limit_value = request.limit if request.limit is not None and request.limit != 0 else None
        
        # If months_back is not provided or 0, use None to mean "all time periods" (no date limit)
        months_back_value = request.months_back if request.months_back is not None and request.months_back > 0 else None
        
        background_tasks.add_task(
            run_triage_agent,
            months_back=months_back_value,
            limit=limit_value,
            patient_ids=request.patient_ids
        )
        
        return TriageRunResponse(
            status="started",
            message="Triage agent started in background. Classification data will be updated shortly."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to start triage agent: {str(e)}"
        )


@router.get("/triage/progress", response_model=dict)
async def get_triage_progress():
    """
    Get the current progress of the triage agent run.
    """
    try:
        from api.progress_tracker import get_progress
        
        progress = get_progress()
        return progress
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get triage progress: {str(e)}"
        )


@router.get("/triage/status", response_model=dict)
async def get_triage_status():
    """
    Get the status of the latest triage classification file.
    """
    try:
        # Status now reflects Mongo-backed classifications instead of JSON files
        from api.data_loader import load_classifications

        records = load_classifications()

        if records:
            return {
                "status": "ready",
                "source": "mongo:classification",
                "record_count": len(records),
            }
        else:
            return {
                "status": "no_data",
                "message": "No classification records found in MongoDB 'classification' collection",
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get triage status: {str(e)}"
        )
