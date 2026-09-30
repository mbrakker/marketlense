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

## Same-validator repair attribution

For each reconstructed case, replay validates the unchanged original artifacts
and merged payload through the current production candidate-integrity,
semantic-validation, public-editorial, and retained-claim checks before it
starts regeneration. That current report is the loop's `validation_before`;
the frozen historical validation remains provenance and is never supplied to
the planner or repair-delta calculation. Candidate deltas and hard-failure
counts therefore compare reports produced by the same current validator
implementation and run configuration.

A frozen case is `reproducible` when a current hard-error fingerprint matches
one of its pinned historical target fingerprints. If none matches, replay
retains the case in the seven-case corpus, labels it
`no_longer_reproducible`, and skips repair planning. Reproducible cases form
the success@1/@3 denominator, including cases that stop before a candidate is
audited; non-reproducible cases are excluded from both repair successes and
failures. The generated reliability scorecard retains historical and current
fingerprints plus baseline and candidate validator, configuration, policy,
and build identities for each case. Historical cohort comparisons remain
incompatible when their frozen identities do not match the current run.

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

Insight failures resolve to the exact failed leaf. Prose number failures such
as `so_what` remain atomic prose repairs; retained metric failures resolve to
the specific value, unit, timeframe, geography, cohort, denominator, trend,
observation-status, or label leaves implicated by their rule IDs. A canonical
metric copy is selected only when its same-ID retained candidate changes at
least one declared leaf. If a hard metric fingerprint persists after a
downstream public-copy repair, the retry planner uses the latest repair delta
and the promoted baseline's hard issue to repair the source insight first;
matching Expert View or LinkedIn metric-label repairs wait for full candidate
revalidation after the source correction. Retry limits and the evidence,
scope, and promotion validators are unchanged.

For atomic Expert View and LinkedIn claim targets, non-blocking family warnings
remain available as repair context but are excluded from the claim-to-provenance
resolver. Only hard findings select claim spans for mutation, so a warning about
the surrounding family cannot make a uniquely identified failed claim appear
unresolvable.

Planning abstains when it cannot resolve a writable scalar leaf. Before a
provider client is required, runtime preflight also verifies that every path
resolves uniquely to a scalar. The generator computes protected fields as the
actual leaf complement; the complement may be empty when the writable leaf is
the only leaf in its root, and it is never requested from the model.
Deterministic dependent-artifact changes continue
to be recorded and checked through the existing verified-derived-path audit;
they do not become model-writable paths. This contract change is measured
against the unchanged seven-case manifests after the implementation commit.

After the generator restores the declared atomic leaves onto the promoted
artifact, it rebuilds only downstream deterministic projections for source
roots that actually changed. The dependency map is shared by the projection
builders and mutation-scope check. The candidate validator independently
recomputes changed projections through those same canonical builders; only an
exact match makes that changed root's paths legal dependents. A mismatch stays
a `regeneration_derived_projection` error and its changed paths remain outside
scope. The model cannot write projection roots directly.

Prompt cache identities are updated only for prompt calls made during that
repair. A deterministic attempt that makes no prompt call does not add empty
cache maps, so retry metadata does not appear as a candidate mutation. Existing
cache entries are retained, and changed prompt metadata still has to pass the
candidate validator's planned-versus-actual identity checks.

An atomic target is planned as a unit: if any issue in that target has no exact
leaf resolution, the planner abstains for the whole target instead of dropping
the unresolved issue and widening the remaining repair to its family. Stable
item selectors and positional selectors must resolve to the same retained
leaves in planning, protected-field calculation, patching, and scope comparison.
The frozen replay below exercises this contract at implementation SHA
`9120a8fee9289c3850e9f91048a22c9da5457038`.

## Direct-string provider contract replay — 2026-09-27, implementation SHA ed1aa545

The provider-facing minimal_patch operation now uses a direct string value.
The repair response identity is version v5; old and new response contracts
cannot share a cached identity. The pre-provider check confirms that every
planned model path resolves uniquely to a string leaf before a provider client
is required. Internal RepairPatchOperation values remain reusable for
deterministic callers.

The focused IAS path regression passed 14 tests. It retained the exact
expert_comment[claim_index=0] planner path, accepted a direct string
replacement, rejected object and array values at schema validation, rejected
parent and undeclared sibling paths, preserved the sibling text, and passed
candidate validation.

The unchanged A21, Mobile editorial, and DoubleVerify manifests were replayed
at implementation SHA ed1aa545b0f447beb7c8548f15a0c995730f1ccd. The benchmark
manifest identities match the frozen hashes above. Three of seven cases
reproduced; four were no longer reproducible. Six candidates reached
validation and rolled back; none promoted. Success@1/@3 remained 0/3. The new
replay outputs contained zero regeneration_repair_decision_invalid or
patch_value_over_broad occurrences. Isolated cost ledgers recorded 34 provider
calls, 710,547 input tokens, 45,276 output tokens, and estimated USD 0.092600.
Repair-attributed usage was available for DoubleVerify only: 7 calls, 45,412
input tokens, 5,760 output tokens, and USD 0.007422. Attribution was
unavailable for A21 and Mobile.

