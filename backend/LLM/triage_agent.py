#!/usr/bin/env python3
"""
Physiotherapy Triage Agent
Classifies patients into a structured recovery matrix based on diagnosis and complaints.
"""

import os
import json
from typing import List, Dict, Any, Optional
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading

# Pydantic for validation
from pydantic import BaseModel, Field, field_validator

# Google GenAI integration
try:
    from google import genai
    from google.genai import types
except ImportError:
    print("❌ google-genai not installed. Install with: pip install google-genai")
    exit(1)

# Load environment
from dotenv import load_dotenv
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Import filter
import sys
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

import importlib.util
filters_dir = backend_dir / "filters"
filter_module = importlib.util.spec_from_file_location(
    "patient_filter",
    filters_dir / "patient_filter.py"
)
patient_filter_mod = importlib.util.module_from_spec(filter_module)
filter_module.loader.exec_module(patient_filter_mod)
PatientFilter = patient_filter_mod.PatientFilter


# ============================================================================
# Pydantic Models for Structured Output
# ============================================================================

class RiskStratification(BaseModel):
    """Risk stratification based on STarT Back Model."""
    risk_level: str = Field(
        description="Risk level: Low Risk or High Risk (Psychosocially Mediated)",
        pattern="^(Low Risk|High Risk)$"
    )
    psychosocial_flags: List[str] = Field(
        description="List of psychosocial yellow flags identified",
        default_factory=list
    )
    risk_reasoning: str = Field(
        description="Explanation of risk classification"
    )


# Standardized joint/body part values
STANDARD_JOINTS = [
    "Left Knee", "Right Knee", "Bilateral Knee",
    "Left Ankle", "Right Ankle", "Bilateral Ankle",
    "Left Hip", "Right Hip", "Bilateral Hip",
    "Left Shoulder", "Right Shoulder", "Bilateral Shoulder",
    "Cervical Spine", "Thoracic Spine", "Lumbar Spine",
    "Achilles Tendon", "Hamstring", "Patellar Tendon",
    "Other", "Multiple"
]


def normalize_joint_name(joint_name: str) -> str:
    """
    Normalize joint name to standard format.
    
    Args:
        joint_name: Raw joint name from diagnosis or LLM
    
    Returns:
        Standardized joint name
    """
    if not joint_name:
        return "Other"
    
    joint_lower = joint_name.lower().strip()
    
    # Mapping of variations to standard names
    joint_mapping = {
        # Knee variations
        "knee": "Bilateral Knee",
        "l knee": "Left Knee",
        "left knee": "Left Knee",
        "r knee": "Right Knee",
        "right knee": "Right Knee",
        "l-knee": "Left Knee",
        "r-knee": "Right Knee",
        "left knee (": "Left Knee",  # Handle cases like "Left Knee (Hamstring involvement)"
        "right knee (": "Right Knee",
        
        # Ankle variations
        "ankle": "Bilateral Ankle",
        "l ankle": "Left Ankle",
        "left ankle": "Left Ankle",
        "r ankle": "Right Ankle",
        "right ankle": "Right Ankle",
        "achilles": "Achilles Tendon",
        "achilles tendon": "Achilles Tendon",
        
        # Hip variations
        "hip": "Bilateral Hip",
        "l hip": "Left Hip",
        "left hip": "Left Hip",
        "r hip": "Right Hip",
        "right hip": "Right Hip",
        
        # Shoulder variations
        "shoulder": "Bilateral Shoulder",
        "l shoulder": "Left Shoulder",
        "left shoulder": "Left Shoulder",
        "r shoulder": "Right Shoulder",
        "right shoulder": "Right Shoulder",
        
        # Spine variations
        "lumbar": "Lumbar Spine",
        "lumbar spine": "Lumbar Spine",
        "lower back": "Lumbar Spine",
        "cervical": "Cervical Spine",
        "cervical spine": "Cervical Spine",
        "neck": "Cervical Spine",
        "thoracic": "Thoracic Spine",
        "thoracic spine": "Thoracic Spine",
        "upper back": "Thoracic Spine",
        
        # Tendon/muscle variations
        "hamstring": "Hamstring",
        "patellar": "Patellar Tendon",
        "patellar tendon": "Patellar Tendon",
        "patella": "Patellar Tendon",
        "patellofemoral": "Patellar Tendon",
        
        # General/unknown
        "general": "Other",
        "unknown": "Other",
        "multiple": "Multiple",
    }
    
    # Check for exact matches first
    for key, standard in joint_mapping.items():
        if key in joint_lower:
            return standard
    
    # Check if it contains side indicators
    if "left" in joint_lower or "l " in joint_lower:
        if "knee" in joint_lower:
            return "Left Knee"
        elif "ankle" in joint_lower:
            return "Left Ankle"
        elif "hip" in joint_lower:
            return "Left Hip"
        elif "shoulder" in joint_lower:
            return "Left Shoulder"
    
    if "right" in joint_lower or "r " in joint_lower:
        if "knee" in joint_lower:
            return "Right Knee"
        elif "ankle" in joint_lower:
            return "Right Ankle"
        elif "hip" in joint_lower:
            return "Right Hip"
        elif "shoulder" in joint_lower:
            return "Right Shoulder"
    
    # If no match found, return as-is but capitalize properly
    return joint_name.strip().title() if joint_name.strip() else "Other"


class JointSpecificGroup(BaseModel):
    """Joint-specific sub-group classification."""
    group: str = Field(
        description="Group: Posterior Chain Dominant, Anterior Chain Dominant, or Other",
        pattern="^(Posterior Chain Dominant|Anterior Chain Dominant|Other)$"
    )
    primary_joint: str = Field(
        description="Primary joint/area affected. Must be one of: Left Knee, Right Knee, Bilateral Knee, Left Ankle, Right Ankle, Bilateral Ankle, Left Hip, Right Hip, Bilateral Hip, Left Shoulder, Right Shoulder, Bilateral Shoulder, Cervical Spine, Thoracic Spine, Lumbar Spine, Achilles Tendon, Hamstring, Patellar Tendon, Other, Multiple"
    )
    testing_focus: str = Field(
description="Recommended testing focus: ForceFrame isometric or ForceDeck jump/landing"
    )
    group_reasoning: str = Field(
        description="Explanation of group classification"
    )
    
    @classmethod
    def normalize_primary_joint(cls, joint_name: str) -> str:
        """Normalize primary joint name to standard format."""
        return normalize_joint_name(joint_name)


class SourceData(BaseModel):
    """Source data from patient records."""
    provisional_diagnosis_raw: Optional[str] = Field(
        description="Raw provisional diagnosis text from notes",
        default=None
    )
    chief_complaint: Optional[str] = Field(
        description="Chief complaint text",
        default=None
    )
    clinical_history: Optional[str] = Field(
        description="Clinical history text",
        default=None
    )
    subjective_notes: Optional[str] = Field(
        description="Subjective assessment notes",
        default=None
    )
    goals_raw: Optional[str] = Field(
        description="Raw goals/expectations text",
        default=None
    )


class ProvisionalDiagnosisExtraction(BaseModel):
    """Provisional diagnosis extraction details."""
    canonical_label: str = Field(description="Normalized canonical diagnosis category")
    confidence: str = Field(description="Confidence level: high, medium, low")
    raw_matches: List[str] = Field(description="List of raw text matches found", default_factory=list)
    diagnosis_type: str = Field(description="single, multiple, or unclear")


