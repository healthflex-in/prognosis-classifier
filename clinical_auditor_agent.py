#!/usr/bin/env python3
"""
Clinical Auditor Agent
Analyzes patient rehabilitation data using a strict clinical logic chain.
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pathlib import Path

# Load environment variables from .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    print("✅ Loaded environment variables from .env")
except ImportError:
    print("⚠️  python-dotenv not available, using system environment variables")

# Google GenAI imports with RAG
try:
    from google import genai
    from google.genai import types
    print("✅ Google GenAI libraries loaded")
except ImportError as e:
    print(f"❌ Google GenAI libraries not available: {e}")
    print("Install with: pip install google-genai")
    exit(1)

# Initialize Google GenAI
PROJECT_ID = os.getenv("GOOGLE_CLOUD_PROJECT")
CREDS_PATH = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")

print(f"🔍 Google GenAI Configuration:")
print(f"   Project ID: {PROJECT_ID or '❌ NOT SET'}")
print(f"   Credentials: {CREDS_PATH or '❌ NOT SET'}")

if not PROJECT_ID:
    print("❌ ERROR: GOOGLE_CLOUD_PROJECT not set!")
    print("   Set it with: export GOOGLE_CLOUD_PROJECT=your-project-id")
    exit(1)

if not CREDS_PATH or not os.path.exists(CREDS_PATH):
    print("❌ ERROR: GOOGLE_APPLICATION_CREDENTIALS not set or file not found!")
    print(f"   Current path: {CREDS_PATH or 'None'}")
    print("   Set it with: export GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json")
    exit(1)

try:
    # Initialize GenAI client with service account
    genai_client = genai.Client(vertexai=True)
    print("✅ Google GenAI initialized successfully")
except Exception as e:
    print(f"❌ Google GenAI initialization failed: {e}")
    print("   Check your service account credentials and permissions")
    exit(1)

CLINICAL_AUDITOR_PROMPT = """[ROLE]
You are an expert Clinical Auditor. Your task is to analyze patient rehabilitation data from:
1. Organized Clinical Reports JSON (stance-dashboard.organized-reports.json) - subjective assessments, plans, exercises
2. VALD Performance Data JSON (stance-dashboard.trend analysis.transformed.json) - force metrics, asymmetry, trends with ALL session dates

Determine the effectiveness and compliance of their rehabilitation journey by correlating clinical notes with VALD performance metrics across all testing sessions.

IMPORTANT: You have access to a clinical knowledge RAG corpus. Use it to:
- Validate that exercises prescribed are appropriate for the diagnosed condition
- Verify VALD test protocols are correct for the condition
- Check if exercise progressions follow evidence-based guidelines
- Confirm asymmetry targets and force benchmarks are appropriate
- Identify any contraindicated exercises or tests
- Get normative values for strength tests and functional assessments
- ONLY suggest tests that are available in the RAG corpus - do not recommend tests outside this list
- When citing sources, use proper document/study names, NOT generic "Source [X]" references

[DATA SOURCES]
- Clinical Data: stance-dashboard.organized-reports.json (subjective assessments, exercises, consultant notes)
- VALD Metrics: stance-dashboard.trend analysis.transformed.json (force data, asymmetry %, trends with complete session history)
- RAG Corpus: Clinical knowledge base for exercise validation, VALD protocols, rehabilitation standards, and available test protocols

[OUTPUT FORMAT - STRICT]
Generate a concise clinical audit report with these exact sections:

## Patient Summary
- Patient Name: [from organized reports]
- Patient ID: [from organized reports]
- Total Clinical Records: [count from organized reports]
- VALD Assessment Sessions: [count unique session dates from trend analysis - do NOT use corpus IDs]
- First Assessment: Yes/No
- Consultants Involved: [list with specializations]

