#!/usr/bin/env python3
"""Aggregate per-model results into a comparison table + per-claim breakdown.

Reads data/multi_model_results/*.json (excluding _index.json), prints a markdown
report to stdout, and writes data/multi_model_summary.md.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "data" / "multi_model_results"
OUT_PATH = ROOT / "data" / "multi_model_summary.md"


def short_model(name: str) -> str:
    """Compact model display name for column headers."""
    base = name.split("/", 1)[-1]
    aliases = {
        "qwen3-30b-a3b-instruct-2507": "qwen3-30b",
        "prime-intellect/intellect-3": "intellect-3",
        "intellect-3": "intellect-3",
        "INTELLECT-3.1": "INTELLECT-3.1",
        "claude-sonnet-4.6": "sonnet-4.6",
        "claude-opus-4.7": "opus-4.7",
        "gpt-5.2": "gpt-5.2",
        "deepseek-r1-0528": "ds-r1",
        "gemini-2.5-pro": "gemini-2.5-pro",
    }
    return aliases.get(base, base[:18])


def main() -> int:
    files = sorted(p for p in RESULTS_DIR.glob("*.json") if p.name != "_index.json")
    runs = [json.loads(p.read_text()) for p in files]
    ok_runs = [r for r in runs if r.get("status") == "ok"]

    if not ok_runs:
        print("no successful runs found", file=sys.stderr)
        return 1

    lines: list[str] = []
    add = lines.append

    # --- comparison table ---
    add("# Multi-model evaluation summary\n")
    add(f"Dataset: 22 claims, judge=qwen3-30b, sampling: max_tokens=2000 / temp=0.2.\n")

    add("## Models\n")
    add("| Model | Status | Mean composite | Verdict match | Source weighting | Caveat | Hallucination | Tokens (in/out) | Wall (s) | Cost ($) |")
    add("|---|---|---:|---:|---:|---:|---:|---|---:|---:|")
    for r in sorted(runs, key=lambda x: -float(x.get("mean_composite") or 0)):
        if r.get("status") != "ok":
            err = r.get("error", "?")[:60]
            add(f"| `{r['model']}` | **{r.get('status')}** ({err}) | — | — | — | — | — | — | — | — |")
            continue
        m = r.get("avg_metrics") or {}
        tt = r.get("tokens_total") or {}
        wall = (r.get("wall_time_ms") or 0) / 1000
        add(
            f"| `{r['model']}` | ok "
            f"| {r['mean_composite']:.3f} "
            f"| {m.get('verdict_match', 0):.3f} "
            f"| {m.get('source_weighting', 0):.3f} "
            f"| {m.get('caveat_quality', 0):.3f} "
            f"| {m.get('hallucination_check', 0):.3f} "
            f"| {tt.get('in', 0):.0f} / {tt.get('out', 0):.0f} "
            f"| {wall:.1f} "
            f"| {r['estimated_cost_usd']:.4f} |"
        )
    add("")

    # --- per-claim verdict_match breakdown ---
    # Build {claim_id: {model_name: verdict_match_score}}
    claim_ids: list[str] = []
    test_types: dict[str, str] = {}
    gold_verdicts: dict[str, str] = {}
    matrix: dict[str, dict[str, float]] = {}

    for r in ok_runs:
        for c in r.get("per_claim", []):
            cid = c.get("claim_id")
            if cid is None:
                continue
            if cid not in matrix:
                matrix[cid] = {}
                claim_ids.append(cid)
                test_types[cid] = c.get("test_type", "")
                gold_verdicts[cid] = c.get("gold_verdict", "")
            matrix[cid][r["model"]] = float(c.get("metrics", {}).get("verdict_match", 0))

    model_cols = [r["model"] for r in ok_runs]
    short_cols = [short_model(m) for m in model_cols]

    add("## Per-claim verdict_match (1.0 = correct, 0.0 = wrong)\n")
    header = "| claim_id | gold | " + " | ".join(short_cols) + " | n_correct |"
    add(header)
    add("|---" + ("|---:" * (1 + len(model_cols))) + "|---:|")

    for cid in claim_ids:
        row = matrix[cid]
        cells = ["✓" if row.get(m, 0) >= 0.5 else "·" for m in model_cols]
        n_correct = sum(1 for m in model_cols if row.get(m, 0) >= 0.5)
        add(f"| `{cid}` | {gold_verdicts[cid]} | " + " | ".join(cells) + f" | {n_correct}/{len(model_cols)} |")
    add("")

    # --- universally hard / easy claims ---
    n_models = len(model_cols)
    all_fail = [cid for cid in claim_ids if all(matrix[cid].get(m, 0) < 0.5 for m in model_cols)]
    all_pass = [cid for cid in claim_ids if all(matrix[cid].get(m, 0) >= 0.5 for m in model_cols)]

    add("## Universally hard claims (all models wrong)\n")
    if all_fail:
        for cid in all_fail:
            add(f"- `{cid}` (gold={gold_verdicts[cid]}, type={test_types[cid]}) — potential gold-label issue OR truly adversarial")
    else:
        add("_None._")
    add("")

    add("## Universally easy claims (all models correct)\n")
    if all_pass:
        for cid in all_pass:
            add(f"- `{cid}` (gold={gold_verdicts[cid]}, type={test_types[cid]}) — discriminates poorly between models")
    else:
        add("_None._")
    add("")

    # --- per-model unique wins / losses ---
    add("## Per-model uniqueness (vs the 6+ other models)\n")
    add("| Model | Unique wins (only this model right) | Unique losses (only this model wrong) |")
    add("|---|---:|---:|")
    for m in model_cols:
        wins = []
        losses = []
        for cid in claim_ids:
            row = matrix[cid]
            others_right = sum(1 for mm in model_cols if mm != m and row.get(mm, 0) >= 0.5)
            others_wrong = (len(model_cols) - 1) - others_right
            mine = row.get(m, 0) >= 0.5
            if mine and others_right == 0:
                wins.append(cid)
            if (not mine) and others_wrong == 0:
                losses.append(cid)
        add(f"| `{m}` | {len(wins)}: {', '.join(wins) or '—'} | {len(losses)}: {', '.join(losses) or '—'} |")
    add("")

    out = "\n".join(lines) + "\n"
    OUT_PATH.write_text(out)
    print(out)
    print(f"\nWrote {OUT_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
