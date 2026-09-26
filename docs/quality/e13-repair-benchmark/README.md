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
| [`baseline-a21-five.json`](baseline-a21-five.json) (`b50d752a35a37774fe8446df10ab9dd3f163fb28f4692df3ccf3236ff21b3740`) | 5 | summary, insight/metric, quote, Expert View, LinkedIn | 0/5 | 32 calls, 235,970 input + 51,700 output tokens, USD 0.109236; attempt-level attribution unavailable |
| [`baseline-mobile-editorial.json`](baseline-mobile-editorial.json) (`70f8d46d00f36eeb849547aa99c873beca21f778168451f8bc76887be8e961b9`) | 1 | summary, insight/metric, Expert View, public-editorial hard failure | 0/1 | 11 calls, 119,933 input + 23,322 output tokens, USD 0.051973; attempt-level attribution unavailable |
| [`baseline-doubleverify-linkedin-public-editorial.json`](baseline-doubleverify-linkedin-public-editorial.json) (`a0efdd1a80a30137ce3c213edc83ab2c16b27a4b91868bccd95f2dda51fda71a`) | 1 | summary, insight/metric, Expert View, LinkedIn, public-editorial hard failure | 0/1 | unavailable; no repair-attributable usage ledger was retained |

These manifests are deliberately separate. Their configuration, policy,
schema, validator, and build identities do not form one compatible baseline.
The first two have an unavailable historical validator identity. The third
pins its source result's Git SHA as the build attestation for audits from the
same workflow run; the validator identity is unavailable there as well. The
repair-response schema did not exist at any of these source commits, so its
historical identity is explicitly `unavailable`. The current aggregate schema
identity includes that response schema, which keeps every historical
comparison fail-closed.

## Pre-repair payload inputs

Manifest schema 2.0 pins the production state needed to recreate the payload
passed to the repair loop. Five cases have an `analysis_complete` checkpoint
whose retained `analysis.payload` contains the original payload before
normalization and whose `artifacts_payload` hash matches the frozen original
artifacts. Replay decodes every `ReportPayload` field losslessly and calls the
production `normalize_report()` function. It also verifies the merged result
against the same checkpoint's persisted `normalized_payload`, ignoring only
the original run's vector-store ID and evidence-pack paths, which belong to the
isolated source run.

The mobile and DoubleVerify cases stopped before an analysis checkpoint was
written. Their manifests pin the earliest retained selection checkpoint,
report context, doc map, source-run configuration, and source SQLite database.
The frozen taxonomy and category stage outputs come from that database; replay
applies the production metadata resolution and normalization steps to the
selection payload. The source configuration pins figure-caption generation as
disabled, so reconstruction has no missing model-generated caption step.

All checkpoint, context, doc-map, configuration, database, artifact, and
evidence references are workspace-local and SHA-256 checked. Canonical hashes
pin both the reconstructed base payload and its artifact-merged form. Required
top-level and nested `ReportPayload` fields must round-trip exactly through the
production checkpoint decoder. A missing field, changed figure state, source
hash mismatch, or production completeness failure stops the entire cohort
preflight before any repair model clients are built. The replay then passes the
unmerged pre-repair base payload and original artifacts into the existing
validation-regeneration loop; production validation, evidence, semantic,
editorial, scope, promotion, rollback, and retry limits remain in force.

## Atomic writable-path contract

The repair planner resolves each model repair to exact retained scalar leaves
before provider invocation. That sorted `allowed_paths` set is the single
authority sent to the model and checked against `changed_paths`, every
`minimal_patch` operation, the mutation-scope validator, and the protected
field calculation. Protected fields are the retained leaf complement within
the affected artifact roots, so a repair can change its declared leaves while
unrelated fields and sibling items remain immutable. A decision may contain
multiple `replace` operations when multiple leaves need repair; parent items,
families, and undeclared descendants are rejected.

Planning abstains when it cannot resolve a writable scalar leaf. Before a
provider client is required, runtime preflight also verifies that every path
resolves uniquely to a scalar and that both the writable and protected sets
form a non-empty partition. Deterministic dependent-artifact changes continue
to be recorded and checked through the existing verified-derived-path audit;
they do not become model-writable paths. This contract change is measured
against the unchanged seven-case manifests after the implementation commit.

