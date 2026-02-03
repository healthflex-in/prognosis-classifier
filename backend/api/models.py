"""
Pydantic models for API responses.
"""
from pydantic import BaseModel
from typing import Optional, List
from enum import Enum


class Criticality(str, Enum):
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class Goal(str, Enum):
    RTA = "RTA"
    RTS = "RTS"


class TimelineStatus(str, Enum):
    ACUTE = "Acute"
    SUB_ACUTE = "Sub-Acute"
    CHRONIC = "Chronic"


class RiskLevel(str, Enum):
    LOW = "Low"
    HIGH = "High"


class TestingFocus(str, Enum):
    FORCE_FRAME = "ForceFrame"
    FORCE_DECK = "ForceDeck"
    STANDARD = "Standard"


class ForceLevel(str, Enum):
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"


class Patient(BaseModel):
    """Patient data model matching frontend interface."""
    id: str
    patientName: str
    criticality: Criticality
    goal: Goal
    timelineStatus: TimelineStatus
    riskLevel: RiskLevel
    jointGroup: str
    primaryJoint: str
    testingFocus: TestingFocus
    strengthAsymmetry: Optional[float] = None
    absoluteForceLevel: Optional[ForceLevel] = None
    psychosocialFlags: Optional[List[str]] = []


class CountStats(BaseModel):
    """Statistics with name and count."""
    name: str
    value: int
    percentage: Optional[float] = None


class StackedCountStats(BaseModel):
    """Stacked statistics with breakdown by criticality."""
    name: str
    value: int
    High: Optional[int] = 0
    Medium: Optional[int] = 0
    Low: Optional[int] = 0


class JointGroupStats(BaseModel):
    """Joint group statistics with testing focus breakdown."""
    name: str
    value: int
    ForceFrame: Optional[int] = 0
    ForceDeck: Optional[int] = 0
    Standard: Optional[int] = 0


class AsymmetryData(BaseModel):
    """Asymmetry data for charts."""
    name: str
    value: float
    category: Optional[str] = None


class ScatterData(BaseModel):
    """Scatter plot data."""
    x: float
    y: float
    name: str
    category: Optional[str] = None


class DistributionBin(BaseModel):
    """Distribution bin for histograms."""
    range: str
    min: float
    max: float
    count: int


class MatrixCell(BaseModel):
    """Matrix cell for heatmaps."""
    xLabel: str  # Criticality
    yLabel: str  # Risk Level
    value: int   # Count


# ============================================================================
# New Master Prompt Classification Models
# ============================================================================

class FunctionalRegion(str, Enum):
    """Functional region classification."""
    UPPER_LIMB = "Upper limb"
    LOWER_LIMB = "Lower limb"
    SPINE = "Spine"
    POSTERIOR_CHAIN = "Posterior chain"
    MULTI_JOINT = "Multi-joint"
    UNCLEAR = "Unclear"


class OccupationCategory(str, Enum):
    """Occupational category classification."""
    SEDENTARY = "Sedentary / desk-based"
    MANUAL = "Manual / physical"
    STUDENT = "Student"
    ATHLETE = "Athlete"
    RETIRED = "Retired"
    UNCLEAR = "Unclear"


class ActivityProfile(str, Enum):
    """Activity profile classification."""
    SEDENTARY = "Sedentary / minimally active"
    RECREATIONAL = "Recreationally active"
    STRUCTURED_FITNESS = "Structured fitness"
    COMPETITIVE = "Competitive / elite sport"
    UNCLEAR = "Unclear"


class ActivitySubtype(str, Enum):
    """Recreational activity subtype."""
    RUNNING_DOMINANT = "Running-dominant"
    GYM_STRENGTH = "Gym / strength-dominant"
    SPORT_SPECIFIC = "Sport-specific"
    MIXED_FITNESS = "Mixed / general fitness"
    UNCLEAR = "Unclear"


