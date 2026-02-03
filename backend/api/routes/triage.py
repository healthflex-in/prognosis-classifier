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
        from LLM.triage_agent import TriageAgent
        from api.progress_tracker import set_progress, reset_progress
        from pathlib import Path
        from datetime import datetime
        import json
        
        # Reset progress before starting
        reset_progress()
        
        # Create output file path for incremental saving
        output_dir = Path(__file__).parent.parent.parent / "LLM"
        output_file = output_dir / f"triage_classifications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        
        # Store output file path in progress for real-time reading
        from api.progress_tracker import set_progress as set_progress_with_file
        set_progress_with_file("running", 0, 0, message="Starting triage...", output_file=str(output_file))
        
        agent = TriageAgent()
        
        # Run with progress tracking enabled and incremental file saving
        if patient_ids:
            classifications = agent.run_triage_pipeline(
                patient_ids=patient_ids, 
                update_progress=True,
                output_file=output_file
            )
        else:
            classifications = agent.run_triage_pipeline(
                months_back=months_back, 
                limit=limit, 
                update_progress=True,
                output_file=output_file
            )
        
        # Final save is already done incrementally, but verify file exists
        if classifications:
            if output_file.exists():
                print(f"\n💾 Final classifications file: {output_file}")
            else:
                # Fallback: save if file doesn't exist (shouldn't happen with incremental saves)
                with open(output_file, 'w') as f:
                    json.dump(
                        [cls.model_dump(exclude_none=False, mode='json') for cls in classifications],
                        f,
                        indent=2,
                        default=str
                    )
                print(f"\n💾 Classifications saved to: {output_file}")
        else:
            print(f"\n⚠️  No classifications to save. All patients failed or no eligible patients found.")
        
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
        from api.data_loader import find_latest_classification_file
        
        latest_file = find_latest_classification_file()
        
        if latest_file:
            import os
            from datetime import datetime
            
            file_stat = os.stat(latest_file)
            modified_time = datetime.fromtimestamp(file_stat.st_mtime)
            
            return {
                "status": "ready",
                "latest_file": str(latest_file),
                "modified_time": modified_time.isoformat(),
                "file_size": file_stat.st_size
            }
        else:
            return {
                "status": "no_data",
                "message": "No classification files found"
            }
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to get triage status: {str(e)}"
        )
