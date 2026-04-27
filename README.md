# geopolitical-claim-verification

A single-turn verifiers environment that tests whether a model can correctly classify a factual geopolitical claim as `TRUE`, `FALSE`, `PARTIALLY_TRUE`, or `UNVERIFIED` by reasoning over a corpus of mixed-reliability sources under realistic adversarial conditions.

The benchmark targets a real-world skill: separating well-supported claims from belligerent narrative warfare, single-source rumors, partially-true statements where the headline is right but the details are disputed, and source-poisoned propaganda framings.

## Dataset

- **22 hand-curated claims** anchored on the Operation Epic Fury period (US–Iran conflict, February–April 2026).
- Sources include: Trump Truth Social posts, Iranian Supreme National Security Council statements (Araghchi), Pakistani mediator statements (Sharif), Polymarket market resolutions and rules, contemporaneous wire / think-tank reporting.
- **Verdict distribution** (intentionally FALSE-skewed — emphasizes the adversarial reasoning patterns where common heuristics fail):

  | Verdict | Count | % |
  |---|---:|---:|
  | TRUE | 5 | 23% |
  | FALSE | 12 | 55% |
  | PARTIALLY_TRUE | 4 | 18% |
  | UNVERIFIED | 1 | 5% |

The full schema for a claim entry is in [`data/SCHEMA.md`](data/SCHEMA.md). Skeletons for future expansion (Russia–Ukraine, oil/tanker OSINT) are preserved under [`data/_skeletons/`](data/_skeletons/).

## Reasoning patterns tested

The 22 claims were designed to stress seven distinct failure modes that frontier models commonly miss:

1. **Temporal-deadline precision** — distinguishing "X happened by date D" from "X happened after D" (e.g. ceasefire by March 31 vs April 8).
2. **Definitional gap, broad vs narrow target** — "Kharg Island was hit" (broad, TRUE) vs "Kharg Island oil terminal was hit" (specific subset, FALSE).
3. **Threats vs actions** — distinguishing a conditional future threat from an executed order.
4. **Unilateral action vs mutual agreement** — a head-of-state extending their own pause is not the same as a bilateral ceasefire extension.
5. **Source-poisoning recognition** — rejecting clusters of one-sided belligerent or state-media sources as insufficient regardless of count.
6. **Belligerent claim contradicted by counterparty behavior** — Trump's "Iran is fractured" is FALSE, not UNVERIFIED, when Iran's documented diplomatic activity contradicts it.
7. **Prediction-market source calibration** — treating Polymarket resolutions and rules as authoritative evidence (the dataset uses them as primary sources for many event-claims).

## Verdict labels — strict definitions

The dataset enforces strict label semantics (see [`data/SCHEMA.md`](data/SCHEMA.md) for the full spec):

- **`TRUE`** — well-supported by reliable, independent sources. `supporting_source_ids` lists only sources that affirmatively support the claim.
- **`FALSE`** — reliable sources contradict the claim. `supporting_source_ids` lists only sources that affirmatively contradict.
- **`PARTIALLY_TRUE`** — the core event is confirmed but key details (target identity, scope, timing, casualties, attribution) are disputed. `supporting_source_ids` lists only sources supporting the TRUE component; contradicting / qualifying sources go in `caveats`.
- **`UNVERIFIED`** — *absence* of evidence, not *presence* of contradicting evidence. Reserved for cases of insufficient evidence: single-source belligerent claim with no corroboration, source-poisoning, or genuine epistemic uncertainty. `supporting_source_ids` MUST be `[]`. If any source contradicts the claim, the verdict is `FALSE` or `PARTIALLY_TRUE`, not `UNVERIFIED`. *(`UNVERIFIED` = absence of evidence; `FALSE` = presence of contradicting evidence — these are categorically different epistemic states.)*

## Scoring rubric

Composite reward is the weighted sum of four components:

| Component | Weight | Type | What it measures |
|---|---:|---|---|
| `verdict_match` | 0.4 | deterministic | Exact match against gold verdict label |
| `source_weighting` | 0.3 | LLM-judge (+ deterministic shortcut for `UNVERIFIED`) | Did the model select `supporting_source_ids` per the strict per-verdict semantics, weighting reliable / independent sources higher than single-side belligerent statements? |
| `caveat_quality` | 0.2 | LLM-judge | Especially for `PARTIALLY_TRUE` and `UNVERIFIED`, did caveats reflect the required nuance? |
| `hallucination_check` | 0.1 | deterministic | All `supporting_source_ids` cited by the model exist in the input source list |

LLM-judge calls go through the Prime Intellect inference router (`https://api.pinference.ai/api/v1`) using **`qwen/qwen3-30b-a3b-instruct-2507`** as judge — chosen for cost-effectiveness and consistency. Routing through pinference also generates a double-signal (env author + inference user) for provenance.

## Multi-model evaluation results

