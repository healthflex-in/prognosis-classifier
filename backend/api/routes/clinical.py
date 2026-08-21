"""
Clinical analysis routes using the LLM clinical_agent.

These endpoints allow triggering the ClinicalAnalysisAgent over HTTP,
so running backend/start_api.sh (uvicorn api.main:app) exposes this agent.
"""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from typing import Any
from pathlib import Path
import importlib.util


router = APIRouter(prefix="/clinical", tags=["clinical"])


# ----------------------------------------------------------------------------
# Load ClinicalAnalysisAgent from backend/LLM/classification/clinical_agent.py
# ----------------------------------------------------------------------------

backend_dir = Path(__file__).parent.parent.parent
clinical_agent_path = backend_dir / "LLM" / "classification" / "clinical_agent.py"

spec = importlib.util.spec_from_file_location("clinical_agent_module", clinical_agent_path)
clinical_agent_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None  # for type checkers
spec.loader.exec_module(clinical_agent_module)

ClinicalAnalysisAgent = clinical_agent_module.ClinicalAnalysisAgent
ClinicalAnalysis = clinical_agent_module.ClinicalAnalysis


class ClinicalAnalysisRequest(BaseModel):
    """Request body for clinical analysis."""
    patient_id: str


@router.post("/analyze")
async def analyze_patient_post(request: ClinicalAnalysisRequest) -> Any:
    """
    Run the ClinicalAnalysisAgent for a given patient_id (POST body).
    """
    agent = ClinicalAnalysisAgent()
    analysis: ClinicalAnalysis = agent.analyze_patient(request.patient_id)
    return analysis.model_dump()


@router.get("/analyze")
async def analyze_patient_get(patient_id: str) -> Any:
    """
    Run the ClinicalAnalysisAgent for a given patient_id (GET query param).

    Usage (browser/cURL):
      GET /api/clinical/analyze?patient_id=... 
    """
    agent = ClinicalAnalysisAgent()
    analysis: ClinicalAnalysis = agent.analyze_patient(patient_id)
    return analysis.model_dump()


@router.websocket("/ws/analyze")
async def analyze_patient_ws(websocket: WebSocket):
    """
    WebSocket endpoint for running the ClinicalAnalysisAgent.

    Protocol:
      1. Client connects to: ws://<host>:8013/api/clinical/ws/analyze
      2. Client sends a JSON message: {"patient_id": "<id>"}
      3. Server runs the agent and sends back one JSON message with the analysis
      4. Connection is then closed by the server
    """
    await websocket.accept()
    try:
        msg = await websocket.receive_json()
        patient_id = msg.get("patient_id")
        if not patient_id:
            await websocket.send_json({"error": "patient_id is required"})
            await websocket.close()
            return

        agent = ClinicalAnalysisAgent()
        analysis: ClinicalAnalysis = agent.analyze_patient(patient_id)
        await websocket.send_json(analysis.model_dump())
        await websocket.close()
    except WebSocketDisconnect:
        # Client disconnected; nothing else to do
        return
    except Exception as e:
        await websocket.send_json({"error": str(e)})
        await websocket.close()

