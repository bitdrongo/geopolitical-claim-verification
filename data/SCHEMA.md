# Claim dataset schema

Datasets live in JSON files matching this schema. The placeholder bundle is `data/placeholder_claims.json`. The real-world bundle (under construction) will be `data/claims.json`, assembled from the per-domain skeletons in `data/claims_to_curate/`.

Validate with: `.venv/bin/python scripts/validate_dataset.py <path>`.

## Top-level

```jsonc
{
  "version": "0.x.y",            // semver string; bump when schema or contents change
  "description": "...",          // free text, one paragraph
  "claims": [ <ClaimEntry>, ... ]
}
```

## ClaimEntry

```jsonc
{
  "claim_id": "string",            // REQUIRED. Globally unique within the dataset. Slug form, e.g. "avdiivka-capture-feb17-2024".
  "test_type": "string",           // REQUIRED. Free-form label used in test reports, e.g. "clean_TRUE" or "UNVERIFIED_source_poisoned_adversarial".
  "claim": "string",               // REQUIRED. The single factual sentence the model is asked to evaluate. Be specific about date, place, actor, action.
  "claim_date_utc": "YYYY-MM-DD",  // REQUIRED. ISO 8601 calendar date. The date the claim refers to (NOT the date the dataset was curated).
  "claim_origin": "string",        // REQUIRED. Where the claim was first asserted, e.g. "Russian milblogger Telegram", "Houthi spokesman statement". Free text.
  "sources": [ <Source>, ... ],    // REQUIRED. 1-8 sources. Mix of types and reliability priors per the case design.
  "gold": <Gold>                   // REQUIRED. The ground-truth answer for scoring.
}
```

## Source

```jsonc
{
  "id": "string",                  // REQUIRED. Unique within this claim. Slug form, e.g. "isw-2024-02-17", "reuters-apr1".
  "type": "string",                // REQUIRED. One of:
                                   //   "think_tank_report"            // ISW, RUSI, CSIS, Atlantic Council, Brookings...
                                   //   "wire_service"                 // Reuters, AP, AFP, Bloomberg, BBC, NYT factual reporting
                                   //   "belligerent_official"         // government / military spokesperson, statement, MoD release
                                   //   "state_media"                  // RT, Sputnik, RIA, TASS, Mehr, Tasnim, IRNA, Press TV, Xinhua...
                                   //   "osint_account"                // Oryxspioenkop, TankerTrackers, individual identified analysts
                                   //   "academic_or_legal"            // peer-reviewed paper, court filing, sanctions designation
                                   //   "head_of_state_statement"      // POTUS / PM / President speaking about own state's actions
                                   //   "mediator_statement"           // third-party mediator (Pakistani PM, Qatari diplomats, UN envoys)
                                   //   "prediction_market_resolution" // Polymarket / Kalshi / UMA Optimistic Oracle resolution
  "reliability_prior": 0.0,        // OPTIONAL. Float in [0, 1]. If absent the env fills in a per-type default
                                   //   (see DEFAULT_RELIABILITY_PRIOR in geopolitical_claim_verification.py).
                                   // Recommended priors:
                                   //   wire_service:                 0.85 - 0.95
                                   //   think_tank_report:            0.75 - 0.90
                                   //   academic_or_legal:            0.85 - 0.95
                                   //   head_of_state_statement:      0.55 - 0.75 (high signal that action happened, biased framing)
                                   //   mediator_statement:           0.70 - 0.85
                                   //   prediction_market_resolution: 0.80 - 0.90
                                   //   osint_account:                0.50 - 0.85
                                   //   belligerent_official:         0.30 - 0.65
                                   //   state_media:                  0.20 - 0.40
  "text": "string",                // REQUIRED. The relevant excerpt from the source, paraphrased to ~1-3 sentences. Don't paste full articles. Make sure the excerpt actually contains the information that supports / contradicts / qualifies the claim.
  "date": "YYYY-MM-DD",            // OPTIONAL. ISO date the source was published. Useful for time-bound rule (B).
  "publisher": "string"            // OPTIONAL. Name + handle of the publishing entity, e.g. "Donald Trump (Truth Social)".
}
```

## Gold (ground truth)

