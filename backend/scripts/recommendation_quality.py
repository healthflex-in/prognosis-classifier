#!/usr/bin/env python3
"""
Deterministic quality scorer for RecommendationAgent output.

Grades a recommendation (top_3_action_areas + next_session_plan) against the
agent's OWN prompt rules, so different thinking budgets can be compared on
quality objectively — not by eyeballing. No LLM/judge, no cost, fully
reproducible.

Dimensions (weights sum to 100):
  structure     30  → exactly 3 areas; each 4-10 words; plan <= 90 chars
  no_generic    25  → none of the prompt's STRICTLY-FORBIDDEN generic phrases
  specificity   30  → each area (and the plan) names something anchored in THIS
                      patient's assessment text (body part / activity / goal)
  distinct      10  → the 3 areas are genuinely different ideas
  no_alarming    5  → avoids "severe weakness / high risk / damage / abnormal /
                      dysfunction" (the prompt bans these)

Use as a library (`score_output(...)`) — the benchmark imports it — or standalone
against a benchmark's --json-out file:

  python -m scripts.recommendation_quality --results results.json
"""

import argparse
import json
import re
import sys
from typing import Any, Dict, List, Optional, Set

# ── Lexicons / rules (taken straight from the agent's system prompt) ───────────

# Phrases the prompt marks STRICTLY FORBIDDEN (too generic — apply to any patient).
GENERIC_PHRASES = [
    "improve strength and function",
    "reduce pain and improve daily movement",
    "build tolerance to activity",
    "build tolerance to activity and exercise",
    "improve overall mobility",
    "improve strength and physical function",
    "reduce pain and restore comfortable movement",
    "continue with your rehabilitation",
    "continue your rehabilitation",
    "improve mobility and function",
    "improve movement and reduce pain",
]

# Alarming language the prompt bans.
ALARMING_TERMS = [
    "severe weakness", "high risk", "damage", "abnormal", "dysfunction",
]

# Body regions / movements / activities that count as a concrete anchor even if
# the exact word isn't echoed from the report text.
BODY_ACTIVITY_LEXICON = {
    # joints / regions
    "knee", "shoulder", "hip", "ankle", "elbow", "wrist", "neck", "back",
    "spine", "lumbar", "cervical", "thoracic", "foot", "hand", "calf", "thigh",
    "hamstring", "quad", "quadriceps", "glute", "groin", "achilles", "rotator",
    "hip", "pelvis", "scapula", "tendon", "patella",
    # movements / activities
    "running", "walking", "sitting", "standing", "lifting", "squat", "squatting",
    "overhead", "reaching", "reach", "stairs", "stair", "throwing", "jumping",
    "landing", "bending", "twisting", "kneeling", "climbing", "gripping",
    "sprinting", "cycling", "swimming", "rotation", "flexion", "extension",
    "balance", "gait", "posture", "mobility", "strength", "loading",
}

STOPWORDS = {
    "the", "and", "for", "with", "your", "you", "this", "that", "will", "are",
    "was", "has", "have", "had", "not", "but", "from", "into", "onto", "our",
    "their", "his", "her", "its", "they", "them", "who", "whom", "which",
    "when", "what", "where", "why", "how", "all", "any", "can", "may", "been",
    "being", "during", "after", "before", "over", "under", "than", "then",
    "also", "more", "most", "some", "such", "very", "just", "only", "about",
    "improve", "improving", "reduce", "reducing", "restore", "restoring",
    "build", "building", "increase", "increasing", "better", "help", "helping",
    "work", "working", "focus", "focusing", "begin", "beginning", "start",
    "starting", "continue", "session", "sessions", "next", "plan", "planning",
    "patient", "assessment", "report", "care", "treatment", "level", "levels",
    "pain", "comfortable", "comfort", "daily", "function", "functional",
    "activity", "activities", "movement", "movements", "exercise", "exercises",
    "tolerance", "control", "area", "areas", "good", "well", "able", "months",
    "provided", "documented", "history", "clinical", "subjective", "objective",
    "notes", "goals", "goal", "diagnosis", "complaint", "complaints",
    "not", "available", "unknown", "none", "identified", "data",
}

WORD_RE = re.compile(r"[a-zA-Z]+")


def _words(text: str) -> List[str]:
    return WORD_RE.findall((text or "").lower())


def _content_tokens(text: str) -> Set[str]:
    """Meaningful (non-stopword, length>=4) tokens from a blob of text."""
    return {w for w in _words(text) if len(w) >= 4 and w not in STOPWORDS}


def build_specificity_corpus(patient_data: Dict[str, Any]) -> Set[str]:
    """Concrete anchor tokens drawn from THIS patient's own assessment text."""
    sd = patient_data.get("source_data", {}) or {}
    blob = " ".join(
        str(sd.get(k, ""))
        for k in (
            "chief_complaint", "clinical_history", "subjective_notes",
            "objective_notes", "patient_goals", "provisional_diagnosis_raw",
            "existing_recommendations",
        )
    )
    return _content_tokens(blob)


def _is_specific(text: str, corpus: Set[str]) -> bool:
    """True if `text` names a concrete body part/activity, or echoes a
    meaningful token from the patient's own assessment (prefix match to be
    tolerant of plurals / morphology like run/running, knee/knees)."""
    toks = [w for w in _words(text) if len(w) >= 4]
    for t in toks:
        if t in BODY_ACTIVITY_LEXICON:
            return True
    for t in toks:
        if t in STOPWORDS:
            continue
        for c in corpus:
            if c[:5] == t[:5]:  # shared stem
                return True
    return False


