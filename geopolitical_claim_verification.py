"""geopolitical-claim-verification: a single-turn verifiers environment.

The model is shown one factual geopolitical claim plus a list of sources
with type and reliability_prior metadata, and must classify the claim as
TRUE / FALSE / PARTIALLY_TRUE / UNVERIFIED with rationale and caveats.

Composite reward (weights):
  verdict_match       0.4   deterministic exact-match against gold label
  source_weighting    0.3   LLM-judge over reliability of cited sources
  caveat_quality      0.2   LLM-judge over caveat nuance (esp. PT / UV)
  hallucination_check 0.1   deterministic: cited source ids exist in input

The judge LLM is called via the Prime Intellect inference router so the env
generates a double-signal of env author + inference user.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import verifiers as vf
from datasets import Dataset
from openai import AsyncOpenAI


SYSTEM_PROMPT = """You are an analyst evaluating factual claims about geopolitical events.

You will be given:
- A specific factual claim with date and origin context.
- A list of sources, each with `id`, `type`, and `reliability_prior` between 0 and 1. Source types include:
    think_tank_report, wire_service, belligerent_official, osint_account, state_media,
    head_of_state_statement (a head of state speaking about own state's actions — high signal that the action was taken, but framing biased toward own narrative),
    mediator_statement (an official statement from a third-party mediator — usually high credibility for confirming agreements and de-escalation),
    prediction_market_resolution (the outcome of a regulated prediction market like Polymarket / Kalshi / UMA Optimistic Oracle — reflects aggregated public information at resolution time).

Classify the claim into exactly one of:
- TRUE          - well-supported by reliable, independent sources.
- FALSE         - reliable sources contradict the claim.
- PARTIALLY_TRUE- the core event is confirmed but key details (target identity, scope, timing, casualties, attribution) are disputed.
- UNVERIFIED    - sources are insufficient, only one-sided belligerent or state-media statements, or no independent corroboration.

Source weighting principles:
- Wire services (Reuters/AP/AFP) and well-regarded think tanks (ISW) carry the most weight.
- A single belligerent_official or state_media source is INSUFFICIENT to call something TRUE - treat as UNVERIFIED unless an independent source confirms.
- Sources from only one side of a conflict do not establish independent verification, no matter how many of them there are.
- OSINT accounts vary; trust depends on reliability_prior.

`supporting_source_ids` semantics — strict, depends on verdict:
- TRUE          : list ONLY sources that affirmatively support the claim.
- FALSE         : list ONLY sources that affirmatively contradict the claim.
- PARTIALLY_TRUE: list ONLY sources that support the TRUE component of the claim. Sources contradicting or qualifying the disputed details go in `caveats`, not here.
- UNVERIFIED    : MUST be an empty list `[]`. Sources you considered but rejected (e.g. a single belligerent statement) belong in `rationale`, not in this field. If you find yourself wanting to list anything here, your verdict is probably wrong.

Output format - return ONLY a single JSON object inside a ```json fenced block, with these exact keys:
{
  "verdict": "TRUE" | "FALSE" | "PARTIALLY_TRUE" | "UNVERIFIED",
  "confidence": 0.0,
  "supporting_source_ids": ["<source id>", ...],
  "rationale": "<short explanation citing specific source ids>",
  "caveats": "<any caveats, especially for PARTIALLY_TRUE / UNVERIFIED>"
}

Do not include any text outside the json fenced block.
"""


JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(\{.*?\})\s*```", re.DOTALL)


def extract_json(text: str) -> str:
    """Return the JSON object from inside a ```json``` fence, or a best-effort top-level {...}."""
    if not text:
        return ""
    m = JSON_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    start = text.find("{")
    if start == -1:
        return ""
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1].strip()
    return ""


def safe_load_json(text: str) -> dict | None:
    if not text:
        return None
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else None
    except Exception:
        return None


DEFAULT_RELIABILITY_PRIOR = {
    "wire_service": 0.90,
    "think_tank_report": 0.85,
    "academic_or_legal": 0.90,
    "head_of_state_statement": 0.65,
    "mediator_statement": 0.80,
    "prediction_market_resolution": 0.85,
    "prediction_market_rules": 0.95,
    "osint_account": 0.65,
    "belligerent_official": 0.50,
    "state_media": 0.30,
    "belligerent_state_media": 0.20,
    "anonymous_social_media": 0.15,
    "absence_of_evidence": 0.60,
}


def _resolved_prior(s: dict) -> float:
    rp = s.get("reliability_prior")
    if isinstance(rp, (int, float)):
        return float(rp)
    return DEFAULT_RELIABILITY_PRIOR.get(s.get("type", ""), 0.5)


