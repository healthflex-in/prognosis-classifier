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
import threading
import time
import warnings
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from dotenv import load_dotenv
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_google_vertexai import ChatVertexAI
from pydantic import ValidationError
from utils.recommendation_output import RecommendationOutput

warnings.filterwarnings("ignore", category=DeprecationWarning, module="langchain_google_vertexai")

backend_env = Path(__file__).parent.parent.parent / ".env"
if backend_env.exists():
    load_dotenv(backend_env)


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
- Write complete words and complete thoughts. Never shorten text by cutting a word or sentence.
- If text is too long, rewrite it more concisely while preserving the clinical meaning and side of the body. Do not use R/L abbreviations to fit.

SPECIFICITY REQUIREMENT — THIS IS THE MOST IMPORTANT RULE:
Every concern and the session plan MUST be specific to THIS patient's actual data. You must name the exact body part, movement, activity, or limitation that appears in the assessment. Generic phrases like "Improve strength and function", "Reduce pain and improve daily movement", or "Build tolerance to activity" are STRICTLY FORBIDDEN — they could apply to any patient and add zero value. If you catch yourself writing something that could apply to any random patient, rewrite it using the specific body part, sport, activity, limitation, or goal mentioned in THIS assessment.

FIELD 1 — top_3_action_areas:
- Return EXACTLY 3 items.
- Each item MUST be 40 characters or fewer (hard limit — count every character including spaces).
- Use a complete, concise action phrase. Prefer 25–35 characters to leave space; never return a fragment cut from a longer phrase.
- Each item MUST name the specific body region, movement pattern, or activity from this patient's assessment (e.g. "knee", "shoulder", "running", "sitting tolerance", "overhead reach", "stair descent", "throwing").
- Phrase each as an action or improvement area — NEVER as a diagnosis, test result, or clinical label.
  - Good: "Knee strength for stair climbing", "Pain-free shoulder overhead reach", "Build running distance gradually", "Reduce neck stiffness at desk"
  - Bad (too generic — rejected): "Improve strength and function", "Reduce pain and improve daily movement", "Build tolerance to activity and exercise", "Improve overall mobility"
- Do not simply name a body part alone — always pair it with the specific action, goal, or limitation.
- Prioritise the three areas most relevant to this patient's primary complaint and stated goals. These must be the genuinely highest-priority areas from this specific assessment.
- Priority order: (1) primary complaint and its functional impact, (2) objective findings that materially affect function, (3) patient's stated goals.
- Each of the 3 items must reflect a distinct idea — do not restate the same concept in different words.

