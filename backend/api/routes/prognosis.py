"""
Prognosis API routes.
Provides AI-powered clinical prognosis analysis using patient data and VALD assessments.
"""

from typing import Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from pathlib import Path
import sys

# Ensure backend root is on sys.path for imports
backend_dir = Path(__file__).parent.parent.parent
sys.path.insert(0, str(backend_dir))

from LLM.prognosis.prognosis_agent import ClinicalPrognosisAgent, PrognosisAnalysis, analyze_patient_from_file
from LLM.prognosis.prognosis_langchain_agent import run_langchain_prognosis
from LLM.classification.clinical_agent import ClinicalAnalysis

router = APIRouter(prefix="/prognosis", tags=["prognosis"])


class PrognosisRequest(BaseModel):
    """Request for prognosis analysis."""
    
    patient_id: str = Field(description="Patient ID to analyze")
    include_vald_baseline: bool = Field(default=True, description="Include VALD baseline assessment in analysis")


class PrognosisResponse(BaseModel):
    """Response containing prognosis analysis."""
    
    patient_id: str
    analysis: PrognosisAnalysis
    processing_time_ms: int


class LangchainPrognosisResponse(BaseModel):
    """Response for LangChain-based prognosis analysis."""
    
    patient_id: str
    analysis: ClinicalAnalysis
    processing_time_ms: int


@router.post("/analyze", response_model=PrognosisResponse)
async def analyze_patient_prognosis(request: PrognosisRequest) -> PrognosisResponse:
    """
    Analyze patient condition and provide comprehensive prognosis using clinical data and VALD assessments.
    
    This endpoint:
    - Analyzes patient clinical findings and VALD assessment data
    - Provides AI-powered provisional diagnosis with confidence level
    - Integrates first VALD assessment as baseline for prognosis
    - Recommends treatment interventions and monitoring parameters
    - Identifies risk factors and differential diagnoses
    """
    
    import time
    start_time = time.time()
    
    try:
        # Analyze patient using the prognosis agent
        analysis = analyze_patient_from_file(request.patient_id)
        
        processing_time = int((time.time() - start_time) * 1000)
        
        return PrognosisResponse(
            patient_id=request.patient_id,
            analysis=analysis,
            processing_time_ms=processing_time
        )
        
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prognosis analysis failed: {str(e)}")


@router.get("/patient/{patient_id}", response_model=PrognosisResponse)
async def get_patient_prognosis(patient_id: str) -> PrognosisResponse:
    """
    Get prognosis analysis for a specific patient.
    Convenience endpoint that wraps the analyze endpoint.
    """
    
    request = PrognosisRequest(patient_id=patient_id)
    return await analyze_patient_prognosis(request)


@router.get("/langchain/{patient_id}", response_model=LangchainPrognosisResponse)
async def analyze_patient_prognosis_langchain(patient_id: str) -> LangchainPrognosisResponse:
    """
    Analyze patient condition using the LangChain-based prognosis agent.
    
    This endpoint:
    - Runs the LangChain AgentExecutor with verbose step tracing
    - Uses Mongo-backed clinical + VALD data via tools
    - Persists the ClinicalAnalysis document into MongoDB.prognosis
    - Returns the same structured ClinicalAnalysis object
    """
    import time
    start_time = time.time()
    
    try:
        analysis = run_langchain_prognosis(patient_id)
        processing_time = int((time.time() - start_time) * 1000)
        
        return LangchainPrognosisResponse(
            patient_id=patient_id,
            analysis=analysis,
            processing_time_ms=processing_time,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"LangChain prognosis analysis failed: {str(e)}")


class VALDInterpretationRequest(BaseModel):
    """Request for VALD data interpretation."""
    
    strength_asymmetry_percent: float = Field(description="Strength asymmetry percentage")
    rom_asymmetry_degrees: float = Field(description="ROM asymmetry in degrees") 
    absolute_force_level: str = Field(description="Absolute force level (Low/Medium/High)")
    is_first_assessment: bool = Field(default=True, description="Whether this is first VALD assessment")


class VALDInterpretationResponse(BaseModel):
    """Response with VALD data interpretation."""
    
    interpretation: str = Field(description="Clinical interpretation of VALD findings")
    significance_level: str = Field(description="Clinical significance (Normal/Mild/Moderate/Severe)")
    recommendations: list[str] = Field(description="Recommendations based on VALD findings")
    follow_up_timeline: str = Field(description="Recommended follow-up timeline")


