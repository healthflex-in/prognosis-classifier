#!/usr/bin/env python3
"""
LangChain-based Clinical Analysis Agent
Analyzes patient rehabilitation data using structured tools and validation.
"""

import os
import json
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from pathlib import Path

import yaml

# Pydantic for validation
from pydantic import BaseModel, Field, validator

# LangChain imports
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.tools import tool
from langchain_core.output_parsers import PydanticOutputParser

# LLM client — provider comes from LLM_PROVIDER (see utils/llm_provider.py)
from utils.llm_provider import build_chat_llm
from utils.llm_text import message_text
from utils.pricing_guard import guard_messages_length

# Load environment
from dotenv import load_dotenv
from pymongo import MongoClient

# Prefer classification/.env, fall back to backend/.env, then system env
llm_env = Path(__file__).parent / ".env"
backend_env = Path(__file__).parent.parent.parent / ".env"  # LLM/classification -> LLM -> backend
if llm_env.exists():
    load_dotenv(llm_env)
elif backend_env.exists():
    load_dotenv(backend_env)
else:
    load_dotenv()

# Import data injectors
import sys
import importlib.util
# Add backend directory to path to find data-injectors
backend_dir = Path(__file__).parent.parent.parent  # LLM/classification -> LLM -> backend
data_injectors_dir = backend_dir / "data-injectors"

