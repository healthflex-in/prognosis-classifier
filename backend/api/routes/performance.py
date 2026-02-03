"""
Performance routes for asymmetry and force data.
"""
from fastapi import APIRouter, Query
from typing import Optional, List
from api.models import AsymmetryData, ScatterData, DistributionBin, ClinicalStage
from api.data_loader import get_all_patients

router = APIRouter()


@router.get("/asymmetry", response_model=List[AsymmetryData])
async def get_asymmetry_data(
    clinical_stage: Optional[ClinicalStage] = Query(None),
    functional_region: Optional[str] = Query(None),
):
    """
    Get asymmetry data for lollipop chart.
    
    Returns:
        List of patient asymmetry data
    """
    patients = get_all_patients()
    
    # Apply filters
    if clinical_stage:
        patients = [p for p in patients if p.clinicalStage == clinical_stage]
    
    if functional_region:
        patients = [p for p in patients if p.functionalRegion and p.functionalRegion.value == functional_region]
    
    # Filter patients with asymmetry data
    asymmetry_patients = [p for p in patients if p.strengthAsymmetry is not None]
    
    return [
        AsymmetryData(
            name=patient.patientName,
            value=patient.strengthAsymmetry,
            category=patient.clinicalStage.value if patient.clinicalStage else "Unclear"
        )
        for patient in asymmetry_patients
    ]


@router.get("/asymmetry-force", response_model=List[ScatterData])
async def get_asymmetry_force_data():
    """
    Get asymmetry vs force scatter plot data.
    
    Returns:
        List of scatter plot points (y values: Low=1, Medium=2, High=3)
    """
    patients = get_all_patients()
    
    # Filter patients with both asymmetry and force data
    valid_patients = [
        p for p in patients
        if p.strengthAsymmetry is not None and p.absoluteForceLevel is not None
    ]
    
    force_level_map = {"Low": 1, "Medium": 2, "High": 3}
    
    return [
        ScatterData(
            x=patient.strengthAsymmetry,
            y=force_level_map.get(patient.absoluteForceLevel, 2),
            name=patient.patientName,
            category=patient.clinicalStage.value if patient.clinicalStage else "Unclear"
        )
        for patient in valid_patients
    ]


@router.get("/distribution", response_model=List[DistributionBin])
async def get_distribution_data():
    """
    Get asymmetry distribution histogram data.
    
    Returns:
        List of distribution bins
    """
    patients = get_all_patients()
    
    # Get all asymmetry values
    asymmetry_values = [
        p.strengthAsymmetry for p in patients
        if p.strengthAsymmetry is not None
    ]
    
    if not asymmetry_values:
        return []
    
    # Define bins
    bins = [
        (0, 10),
        (10, 20),
        (20, 30),
        (30, 40),
        (40, 50),
        (50, 100),
    ]
    
    # Count values in each bin
    distribution = []
    for min_val, max_val in bins:
        count = sum(1 for val in asymmetry_values if min_val <= val < max_val)
        distribution.append(
            DistributionBin(
                range=f"{min_val}-{max_val}%",
                min=min_val,
                max=max_val,
                count=count
            )
        )
    
    return distribution
