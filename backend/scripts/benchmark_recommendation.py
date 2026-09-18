#!/usr/bin/env python3
"""
Benchmark the RecommendationAgent across thinking-budget settings.

Goal: compare latency AND output quality of different Gemini 2.5 Flash thinking
budgets (Auto vs a small cap vs off) on REAL first-assessment reports, so we can
pick a budget that keeps prioritisation quality while cutting the ~15s latency.

SAFETY — this script is strictly READ-ONLY:
  • It reads `reports` / `users` / VALD data to build the agent input.
  • It NEVER calls save_recommendation and NEVER writes to any collection.
  • It NEVER changes production config or the deployed service.
  • It only calls the Vertex LLM (inference) and writes a local report file.

Usage:
  # Benchmark real patients straight from Mongo (read-only reads):
  python -m scripts.benchmark_recommendation --patient-id 6a4bacd2... 64f1... \
      --budgets auto,128,0 --repeat 2 --out bench_report.md

  # Save the fetched inputs so future runs are fully offline (zero DB access):
  python -m scripts.benchmark_recommendation --patient-id 6a4bacd2... \
      --dump-input samples.json

  # Re-run entirely offline from a saved sample file (no DB at all):
  python -m scripts.benchmark_recommendation --input-file samples.json \
      --budgets auto,256,128,0 --repeat 3 --out bench_report.md

Budget tokens:
  auto | -1  → dynamic thinking, the current production default (baseline)
  0          → thinking disabled (fastest)
  <positive> → capped thinking tokens (e.g. 128, 256)
"""

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Make `backend/` importable regardless of where this is invoked from.
BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from LLM.recommendation.recommendation_agent import RecommendationAgent  # noqa: E402
from scripts.recommendation_quality import (  # noqa: E402
    score_output,
    build_specificity_corpus,
)


def _parse_budget(token: str) -> Optional[int]:
    """Map a CLI budget token to the agent's thinking_budget value.

    'auto' → None (don't pass the kwarg → library default == current prod behaviour).
    '-1'   → -1 (dynamic; equivalent to Auto but explicitly requested).
    else   → int.
    """
    t = token.strip().lower()
    if t in ("auto", "baseline", "default", "none"):
        return None
    return int(t)


def _budget_label(budget: Optional[int]) -> str:
    if budget is None:
        return "auto (baseline)"
    if budget == -1:
        return "-1 (dynamic)"
    if budget == 0:
        return "0 (off)"
    return f"{budget} (capped)"


def _load_inputs_from_db(patient_ids: List[str]) -> List[Dict[str, Any]]:
    """READ-ONLY: build agent inputs for real patients from Mongo."""
    from api.routes.recommendation import build_recommendation_input, _get_db

    db = _get_db()
    inputs: List[Dict[str, Any]] = []
    for pid in patient_ids:
        data = build_recommendation_input(db, pid)
        if not data:
            print(f"⚠️  No usable first-assessment report for {pid}, skipping.")
            continue
        inputs.append(data)
    return inputs


def _load_inputs_from_file(path: str) -> List[Dict[str, Any]]:
    with open(path, "r") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else [data]


def _run_once(agent: RecommendationAgent, patient_data: Dict[str, Any]) -> Dict[str, Any]:
    start = time.perf_counter()
    output = agent.generate(patient_data)
    elapsed = time.perf_counter() - start
    return {
        "seconds": elapsed,
        "top_3_action_areas": output.top_3_action_areas,
        "next_session_plan": output.next_session_plan,
    }


def benchmark(
    inputs: List[Dict[str, Any]],
    budgets: List[Optional[int]],
    repeat: int,
    max_tokens: Optional[int] = None,
) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []

    # Build one agent per budget (avoids re-instantiating the client each call).
    # If max_tokens is given, apply it; otherwise use the agent's own default.
    agents = {}
    for b in budgets:
        if max_tokens is not None:
            agents[_budget_label(b)] = RecommendationAgent(thinking_budget=b, max_tokens=max_tokens)
        else:
            agents[_budget_label(b)] = RecommendationAgent(thinking_budget=b)

    for patient_data in inputs:
        pid = patient_data.get("patient_id", "unknown")
        name = patient_data.get("patient_name", "unknown")
        complaint = patient_data.get("source_data", {}).get("chief_complaint", "")
        print(f"\n=== Patient {pid} ({name}) — {complaint[:60]} ===")

        per_patient: Dict[str, Any] = {
            "patient_id": pid,
            "patient_name": name,
            "chief_complaint": complaint,
            # Embed the anchor text so a benchmark JSON can be re-scored offline.
            "_specificity_corpus": sorted(build_specificity_corpus(patient_data)),
            "by_budget": {},
        }

        for b in budgets:
            label = _budget_label(b)
            agent = agents[label]
            runs = []
            last_output = None
            for i in range(repeat):
                try:
                    r = _run_once(agent, patient_data)
                    runs.append(r["seconds"])
                    last_output = r
                    print(f"  [{label}] run {i + 1}/{repeat}: {r['seconds']:.2f}s")
                except Exception as e:  # noqa: BLE001
                    print(f"  [{label}] run {i + 1} FAILED: {e}")
            if last_output is not None:
                quality = score_output(
                    last_output["top_3_action_areas"],
                    last_output["next_session_plan"],
                    patient_data,
                )
                print(f"  [{label}] quality={quality['total']}/100 {quality['breakdown']}")
                per_patient["by_budget"][label] = {
                    "median_seconds": round(statistics.median(runs), 2) if runs else None,
                    "min_seconds": round(min(runs), 2) if runs else None,
                    "runs": [round(x, 2) for x in runs],
                    "top_3_action_areas": last_output["top_3_action_areas"],
                    "next_session_plan": last_output["next_session_plan"],
                    "quality": quality,
                }
        results.append(per_patient)
    return results


