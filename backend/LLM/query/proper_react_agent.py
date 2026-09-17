#!/usr/bin/env python3
"""
Proper ReAct Query Widget Agent
Uses reasoning and action pattern with tools to understand user queries and generate appropriate widgets.
"""

from __future__ import annotations

import os
import json
import requests
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal

from pydantic import BaseModel, Field
from dotenv import load_dotenv
from LLM.query.db_schema_discovery import get_database_schema

# LangChain Google Vertex AI
from langchain_google_vertexai import ChatVertexAI
from langchain_core.messages import HumanMessage, SystemMessage
import warnings

# Suppress the deprecation warning for ChatVertexAI
warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_google_vertexai")

# Load environment
backend_env = Path(__file__).parent.parent.parent / ".env"  # query -> LLM -> backend
if backend_env.exists():
    load_dotenv(backend_env)
else:
    load_dotenv()

# ============================================================================
# Pydantic models for structured output
# ============================================================================

class QueryAnalysis(BaseModel):
    """Analysis of the user query to understand intent."""
    
    intent: Literal["show_patients", "show_distribution", "show_comparison", "show_correlation"] = Field(
        description="Primary intent: show_patients (list people), show_distribution (stats/charts), show_comparison (compare groups), show_correlation (relationships)"
    )
    
    entities: List[str] = Field(
        description="Key entities mentioned: diagnosis, pain_interference, joint, occupation, etc."
    )
    
    filters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Specific filters to apply based on conditions mentioned. Can be string or list of strings for multiple values."
    )
    
    chart_type: Optional[str] = Field(
        default=None,
        description="Specific chart type requested: bar, pie, scatter, table, etc."
    )
    
    reasoning: str = Field(
        description="Explanation of why this interpretation was chosen"
    )


class WidgetSpec(BaseModel):
    """Specification for a dashboard widget."""

    id: str = Field(description="Client-unique widget ID")
    type: Literal[
        "bar", "pie", "stacked-bar", "grouped-bar", "scatter", "lollipop", "histogram", "heatmap", "patient-table"
    ] = Field(description="Widget visualization type.")
    title: str = Field(description="Human-readable widget title")
    endpoint: str = Field(description="REST endpoint to call")
    filters: Optional[Dict[str, Any]] = Field(default=None, description="Query parameters/filters - can be string or list")
    refresh_interval: Optional[int] = Field(default=60, description="Refresh interval in seconds")
    minW: Optional[int] = Field(default=None, description="Minimum width")
    minH: Optional[int] = Field(default=None, description="Minimum height")


class ReActQueryResponse(BaseModel):
    """Complete response with analysis and widgets."""
    
    analysis: QueryAnalysis = Field(description="Analysis of the user query")
    widgets: List[WidgetSpec] = Field(description="Generated widgets")


# Resolve forward references for Pydantic v2 when using __future__.annotations
QueryAnalysis.model_rebuild()
WidgetSpec.model_rebuild()
ReActQueryResponse.model_rebuild()