@router.post("/vald/interpret", response_model=VALDInterpretationResponse)
async def interpret_vald_assessment(request: VALDInterpretationRequest) -> VALDInterpretationResponse:
    """
    Interpret VALD assessment data and provide clinical recommendations.
    
    This endpoint provides standalone VALD interpretation without full patient analysis.
    Useful for quick assessment of VALD results.
    """
    
    try:
        # Initialize agent for VALD interpretation
        agent = ClinicalPrognosisAgent()
        
        # Create mock VALD data structure
        from LLM.prognosis.prognosis_agent import VALDAssessment
        vald_data = VALDAssessment(
            strength_asymmetry_percent=request.strength_asymmetry_percent,
            rom_asymmetry_degrees=request.rom_asymmetry_degrees,
            absolute_force_level=request.absolute_force_level,
            is_first_assessment=request.is_first_assessment
        )
        
        # Interpret VALD findings
        interpretation = agent._interpret_vald_findings(vald_data)
        
        # Determine significance level
        significance = "Normal"
        if request.strength_asymmetry_percent > 25 or request.rom_asymmetry_degrees > 15:
            significance = "Severe"
        elif request.strength_asymmetry_percent > 20 or request.rom_asymmetry_degrees > 10:
            significance = "Moderate"
        elif request.strength_asymmetry_percent > 15 or request.rom_asymmetry_degrees > 5:
            significance = "Mild"
        
        # Generate recommendations
        recommendations = []
        if request.strength_asymmetry_percent > 15:
            recommendations.append("Targeted strength training for asymmetry correction")
        if request.absolute_force_level == "Low":
            recommendations.append("Progressive strength and conditioning program")
        if request.is_first_assessment:
            recommendations.append("Establish baseline and plan follow-up assessments")
        
        # Follow-up timeline
        if significance in ["Severe", "Moderate"]:
            follow_up = "2-4 weeks"
        elif significance == "Mild":
            follow_up = "4-6 weeks"
        else:
            follow_up = "6-8 weeks"
        
        return VALDInterpretationResponse(
            interpretation=interpretation,
            significance_level=significance,
            recommendations=recommendations,
            follow_up_timeline=follow_up
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"VALD interpretation failed: {str(e)}")


@router.get("/patients/with-vald")
async def get_patients_with_vald_data():
    """
    Get list of patients who have VALD assessment data available.
    Useful for identifying which patients can be analyzed with the prognosis agent.
    """
    
    try:
        # Load test data to find patients with VALD data
        import json
        test_file = Path(__file__).parent.parent.parent / "LLM" / "test.json"
        
        with open(test_file, 'r') as f:
            patients = json.load(f)
        
        patients_with_vald = []
        
        for patient in patients:
            patient_id = patient.get("patient_id")
            patient_name = patient.get("patient_name", "Unknown")
            
            # Check if patient has VALD data
            has_strength_data = patient.get("strength_asymmetry_percent") is not None
            has_force_data = patient.get("absolute_force_level") is not None
            has_rom_data = patient.get("rom_asymmetry_degrees") is not None
            
            if has_strength_data or has_force_data or has_rom_data:
                patients_with_vald.append({
                    "patient_id": patient_id,
                    "patient_name": patient_name,
                    "vald_data_available": {
                        "strength_asymmetry": has_strength_data,
                        "absolute_force": has_force_data,
                        "rom_asymmetry": has_rom_data
                    },
                    "strength_asymmetry_percent": patient.get("strength_asymmetry_percent"),
                    "absolute_force_level": patient.get("absolute_force_level")
                })
        
        return {
            "total_patients_with_vald": len(patients_with_vald),
            "patients": patients_with_vald
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve VALD patients: {str(e)}")


@router.get("/health")
async def prognosis_health_check():
    """Health check for prognosis service."""
    
    try:
        # Test agent initialization
        agent = ClinicalPrognosisAgent()
        
        return {
            "status": "healthy",
            "service": "Clinical Prognosis Agent",
            "model": "gemini-2.5-flash",
            "features": [
                "AI-powered provisional diagnosis",
                "VALD assessment integration", 
                "Clinical reasoning analysis",
                "Risk factor identification",
                "Treatment recommendations"
            ]
        }
        
    except Exception as e:
        return {
            "status": "unhealthy",
            "error": str(e)
        }