Compared with the immediately preceding frozen replay, candidate validation
attempts increased from four to six, while promotions and success@1/@3 were
unchanged at zero. Out-of-scope mutation attempts increased from four to six,
and hard-failure introduction attempts increased from two (25 occurrences) to
five (52 occurrences). These candidate outcomes varied across model runs and
are not attributed to the response-contract change.

The isolated IAS canary used fresh state and kept publication disabled. It
terminated at validation_failed during semantic validation, before the
regeneration planner or candidate audit ran. Therefore that canary did not
exercise expert_comment[claim_index=0]; the focused generator regression did.
The canary recorded 38 provider calls, 304,855 input tokens, 49,524 output
tokens, and estimated USD 0.055093. The previous IAS canary had terminated at
regeneration_repair_decision_invalid / patch_value_over_broad after 44 calls,
297,349 input tokens, 56,195 output tokens, and USD 0.057830. The current
canary did not pass the end-to-end workflow gate, and E13 remains **Active**.

The detailed bounded results, commands, test outcomes, frozen manifest
identities, per-cohort counts, and canary limitation are retained in the
[direct-string measurement](results/2026-09-27-ed1aa545.json), with its
[SHA-256 sidecar](results/2026-09-27-ed1aa545.json.sha256).

## Deterministic candidate rejection and evidence metrics

Candidate artifact integrity and mutation scope are resolved before semantic
and grounding provider validation. When either deterministic check returns a
hard error, the candidate audit records
`not_evaluated_due_to_deterministic_failure`; public editorial evaluation,
scope and lineage results, the complete `RepairDelta`, rollback, and retry
memory are still retained. A deterministically valid candidate continues
through the normal semantic, grounding, and public-editorial gates. Candidate
validation usage is attributed by its regeneration task identity, separately
from baseline validation and repair-generation usage.

The scorecard reports introduced hard factual failures in three bounded
categories: unknown or hallucinated evidence identity, unsupported claim or
claim/evidence support, and provenance or lineage. Unknown identity requires
an explicit unknown-evidence rule or reason; a generic `retained_claim.*`
rule is not treated as hallucination. Numeric and protected-fact mismatches
are unsupported-claim failures. Provenance coverage, integrity, source-page,
and lineage rules are reported separately. The historical
`unsupported_evidence_introduction_attempt_count` field remains readable for
older scorecards; use the three explicit counters for current classification.
Historical audits without category or deterministic-validation telemetry keep
those newer measurements unavailable rather than assigning zero.

## 2026-09-27 atomic summary path disposition — implementation SHA `a572ab89cb74c2c480d473e00d159d8f45869651`

The planner now separates summary claim-map leaves from public-copy field
targets before provider invocation. A map-claim request exposes its selected
item and exact `allowed_paths`; the existing repair-decision and candidate
scope validators reject paths outside that set. The atomic summary tests also
verify unchanged sibling claims and public copy, rejection of whole-summary
replacement, and audit retention of planned and applied paths.

The fresh IAS canary completed one isolated workflow attempt with publication
disabled. Its current hard finding was `numbers` on `expert_comment`; summary
findings were warnings and produced no summary repair target. Reconstructing
the production planner from the retained initial artifacts and validation
report yields `expert_comment[claim_index=0]`. The run stopped before candidate
audit or candidate validation at
`regeneration_repair_decision_invalid / patch_value_over_broad`. No candidate
changed-path or applied-patch arrays were retained for that rejected decision,
and no candidate artifact was promoted. This IAS run therefore does not replay
the earlier summary-target failure. Full canary and replay measurements are in
the [2026-09-27 result](results/2026-09-27-a572ab89.json); the isolated run
files remain under ignored `tmp/e13-summary-a572ab89/`.

The unchanged seven-case frozen corpus produced three currently reproducible
cases and four no-longer-reproducible cases. Success@1 and success@3 remain
0/3 (0.0), with zero candidate promotions. The prior replay was 0/4; the
denominator differs because the attachment case is no longer reproducible.
Out-of-scope mutation attempts fell from 6 to 4, introduced scope-violation
occurrences fell from 41 to 25, protected-field incompleteness remained zero,
and provenance/lineage introductions fell from 2 to 1. E13 remains active.
The currently reproducible E13 plans target an insight or Expert View claim;
they do not select a summary claim-map target, so the focused summary contract
tests remain the direct evidence for this path change.

Verification at the implementation SHA: 193 focused atomic/repair tests and
167 broader validation tests passed. The prompt, fixture, and LLM suite passed
40 tests, and the prompt fixture regression gate passed within its configured
token tolerance. The report-analysis planner suite had six failures; the same
six tests failed on the parent commit, while 33 tests passed on this revision.
The documentation validation suite had four passes and one failure from 12
stale heading anchors in `simplification.md`; the parent commit has the same
failure.

## Measurement status

