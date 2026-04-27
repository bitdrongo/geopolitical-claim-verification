# Multi-model evaluation summary

Dataset: 22 claims, judge=qwen3-30b, sampling: max_tokens=2000 / temp=0.2.

## Models

| Model | Status | Mean composite | Verdict match | Source weighting | Caveat | Hallucination | Tokens (in/out) | Wall (s) | Cost ($) |
|---|---|---:|---:|---:|---:|---:|---|---:|---:|
| `google/gemini-2.5-pro` | ok | 0.892 | 0.909 | 0.761 | 1.000 | 1.000 | 24960 / 35444 | 211.2 | 0.3906 |
| `anthropic/claude-opus-4.7` | ok | 0.831 | 0.818 | 0.689 | 0.986 | 1.000 | 37502 / 7938 | 102.9 | 0.3910 |
| `prime-intellect/intellect-3` | ok | 0.763 | 0.636 | 0.711 | 0.977 | 1.000 | 23259 / 15687 | 119.0 | 0.0269 |
| `anthropic/claude-sonnet-4.6` | ok | 0.737 | 0.636 | 0.734 | 0.814 | 1.000 | 26033 / 8085 | 129.8 | 0.2044 |
| `qwen/qwen3-30b-a3b-instruct-2507` | ok | 0.729 | 0.636 | 0.605 | 0.964 | 1.000 | 23970 / 5253 | 69.5 | 0.0140 |
| `deepseek/deepseek-r1-0528` | ok | 0.725 | 0.636 | 0.568 | 1.000 | 1.000 | 23579 / 32647 | 206.3 | 0.3043 |
| `openai/gpt-5.2` | ok | 0.655 | 0.545 | 0.473 | 0.973 | 1.000 | 23071 / 10060 | 126.8 | 0.1862 |
| `PrimeIntellect/INTELLECT-3.1` | ok | 0.532 | 0.000 | 0.773 | 1.000 | 1.000 | 0 / 0 | 653.6 | 0.0050 |

## Per-claim verdict_match (1.0 = correct, 0.0 = wrong)

| claim_id | gold | INTELLECT-3.1 | opus-4.7 | sonnet-4.6 | ds-r1 | gemini-2.5-pro | gpt-5.2 | intellect-3 | qwen3-30b | n_correct |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `iran-israel-001` | TRUE | · | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | 6/8 |
| `iran-israel-002` | FALSE | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/8 |
| `iran-israel-003` | FALSE | · | ✓ | ✓ | ✓ | ✓ | ✓ | · | · | 5/8 |
| `iran-israel-004` | PARTIALLY_TRUE | · | · | · | ✓ | ✓ | · | · | ✓ | 3/8 |
| `iran-israel-005` | FALSE | · | ✓ | ✓ | · | ✓ | ✓ | · | · | 4/8 |
| `iran-israel-006` | TRUE | · | ✓ | · | ✓ | ✓ | · | ✓ | · | 4/8 |
| `iran-israel-007` | FALSE | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/8 |
| `iran-israel-008` | UNVERIFIED | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/8 |
| `iran-israel-009` | FALSE | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/8 |
| `iran-israel-010` | FALSE | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/8 |
| `iran-israel-011` | PARTIALLY_TRUE | · | ✓ | · | · | ✓ | · | · | · | 2/8 |
| `iran-israel-012` | FALSE | · | · | · | · | ✓ | · | · | ✓ | 2/8 |
| `iran-israel-013` | PARTIALLY_TRUE | · | · | · | · | · | · | · | ✓ | 1/8 |
| `iran-israel-014` | TRUE | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | · | 5/8 |
| `iran-israel-015` | FALSE | · | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | 6/8 |
| `iran-israel-016` | FALSE | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/8 |
| `iran-israel-017` | FALSE | · | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | 7/8 |
| `iran-israel-018` | TRUE | · | · | · | · | · | · | ✓ | · | 1/8 |
| `iran-israel-019` | FALSE | · | ✓ | ✓ | · | ✓ | ✓ | ✓ | ✓ | 6/8 |
| `iran-israel-020` | PARTIALLY_TRUE | · | ✓ | · | · | ✓ | ✓ | · | · | 3/8 |
| `iran-israel-021` | TRUE | · | ✓ | · | ✓ | ✓ | · | · | · | 3/8 |
| `iran-israel-022` | FALSE | · | ✓ | ✓ | ✓ | ✓ | · | ✓ | ✓ | 6/8 |

