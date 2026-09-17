"""
Data loader for reading and transforming triage classification data.

Originally this read from JSON files written by the triage agent.
We now prefer to read from MongoDB (`stance-dashboard.classification` collection)
so the frontend always works off the latest stored classifications.
"""

import os
import json
from pathlib import Path
from typing import List, Dict, Any, Optional
from datetime import datetime
import time
from threading import Lock

from pymongo import MongoClient

from api.models import (
    Patient, TestingFocus, ForceLevel, RiskLevel,
    PatientMasterView, FunctionalRegion, OccupationCategory, ActivityProfile, ActivitySubtype,
    ClinicalStage, PainInterference, IntentCategory
)

# Simple in-memory cache for patient data
_patient_cache = {
    "data": None,
    "timestamp": 0,
    "ttl": 30  # Cache for 30 seconds
}
_cache_lock = Lock()


def _get_mongo_classification_collection():
    """
    Get a handle to the MongoDB classification collection.

    Uses the same environment variables as the Mongo loaders:
    - MONGO_URI or MONGODB_URI for the connection string
    - MONGO_DB for the database name (defaults to 'stance-dashboard')
    """
    mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
    db_name = os.getenv("MONGO_DB", "stance-dashboard")

    client = MongoClient(
        mongo_uri,
        tlsAllowInvalidCertificates=True,
        tlsAllowInvalidHostnames=True,
        serverSelectionTimeoutMS=5000,  # Reduced from 30s to 5s
        connectTimeoutMS=5000,  # Reduced from 30s to 5s
        socketTimeoutMS=10000,  # Reduced from 60s to 10s
        retryWrites=True,
        retryReads=True,
        maxPoolSize=20,  # Reduced pool size
        minPoolSize=5,   # Reduced min pool size
    )
    db = client[db_name]
    return db["classification"]


def _load_classifications_from_mongo() -> List[Dict[str, Any]]:
    """
    Load all classifications from MongoDB.

    Returns:
        List of classification dictionaries (with `_id` stripped and patient_id converted to string).
    """
    try:
        from bson import ObjectId
        collection = _get_mongo_classification_collection()

        # Only show fully classified patients on the dashboard, and avoid
        # pulling unnecessary fields to keep queries fast while triage runs.
        query = {"status": "completed"}
        projection = {
            "_id": 1,
            "patient_id": 1,
            "patient_name": 1,
            "status": 1,
            "created_at": 1,
            "updated_at": 1,
            "canonical_diagnosis": 1,
            "provisional_diagnosis": 1,
            "extracted_fields": 1,
            "source_data": 1,
        }

        cursor = collection.find(query, projection=projection).batch_size(500)
        docs = list(cursor)

        # Convert ObjectId fields to strings for JSON serialization
        for doc in docs:
            # Strip Mongo _id
            doc.pop("_id", None)
            # Convert patient_id from ObjectId to string if needed
            if "patient_id" in doc and isinstance(doc["patient_id"], ObjectId):
                doc["patient_id"] = str(doc["patient_id"])

        return docs
    except Exception as e:
        # If Mongo is not reachable or collection missing, fall back to JSON files
        print(f"⚠️  Error loading classifications from MongoDB, falling back to JSON files: {e}")
        return []


def find_latest_classification_file() -> Optional[Path]:
    """
    Find the most recent triage classification JSON file.
    
    Returns:
        Path to the latest classification file, or None if not found
    """
    llm_dir = Path(__file__).parent.parent / "LLM"
    
    # Find all classification files
    classification_files = list(llm_dir.glob("triage_classifications_*.json"))
    
    if not classification_files:
        return None
    
    # Sort by modification time (most recent first)
    classification_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    
    return classification_files[0]