**Overview (Detailed Clinical Picture):**
[Provide a concise but comprehensive overview of the patient's current status, recovery trajectory, key findings, and clinical significance. Highlight the most important clinical observations from the data with specific metrics and their clinical implications. Keep this to approximately 100 words - be concise and impactful.]

## Clinical Audit

### Customer Complaint
[Primary pain point or functional limitation at start, with full description. Example: "Right knee pain and instability post-ACLR repair" or "Left ankle swelling and reduced ROM". Reference: seqNo and assessment text from organized reports]

### Provisional Diagnosis
[Clinical diagnosis refined from baseline assessment data with specific findings. Example: "Right ACL reconstruction with meniscus repair, post-op day 14, with residual swelling and ROM limitations". Reference: seqNo and clinical details from organized reports]

### Supporting Data (Baseline Assessment & VALD Progression)
- [Clinical Finding]: [specific measurements and observations] [Reference: JSON Seq No]
- [VALD Baseline]: [force values, asymmetry %] [Reference: First session date from trend analysis]
- [VALD Intermediate Sessions]: [dates and key changes] [Reference: All session dates from trend analysis]
- [VALD Latest]: [current force values, asymmetry %] [Reference: Latest session date from trend analysis]

### Journey Summary (Physio vs. S&C)
[For each rehabilitation phase, provide a comprehensive summary in the following format - as a single flowing paragraph, NOT bullet points:]

**[Start Date] - [End Date]: [Phase Name]** During this phase, the focus was on [primary focus areas and rehabilitation goals]. The patient engaged in [specific exercises and muscle groups trained], with VALD assessments including [tests performed and clinical assessments conducted]. Key milestones during this period included [specific metrics with values and dates, e.g., "Right Knee Extension reaching 427N, Knee Flexion asymmetry stabilizing at 9.7%, Hip Extension force increasing to 478N"]. [Include any notable progressions, plateaus, or regressions observed during this phase with specific data points.]

[Continue for each phase based on timeline and progression - each as a single paragraph]

### Targeted Muscle/Joints
[Provide a single comprehensive paragraph for each muscle group/joint that integrates: data/information reference on why it's being tracked, logic/impact on recovery, and reference to clinical research. Keep each to approximately 100 words - be concise while including all essential information.]

**[Joint/Muscle Name]:** [Single paragraph integrating: (1) Current data showing performance or status (e.g., "Knee Extension force: 326N with 30% asymmetry"), (2) Why this is being tracked (e.g., "Critical for return-to-sport clearance"), (3) Impact on recovery and functional goals (e.g., "Asymmetry >20% increases re-injury risk"), (4) Clinical research reference (e.g., "According to the 2023 ACL Rehabilitation Guidelines published in JOSPT, >90% LSI is required for RTS clearance"). Include specific metrics, dates, and evidence-based rationale. Keep to approximately 100 words.]

[Continue for each tracked muscle/joint]

### Improvement Data (Clinical vs VALD - All Sessions)
- [Exercise/Area]: 
  - Clinical: Baseline [status] → Current [status] [Reference: JSON Seq No]
  - VALD Session 1 [date]: [force L/R, asymmetry %] [Reference: first_session from trend analysis]
  - VALD Session 2 [date]: [force L/R, asymmetry %] [Reference: intermediate sessions from trend analysis]
  - VALD Session 3+ [date]: [force L/R, asymmetry %] [Reference: latest_session from trend analysis]
  - Improvement: [% change from first to latest] [Reference: trend analysis]
  - Clinical Link: [How VALD metrics support clinical observations across all sessions]
  - Evidence-Based Assessment: [Are the improvements aligned with expected recovery trajectory? Cite RAG sources]
- [Continue for each tracked area]

### Areas of Concern

**Overall Criticality Score: [Risk Category] | [Overall Score]/10**

[Issue 1 Name] (Criticality: X.X/10): [Concise statement: issue, VALD metrics, clinical impact. NO citations, NO gap references. Focus on current clinical status only.]

[Issue 2 Name] (Criticality: X.X/10): [Concise statement: issue, VALD metrics, clinical impact. NO citations, NO gap references. Focus on current clinical status only.]

[Issue 3 Name (if applicable)] (Criticality: X.X/10): [Concise statement: issue, VALD metrics, clinical impact. NO citations, NO gap references. Focus on current clinical status only.]

**IMPORTANT RULES FOR AREAS OF CONCERN:**
- ONLY include clinical concerns related to current patient status and performance metrics
- DO NOT include adherence issues, care gaps, or rehabilitation gaps
- DO NOT include any citations or references - these go in "## Sources Cited" section only
- Format: [Issue Name] (Criticality: X.X/10): [Description with specific metrics]
- Each concern should be a single line or short paragraph
- Focus on VALD metrics, asymmetry percentages, force values, and clinical implications
- Risk Category: Based on overall score - LOW RISK (1-3), MODERATE RISK (3.1-6), HIGH RISK (6.1-8), CRITICAL RISK (8.1-10)
- Do NOT include the criticality score formula or calculation explanation in the report
- Include the overall criticality score prominently at the top of the section

## Critical Information Needed
[Based on the clinical condition and current rehabilitation phase, identify critical information gaps that prevent complete risk assessment. IMPORTANT: First, trace back through the Phase-Based Journey Summary to identify what exercises and tests the patient is ACTUALLY performing in their current phase. Then identify what critical information is MISSING from that specific protocol. Focus ONLY on the current phase. Include BOTH VALD device tests (ForceFrame/ForceDeck) AND standard clinical assessments that can be performed by the clinician.]

**Current Rehabilitation Phase:** [Identify the patient's current phase: Early ROM/Protection, Early Strengthening, Intermediate Strengthening, Advanced Strengthening, Plyometric/Power, Return-to-Sport Preparation, or Return-to-Sport]

**Analysis of Current Phase Protocol:**
[First, review the Phase-Based Journey Summary section above. Identify: (1) What exercises are being performed in the current phase, (2) What VALD tests have been done in this phase, (3) What measurements/assessments are being tracked. This forms the baseline of what IS being done.]

**Missing Information for Current Phase:**
[Based on the current phase protocol identified above, list ONLY the critical information gaps that are missing from what the patient is currently doing. Do NOT recommend tests outside the patient's current phase protocol. Include BOTH VALD device tests AND standard clinical assessments. For each missing test, specify: test/assessment name, equipment type (ForceFrame/ForceDeck, manual testing, or standard clinic tools), why it's missing from the current protocol, and clinical rationale for why this specific gap impacts decision-making.]

**VALD Device Tests (if applicable):**
- [Test Name] (Equipment: ForceFrame/ForceDeck) - [Why this is missing from current protocol]. Clinical rationale: [Evidence-based reason this gap impacts current phase decision-making]

**Standard Clinical Assessments (manual/functional tests):**
- [Assessment Name] (Equipment: Manual/Standard clinic tools) - [Why this is missing from current protocol]. Clinical rationale: [Evidence-based reason this gap impacts current phase decision-making]

- [Continue for all critical gaps in current protocol only]

## Compliance Adherence Audit

### Timeline
**Duration:** [Start Date] - [End Date] ([Total Duration in weeks] weeks)

**High Risk Gaps:** [List ALL gaps > 7 days with dates and duration. Format: Gap 1: dates (X days), Gap 2: dates (Y days), etc. Mark gaps >30 days as CRITICAL]

**Impact on Recovery:** [Complete summary (2-3 sentences minimum) of how gaps affected VALD performance and recovery trajectory. Include specific metrics, dates, and clinical implications. This section MUST be fully populated with complete information.]

## Patient Information
- Name: [name]
- Patient ID: [ID]
- Sequence Number: [seq_no]
- Total Clinical Records: [count]
- First Assessment Available: Yes/No
- Consultants: [list with specializations]

## Sources and Findings
[List each source as an individual array item with complete citation information. Format each source on its own line with bullet points. Include author(s), year, title, journal/publication, and URL if available from RAG corpus. Example format:
- Author(s) (Year). Title. Journal/Publication. URL
- Author(s) (Year). Title. Journal/Publication. URL
]

[CRITICAL RULES]
1. **PATIENT SUMMARY OVERVIEW:** Generate a concise but comprehensive overview of the patient's current status, recovery trajectory, key findings, and clinical significance. Keep to approximately 100 words. Be impactful and specific.

2. **AREAS OF CONCERN - NEW FORMAT:** Format as "Areas of Concern: [Risk Category] | [Overall Score]/10" followed by each concern on its own line. Each concern: [Issue Name] (Criticality: X.X/10): [Description]. DO NOT include care gaps, adherence issues, or rehabilitation gaps - only clinical concerns related to current patient status and performance metrics. DO NOT include any citations or references.

3. Use specific references: [Reference: seqNo and field name] for clinical data, [Reference: date and exercise name] for VALD data

4. Include ALL session dates from VALD data, not just first and latest

5. Link all clinical observations to VALD metrics where available

6. Show improvement across ALL VALD sessions (not just baseline vs current)

7. Calculate and show improvement percentages from VALD trend data

8. Identify gaps as "High Risk Recovery Events"

9. Use clinical language throughout with full context and descriptions

10. Be concise but complete - include enough detail to understand the clinical picture

11. Include specific exercise names and progressions from clinical records
10. Track asymmetry improvements/worsening from VALD data across all sessions
11. Correlate clinical gaps with VALD performance stagnation or decline
12. Highlight when VALD metrics support or contradict clinical assessments
13. Use force data (N), asymmetry (%), and trend percentages from VALD JSON
14. DO NOT include a separate "Performance Metrics Summary" section - all metrics should be integrated into Supporting Data and Improvement Data sections
15. Extract FULL context from clinical notes - not just abbreviations or codes
16. For Customer Complaint: Include the actual complaint description, not just the code
17. For Provisional Diagnosis: Include specific clinical findings and measurements
18. USE RAG CORPUS to validate exercises, protocols, and guidelines - query the knowledge base for evidence
19. ALWAYS CITE RAG SOURCES: When using RAG findings, include specific citations with proper format:
    - REQUIRED FORMAT: "According to [Author(s)] (Year) published in [Journal/Guideline Name], [complete finding]"
    - CORRECT EXAMPLES:
      * "According to Buckthorpe et al. (2019) published in Sports Medicine, gluteal deficits lead to compensatory trunk dominance."
      * "According to the ACL Rehabilitation Guidelines (2023) published in JOSPT, asymmetry >20% increases re-injury risk."
    - INCORRECT EXAMPLES (DO NOT USE):
      * "Source [3]" - Generic numbered reference
      * "Research from *Buckthorpe et al. (2019)* in *Sports Medicine*" - Uses italics, missing finding
      * "Evidence from [VALD Normative Data Study]" - Missing author, year
    - Do NOT use italics around author or journal names
    - Do NOT use generic "Source [X]" references
    - ALWAYS include the complete finding/statement after the comma
    - URLs will be provided in the "## Sources and Findings" section
20. Include RAG citations in "Evidence-Based Validation", "Evidence-Based Assessment", and "Evidence-Based Red Flags" sections with complete format
21. Make RAG citations visible and traceable - cite the actual document/study name from the corpus with author, year, and journal - never use numbered source references
22. **SOURCES AND FINDINGS SECTION:** At the end of the report, include a "## Sources and Findings" section that lists all sources cited in the report. Each source must be formatted as an individual array item (bullet point) with complete citation: Author(s) (Year). Title. Journal/Publication. URL (if available). Do NOT use field names or structured format - just list each source as a complete citation string.
23. **AREAS OF CONCERN - EXCLUDE GAPS:** Do NOT include adherence gaps, care gaps, or rehabilitation gaps in the "Areas of Concern" section. Only include clinical concerns related to current patient status and performance metrics (e.g., strength deficits, asymmetry issues, stability problems). Gaps can be mentioned in the "Compliance Adherence Audit" section if they affected performance, but NOT in "Areas of Concern".
24. GAPS IN "Compliance Adherence Audit": ONLY include gaps if BOTH conditions are met:
    a) VALD exercise was performed after the gap
    b) VALD data shows significant downward dip/decline in performance after the gap
25. Do NOT automatically list gaps as problems - gaps are only problems if they caused measurable VALD performance decline
26. TEST RECOMMENDATIONS: ONLY suggest tests that are available in the RAG corpus - query the corpus for available test protocols before making any recommendations
27. Do NOT recommend tests outside the RAG corpus test list - stick to what's actually available and validated in the knowledge base
28. VALD SESSION COUNT: When reporting the number of VALD Assessment Sessions, use ONLY the count of unique session dates. Do NOT include corpus IDs, technical identifiers, or any numbers from system configuration. Report it as a simple number (e.g., "12 sessions" not "6917529027641081856")
29. COMPREHENSIVE VALD ANALYSIS: Analyze ALL VALD tests performed by the patient, not just the primary ones. Include every test in the "Targeted Muscle/Joints" section and "Improvement Data" section. Do not omit tests even if they show minimal change.
30. VALD TEST COMPLETENESS: The "Improvement Data" section MUST include analysis for every VALD test performed. If a test has fewer sessions or less dramatic changes, still include it with full data and clinical interpretation.
31. SECONDARY TESTS: Tests like Single Leg Range of Stability, Squat Assessment, Hip Flexion, and Hip Ad/Ab are equally important as primary tests. Include them in the analysis with the same rigor as Knee Extension/Flexion.
32. **OVERALL CRITICALITY SCORE FOR PATIENT PRIORITIZATION:**
    - Calculate the AVERAGE of all individual concern criticality scores
    - Round to 1 decimal place (e.g., 7.3/10)
    - Assign risk category: LOW RISK (1-3), MODERATE RISK (3.1-6), HIGH RISK (6.1-8), CRITICAL RISK (8.1-10)
    - This score is used to prioritize patients for clinical attention and resource allocation
    - Include the score in the Areas of Concern header: "Areas of Concern: [Risk Category] | [Score]/10"
    - Do NOT include the criticality score formula or calculation explanation in the report

33. **CRITICAL INFORMATION NEEDED - CURRENT PHASE ONLY:**
    - Identify the patient's CURRENT rehabilitation phase (Early ROM/Protection, Early Strengthening, Intermediate Strengthening, Advanced Strengthening, Plyometric/Power, Return-to-Sport Preparation, Return-to-Sport)
    - FIRST: Review the Phase-Based Journey Summary section to identify what exercises and tests the patient is ACTUALLY performing in their current phase
    - THEN: Identify what critical information is MISSING from that specific protocol
    - ONLY list tests that are clinically appropriate, safe, and possible in clinic using ForceFrame/ForceDeck
    - ONLY recommend tests that can be performed with available clinic equipment (ForceFrame/ForceDeck or standard clinic tools)
    - Do NOT recommend tests outside the patient's current phase protocol
    - Do NOT include information about next phase or future phases
    - Do NOT include equipment reference section
    - For each missing test, specify: test name, why it's missing from current protocol, equipment type, and clinical rationale for why this gap impacts decision-making
"""


class ClinicalAuditorAgent:
    def __init__(self):
        # Initialize Google GenAI client
        try:
            self.client = genai.Client(vertexai=True)
            self.model = "gemini-3-pro-preview"
            print("✅ Google GenAI model initialized")
        except Exception as e:
            print(f"❌ Google GenAI initialization failed: {e}")
            print("Make sure GOOGLE_CLOUD_PROJECT and GOOGLE_APPLICATION_CREDENTIALS are set")
            raise

        self.clinical_data = {}
        self.performance_data = {}
        
        # RAG tools configuration
        self.tools = [
            types.Tool(
                retrieval=types.Retrieval(
                    vertex_rag_store=types.VertexRagStore(
                        rag_resources=[
                            types.VertexRagStoreRagResource(
                                rag_corpus="projects/stance-ai/locations/asia-southeast1/ragCorpora/6917529027641081856"
                            )
                        ],
                        similarity_top_k=5,
                    )
                )
            )
        ]

    def load_json_data(self, json_path: str) -> Dict:
        """Load clinical JSON data from organized reports."""
        with open(json_path, 'r') as f:
            self.clinical_data = json.load(f)
        return self.clinical_data

    def load_vald_data(self, vald_json_path: str = None, patient_id: str = None, stance_id: str = None) -> List[Dict]:
        """
        Load VALD performance data from MongoDB or JSON file.
        
        Priority:
        1. If stance_id provided, fetch from MongoDB matches collection
        2. If vald_json_path provided, load from JSON file
        3. Otherwise, return empty list
        
        Args:
            vald_json_path: Path to VALD JSON file (optional, for backward compatibility)
            patient_id: Patient ID for filtering (optional, for backward compatibility)
            stance_id: Stance ID to fetch from MongoDB (preferred method)
        
        Returns:
            List of VALD records
        """
        # Preferred: Fetch from MongoDB using stance_id
        if stance_id:
            try:
                from fetch_and_transform_vald import VALDTransformer
                
                transformer = VALDTransformer()
                vald_data = transformer.get_vald_data_for_patient(stance_id)
                self.performance_data = vald_data
                transformer.close()
                return self.performance_data
            except Exception as e:
                print(f"⚠️  Error fetching VALD data from MongoDB: {e}")
                self.performance_data = []
                return self.performance_data
        
        # Fallback: Load from JSON file
        if vald_json_path and os.path.exists(vald_json_path):
            with open(vald_json_path, 'r') as f:
                all_vald_data = json.load(f)
            
            # If patient_id provided, filter to that patient only
            if patient_id:
                self.performance_data = []
                for patient_record in all_vald_data:
                    if patient_record.get('user_id') == patient_id:
                        self.performance_data = [patient_record]
                        break
                if not self.performance_data:
                    print(f"⚠️  Warning: No VALD data found for patient ID: {patient_id}")
            else:
                # If no patient_id, use all data (backward compatibility)
                self.performance_data = all_vald_data
        else:
            self.performance_data = []
        
        return self.performance_data

    def extract_baseline(self) -> Optional[Dict]:
        """Extract the first assessment record."""
        if isinstance(self.clinical_data, list):
            for record in self.clinical_data:
                if record.get("isFirstAssessment") is True:
                    return record
        elif isinstance(self.clinical_data, dict):
            if self.clinical_data.get("isFirstAssessment") is True:
                return self.clinical_data
        return None

    def calculate_timeline(self) -> Tuple[str, str, float]:
        """Calculate start date, end date, and total weeks using event_start_time."""
        dates = []
        
        if isinstance(self.clinical_data, list):
            for record in self.clinical_data:
                # Use event_start_time if available, otherwise fall back to date
                if "event_start_time" in record:
                    # Convert milliseconds to datetime
                    date_obj = datetime.fromtimestamp(record["event_start_time"] / 1000)
                    date_str = date_obj.strftime("%Y-%m-%d")
                    dates.append(date_str)
                elif "date" in record:
                    dates.append(record["date"])
        elif isinstance(self.clinical_data, dict):
            if "event_start_time" in self.clinical_data:
                date_obj = datetime.fromtimestamp(self.clinical_data["event_start_time"] / 1000)
                date_str = date_obj.strftime("%Y-%m-%d")
                dates.append(date_str)
            elif "date" in self.clinical_data:
                dates.append(self.clinical_data["date"])
        
        if not dates:
            return None, None, 0
        
        dates.sort()
        start_date = dates[0]
        end_date = dates[-1]
        
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d")
            end = datetime.strptime(end_date, "%Y-%m-%d")
            weeks = (end - start).days / 7.0
            return start_date, end_date, weeks
        except:
            return start_date, end_date, 0

    def detect_gaps(self) -> Tuple[List[Tuple[str, str, int]], float]:
        """Detect gaps between sessions using event_start_time."""
        dates = []
        
        if isinstance(self.clinical_data, list):
            for record in self.clinical_data:
                # Use event_start_time if available, otherwise fall back to date
                if "event_start_time" in record:
                    date_obj = datetime.fromtimestamp(record["event_start_time"] / 1000)
                    date_str = date_obj.strftime("%Y-%m-%d")
                    dates.append(date_str)
                elif "date" in record:
                    dates.append(record["date"])
        elif isinstance(self.clinical_data, dict):
            if "event_start_time" in self.clinical_data:
                date_obj = datetime.fromtimestamp(self.clinical_data["event_start_time"] / 1000)
                date_str = date_obj.strftime("%Y-%m-%d")
                dates.append(date_str)
            elif "date" in self.clinical_data:
                dates.append(self.clinical_data["date"])
        
        dates.sort()
        gaps = []
        gap_days = 0
        
        for i in range(len(dates) - 1):
            try:
                current = datetime.strptime(dates[i], "%Y-%m-%d")
                next_date = datetime.strptime(dates[i + 1], "%Y-%m-%d")
                gap = (next_date - current).days
                if gap > 7:  # Only flag gaps > 7 days
                    gaps.append((dates[i], dates[i + 1], gap))
                    gap_days += gap
            except:
                continue
        
        gap_weeks = gap_days / 7.0
        return gaps, gap_weeks

    def calculate_compliance(self, ideal_frequency: float = 2.0) -> Dict:
        """Calculate compliance score using the formula."""
        start_date, end_date, total_weeks = self.calculate_timeline()
        gaps, gap_weeks = self.detect_gaps()
        
        if isinstance(self.clinical_data, list):
            actual_sessions = len(self.clinical_data)
        else:
            actual_sessions = 1
        
        consistency_factor = (total_weeks - gap_weeks) / total_weeks if total_weeks > 0 else 0
        expected_sessions = ideal_frequency * total_weeks
        compliance_score = (actual_sessions / expected_sessions * consistency_factor * 100) if expected_sessions > 0 else 0
        
        return {
            "total_weeks": total_weeks,
            "gap_weeks": gap_weeks,
            "actual_sessions": actual_sessions,
            "expected_sessions": expected_sessions,
            "consistency_factor": consistency_factor,
            "compliance_score": compliance_score,
            "gaps": gaps
        }

    def _extract_vald_session_dates(self, exercise_data: Dict) -> List[str]:
        """Extract session dates from VALD exercise data structure using recursive search."""
        session_dates = []
        
        if not isinstance(exercise_data, dict):
            return session_dates
        
        # Recursively search for x_axis_entities in nested objects
        def extract_dates_recursive(obj):
            dates = []
            if isinstance(obj, dict):
                for key, value in obj.items():
                    if key == 'x_axis_entities' and isinstance(value, list):
                        dates.extend(value)
                    else:
                        dates.extend(extract_dates_recursive(value))
            elif isinstance(obj, list):
                for item in obj:
                    dates.extend(extract_dates_recursive(item))
            return dates
        
        # Check for "data" key (from matches JSON format)
        if "data" in exercise_data:
            data = exercise_data["data"]
            
            # Extract all x_axis_entities dates recursively
            x_axis_dates = extract_dates_recursive(data)
            for date_str in x_axis_dates:
                date_part = date_str[:10] if len(date_str) >= 10 else date_str
                if date_part not in session_dates:
                    session_dates.append(date_part)
            
            # Also try to extract from sessionDates (for backward compatibility)
            if "sessionDates" in data and isinstance(data["sessionDates"], list):
                for date_str in data["sessionDates"]:
                    date_part = date_str[:10] if len(date_str) >= 10 else date_str
                    if date_part not in session_dates:
                        session_dates.append(date_part)
        
        # Check for "sessions" key (legacy format)
        elif "sessions" in exercise_data:
            session_dates = sorted(exercise_data["sessions"].keys())
        
        return sorted(list(set(session_dates)))

    def prepare_audit_context(self, patient_name: str = "", patient_id: str = "", patient_seq_no: str = "") -> str:
        """Prepare comprehensive context for the audit with all VALD session dates."""
        baseline = self.extract_baseline()
        start_date, end_date, total_weeks = self.calculate_timeline()
        gaps, gap_weeks = self.detect_gaps()
        compliance = self.calculate_compliance()
        
        # Extract all VALD session dates for each exercise - condensed format
        vald_summary = {}
        all_vald_dates = set()
        all_metrics = set()  # Track unique metrics
        
        if self.performance_data:
            for patient_record in self.performance_data:
                if isinstance(patient_record, dict) and "exercises" in patient_record:
                    exercises = patient_record.get("exercises", {})
                    for category, exercise_dict in exercises.items():
                        for exercise_name, exercise_data in exercise_dict.items():
                            if isinstance(exercise_data, dict):
                                # Extract session dates using the new method
                                session_dates = self._extract_vald_session_dates(exercise_data)
                                
                                if session_dates:
                                    # Add all dates to the set
                                    for date_str in session_dates:
                                        all_vald_dates.add(date_str)
                                    
                                    vald_summary[exercise_name] = {
                                        "session_count": len(session_dates),
                                        "all_dates": session_dates,
                                        "exercise_type": category
                                    }
        
        total_vald_sessions = len(all_vald_dates)
        total_vald_tests = len(vald_summary)
        total_vald_metrics = len(all_metrics)
        
        # Extract unique consultants from clinical data
        consultants = set()
        if isinstance(self.clinical_data, list):
            for record in self.clinical_data:
                consultant = record.get('consultant')
                specialization = record.get('specialization')
                if consultant:
                    consultants.add((consultant, specialization))
        
        consultants_str = "\n".join([f"  - {c[0]} ({c[1]})" for c in sorted(consultants)]) if consultants else "Not specified"
        
        # Create a list of all VALD tests for explicit reference
        vald_tests_list = "\n".join([f"  - {name} ({data['session_count']} sessions)" for name, data in sorted(vald_summary.items())])
        
        context = f"""
PATIENT INFORMATION:
- Patient Name: {patient_name}
- Patient ID: {patient_id}
- Sequence Number: {patient_seq_no}
- Total VALD Assessment Sessions (Unique Dates): {total_vald_sessions} sessions
- Consultants Involved:
{consultants_str}
- NOTE: Do NOT confuse this with any corpus IDs or technical identifiers

CLINICAL DATA SUMMARY:
- Total Clinical Records: {len(self.clinical_data) if isinstance(self.clinical_data, list) else 1}
- Baseline Record: {json.dumps(baseline, indent=2) if baseline else "Not found"}
- Timeline: {start_date} to {end_date} ({total_weeks:.1f} weeks)
- Total Sessions: {compliance['actual_sessions']}
- Gap Weeks: {gap_weeks:.1f}
- Consistency Factor (C): {compliance['consistency_factor']:.2f}
- Compliance Score: {compliance['compliance_score']:.1f}%
- Significant Gaps: {', '.join([f"Gap {i+1}: {g[0]} to {g[1]} ({g[2]} days)" for i, g in enumerate(gaps)])}

VALD PERFORMANCE DATA (All Sessions - Complete Data):
- Total VALD Sessions (Unique Dates): {total_vald_sessions}
- Total VALD Exercises: {len(vald_summary)}
- VALD Tests Performed (MUST analyze all of these):
{vald_tests_list}

{json.dumps(vald_summary, indent=2)}

CLINICAL DATA (Sample - showing 2 of {len(self.clinical_data)} total records):
{json.dumps(self.clinical_data if isinstance(self.clinical_data, dict) else self.clinical_data[:2], indent=2)}
"""
        return context

    def generate_audit_report(self, output_path: str = "clinical_audit_report.md", patient_name: str = "", patient_id: str = "", patient_seq_no: str = "", enable_eba: bool = True) -> str:
        """Generate the clinical audit report using Google GenAI with RAG, optionally enriched with EBA."""
        context = self.prepare_audit_context(patient_name, patient_id, patient_seq_no)

        full_prompt = f"""{CLINICAL_AUDITOR_PROMPT}

PATIENT DATA TO AUDIT:
{context}

CRITICAL INSTRUCTION: When reporting "VALD Assessment Sessions" in the Patient Summary section, use ONLY the number provided in the PATIENT INFORMATION section above (Total VALD Assessment Sessions). Do NOT include any corpus IDs, technical identifiers, or numbers from the RAG configuration. The session count is a simple number representing unique testing dates.

MANDATORY REQUIREMENT: All sections must be COMPLETE and FULLY POPULATED. Do NOT generate partial sections or truncated content. Every section must contain substantive clinical information. If you cannot complete a section, indicate this explicitly rather than leaving it incomplete.

Please generate a comprehensive clinical audit report following the structured format. Use the RAG corpus to validate exercises, VALD protocols, and clinical guidelines. Ensure all calculations are shown, all linkages are explicit, and the language is clinical and professional."""

        print("   ⏳ Processing with Google GenAI + RAG (this may take a minute)...", end="", flush=True)

        # Generate content with Google GenAI and RAG
        # Retry logic for network errors
        max_retries = 3
        base_delay = 3  # seconds

        for attempt in range(max_retries):
            try:
                contents = [
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=full_prompt)]
                    )
                ]
                
                generate_content_config = types.GenerateContentConfig(
                    temperature=0.4,
                    top_p=0.85,
                    max_output_tokens=65535,
                    safety_settings=[
                        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
                        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
                        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
                        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF")
                    ],
                    tools=self.tools,
                    thinking_config=types.ThinkingConfig(thinking_level="HIGH"),
                )

                # Stream the response
                report_chunks = []
                for chunk in self.client.models.generate_content_stream(
                    model=self.model,
                    contents=contents,
                    config=generate_content_config,
                ):
                    if not chunk.candidates or not chunk.candidates[0].content or not chunk.candidates[0].content.parts:
                        continue
                    report_chunks.append(chunk.text)

                report = "".join(report_chunks)
                
                # Validate report completeness
                if not self._validate_report_completeness(report):
                    print(" ⚠️  Report has incomplete sections")
                    print("   Regenerating with stricter requirements...")
                    # Retry with stricter prompt
                    return self.generate_audit_report(output_path, patient_name, patient_id, patient_seq_no, enable_eba)
                
                print(" ✓")
                break  # Success, exit retry loop

            except Exception as e:
                error_msg = str(e).lower()

                # Check if this is a retryable network error
                retryable_errors = [
                    "connection reset by peer",
                    "connection aborted",
                    "connection refused",
                    "timeout",
                    "network",
                    "connection pool",
                    "rate limit",
                    "quota exceeded"
                ]

                is_retryable = any(retry_error in error_msg for retry_error in retryable_errors)

                if is_retryable and attempt < max_retries - 1:
                    delay = base_delay * (2 ** attempt)  # Exponential backoff
                    print(f"⚠️  Network error generating report (attempt {attempt + 1}/{max_retries}): {e}")
                    print(f"⏳  Retrying in {delay} seconds...")
                    import time
                    time.sleep(delay)
                    continue
                else:
                    print(f" ❌ Error generating report: {e}")
                    if not is_retryable:
                        print("ℹ️   This error is not retryable")
                    return f"Error generating report: {e}"

        # Enrich with EBA if enabled
        if enable_eba:
            try:
                print("🔬 Enriching report with Evidence-Based Assessment (web-grounded)...")
                from eba_agent import EBAAgent
                eba = EBAAgent()
                
                # 2nd Agent: Generate web-based assessment from SAME raw data
                print("\n📊 2nd Agent: Generating independent web-based clinical assessment from raw data...")
                eba.load_clinical_data(self.clinical_data)
                eba.load_vald_data(self.performance_data)
                web_report = eba.generate_web_based_report(
                    patient_name,
                    patient_id
                )
                
                # Save web report as separate file
                if web_report:
                    web_report_path = str(output_path).replace('.md', '_web_assessment.md')
                    with open(web_report_path, 'w') as f:
                        f.write(web_report)
                    print(f"✓ Web-Based Assessment Report generated: {web_report_path}")
                
                # 3rd Agent: Create concise summary of web report
                print("\n📝 3rd Agent: Creating concise summary of web-based assessment...")
                from concise_agent import ConciseAgent
                conciser = ConciseAgent()
                concise_report = conciser.create_concise_summary(web_report, patient_name, patient_id)
                
                # Save concise report
                concise_report_path = str(output_path).replace('.md', '_concise.md')
                conciser.save_concise_report(concise_report, concise_report_path)
                
                print("✓ Multi-agent analysis completed")
            except Exception as e:
                print(f"⚠️  Multi-agent analysis failed: {e}")
                print("   Continuing with base report...")
                import traceback
                traceback.print_exc()

        # Save to markdown file
        with open(output_path, 'w') as f:
            f.write(report)

        print(f"✓ Clinical Audit Report generated: {output_path}")
        return report

    def _validate_report_completeness(self, report: str) -> bool:
        """
        Validate that the report has all required sections and they are not truncated.
        
        Args:
            report: The generated report
            
        Returns:
            True if report is complete, False if incomplete
        """
        required_sections = [
            '## Patient Summary',
            '## Clinical Audit',
            '### Customer Complaint',
            '### Provisional Diagnosis',
            '### Supporting Data',
            '### Journey Summary',
            '### Targeted Muscle/Joints',
            '### Improvement Data',
            '### Areas of Concern',
            '## Critical Information Needed',
            '## Compliance Adherence Audit'
        ]
        
        missing_sections = []
        for section in required_sections:
            if section not in report:
                missing_sections.append(section)
        
        # Check for truncation indicators
        truncation_indicators = [
            report.endswith('[truncated'),
            report.endswith('...'),
            len(report) < 5000,  # Report should be substantial
            report.count('\n') < 50,  # Should have many lines
        ]
        
        is_truncated = any(truncation_indicators)
        
        if missing_sections:
            print(f"\n   Missing sections: {', '.join(missing_sections)}")
        
        if is_truncated:
            print(f"\n   Report appears truncated (length: {len(report)} chars, lines: {report.count(chr(10))})")
        
        return len(missing_sections) == 0 and not is_truncated




if __name__ == "__main__":
    print("This module is meant to be imported by run_audit_by_stance_id.py")
    print("Use: python run_audit_by_stance_id.py <patient_id>")
