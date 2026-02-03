"""
Statistics routes for dashboard widgets.
"""
from fastapi import APIRouter, Query
from typing import Optional, List
from api.models import (
    CountStats, StackedCountStats,
    NPRSAvailabilityStats, NPRSDistributionBin
)
from api.data_loader import get_all_patients_master_view

router = APIRouter()


# ============================================================================
# Master Prompt Classification Endpoints
# ============================================================================

@router.get("/diagnosis", response_model=List[CountStats])
async def get_diagnosis_stats():
    """
    Get diagnosis distribution statistics (Step 1).
    
    Returns:
        List of diagnosis counts with percentages
    """
    patients = get_all_patients_master_view()
    total = len(patients)
    
    if total == 0:
        return []
    
    # Count by canonical diagnosis
    diagnosis_counts = {}
    for patient in patients:
        diagnosis = patient.canonicalDiagnosis or "Unclear"
        diagnosis_counts[diagnosis] = diagnosis_counts.get(diagnosis, 0) + 1
    
    return [
        CountStats(
            name=diagnosis,
            value=count,
            percentage=round((count / total) * 100, 2)
        )
        for diagnosis, count in sorted(diagnosis_counts.items(), key=lambda x: x[1], reverse=True)
    ]


@router.get("/joint-region", response_model=List[CountStats])
async def get_joint_region_stats():
    """
    Get joint and functional region statistics (Step 2).
    
    Returns:
        List of functional regions with joint breakdown
    """
    patients = get_all_patients_master_view()
    total = len(patients)
    
    if total == 0:
        return []
    
    # Group by functional region, then by joint
    region_data = {}
    for patient in patients:
        region = patient.functionalRegion.value if patient.functionalRegion else "Unclear"
        joint = patient.primaryJoint or "Unknown"
        
        if region not in region_data:
            region_data[region] = {"total": 0, "breakdown": {}}
        region_data[region]["total"] += 1
        region_data[region]["breakdown"][joint] = region_data[region]["breakdown"].get(joint, 0) + 1
    
    return [
        CountStats(
            name=region,
            value=data["total"],
            percentage=round((data["total"] / total) * 100, 2)
        )
        for region, data in sorted(region_data.items(), key=lambda x: x[1]["total"], reverse=True)
    ]


@router.get("/occupation", response_model=List[CountStats])
async def get_occupation_stats():
    """
    Get occupational category statistics (Step 3).
    
    Returns:
        List of occupation counts with percentages
    """
    patients = get_all_patients_master_view()
    total = len(patients)
    
    if total == 0:
        return []
    
    # Count by occupation
    occupation_counts = {}
    for patient in patients:
        occupation = patient.occupationCategory.value if patient.occupationCategory else "Unclear"
        occupation_counts[occupation] = occupation_counts.get(occupation, 0) + 1
    
    return [
        CountStats(
            name=occupation,
            value=count,
            percentage=round((count / total) * 100, 2)
        )
        for occupation, count in sorted(occupation_counts.items(), key=lambda x: x[1], reverse=True)
    ]


@router.get("/activity-profile", response_model=List[CountStats])
async def get_activity_profile_stats():
    """
    Get activity profile statistics (Step 4 - Primary).
    
    Returns:
        List of activity profile counts with percentages
    """
    patients = get_all_patients_master_view()
    total = len(patients)
    
    if total == 0:
        return []
    
    # Count by activity profile
    profile_counts = {}
    for patient in patients:
        profile = patient.activityProfile.value if patient.activityProfile else "Unclear"
        profile_counts[profile] = profile_counts.get(profile, 0) + 1
    
    return [
        CountStats(
            name=profile,
            value=count,
            percentage=round((count / total) * 100, 2)
        )
        for profile, count in sorted(profile_counts.items(), key=lambda x: x[1], reverse=True)
    ]


@router.get("/activity-recreational", response_model=List[CountStats])
async def get_activity_recreational_stats():
    """
    Get recreational activity subtype statistics (Step 4 - Sub-table).
    
    Returns:
        List of recreational subtype counts with percentages (of recreationally active patients)
    """
    patients = get_all_patients_master_view()
    
    # Filter to only recreationally active patients
    recreational_patients = [
        p for p in patients
        if p.activityProfile and p.activityProfile.value == "Recreationally active"
    ]
    
    total_recreational = len(recreational_patients)
    
    if total_recreational == 0:
        return []
    
    # Count by subtype
    subtype_counts = {}
    for patient in recreational_patients:
        subtype = patient.activitySubtype.value if patient.activitySubtype else "Unclear"
        subtype_counts[subtype] = subtype_counts.get(subtype, 0) + 1
    
    return [
        CountStats(
            name=subtype,
            value=count,
            percentage=round((count / total_recreational) * 100, 2)
        )
        for subtype, count in sorted(subtype_counts.items(), key=lambda x: x[1], reverse=True)
    ]