class JointMapping(BaseModel):
    """Joint and functional region mapping."""
    primary_joint: str = Field(description="Primary joint name (standardized)")
    functional_region: str = Field(description="Functional region: upper_limb, lower_limb, spine, posterior_chain, multi_joint")
    is_multi_joint: bool = Field(description="Whether multiple joints are involved", default=False)


class ClinicalStageExtraction(BaseModel):
    """Clinical stage extraction details."""
    stage: str = Field(description="Clinical stage: acute, subacute, chronic, recurrent, pre_hab, post_operative, unclear")
    evidence: List[str] = Field(description="Evidence text supporting the stage classification", default_factory=list)


class ActivityProfileExtraction(BaseModel):
    """Activity profile extraction details."""
    primary_category: str = Field(description="Primary activity category: sedentary, recreationally_active, structured_fitness, competitive, unclear")
    sub_category: Optional[str] = Field(
        description="Sub-category (only if recreationally_active): running_dominant, gym_strength, sport_specific, mixed_fitness, unclear",
        default=None
    )
    evidence: List[str] = Field(description="Evidence text supporting the activity classification", default_factory=list)


class OccupationExtraction(BaseModel):
    """Occupation extraction details."""
    category: str = Field(description="Occupation category: sedentary_desk, manual_physical, student, athlete, retired, unclear")
    evidence: List[str] = Field(description="Evidence text supporting the occupation classification", default_factory=list)


class PainInterferenceExtraction(BaseModel):
    """Pain interference extraction details."""
    category: str = Field(description="Pain interference category: no_interference, activity_interference, work_interference, multi_domain, forced_entry, unclear")
    domains_affected: List[str] = Field(description="List of domains affected by pain", default_factory=list)
    confidence: str = Field(description="Confidence level: high, medium, low")


class PainIntensityNPRS(BaseModel):
    """NPRS extraction details."""
    value: Optional[int] = Field(
        description="NPRS score (0-10) if found",
        default=None,
        ge=0,
        le=10
    )
    scale: str = Field(description="Scale used: NPRS, VAS, or other", default="NPRS")
    found: bool = Field(description="Whether NPRS was found in text", default=False)
    extraction_method: Optional[str] = Field(
        description="How it was extracted: explicit_numeric, inferred, or null",
        default=None
    )
    evidence_text: Optional[str] = Field(
        description="The text where NPRS was found",
        default=None
    )


class IntentExtraction(BaseModel):
    """Intent/expectation extraction details."""
    primary_intent: str = Field(description="Primary intent: pain_relief, return_daily_function, return_activity, return_sport, performance, post_surgical, unclear")
    confidence: str = Field(description="Confidence level: high, medium, low")
    evidence: List[str] = Field(description="Evidence text supporting the intent classification", default_factory=list)


class ExtractedFields(BaseModel):
    """All extracted classification fields."""
    provisional_diagnosis: ProvisionalDiagnosisExtraction
    joint_mapping: JointMapping
    clinical_stage: ClinicalStageExtraction
    activity_profile: ActivityProfileExtraction
    occupation: OccupationExtraction
    pain_interference: PainInterferenceExtraction
    pain_intensity_nprs: PainIntensityNPRS
    intent: IntentExtraction


class DataQualityFlags(BaseModel):
    """Data quality and availability flags."""
    nprs_available: bool = Field(description="Whether NPRS score is available", default=False)
    occupation_available: bool = Field(description="Whether occupation data is available", default=False)
    intent_clear: bool = Field(description="Whether intent is clearly stated", default=False)
    diagnosis_clear: bool = Field(description="Whether diagnosis is clear", default=False)


class ExtractedFields(BaseModel):
    """All extracted classification fields."""
    provisional_diagnosis: ProvisionalDiagnosisExtraction
    joint_mapping: JointMapping
    clinical_stage: ClinicalStageExtraction
    activity_profile: ActivityProfileExtraction
    occupation: OccupationExtraction
    pain_interference: PainInterferenceExtraction
    pain_intensity_nprs: PainIntensityNPRS
    intent: IntentExtraction


class DataQualityFlags(BaseModel):
    """Data quality and availability flags."""
    nprs_available: bool = Field(description="Whether NPRS score is available", default=False)
    occupation_available: bool = Field(description="Whether occupation data is available", default=False)
    intent_clear: bool = Field(description="Whether intent is clearly stated", default=False)
    diagnosis_clear: bool = Field(description="Whether diagnosis is clear", default=False)


class TriageClassification(BaseModel):
    """Triage classification output with nested structure and validation."""
    patient_id: str = Field(description="Patient ID")
    patient_name: Optional[str] = Field(description="Patient name", default=None)
    
    source_data: SourceData
    extracted_fields: ExtractedFields
    data_quality_flags: DataQualityFlags
    
    
    @field_validator('extracted_fields')
    @classmethod
    def validate_all_fields_present(cls, v):
        """Ensure all extracted fields are present (but allow 'unclear' as valid value)."""
        # Validate that all required fields are present (but allow "unclear" as a valid value)
        if not v.provisional_diagnosis or not v.provisional_diagnosis.canonical_label:
            raise ValueError("provisional_diagnosis.canonical_label must be provided")
        if not v.joint_mapping or not v.joint_mapping.primary_joint:
            raise ValueError("joint_mapping.primary_joint must be provided")
        if not v.clinical_stage or not v.clinical_stage.stage:
            raise ValueError("clinical_stage.stage must be provided")
        if not v.activity_profile or not v.activity_profile.primary_category:
            raise ValueError("activity_profile.primary_category must be provided")
        if not v.pain_interference or not v.pain_interference.category:
            raise ValueError("pain_interference.category must be provided")
        if not v.intent or not v.intent.primary_intent:
            raise ValueError("intent.primary_intent must be provided")
        return v