FIELD 2 — next_session_plan:
- Hard limit: 90 characters including spaces and the final punctuation. 1–2 short sentences maximum. Be concise.
- Write one complete sentence of 60–75 characters. Count the characters before answering; if it is over 80, shorten it. End with sentence punctuation. Never end with an unfinished thought such as "strengthening for" or a cut word such as "exerc".
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
  "next_session_plan": "string — max 80 characters, specific to this patient, forward-looking"
}"""



PLAN_REWRITE_SYSTEM = (
    "You shorten one sentence for a physiotherapy patient message. Keep exactly the same meaning, "
    "the same body area, the same side (left/right) and the same activity. Do not add any new "
    "treatment, fact or advice. Use complete words and one complete sentence that ends with a full "
    "stop. It must be at most 80 characters including spaces and the full stop. To make it shorter, "
    "remove or replace whole words. Never abbreviate or cut any word. Return only the sentence."
)

AREA_REWRITE_SYSTEM = (
    "You shorten one short action phrase for a physiotherapy patient card. Keep exactly the same meaning, "
    "the same body area, the same side (left/right) and the same activity. Do not add anything new. "
    "It must be at most 40 characters including spaces, with no full stop at the end. To make it shorter, "
    "remove or replace whole words. Never abbreviate, shorten or cut any word. Return only the phrase."
)



def _has_cut_word(original: str, rewritten: str) -> bool:
    """True if the rewrite contains a word that is just the front of a longer word from the
    original (for example "sit" for "sitting"). Shortening must drop whole words, never chop them."""
    original_words = set(re.findall(r"[a-z]+", original.lower()))
    for word in re.findall(r"[a-z]+", rewritten.lower()):
        if len(word) >= 3 and word not in original_words and any(
            longer.startswith(word) and len(longer) - len(word) >= 2 for longer in original_words
        ):
            return True
    return False

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
        f"NPRS pain score: {sd.get('nprs', 'Not provided')}",
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


# ── Timing-log helpers: sizes and counts only, never text ─────────────────────

def _prompt_size_fields(patient_data: Dict[str, Any], user_prompt: str) -> Dict[str, Any]:
    sd = patient_data.get("source_data", {}) or {}
    return {
        "system_chars": len(SYSTEM_PROMPT),
        "user_chars": len(user_prompt),
        "goals_chars": len(str(sd.get("patient_goals") or "")),
        "objective_chars": len(str(sd.get("objective_notes") or "")),
        "existing_recs_chars": len(str(sd.get("existing_recommendations") or "")),
    }


def _token_usage_fields(response: Any) -> Dict[str, Any]:
    try:
        usage = getattr(response, "usage_metadata", None) or {}
        details = usage.get("output_token_details") or {}
        fields = {
            "input_tokens": usage.get("input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "reasoning_tokens": details.get("reasoning"),
        }
        return {key: value for key, value in fields.items() if value is not None}
    except Exception:
        return {}


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
        # Tiny task (shorten one sentence): no thinking, short output.
        self._rewriter = self._build_llm(0, 256)

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

    def _shorten_overlong(
        self,
        patient_data: Dict[str, Any],
        raw: str,
        error: ValidationError,
        timing_callback: Optional[Callable[..., None]] = None,
    ) -> Optional[RecommendationOutput]:
        """Fix an answer whose ONLY problem is text that is a little too long.

        Each over-long field (the plan, or an action area) is shortened by a small call that
        sees just that text and the chief complaint. Every other field stays exactly as the
        model wrote it. Returns None for any other problem, or if the result is still
        invalid, so the caller falls back to the full rewrite retry."""
        try:
            issues = error.errors(include_input=False, include_url=False)
            targets = []  # ("plan",) or ("area", index)
            for issue in issues:
                loc = tuple(issue["loc"])
                if issue["type"] != "string_too_long":
                    return None
                if loc == ("next_session_plan",):
                    targets.append(("plan",))
                elif len(loc) == 2 and loc[0] == "top_3_action_areas" and isinstance(loc[1], int):
                    targets.append(("area", loc[1]))
                else:
                    return None
            if not targets or len(targets) > 3:
                return None
            data = json.loads(_clean_json(raw))
            areas, plan = list(data["top_3_action_areas"]), data["next_session_plan"]
            chief = (patient_data.get("source_data", {}) or {}).get("chief_complaint", "")
            for target in targets:
                if target[0] == "plan":
                    system, label, text = PLAN_REWRITE_SYSTEM, "Sentence", plan
                else:
                    system, label, text = AREA_REWRITE_SYSTEM, "Phrase", areas[target[1]]
                started = time.monotonic()
                response = None
                try:
                    response = self._rewriter.invoke([
                        SystemMessage(content=system),
                        HumanMessage(content=f"Chief complaint: {chief}\n{label} to shorten ({len(text)} characters): {text}"),
                    ])
                finally:
                    if timing_callback:
                        try:
                            timing_callback("recommendation_shorten", started,
                                            field=target[0], **_token_usage_fields(response))
                        except Exception:
                            pass  # timing must never affect generation
                shortened = response.content
                if not isinstance(shortened, str):
                    return None
                shortened = shortened.strip().strip('"').strip()
                if not shortened or _has_cut_word(text, shortened):
                    return None  # a chopped word is worse than a retry: use the full rewrite
                if target[0] == "plan":
                    plan = shortened
                else:
                    areas[target[1]] = shortened
            return RecommendationOutput.model_validate(
                {"top_3_action_areas": areas, "next_session_plan": plan}
            )
        except Exception:
            return None

    def generate(
        self,
        patient_data: Dict[str, Any],
        timing_callback: Optional[Callable[..., None]] = None,
    ) -> RecommendationOutput:
        user_prompt = _build_user_prompt(patient_data)
        messages = [
            SystemMessage(content=SYSTEM_PROMPT),
            HumanMessage(content=user_prompt),
        ]

        # One bounded rewrite: valid responses need only the original call.
        for attempt in range(2):
            invoke_started = time.monotonic()
            response = None
            try:
                response = self.llm.invoke(messages)
            except Exception as error:
                raise RuntimeError("Recommendation generation failed. Please try again.") from error
            finally:
                if timing_callback:
                    try:
                        timing_callback("recommendation_model_invoke", invoke_started,
                                        attempt=attempt + 1,
                                        **_prompt_size_fields(patient_data, user_prompt),
                                        **_token_usage_fields(response))
                    except Exception:
                        pass  # timing must never affect generation
            raw = response.content
            try:
                if not isinstance(raw, str):
                    raise ValueError("Return a single JSON object as text")
                return RecommendationOutput.model_validate(json.loads(_clean_json(raw)))
            except (ValueError, TypeError) as error:
                if attempt == 1:
                    break
                if isinstance(error, ValidationError) and isinstance(raw, str):
                    shortened = self._shorten_overlong(patient_data, raw, error, timing_callback)
                    if shortened is not None:
                        return shortened
                if isinstance(error, ValidationError):
                    issues = "; ".join(
                        f"{'.'.join(map(str, item['loc']))}: {item['msg']}"
                        for item in error.errors(include_input=False, include_url=False)
                    )
                else:
                    issues = "Return valid JSON with the required fields and string values."
                if isinstance(raw, str):
                    messages.append(AIMessage(content=raw))
                messages.append(HumanMessage(content=(
                    f"Rewrite the response to correct these validation issues: {issues}\n"
                    "Return exactly 3 distinct, complete action phrases, each at most 40 characters, "
                    "and a complete next-session sentence at most 90 characters, including spaces "
                    "and punctuation. Use shorter wording, never cut words or unfinished sentences. "
                    "Preserve the original assessment's meaning, body area and laterality. "
                    "Do not invent treatment details. Return only the full corrected JSON object."
                )))
        # Never save a truncated response or disguise an AI failure as a generic
        # patient recommendation. Existing routes surface this error to the UI.
        raise RuntimeError("Could not generate complete recommendations within the character limits. Please try again.")


# ── Shared instance ───────────────────────────────────────────────────────────
# Building ChatVertexAI per request repeats credential/client setup. The client is
# stateless between calls, so one instance per process is reused.

_shared_agent: Optional[RecommendationAgent] = None
_shared_agent_lock = threading.Lock()


def get_shared_agent() -> RecommendationAgent:
    global _shared_agent
    if _shared_agent is None:
        with _shared_agent_lock:
            if _shared_agent is None:
                _shared_agent = RecommendationAgent()
    return _shared_agent
