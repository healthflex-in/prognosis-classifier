#!/usr/bin/env python3
"""
Advanced Clinical Prognosis Agent
Analyzes patient conditions and provides evidence-based provisional diagnoses using:
- Clinical data and VALD assessments
- Force production analysis and absolute values
- Web research for normative data and evidence-based prognosis
- Comprehensive biomechanical assessment
"""

import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal
from pydantic import BaseModel, Field
from dotenv import load_dotenv

# LangChain Google Vertex AI
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, SystemMessage
import warnings

# Suppress deprecation warnings
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_google_vertexai")

# Load environment
backend_env = Path(__file__).parent.parent.parent / ".env"  # prognosis -> LLM -> backend
if backend_env.exists():
    load_dotenv(backend_env)
else:
    load_dotenv()


class VALDAssessment(BaseModel):
    """Enhanced VALD assessment data structure with comprehensive force analysis."""
    
    assessment_date: Optional[str] = Field(description="Date of VALD assessment")
    strength_asymmetry_percent: Optional[float] = Field(description="Strength asymmetry percentage")
    rom_asymmetry_degrees: Optional[float] = Field(description="ROM asymmetry in degrees")
    absolute_force_level: Optional[Literal["Low", "Medium", "High"]] = Field(description="Absolute force level")
    is_first_assessment: bool = Field(default=False, description="Whether this is the first VALD assessment")
    
    # Enhanced force production metrics
    peak_force_newtons: Optional[float] = Field(description="Peak force production in Newtons")
    rate_of_force_development: Optional[float] = Field(description="Rate of force development (N/s)")
    force_at_250ms: Optional[float] = Field(description="Force at 250ms (early force production)")
    bilateral_force_ratio: Optional[float] = Field(description="Bilateral force ratio (affected/unaffected)")
    
    # Normative data comparison
    age_matched_percentile: Optional[int] = Field(description="Percentile compared to age-matched norms")
    sport_specific_percentile: Optional[int] = Field(description="Percentile compared to sport-specific norms")
    
    # Movement quality indicators
    movement_variability: Optional[float] = Field(description="Movement variability coefficient")
    compensation_patterns: List[str] = Field(default_factory=list, description="Identified compensation patterns")


class EvidenceBasedFindings(BaseModel):
    """Evidence-based research findings for prognosis."""
    
    research_summary: str = Field(description="Summary of relevant research findings")
    normative_data_comparison: str = Field(description="Comparison to normative population data")
    prognostic_indicators: List[str] = Field(description="Evidence-based prognostic indicators")
    treatment_efficacy_data: str = Field(description="Evidence for treatment approaches")
    return_to_activity_predictors: List[str] = Field(description="Predictors of successful return to activity")


class ClinicalFindings(BaseModel):
    """Clinical examination findings."""
    
    chief_complaint: str = Field(description="Primary complaint from patient")
    clinical_history: str = Field(description="Clinical history and background")
    subjective_notes: str = Field(description="Subjective examination findings")
    duration_months: Optional[float] = Field(description="Duration of symptoms in months")
    clinical_stage: str = Field(description="Clinical stage (acute, subacute, chronic)")
    primary_joint: str = Field(description="Primary joint affected")
    functional_region: str = Field(description="Functional region affected")


# ============================================================================
# Tier System Models (matching the Provisional Diagnosis AI View framework)
# ============================================================================

class ProbabilityTier(BaseModel):
    """Probability tier for a diagnosis (Tier 1-5 system)."""
    
    tier: int = Field(description="Tier 1-5: 1=Very Unlikely, 2=Unlikely, 3=Plausible, 4=Likely, 5=Very Likely", ge=1, le=5)
    label: str = Field(description="Tier label: Very Unlikely / Unlikely / Plausible / Likely / Very Likely")
    rationale: str = Field(description="Why this tier was assigned — evidence supporting or against")


class DiagnosticBucket(BaseModel):
    """Primary and secondary diagnostic bucket assignment."""
    
    primary_bucket: str = Field(description="Primary diagnostic bucket / category")
    secondary_bucket: Optional[str] = Field(description="Secondary contributing bucket", default=None)
    bucket_reasoning: str = Field(description="Why these buckets were assigned")


class DifferentialDiagnosis(BaseModel):
    """A single differential diagnosis with tier and decision-changing impact."""
    
    diagnosis: str = Field(description="Differential diagnosis label")
    tier: int = Field(description="Probability tier 1-5", ge=1, le=5)
    tier_label: str = Field(description="Tier label")
    fits_because: List[str] = Field(description="Evidence that supports this differential")
    directional_impact: str = Field(description="How this differential would change rehab direction or constraints if confirmed")
    included_reason: str = Field(description="Why this differential is decision-changing (not just semantic)")


class DiagnosticSufficiency(BaseModel):
    """Diagnostic sufficiency gate — does the data converge enough?"""
    
    is_sufficient: bool = Field(description="True if intake + objective + biomechanics converge to support provisional direction")
    sufficiency_answer: str = Field(description="Yes/No with brief explanation")
    driver_systems: List[Dict[str, str]] = Field(
        description="Table of driver systems: [{driver, evidence_present, rehab_direction_impact}]",
        default_factory=list
    )
    why_not_sufficient: Optional[str] = Field(
        description="If not sufficient: which competing driver systems prevent convergence",
        default=None
    )


class DecisionChangingMissingData(BaseModel):
    """Missing data that could re-rank differentials or change rehab direction."""
    
    category: str = Field(description="What clinical question this data would answer")
    missing_tests: List[str] = Field(description="Specific tests or data points missing")
    impact_if_positive: str = Field(description="How results would change diagnosis or direction")


class PrognosisAnalysis(BaseModel):
    """
    Comprehensive prognosis analysis using the Provisional Diagnosis AI View framework.
    Includes probability tier system, diagnostic sufficiency gating, and decision-changing differentials.
    """
    
    # ── Intake snapshot ──────────────────────────────────────────────────────
    intake_snapshot: str = Field(description="Condensed summary of primary complaints, context, and irritability")
    
    # ── Biomechanical findings ────────────────────────────────────────────────
    biomechanical_summary: str = Field(description="Summary of VALD findings and what they support/rule out")
    force_production_analysis: str = Field(description="Detailed force production analysis — absolute values, asymmetry, movement quality")
    biomechanical_deficits: List[str] = Field(description="Identified biomechanical deficits from VALD")
    vald_supports_diagnosis: bool = Field(description="Whether VALD data supports the provisional diagnosis")
    
    # ── Provisional diagnosis with tier ──────────────────────────────────────
    provisional_diagnosis: str = Field(description="AI-generated provisional diagnosis label")
    diagnostic_bucket: DiagnosticBucket = Field(description="Primary and secondary bucket assignment")
    probability_tier: ProbabilityTier = Field(description="Probability tier for the provisional diagnosis (1-5)")
    why_not_higher_tier: Optional[str] = Field(
        description="If tier < 5: what prevents higher confidence (competing hypotheses, missing data)",
        default=None
    )
    
    # ── Diagnostic sufficiency gate ───────────────────────────────────────────
    diagnostic_sufficiency: DiagnosticSufficiency = Field(
        description="Does intake + objective + biomechanics converge sufficiently?"
    )
    
    # ── Differential diagnoses (decision-changing only) ───────────────────────
    differential_diagnoses: List[DifferentialDiagnosis] = Field(
        description="Only differentials that would materially change rehab direction or constraints"
    )
    
    # ── Decision-changing missing data ────────────────────────────────────────
    decision_changing_missing_data: List[DecisionChangingMissingData] = Field(
        description="Only missing data that could re-rank differentials or change direction"
    )
    
    # ── Evidence-based insights ───────────────────────────────────────────────
    research_evidence: EvidenceBasedFindings = Field(description="Evidence-based research findings")
    
    # ── Risk / protective factors ─────────────────────────────────────────────
    risk_factors: List[str] = Field(description="Identified risk factors")
    protective_factors: List[str] = Field(description="Identified protective factors")
    
    # ── Prognosis ─────────────────────────────────────────────────────────────
    expected_recovery_timeline: str = Field(description="Evidence-based recovery timeline")
    return_to_activity_probability: str = Field(description="Probability of successful return to activity")
    
    # ── Treatment ─────────────────────────────────────────────────────────────
    recommended_interventions: List[str] = Field(description="Evidence-based treatment interventions")
    contraindicated_activities: List[str] = Field(description="Activities to avoid during recovery")
    
    # ── Red flags ─────────────────────────────────────────────────────────────
    red_flags: List[str] = Field(description="Any red flags identified")
    
    # ── Follow-up ─────────────────────────────────────────────────────────────
    follow_up_vald_recommended: bool = Field(description="Whether follow-up VALD assessment is recommended")
    monitoring_parameters: List[str] = Field(description="Parameters to monitor during treatment")
    reassessment_timeline: str = Field(description="Recommended reassessment timeline")
    
    # ── Positioning summary ───────────────────────────────────────────────────
    positioning_summary: Dict[str, str] = Field(
        description="V4-style summary table: {provisional_bucket, probability, sufficiency, competing_drivers, additional_data_required}",
        default_factory=dict
    )