The implementation commit must be measured after it is committed, using its
exact full SHA. Each manifest is replayed independently by
`scripts/quality/replay_validation_repair_benchmark.py` through the existing
production validation-regeneration loop, with the same scoped validation and
artifact-regeneration model service clients used by the report workflow. The
provider schema projection uses the API-supported strict subset; the full
canonical schema remains authoritative when the response is validated. The
repair decision's fixed `replace` operation is explicitly typed as a string
for strict structured output. The response contract is identified as v4; its
failure class is derived from the planner's issue list. Provider decisions carry
replacement values and selected retained evidence IDs; the generator derives
protected fields and soft-copy provenance. Replacement values cross that
provider boundary as JSON-encoded strings and are parsed before the existing
deterministic patch checks. The scorecard retains its normal
validation, evidence, mutation-scope, promotion, and rollback gates. It does
not author replacement copy or raise the configured retry limit. A
non-retryable typed `AppError` from one case is retained on that case's
final-validation stage with its stable failure code and a bounded safe reason,
then replay continues to the next independent frozen case. The case remains
failed, and this does not create a candidate audit or count as repair success.
Retryable errors still propagate and stop the replay.

## 2026-09-27 derived-projection disposition — implementation SHA `61aae82d1f2ad36a00281008a40d7cad904f72d2`

The prior retained audits contained two ebook attempts with two
`regeneration_derived_projection` errors each and six
`regeneration_scope_violation` paths each: three key figures and three chart
cards per attempt. A later DoubleVerify audit also contained one scope
violation for `_cache.regeneration_prompt_requirements`.

The frozen A21 replay's ebook model response left the target item unchanged,
so that live case stopped before candidate artifact generation. The mobile
case stopped on an invalid repair decision, and the DoubleVerify case stopped
on invalid claim-provenance coverage. Across the three new replay outputs,
the one candidate audit contained zero derived-projection and zero scope
violations; the other frozen cases did not reach candidate validation. This
does not count as a live re-execution of those prior scope failures.

To test the exact prior ebook candidate without another model call, the saved
candidate artifact from the prior replay was run through the new deterministic
rebuild using the six hash-pinned evidence packs. Before rebuilding it had two
derived-projection errors and six key-figure/card scope errors. The rebuilt
`key_figures` and `chart_insight_cards` matched both the canonical builders and
the last promoted artifact, leaving zero derived-projection errors and zero
scope errors on those roots. Separate regressions prove the positive case
where a canonical rebuild changes figure/card entries, verify only those
roots, and reject tampering within either family.

The isolated discovery-to-publish canary reached validation pass but ended at
publication readiness failure `card_tldr_compact_invalid`; it made one
workflow attempt and no automatic repair attempt. The failure occurred
outside candidate regeneration. Frozen replay details, manifest hashes,
audit counts, usage, and command outcomes are in the [2026-09-27 result](results/2026-09-27-61aae82d.json)
(SHA-256 recorded in its sidecar).

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

## Prior measurement disposition — 2026-09-26, implementation SHA `baad5a69d9dc63c6a0b9e807c97fa1aea0f8bff3`

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

## Current measurement disposition — 2026-09-26, implementation SHA `9120a8fee9289c3850e9f91048a22c9da5457038`

The unchanged seven frozen cases were replayed independently on the exact
implementation SHA after the code commit. All seven payloads passed the
production reconstruction and completeness preflight; no case or manifest was
changed. Candidate validation was reached for six cases, producing 12
candidate audits. Mobile editorial stopped before candidate validation with
`regeneration_target_item_unchanged`. The strict scorecard denominator is 6/7
because mobile produced no candidate audit; valid success@1 and success@3 are
both 0/6, and the full case outcome is 0/7. Global and attachment each ended
with final validation `pass`, but neither qualifies as a successful repair:
their strict scorecard fingerprints persisted and/or the mutation exceeded the
frozen legal scope. “Runner attempts” below is the attempt count emitted by the
replay result; “not emitted” means that terminal event did not include that
counter. Candidate audit counts independently record how many candidates
reached validation.

| Frozen case | Runner attempts | Candidate audits | Final outcome / terminal failure | Success@1 / @3 | Scorecard out-of-scope attempts | Runtime scope paths | Protected changed / incomplete | Unsupported-evidence attempts | New hard failures |
| --- | ---: | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `2026-global-co-8970fc13f012` | 1 | 1 | validation pass; no terminal code | false / false | 1 | 0 | 0 / 0 | 0 | 0 |
| `attachment-the-6dddc246d289` | 2 | 2 | validation pass; no terminal code | false / false | 0 | 0 | 0 / 0 | 0 | 0 |
| `ebook-0225-fut-997cc1cccd6a` | not emitted | 2 | `schema_type_mismatch` | false / false | 2 | 12 | 0 / 0 | 1 | 17 |
| `final-web-vers-1d9e64dd7425` | 3 | 3 | `validation_failed_after_max_attempts` | false / false | 3 | 39 | 0 / 0 | 3 | 52 |
| `g0-ec-trends-r-41f8ffd78145` | not emitted | 1 | `regeneration_repair_decision_invalid` / `protected_fields_incomplete` | false / false | 1 | 4 | 0 / 1 | 1 | 6 |
| `public-editorial-linkedin-mobile-app` | not emitted | 0 | `regeneration_target_item_unchanged` before candidate validation | unavailable | 0 | 0 | 0 / 0 | 0 | 0 |
| `doubleverify-linkedin-public-editorial-hard-failure` | 3 | 3 | `validation_failed_after_max_attempts` | false / false | 1 | 1 | 0 / 0 | 2 | 3 |

