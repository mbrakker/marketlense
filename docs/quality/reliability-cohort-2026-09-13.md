# Frozen 20-report reliability cohort — 2026-09-13

The frozen source set in `scripts/quality/frozen_reliability_cohort_20.json`
was evaluated once per member by the isolated runner at commit
`340d992361c4e7e59206122fa44c33cb8ee21f77`; every admitted member used the
normal frozen-cohort queue path. The exact compact machine-readable result is
[`reliability-cohort-2026-09-13.json`](reliability-cohort-2026-09-13.json).

All 20 members have a typed terminal classification. No operator intervention,
manual queue requeue, database edit, report replacement, or second workflow
attempt occurred. The result does not meet either reliability target: no
member reached `awaiting_review` or publication readiness.

| Metric | Result |
| --- | ---: |
| First-attempt awaiting-review rate | 0.0% |
| Publication-readiness rate | 0.0% |
| Bounded-repair rate | 0.0% |
| Workflow failure rate | 100.0% |
| Typed-terminal rate | 100.0% |
| Operator interventions | 0 |
| Mean / median cost | $0.001802 / $0.000000 |
| Mean / median duration | 22.504s / 1.562s |

Failure Pareto: `frozen_cohort_admission_missing_source_identity` 14,
`report_canonical_identity_missing` 3,
`frozen_cohort_admission_insufficient_content` 2, and `file_write_failed` 1.

The fourteen source-admission identity terminals are measurement-input
failures: these locally retained PDFs do not carry the source-record provenance
that normal discovery persists before queue submission. They are recorded, not
counted as successful admissions, and are not a claim that the production
report workflow failed. The three reports admitted with source identities did
enter the normal queue but then terminated with
`report_canonical_identity_missing`; the StackAdapt report entered the normal
queue and terminated with `file_write_failed` while persisting
`report_analysis/crop_refine.json`.
