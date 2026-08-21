"""
Recommendation API routes.
Fetches AI-generated patient-facing retention fields stored in the `recommendation-data` collection.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import sys

from bson import ObjectId
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

router = APIRouter(prefix="/recommendation", tags=["recommendation"])


# ── Pydantic models ───────────────────────────────────────────────────────────

class RecommendationResponse(BaseModel):
    patient_id: str
    top_3_action_areas: List[str]
    next_session_plan: str
    generated_at: Optional[str] = None


# ── DB helper ─────────────────────────────────────────────────────────────────

def _get_db():
    from utils.mongo_connection import get_mongo_db
    _, db = get_mongo_db()
    return db


# ── Data builder ──────────────────────────────────────────────────────────────

def build_recommendation_input(db, patient_id: str) -> Optional[Dict[str, Any]]:
    """
    Assemble all first-assessment report fields (except document, advice, clinical notes)
    into the input dict consumed by RecommendationAgent.generate().
    """
    pid_obj = ObjectId(patient_id) if len(str(patient_id)) == 24 else patient_id

    user = db.users.find_one({"_id": pid_obj})
    if not user:
        return None
    if user.get("userType") and user.get("userType") != "PATIENT":
        return None

    profile = user.get("profileData") or {}
    patient_name = f"{profile.get('firstName', '')} {profile.get('lastName', '')}".strip() or "Unknown"

    report = db.reports.find_one({"patient": pid_obj, "isFirstAssessment": True})
    if not report:
        return None
    records = report.get("records") or {}
    if not records:
        return None

    # ── Extract all fields except: document, advice, bodyChart, clinicalNotes ─
    clinical = records.get("clinicalDetails") or {}
    subjective = records.get("subjectiveAssessment") or {}
    objective_raw = records.get("objectiveAssessment") or {}
    prov_dx = records.get("provisionalDiagnosis") or {}
    # Goals from multiple possible locations
    func_goals = records.get("functionalGoals") or records.get("goals") or {}
    subjective_goals_list = records.get("subjectiveGoals") or []

    # Existing recommendations (session type / frequency / plans)
    recs_raw = records.get("recommendations") or []
    rec_lines = []
    for r in recs_raw:
        if not r:
            continue
        parts = []
        if r.get("sessionType"):
            parts.append(r["sessionType"])
        if r.get("frequency"):
            parts.append(r["frequency"])
        if r.get("sessionCount"):
            parts.append(f"{r['sessionCount']} sessions")
        if r.get("plans"):
            parts.append(r["plans"])
        if parts:
            rec_lines.append(" · ".join(parts))
    existing_recommendations = "; ".join(rec_lines) if rec_lines else ""

    # Objective assessment — flatten tests array into readable lines
    obj_parts = []
    tests = []
    if isinstance(objective_raw, dict):
        tests = objective_raw.get("tests") or []
        for key in ("assessment", "findings", "notes", "observation"):
            val = objective_raw.get(key)
            if val and isinstance(val, str) and val.strip():
                obj_parts.append(val.strip())
    elif isinstance(objective_raw, list):
        for item in objective_raw:
            if isinstance(item, dict):
                tests.extend(item.get("tests") or [])
    for t in tests:
        if not t:
            continue
        name = t.get("testName") or ""
        comments = t.get("comments") or ""
        left = t.get("left")
        right = t.get("right")
        value = t.get("value")
        parts = [name]
        if left is not None or right is not None:
            parts.append(f"L:{left} R:{right}")
        elif value is not None:
            parts.append(str(value))
        if comments:
            parts.append(comments)
        obj_parts.append(" ".join(p for p in parts if p))
    objective_notes = " | ".join(obj_parts) if obj_parts else ""

    # Patient goals — check all known locations
    goal_texts = []
    # Structured subjective goals list (e.g. [{goal: "..."}])
    for g in subjective_goals_list:
        if isinstance(g, dict):
            txt = g.get("goal") or g.get("description") or ""
            if txt.strip():
                goal_texts.append(txt.strip())
    # Flat goal fields
    for src in (func_goals, subjective):
        for key in ("goals", "patientGoals", "description", "goal"):
            val = src.get(key) if isinstance(src, dict) else None
            if val and isinstance(val, str) and val.strip():
                goal_texts.append(val.strip())
    patient_goals = "; ".join(dict.fromkeys(goal_texts)) if goal_texts else "Not explicitly documented"

    # Duration inference (simple heuristic from onset/history text)
    history_text = clinical.get("clientHistory") or ""
    duration_months = None  # not stored as a number in reports directly

    # VALD data
    try:
        from utils.vald_extractor import extract_vald_first_session
        vald = extract_vald_first_session(db, str(pid_obj))
    except Exception:
        vald = {
            "vald_exercises": {},
            "strength_asymmetry_percent": None,
            "rom_asymmetry_degrees": None,
            "absolute_force_level": None,
        }

    return {
        "patient_id": str(pid_obj),
        "patient_name": patient_name,
        "source_data": {
            "provisional_diagnosis_raw": (prov_dx.get("diagnosis") or "").strip(),
            "chief_complaint": clinical.get("chiefComplaints") or "",
            "clinical_history": history_text,
            "subjective_notes": subjective.get("assessment") or "",
            "objective_notes": objective_notes,
            "existing_recommendations": existing_recommendations,
            "patient_goals": patient_goals or "Not explicitly documented",
        },
        "extracted_fields": {
            "duration_months": duration_months,
            "joint_mapping": {"primary_joint": "Unknown", "functional_region": "unknown"},
            "clinical_stage": {"stage": "unknown"},
        },
        "strength_asymmetry_percent": vald["strength_asymmetry_percent"],
        "rom_asymmetry_degrees": vald["rom_asymmetry_degrees"],
        "absolute_force_level": vald["absolute_force_level"],
        "vald_exercises": vald["vald_exercises"],
    }


def save_recommendation(db, patient_id: str, output, input_hash: Optional[str] = None) -> None:
    col = db["recommendation-data"]
    try:
        pid = ObjectId(patient_id) if len(str(patient_id)) == 24 else patient_id
    except Exception:
        pid = patient_id

    set_doc: Dict[str, Any] = {
        "patient_id": pid,
        "top_3_action_areas": output.top_3_action_areas,
        "next_session_plan": output.next_session_plan,
        "updated_at": datetime.now(timezone.utc),
    }
    if input_hash is not None:
        set_doc["input_hash"] = input_hash

    col.update_one(
        {"patient_id": pid},
        {
            "$set": set_doc,
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/{patient_id}", response_model=RecommendationResponse)
async def get_recommendation(patient_id: str) -> RecommendationResponse:
    """Fetch the stored AI recommendation for a patient."""
    db = _get_db()
    col = db["recommendation-data"]

    try:
        pid = ObjectId(patient_id) if len(str(patient_id)) == 24 else patient_id
    except Exception:
        pid = patient_id

    doc = col.find_one({"patient_id": pid})
    if not doc:
        raise HTTPException(status_code=404, detail="No recommendation found for this patient")

    generated_at = None
    for ts_field in ("updated_at", "created_at"):
        ts = doc.get(ts_field)
        if ts:
            generated_at = ts.isoformat() if hasattr(ts, "isoformat") else str(ts)
            break

    return RecommendationResponse(
        patient_id=patient_id,
        top_3_action_areas=doc.get("top_3_action_areas", []),
        next_session_plan=doc.get("next_session_plan", ""),
        generated_at=generated_at,
    )


class RecommendationPatch(BaseModel):
    top_3_action_areas: Optional[List[str]] = None
    next_session_plan: Optional[str] = None


@router.patch("/{patient_id}", response_model=RecommendationResponse)
async def patch_recommendation(patient_id: str, body: RecommendationPatch) -> RecommendationResponse:
    """Update stored recommendation fields (clinician edits)."""
    db = _get_db()
    col = db["recommendation-data"]

    try:
        pid = ObjectId(patient_id) if len(str(patient_id)) == 24 else patient_id
    except Exception:
        pid = patient_id

    updates: Dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
    if body.top_3_action_areas is not None:
        updates["top_3_action_areas"] = body.top_3_action_areas
    if body.next_session_plan is not None:
        updates["next_session_plan"] = body.next_session_plan

    result = col.update_one(
        {"patient_id": pid},
        {"$set": updates, "$setOnInsert": {"created_at": datetime.now(timezone.utc)}},
        upsert=True,
    )

    doc = col.find_one({"patient_id": pid})
    return RecommendationResponse(
        patient_id=patient_id,
        top_3_action_areas=doc.get("top_3_action_areas", []),
        next_session_plan=doc.get("next_session_plan", ""),
        generated_at=updates["updated_at"].isoformat(),
    )


@router.post("/generate/{patient_id}", response_model=RecommendationResponse)
async def generate_recommendation(patient_id: str) -> RecommendationResponse:
    """Generate and persist the AI recommendation for a patient (synchronous)."""
    import asyncio

    db = _get_db()
    patient_data = await asyncio.to_thread(build_recommendation_input, db, patient_id)
    if not patient_data:
        raise HTTPException(status_code=404, detail="No usable first-assessment report found")

    from LLM.recommendation.recommendation_agent import RecommendationAgent
    agent = RecommendationAgent()
    output = await asyncio.to_thread(agent.generate, patient_data)
    await asyncio.to_thread(save_recommendation, db, patient_id, output)

    return RecommendationResponse(
        patient_id=patient_id,
        top_3_action_areas=output.top_3_action_areas,
        next_session_plan=output.next_session_plan,
    )
