#!/usr/bin/env python3
"""
Batch push prognosis analyses to MongoDB 'prognosis' collection.

Usage:
  python push_prognosis_to_mongo.py                  # all patients
  python push_prognosis_to_mongo.py --limit 10       # first N patients
  python push_prognosis_to_mongo.py --patient <id>   # single patient
  python push_prognosis_to_mongo.py --vald-only      # only patients with VALD data
  python push_prognosis_to_mongo.py --resume         # skip already-processed patients
  python push_prognosis_to_mongo.py --reset          # clear progress and start fresh
"""

import os
import sys
import json
import argparse
import time
import signal
from datetime import datetime, timezone
from pathlib import Path
from dotenv import load_dotenv

# Resolve paths — this script lives at backend/LLM/prognosis/
_THIS_DIR = Path(__file__).parent          # backend/LLM/prognosis
_BACKEND_DIR = _THIS_DIR.parent.parent     # backend/
_PROJECT_ROOT = _BACKEND_DIR.parent        # project root

# Load env from backend/.env
backend_env = _BACKEND_DIR / ".env"
if backend_env.exists():
    load_dotenv(backend_env)
else:
    load_dotenv()

from typing import Optional
from pymongo import MongoClient
from bson import ObjectId

sys.path.insert(0, str(_BACKEND_DIR))
sys.path.insert(0, str(_PROJECT_ROOT))

from LLM.prognosis.prognosis_agent import ClinicalPrognosisAgent
from utils.vald_extractor import extract_vald_first_session
from utils.input_gate import has_minimum_clinical_input
from load_reports_from_mongo import MongoReportsLoader

# Progress file lives next to this script
PROGRESS_FILE = _THIS_DIR / "push_progress.json"


def _now():
    return datetime.now(timezone.utc)


# ── Progress tracking ─────────────────────────────────────────────────────────

def load_progress() -> dict:
    if PROGRESS_FILE.exists():
        try:
            return json.loads(PROGRESS_FILE.read_text())
        except Exception:
            pass
    return {"done": [], "failed": [], "started_at": None, "last_updated": None}


def save_progress(progress: dict):
    progress["last_updated"] = datetime.now().isoformat()
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


def reset_progress():
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()
    print("🗑️  Progress file cleared.")


def print_progress_bar(current: int, total: int, success: int, failed: int, width: int = 40):
    pct = current / total if total else 0
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    eta_str = ""
    print(f"\r  [{bar}] {current}/{total} ({pct*100:.1f}%)  ✅{success}  ❌{failed}{eta_str}  ", end="", flush=True)


# ── MongoDB helpers ───────────────────────────────────────────────────────────

def get_mongo_db():
    mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
    db_name = os.getenv("MONGO_DB", "stance-dashboard")
    client = MongoClient(mongo_uri, tlsAllowInvalidCertificates=True, tlsAllowInvalidHostnames=True)
    return client, client[db_name]


def get_patient_ids(db, vald_only: bool = False, limit: int = None) -> list:
    loader = MongoReportsLoader()
    patients = loader.list_patients()
    print(f"   Total patients in DB: {len(patients)}")

    if vald_only:
        vald_ids = set(
            str(doc.get("stanceId") or doc.get("valdSyncId") or doc.get("patient_id") or "")
            for doc in db["vald-exercise-data"].find(
                {"$or": [
                    {"savedResponse.data.is_forceframe": True},
                    {"savedResponse.data.is_forcedeck": True},
                ]},
                {"stanceId": 1, "valdSyncId": 1, "patient_id": 1}
            )
        )
        vald_ids.discard("")
        patients = [p for p in patients if str(p.get("_id") or p.get("patient_id") or p.get("id")) in vald_ids]
        print(f"   Filtered to {len(patients)} patients with VALD data")

    if limit:
        patients = patients[:limit]

    return [str(p.get("_id") or p.get("patient_id") or p.get("id")) for p in patients
            if p.get("_id") or p.get("patient_id") or p.get("id")]