def clean_json_response(response: str) -> str:
    """
    Cleans an LLM response string to extract a valid JSON object.
    Strips markdown fences, removes trailing commas, and filters out comments.
    """
    import re
    # 1. Strip markdown code fences (```json ... ``` or ``` ...)
    response = re.sub(r'```(?:json)?\s*([\s\S]*?)\s*```', r'\1', response)

    # 2. Extract the first { ... } or [ ... ] structure
    json_match = re.search(r'(\{[\s\S]*\}|\[[\s\S]*\])', response)
    if json_match:
        json_str = json_match.group(1)
    else:
        json_str = response

    # 3. Remove single-line comments (// or #) - careful with URLs
    json_str = re.sub(r'(?m)^\s*//.*$', '', json_str)
    json_str = re.sub(r'(?m)^\s*#.*$', '', json_str)

    # 4. Remove trailing commas before } or ]
    json_str = re.sub(r',\s*(\}|\])', r'\1', json_str)

    return json_str.strip()

class ClinicalPrognosisAgent:
    """
    Advanced AI agent that analyzes patient conditions and provides evidence-based provisional diagnoses
    using clinical data, comprehensive VALD assessment results, and web research for normative data.
    """

    def __init__(self):
        # Vertex AI configuration
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

        if not self.project_id:
            raise RuntimeError("GOOGLE_CLOUD_PROJECT not set in environment")
        if not self.creds_path or not os.path.exists(self.creds_path):
            raise RuntimeError(f"GOOGLE_APPLICATION_CREDENTIALS not set or file not found: {self.creds_path}")

        # Initialize LangChain Vertex AI LLM
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = self.creds_path
        
        self.llm = ChatVertexAI(
            model_name="gemini-2.5-flash",
            project=self.project_id,
            location=self.location,
            temperature=0.1,
            max_output_tokens=8192,
        )
        
        print(f"🏥 Advanced Clinical Prognosis Agent initialized with model: gemini-2.5-flash")

    def _research_condition_online(self, condition: str, joint: str, age_group: str = "adult") -> str:
        """
        Research the condition online to gather evidence-based prognosis data.
        This simulates web research - in production, you'd use actual web search APIs.
        """
        
        # Simulate research findings based on common conditions
        research_database = {
            "knee": {
                "meniscal": {
                    "prognosis": "Good to excellent prognosis with appropriate treatment. 80-90% return to pre-injury activity levels within 3-6 months.",
                    "force_implications": "Quadriceps strength deficits of 15-25% common initially. Force asymmetry >20% associated with delayed recovery.",
                    "normative_data": "Healthy adults: Bilateral force ratio 0.90-1.10. Athletes: >0.95 for return to sport."
                },
                "patellofemoral": {
                    "prognosis": "Variable prognosis. 60-80% good outcomes with conservative treatment over 6-12 months.",
                    "force_implications": "Quadriceps weakness and altered activation patterns common. VMO:VL ratio important.",
                    "normative_data": "Peak force deficits of 10-30% common. Early force production (0-250ms) particularly affected."
                }
            },
            "lumbar": {
                "discogenic": {
                    "prognosis": "Generally favorable with conservative treatment. 70-85% improvement within 6-12 weeks.",
                    "force_implications": "Core stability and hip extensor strength deficits common. Asymmetrical loading patterns.",
                    "normative_data": "Hip extensor force asymmetry >15% associated with recurrence risk."
                }
            },
            "shoulder": {
                "rotator_cuff": {
                    "prognosis": "Age-dependent. <40 years: 85-95% good outcomes. >60 years: 60-75% good outcomes.",
                    "force_implications": "External rotation strength deficits of 20-40% common. Scapular dyskinesis present.",
                    "normative_data": "ER:IR strength ratio should be >0.66. Force production rate critical for overhead athletes."
                }
            }
        }
        
        # Extract relevant research data
        joint_lower = joint.lower()
        condition_lower = condition.lower()
        
        research_data = "Limited specific research data available."
        
        if joint_lower in research_database:
            for condition_key, data in research_database[joint_lower].items():
                if condition_key in condition_lower:
                    research_data = f"Research Evidence: {data['prognosis']} Force Analysis: {data['force_implications']} Normative Data: {data['normative_data']}"
                    break
        
        return research_data

    def _analyze_force_production_comprehensively(self, vald_data: VALDAssessment, 
                                                clinical_findings: ClinicalFindings) -> str:
        """
        Comprehensive analysis of force production data beyond just asymmetry.
        """
        
        analysis_points = []
        
        # Absolute force level analysis
        if vald_data.absolute_force_level:
            force_level = vald_data.absolute_force_level
            if force_level == "Low":
                analysis_points.append("Absolute force production below normative values (<80th percentile) indicates significant strength deficit requiring targeted intervention")
            elif force_level == "Medium":
                analysis_points.append("Absolute force production within normal range (80-120th percentile) but may benefit from optimization")
            else:  # High
                analysis_points.append("Absolute force production above average (>120th percentile) suggesting good strength capacity")
        
        # Asymmetry analysis in context
        if vald_data.strength_asymmetry_percent is not None:
            asymmetry = vald_data.strength_asymmetry_percent
            
            # Context-dependent asymmetry interpretation
            if clinical_findings.clinical_stage == "acute":
                threshold = 10  # Lower threshold for acute conditions
            elif clinical_findings.clinical_stage == "chronic":
                threshold = 20  # Higher threshold acceptable for chronic conditions
            else:
                threshold = 15  # Standard threshold
            
            if asymmetry > threshold:
                analysis_points.append(f"Strength asymmetry ({asymmetry:.1f}%) exceeds acceptable threshold for {clinical_findings.clinical_stage} conditions ({threshold}%)")
            else:
                analysis_points.append(f"Strength asymmetry ({asymmetry:.1f}%) within acceptable range for {clinical_findings.clinical_stage} stage")
        
        # Rate of force development implications
        if vald_data.rate_of_force_development:
            rfd = vald_data.rate_of_force_development
            analysis_points.append(f"Rate of force development: {rfd} N/s - critical for explosive movements and injury prevention")
        
        # Early force production (0-250ms) analysis
        if vald_data.force_at_250ms:
            early_force = vald_data.force_at_250ms
            analysis_points.append(f"Early force production (250ms): {early_force}N - important for reactive strength and stability")
        
        # Movement quality considerations
        if vald_data.movement_variability:
            variability = vald_data.movement_variability
            if variability > 0.15:  # High variability
                analysis_points.append(f"High movement variability ({variability:.2f}) suggests motor control deficits requiring neuromuscular re-education")
            else:
                analysis_points.append(f"Movement variability ({variability:.2f}) within normal limits indicating good motor control")
        
        # Compensation patterns
        if vald_data.compensation_patterns:
            patterns = ", ".join(vald_data.compensation_patterns)
            analysis_points.append(f"Identified compensation patterns: {patterns} - require specific corrective interventions")
        
        return "; ".join(analysis_points) if analysis_points else "Limited force production data available for comprehensive analysis"

    def _get_evidence_based_findings(self, clinical_findings: ClinicalFindings, 
                                   vald_data: VALDAssessment) -> EvidenceBasedFindings:
        """
        Gather evidence-based findings through research and normative data comparison.
        """
        
        # Research the condition
        research_summary = self._research_condition_online(
            clinical_findings.chief_complaint,
            clinical_findings.primary_joint,
            "adult"  # Could be enhanced with actual age data
        )
        
        # Normative data comparison
        normative_comparison = "Comparison to normative data: "
        if vald_data.age_matched_percentile:
            normative_comparison += f"Age-matched percentile: {vald_data.age_matched_percentile}th percentile. "
        if vald_data.sport_specific_percentile:
            normative_comparison += f"Sport-specific percentile: {vald_data.sport_specific_percentile}th percentile. "
        
        if not vald_data.age_matched_percentile and not vald_data.sport_specific_percentile:
            normative_comparison += "Limited normative comparison data available."
        
        # Prognostic indicators based on evidence
        prognostic_indicators = []
        
        if vald_data.absolute_force_level == "Low":
            prognostic_indicators.append("Low absolute force production associated with delayed recovery")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 20:
            prognostic_indicators.append("Significant strength asymmetry (>20%) associated with increased re-injury risk")
        
        if clinical_findings.clinical_stage == "chronic":
            prognostic_indicators.append("Chronic condition may require extended rehabilitation timeline")
        
        if clinical_findings.duration_months and clinical_findings.duration_months > 12:
            prognostic_indicators.append("Duration >12 months associated with more complex recovery patterns")
        
        # Treatment efficacy data
        treatment_efficacy = "Evidence-based treatment approaches show: "
        if "knee" in clinical_findings.primary_joint.lower():
            treatment_efficacy += "Strength training combined with neuromuscular control exercises most effective. "
        elif "lumbar" in clinical_findings.primary_joint.lower():
            treatment_efficacy += "Motor control exercises combined with graded loading most effective. "
        elif "shoulder" in clinical_findings.primary_joint.lower():
            treatment_efficacy += "Progressive loading with scapular stabilization most effective. "
        
        treatment_efficacy += "Manual therapy provides short-term benefits when combined with exercise."
        
        # Return to activity predictors
        return_predictors = [
            "Strength asymmetry <10% at discharge",
            "Pain levels <2/10 during functional activities",
            "Successful completion of sport-specific movement patterns"
        ]
        
        if vald_data.absolute_force_level in ["Medium", "High"]:
            return_predictors.append("Adequate absolute force production achieved")
        
        return EvidenceBasedFindings(
            research_summary=research_summary,
            normative_data_comparison=normative_comparison,
            prognostic_indicators=prognostic_indicators,
            treatment_efficacy_data=treatment_efficacy,
            return_to_activity_predictors=return_predictors
        )

    def _extract_vald_data(self, patient_data: Dict[str, Any]) -> VALDAssessment:
        """Extract VALD assessment data — uses vald_exercises from first session where available."""

        strength_asymmetry = patient_data.get("strength_asymmetry_percent")
        rom_asymmetry = patient_data.get("rom_asymmetry_degrees")
        force_level = patient_data.get("absolute_force_level")
        vald_exercises: Dict[str, Any] = patient_data.get("vald_exercises", {})

        # Derive summary metrics from actual exercise data if available
        assessment_date = None
        peak_force_newtons = None
        bilateral_force_ratio = None

        if vald_exercises:
            # Use the session date from the first exercise entry
            first_ex = next(iter(vald_exercises.values()))
            assessment_date = first_ex.get("session_date")

            # Aggregate across exercises: pick the highest max force seen
            all_left, all_right, all_asym = [], [], []
            for ex in vald_exercises.values():
                if ex.get("left_max_force_N") is not None:
                    all_left.append(ex["left_max_force_N"])
                if ex.get("right_max_force_N") is not None:
                    all_right.append(ex["right_max_force_N"])
                if ex.get("asymmetry_pct") is not None:
                    all_asym.append(abs(ex["asymmetry_pct"]))

            if all_left and all_right:
                avg_left = sum(all_left) / len(all_left)
                avg_right = sum(all_right) / len(all_right)
                peak_force_newtons = max(max(all_left), max(all_right))
                bilateral_force_ratio = round(min(avg_left, avg_right) / max(avg_left, avg_right), 3) if max(avg_left, avg_right) > 0 else None
                if strength_asymmetry is None and all_asym:
                    strength_asymmetry = round(sum(all_asym) / len(all_asym), 2)
                if force_level is None:
                    avg_force = (avg_left + avg_right) / 2
                    force_level = "High" if avg_force > 500 else "Medium" if avg_force > 300 else "Low"

        # Compensation patterns from subjective notes
        subjective_notes = patient_data.get("source_data", {}).get("subjective_notes", "")
        subjective_lower = subjective_notes.lower()
        compensation_patterns = []
        for keyword, pattern in {
            "hip drop": "Trendelenburg pattern",
            "knee valgus": "Dynamic knee valgus",
            "trunk lean": "Lateral trunk lean",
            "early heel rise": "Premature heel rise",
            "guarding": "Protective guarding pattern",
        }.items():
            if keyword in subjective_lower:
                compensation_patterns.append(pattern)

        is_first_assessment = bool(vald_exercises)  # True if we have first-session data

        return VALDAssessment(
            assessment_date=assessment_date,
            strength_asymmetry_percent=strength_asymmetry,
            rom_asymmetry_degrees=rom_asymmetry,
            absolute_force_level=force_level,
            is_first_assessment=is_first_assessment,
            peak_force_newtons=peak_force_newtons,
            rate_of_force_development=None,
            force_at_250ms=None,
            bilateral_force_ratio=bilateral_force_ratio,
            age_matched_percentile=None,
            sport_specific_percentile=None,
            movement_variability=None,
            compensation_patterns=compensation_patterns
        )

    def _extract_clinical_findings(self, patient_data: Dict[str, Any]) -> ClinicalFindings:
        """Extract clinical findings from patient record."""
        
        source_data = patient_data.get("source_data", {})
        extracted_fields = patient_data.get("extracted_fields", {})
        
        # Extract basic clinical data
        chief_complaint = source_data.get("chief_complaint", "")
        clinical_history = source_data.get("clinical_history", "")
        subjective_notes = source_data.get("subjective_notes", "")
        
        # Extract processed fields
        clinical_stage = extracted_fields.get("clinical_stage", {}).get("stage", "unknown")
        joint_mapping = extracted_fields.get("joint_mapping", {})
        primary_joint = joint_mapping.get("primary_joint", "unknown")
        functional_region = joint_mapping.get("functional_region", "unknown")
        
        # Estimate duration from clinical stage and history
        duration_months = None
        history_lower = clinical_history.lower()
        import re as _re
        years_match = _re.search(r'(\d+)\s*years?', history_lower)
        months_match = _re.search(r'(\d+)\s*months?', history_lower)
        weeks_match = _re.search(r'(\d+)\s*weeks?', history_lower)
        if years_match:
            duration_months = int(years_match.group(1)) * 12
        elif months_match:
            duration_months = int(months_match.group(1))
        elif weeks_match:
            duration_months = int(weeks_match.group(1)) / 4
        
        return ClinicalFindings(
            chief_complaint=chief_complaint,
            clinical_history=clinical_history,
            subjective_notes=subjective_notes,
            duration_months=duration_months,
            clinical_stage=clinical_stage,
            primary_joint=primary_joint,
            functional_region=functional_region
        )

    def _format_vald_exercises(self, vald_exercises: Dict[str, Any]) -> str:
        """Format vald_exercises dict into a readable string for the AI prompt."""
        if not vald_exercises:
            return "No VALD exercise data available for first session."
        first = next(iter(vald_exercises.values()))
        lines = [f"Session date: {first.get('session_date', 'unknown')}"]
        for name, m in vald_exercises.items():
            parts = []
            if m.get("type") == "forcedeck":
                if m.get("asymmetry_pct") is not None:
                    parts.append(f"asym={m['asymmetry_pct']:.1f}%")
                if m.get("peak_power") is not None:
                    parts.append(f"peak_power={m['peak_power']:.1f}W")
                ex_type = m.get("exercise_type", "")
                lines.append(f"  {name} [{ex_type}]: {', '.join(parts) if parts else 'no data'}")
            else:
                if m.get("left_max_force_N") is not None:
                    parts.append(f"L={m['left_max_force_N']:.1f}N")
                if m.get("right_max_force_N") is not None:
                    parts.append(f"R={m['right_max_force_N']:.1f}N")
                if m.get("asymmetry_pct") is not None:
                    parts.append(f"asym={m['asymmetry_pct']:.1f}%")
                lines.append(f"  {name}: {', '.join(parts) if parts else 'no data'}")
        return "\n".join(lines)
        return "\n".join(lines)

    def analyze_patient_prognosis(self, patient_data: Dict[str, Any]) -> PrognosisAnalysis:
        """
        Analyze patient condition and provide comprehensive evidence-based prognosis using 
        clinical data, comprehensive VALD assessments, and research evidence.
        """
        
        # Extract structured data
        vald_data = self._extract_vald_data(patient_data)
        clinical_findings = self._extract_clinical_findings(patient_data)
        
        # Get evidence-based findings through research
        evidence_findings = self._get_evidence_based_findings(clinical_findings, vald_data)
        
        # Comprehensive force production analysis
        force_analysis = self._analyze_force_production_comprehensively(vald_data, clinical_findings)
        
        # Get existing provisional diagnosis for comparison
        existing_diagnosis = patient_data.get("source_data", {}).get("provisional_diagnosis_raw", "")
        
        # Create enhanced prompt for AI analysis
        system_prompt = """You are an expert clinical physiotherapist and diagnostician specializing in musculoskeletal conditions.

You use the "Provisional Diagnosis AI View" framework. You MUST respond with a single valid JSON object — no markdown, no prose, no code fences.

PROBABILITY TIER SYSTEM (1-5):
- Tier 5 — Very Likely: Multi-layer convergence (history + objective + biomechanics all align, no competing Tier 4 drivers)
- Tier 4 — Likely: Strong positives but meaningful alternative explanations exist
- Tier 3 — Plausible: Fits the data but not dominant
- Tier 2 — Unlikely: Some fit but current dataset doesn't support it
- Tier 1 — Very Unlikely: Rule-out only

RULES:
- Differentials must be DECISION-CHANGING: only include if confirming it would materially change rehab direction, constraints, or referral pathway — NOT just because it's plausible
- A differential MUST have a tier >= the provisional diagnosis tier — if it's less likely than the primary, it cannot displace it and should NOT be listed
- If the provisional is Tier 5, there are no valid differentials — return an empty array
- Prefer 1-3 high-quality differentials over a long list of plausible ones
- Do NOT include differentials that would result in the same rehab program as the provisional diagnosis
- Sufficiency gate must be honest — don't force convergence if drivers overlap
- Tier assignment must reflect actual data convergence, not optimism
- VALD analysis must address absolute values, not just asymmetry
- Low absolute force = global weakness; asymmetric force = unilateral deficit

Respond with this exact JSON structure:
{
  "intake_snapshot": "string — condensed complaint summary with context and irritability flags",
  "provisional_diagnosis": "string — specific diagnosis label (not 'Unknown')",
  "diagnostic_bucket": {
    "primary_bucket": "string",
    "secondary_bucket": "string or null",
    "bucket_reasoning": "string"
  },
  "probability_tier": {
    "tier": 1-5,
    "label": "Very Unlikely|Unlikely|Plausible|Likely|Very Likely",
    "rationale": "string — why this tier, what evidence supports/against"
  },
  "why_not_higher_tier": "string or null — what prevents higher confidence",
  "biomechanical_summary": "string — what VALD supports and rules out",
  "vald_supports_diagnosis": true/false,
  "biomechanical_deficits": ["string"],
  "diagnostic_sufficiency": {
    "is_sufficient": true/false,
    "sufficiency_answer": "string",
    "driver_systems": [{"driver": "string", "evidence_present": "Yes/No/Partial", "rehab_direction_impact": "string"}],
    "why_not_sufficient": "string or null"
  },
  "differential_diagnoses": [
    {
      "diagnosis": "string",
      "tier": 1-5,
      "tier_label": "string",
      "fits_because": ["string"],
      "directional_impact": "string — how rehab changes if confirmed",
      "included_reason": "string — what decision this changes"
    }
  ],
  "decision_changing_missing_data": [
    {
      "category": "string",
      "missing_tests": ["string"],
      "impact_if_positive": "string"
    }
  ],
  "risk_factors": ["string"],
  "protective_factors": ["string"],
  "expected_recovery_timeline": "string",
  "return_to_activity_probability": "string",
  "recommended_interventions": ["string"],
  "contraindicated_activities": ["string"],
  "red_flags": ["string"],
  "monitoring_parameters": ["string"],
  "reassessment_timeline": "string",
  "positioning_summary": {
    "provisional_bucket": "string",
    "probability": "string",
    "sufficiency": "string",
    "competing_drivers": "string",
    "additional_data_required": "string"
  }
}"""

        user_prompt = f"""Analyze this patient using the Provisional Diagnosis AI View framework.

CLINICAL FINDINGS:
- Chief Complaint: {clinical_findings.chief_complaint}
- Clinical History: {clinical_findings.clinical_history}
- Duration: {clinical_findings.duration_months} months (Stage: {clinical_findings.clinical_stage})
- Primary Joint: {clinical_findings.primary_joint}
- Functional Region: {clinical_findings.functional_region}
- Subjective Notes: {clinical_findings.subjective_notes}

VALD BIOMECHANICAL DATA:
- Strength Asymmetry: {vald_data.strength_asymmetry_percent}%
- ROM Asymmetry: {vald_data.rom_asymmetry_degrees}°
- Absolute Force Level: {vald_data.absolute_force_level or 'Not available'}
- Peak Force: {vald_data.peak_force_newtons}N
- Bilateral Force Ratio: {vald_data.bilateral_force_ratio}
- Compensation Patterns: {', '.join(vald_data.compensation_patterns) if vald_data.compensation_patterns else 'None identified'}

FORCE PRODUCTION ANALYSIS:
{force_analysis}

CLINICIAN'S PROVISIONAL DIAGNOSIS: {existing_diagnosis or 'Not provided'}

VALD FIRST-SESSION EXERCISE DATA:
{self._format_vald_exercises(patient_data.get('vald_exercises', {}))}

Return ONLY the JSON object. No markdown, no explanation outside the JSON."""

        ai_text = ""
        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]
            response = self.llm.invoke(messages)
            ai_text = response.content.strip()

            # Use robust cleaning for JSON response
            json_str = clean_json_response(ai_text)
            ai_json = json.loads(json_str)
            return self._build_analysis_from_json(ai_json, vald_data, clinical_findings, evidence_findings)

        except json.JSONDecodeError as e:
            print(f"⚠️  JSON parse failed: {e}")
            # Try to salvage truncated JSON by finding the last complete top-level field
            try:
                # Find the last complete '}' that closes the root object
                last_brace = ai_text.rfind('\n}')
                if last_brace > 0:
                    truncated = ai_text[:last_brace + 2]
                    ai_json = json.loads(truncated)
                    print("   ✅ Recovered from truncated JSON")
                    return self._build_analysis_from_json(ai_json, vald_data, clinical_findings, evidence_findings)
            except Exception:
                pass
            print(f"   AI response (first 500 chars): {ai_text[:500]}")
            return self._create_enhanced_fallback_analysis(
                vald_data, clinical_findings, evidence_findings, existing_diagnosis
            )
        except Exception as e:
            import traceback
            print(f"❌ Error in prognosis analysis: {e}")
            traceback.print_exc()
            return self._create_enhanced_fallback_analysis(
                vald_data, clinical_findings, evidence_findings, existing_diagnosis
            )

    def _build_analysis_from_json(self, data: Dict[str, Any], vald_data: VALDAssessment,
                                   clinical_findings: ClinicalFindings,
                                   evidence_findings: EvidenceBasedFindings) -> PrognosisAnalysis:
        """Build PrognosisAnalysis directly from the AI's JSON response."""

        tier_labels = {1: "Very Unlikely", 2: "Unlikely", 3: "Plausible", 4: "Likely", 5: "Very Likely"}

        # ── Probability tier ──────────────────────────────────────────────────
        pt = data.get("probability_tier", {})
        tier_num = int(pt.get("tier", 3))
        probability_tier = ProbabilityTier(
            tier=tier_num,
            label=pt.get("label", tier_labels.get(tier_num, "Plausible")),
            rationale=pt.get("rationale", "")
        )

        # ── Diagnostic bucket ─────────────────────────────────────────────────
        db = data.get("diagnostic_bucket", {})
        diagnostic_bucket = DiagnosticBucket(
            primary_bucket=db.get("primary_bucket", clinical_findings.primary_joint or "Musculoskeletal"),
            secondary_bucket=db.get("secondary_bucket"),
            bucket_reasoning=db.get("bucket_reasoning", "")
        )

        # ── Diagnostic sufficiency ────────────────────────────────────────────
        ds = data.get("diagnostic_sufficiency", {})
        diagnostic_sufficiency = DiagnosticSufficiency(
            is_sufficient=bool(ds.get("is_sufficient", False)),
            sufficiency_answer=ds.get("sufficiency_answer", ""),
            driver_systems=ds.get("driver_systems", []),
            why_not_sufficient=ds.get("why_not_sufficient")
        )

        # ── Differentials ─────────────────────────────────────────────────────
        provisional_tier = probability_tier.tier
        differentials = []
        for d in data.get("differential_diagnoses", []):
            t = int(d.get("tier", 3))
            # Only include differentials that are at or above the provisional tier
            # — a lower-tier differential cannot displace the primary diagnosis
            if t < provisional_tier:
                continue
            differentials.append(DifferentialDiagnosis(
                diagnosis=d.get("diagnosis", ""),
                tier=t,
                tier_label=d.get("tier_label", tier_labels.get(t, "Plausible")),
                fits_because=d.get("fits_because", []),
                directional_impact=d.get("directional_impact", ""),
                included_reason=d.get("included_reason", "")
            ))

        # ── Missing data ──────────────────────────────────────────────────────
        missing_data = []
        for m in data.get("decision_changing_missing_data", []):
            missing_data.append(DecisionChangingMissingData(
                category=m.get("category", ""),
                missing_tests=m.get("missing_tests", []),
                impact_if_positive=m.get("impact_if_positive", "")
            ))

        return PrognosisAnalysis(
            intake_snapshot=data.get("intake_snapshot", ""),
            biomechanical_summary=data.get("biomechanical_summary", self._interpret_comprehensive_vald_findings(vald_data)),
            force_production_analysis=data.get("force_production_analysis", self._analyze_force_production_comprehensively(vald_data, clinical_findings)),
            biomechanical_deficits=data.get("biomechanical_deficits", []),
            vald_supports_diagnosis=bool(data.get("vald_supports_diagnosis", False)),
            provisional_diagnosis=data.get("provisional_diagnosis", clinical_findings.chief_complaint or "Unknown"),
            diagnostic_bucket=diagnostic_bucket,
            probability_tier=probability_tier,
            why_not_higher_tier=data.get("why_not_higher_tier"),
            diagnostic_sufficiency=diagnostic_sufficiency,
            differential_diagnoses=differentials,
            decision_changing_missing_data=missing_data,
            research_evidence=evidence_findings,
            risk_factors=data.get("risk_factors", []),
            protective_factors=data.get("protective_factors", []),
            expected_recovery_timeline=data.get("expected_recovery_timeline", ""),
            return_to_activity_probability=data.get("return_to_activity_probability", ""),
            recommended_interventions=data.get("recommended_interventions", []),
            contraindicated_activities=data.get("contraindicated_activities", []),
            red_flags=data.get("red_flags", []),
            follow_up_vald_recommended=True,
            monitoring_parameters=data.get("monitoring_parameters", []),
            reassessment_timeline=data.get("reassessment_timeline", "6-8 weeks"),
            positioning_summary=data.get("positioning_summary", {})
        )

    def _infer_probability_tier(self, vald_data: VALDAssessment, clinical_findings: ClinicalFindings, existing_diagnosis: str) -> int:
        """Infer probability tier based on data convergence."""
        score = 0
        if existing_diagnosis:
            score += 2
        if vald_data.absolute_force_level:
            score += 1
        if vald_data.strength_asymmetry_percent is not None:
            score += 1
        if clinical_findings.chief_complaint and len(clinical_findings.chief_complaint) > 20:
            score += 1
        if clinical_findings.duration_months:
            score += 1
        # Multi-region or complex presentation reduces tier
        if clinical_findings.functional_region and "multi" in clinical_findings.functional_region.lower():
            score -= 1
        return max(1, min(5, score))

    def _generate_tiered_differentials(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[DifferentialDiagnosis]:
        """Generate decision-changing differential diagnoses with tiers."""
        differentials = []
        region = (clinical_findings.functional_region or "").lower()
        joint = (clinical_findings.primary_joint or "").lower()
        duration = clinical_findings.duration_months or 0
        
        # Neurodynamic sensitivity — relevant for spine/upper limb
        if any(k in region for k in ["spine", "upper", "cervical"]):
            differentials.append(DifferentialDiagnosis(
                diagnosis="Neurodynamic mechanosensitivity / cervicothoracic contribution",
                tier=4, tier_label="Likely",
                fits_because=["Neural tension signs possible with upper limb/spine involvement", "Trapezius tightness may be protective"],
                directional_impact="Requires neural load pacing, end-range dosing, irritability staging — changes loading constraints significantly",
                included_reason="Would shift emphasis away from local structural rehab toward neural irritability management"
            ))
        
        # Global load tolerance — relevant for chronic/multi-region
        if duration > 3:
            differentials.append(DifferentialDiagnosis(
                diagnosis="Global load tolerance / movement capacity deficit",
                tier=4, tier_label="Likely",
                fits_because=["Chronic duration", "VALD shows " + (vald_data.absolute_force_level or "unknown") + " absolute force"],
                directional_impact="Emphasises capacity restoration and progressive systemic loading over local joint rehab",
                included_reason="Changes rehab from local to systemic — fundamentally different programming"
            ))
        
        # Rotator cuff / shoulder specific
        if "shoulder" in joint:
            differentials.append(DifferentialDiagnosis(
                diagnosis="Subacromial bursitis vs rotator cuff tendinopathy",
                tier=4, tier_label="Likely",
                fits_because=["Overhead pain pattern", "Load-dependent irritability"],
                directional_impact="Bursitis = slower loading progression; tendinopathy = earlier progressive loading",
                included_reason="Changes loading speed and compression tolerance in early rehab"
            ))
        
        # Lumbar referral — relevant for lower limb / posterior chain
        if any(k in region for k in ["lower", "posterior", "lumbar"]):
            differentials.append(DifferentialDiagnosis(
                diagnosis="Lumbar referral / radicular contribution",
                tier=3, tier_label="Plausible",
                fits_because=["Lower limb symptoms", "Posterior chain involvement"],
                directional_impact="Adds neuro screen, irritability framework, avoids provocative flexion loading",
                included_reason="Would change loading choices and add neural precautions"
            ))
        
        return differentials

    def _identify_decision_changing_missing_data(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[DecisionChangingMissingData]:
        """Identify only missing data that could re-rank differentials or change direction."""
        missing = []
        region = (clinical_findings.functional_region or "").lower()
        
        if any(k in region for k in ["spine", "upper", "cervical"]):
            missing.append(DecisionChangingMissingData(
                category="Separate neurodynamic vs structural driver",
                missing_tests=["Myotomes / dermatomes / reflexes", "Symptom change with cervical repositioning", "Neural loading tolerance staging"],
                impact_if_positive="Neurodynamic contribution moves to Tier 5 — changes loading constraints and dosing"
            ))
        
        if not vald_data.strength_asymmetry_percent:
            missing.append(DecisionChangingMissingData(
                category="Quantify bilateral force deficit",
                missing_tests=["ForceFrame isometric testing", "ForceDeck jump/landing assessment"],
                impact_if_positive="Could confirm or rule out unilateral deficit vs global weakness — changes rehab target"
            ))
        
        missing.append(DecisionChangingMissingData(
            category="Confirm primary vs secondary driver",
            missing_tests=["Single-leg squat / step-down quality", "Scapular assistance observation (if shoulder)", "Repeated movement response"],
            impact_if_positive="Identifies whether local control or systemic capacity is the primary driver"
        ))
        
        return missing

    def _interpret_comprehensive_vald_findings(self, vald_data: VALDAssessment) -> str:
        """Comprehensive interpretation of all VALD assessment findings."""
        
        findings = []
        
        # Absolute force analysis (primary focus)
        if vald_data.absolute_force_level:
            if vald_data.absolute_force_level == "Low":
                findings.append("CRITICAL: Low absolute force production indicates significant global weakness requiring immediate strength intervention")
            elif vald_data.absolute_force_level == "Medium":
                findings.append("Moderate absolute force production - adequate for daily activities but may limit higher-level function")
            else:
                findings.append("Good absolute force production capacity - strength adequate for most functional demands")
        
        # Asymmetry in context of absolute values
        if vald_data.strength_asymmetry_percent is not None:
            asymmetry = vald_data.strength_asymmetry_percent
            if vald_data.absolute_force_level == "Low" and asymmetry > 15:
                findings.append(f"Combined low absolute force ({vald_data.absolute_force_level}) with significant asymmetry ({asymmetry:.1f}%) indicates complex bilateral deficit")
            elif asymmetry > 20:
                findings.append(f"Significant strength asymmetry ({asymmetry:.1f}%) requiring targeted unilateral strengthening")
            elif asymmetry > 15:
                findings.append(f"Moderate strength asymmetry ({asymmetry:.1f}%) - monitor and address if functional limitations present")
            else:
                findings.append(f"Acceptable strength asymmetry ({asymmetry:.1f}%) - within normal functional range")
        
        # Normative data comparison
        if vald_data.age_matched_percentile:
            percentile = vald_data.age_matched_percentile
            if percentile < 25:
                findings.append(f"Below average performance ({percentile}th percentile) compared to age-matched peers")
            elif percentile > 75:
                findings.append(f"Above average performance ({percentile}th percentile) compared to age-matched peers")
            else:
                findings.append(f"Average performance ({percentile}th percentile) compared to age-matched peers")
        
        # Movement quality assessment
        if vald_data.movement_variability is not None:
            variability = vald_data.movement_variability
            if variability > 0.15:
                findings.append(f"High movement variability ({variability:.2f}) indicates poor motor control requiring neuromuscular re-education")
            elif variability < 0.10:
                findings.append(f"Excellent movement consistency ({variability:.2f}) indicating good motor control")
            else:
                findings.append(f"Moderate movement variability ({variability:.2f}) - acceptable but could be optimized")
        
        # Compensation patterns
        if vald_data.compensation_patterns:
            patterns = ", ".join(vald_data.compensation_patterns)
            findings.append(f"Movement compensations identified: {patterns} - require specific corrective interventions")
        
        # First assessment significance
        if vald_data.is_first_assessment:
            findings.append("First VALD assessment establishes critical baseline for monitoring treatment progress and return-to-activity decisions")
        
        return "; ".join(findings) if findings else "Limited VALD data available for comprehensive analysis"

    def _identify_comprehensive_risk_factors(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Identify comprehensive risk factors based on evidence and VALD data."""
        
        risk_factors = []
        
        # Clinical risk factors
        if clinical_findings.clinical_stage == "chronic":
            risk_factors.append("Chronic pain condition (>12 weeks) - associated with central sensitization risk")
        
        if clinical_findings.duration_months and clinical_findings.duration_months > 12:
            risk_factors.append("Extended symptom duration (>12 months) - associated with poorer outcomes")
        
        # VALD-based risk factors (comprehensive analysis)
        if vald_data.absolute_force_level == "Low":
            risk_factors.append("Low absolute force production - primary risk factor for delayed recovery and re-injury")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 20:
            risk_factors.append(f"Significant strength asymmetry ({vald_data.strength_asymmetry_percent:.1f}%) - associated with increased re-injury risk")
        
        if vald_data.movement_variability and vald_data.movement_variability > 0.15:
            risk_factors.append("Poor movement control - associated with compensatory movement patterns")
        
        if vald_data.age_matched_percentile and vald_data.age_matched_percentile < 25:
            risk_factors.append("Below-average physical capacity compared to peers - may limit recovery potential")
        
        # Compensation pattern risks
        if vald_data.compensation_patterns:
            risk_factors.append("Movement compensation patterns present - risk of secondary injury development")
        
        return risk_factors

    def _identify_protective_factors(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Identify protective factors that support positive prognosis."""
        
        protective_factors = []
        
        # VALD-based protective factors
        if vald_data.absolute_force_level in ["Medium", "High"]:
            protective_factors.append("Adequate absolute force production - supports functional recovery")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent < 10:
            protective_factors.append("Minimal strength asymmetry - indicates good bilateral function")
        
        if vald_data.movement_variability and vald_data.movement_variability < 0.10:
            protective_factors.append("Excellent movement control - supports stable recovery")
        
        if vald_data.age_matched_percentile and vald_data.age_matched_percentile > 75:
            protective_factors.append("Above-average physical capacity - supports optimal recovery potential")
        
        # Clinical protective factors
        if clinical_findings.clinical_stage in ["acute", "subacute"]:
            protective_factors.append("Early-stage condition - better prognosis for full recovery")
        
        if not vald_data.compensation_patterns:
            protective_factors.append("No significant movement compensations identified")
        
        return protective_factors

    def _calculate_evidence_based_prognosis(self, clinical_findings: ClinicalFindings, 
                                          vald_data: VALDAssessment, 
                                          evidence_findings: EvidenceBasedFindings) -> tuple[str, str]:
        """Calculate evidence-based recovery timeline and return-to-activity probability."""
        
        # Base timeline from clinical stage
        base_timelines = {
            "acute": 4,      # 4 weeks
            "subacute": 8,   # 8 weeks
            "chronic": 16    # 16 weeks
        }
        
        base_weeks = base_timelines.get(clinical_findings.clinical_stage, 12)
        
        # Modify based on VALD findings
        modifier = 1.0
        
        if vald_data.absolute_force_level == "Low":
            modifier *= 1.5  # 50% longer for low force production
        elif vald_data.absolute_force_level == "High":
            modifier *= 0.8  # 20% shorter for high force production
        
        if vald_data.strength_asymmetry_percent:
            if vald_data.strength_asymmetry_percent > 25:
                modifier *= 1.4
            elif vald_data.strength_asymmetry_percent < 10:
                modifier *= 0.9
        
        if vald_data.movement_variability:
            if vald_data.movement_variability > 0.15:
                modifier *= 1.2
            elif vald_data.movement_variability < 0.10:
                modifier *= 0.9
        
        final_weeks = int(base_weeks * modifier)
        
        # Format timeline
        if final_weeks <= 4:
            timeline = f"{final_weeks} weeks"
        elif final_weeks <= 12:
            timeline = f"{final_weeks//4}-{(final_weeks//4)+1} months"
        else:
            timeline = f"{final_weeks//4}-{(final_weeks//4)+2} months"
        
        # Calculate return-to-activity probability
        probability_score = 80  # Base probability
        
        # Adjust based on factors
        if vald_data.absolute_force_level == "Low":
            probability_score -= 20
        elif vald_data.absolute_force_level == "High":
            probability_score += 10
        
        if vald_data.strength_asymmetry_percent:
            if vald_data.strength_asymmetry_percent > 20:
                probability_score -= 15
            elif vald_data.strength_asymmetry_percent < 10:
                probability_score += 10
        
        if clinical_findings.clinical_stage == "chronic":
            probability_score -= 15
        elif clinical_findings.clinical_stage == "acute":
            probability_score += 10
        
        probability_score = max(30, min(95, probability_score))  # Clamp between 30-95%
        
        return timeline, f"{probability_score}% probability of successful return to pre-injury activity level"

    def _generate_evidence_based_interventions(self, clinical_findings: ClinicalFindings, 
                                             vald_data: VALDAssessment, 
                                             evidence_findings: EvidenceBasedFindings) -> List[str]:
        """Generate evidence-based interventions targeting specific deficits."""
        
        interventions = []
        
        # Force production-specific interventions
        if vald_data.absolute_force_level == "Low":
            interventions.append("Progressive resistance training focusing on absolute force development")
            interventions.append("Compound movement patterns to address global strength deficits")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 15:
            interventions.append("Unilateral strength training to address bilateral imbalances")
            interventions.append("Functional movement retraining with emphasis on symmetrical loading")
        
        # Movement quality interventions
        if vald_data.movement_variability and vald_data.movement_variability > 0.15:
            interventions.append("Motor control exercises to improve movement consistency")
            interventions.append("Proprioceptive training and neuromuscular re-education")
        
        # Compensation pattern-specific interventions
        if vald_data.compensation_patterns:
            interventions.append("Movement pattern correction targeting identified compensations")
            interventions.append("Mobility work for restricted movement patterns")
        
        # Stage-specific interventions
        if clinical_findings.clinical_stage == "chronic":
            interventions.append("Pain science education and graded exposure therapy")
            interventions.append("Cognitive-behavioral approaches for chronic pain management")
        
        # Evidence-based additions
        interventions.append("Manual therapy for short-term pain relief and mobility improvement")
        interventions.append("Regular VALD reassessment to monitor objective progress")
        
        return interventions

    def _identify_contraindicated_activities(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Identify activities to avoid during recovery based on deficits."""
        
        contraindications = []
        
        if vald_data.absolute_force_level == "Low":
            contraindications.append("High-load activities until strength improves to Medium level")
            contraindications.append("Explosive/ballistic movements until force production adequate")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 20:
            contraindications.append("Unilateral loading activities that may worsen asymmetry")
            contraindications.append("Sport-specific activities until asymmetry <15%")
        
        if vald_data.movement_variability and vald_data.movement_variability > 0.15:
            contraindications.append("Complex movement patterns until motor control improves")
            contraindications.append("Fatiguing activities that may worsen movement quality")
        
        if clinical_findings.clinical_stage == "acute":
            contraindications.append("Aggressive stretching or mobilization during inflammatory phase")
        
        return contraindications

    def _generate_comprehensive_monitoring_parameters(self, vald_data: VALDAssessment) -> List[str]:
        """Generate comprehensive parameters to monitor during treatment."""
        
        parameters = ["Pain levels (NPRS 0-10)", "Functional capacity and activity tolerance"]
        
        # VALD-specific monitoring
        if vald_data.absolute_force_level:
            parameters.append("Absolute force production progression")
        
        if vald_data.strength_asymmetry_percent is not None:
            parameters.append("Bilateral strength asymmetry reduction")
        
        if vald_data.movement_variability is not None:
            parameters.append("Movement consistency and quality")
        
        if vald_data.compensation_patterns:
            parameters.append("Resolution of movement compensation patterns")
        
        # Functional monitoring
        parameters.extend([
            "Return-to-activity milestones",
            "Patient-reported outcome measures",
            "Objective functional testing results"
        ])
        
        return parameters

    def _determine_reassessment_timeline(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> str:
        """Determine appropriate reassessment timeline based on condition and deficits."""
        
        if clinical_findings.clinical_stage == "acute":
            return "2-3 weeks (post-inflammatory phase)"
        elif vald_data.absolute_force_level == "Low":
            return "4-6 weeks (allow time for strength gains)"
        elif vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 20:
            return "4-6 weeks (monitor asymmetry correction)"
        else:
            return "6-8 weeks (standard reassessment interval)"

    def _extract_comprehensive_indicators(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Extract comprehensive clinical indicators."""
        
        indicators = []
        
        # Primary VALD indicators
        if vald_data.absolute_force_level == "Low":
            indicators.append("Low absolute force production (primary concern)")
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 15:
            indicators.append("Significant bilateral strength imbalance")
        
        if vald_data.movement_variability and vald_data.movement_variability > 0.15:
            indicators.append("Poor motor control and movement consistency")
        
        # Clinical indicators
        if clinical_findings.duration_months and clinical_findings.duration_months > 12:
            indicators.append("Chronic condition with extended duration")
        
        # Normative comparison indicators
        if vald_data.age_matched_percentile and vald_data.age_matched_percentile < 25:
            indicators.append("Below-average physical capacity for age group")
        
        # Movement pattern indicators
        if vald_data.compensation_patterns:
            indicators.append("Movement compensation patterns present")
        
        return indicators

    def _create_enhanced_fallback_analysis(self, vald_data: VALDAssessment, clinical_findings: ClinicalFindings, 
                                         evidence_findings: EvidenceBasedFindings, existing_diagnosis: str) -> PrognosisAnalysis:
        """Create enhanced fallback analysis when AI fails."""
        
        diagnosis = existing_diagnosis or f"{clinical_findings.primary_joint} dysfunction"
        tier = self._infer_probability_tier(vald_data, clinical_findings, existing_diagnosis)
        tier_labels = {1: "Very Unlikely", 2: "Unlikely", 3: "Plausible", 4: "Likely", 5: "Very Likely"}
        
        return PrognosisAnalysis(
            intake_snapshot=f"{clinical_findings.primary_joint} complaint — {clinical_findings.clinical_stage} stage. {clinical_findings.subjective_notes[:200] if clinical_findings.subjective_notes else 'No subjective notes available.'}",
            biomechanical_summary=self._interpret_comprehensive_vald_findings(vald_data),
            force_production_analysis="Limited force production data available — AI analysis unavailable",
            biomechanical_deficits=["Insufficient data for full biomechanical analysis"],
            vald_supports_diagnosis=False,
            provisional_diagnosis=diagnosis,
            diagnostic_bucket=DiagnosticBucket(
                primary_bucket=clinical_findings.functional_region or "Musculoskeletal",
                secondary_bucket=None,
                bucket_reasoning="Assigned from available clinical region data — AI unavailable"
            ),
            probability_tier=ProbabilityTier(
                tier=tier,
                label=tier_labels.get(tier, "Plausible"),
                rationale="Tier inferred from available clinical and VALD data — AI analysis unavailable"
            ),
            why_not_higher_tier="AI analysis unavailable; tier based on heuristic inference only",
            diagnostic_sufficiency=DiagnosticSufficiency(
                is_sufficient=False,
                sufficiency_answer="No — AI analysis unavailable; manual clinical review required",
                driver_systems=[],
                why_not_sufficient="AI analysis failed; cannot assess convergence of intake, objective, and biomechanical data"
            ),
            differential_diagnoses=self._generate_tiered_differentials(clinical_findings, vald_data),
            decision_changing_missing_data=self._identify_decision_changing_missing_data(clinical_findings, vald_data),
            research_evidence=evidence_findings,
            risk_factors=self._identify_comprehensive_risk_factors(clinical_findings, vald_data),
            protective_factors=self._identify_protective_factors(clinical_findings, vald_data),
            expected_recovery_timeline=self._estimate_recovery_timeline(clinical_findings, vald_data),
            return_to_activity_probability="Unable to determine without AI analysis",
            recommended_interventions=self._generate_interventions(clinical_findings, vald_data),
            contraindicated_activities=self._identify_contraindicated_activities(clinical_findings, vald_data),
            red_flags=self._identify_red_flags(clinical_findings),
            follow_up_vald_recommended=True,
            monitoring_parameters=self._generate_comprehensive_monitoring_parameters(vald_data),
            reassessment_timeline=self._determine_reassessment_timeline(clinical_findings, vald_data),
            positioning_summary={
                "provisional_bucket": clinical_findings.functional_region or "Musculoskeletal",
                "probability": tier_labels.get(tier, "Plausible"),
                "sufficiency": "Insufficient — AI unavailable",
                "competing_drivers": "Unknown — manual review required",
                "additional_data_required": "Full AI analysis required"
            }
        )

    def _interpret_vald_findings(self, vald_data: VALDAssessment) -> str:
        """Interpret VALD assessment findings."""
        
        findings = []
        
        if vald_data.strength_asymmetry_percent is not None:
            if vald_data.strength_asymmetry_percent > 20:
                findings.append(f"Significant strength asymmetry ({vald_data.strength_asymmetry_percent:.1f}%) indicating substantial functional deficit")
            elif vald_data.strength_asymmetry_percent > 15:
                findings.append(f"Moderate strength asymmetry ({vald_data.strength_asymmetry_percent:.1f}%) requiring targeted intervention")
            else:
                findings.append(f"Minimal strength asymmetry ({vald_data.strength_asymmetry_percent:.1f}%) within acceptable range")
        
        if vald_data.rom_asymmetry_degrees is not None:
            if vald_data.rom_asymmetry_degrees > 10:
                findings.append(f"Significant ROM asymmetry ({vald_data.rom_asymmetry_degrees}°)")
            else:
                findings.append(f"ROM asymmetry within normal limits ({vald_data.rom_asymmetry_degrees}°)")
        
        if vald_data.absolute_force_level:
            findings.append(f"Absolute force level: {vald_data.absolute_force_level}")
        
        if vald_data.is_first_assessment:
            findings.append("First VALD assessment provides important baseline for monitoring progress")
        
        return "; ".join(findings) if findings else "Limited VALD data available"

    def _extract_key_indicators(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Extract key clinical indicators."""
        
        indicators = []
        
        # Clinical indicators
        if clinical_findings.duration_months and clinical_findings.duration_months > 12:
            indicators.append("Chronic condition (>12 months)")
        
        # VALD indicators
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 15:
            indicators.append("Significant strength asymmetry")
        
        if vald_data.absolute_force_level == "Low":
            indicators.append("Reduced force production capacity")
        
        # Pattern recognition from subjective notes
        if "pain" in clinical_findings.subjective_notes.lower():
            indicators.append("Pain-related movement dysfunction")
        
        return indicators

    def _estimate_recovery_timeline(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> str:
        """Estimate recovery timeline based on clinical and VALD data."""
        
        base_timeline = {
            "acute": "2-6 weeks",
            "subacute": "6-12 weeks", 
            "chronic": "12-24 weeks"
        }
        
        timeline = base_timeline.get(clinical_findings.clinical_stage, "8-16 weeks")
        
        # Modify based on VALD findings
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 25:
            timeline += " (extended due to significant strength deficits)"
        elif vald_data.absolute_force_level == "Low":
            timeline += " (may require additional strength phase)"
        
        return timeline

    def _generate_interventions(self, clinical_findings: ClinicalFindings, vald_data: VALDAssessment) -> List[str]:
        """Generate recommended interventions."""
        
        interventions = ["Manual therapy and movement re-education"]
        
        if vald_data.strength_asymmetry_percent and vald_data.strength_asymmetry_percent > 15:
            interventions.append("Targeted strength training for asymmetry correction")
        
        if vald_data.absolute_force_level == "Low":
            interventions.append("Progressive strength and conditioning program")
        
        if clinical_findings.clinical_stage == "chronic":
            interventions.append("Pain science education and graded exposure")
        
        interventions.append("Regular VALD reassessment to monitor progress")
        
        return interventions

    def _identify_red_flags(self, clinical_findings: ClinicalFindings) -> List[str]:
        """Identify potential red flags."""
        
        red_flags = []
        
        # Check for concerning patterns in history/notes
        concerning_terms = ["trauma", "fracture", "neurological", "bowel", "bladder", "fever"]
        
        combined_text = (clinical_findings.clinical_history + " " + clinical_findings.subjective_notes).lower()
        
        for term in concerning_terms:
            if term in combined_text:
                red_flags.append(f"Potential {term}-related concern mentioned")
        
        return red_flags

    def _generate_differentials(self, clinical_findings: ClinicalFindings) -> List[str]:
        """Generate differential diagnoses."""
        
        differentials = []
        
        # Based on joint/region
        if "spine" in clinical_findings.functional_region.lower():
            differentials.extend(["Discogenic pain", "Facet joint dysfunction", "Myofascial pain"])
        elif "knee" in clinical_findings.primary_joint.lower():
            differentials.extend(["Patellofemoral pain", "Meniscal pathology", "Ligament strain"])
        elif "shoulder" in clinical_findings.primary_joint.lower():
            differentials.extend(["Rotator cuff pathology", "Impingement syndrome", "Adhesive capsulitis"])
        
        return differentials[:3]  # Limit to top 3

    def _generate_monitoring_parameters(self, vald_data: VALDAssessment) -> List[str]:
        """Generate parameters to monitor during treatment."""
        
        parameters = ["Pain levels (NPRS)", "Functional capacity"]
        
        if vald_data.strength_asymmetry_percent is not None:
            parameters.append("Strength asymmetry percentage")
        
        if vald_data.rom_asymmetry_degrees is not None:
            parameters.append("ROM asymmetry")
        
        if vald_data.absolute_force_level:
            parameters.append("Absolute force production")
        
        parameters.append("Return to activity milestones")
        
        return parameters

    def _create_fallback_analysis(self, vald_data: VALDAssessment, clinical_findings: ClinicalFindings, 
                                existing_diagnosis: str) -> PrognosisAnalysis:
        """Create fallback analysis when AI fails."""
        
        diagnosis = existing_diagnosis or f"{clinical_findings.primary_joint} dysfunction"
        tier = self._infer_probability_tier(vald_data, clinical_findings, existing_diagnosis)
        tier_labels = {1: "Very Unlikely", 2: "Unlikely", 3: "Plausible", 4: "Likely", 5: "Very Likely"}
        
        return PrognosisAnalysis(
            intake_snapshot=f"{clinical_findings.primary_joint} complaint — {clinical_findings.clinical_stage} stage.",
            biomechanical_summary=self._interpret_vald_findings(vald_data),
            force_production_analysis="Force production data not available for this analysis",
            biomechanical_deficits=["Insufficient data for biomechanical analysis"],
            vald_supports_diagnosis=False,
            provisional_diagnosis=diagnosis,
            diagnostic_bucket=DiagnosticBucket(
                primary_bucket=clinical_findings.functional_region or "Musculoskeletal",
                secondary_bucket=None,
                bucket_reasoning="Assigned from available clinical region data"
            ),
            probability_tier=ProbabilityTier(
                tier=tier,
                label=tier_labels.get(tier, "Plausible"),
                rationale="Tier inferred from available data — AI analysis unavailable"
            ),
            why_not_higher_tier="AI analysis unavailable",
            diagnostic_sufficiency=DiagnosticSufficiency(
                is_sufficient=False,
                sufficiency_answer="No — insufficient data for convergence assessment",
                driver_systems=[],
                why_not_sufficient="AI analysis failed; manual clinical review required"
            ),
            differential_diagnoses=self._generate_tiered_differentials(clinical_findings, vald_data),
            decision_changing_missing_data=self._identify_decision_changing_missing_data(clinical_findings, vald_data),
            research_evidence=EvidenceBasedFindings(
                condition_prevalence="Unknown",
                evidence_based_interventions=["Comprehensive assessment recommended"],
                prognostic_factors=["Insufficient data"],
                return_to_sport_rates="Unknown",
                recurrence_rates="Unknown"
            ),
            risk_factors=self._identify_comprehensive_risk_factors(clinical_findings, vald_data),
            protective_factors=self._identify_protective_factors(clinical_findings, vald_data),
            expected_recovery_timeline=self._estimate_recovery_timeline(clinical_findings, vald_data),
            return_to_activity_probability="Unable to determine without AI analysis",
            recommended_interventions=self._generate_interventions(clinical_findings, vald_data),
            contraindicated_activities=["Consult healthcare provider"],
            red_flags=self._identify_red_flags(clinical_findings),
            follow_up_vald_recommended=True,
            monitoring_parameters=self._generate_monitoring_parameters(vald_data),
            reassessment_timeline="4-6 weeks",
            positioning_summary={
                "provisional_bucket": clinical_findings.functional_region or "Musculoskeletal",
                "probability": tier_labels.get(tier, "Plausible"),
                "sufficiency": "Insufficient",
                "competing_drivers": "Unknown",
                "additional_data_required": "Full clinical assessment required"
            }
        )


# Rebuild Pydantic models
VALDAssessment.model_rebuild()
ClinicalFindings.model_rebuild()
EvidenceBasedFindings.model_rebuild()
PrognosisAnalysis.model_rebuild()


def analyze_patient_from_file(patient_id: str, test_file_path: str = None) -> PrognosisAnalysis:
    """Analyze a specific patient from the test data file."""
    
    if not test_file_path:
        test_file_path = Path(__file__).parent / "test.json"
    
    try:
        with open(test_file_path, 'r') as f:
            patients = json.load(f)
        
        # Find patient by ID
        patient_data = None
        for patient in patients:
            if patient.get("patient_id") == patient_id:
                patient_data = patient
                break
        
        if not patient_data:
            raise ValueError(f"Patient {patient_id} not found in test data")
        
        # Initialize agent and analyze
        agent = ClinicalPrognosisAgent()
        analysis = agent.analyze_patient_prognosis(patient_data)
        
        return analysis
        
    except Exception as e:
        print(f"❌ Error analyzing patient {patient_id}: {e}")
        raise


if __name__ == "__main__":
    # Test with a sample patient
    try:
        # Use the first patient from test data
        test_file = Path(__file__).parent / "test.json"
        with open(test_file, 'r') as f:
            patients = json.load(f)
        
        if patients:
            patient_id = patients[0]["patient_id"]
            print(f"🔍 Analyzing patient: {patient_id}")
            
            analysis = analyze_patient_from_file(patient_id)
            
            print(f"\n📋 PROGNOSIS ANALYSIS:")
            print(f"Provisional Diagnosis: {analysis.provisional_diagnosis}")
            print(f"Tier: {analysis.probability_tier.tier}/5 — {analysis.probability_tier.label}")
            print(f"Biomechanical Summary: {analysis.biomechanical_summary}")
            print(f"Recovery Timeline: {analysis.expected_recovery_timeline}")
            print(f"Key Interventions: {', '.join(analysis.recommended_interventions)}")
            
    except Exception as e:
        print(f"❌ Test failed: {e}")