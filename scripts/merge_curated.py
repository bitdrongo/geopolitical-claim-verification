#!/usr/bin/env python3
"""Merge filled-in single-claim files from data/claims_to_curate/ into data/claims.json.

Walks every *.json under data/claims_to_curate/{domain}/, skips skeletons whose
claim_id is still the placeholder, strips curation-only meta fields
(`_target_label`, `_domain_hint`, `_comment_*`), validates each, and aggregates
into a single dataset envelope at data/claims.json.

Usage:
    python scripts/merge_curated.py [--out data/claims.json] [--version 0.2.0]
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CURATED_DIR = ROOT / "data" / "claims_to_curate"

# import validator from sibling script
sys.path.insert(0, str(ROOT / "scripts"))
from validate_dataset import _validate_claim, _is_unfilled_skeleton  # noqa: E402


META_FIELDS = {"_target_label", "_domain_hint"}
COMMENT_PREFIX = "_comment"


def _strip_meta(d: dict) -> dict:
    out = {}
    for k, v in d.items():
        if k in META_FIELDS or k.startswith(COMMENT_PREFIX):
            continue
        if isinstance(v, dict):
            out[k] = _strip_meta(v)
        elif isinstance(v, list):
            out[k] = [_strip_meta(x) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "data" / "claims.json"))
    ap.add_argument("--version", default="0.2.0")
    ap.add_argument(
        "--description",
        default="Curated geopolitical claims dataset assembled from data/claims_to_curate/.",
    )
    args = ap.parse_args()

    files = sorted(CURATED_DIR.rglob("*.json"))
    if not files:
        print(f"no curated files under {CURATED_DIR}", file=sys.stderr)
        return 1

    claims: list[dict] = []
    skipped: list[tuple[str, str]] = []
    errors: list[str] = []

    for f in files:
        rel = f.relative_to(ROOT)
        try:
            raw = json.loads(f.read_text())
        except json.JSONDecodeError as e:
            errors.append(f"{rel}: invalid JSON: {e}")
            continue
        if not isinstance(raw, dict):
            errors.append(f"{rel}: top-level must be an object")
            continue
        if _is_unfilled_skeleton(raw):
            skipped.append((str(rel), "unfilled skeleton"))
            continue
        cleaned = _strip_meta(raw)
        per_errors: list[str] = []
        _validate_claim(cleaned, len(claims), set(c.get("claim_id", "") for c in claims), per_errors)
        if per_errors:
            for e in per_errors:
                errors.append(f"{rel}: {e}")
            continue
        claims.append(cleaned)

    print(f"merged {len(claims)} claims from {len(files)} files")
    if skipped:
        print(f"skipped {len(skipped)} unfilled skeletons")
    if errors:
        print(f"FAILED with {len(errors)} validation errors:")
        for e in errors:
            print(f"  - {e}")
        return 1

    out_path = Path(args.out)
    payload = {"version": args.version, "description": args.description, "claims": claims}
    out_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
    print(f"wrote {out_path} ({out_path.stat().st_size} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