def _too_similar(a: str, b: str) -> bool:
    """Jaccard overlap of content tokens — flags restated ideas."""
    ta, tb = _content_tokens(a), _content_tokens(b)
    if not ta or not tb:
        return False
    inter = len(ta & tb)
    union = len(ta | tb)
    return union > 0 and (inter / union) >= 0.6


# ── Scorer ─────────────────────────────────────────────────────────────────────

def score_output(
    top_3: List[str],
    next_plan: str,
    patient_data: Dict[str, Any],
) -> Dict[str, Any]:
    corpus = build_specificity_corpus(patient_data)
    violations: List[str] = []
    areas = list(top_3 or [])
    plan = next_plan or ""

    # 1) structure (30) ────────────────────────────────────────────────────────
    structure = 30.0
    if len(areas) != 3:
        structure -= 12
        violations.append(f"expected 3 action areas, got {len(areas)}")
    for i, a in enumerate(areas):
        wc = len(_words(a))
        if not (4 <= wc <= 10):
            structure -= 4
            violations.append(f"area {i + 1} has {wc} words (want 4-10): '{a}'")
    if len(plan) > 90:
        structure -= 6
        violations.append(f"next_session_plan is {len(plan)} chars (max 90)")
    if not plan.strip():
        structure -= 6
        violations.append("next_session_plan is empty")
    structure = max(0.0, structure)

    # 2) no generic (25) ─────────────────────────────────────────────────────────
    no_generic = 25.0
    all_texts = areas + [plan]
    generic_hits = []
    for t in all_texts:
        low = " ".join(_words(t))
        for g in GENERIC_PHRASES:
            if g in low:
                generic_hits.append((t, g))
                break
    if generic_hits:
        no_generic -= min(25.0, 9.0 * len(generic_hits))
        for t, g in generic_hits:
            violations.append(f"generic/forbidden phrasing: '{t}' (~'{g}')")
    no_generic = max(0.0, no_generic)

    # 3) specificity (30) ────────────────────────────────────────────────────────
    specificity = 0.0
    specific_area_count = sum(1 for a in areas if _is_specific(a, corpus))
    if areas:
        specificity += 22.0 * (specific_area_count / len(areas))
    for i, a in enumerate(areas):
        if not _is_specific(a, corpus):
            violations.append(f"area {i + 1} not anchored to this patient: '{a}'")
    if _is_specific(plan, corpus):
        specificity += 8.0
    else:
        violations.append("next_session_plan not anchored to this patient")
    specificity = min(30.0, specificity)

    # 4) distinct (10) ───────────────────────────────────────────────────────────
    distinct = 10.0
    for i in range(len(areas)):
        for j in range(i + 1, len(areas)):
            if _too_similar(areas[i], areas[j]):
                distinct -= 5
                violations.append(f"areas {i + 1} & {j + 1} restate the same idea")
    distinct = max(0.0, distinct)

    # 5) no alarming (5) ─────────────────────────────────────────────────────────
    no_alarming = 5.0
    for t in all_texts:
        low = " ".join(_words(t))
        for term in ALARMING_TERMS:
            if term in low:
                no_alarming = 0.0
                violations.append(f"alarming language: '{t}' (~'{term}')")
                break

    total = round(structure + no_generic + specificity + distinct + no_alarming, 1)
    return {
        "total": total,
        "breakdown": {
            "structure": round(structure, 1),
            "no_generic": round(no_generic, 1),
            "specificity": round(specificity, 1),
            "distinct": round(distinct, 1),
            "no_alarming": round(no_alarming, 1),
        },
        "specific_area_count": specific_area_count,
        "violations": violations,
    }


# ── Standalone: re-score a benchmark --json-out file ───────────────────────────

def _score_results_file(path: str) -> None:
    with open(path, "r") as fh:
        results = json.load(fh)

    budget_totals: Dict[str, List[float]] = {}
    for p in results:
        corpus_list = p.get("_specificity_corpus") or []
        patient_data = {"source_data": {"chief_complaint": " ".join(corpus_list)}}
        # If the benchmark embedded the corpus, feed it directly.
        if corpus_list:
            # emulate a source_data blob so build_specificity_corpus() recovers it
            patient_data = {"source_data": {"clinical_history": " ".join(corpus_list)}}
        print(f"\n=== Patient {p.get('patient_id')} — {p.get('patient_name')} ===")
        for label, d in (p.get("by_budget") or {}).items():
            q = score_output(
                d.get("top_3_action_areas", []),
                d.get("next_session_plan", ""),
                patient_data,
            )
            budget_totals.setdefault(label, []).append(q["total"])
            print(f"  [{label}] quality={q['total']}/100  {q['breakdown']}")
            for v in q["violations"]:
                print(f"      - {v}")

    print("\n── Mean quality by budget ──")
    for label, scores in budget_totals.items():
        mean = round(sum(scores) / len(scores), 1) if scores else 0.0
        print(f"  {label}: {mean}/100  (n={len(scores)})")


def main() -> None:
    ap = argparse.ArgumentParser(description="Score recommendation output quality.")
    ap.add_argument("--results", required=True, help="Path to a benchmark --json-out file.")
    args = ap.parse_args()
    _score_results_file(args.results)


if __name__ == "__main__":
    main()