class ProperReActQueryAgent:
    """
    ReAct agent that reasons about queries and uses tools to generate widgets.
    """

    def __init__(self) -> None:
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
            max_output_tokens=2048,
        )
        
        print(f"🤖 Using ReAct reasoning agent with model: gemini-2.5-flash")
        
        # Discover database schema dynamically
        try:
            self.db_info = get_database_schema()
            if self.db_info["status"] != "success" or self.db_info["schema"].get("total_patients", 0) == 0:
                print(f"⚠️ Warning: Database appears empty, using fallback schema")
                self.db_info = self._get_fallback_schema()
        except Exception as e:
            print(f"⚠️ Warning: Could not load database schema: {e}, using fallback")
            self.db_info = self._get_fallback_schema()
    
    def _get_fallback_schema(self) -> Dict[str, Any]:
        """Fallback schema when database is empty or unavailable."""
        return {
            "status": "success",
            "schema": {
                "total_patients": 0,
                "filter_parameters": {
                    "pain_interference": {
                        "type": "categorical",
                        "values": [
                            "No / minimal interference",
                            "Activity-only interference", 
                            "Work / daily function interference",
                            "Multi-domain interference",
                            "Forced entry (surgery or trauma)",
                            "Unclear"
                        ]
                    },
                    "canonical_diagnosis": {"type": "categorical", "values": []},
                    "primary_joint": {"type": "categorical", "values": []},
                    "functional_region": {"type": "categorical", "values": ["Upper limb", "Lower limb", "Spine", "Posterior chain", "Multi-joint", "Unclear"]},
                    "occupation_category": {"type": "categorical", "values": ["Sedentary / desk-based", "Manual / physical", "Student", "Athlete", "Retired", "Unclear"]},
                    "activity_profile": {"type": "categorical", "values": ["Sedentary / minimally active", "Recreationally active", "Structured fitness", "Competitive / elite sport", "Unclear"]},
                    "clinical_stage": {"type": "categorical", "values": ["Acute", "Subacute", "Chronic", "Recurrent", "Pre-hab / pre-surgical", "Post-operative", "Unclear"]},
                    "intent_category": {"type": "categorical", "values": ["Pain relief only", "Return to daily function", "Return to activity / fitness", "Return to sport", "Performance / optimisation", "Post-surgical recovery", "Unclear"]}
                }
            }
        }

    def _check_patient_count(self, filters: Dict[str, str]) -> str:
        """Check how many patients match specific criteria."""
        try:
            # Build API URL
            base_url = "http://localhost:8013/api/patients"
            params = []
            for key, value in filters.items():
                params.append(f"{key}={value}")
            
            url = f"{base_url}?{'&'.join(params)}" if params else base_url
            
            # Make API call with longer timeout
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                patients = response.json()
                return f"Found {len(patients)} patients matching criteria: {filters}"
            else:
                return f"Error checking patient count: {response.status_code}"
                
        except Exception as e:
            return f"Error checking patient count: {str(e)}"
    
    def _test_endpoint(self, endpoint: str, params: Dict[str, str]) -> str:
        """Test an API endpoint with specific parameters."""
        try:
            base_url = f"http://localhost:8013{endpoint}"
            param_list = []
            for key, value in params.items():
                param_list.append(f"{key}={value}")
            
            url = f"{base_url}?{'&'.join(param_list)}" if param_list else base_url
            
            response = requests.get(url, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if isinstance(data, list):
                    return f"Endpoint returned {len(data)} items. Sample: {data[:2] if data else 'No data'}"
                else:
                    return f"Endpoint returned: {data}"
            else:
                return f"Endpoint error: {response.status_code} - {response.text}"
                
        except Exception as e:
            return f"Error testing endpoint: {str(e)}"

    def run(self, query: str) -> ReActQueryResponse:
        """Run the ReAct reasoning process to analyze query and generate widgets."""
        try:
            # Step 1: Initial reasoning about the query
            reasoning_prompt = f"""
You are a clinical dashboard widget generator. Use ReAct reasoning to understand this query and generate appropriate widgets.

Query: "{query}"

Think step by step:

1. UNDERSTAND THE INTENT:
   - Does the user want individual patient records (show_patients) or statistics/charts (show_distribution)?
   - Look for keywords: "chart", "graph", "pie", "bar" = show_distribution
   - Look for keywords: "patients", "people", "list" without chart types = show_patients

2. EXTRACT ENTITIES AND FILTERS:
   - What diagnoses are mentioned? (knee pain, shoulder pain, hip pain, etc.)
   - What clinical stages? (acute, subacute, chronic)
   - What other filters? (joint, region, etc.)

3. DETERMINE CHART TYPE:
   - What visualization type is requested? (bar, pie, table)

Let me reason through this query:

Thought: I need to analyze what the user is asking for.
"""
            
            # Get initial reasoning
            messages = [
                SystemMessage(content="You are a clinical dashboard expert that uses step-by-step reasoning."),
                HumanMessage(content=reasoning_prompt)
            ]
            
            reasoning_response = self.llm.invoke(messages)
            reasoning_text = reasoning_response.content
            
            print(f"🧠 Initial Reasoning:\n{reasoning_text}")
            
            # Step 2: Extract structured information from reasoning
            query_lower = query.lower()
            
            # Determine intent
            if any(chart in query_lower for chart in ["chart", "graph", "pie", "bar", "distribution", "breakdown"]):
                intent = "show_distribution"
                chart_type = "pie" if "pie" in query_lower else "bar"
            else:
                intent = "show_patients"
                chart_type = "table"
            
            # Extract entities and filters
            entities = []
            filters = {}
            
            if any(pain in query_lower for pain in ["knee pain", "shoulder pain", "hip pain"]):
                entities.append("diagnosis")
                diagnoses = []
                if "knee pain" in query_lower or "knee" in query_lower:
                    diagnoses.append("knee pain")
                if "shoulder pain" in query_lower or "shoulder" in query_lower:
                    diagnoses.append("shoulder pain")
                if "hip pain" in query_lower or "hip" in query_lower:
                    diagnoses.append("hip pain")
                if diagnoses:
                    filters["canonical_diagnosis"] = ",".join(diagnoses)
            
            if any(stage in query_lower for stage in ["acute", "subacute", "chronic"]):
                entities.append("clinical_stage")
                stages = []
                if "acute" in query_lower and "subacute" not in query_lower:
                    stages.append("Acute")
                if "subacute" in query_lower:
                    stages.append("Subacute")
                if "chronic" in query_lower:
                    stages.append("Chronic")
                if stages:
                    filters["clinical_stage"] = ",".join(stages)
            
            # Step 3: Use tools to validate and refine
            if filters:
                patient_count = self._check_patient_count(filters)
                print(f"🔍 Patient Count Check: {patient_count}")
            
            # Step 4: Test the chosen endpoint
            if intent == "show_distribution" and filters:
                endpoint_test = self._test_endpoint("/api/stats/diagnosis", filters)
                print(f"🔧 Endpoint Test: {endpoint_test}")
            
            # Step 5: Generate final analysis and widget
            analysis = QueryAnalysis(
                intent=intent,
                entities=entities or ["unknown"],
                filters=filters,
                chart_type=chart_type,
                reasoning=f"ReAct reasoning: {intent} intent detected with entities {entities} and filters {filters}"
            )
            
            # Generate widget based on analysis
            if intent == "show_patients":
                widget = WidgetSpec(
                    id="widget-react-001",
                    type="patient-table",
                    title="Filtered Patients",
                    endpoint="/api/patients",
                    filters=filters,
                    refresh_interval=60,
                    minW=4,
                    minH=4
                )
            else:
                # Choose best endpoint for distribution
                if "clinical_stage" in filters and "canonical_diagnosis" in filters:
                    endpoint = "/api/stats/diagnosis"
                    title = f"Diagnosis Distribution"
                    if "clinical_stage" in filters:
                        stages = filters["clinical_stage"].replace(",", " & ")
                        title += f" ({stages} Patients)"
                elif "clinical_stage" in filters:
                    endpoint = "/api/stats/clinical-stage"
                    title = "Clinical Stage Distribution"
                else:
                    endpoint = "/api/stats/diagnosis"
                    title = "Diagnosis Distribution"
                
                widget = WidgetSpec(
                    id="widget-react-001",
                    type=chart_type,
                    title=title,
                    endpoint=endpoint,
                    filters=filters,
                    refresh_interval=60,
                    minW=5 if chart_type == "pie" else 4,
                    minH=5 if chart_type == "pie" else 4
                )
            
            print(f"✅ Final Analysis: {analysis.intent} - {analysis.reasoning}")
            
            return ReActQueryResponse(
                analysis=analysis,
                widgets=[widget]
            )
            
        except Exception as e:
            print(f"⚠️ ReAct agent error: {e}")
            # Fallback to simple analysis
            return self._fallback_response(query)
    
    def _fallback_response(self, query: str) -> ReActQueryResponse:
        """Fallback response when ReAct agent fails."""
        query_lower = query.lower()
        
        # Simple fallback analysis
        if any(chart in query_lower for chart in ["chart", "graph", "pie", "bar"]):
            intent = "show_distribution"
            chart_type = "pie" if "pie" in query_lower else "bar"
        else:
            intent = "show_patients"
            chart_type = "table"
        
        analysis = QueryAnalysis(
            intent=intent,
            entities=["unknown"],
            filters={},
            chart_type=chart_type,
            reasoning="Fallback analysis due to ReAct agent error"
        )
        
        widget = WidgetSpec(
            id="widget-fallback-001",
            type="patient-table" if intent == "show_patients" else chart_type,
            title="Dashboard Widget",
            endpoint="/api/patients" if intent == "show_patients" else "/api/stats/diagnosis",
            filters={},
            refresh_interval=60,
            minW=4,
            minH=4
        )
        
        return ReActQueryResponse(
            analysis=analysis,
            widgets=[widget]
        )


__all__ = ["ProperReActQueryAgent", "QueryAnalysis", "WidgetSpec", "ReActQueryResponse"]