class TriageAgent:
    """Physiotherapy Triage Agent for patient classification."""
    
    def __init__(self):
        """Initialize the triage agent with Google GenAI Vertex AI."""
        # Initialize Google GenAI client with Vertex AI (mandatory)
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        self.location = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")
        
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT not set in environment")
        if not self.creds_path or not os.path.exists(self.creds_path):
            raise ValueError(f"GOOGLE_APPLICATION_CREDENTIALS not set or file not found: {self.creds_path}")
        
        try:
            # Use Vertex AI with service account authentication
            # Note: Vertex AI requires service account credentials, not API keys
            # GOOGLE_APPLICATION_CREDENTIALS must be set to service account JSON path
            self.client = genai.Client(
                vertexai=True,
                project=self.project_id,
                location=self.location
            )
            self.model = "gemini-2.5-flash"
            print(f"✅ Google GenAI Vertex AI client initialized")
            print(f"   Project: {self.project_id}")
            print(f"   Location: {self.location}")
            print(f"   Model: {self.model}")
        except Exception as e:
            print(f"❌ Failed to initialize Google GenAI Vertex AI: {e}")
            print(f"   Project: {self.project_id}")
            print(f"   Credentials: {self.creds_path}")
            raise
        
        # Load system prompt from JSON file
        prompt_file = backend_dir / "triage_prompt.json"
        try:
            with open(prompt_file, 'r') as f:
                prompt_config = json.load(f)
            self.system_prompt = prompt_config.get("system_message", self._get_default_prompt())
            print(f"✅ Loaded triage prompt from: {prompt_file}")
        except FileNotFoundError:
            print(f"⚠️  Prompt file not found: {prompt_file}, using default")
            self.system_prompt = self._get_default_prompt()
        except Exception as e:
            print(f"⚠️  Error loading prompt: {e}, using default")
            self.system_prompt = self._get_default_prompt()
    
    def _get_default_prompt(self) -> str:
        """Get default system prompt if JSON file is not available."""
        return """You are an Expert Physiotherapy Triage Agent. Your task is to classify incoming patients into a structured recovery matrix.

For each patient, analyze the 'Diagnosis' and 'Chief Complaints' and provide a classification based on three specific axes:

1. Criticality Level:

High: Acute injuries (<4 weeks), post-surgical cases (ACLR, repairs), or suspected fractures/stress reactions.

Medium: Significant functional limitations, chronic pain affecting gait, or mechanical blocks.

Low: Postural issues, general stiffness, or wellness/preventative cases.

2. Recovery Goal:

Return to Action (RTA): Goal is daily living, walking without pain, or desk-job ergonomics.

Return to Sports (RTS): Goal is high-impact activity (running, football, basketball). Look for keywords like 'cutting', 'agility', or specific sports names.

3. Timeline Class:

Acute: Symptoms < 6 weeks.

Sub-Acute: Symptoms 6 weeks to 3 months.

Chronic: Symptoms > 3 months.

Output Format: Return only a JSON object with the keys: criticality, goal, timeline_status, and reasoning_summary. The criticality must be one of: High, Medium, Low. The goal must be one of: RTA, RTS. The timeline_status must be one of: Acute, Sub-Acute, Chronic."""
    
    
    def _classify_risk_stratification(
        self, 
        complaints: str, 
        timeline_status: str
    ) -> RiskStratification:
        """
        Classify risk stratification based on psychosocial flags.
        
        Args:
            complaints: Chief complaints text
            timeline_status: Timeline status (Acute, Sub-Acute, Chronic)
        
        Returns:
            RiskStratification
        """
        complaints_lower = complaints.lower()
        
        # Look for psychosocial yellow flags
        psychosocial_keywords = {
            "fear": ["fear", "afraid", "scared", "worried", "anxious"],
            "confidence": ["confidence", "not confident", "unsure", "doubt"],
            "multiple_doctors": ["3 doctors", "multiple doctors", "seen many", "tried everything"],
            "catastrophizing": ["pop sound", "worries me", "terrible", "worst pain"]
        }
        
        flags_found = []
        for category, keywords in psychosocial_keywords.items():
            for keyword in keywords:
                if keyword in complaints_lower:
                    flags_found.append(f"{category}: '{keyword}'")
                    break
        
        # Classification logic: If complaints contains "fear" OR "confidence" AND timeline is Chronic → High Risk
        has_fear_or_confidence = any(
            kw in complaints_lower for kw in ["fear", "afraid", "confidence", "not confident"]
        )
        
        if has_fear_or_confidence and timeline_status == "Chronic":
            risk_level = "High Risk"
            reasoning = f"Psychosocial yellow flags detected ({', '.join(flags_found)}) combined with chronic timeline indicates High Risk for Non-Compliance."
        elif flags_found:
            risk_level = "High Risk"
            reasoning = f"Psychosocial yellow flags detected: {', '.join(flags_found)}"
        else:
            risk_level = "Low Risk"
            reasoning = "Clear mechanical complaint with no psychosocial flags. Usually responds well to standard exercise."
        
        return RiskStratification(
            risk_level=risk_level,
            psychosocial_flags=flags_found,
            risk_reasoning=reasoning
        )
    
    def _classify_joint_specific_group(self, diagnosis: str) -> JointSpecificGroup:
        """
        Classify joint-specific sub-group based on diagnosis.
        
        Args:
            diagnosis: Provisional diagnosis text
        
        Returns:
            JointSpecificGroup
        """
        diagnosis_lower = diagnosis.lower()
        
        # Posterior Chain Dominant conditions
        posterior_keywords = [
            "achilles", "hamstring", "lumbar", "lower back", 
            "posterior", "calf", "glute", "hamstring graft"
        ]
        
        # Anterior Chain Dominant conditions
        anterior_keywords = [
            "patellar", "patella", "quadriceps", "anterior",
            "patellar tendon", "knee extension"
        ]
        
        is_posterior = any(kw in diagnosis_lower for kw in posterior_keywords)
        is_anterior = any(kw in diagnosis_lower for kw in anterior_keywords)
        
        if is_posterior:
            group = "Posterior Chain Dominant"
            primary_joint = self._extract_primary_joint(diagnosis, posterior_keywords)
            # Ensure joint name is normalized
            primary_joint = normalize_joint_name(primary_joint)
            testing_focus = "ForceFrame isometric testing"
            reasoning = f"Diagnosis indicates posterior chain involvement ({primary_joint}). Requires heavy focus on ForceFrame isometric testing for hamstring, glute, and calf strength."
        elif is_anterior:
            group = "Anterior Chain Dominant"
            primary_joint = self._extract_primary_joint(diagnosis, anterior_keywords)
            # Ensure joint name is normalized
            primary_joint = normalize_joint_name(primary_joint)
            testing_focus = "ForceDeck (Jump/Landing) mechanics"
            reasoning = f"Diagnosis indicates anterior chain involvement ({primary_joint}). Requires focus on ForceDeck jump/landing mechanics for patellar tendon and quadriceps function."
        else:
            group = "Other"
            primary_joint = normalize_joint_name("Other")
            testing_focus = "Standard assessment"
            reasoning = "Diagnosis does not clearly indicate posterior or anterior chain dominance. Standard assessment protocol recommended."
        
        return JointSpecificGroup(
            group=group,
            primary_joint=primary_joint,
            testing_focus=testing_focus,
            group_reasoning=reasoning
        )
    
    def _extract_primary_joint(self, diagnosis: str, keywords: List[str]) -> str:
        """
        Extract primary joint from diagnosis based on keywords.
        Returns standardized joint name.
        """
        diagnosis_lower = diagnosis.lower()
        
        # Check for side indicators first
        is_left = "left" in diagnosis_lower or "l " in diagnosis_lower or diagnosis_lower.startswith("l-")
        is_right = "right" in diagnosis_lower or "r " in diagnosis_lower or diagnosis_lower.startswith("r-")
        
        # Extract joint type
        joint_type = None
        if "knee" in diagnosis_lower:
            if is_left:
                return "Left Knee"
            elif is_right:
                return "Right Knee"
            else:
                return "Bilateral Knee"
        elif "ankle" in diagnosis_lower or "achilles" in diagnosis_lower:
            if is_left:
                return "Left Ankle"
            elif is_right:
                return "Right Ankle"
            else:
                return "Achilles Tendon" if "achilles" in diagnosis_lower else "Bilateral Ankle"
        elif "hip" in diagnosis_lower:
            if is_left:
                return "Left Hip"
            elif is_right:
                return "Right Hip"
            else:
                return "Bilateral Hip"
        elif "shoulder" in diagnosis_lower:
            if is_left:
                return "Left Shoulder"
            elif is_right:
                return "Right Shoulder"
            else:
                return "Bilateral Shoulder"
        elif "lumbar" in diagnosis_lower or "lower back" in diagnosis_lower:
            return "Lumbar Spine"
        elif "cervical" in diagnosis_lower or "neck" in diagnosis_lower:
            return "Cervical Spine"
        elif "thoracic" in diagnosis_lower or "upper back" in diagnosis_lower:
            return "Thoracic Spine"
        elif "hamstring" in diagnosis_lower:
            return "Hamstring"
        elif "patellar" in diagnosis_lower or "patella" in diagnosis_lower:
            return "Patellar Tendon"
        
        # Fallback: check keywords
        for keyword in keywords:
            if keyword in diagnosis_lower:
                if keyword in ["achilles"]:
                    return "Achilles Tendon"
                elif keyword in ["hamstring", "hamstring graft"]:
                    return "Hamstring"
                elif keyword in ["lumbar", "lower back"]:
                    return "Lumbar Spine"
                elif keyword in ["patellar", "patella", "patellar tendon"]:
                    return "Patellar Tendon"
        
        return "Other"
    
    def classify_patient(
        self, 
        patient_id: str,
        diagnosis: str,
        complaints: str,
        assessment_date: Optional[str] = None,
        patient_name: Optional[str] = None,
        full_patient_record: Optional[Dict[str, Any]] = None
    ) -> TriageClassification:
        """
        Classify a single patient.
        
        Args:
            patient_id: Patient ID
            diagnosis: Provisional diagnosis
            complaints: Chief complaints
            assessment_date: First assessment date (optional, for timeline calculation)
            patient_name: Patient name (optional, defaults to "Unknown")
            full_patient_record: Full patient record from first assessment (optional, contains all available data)
        
        Returns:
            TriageClassification object
        """
        # Get patient name (use provided name or default to "Unknown")
        if not patient_name:
            patient_name = "Unknown"
        
        print(f"🔍 Classifying patient: {patient_id}")
        
        # Extract all available fields from full patient record
        clinical_history = ""
        subjective_notes = ""
        goals_raw = ""
        additional_context = ""
        
        if full_patient_record:
            import json
            # Try to extract from nested structure
            record = full_patient_record.get('first_assessment_data', full_patient_record)
            if isinstance(record, str):
                try:
                    record = json.loads(record)
                except:
                    record = {}
            
            # Extract clinical history
            clinical_history = record.get('clinical_history', '') or record.get('clinicalHistory', '')
            if not clinical_history:
                raw_data = record.get('raw_data', {})
                if raw_data:
                    records = raw_data.get('records', {})
                    clinical_history = records.get('clinicalDetails', {}).get('clinicalHistory', '')
            
            # Extract subjective notes
            subjective_notes = record.get('subjective_notes', '') or record.get('subjectiveNotes', '')
            if not subjective_notes:
                raw_data = record.get('raw_data', {})
                if raw_data:
                    records = raw_data.get('records', {})
                    subjective_notes = records.get('subjectiveAssessment', {}).get('notes', '')
            
            # Extract goals
            goals_raw = record.get('goals', '') or record.get('goals_raw', '')
            if not goals_raw:
                raw_data = record.get('raw_data', {})
                if raw_data:
                    records = raw_data.get('records', {})
                    goals_raw = records.get('goals', {}).get('goals', '') or records.get('goals', {}).get('expectations', '')
            
            # Build additional context from all available fields
            context_parts = []
            if clinical_history:
                context_parts.append(f"Clinical History: {clinical_history}")
            if subjective_notes:
                context_parts.append(f"Subjective Assessment: {subjective_notes}")
            if goals_raw:
                context_parts.append(f"Goals/Expectations: {goals_raw}")
            
            # Include any other relevant fields from the record
            for key in ['recommendations', 'treatment_plan', 'notes', 'assessment_notes']:
                if record.get(key):
                    context_parts.append(f"{key.replace('_', ' ').title()}: {record.get(key)}")
            
            if context_parts:
                additional_context = "\n\n" + "\n".join(context_parts)
        
        
        prompt = f"""You are analyzing a complete patient record. Read through ALL the information provided below with INTENT-BASED understanding, not keyword matching. Consider the full context, patient's situation, and implied meanings to extract comprehensive classifications.

**COMPLETE PATIENT RECORD:**

Patient ID: {patient_id}
Patient Name: {patient_name or 'Not provided'}
Assessment Date: {assessment_date or 'Not provided'}

**Primary Information:**
Diagnosis: {diagnosis}
Chief Complaints: {complaints}
{additional_context}

**CRITICAL INSTRUCTIONS - AGGRESSIVE INTENT-BASED ANALYSIS:**
1. Read through the ENTIRE patient record above - analyze ALL text fields comprehensively
2. **MANDATORY INFERENCE RULES - DO NOT USE "UNCLEAR" UNLESS ABSOLUTELY NECESSARY:**

   **Activity Profile (MUST INFER):**
   - ANY mention of sports/activities (badminton, tennis, running, gym, exercise, workout, training, competition) → infer activity level
   - "playing [sport]", "doing [activity]", "training", "exercise" → recreationally_active or structured_fitness
   - "gym", "deadlift", "weightlifting", "strength training" → structured_fitness
   - "running", "jogging", "marathon" → recreationally_active, running_dominant
   - "competitive", "tournament", "match" → competitive
   - NO activity mentions but has pain affecting movement → likely sedentary or recreationally_active
   - DEFAULT: If no clear indication, use "recreationally_active" with "mixed_fitness" subcategory (most common for physio patients)

   **Occupation (MUST INFER):**
   - "desk", "office", "computer", "sitting" → sedentary_desk
   - "work", "job", "profession" mentioned → infer from context (desk vs manual)
   - "student", "studying" → student
   - "athlete", "sport" as profession → athlete
   - "retired", "elderly" → retired
   - "construction", "manual", "physical work" → manual_physical
   - DEFAULT: If patient is active (mentions sports/gym) but no work context → likely student or sedentary_desk
   - DEFAULT: If no clear indication, use "sedentary_desk" (most common)

   **Clinical Stage (MUST INFER):**
   - Time indicators: "since [time]" → acute (<1 month), subacute (1-3 months), chronic (>3 months)
   - "since 1 week", "since few days" → acute
   - "since 1 month", "since 2 months" → subacute
   - "since 6 months", "since 1 year", "since years" → chronic
   - "surgery", "post-op", "ACLR", "reconstruction" → post_operative
   - "pre-surgical", "before surgery" → pre_hab
   - DEFAULT: If no time mentioned but has diagnosis → infer from condition type (surgical = post_operative, injury = acute/subacute)

   **Pain Interference (MUST INFER):**
   - "pain during [activity]", "pain while [activity]" → activity_interference
   - "pain at work", "pain affecting work", "desk job" → work_interference
   - "pain affecting daily activities", "pain with ADL" → work_interference or multi_domain
   - "no pain", "minimal pain", "pain-free" → no_interference
   - Surgery mentioned → forced_entry
   - DEFAULT: If pain is mentioned but no specific domain → activity_interference (most common)

   **Intent (MUST INFER):**
   - "return to sport", "return to [sport name]", "play again" → return_sport
   - "return to activity", "return to fitness", "return to exercise" → return_activity
   - "return to work", "return to daily function" → return_daily_function
   - "pain relief", "reduce pain", "manage pain" → pain_relief_only
   - "post-surgical", "recovery", "rehabilitation" → post_surgical_recovery
   - "performance", "optimize", "improve" → performance
   - DEFAULT: If patient mentions activities/sports → return_sport or return_activity
   - DEFAULT: If only pain mentioned → pain_relief_only

3. **Scan ALL text fields for NPRS scores** (numbers 0-10 explicitly linked to pain)

5. **CRITICAL: "unclear" is a LAST RESORT** - make reasonable inferences based on:
   - Patient's age (if mentioned)
   - Condition type (surgical vs injury)
   - Activity mentions (even indirect)
   - Pain descriptions
   - Goals/expectations
   - Overall context of the record

**CRITICAL: You MUST provide ALL fields in the EXACT nested structure below. All fields are REQUIRED.**

Provide classification in this EXACT JSON structure:

{{
  "patient_id": "{patient_id}",
  
  "source_data": {{
    "provisional_diagnosis_raw": "Raw diagnosis text from notes (extract from diagnosis field)",
    "chief_complaint": "Chief complaint text (extract from complaints field)",
    "clinical_history": "Clinical history text (extract from available history)",
    "subjective_notes": "Subjective assessment notes (extract from available notes)",
    "goals_raw": "Raw goals/expectations text (extract from available goals)"
  }},

  "extracted_fields": {{
    "provisional_diagnosis": {{
      "canonical_label": "Canonical diagnosis bucket. You MUST choose ONE of these EXACT labels only: 'Knee pain', 'Hip pain', 'Ankle/Foot pain', 'Shoulder pain', 'Elbow/Wrist/Hand pain', 'Cervical spine pain', 'Thoracic spine pain', 'Lumbar spine pain', 'Multi-site / multi-joint pain', 'Post-operative rehabilitation', 'Other', 'Unclear'. Map all specific diagnoses (e.g. ACL tear, meniscal tear, PFJ pain) into the appropriate bucket.",
      "confidence": "high|medium|low",
      "raw_matches": ["list", "of", "raw", "text", "matches"],
      "diagnosis_type": "single|multiple|unclear"
    }},
    
    "joint_mapping": {{
      "primary_joint": "Standardized joint name: Left Knee|Right Knee|Bilateral Knee|Left Ankle|Right Ankle|Bilateral Ankle|Left Hip|Right Hip|Bilateral Hip|Left Shoulder|Right Shoulder|Bilateral Shoulder|Cervical Spine|Thoracic Spine|Lumbar Spine|Achilles Tendon|Hamstring|Patellar Tendon|Other|Multiple",
      "functional_region": "upper_limb|lower_limb|spine|posterior_chain|multi_joint",
      "is_multi_joint": true/false
    }},
    
    "clinical_stage": {{
      "stage": "acute|subacute|chronic|recurrent|pre_hab|post_operative|unclear",
      "evidence": ["list", "of", "evidence", "text", "supporting", "stage"]
    }},
    
    "activity_profile": {{
      "primary_category": "sedentary|recreationally_active|structured_fitness|competitive|unclear",
      "sub_category": "running_dominant|gym_strength|sport_specific|mixed_fitness|unclear (only if primary_category is 'recreationally_active', otherwise null)",
      "evidence": ["list", "of", "evidence", "text"]
    }},
    
    "occupation": {{
      "category": "sedentary_desk|manual_physical|student|athlete|retired|unclear",
      "evidence": ["list", "of", "evidence", "text"]
    }},
    
    "pain_interference": {{
      "category": "no_interference|activity_interference|work_interference|multi_domain|forced_entry|unclear",
      "domains_affected": ["list", "of", "domains", "affected"],
      "confidence": "high|medium|low"
    }},
    
    "pain_intensity_nprs": {{
      "value": 0-10 or null (only if numeric pain score found in text),
      "scale": "NPRS",
      "found": true/false (true only if numeric score 0-10 explicitly linked to pain),
      "extraction_method": "explicit_numeric|inferred|null",
      "evidence_text": "The exact text where NPRS was found (or null)"
    }},
    
    "intent": {{
      "primary_intent": "pain_relief|return_daily_function|return_activity|return_sport|performance|post_surgical|unclear",
      "confidence": "high|medium|low",
      "evidence": ["list", "of", "evidence", "text"]
    }}
  }},

  "data_quality_flags": {{
    "nprs_available": true/false (true only if pain_intensity_nprs.found is true),
    "occupation_available": true/false (true if occupation.category is not 'unclear'),
    "intent_clear": true/false (true if intent.primary_intent is not 'unclear'),
    "diagnosis_clear": true/false (true if provisional_diagnosis.canonical_label is not 'unclear')
  }}
}}

**REQUIREMENTS:**
1. ALL fields above MUST be present - do not omit any field
2. Use snake_case for all field names (e.g., "primary_joint", not "primaryJoint")
3. For primary_joint, use EXACT standardized names from the list above
4. NPRS EXTRACTION: Scan ALL free-text fields above. Only extract if number 0-10 is explicitly linked to pain (e.g., "pain 6/10", "NPRS 7", "pain score 8"). If no numeric score found → found = false, value = null, extraction_method = null
5. Evidence arrays should contain actual text snippets from the source data that support each classification
6. **AGGRESSIVE INFERENCE REQUIRED**: You MUST make inferences for ALL fields. Use the inference rules above. "unclear" should be used in <5% of cases.
7. **DEFAULT VALUES WHEN UNCERTAIN** (use these instead of "unclear" when data is ambiguous):
   - activity_profile: "recreationally_active" with sub_category: "mixed_fitness" (most physio patients are active)
   - occupation: "sedentary_desk" (most common)
   - clinical_stage: Infer from time indicators, or "subacute" if uncertain (middle ground)
   - pain_interference: "activity_interference" (most common for physio patients)
   - intent: Infer from goals, or "return_activity" if patient mentions activities

**EXAMPLES OF AGGRESSIVE INFERENCE:**
- "playing badminton" → activity_profile: recreationally_active, sub_category: sport_specific, intent: return_sport
- "doing deadlift" or "gym" → activity_profile: structured_fitness, intent: return_activity
- "pain while working" or "desk job" → occupation: sedentary_desk, pain_interference: work_interference
- "wants to return to running" → intent: return_sport, activity_profile: recreationally_active, sub_category: running_dominant
- "pain affects daily activities" → pain_interference: work_interference or multi_domain
- "pain only during exercise" → pain_interference: activity_interference
- "shoulder pain" with no activity mention → activity_profile: recreationally_active (default), occupation: sedentary_desk (default)
- "knee pain since 2 months" → clinical_stage: subacute (inferred from time)
- "ACLR" or "reconstruction" → clinical_stage: post_operative, intent: post_surgical_recovery"""
        
        config = types.GenerateContentConfig(
            temperature=1,
            top_p=1,
            max_output_tokens=65535,
            safety_settings=[
                types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
            ],
            tools=[
                types.Tool(google_search=types.GoogleSearch())
            ],
            thinking_config=types.ThinkingConfig(thinking_budget=-1),
        )
        
        contents = [
            types.Content(
                role="user",
                parts=[types.Part.from_text(text=f"{self.system_prompt}\n\n{prompt}")]
            )
        ]
        
        # Generate response
        response_text = ""
        
        try:
            for chunk in self.client.models.generate_content_stream(
                model=self.model,
                contents=contents,
                config=config
            ):
                if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                    continue
                for part in chunk.candidates[0].content.parts:
                    if hasattr(part, 'text') and part.text:
                        response_text += part.text
        except Exception as api_error:
            # Check if it's a 404 model not found error and we have a fallback
            error_msg = str(api_error)
            fallback_success = False
            
            if ("404" in error_msg or "NOT_FOUND" in error_msg) and hasattr(self, 'fallback_model') and model_to_use == self.model:
                print(f"⚠️  {self.model} not accessible, trying fallback: {self.fallback_model}")
                model_to_use = self.fallback_model
                try:
                    for chunk in self.client.models.generate_content_stream(
                        model=model_to_use,
                        contents=contents,
                        config=config
                    ):
                        if chunk.candidates and chunk.candidates[0].content and chunk.candidates[0].content.parts:
                            for part in chunk.candidates[0].content.parts:
                                if hasattr(part, 'text') and part.text:
                                    response_text += part.text
                    print(f"✅ Using fallback model: {self.fallback_model}")
                    fallback_success = True
                    # Success! Continue to parse response below
                except Exception as fallback_error:
                    # Fallback also failed, treat as original error
                    api_error = fallback_error
                    error_msg = str(fallback_error)
                    fallback_success = False
            
            # If fallback succeeded, skip error handling and continue to parse response
            if fallback_success and response_text:
                # Fallback worked! Continue to parse response below
                pass
            else:
                # Fallback didn't succeed, handle the error
                error_dict = None
                
                # Try to extract error details from exception
                try:
                    if hasattr(api_error, '__dict__'):
                        error_dict = api_error.__dict__
                    elif hasattr(api_error, 'error'):
                        error_dict = api_error.error if isinstance(api_error.error, dict) else {'error': str(api_error.error)}
                except:
                    pass
                
                # Check for permission errors
                is_permission_error = False
                if error_dict and isinstance(error_dict, dict):
                    error_info = error_dict.get('error', {})
                    if isinstance(error_info, dict):
                        code = error_info.get('code')
                        message = error_info.get('message', '')
                        if code == 403 or 'PERMISSION_DENIED' in str(message):
                            is_permission_error = True
                
                if not is_permission_error:
                    is_permission_error = "PERMISSION_DENIED" in error_msg or "403" in error_msg or "permission" in error_msg.lower()
                
                if is_permission_error:
                    print(f"\n❌ PERMISSION DENIED - Vertex AI Access Failed")
                    print(f"   The service account does not have permission to use Vertex AI.")
                    print(f"   Required permission: 'aiplatform.endpoints.predict'")
                    print(f"\n   To fix this, grant the 'Vertex AI User' role to your service account:")
                    print(f"   1. Get service account email from: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'credentials file')}")
                    print(f"   2. Run: gcloud projects add-iam-policy-binding stance-ai \\")
                    print(f"        --member=\"serviceAccount:YOUR_SERVICE_ACCOUNT_EMAIL\" \\")
                    print(f"        --role=\"roles/aiplatform.user\"")
                    print(f"\n   Or use Google Cloud Console:")
                    print(f"   IAM & Admin > IAM > Find service account > Edit > Add 'Vertex AI User' role")
                    print(f"\n   Error details: {error_msg[:300]}")
                    raise PermissionError("Vertex AI permission denied. Service account needs 'roles/aiplatform.user' role.")
                else:
                    # Re-raise other errors (including 404 if fallback failed)
                    raise
        
        # Parse JSON from response
        try:
            # Extract JSON from response
            json_start = response_text.find('{')
            json_end = response_text.rfind('}') + 1
            if json_start >= 0 and json_end > json_start:
                json_str = response_text[json_start:json_end]
                classification_dict = json.loads(json_str)
            else:
                classification_dict = json.loads(response_text)
            
            # Ensure patient_id and patient_name are set
            classification_dict['patient_id'] = patient_id
            if 'patient_name' not in classification_dict:
                classification_dict['patient_name'] = patient_name
            
            # Ensure source_data exists and populate from input data
            if 'source_data' not in classification_dict:
                classification_dict['source_data'] = {}
            source_data = classification_dict['source_data']
            if not source_data.get('provisional_diagnosis_raw'):
                source_data['provisional_diagnosis_raw'] = diagnosis
            if not source_data.get('chief_complaint'):
                source_data['chief_complaint'] = complaints
            if not source_data.get('clinical_history'):
                source_data['clinical_history'] = complaints  # Use complaints as history if not provided
            if not source_data.get('subjective_notes'):
                source_data['subjective_notes'] = None
            if not source_data.get('goals_raw'):
                source_data['goals_raw'] = None
            
            # Ensure extracted_fields exists
            if 'extracted_fields' not in classification_dict:
                raise ValueError("Missing 'extracted_fields' in LLM response")
            extracted = classification_dict['extracted_fields']
            
            # Normalize primary_joint if present
            if 'joint_mapping' in extracted and extracted['joint_mapping'].get('primary_joint'):
                original_joint = extracted['joint_mapping']['primary_joint']
                normalized_joint = normalize_joint_name(original_joint)
                extracted['joint_mapping']['primary_joint'] = normalized_joint
                if original_joint != normalized_joint:
                    print(f"   🔄 Normalized joint name: '{original_joint}' → '{normalized_joint}'")
            
            # Validate NPRS extraction
            if 'pain_intensity_nprs' in extracted:
                nprs = extracted['pain_intensity_nprs']
                if nprs.get('found') and nprs.get('value') is not None:
                    try:
                        score = int(nprs['value'])
                        if not (0 <= score <= 10):
                            nprs['found'] = False
                            nprs['value'] = None
                            nprs['extraction_method'] = None
                            print(f"   ⚠️  Invalid NPRS score {score}, resetting")
                        else:
                            print(f"   📊 LLM extracted NPRS score: {score}/10")
                    except (ValueError, TypeError):
                        nprs['found'] = False
                        nprs['value'] = None
                        nprs['extraction_method'] = None
                else:
                    nprs['found'] = False
                    nprs['value'] = None
                    if not nprs.get('extraction_method'):
                        nprs['extraction_method'] = None
                    print(f"   📊 NPRS not available (no numeric score found)")
            
            # Ensure data_quality_flags exists and is populated
            if 'data_quality_flags' not in classification_dict:
                classification_dict['data_quality_flags'] = {}
            flags = classification_dict['data_quality_flags']
            
            # Populate quality flags based on extracted fields
            nprs_data = extracted.get('pain_intensity_nprs', {})
            flags['nprs_available'] = nprs_data.get('found', False)
            
            occupation_data = extracted.get('occupation', {})
            flags['occupation_available'] = occupation_data.get('category', 'unclear').lower() != 'unclear'
            
            intent_data = extracted.get('intent', {})
            flags['intent_clear'] = intent_data.get('primary_intent', 'unclear').lower() != 'unclear'
            
            diagnosis_data = extracted.get('provisional_diagnosis', {})
            flags['diagnosis_clear'] = diagnosis_data.get('canonical_label', 'unclear').lower() != 'unclear'
            
            
            # Validate with Pydantic - this will ensure all required fields are present
            try:
                classification = TriageClassification(**classification_dict)
                print(f"✅ Classification complete and validated")
                return classification
            except Exception as validation_error:
                print(f"⚠️  Validation error: {validation_error}")
                print(f"   Attempting to fix missing fields...")
                # Try to create a minimal valid structure
                raise validation_error
            
        except json.JSONDecodeError as e:
            print(f"⚠️  Could not parse JSON from response: {e}")
            print(f"Response: {response_text[:500]}")
            raise ValueError(f"Invalid JSON response from LLM: {e}")
        except Exception as e:
            error_msg = str(e)
            error_dict = None
            
            # Try to extract error details if it's a dict-like error
            try:
                if hasattr(e, '__dict__'):
                    error_dict = e.__dict__
                elif isinstance(e, dict):
                    error_dict = e
                elif hasattr(e, 'error'):
                    error_dict = e.error if isinstance(e.error, dict) else {'error': str(e.error)}
            except:
                pass
            
            # Check for permission errors in multiple ways
            is_permission_error = False
            if error_dict:
                # Check nested error structure
                if isinstance(error_dict, dict):
                    error_info = error_dict.get('error', {})
                    if isinstance(error_info, dict):
                        code = error_info.get('code')
                        message = error_info.get('message', '')
                        if code == 403 or 'PERMISSION_DENIED' in str(message):
                            is_permission_error = True
                    # Also check top level
                    if error_dict.get('code') == 403 or 'PERMISSION_DENIED' in str(error_dict):
                        is_permission_error = True
            
            # Check error message string
            if not is_permission_error:
                is_permission_error = "PERMISSION_DENIED" in error_msg or "403" in error_msg
            
            if is_permission_error:
                print(f"\n❌ PERMISSION DENIED - Vertex AI Access Failed")
                print(f"   The service account does not have permission to use Vertex AI.")
                print(f"   Required permission: 'aiplatform.endpoints.predict'")
                print(f"\n   To fix this, grant the 'Vertex AI User' role to your service account:")
                print(f"   1. Get service account email from: {os.getenv('GOOGLE_APPLICATION_CREDENTIALS', 'credentials file')}")
                print(f"   2. Run: gcloud projects add-iam-policy-binding stance-ai \\")
                print(f"        --member=\"serviceAccount:YOUR_SERVICE_ACCOUNT_EMAIL\" \\")
                print(f"        --role=\"roles/aiplatform.user\"")
                print(f"\n   Or use Google Cloud Console:")
                print(f"   IAM & Admin > IAM > Find service account > Edit > Add 'Vertex AI User' role")
                print(f"\n   Error details: {error_msg[:300]}")
                raise PermissionError("Vertex AI permission denied. Service account needs 'roles/aiplatform.user' role.")
            else:
                print(f"❌ Error classifying patient {patient_id}: {error_msg}")
                raise
    
    def classify_filtered_patients(
        self, 
        filtered_patients: List[Dict[str, Any]],
        update_progress: bool = False,
        max_workers: int = 10,
        output_file: Optional[Path] = None
    ) -> List[TriageClassification]:
        """
        Classify multiple filtered patients concurrently.
        
        Args:
            filtered_patients: List of filtered patient records from PatientFilter
            update_progress: Whether to update progress file (for API calls)
            max_workers: Maximum number of concurrent patient classifications (default: 10)
            output_file: Optional path to JSON file for incremental saving (saves every 100 patients)
        
        Returns:
            List of TriageClassification objects
        """
        classifications = []
        total_patients = len(filtered_patients)
        
        print(f"📊 Classifying {total_patients} patients concurrently (max {max_workers} at a time)...")
        
        # Update progress if requested
        if update_progress:
            try:
                from api.progress_tracker import set_progress, increment_progress
                set_progress("running", 0, total_patients, message=f"Classifying patients (0/{total_patients})...")
            except Exception as e:
                print(f"⚠️  Could not initialize progress tracking: {e}")
                increment_progress = None
        else:
            increment_progress = None
        
        # Thread-safe counter for completed patients
        completed_lock = threading.Lock()
        completed_count = [0]  # Use list to allow modification in nested function
        
        # Thread-safe file writing lock for incremental saves
        file_write_lock = threading.Lock()
        
        def save_classifications_incremental(classifications_list: List[TriageClassification], force: bool = False):
            """Thread-safe function to save classifications incrementally."""
            if not output_file:
                return
            
            with file_write_lock:
                try:
                    # Convert to JSON-serializable format
                    json_data = [cls.model_dump(exclude_none=False, mode='json') for cls in classifications_list]
                    
                    # Ensure directory exists
                    output_file.parent.mkdir(parents=True, exist_ok=True)
                    
                    # Write to file
                    with open(output_file, 'w') as f:
                        json.dump(json_data, f, indent=2, default=str)
                    
                    # Always print when saving (for real-time updates)
                    if force:
                        print(f"💾 Saved {len(classifications_list)} classifications to {output_file.name}")
                except Exception as e:
                    print(f"⚠️  Error saving classifications incrementally: {e}")
        
        def classify_single_patient(patient: Dict[str, Any], index: int) -> Optional[TriageClassification]:
            """Classify a single patient and update progress."""
            patient_name = patient.get('patient_name', patient.get('patient_id', 'Unknown'))
            patient_id = patient.get('patient_id')
            
            print(f"\n[{index + 1}/{total_patients}] Processing: {patient_name}")
            
            try:
                classification = self.classify_patient(
                    patient_id=patient_id,
                    diagnosis=patient.get('diagnosis', ''),
                    complaints=patient.get('complaints', ''),
                    assessment_date=patient.get('date'),
                    patient_name=patient_name,
                    full_patient_record=patient  # Pass the full patient record
                )
                
                # Update progress thread-safely
                if update_progress and increment_progress:
                    try:
                        increment_progress(total_patients)
                    except Exception:
                        pass
                elif update_progress:
                    try:
                        from api.progress_tracker import set_progress
                        with completed_lock:
                            completed_count[0] += 1
                            set_progress("running", completed_count[0], total_patients, message=f"Classifying patients ({completed_count[0]}/{total_patients})...")
                    except Exception:
                        pass
                
                print(f"✅ [{index + 1}/{total_patients}] Completed: {patient_name}")
                return classification
                
            except PermissionError as e:
                # Permission errors should stop the pipeline
                print(f"\n❌ Stopping pipeline due to permission error for {patient_name}: {e}")
                if update_progress:
                    try:
                        from api.progress_tracker import set_progress
                        with completed_lock:
                            set_progress("error", completed_count[0], total_patients, error=str(e))
                    except Exception:
                        pass
                raise
            except Exception as e:
                print(f"❌ Error classifying patient {patient_name} ({patient_id}): {e}")
                # Update progress even on error
                if update_progress and increment_progress:
                    try:
                        increment_progress(total_patients)
                    except Exception:
                        pass
                elif update_progress:
                    try:
                        from api.progress_tracker import set_progress
                        with completed_lock:
                            completed_count[0] += 1
                            set_progress("running", completed_count[0], total_patients, message=f"Classifying patients ({completed_count[0]}/{total_patients})...")
                    except Exception:
                        pass
                return None
        
        # Process patients concurrently
        try:
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all tasks
                future_to_patient = {
                    executor.submit(classify_single_patient, patient, i): (patient, i)
                    for i, patient in enumerate(filtered_patients)
                }
                
                # Collect results as they complete
                for future in as_completed(future_to_patient):
                    patient, index = future_to_patient[future]
                    try:
                        result = future.result()
                        if result is not None:
                            classifications.append(result)
                            
                            # Save incrementally after EVERY patient for real-time updates
                            if output_file:
                                save_classifications_incremental(classifications, force=True)
                    except PermissionError:
                        # Re-raise permission errors to stop the pipeline
                        raise
                    except Exception as e:
                        print(f"❌ Unexpected error processing patient {patient.get('patient_id')}: {e}")
                        # Continue with other patients
                        continue
        except PermissionError:
            # Permission error was raised, stop processing
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("error", completed_count[0], total_patients, error="Permission denied")
                except Exception:
                    pass
            raise
        
        # Final save if output file is specified
        if output_file and classifications:
            save_classifications_incremental(classifications, force=True)
            print(f"\n💾 Final save: {len(classifications)} classifications saved to {output_file.name}")
        
        # Mark as completed
        if update_progress:
            try:
                from api.progress_tracker import set_progress
                set_progress("completed", len(classifications), total_patients)
            except Exception:
                pass
        
        print(f"\n✅ Completed classification of {len(classifications)}/{total_patients} patients")
        return classifications
    
    def run_triage_pipeline(
        self, 
        months_back: Optional[int] = None,
        patient_ids: Optional[List[str]] = None,
        limit: Optional[int] = None,
        update_progress: bool = False,
        output_file: Optional[Path] = None
    ) -> List[TriageClassification]:
        """
        Run the complete triage pipeline: filter + classify.
        
        Args:
            months_back: Number of months to look back for filtering (None means no date limit - all patients)
            patient_ids: Optional list of specific patient IDs to process
            limit: Maximum number of patients to process if patient_ids not provided (None or 0 means all patients)
            update_progress: Whether to update progress file (for API calls)
            output_file: Optional path to JSON file for incremental saving (saves every 100 patients)
        
        Returns:
            List of TriageClassification objects
        """
        print("=" * 80)
        print("Physiotherapy Triage Pipeline")
        print("=" * 80)
        print()
        
        # Step 1: Filter patients
        print("Step 1: Filtering patients...")
        filter_agent = PatientFilter(months_back=months_back)
        
        if patient_ids:
            filtered = filter_agent.get_filtered_patients(patient_ids)
        else:
            filtered = filter_agent.filter_all_patients(limit=limit, update_progress=update_progress)
        
        if not filtered:
            print("⚠️  No eligible patients found")
            if update_progress:
                try:
                    from api.progress_tracker import set_progress
                    set_progress("completed", 0, 0)
                except Exception:
                    pass
            return []
        
        print(f"\n✅ Found {len(filtered)} eligible patients")
        if output_file:
            print(f"💾 Incremental saves will be written to: {output_file.name}")
        print()
        
        # Step 2: Classify patients
        print("Step 2: Classifying patients...")
        classifications = self.classify_filtered_patients(
            filtered, 
            update_progress=update_progress,
            output_file=output_file
        )
        
        return classifications


