"""
Patient routes for fetching and filtering patient data.
"""
from fastapi import APIRouter, Query
from typing import Optional, List
from api.models import (
    PatientMasterView, FunctionalRegion, OccupationCategory, ActivityProfile,
    ClinicalStage, PainInterference, IntentCategory
)
from api.data_loader import get_all_patients_master_view
from api.progress_tracker import get_progress

router = APIRouter()


@router.get("/patients", response_model=List[PatientMasterView])
async def get_patients(
    canonical_diagnosis: Optional[str] = Query(None, description="Filter by canonical diagnosis"),
    primary_joint: Optional[str] = Query(None, description="Filter by primary joint"),
    functional_region: Optional[FunctionalRegion] = Query(None, description="Filter by functional region"),
    occupation_category: Optional[OccupationCategory] = Query(None, description="Filter by occupation category"),
    activity_profile: Optional[ActivityProfile] = Query(None, description="Filter by activity profile"),
    clinical_stage: Optional[ClinicalStage] = Query(None, description="Filter by clinical stage"),
    pain_interference: Optional[PainInterference] = Query(None, description="Filter by pain interference"),
    intent_category: Optional[IntentCategory] = Query(None, description="Filter by intent category"),
):
    """
    Get all patients with optional filters (new master prompt format).
    
    Args:
        canonical_diagnosis: Filter by canonical diagnosis
        primary_joint: Filter by primary joint
        functional_region: Filter by functional region
        occupation_category: Filter by occupation category
        activity_profile: Filter by activity profile
        clinical_stage: Filter by clinical stage
        pain_interference: Filter by pain interference
        intent_category: Filter by intent category
        
    Returns:
        List of filtered patients
    """
    # Check if triage is running and get the current output file for real-time updates
    progress = get_progress()
    output_file = progress.get("output_file") if progress.get("status") == "running" else None
    
    patients = get_all_patients_master_view(output_file_path=output_file)
    
    # Apply filters
    if canonical_diagnosis:
        patients = [p for p in patients if p.canonicalDiagnosis == canonical_diagnosis]
    
    if primary_joint:
        patients = [p for p in patients if p.primaryJoint == primary_joint]
    
    if functional_region:
        patients = [p for p in patients if p.functionalRegion == functional_region]
    
    if occupation_category:
        patients = [p for p in patients if p.occupationCategory == occupation_category]
    
    if activity_profile:
        patients = [p for p in patients if p.activityProfile == activity_profile]
    
    if clinical_stage:
        patients = [p for p in patients if p.clinicalStage == clinical_stage]
    
    if pain_interference:
        patients = [p for p in patients if p.painInterference == pain_interference]
    
    if intent_category:
        patients = [p for p in patients if p.intentCategory == intent_category]
    
    return patients
