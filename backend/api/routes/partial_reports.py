"""
Partial-reports route.
Stores the current assessment draft fields from the frontend before recommendation generation,
with a content hash so the service can skip LLM calls when nothing has changed.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter
from pydantic import BaseModel, Field, model_validator

router = APIRouter(prefix="/partial-reports", tags=["partial-reports"])


class PartialReportPayload(BaseModel):
    report_id: Optional[str] = None
    nprs: Optional[float] = Field(default=None, ge=0, le=10, allow_inf_nan=False)
    short_term_goals: list[dict] = Field(default_factory=list)
    objective_assessment: dict = Field(default_factory=dict)
    recommendations: list[dict] = Field(default_factory=list)
    chief_complaint: Optional[str] = None
    client_history: Optional[str] = None
    subjective_assessment: Optional[str] = None
    provisional_diagnosis: Optional[str] = None

    @model_validator(mode='after')
    def validate_draft(self):
        if self.report_id:
            if not ObjectId.is_valid(self.report_id):
                raise ValueError('Invalid report ID')
            if not all(isinstance(v, str) and v.strip() for v in
                       [self.chief_complaint, self.client_history, self.subjective_assessment, self.provisional_diagnosis]):
                raise ValueError('Complete the required clinical text fields')
            if self.nprs is None or not any(isinstance(g.get('goal'), str) and g['goal'].strip() for g in self.short_term_goals):
                raise ValueError('Pain score and at least one short-term goal are required')
            tests = self.objective_assessment.get('tests')
            if not isinstance(tests, list) or not any(isinstance(t, dict) and str(t.get('testName') or '').strip() for t in tests):
                raise ValueError('At least one named objective test is required')
        return self


class PartialReportResponse(BaseModel):
    patient_id: str
    hash: str
    changed: bool  # True if hash differs from the last generated recommendation


def compute_partial_hash(fields: dict) -> str:
    canonical = json.dumps(fields, sort_keys=True, ensure_ascii=False, separators=(',', ':'), default=str)
    return sha256(canonical.encode()).hexdigest()


def _get_db():
    from utils.mongo_connection import get_mongo_db
    _, db = get_mongo_db()
    return db


@router.post("/{patient_id}", response_model=PartialReportResponse)
async def upsert_partial_report(patient_id: str, body: PartialReportPayload) -> PartialReportResponse:
    """
    Store the current form fields and compute a content hash.
    Returns changed=True if the hash differs from what was used for the last
    generated recommendation (meaning the LLM needs to run again).
    """
    db = _get_db()

    try:
        pid = ObjectId(patient_id) if len(str(patient_id)) == 24 else patient_id
    except Exception:
        pid = patient_id

    fields = body.model_dump()
    content_hash = compute_partial_hash(fields)

    db["partial-reports"].update_one(
        {"patient_id": pid},
        {
            "$set": {
                "patient_id": pid,
                "fields": fields,
                "hash": content_hash,
                "updated_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {"created_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )

    rec = db["recommendation-data"].find_one({"patient_id": pid}, {"draft_hash": 1})
    last_hash = rec.get("draft_hash") if rec else None
    changed = last_hash != content_hash

    return PartialReportResponse(patient_id=patient_id, hash=content_hash, changed=changed)