Evaluated **2026-04-27** through the Prime Intellect inference router. All models tested with identical 22-claim dataset, identical system prompt, identical judge model (qwen3-30b), and identical sampling args (`max_tokens=2000, temperature=0.2`).

| Rank | Model | Composite | Verdict match | Source weight | Caveat | Halluc | Cost (22 claims) |
|---:|---|---:|---:|---:|---:|---:|---:|
| 1 | `google/gemini-2.5-pro` | **0.892** | **91%** | 0.761 | 1.000 | 1.000 | $0.391 |
| 2 | `anthropic/claude-opus-4.7` | 0.831 | 82% | 0.689 | 0.986 | 1.000 | $0.391 |
| 3 | `prime-intellect/intellect-3` | 0.763 | 64% | 0.711 | 0.977 | 1.000 | **$0.027** |
| 4 | `anthropic/claude-sonnet-4.6` | 0.737 | 64% | 0.734 | 0.814 | 1.000 | $0.204 |
| 5 | `qwen/qwen3-30b-a3b-instruct-2507` | 0.729 | 64% | 0.605 | 0.964 | 1.000 | $0.014 |
| 6 | `deepseek/deepseek-r1-0528` | 0.725 | 64% | 0.568 | 1.000 | 1.000 | $0.304 |
| 7 | `openai/gpt-5.2` | 0.655 | 55% | 0.473 | 0.973 | 1.000 | $0.186 |
| † | `PrimeIntellect/INTELLECT-3.1` | broken | broken | broken | — | — | — |

† **`INTELLECT-3.1` returns HTTP 500 across all tested configurations** on the pinference router — 8 distinct request_ids documented in [`data/multi_model_summary.md`](data/multi_model_summary.md). Likely a server-side dispatch crash on this specific model (sibling `prime-intellect/intellect-3` works correctly through the same key + endpoint). Bug report drafted; will re-run on resolution.

Full per-claim breakdown, per-model uniqueness analysis, and INTELLECT-3.1 diagnostic detail in [`data/multi_model_summary.md`](data/multi_model_summary.md).

## Notable findings

- **Gemini 2.5 Pro consistently outperforms** other frontier models on definitional-precision cases (ceasefire vs peace deal, broad-vs-narrow target subset, unilateral-vs-mutual agreement).
- **Most models systematically fail at distinguishing FALSE-by-evidence-contradiction from UNVERIFIED-by-evidence-absence** (claims `iran-israel-003`, `005`, `011`). They default to `UNVERIFIED` when the corpus is small, even when sources actively contradict the claim through their own framing.
- **Prediction-market-as-primary-source claims are systematically undervalued** by most models (claims `iran-israel-018`, `021`). Models discount Polymarket resolutions even at high `reliability_prior` and prefer wire-service confirmation that doesn't exist in the corpus.
- **`prime-intellect/intellect-3` offers the strongest cost / performance ratio** on this benchmark — 3rd place composite at **14× cheaper than Sonnet 4.6** and 7× cheaper than Opus 4.7 / Gemini 2.5 Pro.
- **GPT-5.2 underperforms unexpectedly** (7th of 7 working models), particularly on `source_weighting` (0.473 vs 0.6–0.76 typical for the others).

## Usage

Install and run locally:

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python verifiers datasets openai pytest

# Smoke test on the placeholder dataset (5 claims) — no PRIME_KEY needed if you skip
PRIME_KEY=$(security find-generic-password -s api_prime -w) \
  .venv/bin/pytest tests/test_smoke.py -s

# Full 22-claim run on the curated dataset:
CLAIMS_PATH=data/claims.json \
PRIME_KEY=$(security find-generic-password -s api_prime -w) \
  .venv/bin/pytest tests/test_smoke.py -s

# Multi-model comparison (8 models, sequential, ~$1.50 total):
PRIME_KEY=$(security find-generic-password -s api_prime -w) \
  .venv/bin/python scripts/multi_model_eval.py --cap 4

# Aggregate the per-model results into data/multi_model_summary.md:
.venv/bin/python scripts/aggregate_results.py
```

`PRIME_KEY` must be available as an env var — typically sourced inline from macOS Keychain via `security find-generic-password -s api_prime -w` so it never lands in shell history or env-dump.

To validate or extend the dataset:

```bash
# Validate full dataset envelope or single-claim files
.venv/bin/python scripts/validate_dataset.py data/claims.json
.venv/bin/python scripts/validate_dataset.py data/_skeletons/ru-ua/<file>.json

# Dry-mode cost estimate (no API calls)
.venv/bin/python scripts/cost_estimator.py --mode dry data/claims.json

# After filling more skeletons, merge them into the canonical claims.json
.venv/bin/python scripts/merge_curated.py
```

## Citation

```
bitdrongo/geopolitical-claim-verification, April 2026.
GitHub: https://github.com/bitdrongo/geopolitical-claim-verification
```

## License

Apache License 2.0. See [LICENSE](LICENSE).