class ClinicalStage(str, Enum):
    """Clinical stage classification."""
    ACUTE = "Acute"
    SUBACUTE = "Subacute"
    CHRONIC = "Chronic"
    RECURRENT = "Recurrent"
    PRE_HAB = "Pre-hab / pre-surgical"
    POST_OPERATIVE = "Post-operative"
    UNCLEAR = "Unclear"


class PainInterference(str, Enum):
    """Pain interference classification."""
    NO_INTERFERENCE = "No / minimal interference"
    ACTIVITY_ONLY = "Activity-only interference"
    WORK_DAILY = "Work / daily function interference"
    MULTI_DOMAIN = "Multi-domain interference"
    FORCED_ENTRY = "Forced entry (surgery or trauma)"
    UNCLEAR = "Unclear"


class IntentCategory(str, Enum):
    """Outcome intent/expectation classification."""
    PAIN_RELIEF = "Pain relief only"
    DAILY_FUNCTION = "Return to daily function"
    ACTIVITY_FITNESS = "Return to activity / fitness"
    RETURN_TO_SPORT = "Return to sport"
    PERFORMANCE = "Performance / optimisation"
    POST_SURGICAL = "Post-surgical recovery"
    UNCLEAR = "Unclear"


class PatientMasterView(BaseModel):
    """New patient classification model based on master prompt."""
    id: str
    patientName: str
    
    # Step 1: Diagnosis
    provisionalDiagnosis: Optional[str] = None
    canonicalDiagnosis: Optional[str] = None
    
    # Step 2: Joint & Region
    primaryJoint: Optional[str] = None
    functionalRegion: Optional[FunctionalRegion] = None
    
    # Step 3: Occupation
    occupationCategory: Optional[OccupationCategory] = None
    
    # Step 4: Activity Profile
    activityProfile: Optional[ActivityProfile] = None
    activitySubtype: Optional[ActivitySubtype] = None
    
    # Step 5: Clinical Stage
    clinicalStage: Optional[ClinicalStage] = None
    
    # Step 6: Pain Interference
    painInterference: Optional[PainInterference] = None
    
    # Step 7: NPRS
    nprsAvailable: bool = False
    nprsScore: Optional[int] = None  # 0-10
    
    # Step 9: Intent
    intentCategory: Optional[IntentCategory] = None
    


# Stats models for new classification
class DiagnosisStats(BaseModel):
    """Diagnosis distribution statistics."""
    name: str  # Canonical diagnosis
    count: int
    percentage: float


class JointRegionStats(BaseModel):
    """Joint and functional region statistics."""
    primaryJoint: str
    functionalRegion: str
    count: int
    percentage: float


class OccupationalStats(BaseModel):
    """Occupational category statistics."""
    category: str
    count: int
    percentage: float
    unclearCount: Optional[int] = 0
    unclearPercentage: Optional[float] = 0.0


class ActivityProfileStats(BaseModel):
    """Activity profile statistics."""
    profile: str
    count: int
    percentage: float


class ActivityRecreationalStats(BaseModel):
    """Recreational activity subtype statistics."""
    subtype: str
    count: int
    percentage: float  # Percentage of recreationally active patients


class ClinicalStageStats(BaseModel):
    """Clinical stage statistics."""
    stage: str
    count: int
    percentage: float


class PainInterferenceStats(BaseModel):
    """Pain interference statistics."""
    interference: str
    count: int
    percentage: float


class NPRSAvailabilityStats(BaseModel):
    """NPRS availability statistics."""
    totalPatients: int
    nprsPresent: int
    nprsAbsent: int
    presentPercentage: float
    absentPercentage: float


class NPRSDistributionBin(BaseModel):
    """NPRS distribution bin."""
    range: str  # e.g., "0-3", "4-6", "7-10"
    min: int
    max: int
    count: int
    percentage: float  # Percentage of NPRS-present patients


class PainInterferenceNPRSCell(BaseModel):
    """Pain interference × NPRS matrix cell."""
    interference: str
    nprsRange: str
    count: int
    percentage: float  # Percentage of NPRS-present patients


class IntentStats(BaseModel):
    """Intent/expectation statistics."""
    intent: str
    count: int
    percentage: float
