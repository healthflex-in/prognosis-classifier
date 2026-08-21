#!/usr/bin/env python3
"""
Recommendation Agent
Generates two patient-facing retention fields from a completed first-assessment report:
  - top_3_action_areas: 3 action-oriented priority phrases (4-10 words each)
  - next_session_plan:  1-2 short patient-friendly sentences (max 90 chars) describing next steps
"""

import json
import os
import re
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_vertexai import ChatVertexAI
from pydantic import BaseModel, Field

warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_google_vertexai")

backend_env = Path(__file__).parent.parent.parent / ".env"
if backend_env.exists():
    load_dotenv(backend_env)


# ── Output schema ─────────────────────────────────────────────────────────────

class RecommendationOutput(BaseModel):
    top_3_action_areas: List[str] = Field(
        description="Exactly 3 action-oriented priority areas (4-10 words each)"
    )
    next_session_plan: str = Field(
        description="Max 90 characters, 1-2 sentences, patient-friendly, forward-looking"
    )


# ── Prompts ───────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are the Stance Health Clinician Agent — a clinical communication assistant that translates a completed physiotherapy first-assessment report into short, patient-facing retention messaging.

Your output will be shown directly to the patient in a visual summary immediately after their first assessment. It must read as if written by their treating clinician — warm, professional, confident, and specific to this patient's own assessment.

You MUST respond with a single valid JSON object — no markdown, no prose, no code fences.

CORE RULES:
- Use ONLY information supported by the assessment provided: chief complaint, clinical history, subjective notes, objective/VALD findings, functional limitations, and stated goals.
- Do NOT invent diagnoses, findings, goals, treatment frequency, exercises, or treatment plans that are not reasonably supported by the assessment.
- Do NOT use alarming language such as "severe weakness", "high risk", "damage", "abnormal", or "dysfunction" unless clinically essential. Prefer neutral, constructive language focused on what needs to improve.
- Write in the clinician's voice, speaking to the patient directly — reassuring, but never promising outcomes or guarantees.
- Remove all unnecessary medical jargon. Diagnoses, special test names, and imaging findings must be translated into plain, functional, everyday language.
- Simple English only. Assume no medical background.

FIELD 1 — top_3_action_areas:
- Return EXACTLY 3 items.
- Each item must be approximately 4–10 words.
- Phrase each as an action or improvement area — NEVER as a diagnosis, test result, or clinical label.
  - Good: "Improve knee strength and control", "Restore comfortable shoulder mobility", "Build tolerance to running loads", "Reduce sensitivity during prolonged sitting", "Improve landing control and confidence"
  - Bad: "ACL deficiency", "Glute med weakness", "Positive Hawkins-Kennedy", "Suspected tennis elbow", "MRI shows focal tear"
- Do not simply name a body part alone — always pair the body part/area with the action or goal.
- Prioritise the three areas most relevant to the patient's primary complaint and stated goals. These must be the genuinely highest-priority areas from the assessment — not the first three findings encountered, and not an exhaustive list of everything found.
- Priority order should reflect: (1) relevance to primary complaint, (2) objective findings that materially affect function, (3) patient's stated goals.
- Each of the 3 items must reflect a distinct idea. Do not restate the same concept twice in different words.

FIELD 2 — next_session_plan:
- Maximum 90 characters. 1–2 short sentences maximum. Be concise.
- Describe what will actually happen, begin, or progress in the NEXT session — this is forward-looking, not a summary of the diagnosis.
- Use patient-friendly terminology only.
- Prioritise active treatment/rehab content where supported by the assessment (e.g. loading progression, mobility work, movement retraining, strengthening focus).
- Do NOT invent specific named exercises, sets/reps, or treatment frequency unless explicitly documented or clearly planned in the assessment.
- Do NOT repeat the Top 3 Immediate Action Areas word-for-word — this field should sound like a clinician previewing next steps, e.g.:
  - "We will be focussing on knee mobility along with improving ankle proprioception."
  - "In the next session, our focus will be to minimise pain and improve your shoulder mobility."
  - "Next session we will work on running drills, calf strengthening and landing control."

SELF-CHECK before returning output — verify all of the following:
1. Every statement is traceable to something actually present in the assessment.
2. A patient with no medical background would understand every word.
3. The 3 action areas are genuinely the highest priorities relative to the patient's complaint and goals — not arbitrary or repetitive.
4. The next-session plan describes what happens next, not a restatement of the diagnosis or the action areas.
5. There is no unsupported certainty, guarantee, or promised outcome.
6. All clinical jargon has been removed or translated into plain language.
7. Both fields are short enough to fit comfortably on a visual summary card.

If the assessment lacks enough detail to confidently support a specific field, use the most conservative phrasing that is still specific to this patient rather than inventing detail. Never leave a field empty and never fabricate clinical specifics.