# Python can't import modules with hyphens, so we use importlib
def load_module_from_path(module_name, file_path):
    """Load a module from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

# Load the Mongo injector directly from its file
mongo_injector_module = load_module_from_path("mongo_reports_injector", data_injectors_dir / "mongo_reports_injector.py")
MongoReportsInjector = mongo_injector_module.MongoReportsInjector


# ============================================================================
# Pydantic Models for Structured Output
# ============================================================================

class StrengthAsymmetry(BaseModel):
    """Limb Symmetry Index for a specific muscle group."""
    muscle_group: str = Field(description="Name of the muscle group (e.g. Knee Extension)")
    lsi_percentage: Optional[float] = Field(description="Limb Symmetry Index (%)")
    deficit_percentage: Optional[float] = Field(description="Deficit percentage (%)")

class ClinicalAnalysis(BaseModel):
    """Structured clinical analysis output."""
    patient_name: str = Field(description="Patient name")
    baseline_diagnosis: str = Field(description="The original diagnosis from the first assessment")
    surgery_details: str = Field(description="Date and graft type used")
    surgery_date: Optional[str] = Field(description="Surgery date if available")
    first_assessment_date: Optional[str] = Field(description="First assessment date")
    weeks_post_op: Optional[int] = Field(description="Weeks post-surgery at first assessment")

    is_diagnosis_consistent: bool = Field(
        description="True if sensor data matches the clinical notes"
    )
    diagnosis_consistency_reasoning: str = Field(
        description="Explanation of why diagnosis is or isn't consistent"
    )

    findings_summary: str = Field(
        description="Summary of key clinical and biomechanical findings"
    )

    strength_asymmetries: List[StrengthAsymmetry] = Field(
        description="List of calculated strength asymmetries",
        default_factory=list
    )

    differential_complications: List[str] = Field(
        description="List of likely complications based on timeline",
        default_factory=list
    )

    data_gaps: List[str] = Field(
        description="Information missing from the report that would improve confidence",
        default_factory=list
    )

    clinical_priority: str = Field(
        description="Primary clinical priority for next rehab phase"
    )


# ============================================================================
# Custom Tools
# ============================================================================

@tool
def calculate_limb_symmetry_index(left_val: float, right_val: float) -> Dict[str, Any]:
    """
    Calculates the Limb Symmetry Index (LSI) and deficit percentage between two limbs.
    
    Args:
        left_val: Value for left/involved limb
        right_val: Value for right/uninvolved limb
    
    Returns:
        Dictionary with LSI percentage and deficit percentage
    """
    if left_val == 0:
        return {
            "lsi_percentage": None,
            "deficit_percentage": None,
            "error": "Cannot calculate: left value is zero"
        }
    
    lsi = (right_val / left_val) * 100
    deficit = 100 - lsi
    
    return {
        "lsi_percentage": round(lsi, 2),
        "deficit_percentage": round(deficit, 2),
        "interpretation": f"Right limb is {deficit:.1f}% weaker than left" if deficit > 0 else f"Right limb is {abs(deficit):.1f}% stronger than left"
    }


@tool
def get_post_op_week(surgery_date_str: str, assessment_date_str: str) -> Dict[str, Any]:
    """
    Calculates how many weeks post-op the patient is at the assessment date.
    
    Args:
        surgery_date_str: Surgery date in YYYY-MM-DD format
        assessment_date_str: Assessment date in YYYY-MM-DD format
    
    Returns:
        Dictionary with weeks post-op and timeline phase
    """
    try:
        surgery_date = datetime.strptime(surgery_date_str, '%Y-%m-%d')
        assessment_date = datetime.strptime(assessment_date_str, '%Y-%m-%d')
        
        days_diff = (assessment_date - surgery_date).days
        weeks_diff = days_diff / 7.0
        
        # Determine timeline phase
        if weeks_diff < 6:
            phase = "Early Phase (0-6 weeks): Focus on swelling and ROM"
        elif weeks_diff < 12:
            phase = "Mid Phase (6-12 weeks): Focus on muscle hypertrophy and basic strength"
        elif weeks_diff < 24:
            phase = "Advanced Phase (3-6 months): Focus on power and return-to-run"
        else:
            phase = "Return-to-Sport Phase (6+ months): Focus on sport-specific training"
        
        return {
            "weeks_post_op": round(weeks_diff, 1),
            "days_post_op": days_diff,
            "timeline_phase": phase
        }
    except ValueError as e:
        return {
            "error": f"Invalid date format: {e}",
            "weeks_post_op": None
        }


@tool
def extract_vald_strength_data(vald_data: Dict, exercise_name: str, session_date: str) -> Dict[str, Any]:
    """
    Extracts strength values from VALD data for a specific exercise and session date.
    
    Args:
        vald_data: VALD exercise data dictionary
        exercise_name: Name of the exercise (e.g., 'kneeExtensionData_knee_extension___knee_extension_seated_90')
        session_date: Target session date in YYYY-MM-DD format
    
    Returns:
        Dictionary with left and right strength values
    """
    try:
        exercises = vald_data.get('exercises', {})
        
        # Search in all categories
        for category in ['forceFrame', 'forceDeck', 'dynamo']:
            if exercise_name in exercises.get(category, {}):
                exercise_data = exercises[category][exercise_name]
                data = exercise_data.get('data', {})
                
                # Extract values for the specific session date
                # Look for x_axis_entities matching the date
                def find_session_values(data_dict, target_date):
                    """Recursively find values for target date."""
                    if isinstance(data_dict, dict):
                        x_axis = data_dict.get('x_axis_entities', [])
                        y_left = data_dict.get('y_axis_entity_left', [])
                        y_right = data_dict.get('y_axis_entity_right', [])
                        
                        if isinstance(x_axis, list) and len(x_axis) > 0:
                            for i, date_str in enumerate(x_axis):
                                if target_date in str(date_str):
                                    left_val = y_left[i] if i < len(y_left) else None
                                    right_val = y_right[i] if i < len(y_right) else None
                                    return {"left": left_val, "right": right_val}
                        
                        # Recursive search
                        for value in data_dict.values():
                            result = find_session_values(value, target_date)
                            if result:
                                return result
                    elif isinstance(data_dict, list):
                        for item in data_dict:
                            result = find_session_values(item, target_date)
                            if result:
                                return result
                    return None
                
                values = find_session_values(data, session_date)
                if values:
                    return {
                        "exercise_name": exercise_name,
                        "session_date": session_date,
                        "left_value": values.get('left'),
                        "right_value": values.get('right'),
                        "found": True
                    }
        
        return {
            "exercise_name": exercise_name,
            "session_date": session_date,
            "found": False,
            "error": "Exercise or session date not found"
        }
    except Exception as e:
        return {
            "error": str(e),
            "found": False
        }


# ============================================================================
# LangChain Agent Setup
# ============================================================================

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
    # This is a simple version; it might be risky for strings containing these chars
    json_str = re.sub(r'(?m)^\s*//.*$', '', json_str)
    json_str = re.sub(r'(?m)^\s*#.*$', '', json_str)

    # 4. Remove trailing commas before } or ]
    json_str = re.sub(r',\s*(\}|\])', r'\1', json_str)

    return json_str.strip()

class ClinicalAnalysisAgent:
    """LangChain-based clinical analysis agent with tool calling."""
    
    def __init__(self):
        """Initialize the clinical analysis agent."""
        self.model_name = os.getenv("CLINICAL_MODEL", "claude-haiku-5-5")
        self.llm = build_chat_llm(
            model=self.model_name,
            temperature=1,
            max_tokens=8192,
        )
        print(f"✅ LLM client initialized (model={self.model_name})")

        # These tool functions were defined for potential tool-calling use, but
        # were never actually wired into the live generation call below — only
        # Google Search was ever passed as a live tool (see analyze_patient's
        # migration note). Left in place as-is; not deleted, not currently invoked.
        self.tools = [
            calculate_limb_symmetry_index,
            get_post_op_week,
            extract_vald_strength_data,
        ]

        # Create output parser and prompt template
        self.output_parser = PydanticOutputParser(pydantic_object=ClinicalAnalysis)
        self.prompt = self._create_prompt()

    # ------------------------------------------------------------------
    # Persistence helpers
    # ------------------------------------------------------------------

    def _get_mongo_prognosis_collection(self):
        """
        Get a handle to the MongoDB 'prognosis' collection in the stance-dashboard DB.

        Uses:
        - MONGO_URI or MONGODB_URI for connection string
        - MONGO_DB (defaults to 'stance-dashboard') for DB name
        """
        mongo_uri = os.getenv("MONGO_URI") or os.getenv("MONGODB_URI") or "mongodb://localhost:27017/"
        db_name = os.getenv("MONGO_DB", "stance-dashboard")

        client = MongoClient(
            mongo_uri,
            tlsAllowInvalidCertificates=True,
            tlsAllowInvalidHostnames=True,
            serverSelectionTimeoutMS=30000,  # 30 seconds to find a server
            connectTimeoutMS=30000,  # 30 seconds to connect
            socketTimeoutMS=60000,  # 60 seconds for socket operations
            retryWrites=True,
            retryReads=True,
            maxPoolSize=50,
            minPoolSize=10,
        )
        db = client[db_name]
        return client, db["prognosis"]

    def _create_prompt(self) -> ChatPromptTemplate:
        """Create the master prompt template from YAML/JSON config file."""
        # Prefer YAML prompt file; fall back to JSON for backward compatibility
        prompt_file = Path(__file__).parent / "clinical_prompt.yml"
        if not prompt_file.exists():
            prompt_file = Path(__file__).parent.parent / "clinical_prompt.yml"
        if not prompt_file.exists():
            prompt_file = Path(__file__).parent / "clinical_prompt.json"
        if not prompt_file.exists():
            prompt_file = Path(__file__).parent.parent / "clinical_prompt.json"

        try:
            with open(prompt_file, "r") as f:
                if prompt_file.suffix in [".yml", ".yaml"]:
                    prompt_config = yaml.safe_load(f)
                else:
                    prompt_config = json.load(f)

            system_message = prompt_config.get("system_message", "")
            human_template = prompt_config.get("human_message_template", "")

            if not system_message or not human_template:
                raise ValueError("Prompt config file is missing required fields")

            prompt = ChatPromptTemplate.from_messages(
                [
                    ("system", system_message),
                    ("human", human_template),
                ]
            )

            print(f"✅ Loaded prompt from: {prompt_file}")
            return prompt

        except FileNotFoundError:
            print(f"⚠️  Prompt file not found: {prompt_file}")
            print("   Using default prompt...")
            return self._create_default_prompt()
        except (json.JSONDecodeError, yaml.YAMLError) as e:
            print(f"⚠️  Error parsing prompt config: {e}")
            print("   Using default prompt...")
            return self._create_default_prompt()
        except Exception as e:
            print(f"⚠️  Error loading prompt: {e}")
            print("   Using default prompt...")
            return self._create_default_prompt()
    
    def _create_default_prompt(self) -> ChatPromptTemplate:
        """Create default prompt if JSON file is not available."""
        system_message = """You are a Senior Sports Physiotherapist and Data Analyst. 
