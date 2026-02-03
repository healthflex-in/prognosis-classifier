// Clinical data types for patient monitoring dashboard

export type Criticality = "High" | "Medium" | "Low";
export type Goal = "RTA" | "RTS"; // Return to Activity / Return to Sport
export type TimelineStatus = "Acute" | "Sub-Acute" | "Chronic";
export type RiskLevel = "Low" | "High";
export type TestingFocus = "ForceFrame" | "ForceDeck" | "Standard";
export type ForceLevel = "Low" | "Medium" | "High";
export type JointGroup = "Posterior Chain Dominant" | "Anterior Chain Dominant" | "Other";

export interface PatientData {
  id: string;
  patientName: string;
  criticality: Criticality;
  goal: Goal;
  timelineStatus: TimelineStatus;
  riskLevel: RiskLevel;
  jointGroup: JointGroup;
  primaryJoint: string;
  testingFocus: TestingFocus;
  strengthAsymmetry: number | null;
  absoluteForceLevel: ForceLevel | null;
  psychosocialFlags?: string[];
}

export interface CriticalityStats {
  criticality: Criticality;
  count: number;
}

export interface TimelineStats {
  timelineStatus: TimelineStatus;
  count: number;
  byCriticality?: Record<Criticality, number>;
}

export interface RiskStats {
  riskLevel: RiskLevel;
  count: number;
}

export interface JointGroupStats {
  jointGroup: JointGroup;
  count: number;
  byTestingFocus?: Record<TestingFocus, number>;
}

export interface TestingFocusStats {
  testingFocus: TestingFocus;
  count: number;
}

export interface AsymmetryData {
  patientId: string;
  patientName: string;
  asymmetryPercent: number;
  criticality: Criticality;
  riskLevel: RiskLevel;
}

export interface AsymmetryForceData {
  patientId: string;
  patientName: string;
  asymmetryPercent: number;
  forceLevel: ForceLevel;
  criticality: Criticality;
  riskLevel: RiskLevel;
}

export interface DistributionBin {
  range: string;
  min: number;
  max: number;
  count: number;
}

export interface RiskCriticalityMatrix {
  riskLevel: RiskLevel;
  criticality: Criticality;
  count: number;
}

// API Filter types
export interface ClinicalFilters {
  criticality?: Criticality;
  timelineStatus?: TimelineStatus;
  riskLevel?: RiskLevel;
  jointGroup?: JointGroup;
  testingFocus?: TestingFocus;
}

// ============================================================================
// New Master Prompt Classification Types
// ============================================================================

export type FunctionalRegion = 
  | "Upper limb"
  | "Lower limb"
  | "Spine"
  | "Posterior chain"
  | "Multi-joint";

export type ActivityProfile =
  | "Sedentary / minimally active"
  | "Recreationally active"
  | "Structured fitness"
  | "Competitive / elite sport"
  | "Unclear";

export type ActivitySubtype =
  | "Running-dominant"
  | "Gym / strength-dominant"
  | "Sport-specific"
  | "Mixed / general fitness"
  | "Unclear";

export type ClinicalStage =
  | "Acute"
  | "Subacute"
  | "Chronic"
  | "Recurrent"
  | "Pre-hab / pre-surgical"
  | "Post-operative"
  | "Unclear";

export type PainInterference =
  | "No / minimal interference"
  | "Activity-only interference"
  | "Work / daily function interference"
  | "Multi-domain interference"
  | "Forced entry (surgery or trauma)"
  | "Unclear";

export type IntentCategory =
  | "Pain relief only"
  | "Return to daily function"
  | "Return to activity / fitness"
  | "Return to sport"
  | "Performance / optimisation"
  | "Post-surgical recovery"
  | "Unclear";

export interface PatientMasterView {
  id: string;
  patientName: string;
  provisionalDiagnosis?: string | null;
  canonicalDiagnosis?: string | null;
  primaryJoint?: string | null;
  functionalRegion?: FunctionalRegion | null;
  occupationCategory?: string | null;
  activityProfile?: ActivityProfile | null;
  activitySubtype?: ActivitySubtype | null;
  clinicalStage?: ClinicalStage | null;
  painInterference?: PainInterference | null;
  nprsAvailable: boolean;
  nprsScore?: number | null; // 0-10
  intentCategory?: IntentCategory | null;
  strengthAsymmetry?: number | null;
  absoluteForceLevel?: string | null;
  romAsymmetryDegrees?: number | null;
}

// Stats models for new classification
export interface DiagnosisStats {
  name: string;
  count: number;
  percentage: number;
}

export interface JointRegionStats {
  primaryJoint: string;
  functionalRegion: string;
  count: number;
  percentage: number;
}

export interface OccupationalStats {
  category: string;
  count: number;
  percentage: number;
  unclearCount?: number;
  unclearPercentage?: number;
}

export interface ActivityProfileStats {
  profile: string;
  count: number;
  percentage: number;
}

export interface ActivityRecreationalStats {
  subtype: string;
  count: number;
  percentage: number; // Percentage of recreationally active patients
}

export interface ClinicalStageStats {
  stage: string;
  count: number;
  percentage: number;
}

export interface PainInterferenceStats {
  interference: string;
  count: number;
  percentage: number;
}

export interface NPRSAvailabilityStats {
  totalPatients: number;
  nprsPresent: number;
  nprsAbsent: number;
  presentPercentage: number;
  absentPercentage: number;
}

export interface NPRSDistributionBin {
  range: string; // e.g., "0-3", "4-6", "7-10"
  min: number;
  max: number;
  count: number;
  percentage: number; // Percentage of NPRS-present patients
}

export interface PainInterferenceNPRSCell {
  interference: string;
  nprsRange: string;
  count: number;
  percentage: number; // Percentage of NPRS-present patients
}

export interface IntentStats {
  intent: string;
  count: number;
  percentage: number;
}
