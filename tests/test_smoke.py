"""Smoke test: run the env on the 5 placeholder claims, print scores + token usage."""
from __future__ import annotations

import json
import os
import sys

import pytest
import verifiers as vf

from geopolitical_claim_verification import load_environment


PINFERENCE = "https://api.pinference.ai/api/v1"
SMOKE_MODEL = "qwen/qwen3-30b-a3b-instruct-2507"


@pytest.mark.skipif(not os.environ.get("PRIME_KEY"), reason="PRIME_KEY not set")
def test_smoke_run():
    env = load_environment()
    client_config = vf.ClientConfig(
        client_type="openai_chat_completions",
        api_key_var="PRIME_KEY",
        api_base_url=PINFERENCE,
    )

    results = env.evaluate_sync(
        client=client_config,
        model=SMOKE_MODEL,
        sampling_args={"max_tokens": 800, "temperature": 0.2},
        num_examples=-1,
        rollouts_per_example=1,
        max_concurrent=2,
    )

    print("\n" + "=" * 70)
    print("SMOKE RUN RESULTS")
    print("=" * 70)

    outputs = results.get("outputs", [])
    meta = results.get("metadata", {}) or {}

    n = len(outputs)
    rewards = [o.get("reward") for o in outputs]
    print(f"n_rollouts: {n}")
    print(f"composite_rewards: {rewards}")
    print(f"composite_mean: {meta.get('avg_reward')}")
    print(f"avg_metrics: {meta.get('avg_metrics')}")
    print(f"total token usage: {meta.get('usage')}")
    print(f"wall time (ms): {meta.get('time_ms')}")
    print(f"model: {meta.get('model')}  base_url: {meta.get('base_url')}")

    for i, o in enumerate(outputs):
        print("-" * 70)
        info = (o.get("info") or {})
        print(f"Example {i+1}: {info.get('claim_id','?')}  test_type={info.get('test_type','?')}")
        print(f"  reward={o.get('reward')}  metrics={o.get('metrics')}")
        comp = o.get("completion")
        if isinstance(comp, list):
            assistant = next((m for m in reversed(comp) if m.get("role") == "assistant"), None)
            content = (assistant or {}).get("content", "") if assistant else ""
        else:
            content = str(comp)
        if isinstance(content, list):
            content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
        print(f"  completion (first 400 chars): {str(content)[:400]}")
        tu = o.get("token_usage") or {}
        print(f"  per-rollout tokens: in={tu.get('input_tokens')} out={tu.get('output_tokens')}")

    sys.stdout.flush()
    assert n == 5, f"expected 5 rollouts, got {n}"
