"""
Partial-reports route.
Stores the 4 key form fields from the frontend before recommendation generation,
with a content hash so the service can skip LLM calls when nothing has changed.
"""

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Optional

from bson import ObjectId
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/partial-reports", tags=["partial-reports"])


class PartialReportPayload(BaseModel):
    chief_complaint: Optional[str] = None
    client_history: Optional[str] = None
    subjective_assessment: Optional[str] = None
    provisional_diagnosis: Optional[str] = None


class PartialReportResponse(BaseModel):
    patient_id: str
    hash: str
    changed: bool  # True if hash differs from the last generated recommendation


def compute_partial_hash(fields: dict) -> str:
    canonical = json.dumps(
        {k: (v or "").strip() for k, v in sorted(fields.items())},
        ensure_ascii=False,
    )
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

    fields = {
        "chief_complaint":      (body.chief_complaint or "").strip(),
        "client_history":       (body.client_history or "").strip(),
        "subjective_assessment":(body.subjective_assessment or "").strip(),
        "provisional_diagnosis":(body.provisional_diagnosis or "").strip(),
    }
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

    rec = db["recommendation-data"].find_one({"patient_id": pid}, {"input_hash": 1})
    last_hash = rec.get("input_hash") if rec else None
    changed = last_hash != content_hash

    return PartialReportResponse(patient_id=patient_id, hash=content_hash, changed=changed)