def render_markdown(results: List[Dict[str, Any]]) -> str:
    lines: List[str] = ["# Recommendation thinking-budget benchmark\n"]

    # ── Overall summary: latency vs quality per budget, averaged over patients ──
    agg: Dict[str, Dict[str, List[float]]] = {}
    for p in results:
        for label, d in p["by_budget"].items():
            a = agg.setdefault(label, {"secs": [], "quality": []})
            if d.get("median_seconds") is not None:
                a["secs"].append(d["median_seconds"])
            if d.get("quality"):
                a["quality"].append(d["quality"]["total"])

    if agg:
        lines.append("## Summary (averaged across patients)\n")
        lines.append("| Budget | Median latency (s) | Mean quality /100 |")
        lines.append("|---|---|---|")
        for label, a in agg.items():
            med = round(statistics.median(a["secs"]), 2) if a["secs"] else "-"
            mq = round(sum(a["quality"]) / len(a["quality"]), 1) if a["quality"] else "-"
            lines.append(f"| {label} | {med} | {mq} |")
        lines.append("\n> Pick the lowest budget whose mean quality matches `auto (baseline)`.\n")
        lines.append("\n---\n")

    for p in results:
        lines.append(f"## Patient {p['patient_id']} — {p['patient_name']}")
        lines.append(f"**Chief complaint:** {p['chief_complaint']}\n")
        lines.append("| Budget | Median (s) | Min (s) | Quality /100 | Runs |")
        lines.append("|---|---|---|---|---|")
        for label, d in p["by_budget"].items():
            q = d.get("quality", {}).get("total", "-")
            lines.append(
                f"| {label} | {d['median_seconds']} | {d['min_seconds']} | {q} | {d['runs']} |"
            )
        lines.append("")
        for label, d in p["by_budget"].items():
            q = d.get("quality", {})
            score = q.get("total", "-")
            lines.append(f"### Output @ {label} — quality {score}/100")
            bd = q.get("breakdown")
            if bd:
                lines.append(
                    f"_structure {bd['structure']} · no_generic {bd['no_generic']} · "
                    f"specificity {bd['specificity']} · distinct {bd['distinct']} · "
                    f"no_alarming {bd['no_alarming']}_\n"
                )
            for area in d["top_3_action_areas"]:
                lines.append(f"- {area}")
            lines.append(f"\n_Next session plan:_ {d['next_session_plan']}")
            for v in q.get("violations", []):
                lines.append(f"  - ⚠️ {v}")
            lines.append("")
        lines.append("\n---\n")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="Benchmark RecommendationAgent thinking budgets (READ-ONLY).")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--patient-id", nargs="+", help="One or more patient ids (reads Mongo, read-only).")
    src.add_argument("--input-file", help="JSON file of pre-built patient_data (fully offline, no DB).")
    ap.add_argument("--budgets", default="auto,128,0",
                    help="Comma list of thinking budgets. 'auto' = current prod baseline. Default: auto,128,0")
    ap.add_argument("--repeat", type=int, default=2, help="Runs per budget per patient (for stable timings).")
    ap.add_argument("--max-tokens", type=int, default=None,
                    help="Override max output tokens for all agents this run "
                         "(e.g. 8192 to reproduce the current production baseline).")
    ap.add_argument("--out", help="Write a markdown comparison report to this path.")
    ap.add_argument("--json-out", help="Write raw results JSON to this path.")
    ap.add_argument("--dump-input", help="Save the fetched patient_data to this JSON (for offline re-runs).")
    args = ap.parse_args()

    budgets = [_parse_budget(t) for t in args.budgets.split(",") if t.strip()]

    if args.patient_id:
        inputs = _load_inputs_from_db(args.patient_id)
    else:
        inputs = _load_inputs_from_file(args.input_file)

    if not inputs:
        print("❌ No usable inputs — nothing to benchmark.")
        sys.exit(1)

    if args.dump_input:
        with open(args.dump_input, "w") as fh:
            json.dump(inputs, fh, indent=2, default=str)
        print(f"💾 Saved {len(inputs)} input(s) to {args.dump_input} (offline re-runs).")

    print(f"\n▶ Benchmarking {len(inputs)} patient(s) × budgets={[_budget_label(b) for b in budgets]} × repeat={args.repeat}")
    print("   (READ-ONLY: no collection writes, no prod config changes.)")

    results = benchmark(inputs, budgets, args.repeat, max_tokens=args.max_tokens)

    if args.json_out:
        with open(args.json_out, "w") as fh:
            json.dump(results, fh, indent=2, default=str)
        print(f"\n💾 Raw results → {args.json_out}")

    md = render_markdown(results)
    if args.out:
        with open(args.out, "w") as fh:
            fh.write(md)
        print(f"📄 Markdown report → {args.out}")
    else:
        print("\n" + md)


if __name__ == "__main__":
    main()