## Universally hard claims (all models wrong)

_None._

## Universally easy claims (all models correct)

_None._

## Per-model uniqueness (vs the 6+ other models)

| Model | Unique wins (only this model right) | Unique losses (only this model wrong) |
|---|---:|---:|
| `PrimeIntellect/INTELLECT-3.1` | 0: — | 7: iran-israel-002, iran-israel-007, iran-israel-008, iran-israel-009, iran-israel-010, iran-israel-016, iran-israel-017 |
| `anthropic/claude-opus-4.7` | 0: — | 0: — |
| `anthropic/claude-sonnet-4.6` | 0: — | 0: — |
| `deepseek/deepseek-r1-0528` | 0: — | 0: — |
| `google/gemini-2.5-pro` | 0: — | 0: — |
| `openai/gpt-5.2` | 0: — | 0: — |
| `prime-intellect/intellect-3` | 1: iran-israel-018 | 0: — |
| `qwen/qwen3-30b-a3b-instruct-2507` | 1: iran-israel-013 | 0: — |


## INTELLECT-3.1 status (as of 2026-04-27) — BROKEN AT PROVIDER

`PrimeIntellect/INTELLECT-3.1` returns **HTTP 500 `Internal Server Error`** on every tested configuration through the Prime Intellect inference router (`https://api.pinference.ai/api/v1/chat/completions`). The 22-claim eval row showing 0/0 token usage and `verdict_match=0.0` is the verifiers-framework artifact of every underlying call failing — not real model performance.

### Configurations tried (all returned HTTP 500)

| # | Variant | Sample request_id |
|---|---|---|
| a | Standard call: `{"model":"PrimeIntellect/INTELLECT-3.1","messages":[{"role":"user","content":"What is 2+2?"}],"max_tokens":100}` | `9f2ce815ae9811c9-KUL` |
| d | Same as (a) plus `"stream":true` | `9f2ce857cb345348-KUL` |
| e | `max_tokens=4096` | `9f2ce82fb95611c9-KUL` |
| f | System-only: `messages:[{"role":"system","content":"You are a helpful assistant."}]` | `9f2ce83818431be4-KUL` |
| g | `temperature=0, top_p=1.0` | `9f2ce8408e53ee09-KUL` |
| i | Reasoning-budget `max_tokens=8192, temperature=0` | `9f2ceb0648145e23-KUL` |
| j | Minimal payload: `{"model":"PrimeIntellect/INTELLECT-3.1","messages":[{"role":"user","content":"hi"}]}` | `9f2ceb0e9ac0454a-KUL` |

Body in every case:
```json
{"error":{"message":"Internal Server Error","type":"server_error","param":null,"code":"server_error"}}
```

Time-to-failure consistently ~1.3-1.5s, suggesting fast upstream rejection rather than runaway inference.

### Model-ID variants

| Variant | HTTP | Notes |
|---|---|---|
| `PrimeIntellect/INTELLECT-3.1` | 500 | Only registry-listed ID; broken |
| `primeintellect/intellect-3.1` | 404 | `model_not_found` |
| `prime-intellect/intellect-3.1` (hyphenated) | 404 | `model_not_found` |
| `prime-intellect/intellect-3` (sibling) | 200 | Works — returns reasoning-style response (content + reasoning fields) |

### Sibling success-case structure (for contrast)

`prime-intellect/intellect-3` with the same minimal payload returns HTTP 200 in ~3.4s with `message.content` (125 chars) and `message.reasoning` (652 chars) populated, `usage.cost = $0.0002`. Same registry, same key, same endpoint path — only the model ID differs.

### Disposition

This is a **provider-side fault**, not a client-side parsing issue. INTELLECT-3.1 is excluded from the comparison ranking above; rankings should be read against the seven working models. Recommended next step: report to Prime with the request_ids above so they can correlate against their backend logs.
