# Frozen 20-report reliability cohort — 2026-09-14

## Measurement identity

- Measured Git SHA: `bfab37bbd1e4c194c027f14dd54817fb61f940a6`.
- Workflow: one standard production queue submission using the unchanged frozen
  20-member manifest; no validation-only workflow sequencing was used.
- Preflight: 20 of 20 admitted (100%). The retained
  [`cohort_preflight.json`](cohort_preflight.json) records each canonical source
  identity and production-equivalent admission outcome.
- Measured result: 20 of 20 reports have a typed terminal outcome. The exact
  retained member-level evidence is [`cohort_result.json`](cohort_result.json).

## First-attempt cohort result

The workflow denominator is the 20 admitted reports, not the original cohort
size by coincidence. No admission rejection was excluded.

| Measure | Result |
| --- | ---: |
| admitted reports / admission rate | 20 / 100% |
| first-attempt `awaiting_review` | 2 / 20 (10%) |
| publication readiness | 2 / 20 (10%) |
| workflow failures | 18 / 20 (90%) |
| typed-terminal outcomes | 20 / 20 (100%) |
| bounded repair rate | unavailable (repair telemetry is batch-scoped) |
| batch automatic repair occurred | yes |
| operator interventions | 0 |
| duration | 4,201.470 seconds |
| cost | USD 1.606652 |
| provider calls | 560 |
| input / output tokens | 4,631,002 / 585,329 |

Per-report duration, cost, usage, and repair values are intentionally null with
`metric_attribution="unavailable"` in the member records: retained telemetry
is scoped to the one shared batch workflow, so assigning it to a report would
be false attribution.

## Failure Pareto

| Failure code | Reports |
| --- | ---: |
| `schema_reference_missing` | 7 |
| `workflow_queue_report_stage_failed` | 5 |
| `artifact_structured_output_invalid` | 2 |
| `soft_copy_claim_provenance_binding_invalid` | 2 |
| `evidence_pack_invalid_json` | 1 |
| `soft_copy_claim_provenance_bindings_missing` | 1 |

Every non-success is retained in `cohort_result.json`. The bounded terminal
outcome, failure-detail, Pareto, aggregate-funnel, and audit views under
[`evidence-export/`](evidence-export/) are projected directly from those typed
outcomes, rather than reconstructed from a separate exporter query. No manual
requeue, database edit, member replacement, or second workflow attempt occurred
during this measurement.

## Comparison and conclusion

The preceding invalid run had 20 members but only 4 entered the normal workflow
and none reached review or publication readiness. This corrected run has valid
source provenance, 20/20 production admission, complete terminal accounting,
and 2 reports reaching review/readiness. It is therefore valid cohort-level
evidence, but it **does not achieve** the production-reliability target: 18 of
20 admitted reports failed on their first workflow attempt.