The original terminal repair-decision guard classes are now absent from the
replay: `changed_path_outside_allowed_paths` 0, `patch_target_not_atomic` 0,
and `protected_field_changed` 0. No validator was relaxed. Candidate-level
scope failures still occur: the unchanged runtime scope validator reported 56
out-of-scope path occurrences, and the frozen-scope scorecard marked 8/12
candidate attempts out of scope. Audited paths identify deterministic derived
projections and expert-comment provenance, plus one `_cache` prompt-requirement
path; these remain integrity failures and were not promoted. One subsequent
repair decision failed closed with `protected_fields_incomplete`. Across the 12
candidate audits, 78 new hard failures were introduced in 8 attempts and
unsupported evidence was introduced in 7 attempts. Existing evidence,
grounding, public-editorial, promotion, rollback, and retry gates remained
active. Scorecard comparison is incompatible across cohorts, the denominator
is incomplete, and provider usage is not attributable to repair attempts.

The required isolated IAS discovery-to-publish canary passed on this SHA in one
workflow attempt: validation and publication readiness passed, final state was
`awaiting_review`, and publication remained disabled. It made 41 provider calls
(260,610 input and 44,466 output tokens; USD 0.048154) in 310.049 seconds. A PDF
parser emitted an invalid-float warning; the run still passed both gates. This
canary does not exercise candidate repair and is excluded from E13 repair
metrics.

The retained result includes each case outcome, emitted scorecards, bounded
candidate-audit summaries and hashes, exact commands, usage attribution,
canary outcome, and validation results: [2026-09-26 measurement](results/2026-09-26-9120a8fe.json)
(SHA-256 `56bdc065fcfade8e0e1c87cca6595bc4bd455b261de986233cddeb8c8e41f797`; see [SHA-256 sidecar](results/2026-09-26-9120a8fe.json.sha256)).
Full private audits and run data remain in isolated local storage. The result
contains no rendered prompt, source extract, model response, or replacement
copy.

E13 remains **Active**. This change removes the three observed atomic
repair-decision guard failures, but it does not yet establish atomic scope
safety across candidate artifacts: the scorecard still records 8/12
out-of-scope attempts and 56 runtime scope-path occurrences. The evidence,
semantic, public-editorial, and newly introduced hard-failure thresholds also
remain unmet; the denominator and cohort comparison are incomplete, residual
odds are unbounded, and no valid success@1/@3 is demonstrated. The canary
passed but is not repair evidence. The documentation validator still reports
12 pre-existing stale anchors in unrelated `simplification.md`.

## Same-validator measurement — 2026-09-26, implementation SHA `6a9c8d07851f27d682be12920cee538898f21a85`

The unchanged seven-case corpus was replayed against the exact committed
implementation. The three frozen manifest hashes match their retained values.
Current baseline and candidate reports carry the same validator identity,
configuration hash, policy hash, and build identity. Frozen historical
validation remains provenance and comparison data; it was not passed to
current repair planning or delta calculations.

Four cases reproduced their historical target failure under the current
validator, and three were classified `no_longer_reproducible`. The latter were
skipped before repair planning and remain in the seven-case corpus count, but
are excluded from repair successes and failures. The effectiveness denominator
is therefore 4: success@1 is 0/4 and success@3 is 0/4. The case that ended with
replay status `pass` among the non-reproducible cases had no repair attempt and
is not a repair success. The four reproducible cases also produced no
successful repair.

| Cohort | Cases | Reproducible | No longer reproducible | Success@1 / @3 denominator | Success@1 / @3 | Candidate validations | Introduced hard-failure observations | Persisting | Resolved |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| A21 | 5 | 2 | 3 | 2 | 0/2, 0/2 | 3 | 21 | 13 | 2 |
| Mobile editorial | 1 | 1 | 0 | 1 | 0/1, 0/1 | 0 | not observed | 0 | 0 |
| DoubleVerify | 1 | 1 | 0 | 1 | 0/1, 0/1 | 3 | 3 | 24 | 3 |
| **Total** | **7** | **4** | **3** | **4** | **0/4, 0/4** | **6** | **24** | **37** | **5** |

The mobile case reproduced, but the repair stopped at
`regeneration_target_item_unchanged` before candidate validation; its
introduced-failure count is unavailable, not zero. Across cases that reached
candidate validation, same-validator comparison recorded 24 introduced hard
failure observations over four attempts, 37 persisting observations, and 5
resolved observations. Cohort-to-historical comparisons remain incompatible.
The exact per-case reproducibility status, current baseline fingerprints,
validator identities, scorecard hashes, and commands are in the
[2026-09-26 measurement](results/2026-09-26-6a9c8d07.json) (SHA-256
`b715fb9bcd6c3b78fdc7bcf2dff1236975d86de9a84f01dd76c0230fc56722b0`; see
[SHA-256 sidecar](results/2026-09-26-6a9c8d07.json.sha256)).

The required isolated IAS workflow ran at this SHA with fresh state and
publication disabled in two runs. The first failed during semantic validation for
`insights:ctv-quality-concerns`; the semantic validator reported that the
inventory-and-sellers condition was attached to the 82% brand-safety figure
instead of the 84% attention-measurement figure. The existing regeneration
scope gate also rejected an undeclared artifact-path change. This failure is
in generated content and existing validation/scope behavior; the benchmark-
only baseline helper is not used by the canary. A fresh-state rerun failed
before candidate validation when the existing repair-decision patch gate
returned `patch_application_failed`; the benchmark baseline and delta-count
helpers do not participate at that stage. Both runs kept publication disabled.
Their usage, run directories, parser warning, and terminal outcomes are
retained in the result. E13 remains **Active**: no reproducible case succeeded,
and neither required-workflow canary run passed.