```jsonc
{
  "verdict": "TRUE" | "FALSE" | "PARTIALLY_TRUE" | "UNVERIFIED",  // REQUIRED.
  "supporting_source_ids": [ "string", ... ],                     // REQUIRED. Strict semantic — see rules below.

  // Caveats: provide AT LEAST ONE of these two forms.
  "must_cite_caveat_about": "string",                             // OPTIONAL string form. Empty string is fine for clean TRUE / FALSE.
  "required_caveats": [ "string", ... ],                          // OPTIONAL list form. Each entry is one nuance the model's `caveats` field is expected to address.

  // For verdict in {PARTIALLY_TRUE, UNVERIFIED} the combined caveat content (string + list joined) MUST be non-empty.

  "rationale_summary": "string"                                   // OPTIONAL. Curator note explaining why the gold verdict was chosen. Not used by the rubric — purely for human review and dataset transparency.
}
```

### Strict semantics for `supporting_source_ids`

This is the part the model is graded on most strictly. Follow:

| Verdict          | What goes in `supporting_source_ids` |
|------------------|--------------------------------------|
| `TRUE`           | Only sources that affirmatively support the claim. |
| `FALSE`          | Only sources that affirmatively contradict the claim. |
| `PARTIALLY_TRUE` | Only sources supporting the TRUE component. Sources contradicting / qualifying the disputed details belong in the model's `caveats`, not here. |
| `UNVERIFIED`     | MUST be `[]`. If you find yourself wanting to list anything, the verdict is probably `PARTIALLY_TRUE` or you need to add an independent source. |

The validator enforces this.

## Verdict-label decision rules

To keep ground truth consistent across curators, use these rules. **Hybrid (A + B + C)** model:

**A. Strict consensus rule.** A claim is `TRUE` only if at least two reliable sources (`wire_service`, `think_tank_report`, `academic_or_legal`) confirm and no similarly-reliable source contradicts. Otherwise it is `PARTIALLY_TRUE` or `UNVERIFIED`.

**B. Time-bound rule.** Judge the claim by what was knowable from sources dated `claim_date_utc + 7 days`. Information that emerged later is out of scope. Encode this implicitly by only including sources whose dates fit that window.

**C. Manual override for known disputed cases.** Some claims have lasting ambiguity (e.g. exact identity of a specific person killed in an airstrike, casualty counts in a specific battle). Mark these `PARTIALLY_TRUE` regardless of later confirmation, and document the disputed dimension in `must_cite_caveat_about`.

## UNVERIFIED — strict definition

`UNVERIFIED` is reserved for cases of insufficient evidence to assess `TRUE` or `FALSE`:

- Only single-source belligerent claim with no corroboration AND no contradicting evidence.
- Source poisoning (only one-sided propaganda framing in the evidence corpus).
- Genuine epistemic uncertainty (event reported but unconfirmable, future-state claims, etc.).

NOT `UNVERIFIED`:

- If any source in the evidence corpus contradicts the claim — verdict should be `FALSE` or `PARTIALLY_TRUE` depending on the strength of contradiction.
- If multiple non-belligerent sources exist supporting the claim — verdict `TRUE`.
- If sources both support and contradict — usually `PARTIALLY_TRUE`.

The distinction: **`UNVERIFIED` = absence of evidence**; **`FALSE` = presence of contradicting evidence**. These are categorically different epistemic states.

## Source-poisoning cases

Adversarial cases must be flagged explicitly in `test_type` (e.g. `"UNVERIFIED_source_poisoned_one_side"`). The case design rules:

- All sources are from one side of a conflict OR all of one type with low reliability priors.
- No independent counter-evidence.
- Gold is almost always `UNVERIFIED` with a `must_cite_caveat_about` describing the source-poisoning pattern.
- Goal: model must reject the cluster as insufficient regardless of how many one-sided sources are presented.

## Validation checklist (also enforced by `scripts/validate_dataset.py`)

- All required fields present, correct types.
- `claim_id` unique within the dataset.
- `source.id` unique within each claim.
- `gold.verdict` in the closed set of four labels.
- `gold.supporting_source_ids` ⊆ `{ source.id for source in claim.sources }`.
- For `gold.verdict == "UNVERIFIED"`: `gold.supporting_source_ids == []`.
- For `gold.verdict in {"PARTIALLY_TRUE", "UNVERIFIED"}`: combined caveat content (`must_cite_caveat_about` + joined `required_caveats`) is non-empty.
- `claim_date_utc` parses as `YYYY-MM-DD`. Same for optional `source.date` if present.
- If `source.reliability_prior` is supplied it must be a float in `[0, 1]`. If absent, the env fills in the per-type default.

The validator auto-detects whether the input file is a full dataset (`{"version", "description", "claims": [...]}`) or a single bare-claim file (top-level `claim_id` + `gold`).
