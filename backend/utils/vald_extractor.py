"""
Shared VALD exercise data extractor.
Pulls exercises from vald-exercise-data collection using the earliest session date only.
Handles ForceFrame (bilateral L/R maxForce) and ForceDeck (squat/jump assessments) schemas.
"""

from datetime import datetime
from typing import Any, Dict, Optional, Tuple


def extract_vald_first_session(db, patient_id: str) -> Dict[str, Any]:
    """
    Fetch VALD exercise data for a patient from vald-exercise-data collection.
    Only returns exercises that occurred on the earliest (first) session date.

    Returns dict with keys:
      vald_exercises        — {exercise_name: {metrics...}}
      strength_asymmetry_percent
      rom_asymmetry_degrees
      absolute_force_level
    """
    empty = {
        "vald_exercises": {},
        "strength_asymmetry_percent": None,
        "rom_asymmetry_degrees": None,
        "absolute_force_level": None,
    }

    vald_doc = db["vald-exercise-data"].find_one({
        "$or": [
            {"stanceId": patient_id}, {"valdSyncId": patient_id},
            {"patient_id": patient_id}, {"patientId": patient_id},
        ]
    })
    if not vald_doc:
        return empty

    data = vald_doc.get("savedResponse", {}).get("data", {})
    ff = data.get("forceFrame", {})
    fd = data.get("forceDeck", {})
    exercises = {**ff, **fd}

    if not exercises:
        return empty

    # ── Find earliest session date across all exercises ───────────────────────
    all_dates = []
    for ex_data in exercises.values():
        dates = ex_data.get("sessionDates") or []
        if not dates and ex_data.get("sessionDate"):
            dates = [ex_data["sessionDate"]]
        for d in dates:
            if not d:
                continue
            try:
                all_dates.append(datetime.fromisoformat(d.replace("Z", "+00:00")))
            except Exception:
                pass

    if not all_dates:
        return empty

    earliest_date_str = min(all_dates).date().isoformat()

    # ── Collect exercises on that earliest date ───────────────────────────────
    vald_exercises: Dict[str, Any] = {}
    all_asym, all_left, all_right = [], [], []

    for ex_name, ex_data in exercises.items():
        dates = ex_data.get("sessionDates") or []
        if not dates and ex_data.get("sessionDate"):
            dates = [ex_data["sessionDate"]]

        on_earliest = any(
            (d or "").replace("Z", "").startswith(earliest_date_str)
            for d in dates
        )
        if not on_earliest:
            continue

        entry = _parse_exercise(ex_name, ex_data, earliest_date_str)
        if entry:
            vald_exercises[ex_name] = entry
            if entry.get("asymmetry_pct") is not None:
                all_asym.append(abs(entry["asymmetry_pct"]))
            if entry.get("left_max_force_N") is not None:
                all_left.append(entry["left_max_force_N"])
            if entry.get("right_max_force_N") is not None:
                all_right.append(entry["right_max_force_N"])

    # ── Derive summary metrics ────────────────────────────────────────────────
    strength_asym = round(sum(all_asym) / len(all_asym), 2) if all_asym else None
    absolute_force_level = None
    if all_left and all_right:
        avg = (sum(all_left) / len(all_left) + sum(all_right) / len(all_right)) / 2
        absolute_force_level = "High" if avg > 500 else "Medium" if avg > 300 else "Low"

    return {
        "vald_exercises": vald_exercises,
        "strength_asymmetry_percent": strength_asym,
        "rom_asymmetry_degrees": None,
        "absolute_force_level": absolute_force_level,
    }


NON_MOVEMENT_KEYS = {"sessionDate", "sessionDates", "graph", "exerciseType", "asym", "ratio"}


def _max_force_lr(metrics: Any) -> Tuple[Optional[float], Optional[float]]:
    """Pull left/right maxForce from a metrics dict, tolerating both schemas:
    current  — maxForce: [{"left": .., "right": ..}]
    legacy   — maxForce: {"left": {"max": ..}, "right": {"max": ..}}
    """
    if not isinstance(metrics, dict):
        return None, None
    mf = metrics.get("maxForce")
    if isinstance(mf, list) and mf and isinstance(mf[0], dict):
        return mf[0].get("left"), mf[0].get("right")
    if isinstance(mf, dict):
        left = mf.get("left", {}).get("max") if isinstance(mf.get("left"), dict) else None
        right = mf.get("right", {}).get("max") if isinstance(mf.get("right"), dict) else None
        return left, right
    return None, None


def _asymmetry_pct(left: Optional[float], right: Optional[float]) -> Optional[float]:
    """Bilateral asymmetry as a percentage of the stronger side."""
    if left is None or right is None:
        return None
    hi = max(abs(left), abs(right))
    if hi == 0:
        return None
    return round(abs(left - right) / hi * 100, 2)


def _force_entry(left, right, session_date, movements=None) -> Dict[str, Any]:
    entry = {
        "type": "forceframe",
        "left_max_force_N": left,
        "right_max_force_N": right,
        "asymmetry_pct": _asymmetry_pct(left, right),
        "session_date": session_date,
    }
    if movements:
        entry["movements"] = movements
    return entry


def _parse_exercise(name: str, ex_data: dict, session_date: str) -> Optional[Dict[str, Any]]:
    """Parse a single exercise entry — handles ForceFrame and ForceDeck schemas."""
    if not isinstance(ex_data, dict):
        return None

    # ── ForceFrame, single movement: metrics directly under ex_data["data"] ───
    left, right = _max_force_lr(ex_data.get("data"))
    if left is not None or right is not None:
        return _force_entry(left, right, session_date)

    # ── ForceFrame, multi-movement: e.g. "Hip AD/AB - 45" → abduction/adduction
    movements: Dict[str, Any] = {}
    lefts, rights = [], []
    for mv, mv_data in ex_data.items():
        if mv in NON_MOVEMENT_KEYS or not isinstance(mv_data, dict):
            continue
        l, r = _max_force_lr(mv_data.get("data"))
        if l is None and r is None:
            continue
        movements[mv] = {
            "left_max_force_N": l,
            "right_max_force_N": r,
            "asymmetry_pct": _asymmetry_pct(l, r),
        }
        if l is not None:
            lefts.append(l)
        if r is not None:
            rights.append(r)
    if movements:
        avg_left = round(sum(lefts) / len(lefts), 2) if lefts else None
        avg_right = round(sum(rights) / len(rights), 2) if rights else None
        return _force_entry(avg_left, avg_right, session_date, movements=movements)

    # ── ForceDeck: squat / jump assessment ───────────────────────────────────
    ex_type = ex_data.get("exerciseType", "")
    if ex_type or "asym" in ex_data:
        asym_data = ex_data.get("asym", {})
        asym_val = asym_data.get("meanAsymPeakForce") if isinstance(asym_data, dict) else None
        peak_power = ex_data.get("maxConcentricMeanPowerByBw") or ex_data.get("maxEccentricPeakPower")
        return {
            "type": "forcedeck",
            "exercise_type": ex_type,
            "asymmetry_pct": round(asym_val, 2) if asym_val is not None else None,
            "peak_power": peak_power,
            "left_max_force_N": None,
            "right_max_force_N": None,
            "session_date": session_date,
        }

    return None
