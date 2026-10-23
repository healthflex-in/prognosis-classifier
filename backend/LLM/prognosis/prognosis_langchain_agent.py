#!/usr/bin/env python3
"""
Compatibility wrapper so the new /api/prognosis/langchain endpoint can
reuse the existing ClinicalAnalysisAgent without importing unsupported
LangChain helpers in this environment.

This function simply delegates to ClinicalAnalysisAgent.analyze_patient,
which already:
- loads clinical + VALD data from Mongo
- performs ReAct-style reasoning with tools
- saves the ClinicalAnalysis document to MongoDB.prognosis
- returns a ClinicalAnalysis Pydantic model.
"""

from LLM.classification.clinical_agent import ClinicalAnalysisAgent, ClinicalAnalysis


def run_langchain_prognosis(patient_id: str) -> ClinicalAnalysis:
    """Run the existing ClinicalAnalysisAgent for API compatibility."""
    agent = ClinicalAnalysisAgent()
    return agent.analyze_patient(patient_id)