## Deterministic validation telemetry — 2026-09-27, implementation SHA `bd8f2927`

The unchanged three manifests were replayed at exact implementation SHA
`bd8f29277cba42a97e3bdaf756cbbd31ebef757d`; their hashes match the frozen
values above. Five candidate attempts had deterministic hard failures in both
the baseline and current replay. Before the fast-fail change, all five still
ran semantic/grounding validation. Afterward, all five were recorded as
deterministic rejections and skipped those provider validations while retaining
candidate audits, scope results, `RepairDelta`, rollback, and retry memory.

| Cohort | Deterministic hard rejects before / after | Candidate semantic/grounding provider calls before / after | Repair attempts before / after | Success@1 before / after | Success@3 before / after |
| --- | ---: | ---: | ---: | ---: | ---: |
| A21 | 2 / 2 | 4 / 0 | 2 / 2 | 0/2 / 0/1 | 0/2 / 0/1 |
| Mobile editorial | 0 / 0 | 0 / 0 | 0 / 0 | 0/1 / 0/1 | 0/1 / 0/1 |
| DoubleVerify | 3 / 3 | 6 / 0 | 3 / 3 | 0/1 / 0/1 | 0/1 / 0/1 |
| **Total** | **5 / 5** | **10 / 0** | **5 / 5** | **0/4 / 0/3** | **0/4 / 0/3** |

The skipped candidate validations avoided 10 provider calls, 180,612 input
tokens, 17,787 output tokens, and USD 0.026245 in the baseline usage ledger.
The current scorecards attribute zero semantic/grounding candidate calls,
tokens, and cost to the five rejected attempts. Mobile stopped at
`regeneration_target_item_unchanged` before candidate validation, so its
candidate-specific counters remain unavailable. The success denominator fell
from four to three because one A21 case no longer reproduced; no repair
succeeded in either replay.

The new factual-introduction counters report 0 unknown/hallucinated evidence,
0 unsupported-claim evidence, and 0 provenance/lineage introductions across
the five audited candidate attempts. The baseline did not persist these split
counters, so its counts were reconstructed from retained audit issues and
introduced fingerprints with the same explicit rule/reason classifier. The
mobile case has no candidate audit and remains unavailable for these counts.

The required isolated IAS workflow passed at this SHA in one attempt, with
validation and publication readiness passing, terminal state `awaiting_review`,
and publication disabled. A PDF float-parse message appeared during the run;
the canonical workflow continued and completed successfully. E13 remains
**Active** because success@1/@3 and repair-success thresholds remain unmet.
Exact commands, bounded metrics, scorecard hashes, and canary evidence are in
the [2026-09-27 measurement](results/2026-09-27-bd8f2927.json) (SHA-256
recorded in its [sidecar](results/2026-09-27-bd8f2927.json.sha256)).

## Atomic soft-copy provenance replay — 2026-09-27, implementation SHA `197ba2d4544a49c2d9050c2ce74811f95b1dc045`

The same seven frozen cases were replayed at the committed provenance repair
implementation. All three frozen manifest hashes matched. `final-web` and
`g0` were classified `no_longer_reproducible`: their historical target
fingerprints were absent from current baseline validation, so neither reached
repair planning or candidate audit. This is not evidence of a repaired
candidate. The ebook case remained reproducible but stopped at
`regeneration_target_item_unchanged`, before candidate validation. The mobile
editorial case stopped at the same unchanged-target gate.

The DoubleVerify Expert View / LinkedIn case reached three candidate attempts.
Its candidate audits had no soft-copy provenance-integrity or protected-field
contract failure. All three attempts rolled back on remaining content checks,
including metric-label relationship and retained numeric/protected-fact
support. Candidate semantic/grounding validation made zero provider calls on
these deterministic rejects. Across the cohort, no audited attempt introduced
unknown or hallucinated evidence or a provenance/lineage defect; one A21
attempt introduced an unsupported-claim/evidence failure. The mobile case had
no candidate audit, so candidate introduction metrics are unavailable there.

| Cohort | Cases | Reproducible | No longer reproducible | Attempts | Success@1 / @3 | Factual introduction attempts: unknown / unsupported / provenance |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A21 | 5 | 2 | 3 | 2 | 0/2, 0/2 | 0 / 1 / 0 |
| Mobile editorial | 1 | 1 | 0 | 0 | 0/1, 0/1 | unavailable |
| DoubleVerify | 1 | 1 | 0 | 3 | 0/1, 0/1 | 0 / 0 / 0 |
| **Total** | **7** | **4** | **3** | **5** | **0/4, 0/4** | **0 / 1 / 0** |

These are case-level repair-success metrics: no reproducible case met the
scorecard success condition, even though one A21 candidate had a promoted
attempt. A21 attributed two repair-model calls, 13,527 input tokens, 1,781
output tokens, and USD 0.002243. DoubleVerify's aggregate scorecard usage
attribution was unavailable; its two non-abstention attempt records show two
repair-model calls, 8,584 input tokens, 821 output tokens, and USD 0.001269.
The third attempt used safe removal. Across the four model-backed repair
attempts, the available attempt records total four repair-model calls, 22,111
input tokens, 2,602 output tokens, and USD 0.003512. Its candidate semantic /
grounding scorecard reports zero provider calls and three skipped validation
invocations. Historical and current scorecards are not comparable for usage or
failure distributions.

