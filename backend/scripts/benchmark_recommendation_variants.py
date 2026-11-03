#!/usr/bin/env python3
"""
Benchmark the recommendation (user message) model call across model / thinking variants.

SAFETY: uses only the built-in SYNTHETIC assessments below. It reads no database,
writes nothing to any collection, and sends no patient data to the model. It only
calls Vertex inference and prints/writes local result files.

The production system prompt, user-prompt builder, output trimming and schema are
used unchanged; each variant only swaps the agent's `llm` object.

Variants are `model[:thinking]` where thinking is `auto`, `0` (off) or a token budget:
  gemini-2.5-flash:128      <- baseline (current default)
  gemini-2.5-flash:0
  gemini-2.5-flash-lite:0

Usage (inside the backend container):
  python -m scripts.benchmark_recommendation_variants --variants gemini-2.5-flash:128,gemini-2.5-flash:0 --repeat 3
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from langchain_core.messages import HumanMessage, SystemMessage  # noqa: E402

from LLM.recommendation.recommendation_agent import (  # noqa: E402
    SYSTEM_PROMPT,
    RecommendationAgent,
    _build_user_prompt,
    _clean_json,
)

CASES: List[Dict[str, Any]] = [
    {"name": "knee-stairs", "keywords": ["knee", "stair"],
     "source_data": {"chief_complaint": "Right knee pain on stairs for 3 months",
                     "clinical_history": "Recreational runner, pain began after increasing weekly distance.",
                     "subjective_notes": "Pain 6/10 descending stairs, stiffness after sitting.",
                     "provisional_diagnosis_raw": "Patellofemoral pain",
                     "patient_goals": "Return to running 5 km", "nprs": 6}},
    {"name": "shoulder-overhead", "keywords": ["shoulder", "overhead", "reach"],
     "source_data": {"chief_complaint": "Left shoulder pain lifting overhead",
                     "clinical_history": "Swimmer, gradual onset over 6 weeks.",
                     "subjective_notes": "Night pain when lying on the left side.",
                     "provisional_diagnosis_raw": "Rotator cuff related shoulder pain",
                     "patient_goals": "Swim freestyle without pain", "nprs": 5}},
    {"name": "neck-desk", "keywords": ["neck", "desk", "sitting", "stiff"],
     "source_data": {"chief_complaint": "Neck stiffness and headaches at work",
                     "clinical_history": "Desk job 9 hours a day, symptoms for 4 months.",
                     "subjective_notes": "Worse by afternoon, eased by walking.",
                     "provisional_diagnosis_raw": "Mechanical neck pain",
                     "patient_goals": "Work a full day without headaches", "nprs": 4}},
    {"name": "lowback-lifting", "keywords": ["back", "lift", "bend"],
     "source_data": {"chief_complaint": "Low back pain when lifting and bending",
                     "clinical_history": "Warehouse worker, two prior episodes.",
                     "subjective_notes": "Morning stiffness, pain 7/10 after lifting.",
                     "provisional_diagnosis_raw": "Non-specific low back pain",
                     "patient_goals": "Lift at work without flare-ups", "nprs": 7}},
    {"name": "ankle-sport", "keywords": ["ankle", "jump", "landing", "balance", "football", "sport"],
     "source_data": {"chief_complaint": "Recurrent right ankle sprains playing football",
                     "clinical_history": "Third sprain in a year, feels unstable cutting.",
                     "subjective_notes": "Swelling settled, confidence low when landing.",
                     "provisional_diagnosis_raw": "Chronic lateral ankle instability",
                     "patient_goals": "Play football without strapping", "nprs": 3}},
    {"name": "hip-sitting", "keywords": ["hip", "sitting", "groin", "squat"],
     "source_data": {"chief_complaint": "Right hip pinching when sitting and squatting",
                     "clinical_history": "Gym-goer, pinch began with deep squats.",
                     "subjective_notes": "Groin ache after long drives.",
                     "provisional_diagnosis_raw": "Femoroacetabular impingement",
                     "patient_goals": "Squat deep without pinching", "nprs": 5}},
]


def parse_variant(token: str) -> Dict[str, Any]:
    model, _, thinking = token.strip().partition(":")
    thinking = (thinking or "auto").lower()
    budget = None if thinking in ("auto", "-1") else int(thinking)
    return {"label": f"{model}:{thinking}", "model": model, "budget": budget}


def build_llm(variant: Dict[str, Any]):
    import os
    from langchain_google_vertexai import ChatVertexAI

    kwargs: Dict[str, Any] = dict(
        model=variant["model"],
        project=os.getenv("GOOGLE_CLOUD_PROJECT", "stance-ai"),
        location="us-central1",
        temperature=0.3,
        max_tokens=1024,
    )
    if variant["budget"] is not None:
        kwargs["thinking_budget"] = variant["budget"]
    return ChatVertexAI(**kwargs)


def check(output: Dict[str, Any], keywords: List[str]) -> Dict[str, Any]:
    areas = output.get("top_3_action_areas") or []
    plan = output.get("next_session_plan") or ""
    text = " ".join(areas + [plan]).lower()
    return {
        "three_areas": len(areas) == 3,
        "areas_le_40": all(isinstance(a, str) and 0 < len(a) <= 40 for a in areas),
        "plan_le_90": 0 < len(plan) <= 90,
        "specific": any(k in text for k in keywords),
        "distinct": len({a.lower() for a in areas}) == len(areas),
    }


def run(variants, repeat) -> List[Dict[str, Any]]:
    agent = RecommendationAgent()
    results = []
    for variant in variants:
        agent.llm = build_llm(variant)
        for case in CASES:
            prompt = _build_user_prompt({"source_data": case["source_data"]})
            messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]
            for run_index in range(repeat):
                started = time.monotonic()
                try:
                    response = agent.llm.invoke(messages)
                    latency = time.monotonic() - started
                    output = json.loads(_clean_json(response.content.strip()))
                    row = {"valid_json": True, "output": output, **check(output, case["keywords"])}
                except Exception as exc:
                    latency = time.monotonic() - started
                    row = {"valid_json": False, "error": type(exc).__name__}
                row.update(variant=variant["label"], case=case["name"], run=run_index,
                           latency_s=round(latency, 2))
                results.append(row)
                print(f"  {variant['label']:<28} {case['name']:<18} run {run_index}: "
                      f"{latency:.2f}s valid={row['valid_json']}")
    return results


def summarise(results, variants, out_prefix) -> None:
    Path(f"{out_prefix}.json").write_text(json.dumps(results, indent=2))
    lines = ["# Recommendation variant benchmark (synthetic cases)", "",
             "| Variant | Median s | p90 s | Valid JSON | 3 areas | <=40 chars | Plan <=90 | Specific | Distinct |",
             "|---|---|---|---|---|---|---|---|---|"]
    for variant in variants:
        rows = [r for r in results if r["variant"] == variant["label"]]
        lat = sorted(r["latency_s"] for r in rows)
        p90 = lat[min(len(lat) - 1, int(len(lat) * 0.9))]

        def rate(key):
            return f"{sum(1 for r in rows if r.get(key))}/{len(rows)}"

        lines.append(f"| `{variant['label']}` | {statistics.median(lat):.2f} | {p90:.2f} | {rate('valid_json')} "
                     f"| {rate('three_areas')} | {rate('areas_le_40')} | {rate('plan_le_90')} "
                     f"| {rate('specific')} | {rate('distinct')} |")
    lines += ["", "## Side-by-side output, run 0 (for human review)", ""]
    for case in CASES:
        lines.append(f"### {case['name']}")
        for variant in variants:
            row = next((r for r in results if r["variant"] == variant["label"]
                        and r["case"] == case["name"] and r["run"] == 0 and r.get("output")), None)
            if row:
                o = row["output"]
                lines.append(f"- `{variant['label']}`: {o.get('top_3_action_areas')} | {o.get('next_session_plan')!r}")
        lines.append("")
    Path(f"{out_prefix}.md").write_text("\n".join(lines))
    print("\n" + "\n".join(lines[:4 + len(variants)]))
    print(f"\nWrote {out_prefix}.json and {out_prefix}.md")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--variants", default="gemini-2.5-flash:128")
    parser.add_argument("--repeat", type=int, default=2)
    parser.add_argument("--out", default="recommendation_bench")
    args = parser.parse_args()
    variants = [parse_variant(v) for v in args.variants.split(",")]
    summarise(run(variants, args.repeat), variants, args.out)


if __name__ == "__main__":
    main()