Respond with this exact JSON structure:
{
  "top_3_action_areas": [
    "string — 4-10 words, action-oriented, highest priority area",
    "string — 4-10 words, action-oriented, second priority area",
    "string — 4-10 words, action-oriented, third priority area"
  ],
  "next_session_plan": "string — max 90 characters, 1-2 sentences, patient-friendly, forward-looking"
}"""


def _build_user_prompt(patient_data: Dict[str, Any]) -> str:
    sd = patient_data.get("source_data", {})
    ef = patient_data.get("extracted_fields", {})

    chief_complaint = sd.get("chief_complaint", "Not provided")
    clinical_history = sd.get("clinical_history", "Not provided")
    subjective_notes = sd.get("subjective_notes", "Not provided")
    existing_diagnosis = sd.get("provisional_diagnosis_raw", "Not provided")
    patient_goals = sd.get("patient_goals", "Not explicitly documented")

    objective_notes = sd.get("objective_notes", "")
    existing_recommendations = sd.get("existing_recommendations", "")

    duration_months = ef.get("duration_months", "Unknown")
    clinical_stage = ef.get("clinical_stage", {}).get("stage", "unknown")
    primary_joint = ef.get("joint_mapping", {}).get("primary_joint", "Unknown")
    functional_region = ef.get("joint_mapping", {}).get("functional_region", "unknown")

    strength_asym = patient_data.get("strength_asymmetry_percent")
    rom_asym = patient_data.get("rom_asymmetry_degrees")
    abs_force = patient_data.get("absolute_force_level")

    vald_lines = []
    if strength_asym is not None:
        vald_lines.append(f"- Strength Asymmetry: {strength_asym}%")
    if rom_asym is not None:
        vald_lines.append(f"- ROM Asymmetry: {rom_asym}°")
    if abs_force:
        vald_lines.append(f"- Absolute Force Level: {abs_force}")
    vald_section = "\n".join(vald_lines) if vald_lines else "- No VALD data available"

    parts = [
        "Read the completed first-assessment report below and pre-fill the two customer-facing retention fields for the treating clinician to review.",
        "",
        "CLINICAL FINDINGS:",
        f"- Chief Complaint: {chief_complaint}",
        f"- Clinical History: {clinical_history}",
        f"- Duration: {duration_months} months (Stage: {clinical_stage})",
        f"- Primary Joint: {primary_joint}",
        f"- Functional Region: {functional_region}",
        f"- Subjective Notes: {subjective_notes}",
    ]

    if objective_notes:
        parts += ["", "OBJECTIVE FINDINGS:", objective_notes]

    if existing_recommendations:
        parts += ["", "EXISTING RECOMMENDATIONS (session plan):", existing_recommendations]

    parts += [
        "",
        "VALD BIOMECHANICAL DATA:",
        vald_section,
        "",
        f"PROVISIONAL DIAGNOSIS (for internal reasoning only — do not surface directly to patient): {existing_diagnosis}",
        "",
        f"PATIENT GOALS (if documented): {patient_goals}",
        "",
        "Return ONLY the JSON object. No markdown, no explanation outside the JSON.",
    ]

    return "\n".join(parts)


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
    return raw


# ── Agent ─────────────────────────────────────────────────────────────────────

class RecommendationAgent:
    def __init__(self):
        self.llm = ChatVertexAI(
            model="gemini-2.5-flash",
            project=os.getenv("GOOGLE_CLOUD_PROJECT", "stance-ai"),
            location="us-central1",
            temperature=0.3,
            max_tokens=1024,
        )

    def generate(self, patient_data: Dict[str, Any]) -> RecommendationOutput:
        user_prompt = _build_user_prompt(patient_data)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        try:
            response = self.llm.invoke(messages)
            raw = response.content.strip()
            data = json.loads(_clean_json(raw))
            areas = data.get("top_3_action_areas", [])
            # Ensure exactly 3 items
            if len(areas) < 3:
                areas += ["Continue with your rehabilitation programme"] * (3 - len(areas))
            return RecommendationOutput(
                top_3_action_areas=areas[:3],
                next_session_plan=(data.get("next_session_plan") or "")[:90],
            )
        except Exception as e:
            print(f"⚠️  RecommendationAgent LLM failed: {e}")
            return self._fallback(patient_data)

    def _fallback(self, patient_data: Dict[str, Any]) -> RecommendationOutput:
        complaint = patient_data.get("source_data", {}).get("chief_complaint", "your condition")
        joint = (
            patient_data.get("extracted_fields", {})
            .get("joint_mapping", {})
            .get("primary_joint", "affected area")
        )
        return RecommendationOutput(
            top_3_action_areas=[
                f"Improve {joint} strength and function",
                "Reduce pain and improve daily movement",
                "Build tolerance to activity and exercise",
            ],
            next_session_plan=f"Next session we will begin targeted rehabilitation for {complaint}."[:90],
        )
