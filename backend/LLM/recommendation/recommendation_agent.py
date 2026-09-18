#!/usr/bin/env python3
"""
Recommendation Agent
Generates two patient-facing retention fields from a completed first-assessment report:
  - top_3_action_areas: 3 action-oriented priority phrases (max 40 characters each)
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
        description="Exactly 3 action-oriented priority areas (max 40 characters each)"
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
- Do NOT use alarming language such as "severe weakness", "high risk", "damage", "abnormal", or "dysfunction". Prefer neutral, constructive language focused on what needs to improve.
- Write in the clinician's voice, speaking to the patient directly — reassuring, but never promising outcomes or guarantees.
- Remove all unnecessary medical jargon. Diagnoses, special test names, and imaging findings must be translated into plain, functional, everyday language.
- Simple English only. Assume no medical background.

SPECIFICITY REQUIREMENT — THIS IS THE MOST IMPORTANT RULE:
Every concern and the session plan MUST be specific to THIS patient's actual data. You must name the exact body part, movement, activity, or limitation that appears in the assessment. Generic phrases like "Improve strength and function", "Reduce pain and improve daily movement", or "Build tolerance to activity" are STRICTLY FORBIDDEN — they could apply to any patient and add zero value. If you catch yourself writing something that could apply to any random patient, rewrite it using the specific body part, sport, activity, limitation, or goal mentioned in THIS assessment.

FIELD 1 — top_3_action_areas:
- Return EXACTLY 3 items.
- Each item MUST be 40 characters or fewer (hard limit — count every character including spaces).
- Each item MUST name the specific body region, movement pattern, or activity from this patient's assessment (e.g. "knee", "shoulder", "running", "sitting tolerance", "overhead reach", "stair descent", "throwing").
- Phrase each as an action or improvement area — NEVER as a diagnosis, test result, or clinical label.
  - Good: "Knee strength for stair climbing", "Pain-free shoulder overhead reach", "Build running distance gradually", "Reduce neck stiffness at desk"
  - Bad (too generic — rejected): "Improve strength and function", "Reduce pain and improve daily movement", "Build tolerance to activity and exercise", "Improve overall mobility"
- Do not simply name a body part alone — always pair it with the specific action, goal, or limitation.
- Prioritise the three areas most relevant to this patient's primary complaint and stated goals. These must be the genuinely highest-priority areas from this specific assessment.
- Priority order: (1) primary complaint and its functional impact, (2) objective findings that materially affect function, (3) patient's stated goals.
- Each of the 3 items must reflect a distinct idea — do not restate the same concept in different words.

FIELD 2 — next_session_plan:
- Maximum 90 characters. 1–2 short sentences maximum. Be concise.
- Must reference something specific from this patient's assessment — the affected body area, a specific movement goal, or a treatment approach directly relevant to their complaint.
- Describe what will actually happen next session — forward-looking, not a summary of findings.
- Use patient-friendly language only.
- Do NOT repeat the Top 3 concerns word-for-word. Sound like a clinician previewing next steps:
  - "We will focus on releasing your neck stiffness and starting gentle strengthening."
  - "Next session we will work on your knee's range of motion and begin loading exercises."
  - "We will start hands-on treatment for your shoulder and gentle overhead mobility work."

SELF-CHECK before returning output:
1. Could any of the 3 concerns apply to a different patient with a completely different complaint? If yes — rewrite.
2. Does every item name something specific from THIS assessment (body part, activity, limitation)?
3. Is all clinical jargon removed or translated?
4. Does the next-session plan describe what actually happens next, not a diagnosis restatement?
5. Are both fields short enough to fit on a small visual summary card?

If the assessment lacks enough detail, use the most conservative phrasing that is still specific to this patient. Never fabricate clinical specifics. Never leave a field empty.

Respond with this exact JSON structure:
{
  "top_3_action_areas": [
    "string — max 40 chars, specific to this patient's complaint/body area",
    "string — max 40 chars, specific to this patient's findings/goals",
    "string — max 40 chars, specific to this patient's functional limitation"
  ],
  "next_session_plan": "string — max 90 characters, specific to this patient, forward-looking"
}"""