Your task is to analyze clinical rehabilitation data and validate diagnoses using objective sensor data.

Follow this step-by-step workflow:

**Step 1: Baseline Extraction**
- Identify the 'First Assessment' report
- Extract: primary diagnosis, surgical history (date and graft type), chief complaints
- Note the first assessment date

**Step 2: Sensor Data Integration**
- Cross-reference the first assessment date with the nearest VALD/ForceFrame session
- Use `extract_vald_strength_data` to get strength values for key exercises

**Step 3: Diagnosis Validation**
- Compare the 'Provisional Diagnosis' with objective strength data
- State whether they match
- Provide reasoning

**Step 4: Timeline Analysis**
- Use `get_post_op_week` to calculate weeks post-surgery
- Apply timeline rules:
  * 0-6 weeks: Focus on swelling and ROM
  * 6-12 weeks: Focus on muscle hypertrophy and basic strength
  * 3-6 months: Focus on power and return-to-run
  * 6+ months: Focus on sport-specific training

**Step 5: Differential Complications**
- List 3-5 likely complications based on timeline (e.g., Arthrofibrosis, Graft failure, PFPS)
- Prioritize the most critical clinical concern

**Step 6: Output Format**
Provide structured output with:
- Diagnosis consistency assessment
- Differential complications
- Clinical priority