@router.get("/clinical-stage", response_model=List[CountStats])
async def get_clinical_stage_stats():
    """
    Get clinical stage statistics (Step 5).
    
    Returns:
        List of clinical stage counts with percentages
    """
    patients = get_all_patients_master_view()
    total = len(patients)
    
    if total == 0:
        return []
    
    # Count by clinical stage
    stage_counts = {}
    for patient in patients:
        stage = patient.clinicalStage.value if patient.clinicalStage else "Unclear"
        stage_counts[stage] = stage_counts.get(stage, 0) + 1
    
    return [
        CountStats(
            name=stage,
            value=count,
            percentage=round((count / total) * 100, 2)
        )
        for stage, count in sorted(stage_counts.items(), key=lambda x: x[1], reverse=True)
    ]


@router.get("/pain-interference", response_model=List[CountStats])
async def get_pain_interference_stats():
    """
    Get pain interference statistics (Step 6).
    
    Returns:
        List of pain interference counts with percentages
    """
    patients = get_all_patients_master_view()
    total = len(patients)
    
    if total == 0:
        return []
    
    # Count by pain interference
    interference_counts = {}
    for patient in patients:
        interference = patient.painInterference.value if patient.painInterference else "Unclear"
        interference_counts[interference] = interference_counts.get(interference, 0) + 1
    
    return [
        CountStats(
            name=interference,
            value=count,
            percentage=round((count / total) * 100, 2)
        )
        for interference, count in sorted(interference_counts.items(), key=lambda x: x[1], reverse=True)
    ]


@router.get("/nprs-availability", response_model=NPRSAvailabilityStats)
async def get_nprs_availability_stats():
    """
    Get NPRS availability statistics (Step 7 - Part 1).
    
    Returns:
        NPRS availability counts and percentages
    """
    patients = get_all_patients_master_view()
    total = len(patients)
    
    nprs_present = sum(1 for p in patients if p.nprsAvailable)
    nprs_absent = total - nprs_present
    
    return NPRSAvailabilityStats(
        totalPatients=total,
        nprsPresent=nprs_present,
        nprsAbsent=nprs_absent,
        presentPercentage=round((nprs_present / total) * 100, 2) if total > 0 else 0.0,
        absentPercentage=round((nprs_absent / total) * 100, 2) if total > 0 else 0.0
    )


@router.get("/nprs-distribution", response_model=List[NPRSDistributionBin])
async def get_nprs_distribution_stats():
    """
    Get NPRS distribution statistics (Step 7 - Part 2).
    
    Returns:
        List of NPRS distribution bins (for NPRS-present patients only)
    """
    patients = get_all_patients_master_view()
    
    # Filter to only patients with NPRS
    nprs_patients = [p for p in patients if p.nprsAvailable and p.nprsScore is not None]
    total_nprs = len(nprs_patients)
    
    if total_nprs == 0:
        return []
    
    # Define bins
    bins = [
        {"range": "0-3", "min": 0, "max": 3},
        {"range": "4-6", "min": 4, "max": 6},
        {"range": "7-10", "min": 7, "max": 10}
    ]
    
    bin_counts = {bin_info["range"]: 0 for bin_info in bins}
    
    for patient in nprs_patients:
        score = patient.nprsScore
        if 0 <= score <= 3:
            bin_counts["0-3"] += 1
        elif 4 <= score <= 6:
            bin_counts["4-6"] += 1
        elif 7 <= score <= 10:
            bin_counts["7-10"] += 1
    
    return [
        NPRSDistributionBin(
            range=bin_info["range"],
            min=bin_info["min"],
            max=bin_info["max"],
            count=bin_counts[bin_info["range"]],
            percentage=round((bin_counts[bin_info["range"]] / total_nprs) * 100, 2)
        )
        for bin_info in bins
    ]


@router.get("/intent", response_model=List[CountStats])
async def get_intent_stats():
    """
    Get intent/expectation statistics (Step 9).
    
    Returns:
        List of intent category counts with percentages
    """
    patients = get_all_patients_master_view()
    total = len(patients)
    
    if total == 0:
        return []
    
    # Count by intent category
    intent_counts = {}
    for patient in patients:
        intent = patient.intentCategory.value if patient.intentCategory else "Unclear"
        intent_counts[intent] = intent_counts.get(intent, 0) + 1
    
    return [
        CountStats(
            name=intent,
            value=count,
            percentage=round((count / total) * 100, 2)
        )
        for intent, count in sorted(intent_counts.items(), key=lambda x: x[1], reverse=True)
    ]
