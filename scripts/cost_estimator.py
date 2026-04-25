#!/usr/bin/env python3
"""Estimate the inference cost of a full eval run on a claim dataset.

Strategies:
  1. dry: count tokens locally (rough), apply per-token pricing.
  2. live: actually call the model on a sample of N claims, sum the `cost`
     fields returned by the Prime Intellect inference router, and extrapolate.

Both modes account for the model rollout AND the LLM-judge calls
(source_weighting + caveat_quality, with caveat_quality firing only on
PARTIALLY_TRUE / UNVERIFIED claims, source_weighting deterministic on
UNVERIFIED so no judge call there).

Usage:
    PRIME_KEY=$(security find-generic-password -s api_prime -w) \\
        python scripts/cost_estimator.py [--mode dry|live] [--sample N] [PATH]

PATH defaults to data/placeholder_claims.json.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# Pricing for qwen3-30b-a3b-instruct-2507 on api.pinference.ai
INPUT_USD_PER_1M = 0.20
OUTPUT_USD_PER_1M = 0.80


def _approx_tokens(text: str) -> int:
    """Rough char/4 heuristic. Good enough for dry-run estimates."""
    return max(1, len(text) // 4)


def _per_claim_token_estimate(claim: dict, system_prompt_chars: int) -> dict:
    """Approximate per-claim tokens for model + judge calls."""
    sources_chars = sum(len(s.get("text", "")) for s in claim.get("sources", []))
    prompt_chars = system_prompt_chars + sources_chars + len(claim.get("claim", "")) + 200
    in_model = _approx_tokens(str(prompt_chars))
    out_model = 250  # observed median completion size
    in_judge = _approx_tokens(str(prompt_chars + 600))  # judge sees claim + sources + model output
    out_judge = 80

    verdict = claim.get("gold", {}).get("verdict", "")
    judges = 1  # source_weighting always (except UNVERIFIED, deterministic)
    if verdict == "UNVERIFIED":
        judges = 0
    if verdict in ("PARTIALLY_TRUE", "UNVERIFIED"):
        judges += 1  # caveat_quality

    in_total = prompt_chars // 4 + judges * in_judge
    out_total = out_model + judges * out_judge
    return {"in": in_total, "out": out_total, "judges": judges}


def _system_prompt_chars() -> int:
    """Read SYSTEM_PROMPT length from the env module without importing it (no PRIME_KEY needed)."""
    env_path = Path(__file__).resolve().parent.parent / "geopolitical_claim_verification.py"
    src = env_path.read_text()
    m = src.split('SYSTEM_PROMPT = """', 1)
    if len(m) < 2:
        return 1500
    end = m[1].find('"""')
    return end if end > 0 else 1500


def dry_estimate(claims: list[dict]) -> dict:
    sp = _system_prompt_chars()
    rows = [_per_claim_token_estimate(c, sp) for c in claims]
    in_tot = sum(r["in"] for r in rows)
    out_tot = sum(r["out"] for r in rows)
    judges = sum(r["judges"] for r in rows)
    cost = in_tot * INPUT_USD_PER_1M / 1e6 + out_tot * OUTPUT_USD_PER_1M / 1e6
    return {
        "mode": "dry",
        "claims": len(claims),
        "judge_calls": judges,
        "tokens_in": in_tot,
        "tokens_out": out_tot,
        "cost_usd": round(cost, 6),
    }


def live_estimate(claims: list[dict], sample: int) -> dict:
    """Actually run the env on `sample` claims and sum the API-reported `cost` fields."""
    sample = max(1, min(sample, len(claims)))
    subset = claims[:sample]

    # Local import: avoids requiring PRIME_KEY for dry mode
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from datasets import Dataset  # noqa
    import verifiers as vf  # noqa
    from geopolitical_claim_verification import (  # noqa
        SYSTEM_PROMPT,
        format_prompt,
        load_environment,
    )

    if not os.environ.get("PRIME_KEY"):
        print("PRIME_KEY not set; cannot run live estimate", file=sys.stderr)
        sys.exit(2)

    # Build a transient dataset from the sample
    rows = []
    for c in subset:
        rows.append(
            {
                "prompt": [{"role": "user", "content": format_prompt(c)}],
                "answer": c["gold"],
                "info": {
                    "claim_id": c["claim_id"],
                    "claim": c["claim"],
                    "sources": c["sources"],
                    "all_source_ids": [s["id"] for s in c["sources"]],
                    "test_type": c.get("test_type", ""),
                },
                "task": "geopolitical-claim-verification",
            }
        )

    env = load_environment()
    # Replace the dataset in-place with our subset
    env.dataset = Dataset.from_list(rows)
    env.eval_dataset = Dataset.from_list(rows)

    client_config = vf.ClientConfig(
        client_type="openai_chat_completions",
        api_key_var="PRIME_KEY",
        api_base_url="https://api.pinference.ai/api/v1",
    )
    results = env.evaluate_sync(
        client=client_config,
        model="qwen/qwen3-30b-a3b-instruct-2507",
        sampling_args={"max_tokens": 800, "temperature": 0.2},
        num_examples=-1,
        rollouts_per_example=1,
        max_concurrent=2,
    )

    meta = results.get("metadata", {}) or {}
    usage = meta.get("usage") or {}
    in_per_call = float(usage.get("input_tokens") or 0)
    out_per_call = float(usage.get("output_tokens") or 0)

    # Extrapolate to full dataset
    n_full = len(claims)
    scale = n_full / sample if sample else 0
    in_tot_full = in_per_call * sample * scale
    out_tot_full = out_per_call * sample * scale
    sample_cost = (in_per_call * sample) * INPUT_USD_PER_1M / 1e6 + (
        out_per_call * sample
    ) * OUTPUT_USD_PER_1M / 1e6
    full_cost = sample_cost * scale

    return {
        "mode": "live",
        "sample_claims": sample,
        "full_claims": n_full,
        "sample_avg_in_per_call": in_per_call,
        "sample_avg_out_per_call": out_per_call,
        "sample_total_cost_usd": round(sample_cost, 6),
        "extrapolated_full_cost_usd": round(full_cost, 6),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", nargs="?", default="data/placeholder_claims.json")
    ap.add_argument("--mode", choices=["dry", "live"], default="dry")
    ap.add_argument("--sample", type=int, default=5, help="live mode: sample N claims to extrapolate from")
    args = ap.parse_args()

    p = Path(args.path)
    if not p.exists():
        print(f"file not found: {p}", file=sys.stderr)
        return 1

    data = json.loads(p.read_text())
    claims = data.get("claims") or []
    if not claims:
        print("no claims in dataset", file=sys.stderr)
        return 1

    out = (dry_estimate(claims) if args.mode == "dry" else live_estimate(claims, args.sample))
    out["dataset"] = str(p)
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