def load_classifications(output_file_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Load classification data, preferring MongoDB, with JSON file fallback.

    Args:
        output_file_path: Optional specific file path to load from (for legacy JSON-based runs)

    Returns:
        List of classification dictionaries
    """
    # 1) Prefer MongoDB (source of truth going forward)
    mongo_data = _load_classifications_from_mongo()
    if mongo_data:
        return mongo_data

    # 2) Fallback to JSON files (older runs / local testing)
    # If a specific file is provided, use it
    if output_file_path:
        classification_file = Path(output_file_path)
        if classification_file.exists():
            try:
                with open(classification_file, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
                    return []
            except Exception as e:
                print(f"Error loading classifications from {output_file_path}: {e}")
                # Fall back to latest file
                pass
    
    # Otherwise, find the latest classification file
    classification_file = find_latest_classification_file()
    
    if not classification_file:
        return []
    
    try:
        with open(classification_file, 'r') as f:
            data = json.load(f)
            if isinstance(data, list):
                return data
            return []
    except Exception as e:
        print(f"Error loading classifications: {e}")
        return []


def transform_to_patient(classification: Dict[str, Any]) -> Patient:
    """
    Transform a classification dictionary to Patient model.
    
    Args:
        classification: Classification dictionary from JSON
        
    Returns:
        Patient model instance
    """
    # Extract risk level from risk_stratification
    risk_strat = classification.get('risk_stratification', {})
    risk_level = risk_strat.get('risk_level', 'Low Risk')
    # Convert "Low Risk" / "High Risk" / "High Risk (Psychosocially Mediated)" to "Low" / "High"
    if 'High' in risk_level or 'Psychosocially Mediated' in risk_level:
        risk_level = 'High'
    else:
        risk_level = 'Low'
    
    # Extract joint-specific group data
    joint_group_data = classification.get('joint_specific_group', {})
    joint_group = joint_group_data.get('group', 'Other')
    primary_joint = joint_group_data.get('primary_joint', 'Unknown')
    testing_focus_str = joint_group_data.get('testing_focus', 'Standard')
    
    # Map testing focus
    testing_focus_map = {
        'ForceFrame isometric': TestingFocus.FORCE_FRAME,
        'ForceDeck jump/landing': TestingFocus.FORCE_DECK,
        'ForceFrame': TestingFocus.FORCE_FRAME,
        'ForceDeck': TestingFocus.FORCE_DECK,
        'Standard': TestingFocus.STANDARD,
    }
    # Check if any key is in the string (for partial matches)
    testing_focus = TestingFocus.STANDARD
    for key, value in testing_focus_map.items():
        if key.lower() in testing_focus_str.lower():
            testing_focus = value
            break
    
    # Extract force level
    absolute_force_level_str = classification.get('absolute_force_level')
    absolute_force_level = None
    if absolute_force_level_str:
        try:
            absolute_force_level = ForceLevel(absolute_force_level_str)
        except ValueError:
            absolute_force_level = None
    
    # Extract psychosocial flags
    psychosocial_flags = risk_strat.get('psychosocial_flags', [])
    
    return Patient(
        id=classification.get('patient_id', ''),
        patientName=classification.get('patient_name', 'Unknown'),
        criticality=classification.get('criticality', 'Medium'),
        goal=classification.get('goal', 'RTA'),
        timelineStatus=classification.get('timeline_status', 'Sub-Acute'),
        riskLevel=risk_level,
        jointGroup=joint_group,
        primaryJoint=primary_joint,
        testingFocus=testing_focus,
        strengthAsymmetry=classification.get('strength_asymmetry_percent'),
        absoluteForceLevel=absolute_force_level,
        psychosocialFlags=psychosocial_flags if isinstance(psychosocial_flags, list) else []
    )


def get_all_patients() -> List[PatientMasterView]:
    """
    Get all patients from the latest classification file.
    Now returns PatientMasterView (new format only).
    
    Returns:
        List of PatientMasterView models
    """
    return get_all_patients_master_view()


def transform_to_master_view(classification: Dict[str, Any]) -> PatientMasterView:
    """
    Transform a classification dictionary to PatientMasterView model.
    Handles both old flat structure and new nested structure.
    
    Args:
        classification: Classification dictionary from JSON
        
    Returns:
        PatientMasterView model instance
    """
    # Helper to safely get enum value
    def get_enum_value(enum_class, value: Optional[str], default=None):
        if not value:
            return default
        try:
            # Try to match by value
            for item in enum_class:
                if item.value == value:
                    return item
            # Try case-insensitive match
            value_lower = value.lower()
            for item in enum_class:
                if item.value.lower() == value_lower:
                    return item
        except:
            pass
        return default
    
    # Helper to map snake_case to enum values
    def map_snake_case_to_enum(value: str, enum_class, default):
        """Map snake_case values (e.g., 'lower_limb') to enum values (e.g., 'Lower limb')."""
        if not value:
            return default
        value_lower = value.lower()
        # Map common snake_case patterns
        mapping = {
            'lower_limb': 'Lower limb',
            'upper_limb': 'Upper limb',
            'posterior_chain': 'Posterior chain',
            'multi_joint': 'Multi-joint',
            'recreationally_active': 'Recreationally active',
            'structured_fitness': 'Structured fitness',
            'running_dominant': 'Running-dominant',
            'gym_strength': 'Gym / strength-dominant',
            'sport_specific': 'Sport-specific',
            'mixed_fitness': 'Mixed / general fitness',
            'sedentary_desk': 'Sedentary / desk-based',
            'manual_physical': 'Manual / physical',
            'activity_interference': 'Activity-only interference',
            'work_interference': 'Work / daily function interference',
            'multi_domain': 'Multi-domain interference',
            'forced_entry': 'Forced entry (surgery or trauma)',
            'no_interference': 'No / minimal interference',
            'return_activity': 'Return to activity / fitness',
            'return_sport': 'Return to sport',
            'return_daily_function': 'Return to daily function',
            'post_surgical': 'Post-surgical recovery',
            'pre_hab': 'Pre-hab / pre-surgical',
            'post_operative': 'Post-operative',
        }
        mapped_value = mapping.get(value_lower, value)
        return get_enum_value(enum_class, mapped_value, default)
    
    # Check if this is the new nested structure
    extracted_fields = classification.get('extracted_fields', {})
    source_data = classification.get('source_data', {})
    
    # Extract from nested structure if present, otherwise fall back to flat structure
    if extracted_fields:
        # New nested structure
        provisional_diag = extracted_fields.get('provisional_diagnosis', {})
        canonical_diagnosis = provisional_diag.get('canonical_label', 'Unclear')
        provisional_diagnosis = source_data.get('provisional_diagnosis_raw') or 'Unclear'
        
        joint_mapping = extracted_fields.get('joint_mapping', {})
        primary_joint = joint_mapping.get('primary_joint', 'Unclear')
        functional_region_str = joint_mapping.get('functional_region', 'unclear')
        
        clinical_stage_data = extracted_fields.get('clinical_stage', {})
        clinical_stage_str = clinical_stage_data.get('stage', 'unclear')
        
        activity_data = extracted_fields.get('activity_profile', {})
        activity_profile_str = activity_data.get('primary_category', 'unclear')
        activity_subtype_str = activity_data.get('sub_category')
        
        occupation_data = extracted_fields.get('occupation', {})
        occupation_category_str = occupation_data.get('category', 'unclear')
        
        pain_data = extracted_fields.get('pain_interference', {})
        pain_interference_str = pain_data.get('category', 'unclear')
        
        nprs_data = extracted_fields.get('pain_intensity_nprs', {})
        nprs_available = nprs_data.get('found', False)
        nprs_score = nprs_data.get('value')
        
        intent_data = extracted_fields.get('intent', {})
        intent_category_str = intent_data.get('primary_intent', 'unclear')
    else:
        # Old flat structure (for backward compatibility)
        canonical_diagnosis = classification.get('canonical_diagnosis') or classification.get('canonicalDiagnosis') or 'Unclear'
        provisional_diagnosis = classification.get('provisional_diagnosis') or classification.get('provisionalDiagnosis') or 'Unclear'
        primary_joint = classification.get('primary_joint') or classification.get('primaryJoint') or 'Unclear'
        functional_region_str = classification.get('functional_region') or classification.get('functionalRegion') or 'unclear'
        clinical_stage_str = classification.get('clinical_stage') or classification.get('clinicalStage') or 'unclear'
        activity_profile_str = classification.get('activity_profile') or classification.get('activityProfile') or 'unclear'
        activity_subtype_str = classification.get('activity_subtype') or classification.get('activitySubtype')
        occupation_category_str = classification.get('occupation_category') or classification.get('occupationCategory') or 'unclear'
        pain_interference_str = classification.get('pain_interference') or classification.get('painInterference') or 'unclear'
        nprs_available = classification.get('nprs_available', False) or classification.get('nprsAvailable', False)
        nprs_score = classification.get('nprs_score') or classification.get('nprsScore')
        intent_category_str = classification.get('intent_category') or classification.get('intentCategory') or 'unclear'
    
    # Map to enums
    functional_region = map_snake_case_to_enum(functional_region_str, FunctionalRegion, FunctionalRegion.UNCLEAR) or FunctionalRegion.UNCLEAR
    clinical_stage = map_snake_case_to_enum(clinical_stage_str, ClinicalStage, ClinicalStage.UNCLEAR) or ClinicalStage.UNCLEAR
    activity_profile = map_snake_case_to_enum(activity_profile_str, ActivityProfile, ActivityProfile.UNCLEAR) or ActivityProfile.UNCLEAR
    activity_subtype = map_snake_case_to_enum(activity_subtype_str, ActivitySubtype, None) if activity_subtype_str else None
    occupation_category = map_snake_case_to_enum(occupation_category_str, OccupationCategory, OccupationCategory.UNCLEAR) or OccupationCategory.UNCLEAR
    pain_interference = map_snake_case_to_enum(pain_interference_str, PainInterference, PainInterference.UNCLEAR) or PainInterference.UNCLEAR
    intent_category = map_snake_case_to_enum(intent_category_str, IntentCategory, IntentCategory.UNCLEAR) or IntentCategory.UNCLEAR
    
    # Validate NPRS score
    if nprs_score is not None:
        try:
            nprs_score = int(nprs_score)
            if not (0 <= nprs_score <= 10):
                nprs_score = None
                nprs_available = False
        except:
            nprs_score = None
            nprs_available = False
    
    return PatientMasterView(
        id=classification.get('patient_id', ''),
        patientName=classification.get('patient_name', 'Unknown'),
        provisionalDiagnosis=provisional_diagnosis,
        canonicalDiagnosis=canonical_diagnosis,
        primaryJoint=primary_joint,
        functionalRegion=functional_region,
        occupationCategory=occupation_category,
        activityProfile=activity_profile,
        activitySubtype=activity_subtype,
        clinicalStage=clinical_stage,
        painInterference=pain_interference,
        nprsAvailable=nprs_available,
        nprsScore=nprs_score,
        intentCategory=intent_category,
        strengthAsymmetry=classification.get('strength_asymmetry_percent') or classification.get('strengthAsymmetry'),
        absoluteForceLevel=classification.get('absolute_force_level') or classification.get('absoluteForceLevel'),
        romAsymmetryDegrees=classification.get('rom_asymmetry_degrees') or classification.get('romAsymmetryDegrees')
    )


def get_all_patients_master_view(output_file_path: Optional[str] = None) -> List[PatientMasterView]:
    """
    Get all patients in master view format from the latest classification file.
    Uses in-memory caching to improve dashboard performance.
    
    Args:
        output_file_path: Optional specific file path to load from (for real-time updates during triage)
    
    Returns:
        List of PatientMasterView models
    """
    current_time = time.time()
    
    # Use cache if data is fresh (within TTL)
    with _cache_lock:
        if (_patient_cache["data"] is not None and 
            current_time - _patient_cache["timestamp"] < _patient_cache["ttl"] and
            output_file_path is None):  # Don't use cache for specific file requests
            return _patient_cache["data"]
    
    # Load fresh data
    classifications = load_classifications(output_file_path=output_file_path)
    patient_data = [transform_to_master_view(cls) for cls in classifications]
    
    # Update cache (only for general requests, not specific files)
    if output_file_path is None:
        with _cache_lock:
            _patient_cache["data"] = patient_data
            _patient_cache["timestamp"] = current_time
    
    return patient_data


def clear_patient_cache():
    """Clear the patient data cache to force fresh data loading."""
    with _cache_lock:
        _patient_cache["data"] = None
        _patient_cache["timestamp"] = 0
