# Frozen A21 20-report reliability measurement — 2026-09-20

## Identity and controls

- Commit: `89b4fc4c1159499806ed16993d76f3684fe3412e` (full CI and CodeQL passed).
- Frozen manifest: [`frozen_cohort.json`](frozen_cohort.json), SHA-256 `21a9a1b995d10b5add412780d96930ecc29bafd082907ecbf0741c80be841a07`.
- Authoritative result: [`cohort_result.json`](cohort_result.json), SHA-256 `f45047b8343f18192783e26e8d42ffa2524d18c90fdd33d09e945e404902b5ee`.
- Preflight admitted all 20 checksum-validated members. One clean isolated production-queue submission ran to completion; no publication, operator requeue, manual repair, substitution, or derived-artifact reuse occurred.

## Results

| Measure | Result | Target |
| --- | ---: | ---: |
| typed terminal outcomes | 20 / 20 | 20 / 20 |
| first-attempt `awaiting_review` | 9 / 20 (45%) | >=19 / 20 |
| publish-ready without targeted editorial regeneration | 9 / 20 (45%) | >=18 / 20 |
| operator interventions | 0 | 0 |
| provider calls / tokens / cost / runtime | 644 / 5,299,676 in + 699,778 out / USD 1.869133 / 5,424.234s | retained |

The cohort did not meet either readiness target. It did reach complete typed terminal closure and retained actionable diagnostics for each terminal failure.

## Failure Pareto and regression comparison

The 11 failures are `validation_failed` (5), `soft_copy_claim_provenance_bindings_incomplete` (4), `openai_bad_request` (1), and `publish_readiness_failed` (1). The per-report exact stages, validator rules, repair attempts and bounded contexts are retained in [`evidence-export/failure_details.json`](evidence-export/failure_details.json).

Compared with the five successful reports in the prior full cohort, Activate and Merchant Risk Council remained ready; Capgemini regressed to `validation_failed` (grounding, Expert View), Algolia to `soft_copy_claim_provenance_bindings_incomplete`, and Robeco to `publish_readiness_failed`. Therefore the no-regression criterion was not met.

`repair_effectiveness.json` is retained and explicitly reports `unavailable`: the run has no compatible retained reliability sidecar, so usage/repair attribution is not fabricated as zero. The unchanged workflow did perform bounded automatic recovery at cohort scope.

## Artifact inspection

`python scripts/ci/check_public_report_quality.py` passed against inspectable retained output. The nine ready packages passed readiness; failed/incomplete packages are not represented as quality-cleared. [`evidence-export/`](evidence-export/) contains the read-only state projection plus authoritative frozen terminal views.