The required isolated IAS workflow was run twice with publication disabled;
neither run passed. The first reached validation pass but failed publication
readiness at `card_tldr_compact_invalid` (39 provider calls, 249,704 input and
49,113 output tokens, USD 0.049389). A fresh-state rerun terminated at
`validation_failed` on grounding for an insight's `so_what` field (38 calls,
242,095 input and 42,559 output tokens). Both emitted the existing PDF float
parse warning and published nothing. The second run's candidate audit also
reported soft-copy provenance integrity issues for Expert View / LinkedIn
content that was byte-identical before and after the candidate; inspection
showed claim-validator sentence fragments absent from the material-sentence
index. This existing segmentation mismatch remains unresolved. The canary's
terminal failures were the compact-summary gate and insight grounding, and the
required end-to-end canary remains unpassed.

The exact replay classifications, bounded usage, case-level scorecard hashes,
telemetry hashes, canary outcomes, and verification commands are in the
[2026-09-27 provenance measurement](results/2026-09-27-197ba2d4.json) (SHA-256
recorded in its [sidecar](results/2026-09-27-197ba2d4.json.sha256)). E13 remains
**Active**: final-web, g0, and ebook did not reach repair candidate validation;
the DoubleVerify candidate audits had no provenance or protected-field
contract defects, but content validation blocked promotion and the required
workflow canary did not pass.

## Atomic source-target planner replay — 2026-09-27, implementation SHA `d6bf489c`

The same three frozen manifests were replayed at the committed planner and
generator change. All manifest hashes matched. Five of seven cases reproduced
at current validation; two were no longer reproducible. The Mobile case now
plans the exact `insight-005.so_what` leaf and reached candidate validation on
all three attempts instead of stopping at `regeneration_target_item_unchanged`.
Attempts one and two resolved the original numbers and LinkedIn grounding
failures, then rolled back on deterministic key-figure/chart projection checks.
The existing safe-removal attempt also failed candidate integrity and the run
ended at `report_payload_incomplete`; no Mobile candidate was promoted.

For DoubleVerify, offline reconstruction from the unchanged persisted current
validation report, deterministic candidate checks, retained-claim diagnostics,
and frozen artifacts puts the canonical Q1 metric's exact `value` and `unit`
leaves before Expert View. The replay recorded one insight-generation provider
call, then failed at the separate Expert View claim scope partition check. It
produced no candidate audit or candidate validation. This confirms source-first
planning but does not count as a repair or promotion.

Across the five reproducible cases, the replay made nine repair provider calls
and reached seven candidate audits. Two candidates were promoted in A21, but
persisting failures kept case success@1 and success@3 at 0/5. One A21 and one
Mobile candidate introduced unsupported-claim failures; no attempt introduced
unknown or hallucinated evidence or a provenance/lineage failure. Three audits
were explicitly marked `not_evaluated_due_to_deterministic_failure`; a fourth
Mobile audit recorded deterministic failures with semantic/grounding status
`not_evaluated`. The unchanged validation checks remain enabled.

The required isolated IAS workflow passed on this SHA in one attempt, with
validation and publication readiness passing, terminal state `awaiting_review`,
and publication disabled. It made 39 provider calls (253,205 input and 57,405
output tokens; USD 0.053880). The PDF float-parse warning appeared, and the
workflow completed successfully.

The detailed per-case fingerprints, targets, actions, call counts, candidate
validation and failure deltas, promotion outcomes, verification commands, and
canary evidence are in the [2026-09-27 planner measurement](results/2026-09-27-d6bf489c.json)
(SHA-256 recorded in its [sidecar](results/2026-09-27-d6bf489c.json.sha256)).
E13 remains **Active**: success@1/@3 is 0/5, Mobile did not promote, and
DoubleVerify did not reach candidate validation or promotion.

When a candidate resolves every authoritative source metric fingerprint but
still fails downstream public-copy validation, retry planning keeps the source
target first and also includes the matching public-copy target. The retry
memory's `resolved` set must cover all current source fingerprints before those
dependent targets are admitted; otherwise planning remains source-only. This
lets the next candidate repair the source and its dependent copy in one bounded
attempt after prior evidence proved that the source edit itself worked.

The insight safe-removal strategy is planned only when its issue set resolves
to one stable failed insight ID, which is the existing removal handler's
atomicity contract. A multi-insight batch that exhausts its rewrite and
rebind strategies is left blocked before the invalid single-item removal path.

## Root-target planner replay — 2026-09-27, implementation SHA `6854d5d2`

The unchanged A21, Mobile editorial, and DoubleVerify manifests were replayed
at the committed planner SHA. Their hashes match the frozen manifests. Four of
seven cases reproduced at the current validator; three A21 cases were no
longer reproducible. The current case-level denominator is four, and success
at one or three attempts is 0/4. One A21 attachment candidate was promoted,
but its case did not meet the scorecard closure condition. E13 remains
**Active**.