An atomic target is planned as a unit: if any issue in that target has no exact
leaf resolution, the planner abstains for the whole target instead of dropping
the unresolved issue and widening the remaining repair to its family. Stable
item selectors and positional selectors must resolve to the same retained
leaves in planning, protected-field calculation, patching, and scope comparison.

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
not author replacement copy or raise the configured retry limit. A
non-retryable typed `AppError` from one case is retained on that case's
final-validation stage with its stable failure code and a bounded safe reason,
then replay continues to the next independent frozen case. The case remains
failed, and this does not create a candidate audit or count as repair success.
Retryable errors still propagate and stop the replay.

## Prior measurement disposition — 2026-09-26, implementation SHA `09df2bac76111e44b8e811337c83a1995c791954`

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

The isolated discovery-to-publish readiness canary passed on that SHA in one
attempt and ended at `awaiting_review`; validation and publication readiness
passed, and publication remained disabled. It did not exercise repair and is
not counted in repair metrics. The missing payload inputs were subsequently
pinned in the schema 2.0 manifests.

## Current measurement disposition — 2026-09-26, implementation SHA `baad5a69d9dc63c6a0b9e807c97fa1aea0f8bff3`

All seven frozen cases passed exact payload reconstruction and the production
completeness preflight before repair clients were built. The five analysis
checkpoint cases use the production checkpoint decoder and normalizer; mobile
and DoubleVerify use their earliest retained selection state plus pinned
metadata inputs. No production fields were invented. A comparison against the
original manifests at `02072208` checked 173 historical case fields and input
references with zero mismatches. The three manifests retain their original
cases and historical artifact, evidence, validation, and failure identities.

All seven cases reached the production regeneration loop and ended in failure.
The case outcome count is 0/7 successes; it is separate from the canonical
candidate-audit scorecard denominator:

| Cohort | Cases failed | Cases with candidate audits | Candidate attempts | Scorecard disposition |
| --- | ---: | ---: | ---: | --- |
| A21 | 5/5 | 3/5 | 5 | Available, denominator incomplete, comparison incompatible; success@1 and @3 are 0/3 among audited chains |
| Mobile editorial | 1/1 | 0/1 | 0 | Unavailable; repair decision rejected before candidate audit |
| DoubleVerify | 1/1 | 0/1 | 0 | Unavailable; repair decision rejected before candidate audit |

The A21 audits record 5/5 hard-failure introductions, 5/5 out-of-scope
mutations, and 5/5 unsupported-evidence introductions. They also record one
abstention or removal, zero repeated candidate hashes, and zero repeated
strategy/evidence combinations. A21's scorecard usage attribution is
unavailable; the isolated usage ledger retained 28 events, 219,275 input and
39,158 output tokens, and USD 0.034411. Mobile retained one event (5,547 input,
1,437 output tokens, USD 0.001273); DoubleVerify retained one event (10,419
input, 2,184 output tokens, USD 0.002134). These run-level totals are not
attributed to candidate attempts, and comparable latency/cost is unavailable.
The three cohorts remain identity-incompatible. Since baseline success@3 was
0/7 with unbounded residual odds, no residual-odds reduction is demonstrated.

The required isolated discovery-to-publish canary failed twice at this SHA.
The first run stopped during `insights_candidates` structured-output recovery
(`deterministic_repair_invalid`); the second stopped in the report pipeline
when the production mutation-scope guard rejected a repair decision with
`changed_path_outside_allowed_paths`. Both used fresh isolated state. The
benchmark replays did not change production validation or promotion gates.

The complete per-case outcomes, full emitted scorecards, observed usage,
failure-class coverage, exact commands, canary results, and validation results
are retained in [the 2026-09-26 measurement](results/2026-09-26-baad5a69.json)
(SHA-256 `ef963b0cdc12341dc22f73aa4a4600b9b571aad6d8c4243abc3776a52564b88d`; see
[SHA-256 sidecar](results/2026-09-26-baad5a69.json.sha256)).

E13 remains **Active**. The corpus reconstruction defect is fixed, but closure
criteria are not met: no repair succeeded, A21's measured candidate attempts
exceed the hard-failure, scope, and evidence thresholds, mobile and DoubleVerify
have no candidate-audit measurements, the scorecard denominators are
incomplete, and the required canary failed twice. The documentation gate also
continues to report 12 pre-existing stale line anchors in unrelated
`simplification.md`.