def build_patient_data(loader, db, patient_id: str) -> dict:
    patient_info, clinical_data = loader.get_patient_reports(patient_id)
    if not patient_info or not clinical_data:
        raise ValueError(f"No clinical data for patient {patient_id}")

    first = next((r for r in clinical_data if r.get("isFirstAssessment")), clinical_data[0])
    vald = extract_vald_first_session(db, patient_id)

    if vald["vald_exercises"]:
        ex_names = list(vald["vald_exercises"].keys())
        print(f"   💪 VALD ({len(ex_names)} exercises): {ex_names[:4]}{'...' if len(ex_names) > 4 else ''}")

    return {
        "patient_id": patient_id,
        "patient_name": patient_info.get("patient_name", "Unknown"),
        "source_data": {
            "provisional_diagnosis_raw": first.get("diagnosis", ""),
            "chief_complaint": first.get("chief_complaints", ""),
            "clinical_history": first.get("client_history", ""),
            "subjective_notes": first.get("notes", ""),
        },
        "extracted_fields": {
            "provisional_diagnosis": {"canonical_label": first.get("diagnosis", "") or "Unknown", "confidence": "medium"},
            "joint_mapping": {"primary_joint": "Unknown", "functional_region": "unknown"},
            "clinical_stage": {"stage": "unknown"},
            "pain_interference": {"category": "unknown"},
        },
        "strength_asymmetry_percent": vald["strength_asymmetry_percent"],
        "rom_asymmetry_degrees": vald["rom_asymmetry_degrees"],
        "absolute_force_level": vald["absolute_force_level"],
        "vald_exercises": vald["vald_exercises"],
    }


def build_patient_data_from_reports(db, patient_id: str) -> Optional[dict]:
    """Build the prognosis-agent input for a patient by reading their
    first-assessment report directly from `reports` plus first-session VALD data.

    Reading `reports` directly (rather than the structured-user-reports view)
    reaches patients the view filters out. Returns None when the patient/report
    is missing or has empty records. Shared by the change-stream listener and the
    prognosis queue worker so both produce identical, VALD-aware input.
    """
    pid_obj = ObjectId(patient_id) if isinstance(patient_id, str) and len(patient_id) == 24 else patient_id

    user = db.users.find_one({"_id": pid_obj})
    if not user:
        return None
    if user.get("userType") and user.get("userType") != "PATIENT":
        return None
    profile = user.get("profileData") or {}
    patient_name = f"{profile.get('firstName','')} {profile.get('lastName','')}".strip() or "Unknown"

    report = db.reports.find_one({"patient": pid_obj, "isFirstAssessment": True})
    if not report:
        return None
    records = report.get("records") or {}
    if not records:
        return None

    clinical = records.get("clinicalDetails") or {}
    subjective = records.get("subjectiveAssessment") or {}
    prov_dx = records.get("provisionalDiagnosis") or {}
    diagnosis = (prov_dx.get("diagnosis") or "").strip()

    # VALD — soft-fail so a missing/odd VALD doc never blocks prognosis
    try:
        vald = extract_vald_first_session(db, str(pid_obj))
    except Exception:
        vald = {"vald_exercises": {}, "strength_asymmetry_percent": None,
                "rom_asymmetry_degrees": None, "absolute_force_level": None}

    patient_data = {
        "patient_id": str(pid_obj),
        "patient_name": patient_name,
        "source_data": {
            "provisional_diagnosis_raw": diagnosis,
            "chief_complaint": clinical.get("chiefComplaints", "") or "",
            "clinical_history": clinical.get("clientHistory", "") or "",
            "subjective_notes": subjective.get("assessment", "") or "",
        },
        "extracted_fields": {
            "provisional_diagnosis": {"canonical_label": diagnosis or "Unknown",
                                      "confidence": "low" if not diagnosis else "medium"},
            "joint_mapping": {"primary_joint": "Unknown", "functional_region": "unknown"},
            "clinical_stage": {"stage": "unknown"},
            "pain_interference": {"category": "unknown"},
        },
        "strength_asymmetry_percent": vald["strength_asymmetry_percent"],
        "rom_asymmetry_degrees": vald["rom_asymmetry_degrees"],
        "absolute_force_level": vald["absolute_force_level"],
        "vald_exercises": vald["vald_exercises"],
    }

    # Content gate: a report can exist (even with a non-empty `records` dict)
    # while every clinical field inside is blank and no VALD data is present.
    # Skip the LLM entirely in that case so we don't generate a prognosis from
    # nothing. All live callers already treat a None return as "skip".
    if not has_minimum_clinical_input(patient_data):
        return None

    return patient_data


