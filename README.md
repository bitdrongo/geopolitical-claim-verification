# geopolitical-claim-verification

A single-turn verifiers environment that tests whether a model can correctly classify a factual geopolitical claim as `TRUE`, `FALSE`, `PARTIALLY_TRUE`, or `UNVERIFIED` by reasoning over a corpus of mixed-reliability sources.

The environment targets a real-world skill: separating well-supported claims from belligerent narrative warfare, single-source rumors, and partially-true statements where the headline is right but the details are disputed.

## Task

For each example the model receives:

- A specific factual claim with date and origin context.
- A list of sources, each tagged with a `type` (`think_tank_report`, `wire_service`, `belligerent_official`, `osint_account`, `state_media`, ...) and a `reliability_prior` in [0, 1].

The model must return a structured JSON object:

```json
{
  "verdict": "TRUE" | "FALSE" | "PARTIALLY_TRUE" | "UNVERIFIED",
  "confidence": 0.0,
  "supporting_source_ids": ["..."],
  "rationale": "...",
  "caveats": "..."
}
```

## Scoring rubric

Composite reward is the weighted sum of four components:

| Component             | Weight | Type           | What it measures |
|-----------------------|--------|----------------|------------------|
| `verdict_match`       | 0.4    | deterministic  | Exact match against gold verdict label |
| `source_weighting`    | 0.3    | LLM-judge      | Did the model weight reliable / independent sources higher than single-side belligerent statements? |
| `caveat_quality`      | 0.2    | LLM-judge      | Especially for `PARTIALLY_TRUE` and `UNVERIFIED`, did caveats reflect the required nuance? |
| `hallucination_check` | 0.1    | deterministic  | All `supporting_source_ids` cited by the model exist in the input source list |

The LLM-judge calls go through the Prime Intellect inference router (`https://api.pinference.ai/api/v1`), generating a double-signal of env author + inference user.

## Data

`data/placeholder_claims.json` ships with 5 hand-built smoke-test cases (RU-UA, Iran-Israel, oil/tanker). These exist to validate the env scaffold; a curated dataset of 50–100 real claims will replace them in the next phase.

Citations for the source archetypes used in test cases:

- **ISW** — Institute for the Study of War daily Russia/Ukraine and Iran updates: <https://www.understandingwar.org>
- **Reuters / AP / AFP** — wire services
- **Oryxspioenkop** — OSINT visual loss documentation
- **TankerTrackers / S&P Global / Lloyd's List** — maritime OSINT (used in oil/tanker case)
- **United Against Nuclear Iran (UANI)** — Iranian sanctions OSINT

## Running locally

```bash
uv venv --python 3.11 .venv
uv pip install --python .venv/bin/python verifiers datasets openai pytest
.venv/bin/pytest tests/test_smoke.py -s
```

`PRIME_KEY` must be available as an env var (or sourced inline from macOS Keychain via `security find-generic-password -s api_prime -w`).

## License

Apache License 2.0. See [LICENSE](LICENSE).