Mobile's four root fingerprints cover the unsupported `1.0` number in
`insight-005.so_what`, grounding failures in insight 002 and insight 005, and a
LinkedIn grounding failure. The planner targeted the two exact `so_what`
leaves and LinkedIn claim 5. All three attempts reached candidate validation;
none promoted. Candidate diagnostics resolved the baseline number and
grounding failures, but each candidate introduced unsupported key-figure facts
and unverified downstream projection or scope changes across `key_figures`,
`chart_insight_cards`, `metric_spine`, or `executive_advisory`. The old
`regeneration_target_item_unchanged` terminal did not recur.

DoubleVerify's six root fingerprints include three retained metric
value/unit/number failures, Expert View and LinkedIn metric-label relationship
failures, and a LinkedIn grounding failure. Attempt 1 targeted the canonical
insight metric's exact `value` and `unit` leaves before the LinkedIn claim; the
retained metric failures persisted. Attempt 2 kept the metric source first and
cleared the retained metric and metric-label findings in the candidate, but
introduced `unsupported_numeric_claim` and `regeneration_source_page`. On the
next planning pass, retry memory admitted the dependent metric-label repairs
for Expert View and LinkedIn. Attempt 3 included those claims; deterministic
validation rejected the candidate for an executive-advisory projection
mismatch and reintroduced removed insight. All three candidates rolled back.

The A21 ebook case reached two candidate validations for the exact summary
claim/evidence-map item. Both rolled back, and the case ended at
`schema_type_mismatch`. A21 attachment reached candidate validation twice and
promoted its second evidence rebind, while the A21 scorecard still recorded
0/2 case-level closures. Across reproducible cases, the isolated usage ledgers
recorded 17 artifact-generation provider calls (146,927 input and 19,082
output tokens; estimated USD 0.023329). The benchmark scorecard could not
attribute Mobile and DoubleVerify aggregate usage.

The final isolated IAS workflow used fresh state and kept publication disabled,
but did not pass. It terminated at `regeneration_repair_decision_invalid` with
reason `patch_value_over_broad` before reaching `awaiting_review` (39 provider
calls, 265,570 input and 51,388 output tokens, USD 0.052109). The model's
over-broad patch was rejected by the existing repair contract. The specific
multi-insight safe-removal failure seen in the previous canary was not reached
in this run; the planner regression test covers that guard directly.

Per-case fingerprints, targets, candidate deltas, usage, validation commands,
and canary evidence are in the [2026-09-27 root-target measurement](results/2026-09-27-6854d5d2.json)
(SHA-256 recorded in its [sidecar](results/2026-09-27-6854d5d2.json.sha256)).
E13 remains **Active**: no reproducible case met scorecard closure, and the
required isolated workflow did not pass.

## Deterministic diagnostics after candidate rejection

When candidate integrity or mutation-scope validation rejects an attempt,
the orchestrator still runs the existing validation registry in
`inline_deterministic` mode. This retains deterministic findings such as
numbers, metrics, quotes, claim support, artifact quality, and family
confidence in the candidate report and `RepairDelta`. Existing deterministic
public-editorial validation also runs. Semantic and grounding provider calls
remain skipped, and the audit records
`semantic_grounding_validation_status=not_evaluated_due_to_deterministic_failure`.
Issues with the same existing failure fingerprint are emitted once, keeping
the strongest severity. Retry memory receives the merged deterministic delta;
promotion, scope, integrity, retained-claim, and rollback gates are unchanged.
Candidate report-payload incompleteness is retained as a hard validation issue
in the same audit and delta, so it cannot bypass deterministic diagnostics.
Candidates that pass deterministic candidate checks continue through the full
validation path.

The informational `deferred_grounding_required` issue remains in the stored
candidate validation report and audit, alongside the bounded
`semantic_grounding_validation_status`. It is excluded only when constructing
`RepairDelta`, so it cannot be classified as introduced, persisting, resolved,
or as a severity transition, and retry memory contains only repair findings.
Other warning, info, and error issues retain their existing delta behavior.

## Inline deterministic replay measurement — 2026-09-27, implementation SHA `f48f795c`

The unchanged A21, Mobile editorial, and DoubleVerify manifests were replayed
with their frozen hashes. Four of seven cases reproduced; three were no longer
reproducible. The replay produced nine candidate audits and five deterministic
rejections: three Mobile attempts and two DoubleVerify attempts. Those five
audits retained a combined 108 `RepairDelta` finding occurrences across
introduced, persisting, and resolved states. The captured rules include
`artifact_quality`, `numbers`, `metrics`, `public_editorial_quality`,
`regeneration_scope_violation`, and provenance findings. The exact per-attempt
rule counts are in the [inline deterministic measurement](results/2026-09-27-f48f795c.json).

The rejected attempts emitted zero semantic or grounding provider events. This
preserves ten avoided calls compared with running the normal two-provider path
for all five rejected candidates. The skipped calls used zero tokens and cost
zero in the usage ledger; the full-validation counterfactual token and cost
amount is not estimated because no requests were sent. Across the replay, the
artifact regeneration ledger recorded 16 calls, 108,502 input tokens, 13,342
output tokens, and estimated USD 0.016615. Compared with the prior replay, those
totals were lower by one call, 38,425 input tokens, 5,740 output tokens, and
USD 0.006714; regeneration targets and model outputs differed, so that aggregate
difference is not attributed to inline deterministic validation.