def save_to_mongo(db, patient_id: str, analysis) -> None:
    collection = db["prognosis"]
    try:
        pid = ObjectId(patient_id) if len(str(patient_id)) == 24 else patient_id
    except Exception:
        pid = patient_id

    pt = analysis.probability_tier
    suf = analysis.diagnostic_sufficiency
    doc = {
        "patient_id": pid,
        "schema_version": "v2_tier_system",
        "updated_at": _now(),
        "provisional_diagnosis": analysis.provisional_diagnosis,
        "probability_tier": {"tier": pt.tier, "label": pt.label, "rationale": pt.rationale},
        "why_not_higher_tier": analysis.why_not_higher_tier,
        "positioning_summary": analysis.positioning_summary,
        "diagnostic_sufficiency": {
            "is_sufficient": suf.is_sufficient,
            "sufficiency_answer": suf.sufficiency_answer,
            "driver_systems": suf.driver_systems,
            "why_not_sufficient": suf.why_not_sufficient,
        },
        "differential_diagnoses": [
            {"diagnosis": d.diagnosis, "tier": d.tier, "tier_label": d.tier_label,
             "fits_because": d.fits_because, "directional_impact": d.directional_impact,
             "included_reason": d.included_reason}
            for d in analysis.differential_diagnoses
        ],
        "decision_changing_missing_data": [
            {"category": m.category, "missing_tests": m.missing_tests, "impact_if_positive": m.impact_if_positive}
            for m in analysis.decision_changing_missing_data
        ],
    }
    collection.update_one(
        {"patient_id": pid},
        {"$set": doc, "$setOnInsert": {"created_at": _now()}},
        upsert=True,
    )


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Batch push prognosis analyses to MongoDB")
    parser.add_argument("--patient", "-p", help="Single patient ID to process")
    parser.add_argument("--limit", "-n", type=int, help="Max number of patients to process")
    parser.add_argument("--vald-only", action="store_true", help="Only patients with VALD exercise data")
    parser.add_argument("--delay", type=float, default=2.0, help="Seconds between patients (default: 2)")
    parser.add_argument("--resume", action="store_true", help="Skip already-processed patients and continue")
    parser.add_argument("--reset", action="store_true", help="Clear saved progress and start fresh")
    parser.add_argument("--status", action="store_true", help="Show current progress and exit")
    args = parser.parse_args()

    # ── Status check ──────────────────────────────────────────────────────────
    if args.status:
        p = load_progress()
        print(f"📊 Progress status:")
        print(f"   Started:      {p.get('started_at', 'N/A')}")
        print(f"   Last updated: {p.get('last_updated', 'N/A')}")
        print(f"   ✅ Done:      {len(p['done'])}")
        print(f"   ❌ Failed:    {len(p['failed'])}")
        if p["failed"]:
            print(f"   Failed IDs:   {p['failed']}")
        return

    # ── Reset ─────────────────────────────────────────────────────────────────
    if args.reset:
        reset_progress()

    print("🚀 Prognosis → MongoDB Push Script")
    print("=" * 50)

    # ── Load or init progress ─────────────────────────────────────────────────
    progress = load_progress()
    already_done = set(progress["done"])

    if args.resume and already_done:
        print(f"♻️  Resuming — {len(already_done)} patients already done, skipping them.")
    elif not args.resume:
        # Fresh run: don't carry over old progress unless --resume
        progress = {"done": [], "failed": [], "started_at": datetime.now().isoformat(), "last_updated": None}
        already_done = set()

    if not progress.get("started_at"):
        progress["started_at"] = datetime.now().isoformat()

    # ── Init connections ──────────────────────────────────────────────────────
    client, db = get_mongo_db()
    loader = MongoReportsLoader()
    agent = ClinicalPrognosisAgent()

    # ── Build patient list ────────────────────────────────────────────────────
    if args.patient:
        patient_ids = [args.patient]
    else:
        print("📋 Fetching patient list...")
        patient_ids = get_patient_ids(db, vald_only=args.vald_only, limit=args.limit)

    # Filter out already-done patients when resuming
    if args.resume and already_done:
        original_count = len(patient_ids)
        patient_ids = [pid for pid in patient_ids if pid not in already_done]
        print(f"   Skipping {original_count - len(patient_ids)} already processed → {len(patient_ids)} remaining")

    total = len(patient_ids)
    print(f"   Processing {total} patients\n")

    if total == 0:
        print("✅ Nothing to do.")
        client.close()
        return

    # ── Graceful interrupt handler ────────────────────────────────────────────
    interrupted = False
    def _handle_interrupt(sig, frame):
        nonlocal interrupted
        interrupted = True
        print("\n\n⚠️  Interrupted — saving progress. Run with --resume to continue.")

    signal.signal(signal.SIGINT, _handle_interrupt)

    # ── Process patients ──────────────────────────────────────────────────────
    session_success = 0
    session_failed = []
    session_skipped = 0
    start_time = time.time()

    for i, patient_id in enumerate(patient_ids, 1):
        if interrupted:
            break

        elapsed = time.time() - start_time
        avg_per_patient = elapsed / i if i > 1 else 0
        remaining = total - i
        eta = f"  ETA ~{int(avg_per_patient * remaining)}s" if avg_per_patient > 0 and remaining > 0 else ""

        print(f"\n[{i}/{total}] Patient: {patient_id}{eta}")

        try:
            patient_data = build_patient_data(loader, db, patient_id)

            # Content gate: don't spend an LLM call on a patient with no clinical
            # text and no VALD data — the model only ever returns an
            # "insufficient data" placeholder (or worse, a confident diagnosis
            # invented from nothing).
            if not has_minimum_clinical_input(patient_data):
                print("   ⏭️  Skipped — no clinical content or VALD data")
                session_skipped += 1
                progress.setdefault("skipped", []).append(patient_id)
                save_progress(progress)
                print_progress_bar(i, total, session_success, len(session_failed))
                if i < total and not interrupted:
                    time.sleep(args.delay)
                continue

            analysis = agent.analyze_patient_prognosis(patient_data)
            save_to_mongo(db, patient_id, analysis)
            print(f"   ✅ Tier {analysis.probability_tier.tier} — {analysis.provisional_diagnosis[:70]}")
            session_success += 1
            progress["done"].append(patient_id)
        except Exception as e:
            print(f"   ❌ Failed: {e}")
            session_failed.append(patient_id)
            progress["failed"].append(patient_id)

        # Save progress after every patient
        save_progress(progress)

        # Progress bar
        total_done = len(progress["done"])
        total_failed = len(progress["failed"])
        print_progress_bar(i, total, session_success, len(session_failed))

        if i < total and not interrupted:
            time.sleep(args.delay)

    print()  # newline after progress bar
    client.close()

    # ── Summary ───────────────────────────────────────────────────────────────
    elapsed_total = int(time.time() - start_time)
    print(f"\n{'='*50}")
    print(f"✅ Session done in {elapsed_total}s: {session_success} saved, {session_skipped} skipped, {len(session_failed)} failed")
    print(f"📊 Overall progress: {len(progress['done'])} done / {len(progress.get('skipped', []))} skipped / {len(progress['failed'])} failed total")

    if session_failed:
        print(f"❌ Failed this session: {session_failed}")

    if interrupted:
        print(f"\n💾 Progress saved to {PROGRESS_FILE}")
        print(f"   Run with --resume to continue where you left off.")
    elif not session_failed:
        print(f"\n🎉 All patients processed! You can run --reset to clear progress.")


if __name__ == "__main__":
    main()