IMPORTANT:
- Use tools for all calculations - do not do math manually
- Be specific with numbers and percentages
- Focus on actionable clinical insights
- Flag any data inconsistencies"""
        
        human_template = """Analyze the clinical data for patient: {patient_name}

**Clinical Data (First Assessment):**
{clinical_data}

**VALD Performance Data:**
{vald_data}

**Instructions:**
1. Extract baseline diagnosis and surgery details
2. Extract and analyze VALD strength data for the first assessment date
3. Validate diagnosis consistency
4. Calculate weeks post-op
5. Identify differential complications and clinical priority

{format_instructions}"""
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", system_message),
            ("human", human_template)
        ])
        
        return prompt
    
    def load_patient_data(self, patient_id: str) -> Dict[str, Any]:
        """
        Load patient data using data injectors.
        Note: patient_id is the same as stance_id for both MongoDB and VALD.
        
        Args:
            patient_id: Patient/Stance ID (same for both MongoDB and VALD)
        
        Returns:
            Dictionary with clinical_data and vald_data
        """
        all_data = {
            "clinical_data": None,
            "vald_data": None,
            "patient_name": None
        }
        
        # Load MongoDB reports (FirstAssessment + matching VALD)
        # patient_id is used as stance_id since they're the same
        print(f"📋 Loading clinical reports for patient: {patient_id}")
        mongo_injector = MongoReportsInjector()
        try:
            mongo_docs = mongo_injector.load_data(patient_id, stance_id=patient_id, max_days_range=7)
            
            # Extract FirstAssessment
            first_assessment_doc = next(
                (doc for doc in mongo_docs if doc.metadata.get('record_type') == 'first_assessment'),
                None
            )
            
            if first_assessment_doc:
                all_data["clinical_data"] = json.loads(first_assessment_doc.page_content)
                all_data["patient_name"] = first_assessment_doc.metadata.get('patient_name', 'Unknown')
            
            # Extract matching VALD data
            vald_doc = next(
                (doc for doc in mongo_docs if doc.metadata.get('record_type') == 'matching_vald_tests'),
                None
            )
            
            if vald_doc:
                vald_content = json.loads(vald_doc.page_content)
                all_data["vald_data"] = vald_content.get('matching_vald_tests', [])
            
            mongo_injector.close()
        except Exception as e:
            print(f"⚠️  Error loading MongoDB data: {e}")
            mongo_injector.close()
        
        return all_data
    
    def analyze_patient(self, patient_id: str) -> ClinicalAnalysis:
        """
        Perform complete clinical analysis for a patient.
        Note: patient_id is used for both MongoDB and VALD (they share the same ID).
        
        Args:
            patient_id: Patient/Stance ID (same for both data sources)
        
        Returns:
            ClinicalAnalysis object with structured results
        """
        # Load data (patient_id is the same as stance_id)
        data = self.load_patient_data(patient_id)
        
        if not data["clinical_data"]:
            raise ValueError(f"No clinical data found for patient: {patient_id}")
        
        # Prepare prompt
        format_instructions = self.output_parser.get_format_instructions()
        
        # Format data for prompt
        clinical_json = json.dumps(data["clinical_data"], indent=2, default=str)
        vald_json = json.dumps(data["vald_data"], indent=2, default=str) if data["vald_data"] else "No VALD data available"
        
        # Format prompt
        formatted_messages = self.prompt.format_messages(
            patient_name=data["patient_name"] or patient_id,
            clinical_data=clinical_json,
            vald_data=vald_json,
            format_instructions=format_instructions
        )
        
        system_content = formatted_messages[0].content
        human_content = formatted_messages[1].content

        # ------------------------------------------------------------------
        # MIGRATION NOTE (Gemini -> Claude):
        # This call used to run on Vertex AI with a live `google_search` tool
        # enabled for external grounding (clinical guidelines/textbooks/etc —
        # see clinical_prompt.yml, which was written assuming that tool exists).
        # Claude has no equivalent built-in search-grounding tool, so it is
        # dropped here rather than replaced — the same call made for STT in
        # customer-agent. clinical_prompt.yml's wording was updated to match,
        # so the model is no longer told to rely on a search tool it can't use.
        #
        # Historical config, kept here for reference only (no longer active):
        #   safety_settings=[... HATE_SPEECH/DANGEROUS_CONTENT/SEXUALLY_EXPLICIT/
        #                     HARASSMENT all "OFF" ...]   — no direct Claude equivalent
        #   tools=[types.Tool(google_search=types.GoogleSearch())]   — dropped, see above
        #   thinking_config=types.ThinkingConfig(thinking_budget=-1)  — Claude has no
        #       "unlimited" option; thinking is left off by default (see llm_provider.py)
        #       and can be enabled later via a CLINICAL_THINKING_BUDGET env var if needed.
        #
        # The multi-turn tool-execution loop that used to live here is also removed:
        # it only ever triggered on a `function_call` part, and the only tool that was
        # actually configured (Google Search) is handled server-side by Gemini and never
        # surfaces as a function_call — so in production this loop always ran exactly one
        # iteration. Removing it changes no observable behaviour.
        # ------------------------------------------------------------------
        print("🔬 Performing clinical analysis...")
        print("   ⏳ Generating analysis...")

        messages = [
            SystemMessage(content=system_content),
            HumanMessage(content=human_content),
        ]
        # This is the one agent whose prompt includes raw JSON dumps of clinical
        # + VALD data rather than curated summary fields, so it's the most likely
        # of the five to ever grow large — guard before sending.
        guard_messages_length(self.model_name, messages)
        response = self.llm.invoke(messages)
        full_response = message_text(response.content)
        
        # Parse JSON from response and validate with Pydantic
        try:
            # Use utility to clean and extract JSON
            json_str = clean_json_response(full_response)
            analysis_dict = json.loads(json_str)

            # Validate with Pydantic
            analysis = ClinicalAnalysis(**analysis_dict)
            print("✅ Analysis complete and validated")

            # Persist analysis to MongoDB (stance-dashboard.prognosis)
            try:
                client, collection = self._get_mongo_prognosis_collection()
                now = datetime.utcnow()
                doc = analysis.model_dump(exclude_none=False, mode="json")
                
                # Convert patient_id to ObjectId if it's a valid ObjectId string
                from bson import ObjectId
                try:
                    # Try to convert to ObjectId if it looks like one (24 hex chars)
                    if isinstance(patient_id, str) and len(patient_id) == 24:
                        patient_id_obj = ObjectId(patient_id)
                    elif isinstance(patient_id, ObjectId):
                        patient_id_obj = patient_id
                    else:
                        # If not a valid ObjectId format, try to convert anyway
                        patient_id_obj = ObjectId(patient_id)
                    
                    # Store as ObjectId in document
                    doc["patient_id"] = patient_id_obj
                    patient_id_for_query = patient_id_obj
                except (ValueError, TypeError):
                    # If conversion fails, keep as string but log warning
                    print(f"⚠️  Warning: patient_id '{patient_id}' is not a valid ObjectId, storing as string")
                    patient_id_for_query = patient_id
                
                doc["updated_at"] = now
                # Upsert by patient_id so latest analysis is always available
                collection.update_one(
                    {"patient_id": patient_id_for_query},
                    {"$set": doc, "$setOnInsert": {"created_at": now}},
                    upsert=True,
                )
                client.close()
                print(f"💾 Clinical analysis saved to MongoDB collection 'prognosis' for patient {patient_id}")
            except Exception as mongo_err:
                print(f"⚠️  Failed to save clinical analysis to MongoDB: {mongo_err}")

            return analysis
            
        except json.JSONDecodeError as e:
            print(f"⚠️  Could not parse JSON from response: {e}")
            print(f"Response preview: {full_response[:500]}")
            # Return a basic analysis with the raw response
            return ClinicalAnalysis(
                patient_name=data["patient_name"] or patient_id,
                baseline_diagnosis="Analysis incomplete - see raw response",
                surgery_details="N/A",
                is_diagnosis_consistent=False,
                diagnosis_consistency_reasoning=f"Could not parse structured output: {str(e)}",
                clinical_priority="Data parsing error",
                findings_summary=full_response[:1000],
                data_gaps=["Could not parse analysis output"]
            )
        except Exception as e:
            print(f"❌ Error validating analysis: {e}")
            raise
    
    def _execute_tool_call(self, function_call) -> Dict[str, Any]:
        """Execute a tool call and return the result."""
        try:
            function_name = function_call.name if hasattr(function_call, 'name') else str(function_call)
            
            # Parse arguments
            if hasattr(function_call, 'args'):
                if isinstance(function_call.args, str):
                    args = json.loads(function_call.args)
                elif isinstance(function_call.args, dict):
                    args = function_call.args
                else:
                    args = {}
            else:
                args = {}
            
            print(f"      🧩 Executing tool '{function_name}' with args: {args}")

            # Execute appropriate tool
            if function_name == "calculate_limb_symmetry_index":
                left_val = args.get('left_val', 0)
                right_val = args.get('right_val', 0)
                result = calculate_limb_symmetry_index.invoke({
                    "left_val": left_val,
                    "right_val": right_val
                })
            elif function_name == "get_post_op_week":
                surgery_date = args.get('surgery_date_str', '')
                assessment_date = args.get('assessment_date_str', '')
                result = get_post_op_week.invoke({
                    "surgery_date_str": surgery_date,
                    "assessment_date_str": assessment_date
                })
            elif function_name == "extract_vald_strength_data":
                vald_data = args.get('vald_data', {})
                exercise_name = args.get('exercise_name', '')
                session_date = args.get('session_date', '')
                result = extract_vald_strength_data.invoke({
                    "vald_data": vald_data,
                    "exercise_name": exercise_name,
                    "session_date": session_date
                })
            else:
                result = {"error": f"Unknown tool: {function_name}"}
            
            print(f"      ✅ Tool '{function_name}' completed")
            return result
        except Exception as e:
            import traceback
            traceback.print_exc()
            return {"error": str(e), "function_call": str(function_call)}


# ============================================================================
# Main Execution
# ============================================================================

if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python clinical_agent.py <patient_id>")
        print("Note: patient_id is used for both MongoDB and VALD (they share the same ID)")
        sys.exit(1)
    
    patient_id = sys.argv[1]
    
    print("=" * 80)
    print("Clinical Analysis Agent")
    print("=" * 80)
    print()
    
    try:
        agent = ClinicalAnalysisAgent()
        analysis = agent.analyze_patient(patient_id)
        
        print("\n" + "=" * 80)
        print("Analysis Results")
        print("=" * 80)
        print(f"\nPatient: {analysis.patient_name}")
        print(f"Diagnosis: {analysis.baseline_diagnosis}")
        print(f"Surgery: {analysis.surgery_details}")
        print(f"Weeks Post-Op: {analysis.weeks_post_op}")
        print(f"\nDiagnosis Consistent: {analysis.is_diagnosis_consistent}")
        print(f"Reasoning: {analysis.diagnosis_consistency_reasoning}")
        print(f"\nClinical Priority: {analysis.clinical_priority}")
        print(f"\nFindings Summary:\n{analysis.findings_summary}")
        
        if analysis.strength_asymmetries:
            print(f"\nStrength Asymmetries:")
            for asym in analysis.strength_asymmetries:
                print(f"  - {asym.muscle_group}: LSI {asym.lsi_percentage}%, Deficit {asym.deficit_percentage}%")
        
        if analysis.differential_complications:
            print(f"\nDifferential Complications:")
            for comp in analysis.differential_complications:
                print(f"  - {comp}")
        
        if analysis.data_gaps:
            print(f"\nData Gaps:")
            for gap in analysis.data_gaps:
                print(f"  - {gap}")
        
        # Save to JSON
        output_file = f"analysis_{patient_id}.json"
        with open(output_file, 'w') as f:
            f.write(analysis.model_dump_json(indent=2))
        print(f"\n💾 Full analysis saved to: {output_file}")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
