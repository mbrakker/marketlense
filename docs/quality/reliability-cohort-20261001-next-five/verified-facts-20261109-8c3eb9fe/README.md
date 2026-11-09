# Activate + Adjust verified-facts E2E

Run date: 2026-11-09
Producer SHA: `8c3eb9fe366f0f2c00fb89abb39800dd575d0daf`

This is the required isolated provider-backed run for the exact frozen cohort
members Activate and Adjust. The original PDFs were independently hash-checked
in the authorized source workspace and are not committed. The report-level
projections under `export/reports/` were produced by the repository's existing
`export_reliability_run_evidence.py` tool. Raw provider responses, caches,
private databases, usage ledgers and source PDF bytes are excluded.

## Outcome

| Measure | Result |
| --- | ---: |
| Reports admitted | 2 / 2 |
| Terminal outcomes | 2 failed |
| Verified-facts admission | 20 / 20 facts admitted; 0 quarantined |
| Provider calls | 650 |
| Input / output tokens | 3,480,985 / 658,356 |
| Estimated cost | $0.704460 |
| Wall-clock | 5,237.735 s |
| Automatic repairs | 0 |
| WordPress writes | 0 |

Both reports reached artifact generation and the corrected verified editorial
plan boundary. Neither reached a publishable HTML artifact: both failed closed
at semantic/grounding validation with an incomplete public-item verdict in a
grounding batch. No unsupported retained factual claim was marked verified,
no candidate was promoted, and publication readiness remained `fail`.

## Per-report outcome

| Report | Calls | Cost | Duration | Terminal stage | Failure | HTML |
| --- | ---: | ---: | ---: | --- | --- | --- |
| Activate | 482 | $0.446986 | 3,548.907 s | `semantic_validation` | `validation_failed` / `grounding` | absent |
| Adjust | 168 | $0.257474 | 1,688.828 s | `semantic_validation` | `validation_failed` / `grounding` | absent |

Activate admitted 10/10 verified facts and failed on missing verdict coverage
for `soft_copy:expert_comment:8f99ed4197a3ac39`. Adjust admitted 10/10 and
failed on missing verdict coverage for `insight:insight-09:now_what`. The
existing bounded structured-output recovery was exhausted for each affected
grounding batch; no extra retry policy was introduced.

The run also retained a public-editorial review failure: Activate had a
semantic-review support mismatch for `insight:finding-05:text`, while Adjust
had a localized semantic-redundancy finding for the `insight-09` so-what.
These are recorded in the retained validation projection and were not
overridden by the grounding failure.

## Evidence and verdict

* `cohort_result.json` is the authoritative mutually exclusive terminal ledger.
* `source_identity_manifest.json` records both expected source hashes and page counts.
* `execution_config_identity.json` records the isolated runner policy.
* `export/reports/` contains the sanitized exporter projections, including
  admission, stage, recovery, failure, readiness and usage summaries.
* `inspection_notes.md` records the accepted-plan handoff, artifact counts and
  the exact fail-closed terminal reasons without raw model or source text.

Verdict: **PARTIAL / NO-GO** for live downstream editorial/readiness acceptance.
The verified planning contract correction is exercised successfully, but the
grounding/public-editorial contract remains an actionable blocker. Step 3 must
not start.
