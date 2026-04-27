#!/usr/bin/env python3
"""Run all claims through each model on the Prime Intellect inference router.

Sequential. Per-model results are saved to data/multi_model_results/<slug>.json.
Stops if accumulated estimated cost exceeds the cap.

Usage:
    PRIME_KEY=$(security find-generic-password -s api_prime -w) \\
        python scripts/multi_model_eval.py [--cap 4] [--max-tokens 2000]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import verifiers as vf  # noqa: E402
from geopolitical_claim_verification import load_environment  # noqa: E402

PINFERENCE = "https://api.pinference.ai/api/v1"

# USD per 1M tokens (input, output) — pulled from `prime inference models --plain --output json`.
MODEL_PRICING = {
    "qwen/qwen3-30b-a3b-instruct-2507": (0.20, 0.80),
    "prime-intellect/intellect-3": (0.20, 1.10),
    "PrimeIntellect/INTELLECT-3.1": (0.10, 0.20),
    "anthropic/claude-sonnet-4.6": (3.00, 15.00),
    "anthropic/claude-opus-4.7": (5.00, 25.00),
    "openai/gpt-5.2": (1.75, 14.00),
    "deepseek/deepseek-r1-0528": (3.00, 7.00),
    "google/gemini-2.5-pro": (1.25, 10.00),
}

# Run cheap models first so a later cap-exceeded stop loses the most-expensive runs first.
DEFAULT_MODELS = [
    "qwen/qwen3-30b-a3b-instruct-2507",
    "PrimeIntellect/INTELLECT-3.1",
    "prime-intellect/intellect-3",
    "google/gemini-2.5-pro",
    "openai/gpt-5.2",
    "anthropic/claude-sonnet-4.6",
    "deepseek/deepseek-r1-0528",
    "anthropic/claude-opus-4.7",
]

# Rough per-model-run judge cost (qwen3-30b judge over ~26 calls of ~600 in / 80 out).
JUDGE_COST_PER_RUN = 0.005


def model_slug(model: str) -> str:
    return model.replace("/", "_").replace(":", "-")


def cost_for(model: str, in_tokens: float, out_tokens: float) -> float:
    pin, pout = MODEL_PRICING.get(model, (0.0, 0.0))
    return (in_tokens * pin + out_tokens * pout) / 1e6


def run_model(env, model: str, client_config, max_tokens: int, max_concurrent: int) -> dict:
    print(f"\n{'='*72}\n  {model}\n{'='*72}", flush=True)
    started = datetime.now(timezone.utc).isoformat()
    try:
        results = env.evaluate_sync(
            client=client_config,
            model=model,
            sampling_args={"max_tokens": max_tokens, "temperature": 0.2},
            num_examples=-1,
            rollouts_per_example=1,
            max_concurrent=max_concurrent,
            max_retries=1,
        )
    except Exception as e:
        msg = f"{type(e).__name__}: {e}"
        print(f"  FAILED: {msg}", flush=True)
        return {
            "model": model,
            "started_utc": started,
            "status": "failed",
            "error": msg,
        }

    meta = dict(results.get("metadata") or {})
    outputs = list(results.get("outputs") or [])
    if not outputs:
        return {"model": model, "started_utc": started, "status": "empty", "error": "no outputs"}

    per_claim = []
    total_in = 0.0
    total_out = 0.0
    for o in outputs:
        info = dict(o.get("info") or {})
        tu = dict(o.get("token_usage") or {})
        in_t = float(tu.get("input_tokens") or 0)
        out_t = float(tu.get("output_tokens") or 0)
        total_in += in_t
        total_out += out_t
        per_claim.append(
            {
                "claim_id": info.get("claim_id"),
                "test_type": info.get("test_type"),
                "gold_verdict": (o.get("answer") or {}).get("verdict"),
                "reward": o.get("reward"),
                "metrics": dict(o.get("metrics") or {}),
                "token_usage": tu,
            }
        )

    rollout_cost = cost_for(model, total_in, total_out)
    total_cost = rollout_cost + JUDGE_COST_PER_RUN
    avg_reward = float(meta.get("avg_reward") or 0.0)
    avg_metrics = dict(meta.get("avg_metrics") or {})

    print(f"  mean_composite:   {avg_reward:.3f}", flush=True)
    print(f"  verdict_match:    {avg_metrics.get('verdict_match', 0):.3f}", flush=True)
    print(f"  source_weighting: {avg_metrics.get('source_weighting', 0):.3f}", flush=True)
    print(f"  rollout_tokens:   in={total_in:.0f}  out={total_out:.0f}", flush=True)
    print(f"  rollout_cost:     ${rollout_cost:.4f}", flush=True)
    print(f"  est_total_cost:   ${total_cost:.4f}  (incl ~${JUDGE_COST_PER_RUN:.3f} judges)", flush=True)

    return {
        "model": model,
        "started_utc": started,
        "status": "ok",
        "n_rollouts": len(outputs),
        "mean_composite": avg_reward,
        "avg_metrics": avg_metrics,
        "per_claim": per_claim,
        "tokens_total": {"in": total_in, "out": total_out},
        "estimated_cost_usd": total_cost,
        "wall_time_ms": meta.get("time_ms"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cap", type=float, default=4.0, help="USD cost cap; stop when crossed")
    ap.add_argument("--max-tokens", type=int, default=2000, help="sampling max_tokens (higher for reasoning models)")
    ap.add_argument("--max-concurrent", type=int, default=2)
    ap.add_argument("--data", default=str(ROOT / "data" / "claims.json"))
    ap.add_argument("--models", nargs="*", default=DEFAULT_MODELS)
    args = ap.parse_args()

    if not os.environ.get("PRIME_KEY"):
        print("PRIME_KEY not set", file=sys.stderr)
        return 2

    out_dir = ROOT / "data" / "multi_model_results"
    out_dir.mkdir(parents=True, exist_ok=True)

    env = load_environment(data_path=args.data)
    client_config = vf.ClientConfig(
        client_type="openai_chat_completions",
        api_key_var="PRIME_KEY",
        api_base_url=PINFERENCE,
    )

    running_cost = 0.0
    summary = []
    for model in args.models:
        if running_cost >= args.cap:
            print(
                f"\nCOST CAP REACHED: ${running_cost:.4f} >= ${args.cap:.2f}. Stopping.",
                flush=True,
            )
            break
        res = run_model(env, model, client_config, args.max_tokens, args.max_concurrent)
        summary.append(res)
        slug = model_slug(model)
        (out_dir / f"{slug}.json").write_text(json.dumps(res, indent=2, ensure_ascii=False) + "\n")
        if res.get("status") == "ok":
            running_cost += res["estimated_cost_usd"]
        print(f"  running_total_cost: ${running_cost:.4f} / ${args.cap:.2f}", flush=True)

    # Store data_path relative to repo root so it doesn't leak the local username/path.
    try:
        rel_data = str(Path(args.data).resolve().relative_to(ROOT))
    except ValueError:
        rel_data = args.data
    index = {
        "data_path": rel_data,
        "cost_cap_usd": args.cap,
        "running_cost_usd": round(running_cost, 6),
        "max_tokens": args.max_tokens,
        "models_attempted": [s["model"] for s in summary],
        "models_succeeded": [s["model"] for s in summary if s.get("status") == "ok"],
        "models_failed": [s["model"] for s in summary if s.get("status") != "ok"],
    }
    (out_dir / "_index.json").write_text(json.dumps(index, indent=2) + "\n")

    print(f"\nDone.")
    print(f"  ok: {len(index['models_succeeded'])}  failed: {len(index['models_failed'])}")
    print(f"  total estimated cost: ${running_cost:.4f}")
    print(f"  results dir: {out_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