Case-level success remains 0/4 at one attempt and 0/4 at three attempts. One
A21 attachment candidate promoted, but the case did not meet its closure
criteria. The new findings give retry planning a fuller deterministic delta,
but did not produce a measured case-level promotion improvement. E13 remains
**Active**.

The required isolated IAS workflow canary used fresh state with publication
disabled, but failed in report-analysis repair application with
`regeneration_repair_decision_invalid` (`patch_application_failed`) before
`awaiting_review`. The [earlier mainline canary](results/2026-09-27-6854d5d2.json)
had the same terminal code with a different patch-rejection reason. The full
workflow gate therefore remains failed. The focused orchestrator and
regeneration/validation suites passed (4 focused and 216 combined tests); the
broader affected suite had 268 passes and the same two known frozen
queue-lineage failures recorded in the prior measurement.

Replay manifests, per-attempt deterministic `RepairDelta` counts, usage totals,
canary results, and verification outcomes are retained in the [2026-09-27
measurement](results/2026-09-27-f48f795c.json), with its [SHA-256 sidecar](results/2026-09-27-f48f795c.json.sha256).

## Deferred-grounding RepairDelta cleanup — 2026-09-27, implementation SHA `26be4e17`

The unchanged frozen A21, Mobile editorial, and DoubleVerify manifests were
replayed after filtering the informational `deferred_grounding_required` issue
at the `RepairDelta` boundary. The issue remains in candidate validation
reports and audits, with
`semantic_grounding_validation_status=not_evaluated_due_to_deterministic_failure`;
its `RepairDelta` occurrences fell from 5 to **0**. The three deterministic
rejections in this replay retained their real scope, artifact-quality,
derived-projection, retained-claim, numbers, and grounding findings. No
semantic or grounding provider event occurred on those rejected attempts.

This replay was not output-identical to the prior run. It had three
deterministic rejections and six avoided semantic/grounding calls, compared
with five rejections and ten avoided calls previously. On all eight overlapping
attempts, allowed paths, actions, and strategies matched the prior replay;
seven candidate hashes changed. DoubleVerify attempt 2 used the same plan but
produced a different candidate hash and promoted. Attempt 1 had full validation,
so the marker was not in its retry memory. The changed rejection and promotion
counts therefore followed changed model output, not a retry-plan change caused
by this cleanup. Artifact-generation usage was 13 calls, 89,246 input tokens,
12,824 output tokens, and estimated USD 0.015338; these totals are not attributed
to the marker filter. Skipped provider calls themselves used zero observed
tokens and cost USD 0; a full-validation counterfactual was not estimated.

Success remained 0/4 at both one and three attempts. Two candidates promoted,
but no reproducible case met its closure criteria; E13 remains **Active**.
The required isolated IAS workflow canary also failed before `awaiting_review`
with `regeneration_repair_decision_invalid` / `patch_application_failed`.
Its initial repair targeted `summary.claim_evidence_map[3].claim` but proposed
changes to `summary.executive_summary[claim_index=0..4]` as well, so the existing
repair contract rejected the out-of-target patch. This was the first repair
application, before retry memory or `RepairDelta` filtering was involved.
Publication remained disabled.

The [deferred-grounding cleanup measurement](results/2026-09-27-26be4e17.json)
contains frozen manifest hashes, per-case attempt outcomes, bounded real
finding counts, provider usage, and verification results; its [SHA-256
sidecar](results/2026-09-27-26be4e17.json.sha256) verifies the retained record.
The broader affected suite had 270 passes and the same two known frozen
queue-lineage failures recorded in the prior measurement. Focused tests,
registry tests, scorecard/telemetry tests, lint, formatting, and typing passed.

## Atomic summary safe-removal replay — 2026-09-30, `427af8fb`

The unchanged A21, Mobile editorial, and DoubleVerify manifests were replayed
at implementation `427af8fb3810e2ece49d90b254dfaee2a93c95ee`. The seven cases
had three reproducible chains and four no longer reproducible cases. Four
candidate validations produced one promotion; strict success@1 and success@3
remain 0/3. Deterministic projection errors and deterministic-dependent scope
violations were both zero. Three out-of-scope patch attempts were rejected;
one unsupported-evidence introduction and one provenance/lineage introduction
remained blocking and were rolled back. No removed insight was reintroduced.

The replay used 82 provider calls, 779,201 input tokens, 363,158 output
tokens, and estimated `$0.246059`. The previous retained replay at
`0be495a9` had 35 calls, 799,767 input tokens, 159,178 output tokens, and
estimated `$0.154546`; these are observed replay totals, not a controlled cost
comparison because provider responses and candidate counts vary. The current
strict closure rate did not improve. Full per-manifest counts, scorecard
hashes, and the comparison are in the [retained E13 measurement](../reliability-cohort-20260927-grounding/final-package-lifecycle-5/2026-09-30-427af8fb-e13-replay-measurement.json).

This repair fixes the separate Emplifi summary safe-removal merge defect in the
five-report normal-processing cohort. E13 continues to serve as a historical
repair benchmark; its residual candidate failures stayed blocked and were not
used to waive current claim or scope validation.