def _build_user_prompt(patient_data: Dict[str, Any]) -> str:
    sd = patient_data.get("source_data", {})

    chief_complaint = sd.get("chief_complaint", "Not provided")
    clinical_history = sd.get("clinical_history", "Not provided")
    subjective_notes = sd.get("subjective_notes", "Not provided")
    existing_diagnosis = sd.get("provisional_diagnosis_raw", "Not provided")
    patient_goals = sd.get("patient_goals", "Not explicitly documented")
    objective_notes = sd.get("objective_notes", "")
    existing_recommendations = sd.get("existing_recommendations", "")

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
        "Generate the two patient-facing retention fields for this first-assessment report.",
        "The concerns and session plan MUST be specific to the body area, activities, and limitations described below — not generic.",
        "",
        "── PRIMARY COMPLAINT ──",
        f"Chief Complaint: {chief_complaint}",
        f"Provisional Diagnosis (internal only): {existing_diagnosis}",
        "",
        "── PATIENT HISTORY & SUBJECTIVE ──",
        f"Clinical History: {clinical_history}",
        f"Subjective Notes: {subjective_notes}",
        f"Patient Goals: {patient_goals}",
    ]

    if objective_notes:
        parts += [
            "",
            "── OBJECTIVE FINDINGS ──",
            objective_notes,
        ]

    if vald_section != "- No VALD data available":
        parts += [
            "",
            "── VALD BIOMECHANICAL DATA ──",
            vald_section,
        ]

    if existing_recommendations:
        parts += [
            "",
            "── CLINICIAN'S EXISTING SESSION PLAN ──",
            existing_recommendations,
        ]

    parts += [
        "",
        "Return ONLY the JSON object. No markdown, no explanation outside the JSON.",
    ]

    return "\n".join(parts)


def _clean_json(raw: str) -> str:
    raw = raw.strip()
    raw = re.sub(r"^```(?:json)?", "", raw).rstrip("`").strip()
    return raw


# ── Config (env-tunable, no redeploy needed to change) ─────────────────────────

def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# Thinking budget for gemini-2.5-flash (this is a tiny, structured output task):
#   -1 = dynamic / "Auto"  → the model decides (original production behaviour)
#    0 = thinking disabled  → fastest, but may weaken 3-area prioritisation
#   >0 = capped thinking tokens (e.g. 128 keeps most reasoning, cuts most latency)
# Default 128: keep the prioritisation reasoning, drop the multi-thousand-token
# "thinking" that was the bulk of the ~15s latency.
DEFAULT_THINKING_BUDGET = _env_int("RECOMMENDATION_THINKING_BUDGET", 128)
# Output is 3 short phrases + one <=90 char sentence — 8192 was wildly oversized.
DEFAULT_MAX_TOKENS = _env_int("RECOMMENDATION_MAX_TOKENS", 1024)


# ── Agent ─────────────────────────────────────────────────────────────────────

class RecommendationAgent:
    def __init__(
        self,
        thinking_budget: Optional[int] = DEFAULT_THINKING_BUDGET,
        max_tokens: int = DEFAULT_MAX_TOKENS,
    ):
        self.thinking_budget = thinking_budget
        self.max_tokens = max_tokens
        self.llm = self._build_llm(thinking_budget, max_tokens)

    @staticmethod
    def _build_llm(thinking_budget: Optional[int], max_tokens: int) -> ChatVertexAI:
        kwargs: Dict[str, Any] = dict(
            model="gemini-2.5-flash",
            project=os.getenv("GOOGLE_CLOUD_PROJECT", "stance-ai"),
            location="us-central1",
            temperature=0.3,
            max_tokens=max_tokens,
        )
        # thinking_budget=None means "don't pass it" → library default (Auto),
        # i.e. the exact original behaviour.
        if thinking_budget is not None:
            try:
                return ChatVertexAI(thinking_budget=thinking_budget, **kwargs)
            except TypeError:
                # Installed langchain-google-vertexai predates the thinking_budget
                # kwarg — degrade to library default instead of crashing.
                print(
                    "⚠️  ChatVertexAI has no 'thinking_budget' kwarg in this "
                    "version; falling back to default (Auto) thinking."
                )
        return ChatVertexAI(**kwargs)

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
            if len(areas) < 3:
                areas += ["Continue with your rehabilitation programme"] * (3 - len(areas))
            return RecommendationOutput(
                top_3_action_areas=[a[:40] for a in areas[:3]],
                next_session_plan=(data.get("next_session_plan") or "")[:90],
            )
        except Exception as e:
            import traceback
            print(f"⚠️  RecommendationAgent LLM failed: {e}")
            traceback.print_exc()
            return self._fallback(patient_data)

    def _fallback(self, patient_data: Dict[str, Any]) -> RecommendationOutput:
        return RecommendationOutput(
            top_3_action_areas=[
                "Reduce pain and restore comfortable movement",
                "Improve strength and physical function",
                "Build tolerance to activity and daily tasks",
            ],
            next_session_plan="We will begin hands-on treatment and targeted exercises in your next session.",
        )
