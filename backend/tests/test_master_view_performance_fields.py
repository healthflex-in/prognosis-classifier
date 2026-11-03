"""VALD/performance fields must survive transform_to_master_view."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.data_loader import transform_to_master_view


def test_zero_vald_metrics_are_preserved():
    patient = transform_to_master_view({
        "patient_id": "abc",
        "patient_name": "Zero Asymmetry",
        "strength_asymmetry_percent": 0.0,
        "absolute_force_level": "Low",
        "rom_asymmetry_degrees": 0.0,
        "nprs_available": True,
        "nprs_score": 0,
    })
    assert patient.strengthAsymmetry == 0.0
    assert patient.absoluteForceLevel == "Low"
    assert patient.romAsymmetryDegrees == 0.0
    assert patient.nprsScore == 0
    assert patient.nprsAvailable is True


def test_camel_case_vald_fallback():
    patient = transform_to_master_view({
        "patient_id": "abc",
        "patient_name": "Camel",
        "strengthAsymmetry": 12.5,
        "absoluteForceLevel": "High",
        "romAsymmetryDegrees": 4.0,
    })
    assert patient.strengthAsymmetry == 12.5
    assert patient.absoluteForceLevel == "High"
    assert patient.romAsymmetryDegrees == 4.0


def test_performance_routes_can_read_vald_fields():
    patient = transform_to_master_view({
        "patient_id": "abc",
        "patient_name": "Mapped",
        "strength_asymmetry_percent": 8.0,
        "absolute_force_level": "Medium",
        "clinical_stage": "Chronic",
    })
    assert patient.strengthAsymmetry is not None
    assert patient.absoluteForceLevel is not None
    assert {"Low": 1, "Medium": 2, "High": 3}.get(patient.absoluteForceLevel) == 2
