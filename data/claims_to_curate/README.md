# Curation workspace

Per-claim filled curated entries that get merged into `data/claims.json` via `scripts/merge_curated.py`.

**Status (v0.1):** the `iran-israel/` subfolder holds the 22 curated claims that ship in this release. Skeletons for the unstarted domains (Russia–Ukraine war, oil/tanker OSINT) live under `data/_skeletons/{ru-ua,oil-tanker}/` — pre-allocated empty files with `_target_label` hints, ready for v0.2 expansion.

When a skeleton is filled in, drop it under the matching `data/claims_to_curate/<domain>/` folder and run `python scripts/merge_curated.py` to regenerate `data/claims.json`.

## Original target distribution (60 claims total — v0.2 plan)

| Verdict          | Count | %   |
|------------------|-------|-----|
| TRUE             | 18    | 30% |
| FALSE            | 12    | 20% |
| PARTIALLY_TRUE   | 18    | 30% |
| UNVERIFIED       | 12    | 20% |

By domain:

| Domain                                | Folder                       | Slots | Status (v0.1) |
|---------------------------------------|------------------------------|------:|---|
| Iran / Israel / Houthi / IRGC theatre | `claims_to_curate/iran-israel/` | 22 (originally 20, +2 added) | **filled** |
| Russia-Ukraine war                    | `_skeletons/ru-ua/`          | 25    | empty skeletons (v0.2) |
| Oil / tanker / commodities OSINT      | `_skeletons/oil-tanker/`     | 15    | empty skeletons (v0.2) |

Adversarial source-poisoning cases (12 total, 20%) are pre-allocated:
- `ru-ua-022..025`: RU MoD-only, gold UNVERIFIED with one-sided-sourcing caveat
- `iran-israel-015..016`: IDF-only with propaganda framing, gold PARTIALLY_TRUE
- `iran-israel-017..020`: Iranian state-media only, gold UNVERIFIED with bias caveat
- `oil-tanker-012..013`: single OSINT account no corroboration, gold UNVERIFIED
- `oil-tanker-014..015`: state-media only on tanker movements, gold UNVERIFIED

## Source priors (recommended)

| Source                                    | type                  | prior   |
|-------------------------------------------|-----------------------|---------|
| Reuters / AP / AFP / Bloomberg            | wire_service          | 0.90    |
| BBC / NYT (factual reporting)             | wire_service          | 0.85    |
| ISW (Russia-Ukraine, Iran updates)        | think_tank_report     | 0.85    |
| Oryxspioenkop (visual loss documentation) | osint_account         | 0.80    |
| TankerTrackers / S&P / Lloyd's List       | osint_account         | 0.80    |
| UANI (Iran sanctions OSINT)               | osint_account         | 0.70    |
| Ukrainian / Israeli / IDF official        | belligerent_official  | 0.55-0.65 |
| Russian / Iranian / Houthi official       | belligerent_official  | 0.30-0.45 |
| RIA Novosti / TASS / Sputnik              | state_media           | 0.30    |
| Mehr / Tasnim / IRNA / Press TV           | state_media           | 0.30    |
| RT / RT Arabic                            | state_media           | 0.25    |
| Anonymous milblogger Telegram             | osint_account         | 0.25    |

## Curator workflow per claim

1. Pick a skeleton; read `_target_label` for the slot's intended verdict.
2. Pick a real event from your saved references (ISW daily, Reuters wire, UKMTO bulletins, TankerTrackers tweets, your Polymarket research notes, etc.).
3. Frame the claim as one specific factual sentence, dated. Avoid weasel words.
4. Assemble 1–8 sources per the case design rules in `../SCHEMA.md`. For UNVERIFIED single-source cases, exactly 1 source. For TRUE / FALSE clean cases, ≥2 reliable independent. For PARTIALLY_TRUE, include both supporting AND qualifying. For source-poisoned, all sources from one side.
5. Apply Hybrid A+B+C decision rules (see SCHEMA.md) for the gold verdict.
6. Fill `gold.supporting_source_ids` per the strict semantic table — UNVERIFIED MUST be `[]`.
7. Fill `gold.must_cite_caveat_about` for PARTIALLY_TRUE / UNVERIFIED.
8. Drop the `_comment_*` and `_target_label` and `_domain_hint` fields.
9. Run validator on the standalone file: `python scripts/validate_dataset.py <file>` (after wrapping in a `{"version":..., "description":..., "claims":[...]}` envelope, or skip and validate at merge time).

## Common pitfalls

- **Quoting full articles** in `text` — paraphrase to 1-3 sentences.
- **Including the source for the claim itself** as a separate entry — don't. The claim's `claim_origin` field captures that. Sources are independent corroborating / refuting evidence.
- **Mixing reliable + unreliable in `supporting_source_ids` for TRUE** — only include genuinely supporting reliable ones.
- **Calling something TRUE because the supportive sources outnumber the contradicting** — count quality, not quantity.
- **Filling `supporting_source_ids` for an UNVERIFIED case** — it MUST be `[]`. Validator rejects.
- **Forgetting the date window** — info dated `claim_date_utc + >7 days` shouldn't be in your sources, per Rule B.
- **Curating a claim where YOU don't know the answer with high confidence** — skip it, pick another. Ground truth must be defensible.
