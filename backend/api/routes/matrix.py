"""
Matrix routes for heatmap visualizations.
"""
from fastapi import APIRouter
from typing import List
from api.models import PainInterferenceNPRSCell
from api.data_loader import get_all_patients_master_view

router = APIRouter()


@router.get("/pain-nprs", response_model=List[PainInterferenceNPRSCell])
async def get_pain_nprs_matrix():
    """
    Get pain interference × NPRS matrix (Step 8).
    
    Returns:
        List of matrix cells with counts and percentages (of NPRS-present patients)
    """
    patients = get_all_patients_master_view()
    
    # Filter to only patients with NPRS
    nprs_patients = [p for p in patients if p.nprsAvailable and p.nprsScore is not None]
    total_nprs = len(nprs_patients)
    
    if total_nprs == 0:
        return []
    
    # Define NPRS ranges
    nprs_ranges = ["0-3", "4-6", "7-10"]
    
    # Initialize matrix
    matrix = {}
    for patient in nprs_patients:
        interference = patient.painInterference.value if patient.painInterference else "Unclear"
        score = patient.nprsScore
        
        # Determine NPRS range
        if 0 <= score <= 3:
            nprs_range = "0-3"
        elif 4 <= score <= 6:
            nprs_range = "4-6"
        elif 7 <= score <= 10:
            nprs_range = "7-10"
        else:
            continue
        
        key = (interference, nprs_range)
        matrix[key] = matrix.get(key, 0) + 1
    
    # Get all unique interference categories
    interference_categories = set()
    for patient in nprs_patients:
        interference = patient.painInterference.value if patient.painInterference else "Unclear"
        interference_categories.add(interference)
    
    # Build result list
    result = []
    for interference in sorted(interference_categories):
        for nprs_range in nprs_ranges:
            count = matrix.get((interference, nprs_range), 0)
            result.append(
                PainInterferenceNPRSCell(
                    interference=interference,
                    nprsRange=nprs_range,
                    count=count,
                    percentage=round((count / total_nprs) * 100, 2)
                )
            )
    
    return result
