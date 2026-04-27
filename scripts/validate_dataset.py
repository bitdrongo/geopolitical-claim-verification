#!/usr/bin/env python3
"""Validate a claim dataset JSON file against the schema in data/SCHEMA.md.

Usage:
    python scripts/validate_dataset.py [PATH]

If PATH is omitted, validates `data/placeholder_claims.json`. Exits 0 on success,
non-zero with a list of errors on failure.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

VERDICTS = {"TRUE", "FALSE", "PARTIALLY_TRUE", "UNVERIFIED"}
SOURCE_TYPES = {
    "think_tank_report",
    "wire_service",
    "belligerent_official",
    "state_media",
    "osint_account",
    "academic_or_legal",
    "head_of_state_statement",
    "mediator_statement",
    "prediction_market_resolution",
    "prediction_market_rules",
    "belligerent_state_media",
    "anonymous_social_media",
    "absence_of_evidence",
}
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")


def _err(errors: list[str], path: str, msg: str) -> None:
    errors.append(f"{path}: {msg}")


def _check_iso_date(s: object) -> bool:
    if not isinstance(s, str):
        return False
    try:
        datetime.strptime(s, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _validate_source(src: dict, claim_path: str, errors: list[str]) -> None:
    p = f"{claim_path}.sources"
    if not isinstance(src, dict):
        _err(errors, p, "source must be an object")
        return
    sid = src.get("id")
    if not isinstance(sid, str) or not SLUG_RE.match(sid):
        _err(errors, p, f"id must be a slug string; got {sid!r}")
    stype = src.get("type")
    if stype not in SOURCE_TYPES:
        _err(errors, p, f"type must be one of {sorted(SOURCE_TYPES)}; got {stype!r}")
    # reliability_prior is OPTIONAL — env code fills in a per-type default if missing
    if "reliability_prior" in src:
        rp = src.get("reliability_prior")
        if not isinstance(rp, (int, float)) or not (0.0 <= float(rp) <= 1.0):
            _err(errors, p, f"reliability_prior must be a float in [0,1]; got {rp!r}")
    text = src.get("text")
    if not isinstance(text, str) or not text.strip():
        _err(errors, p, f"text must be a non-empty string")
    # date / publisher are OPTIONAL extras; type-check if present
    if "date" in src and not _check_iso_date(src["date"]):
        _err(errors, p, f"date must be YYYY-MM-DD if present; got {src['date']!r}")
    if "publisher" in src and not isinstance(src["publisher"], str):
        _err(errors, p, f"publisher must be a string if present; got {src['publisher']!r}")


def _validate_claim(c: dict, idx: int, seen_claim_ids: set[str], errors: list[str]) -> None:
    p = f"claims[{idx}]"
    if not isinstance(c, dict):
        _err(errors, p, "claim must be an object")
        return

    # required scalar fields
    for field in ("claim_id", "test_type", "claim", "claim_origin"):
        v = c.get(field)
        if not isinstance(v, str) or not v.strip():
            _err(errors, p, f"{field} must be a non-empty string; got {v!r}")

    cid = c.get("claim_id")
    if isinstance(cid, str):
        if not SLUG_RE.match(cid):
            _err(errors, p, f"claim_id must be a slug string; got {cid!r}")
        if cid in seen_claim_ids:
            _err(errors, p, f"duplicate claim_id: {cid!r}")
        seen_claim_ids.add(cid)

    if not _check_iso_date(c.get("claim_date_utc")):
        _err(errors, p, f"claim_date_utc must be YYYY-MM-DD; got {c.get('claim_date_utc')!r}")

    sources = c.get("sources")
    source_ids: set[str] = set()
    if not isinstance(sources, list) or not sources:
        _err(errors, p, "sources must be a non-empty list")
    else:
        for src in sources:
            _validate_source(src, p, errors)
            sid = src.get("id") if isinstance(src, dict) else None
            if isinstance(sid, str):
                if sid in source_ids:
                    _err(errors, f"{p}.sources", f"duplicate source id: {sid!r}")
                source_ids.add(sid)

    gold = c.get("gold")
    if not isinstance(gold, dict):
        _err(errors, p, "gold must be an object")
        return

    verdict = gold.get("verdict")
    if verdict not in VERDICTS:
        _err(errors, f"{p}.gold", f"verdict must be one of {sorted(VERDICTS)}; got {verdict!r}")

    sids = gold.get("supporting_source_ids")
    if not isinstance(sids, list) or not all(isinstance(x, str) for x in sids):
        _err(errors, f"{p}.gold", f"supporting_source_ids must be a list[str]; got {sids!r}")
    else:
        bad = [x for x in sids if x not in source_ids]
        if bad:
            _err(errors, f"{p}.gold", f"supporting_source_ids reference unknown ids: {bad}")
        if verdict == "UNVERIFIED" and sids:
            _err(errors, f"{p}.gold", "UNVERIFIED requires supporting_source_ids == []; strict semantic")

    # Caveats: accept EITHER `must_cite_caveat_about: str` OR `required_caveats: list[str]`.
    has_string = "must_cite_caveat_about" in gold
    has_list = "required_caveats" in gold
    caveat_text = ""
    if has_string:
        v = gold["must_cite_caveat_about"]
        if not isinstance(v, str):
            _err(errors, f"{p}.gold", f"must_cite_caveat_about must be a string; got {v!r}")
        else:
            caveat_text = v.strip()
    if has_list:
        v = gold["required_caveats"]
        if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
            _err(errors, f"{p}.gold", f"required_caveats must be a list[str]; got {v!r}")
        else:
            caveat_text = (caveat_text + " " + " ".join(v)).strip()
    if not has_string and not has_list:
        _err(errors, f"{p}.gold", "must provide must_cite_caveat_about (str) or required_caveats (list[str])")
    if verdict in ("PARTIALLY_TRUE", "UNVERIFIED") and not caveat_text:
        _err(errors, f"{p}.gold", f"caveat content must be non-empty for verdict {verdict}")


def _is_unfilled_skeleton(c: dict) -> bool:
    """Heuristic: a curation_template skeleton has the placeholder slug."""
    return c.get("claim_id") == "REPLACE_WITH_UNIQUE_SLUG"


def validate(path: Path) -> list[str]:
    errors: list[str] = []
    if not path.exists():
        return [f"{path}: file does not exist"]

    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        return [f"{path}: invalid JSON: {e}"]

    if not isinstance(data, dict):
        return [f"{path}: top-level must be an object"]

    # Auto-detect: a single-claim file has `claim_id` and `gold` at top level (not inside `claims`).
    if "claims" not in data and "claim_id" in data and "gold" in data:
        if _is_unfilled_skeleton(data):
            return [f"{path}: skeleton not yet filled in (claim_id is still the placeholder)"]
        seen_ids: set[str] = set()
        _validate_claim(data, 0, seen_ids, errors)
        return errors

    if not isinstance(data.get("version"), str):
        _err(errors, "<root>", f"version must be a string; got {data.get('version')!r}")
    if not isinstance(data.get("description"), str):
        _err(errors, "<root>", f"description must be a string; got {data.get('description')!r}")

    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        return errors + [f"{path}: claims must be a non-empty list"]

    seen_ids = set()
    for i, c in enumerate(claims):
        _validate_claim(c, i, seen_ids, errors)

    return errors


def _claim_count(path: Path) -> int | str:
    try:
        d = json.loads(path.read_text())
        if isinstance(d, dict) and "claims" in d:
            return len(d["claims"])
        if isinstance(d, dict) and "claim_id" in d:
            return 1
    except Exception:
        pass
    return "?"


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data/placeholder_claims.json")
    errors = validate(target)

    if not errors:
        print(f"OK  {target}  ({_claim_count(target)} claims)")
        return 0

    print(f"FAIL  {target}  ({len(errors)} errors)")
    for e in errors:
        print(f"  - {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