# ============================================================================
# Main Execution
# ============================================================================

if __name__ == "__main__":
    import sys
    
    print("=" * 80)
    print("Physiotherapy Triage Agent")
    print("=" * 80)
    print()
    
    try:
        agent = TriageAgent()
        
        # Check if first argument is a flag for specific patients
        if len(sys.argv) > 1 and sys.argv[1] == "--patients":
            # Classify specific patient IDs
            patient_ids = sys.argv[2:]
            print(f"🔍 Classifying specific patients: {patient_ids}")
            classifications = agent.run_triage_pipeline(patient_ids=patient_ids)
        else:
            # Run full pipeline on all eligible patients
            months_back = int(sys.argv[1]) if len(sys.argv) > 1 and sys.argv[1].isdigit() else 5
            if len(sys.argv) > 2:
                if sys.argv[2].lower() in ['all', 'none', '0']:
                    limit = None  # Process all patients
                elif sys.argv[2].isdigit():
                    limit = int(sys.argv[2])
                else:
                    limit = None
            else:
                limit = None  # Default to all patients
            if limit is None:
                print(f"📊 Running triage pipeline: months_back={months_back}, limit=ALL PATIENTS")
            else:
                print(f"📊 Running triage pipeline: months_back={months_back}, limit={limit}")
            classifications = agent.run_triage_pipeline(months_back=months_back, limit=limit)
        
        # Display results
        print("\n" + "=" * 80)
        print("Triage Classification Results")
        print("=" * 80)
        print()
        
        # Group by new master prompt fields
        by_diagnosis = {}
        by_functional_region = {}
        by_clinical_stage = {}
        by_pain_interference = {}
        by_intent = {}
        
        for cls in classifications:
            # Extract from nested structure
            extracted = cls.extracted_fields
            
            # Diagnosis
            diag = extracted.provisional_diagnosis.canonical_label or "Unclear"
            by_diagnosis[diag] = by_diagnosis.get(diag, 0) + 1
            
            # Functional Region
            region = extracted.joint_mapping.functional_region or "Unclear"
            by_functional_region[region] = by_functional_region.get(region, 0) + 1
            
            # Clinical Stage
            stage = extracted.clinical_stage.stage or "Unclear"
            by_clinical_stage[stage] = by_clinical_stage.get(stage, 0) + 1
            
            # Pain Interference
            interference = extracted.pain_interference.category or "Unclear"
            by_pain_interference[interference] = by_pain_interference.get(interference, 0) + 1
            
            # Intent
            intent = extracted.intent.primary_intent or "Unclear"
            by_intent[intent] = by_intent.get(intent, 0) + 1
        
        print(f"Total Classifications: {len(classifications)}\n")
        
        print("By Diagnosis:")
        for diag, count in sorted(by_diagnosis.items(), key=lambda x: x[1], reverse=True):
            print(f"  {diag}: {count}")
        
        print("\nBy Functional Region:")
        for region, count in sorted(by_functional_region.items(), key=lambda x: x[1], reverse=True):
            print(f"  {region}: {count}")
        
        print("\nBy Clinical Stage:")
        for stage, count in sorted(by_clinical_stage.items(), key=lambda x: x[1], reverse=True):
            print(f"  {stage}: {count}")
        
        print("\nBy Pain Interference:")
        for interference, count in sorted(by_pain_interference.items(), key=lambda x: x[1], reverse=True):
            print(f"  {interference}: {count}")
        
        print("\nBy Intent Category:")
        for intent, count in sorted(by_intent.items(), key=lambda x: x[1], reverse=True):
            print(f"  {intent}: {count}")
        
        # NPRS availability
        nprs_available = sum(1 for cls in classifications if cls.data_quality_flags.nprs_available)
        print(f"\nNPRS Available: {nprs_available}/{len(classifications)} ({nprs_available/len(classifications)*100:.1f}%)")
        
        print("\n" + "=" * 80)
        print("Sample Classifications:")
        print("=" * 80)
        
        for cls in classifications[:5]:  # Show first 5
            extracted = cls.extracted_fields
            print(f"\n{cls.patient_name} ({cls.patient_id})")
            print(f"  Diagnosis: {extracted.provisional_diagnosis.canonical_label or 'Unclear'}")
            print(f"  Primary Joint: {extracted.joint_mapping.primary_joint or 'Unclear'}")
            print(f"  Functional Region: {extracted.joint_mapping.functional_region or 'Unclear'}")
            print(f"  Clinical Stage: {extracted.clinical_stage.stage or 'Unclear'}")
            print(f"  Pain Interference: {extracted.pain_interference.category or 'Unclear'}")
            if cls.data_quality_flags.nprs_available and extracted.pain_intensity_nprs.value is not None:
                print(f"  NPRS: {extracted.pain_intensity_nprs.value}/10")
            print(f"  Intent: {extracted.intent.primary_intent or 'Unclear'}")
        
        # Save to JSON only if we have classifications
        if classifications:
            # Save to LLM directory (same directory as this script)
            output_dir = Path(__file__).parent
            output_file = output_dir / f"triage_classifications_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            with open(output_file, 'w') as f:
                # Use model_dump with exclude_none=False to include all fields (even None values)
                # This ensures the new master prompt fields are included in the JSON
                json.dump(
                    [cls.model_dump(exclude_none=False, mode='json') for cls in classifications],
                    f,
                    indent=2,
                    default=str
                )
            print(f"\n💾 Classifications saved to: {output_file}")
        else:
            print(f"\n⚠️  No classifications to save. All patients failed or no eligible patients found.")
            print(f"   Check for permission errors or ensure patients have FirstAssessment and diagnosis.")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
