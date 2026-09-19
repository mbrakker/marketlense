# Final frozen 20-report A21 reliability validation — 2026-09-19

## Measurement identity

- Measured Git SHA: `c89c545d649a2852f4602b8ddbfa4c09a8c39e18` (CI and CodeQL green before submission).
- Unchanged immutable cohort: [`frozen_cohort.json`](frozen_cohort.json), SHA-256 `4da8f4112f37bf880254fe85dc8784752fda089f0cac59f3989520370ae12286`.
- One fresh isolated production-queue workflow: validation run `validation:2e3e49965f8ff3ac9614946b70d512a323ba76c3042bb74301eea5adaf1925b8`; root `053bb9d9-9d88-4f25-88c5-b8695acac359`.
- No member substitution, rerun, operator requeue, database edit, or WordPress publication occurred.
- Authoritative result: [`cohort_result.json`](cohort_result.json), SHA-256 `ec2c5fa35c36dd14841d85e4b81157c957fa36d3be11a2ce40498d83db73c2f3`.

## Result and baseline comparison

| Measure | `bfab37bb` baseline | Final result | Change | A21 target |
| --- | ---: | ---: | ---: | ---: |
| admitted | 20 / 20 | 20 / 20 | — | 20 / 20 |
| typed terminal outcomes | 20 / 20 | 20 / 20 | — | 20 / 20 |
| first-attempt `awaiting_review` | 2 / 20 (10%) | 5 / 20 (25%) | +3 / +15pp | >=19 / 20 (95%) |
| publication-ready | 2 / 20 (10%) | 5 / 20 (25%) | +3 / +15pp | >=18 / 20 (90%) |
| ready without targeted editorial regeneration | not retained | 4 / 20 (20%) | n/a | >=18 / 20 (90%) |
| terminal failures | 18 / 20 (90%) | 15 / 20 (75%) | -3 / -15pp | <=1 / 20 |
| operator interventions | 0 | 0 | — | 0 |

The run improved on the official baseline but did **not** meet either A21 reliability SLO. All 20 members reached a typed terminal outcome; failures were retained, not excluded.

## Operational measurements

| Measure | Baseline | Final result |
| --- | ---: | ---: |
| provider calls | 560 | 611 |
| input / output tokens | 4,631,002 / 585,329 | 5,051,167 / 646,929 |
| estimated cost | USD 1.606652 | USD 1.769029 |
| wall-clock duration | 4,201.470s | 3,369.694s |
| bounded automatic repair | yes | yes |

Batch telemetry is cohort-scoped, so per-member usage, cost, duration, and repair attribution remain `unavailable` rather than fabricated. Two targeted regenerations succeeded, two failed, and four reports had regeneration not required. Algolia was the one final ready package with a successful targeted repair.

## Failure Pareto and remaining causes

| Typed terminal code | Reports |
| --- | ---: |
| `schema_reference_missing` | 6 |
| `artifact_structured_output_invalid` | 4 |
| `validation_failed` | 2 |
| `cover_asset_set_incomplete` | 1 |
| `soft_copy_claim_provenance_binding_invalid` | 1 |
| `soft_copy_claim_provenance_coverage_invalid` | 1 |

Remaining observed root-cause families are the normalized source-reference boundary, semantic structured-artifact validation, failed targeted validation repair, a missing cover-asset set, and two provenance-binding variants. They were not manually repaired or reclassified.

## Editorial/factual inspection

The five final `awaiting_review` packages were inspected through their retained signed `publish_readiness.json` artifacts. Each passed all 14 readiness rule IDs, including semantic grounding, source fidelity, material-claim evidence, editorial quality, public identifier leakage, public source provenance, and repeated boilerplate. Five final-HTML-validation and five publication-preflight records succeeded. No retained factual or editorial blocking regression was found in these ready outputs. Failed reports remain only as their actual typed terminal evidence; incomplete outputs are not treated as quality-cleared.

## Retained evidence

[`evidence-export/`](evidence-export/) contains terminal outcomes, failure Pareto, stage conversion, regeneration lineage, structured-output recovery, publication readiness, intervention, runtime, usage, and cost views. The detailed views were exported read-only from completed production state; terminal/funnel/audit views were then projected directly from the authoritative result. No second workflow or member retry was run.
