# E13 Repair Benchmark Evidence

This package freezes seven real historical failed repair cases in three
identity-separated cohorts. Every retained baseline attempt was rejected;
none was removed because it failed. The JSON manifests pin original promoted
artifacts, initial validation, six evidence packs, source run/audit references,
prompt identity, mutation scope, historical outcomes, and compatible identity
fields. They retain only references, hashes, identifiers, and bounded audit
fields. Source artifacts, rendered prompts, and full candidate audits remain
in their isolated local run storage.

## Frozen cohorts

| Manifest | Cases | Covered failure classes | Baseline success@3 | Baseline usage |
| --- | ---: | --- | ---: | --- |
| [`baseline-a21-five.json`](baseline-a21-five.json) (`d23482c46e0d8498bdf5dd0727472dfbc5c8da17d80443fba2ab43a0d68f12c4`) | 5 | summary, insight/metric, quote, Expert View, LinkedIn | 0/5 | 32 calls, 235,970 input + 51,700 output tokens, USD 0.109236; attempt-level attribution unavailable |
| [`baseline-mobile-editorial.json`](baseline-mobile-editorial.json) (`83b73c0b8fd0fe9dd6e54450fe7db132f5aea9c0bb495b7a01631dbdb0c4c428`) | 1 | summary, insight/metric, Expert View, public-editorial hard failure | 0/1 | 11 calls, 119,933 input + 23,322 output tokens, USD 0.051973; attempt-level attribution unavailable |
| [`baseline-doubleverify-linkedin-public-editorial.json`](baseline-doubleverify-linkedin-public-editorial.json) (`a586f229704a04aa2ebdda6bbcd5bdf7de74974bd15b5405ad64fbd5b8fc7363`) | 1 | summary, insight/metric, Expert View, LinkedIn, public-editorial hard failure | 0/1 | unavailable; no repair-attributable usage ledger was retained |

These manifests are deliberately separate. Their configuration, policy,
schema, validator, and build identities do not form one compatible baseline.
The first two have an unavailable historical validator identity. The third
pins its source result's Git SHA as the build attestation for audits from the
same workflow run; the validator identity is unavailable there as well. The
repair-response schema did not exist at any of these source commits, so its
historical identity is explicitly `unavailable`. The current aggregate schema
identity includes that response schema, which keeps every historical
comparison fail-closed.

## Measurement status

The implementation commit must be measured after it is committed, using its
exact full SHA. Each manifest is replayed independently by
`scripts/quality/replay_validation_repair_benchmark.py` through the existing
production validation-regeneration loop, with the same scoped validation and
artifact-regeneration model service clients used by the report workflow. The
provider schema projection uses the API-supported strict subset; the full
canonical schema remains authoritative when the response is validated. The
repair decision's fixed `replace` operation is explicitly typed as a string
for strict structured output. The response contract is identified as v3; its
failure class is derived from the planner's issue list. Replacement values
cross that provider boundary as JSON-encoded strings and are parsed before
the existing deterministic patch checks. The scorecard retains its normal
validation, evidence, mutation-scope, promotion, and rollback gates. It does
not author replacement copy or raise the configured retry limit.

## Final measurement disposition — 2026-09-26

The implementation was replayed at exact SHA
`09df2bac76111e44b8e811337c83a1995c791954`. The A21 replay stopped in its
first case with `report_payload_incomplete` because the reconstructed payload
had no `figure.title` or `figure.evidence`. A hash-only preflight of all seven
frozen cases found the same missing fields in every case. The original
artifacts and six evidence packs are retained and hash-pinned, but the complete
pre-repair `ReportPayload` that production has after figure selection is not in
the frozen inputs. Candidate validation and promotion were therefore not
reached; the retained candidate audit records mutation scope and evidence
lineage as `not_evaluated`, so it cannot establish either safety result. No
figure prose was invented and no production completeness, validation, or retry
gate was bypassed.

The attempted first case made 3 model calls (9,238 input tokens, 2,079 output
tokens, USD 0.001963) before that completeness check. These calls are diagnostic
generation usage, not a repair scorecard result, and are not comparable with
the aggregate historical usage. Current success, residual odds, newly
introduced hard failures, scope violations, unsupported evidence, repetition,
abstention, repair-mode share, per-class results, and comparable latency/cost
are `unavailable`, not zero. No current scorecard artifact was produced.

The retained baseline contains 7 cases and 19 rejected candidate attempts.
Valid success@1 and success@3 were both 0/7. The three cohorts remain separate
because their identities are incompatible; residual baseline odds are
unbounded at zero success. A21 retains one repeated candidate-hash group and
one repeated failure/strategy/evidence group. Historical per-attempt usage is
unavailable for A21 and mobile, and all usage is unavailable for the
DoubleVerify cohort. The result JSON retains per-cohort calls, tokens, cost,
latency, class coverage, failed-run usage, command outcomes, and the exact
acceptance disposition: [2026-09-26 result](results/2026-09-26-09df2bac.json)
(SHA-256 `1cf12dc7a0a09ae4ea69cd46cfdcc155d9b8052b80a015c923b42c8598a71e6b`).

The isolated discovery-to-publish readiness canary passed on the same SHA in
one attempt and ended at `awaiting_review`; validation and publication
readiness passed, and publication remained disabled. It did not exercise
repair and is not counted in repair metrics.

E13 remains **Active**. Closure requires a retained complete pre-repair
`ReportPayload` for each immutable case, followed by a same-corpus replay on a
new exact implementation SHA. Until then, the quantitative repair criteria are
not demonstrated. The quality check `check_documentation.py --check-generated`
also continues to report 12 pre-existing stale line anchors in
`simplification.md`; none point to files changed for this work.