def _format_sources(sources: list[dict]) -> str:
    out = []
    for s in sources:
        meta_lines = [
            f"  type: {s['type']}",
            f"  reliability_prior: {_resolved_prior(s)}",
        ]
        if s.get("date"):
            meta_lines.append(f"  date: {s['date']}")
        if s.get("publisher"):
            meta_lines.append(f"  publisher: {s['publisher']}")
        meta_lines.append(f"  text: {s['text']}")
        out.append(f"- id: `{s['id']}`\n" + "\n".join(meta_lines))
    return "\n\n".join(out)


def _normalize_caveat(gold: dict) -> str:
    """Accept either `must_cite_caveat_about: str` or `required_caveats: list[str]`."""
    parts: list[str] = []
    s = gold.get("must_cite_caveat_about")
    if isinstance(s, str) and s.strip():
        parts.append(s.strip())
    lst = gold.get("required_caveats")
    if isinstance(lst, list):
        parts.extend(x.strip() for x in lst if isinstance(x, str) and x.strip())
    return " ".join(parts)


def _enriched_sources(sources: list[dict]) -> list[dict]:
    """Mirror sources into info with reliability_prior filled in from defaults if missing."""
    out = []
    for s in sources:
        d = dict(s)
        d["reliability_prior"] = _resolved_prior(s)
        out.append(d)
    return out


def format_prompt(row: dict) -> str:
    return (
        f"# Claim\n{row['claim']}\n\n"
        f"Claim date (UTC): {row['claim_date_utc']}\n"
        f"Origin context: {row.get('claim_origin', '(unspecified)')}\n\n"
        f"# Sources\n{_format_sources(row['sources'])}\n\n"
        "Classify the claim per the system instructions."
    )


JUDGE_SYSTEM = (
    "You are a strict evaluator of analyst reasoning about geopolitical claims. "
    "Return ONLY a single JSON object with keys 'score' (float 0.0-1.0) and 'reason' (one sentence). "
    "No other text."
)


async def _judge(judge_client: AsyncOpenAI, judge_model: str, instruction: str) -> float:
    try:
        resp = await judge_client.chat.completions.create(
            model=judge_model,
            messages=[
                {"role": "system", "content": JUDGE_SYSTEM},
                {"role": "user", "content": instruction},
            ],
            max_tokens=200,
            temperature=0,
        )
        content = resp.choices[0].message.content or ""
        body = extract_json(content) or content.strip()
        parsed = safe_load_json(body) or {}
        score = float(parsed.get("score", 0.0))
        return max(0.0, min(1.0, score))
    except Exception:
        return 0.0


