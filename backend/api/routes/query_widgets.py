"""
Query-driven widget builder routes.

Exposes a single POST /api/query/widgets endpoint that accepts a natural-language
query and returns widget specifications (and optional triage actions) produced
by the LLM-based QueryWidgetAgent.
"""

from typing import List, Dict, Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from pathlib import Path
import importlib.util
import sys

# Ensure backend root is on sys.path for imports
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))


# Load QueryWidgetAgent from backend/LLM/query/proper_react_agent.py
llm_dir = backend_dir / "LLM"
agent_path = llm_dir / "query" / "proper_react_agent.py"
spec = importlib.util.spec_from_file_location("proper_react_agent_module", agent_path)
react_agent_module = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(react_agent_module)

ProperReActQueryAgent = react_agent_module.ProperReActQueryAgent
WidgetSpec = react_agent_module.WidgetSpec
ReActQueryResponse = react_agent_module.ReActQueryResponse


router = APIRouter(prefix="/query", tags=["query"])


class QueryWidgetsRequest(BaseModel):
    """Incoming request from the frontend query bar."""

    query: str = Field(description="Natural language query from the user.")


class QueryWidgetsAPIResponse(BaseModel):
    """API response that mirrors the ReAct agent response."""

    widgets: List[WidgetSpec]
    analysis: dict  # Include the analysis for debugging


# Allowed endpoints that the agent may reference
ALLOWED_ENDPOINTS = {
    "/api/stats/diagnosis",
    "/api/stats/clinical-stage",
    "/api/stats/pain-interference",
    "/api/stats/activity-profile",
    "/api/stats/occupation",
    "/api/stats/nprs-distribution",
    "/api/stats/intent",
    "/api/stats/joint-region",
    "/api/matrix/pain-nprs",
    "/api/patients",
}


def _validate_and_normalize_agent_response(agent_resp: ReActQueryResponse) -> ReActQueryResponse:
    """
    Validate the agent output and drop/adjust anything unsafe or unsupported.
    """
    valid_widgets = []
    for w in agent_resp.widgets:
        if w.endpoint not in ALLOWED_ENDPOINTS:
            # Skip unsupported endpoints silently for now
            continue
        # Ensure refresh_interval sane
        if w.refresh_interval is None or w.refresh_interval <= 0:
            w.refresh_interval = 60
        valid_widgets.append(w)

    return ReActQueryResponse(
        analysis=agent_resp.analysis,
        widgets=valid_widgets
    )


@router.post("/widgets", response_model=QueryWidgetsAPIResponse)
async def query_widgets(body: QueryWidgetsRequest) -> QueryWidgetsAPIResponse:
    """
    Turn a natural-language query into widget specs using ReAct reasoning.

    This endpoint:
    - Invokes the ReAct-based QueryWidgetAgent.
    - Analyzes the query to understand intent (show patients vs show distributions).
    - Validates the returned endpoints against a whitelist.
    - Returns widget specs and analysis to the frontend.
    """
    try:
        agent = ProperReActQueryAgent()
        agent_resp: ReActQueryResponse = agent.run(body.query)
        validated = _validate_and_normalize_agent_response(agent_resp)

        return QueryWidgetsAPIResponse(
            widgets=validated.widgets,
            analysis=validated.analysis.model_dump()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process query: {e}")

