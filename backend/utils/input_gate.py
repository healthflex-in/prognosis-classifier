"""
Input-sufficiency gate for the prognosis pipeline.

Purpose: stop empty / content-less patients from reaching the LLM. A report
row can exist (and even have a non-empty `records` dict) while every clinical
field inside is blank. Feeding that to the model wastes an API call and
produces misleading output (e.g. a confident "undifferentiated" tier-5
diagnosis generated from nothing).

This gate inspects the *content* the agent would actually see and returns
False when there is nothing worth analyzing.
"""

from typing import Any, Dict


def has_minimum_clinical_input(patient_data: Dict[str, Any]) -> bool:
    """Return True only if there is enough real signal to justify an LLM call.

    Sufficient input = at least one non-empty clinical text field OR any VALD
    biomechanical data. Whitespace-only strings count as empty.
    """
    if not patient_data:
        return False

    src = patient_data.get("source_data") or {}
    text_fields = (
        src.get("chief_complaint", ""),
        src.get("clinical_history", ""),
        src.get("subjective_notes", ""),
        src.get("provisional_diagnosis_raw", ""),
    )
    has_clinical_text = any(isinstance(f, str) and f.strip() for f in text_fields)

    has_vald = bool(patient_data.get("vald_exercises")) or any((
        patient_data.get("strength_asymmetry_percent") is not None,
        patient_data.get("rom_asymmetry_degrees") is not None,
        bool(patient_data.get("absolute_force_level")),
    ))

    return has_clinical_text or has_vald
