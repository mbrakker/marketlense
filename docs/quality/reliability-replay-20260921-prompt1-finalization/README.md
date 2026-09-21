# Prompt 1 finalization replay — 2026-09-21

## Measurement identity

- Implementation SHA: `eae4b7fafbb79342e33fd374ff9d978b5b04bc5d`.
- Execution path: `scripts/quality/run_ias_first_attempt_canary.py`, which
  submits each frozen local source through the normal production queue and
  supervisor in fresh isolated state. No run published to WordPress, requeued
  a report, reused an editorial artifact, raised a retry limit, or added a
  provider call.
- Sources: the checksum-validated KPMG, Adjust, Algolia, and Criteo members in
  `scripts/quality/frozen_reliability_cohort_20.json`.
- Final-copy invariant: the canonical
  `assert_retained_soft_copy_claims_match_public_copy` check passed against all
  four retained `artifacts.json` payloads. Each final material sentence has one
  retained provenance hash and no retained provenance claim references obsolete
  public text.

## Before and after

| Report | Earlier relevant failure | Final replay outcome | Provenance coverage | New downstream failure |
| --- | --- | --- | --- | --- |
| KPMG | `cover_asset_set_incomplete` after publisher identity was populated from legal prose | `awaiting_review`; validation/readiness pass | pass (26 claims/hashes) | none |
| Adjust | `soft_copy_claim_provenance_bindings_incomplete` | `validation_failed` | pass (23 claims/hashes) | semantic validation, `quotes:multiplatform-strategy`, repair 1 |
| Algolia | `soft_copy_claim_provenance_bindings_incomplete`, then candidate-only `soft_copy_claim_provenance_coverage_invalid` | `validation_failed` | pass (25 claims/hashes) | claim support, `summary.claim_evidence_map[4]`, `chapter-1`, repair 1 |
| Criteo | `soft_copy_claim_provenance_bindings_incomplete` | `awaiting_review`; validation/readiness pass | pass (27 claims/hashes) | none |

The two retained failures are normal downstream semantic/claim-support gates;
neither is a soft-copy provenance failure. They were not suppressed or retried
beyond the existing bounded flow.

## Retained final-copy and provenance inspection

The complete final Summary (`tldr`, `card_tldr_compact`, and
`executive_summary`), Expert View, LinkedIn copy, full
`soft_copy_claim_provenance` records, text hashes, evidence IDs, and source
spans are retained in the isolated artifact paths below. The committed terminal
outcome projection is under [`results/`](results/) and its canonical bounded
views are under [`evidence-export/`](evidence-export/). Local run state is
intentionally not committed, consistent with the repository reliability-evidence
policy.

| Report | Source identity | Retained artifact | Summary / Expert / LinkedIn claims | Canonical evidence IDs | Unique source spans |
| --- | --- | --- | --- | --- | ---: |
| KPMG | `source:1ffb71d718276f8a1761fc706a2a3cb3` | `tmp/reliability-replay-20260921-prompt1-eae4b7fa/ias-first-attempt-1bn1z3ug/output/kpmg-2026-global-ma-outlook-pdf/report_analysis/artifacts.json` | 7 / 7 / 12 | `2025-retrospective-and-2026-outlook`, `ai-driven-transformation-of-deal-execution`, `diverging-risk-appetites-between-buyers`, `execution-discipline-as-a-decisive-source-of-advantage`, `executive-summary`, `f10`, `five-drivers-shaping-2026-ma-environment`, `implications-for-dealmakers`, `industry-specific-dynamics`, `portfolio-simplification-as-a-value-creation-strategy` | 10 |
| Adjust | `source:8cb648b6bbd9dbae4ec1d915c38cf235` | `tmp/reliability-replay-20260921-prompt1-eae4b7fa/ias-first-attempt-h7hdn23g/output/mobile-app-trends-2026-pdf/report_analysis/artifacts.json` | 8 / 5 / 10 | `ai-infrastructure`, `conclusion`, `ecommerce-finding-keeping-users`, `ecommerce-shopping`, `finance-apps`, `gaming-apps`, `key-takeaways-methodology`, `multiplatform-strategy`, `quote_001` | 17 |
| Algolia | `source:4ea9ae5709898e763efb0945d8d4fa1e` | `tmp/reliability-replay-20260921-prompt1-eae4b7fa/ias-first-attempt-h5fpe6la/output/2026-20b2c-20ecommerce-20ai-2-0ffedeaf63d9/report_analysis/artifacts.json` | 8 / 6 / 11 | `chapter-1`, `chapter-2`, `chapter-3`, `chapter-4`, `chapter-5`, `chapter-6` | 6 |
| Criteo | `source:81027fd399837b2cbd3cefa2abca222b` | `tmp/reliability-replay-20260921-prompt1-eae4b7fa/ias-first-attempt-srwniiym/output/agency-guide-report-criteo-pdf/report_analysis/artifacts.json` | 9 / 6 / 12 | `finding-emerging-channel-exploration`, `finding-retail-media-roi`, `key-takeaways`, `quote_001`, `quote_003`, `quote_004`, `quote_005`, `section-3-new-concepts-in-measurement`, `section-4-the-right-strategy` | 10 |

## Terminal usage and cost

| Report | Calls | Input tokens | Output tokens | Cost | Duration |
| --- | ---: | ---: | ---: | ---: | ---: |
| KPMG | 30 | 306,227 | 28,721 | USD 0.095712 | 229.200s |
| Adjust | 40 | 330,888 | 42,095 | USD 0.100569 | 321.838s |
| Algolia | 56 | 493,265 | 67,898 | USD 0.178986 | 612.902s |
| Criteo | 24 | 211,969 | 27,458 | USD 0.075343 | 192.679s |

## Verification

- `python scripts/ci/run_quality_gate.py` passed at implementation SHA
  `eae4b7fa`: formatting, Ruff, type, architecture, policy, full pytest,
  coverage, mutation, quality-regression, and prompt-fixture gates.
- Full pytest result: 5,921 passed, 1 skipped, 26 deselected; all coverage
  thresholds passed.
- `python -c "...assert_retained_soft_copy_claims_match_public_copy(...)..."`
  passed over each of the four retained final artifacts.