class GeoClaimRubric(vf.Rubric):
    def __init__(
        self,
        judge_client: AsyncOpenAI,
        judge_model: str,
        parser: vf.Parser | None = None,
    ):
        super().__init__(parser=parser or vf.Parser(extract_fn=extract_json))
        self.judge_client = judge_client
        self.judge_model = judge_model
        self.add_reward_func(self.verdict_match, weight=0.4)
        self.add_reward_func(self.source_weighting, weight=0.3)
        self.add_reward_func(self.caveat_quality, weight=0.2)
        self.add_reward_func(self.hallucination_check, weight=0.1)

    @staticmethod
    def _parsed(parser: vf.Parser, completion: Any) -> dict:
        raw = parser.parse_answer(completion) or ""
        return safe_load_json(raw) or {}

    async def verdict_match(self, parser, completion, answer, **_):
        m = self._parsed(parser, completion)
        gold = (answer or {}).get("verdict", "").strip().upper()
        got = str(m.get("verdict", "")).strip().upper()
        return 1.0 if (gold and got and gold == got) else 0.0

    async def source_weighting(self, parser, completion, answer, info, **_):
        """Score how well the model selected `supporting_source_ids` per the strict semantics.

        UNVERIFIED is checked deterministically (must be an empty list); for the other
        verdict labels we use an LLM judge with the strict-semantic instruction.
        """
        m = self._parsed(parser, completion)
        gold_verdict = (answer or {}).get("verdict", "").strip().upper()
        cited = list(m.get("supporting_source_ids", []) or [])

        if gold_verdict == "UNVERIFIED":
            # Deterministic: per system prompt, UNVERIFIED MUST have empty supporting list.
            return 1.0 if not cited else 0.0

        rule = {
            "TRUE": "ONLY sources that affirmatively support the claim.",
            "FALSE": "ONLY sources that affirmatively contradict the claim.",
            "PARTIALLY_TRUE": "ONLY sources supporting the TRUE component; contradicting / qualifying sources must go in caveats, NOT here.",
        }.get(gold_verdict, "ONLY sources that genuinely support the verdict.")

        instruction = (
            "Original claim: " + (info or {}).get("claim", "") + "\n\n"
            "Sources (with type and reliability_prior):\n"
            + json.dumps((info or {}).get("sources", []), indent=2)
            + "\n\n"
            "Model output:\n" + json.dumps(m, indent=2) + "\n\n"
            "Gold verdict: " + gold_verdict + "\n"
            "Gold supporting_source_ids: "
            + json.dumps((answer or {}).get("supporting_source_ids", []))
            + "\n\n"
            f"For verdict {gold_verdict}, supporting_source_ids must contain {rule}\n\n"
            "IMPORTANT distinction:\n"
            "For event-announcement claims (ceasefires, agreements, statements, declarations, resolutions), "
            "direct confirmation by a participating party constitutes primary supporting evidence, not secondary "
            "corroboration. Weight differently from claims about observed events (strikes, casualties, troop "
            "movements, capabilities) where belligerent self-reports require independent third-party verification.\n\n"
            "Score 0.0-1.0 how correctly the model selected supporting_source_ids and weighted source reliability:\n"
            "- 1.0 = list contains ONLY sources matching the strict semantics for this verdict; relied on the most reliable independent sources.\n"
            "- 0.5 = mostly correct semantics, minor mis-weighting (e.g. cited a low-reliability source alongside good ones).\n"
            "- 0.0 = included sources that contradict the verdict, or relied primarily on single-side belligerent statements treated as independent.\n"
            'Return ONLY: {"score": <float>, "reason": "<one sentence>"}'
        )
        return await _judge(self.judge_client, self.judge_model, instruction)

    async def caveat_quality(self, parser, completion, answer, info, **_):
        m = self._parsed(parser, completion)
        gold = answer or {}
        gold_verdict = gold.get("verdict", "").upper()
        if gold_verdict not in ("PARTIALLY_TRUE", "UNVERIFIED"):
            caveats = (m.get("caveats") or "").strip()
            return 1.0 if len(caveats) <= 400 else 0.7
        required = (info or {}).get("required_caveat_text", "") or _normalize_caveat(gold)
        instruction = (
            f"Claim: {(info or {}).get('claim', '')}\n\n"
            f"Gold verdict: {gold_verdict}\n"
            f"Required caveat topic: {required}\n"
            f"Model caveats: {m.get('caveats', '')}\n\n"
            "Score 0.0-1.0 how well the model's caveat reflects the required nuance.\n"
            "- 1.0 = caveat clearly addresses the required topic.\n"
            "- 0.5 = partial / shallow.\n"
            "- 0.0 = missing or wrong direction.\n"
            'Return ONLY: {"score": <float>, "reason": "<one sentence>"}'
        )
        return await _judge(self.judge_client, self.judge_model, instruction)

    async def hallucination_check(self, parser, completion, info, **_):
        m = self._parsed(parser, completion)
        cited = set(m.get("supporting_source_ids", []) or [])
        existing = set((info or {}).get("all_source_ids", []))
        if not cited:
            return 1.0
        if cited.issubset(existing):
            return 1.0
        bad = cited - existing
        return max(0.0, 1.0 - len(bad) / max(1, len(cited)))


def load_environment(
    data_path: str | None = None,
    judge_base_url: str = "https://api.pinference.ai/api/v1",
    judge_model: str = "qwen/qwen3-30b-a3b-instruct-2507",
    judge_api_key_env: str = "PRIME_KEY",
    **_,
) -> vf.Environment:
    """Construct the env with a Prime-Intellect-routed LLM judge."""
    here = Path(__file__).resolve().parent
    data_file = Path(data_path) if data_path else (here / "data" / "placeholder_claims.json")
    raw = json.loads(data_file.read_text())

    rows = []
    for c in raw["claims"]:
        enriched = _enriched_sources(c["sources"])
        rows.append(
            {
                "prompt": [{"role": "user", "content": format_prompt(c)}],
                "answer": c["gold"],
                "info": {
                    "claim_id": c["claim_id"],
                    "claim": c["claim"],
                    "sources": enriched,
                    "all_source_ids": [s["id"] for s in c["sources"]],
                    "test_type": c.get("test_type", ""),
                    "domain": c.get("domain", ""),
                    "required_caveat_text": _normalize_caveat(c["gold"]),
                },
                "task": "geopolitical-claim-verification",
            }
        )
    dataset = Dataset.from_list(rows)

    api_key = os.environ.get(judge_api_key_env)
    if not api_key:
        raise RuntimeError(f"{judge_api_key_env} env var is required for the judge client")
    judge_client = AsyncOpenAI(base_url=judge_base_url, api_key=api_key)

    parser = vf.Parser(extract_fn=extract_json)
    rubric = GeoClaimRubric(judge_client=judge_client, judge_model=judge_model, parser=parser)

    return vf.SingleTurnEnv(
        dataset=dataset,
        eval_dataset=dataset,
        system_prompt=SYSTEM_PROMPT,
        parser=parser,
        rubric=rubric,
    )
