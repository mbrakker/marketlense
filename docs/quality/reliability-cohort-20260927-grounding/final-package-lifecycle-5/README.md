# Final retained-claim package lifecycle — pinned five-report cohort

This follow-up uses exactly five reports from the frozen reliability cohort:
Merchant Risk Council, Deloitte, Emplifi, StackAdapt, and DoubleVerify. The
source files and checksums are pinned in [`frozen_cohort.json`](frozen_cohort.json).
The full 20-report cohort is not part of this measurement.

The runner uses fresh isolated state and the normal production report workflow.
It stops at publication readiness and does not perform WordPress publication.
The temporary database and full workflow output stay under the ignored `tmp/`
directory; this README will retain only sanitized scalar counts, run identities,
hashes, and typed per-report outcomes.

Invocation:

```powershell
python scripts/quality/run_frozen_reliability_cohort.py `
  --sources-manifest docs/quality/reliability-cohort-20260927-grounding/final-package-lifecycle-5/frozen_cohort.json `
  --runs-root tmp/retained-claim-package-lifecycle-5 `
  --max-duration 7200
```

## Measurement — 2026-09-27 UTC

The pinned five-member cohort ran once from fresh isolated state against
implementation `2f0e7c925e2543a10266582c716ae7fd20fa77f9`. It admitted all five
reports, took 1,138.97 seconds, made 129 provider calls during normal processing,
and made no WordPress publication attempt. The run identity is
`frozen-reliability-mwi3zq_8` / `ias-first-attempt-trbpwjto`.

The exact manifest SHA-256 is
`5a2b8bc4dd7c6d919f66770437c83439233e4671c2c673de9dbb30dc5086cc04`; the
retained `cohort_result.json` SHA-256 is
`188985a4a8d8d72c0a78dca9e5794c4737918627ee42390ead46f6fdd942b8a5`.
The runner summary records 1,350,377 input tokens, 195,499 output tokens, and
estimated cost `$0.232007`. Those are cohort totals, not readiness-stage use.

### Readiness and package counts

Three reports reached final HTML and report-level readiness evaluation. All
three have a final retained-claim package whose report ID, final artifact hash,
source identity, configuration/policy, and validator lineage match the
readiness record. The readiness record's retained-package hash equals that
package's `package_hash` in each case.

| Measurement | Result |
| --- | ---: |
| Eligible final reports | 3 |
| Final packages materialized and bound | 3 |
| Unexplained `package_missing` among eligible reports | 0 |
| `package_invalid` | 0 |
| `not_publishable` | 2 |
| Report-level readiness passes | 1 |
| Provider calls during report-level readiness | 0 |
| Queued publication-readiness handoffs | 0 (publication disabled) |
| Typed pre-package validation failures | 2 |

The runner's `publication_readiness_rate` is the later queued handoff measure;
it is 0/5 because publication was disabled and no publication-readiness jobs
were created. The report-level decisions below come from each canonical
`report_analysis/publish_readiness.json` artifact. The usage ledger also has
zero events whose stage, semantic task, or prompt namespace identifies
readiness, and focused tests assert that the readiness call path makes zero
provider calls.

| Report | Final artifact SHA-256 | Final package SHA-256 | Report-level outcome | Terminal outcome |
| --- | --- | --- | --- | --- |
| Merchant Risk Council | `84c6806bf0b09a555addb480719afcfcb53e4fd654b326f190b0ea12b4d825d5` | `4efad163fa6d707ce9338d86795fa12840a0665929cee464a5fe321a615de847` | `not_publishable`; 0 unsupported and 9 unresolved factual claims | `publish_readiness_failed` |
| Deloitte | `e13ed55579d5af46b5c4763b8cf6ab7545f25752a29e4277e25a9c3007f90018` | `35f60c6f2f63bea4f604aee64b3b04b0eab774115d7bde8ec8b23ccb9b3252d8` | `not_publishable`; 0 unsupported and 17 unresolved factual claims | `publish_readiness_failed` |
| Emplifi | `ef6030d2108130d1e858d53f5d80ea91f3708d628c0e144db7d059f971015cd6` | `62d4a99b03421af739dee4ec54b27ca903411bddd5545ba143e6f6d74f95a6bc` | `pass`; package is `awaiting_review` | `card_tldr_compact_invalid` after readiness |
| StackAdapt | — | Candidate only | No final package/readiness; validation failed before promotion | `validation_failed` |
| DoubleVerify | — | Candidate only | No final package/readiness; validation failed before promotion | `validation_failed` |

Merchant Risk Council therefore reproduces the prior pattern with the final
43% value retained in the canonical artifacts and a usable package bound to
the exact final artifact. The final summary claim identity `summary_claim:2`
is `supported` by deterministic validation and retains three protected facts.
Its readiness block is explicit and claim scoped:
`publish_readiness.retained_claim_grounding` reports 9 unresolved claims. It
does not fail because the final package is missing or stale.

The three evaluated reports have the same 15 readiness rules. Emplifi passed
all 15. Merchant Risk Council passed all except
`publish_readiness.retained_claim_grounding`. Deloitte passed all except
`publish_readiness.public_identifier_leak` and
`publish_readiness.retained_claim_grounding`. The retained grounding blocks
remain in force; this cohort does not waive unsupported or unresolved claims.

The other two reports stopped before finalization with typed `validation_failed`
outcomes. Their candidate packages were not promoted, no final package was
written, and no readiness record was produced. The Emplifi card error occurred
after its final package and report-level readiness pass; the package remains
bound, while the overall report correctly retains the later typed terminal
failure.

## Deterministic repair finalization measurement — 2026-09-28 UTC

The deterministic post-repair finalization changes were measured at
`a7fd7aca7eedbb6d27dec11c100cc344ee7dc653`. The unchanged E13 frozen corpus was
replayed using its three existing manifests, followed by the pinned five-report
cohort from fresh isolated state and one isolated IAS canary. Publication was
disabled in the live workflow runs. The full 20-report cohort was not run.
Sanitized per-run measurements, manifest/output hashes, and typed outcomes are
retained in
[`2026-09-28-a7fd7aca-finalization-measurement.json`](2026-09-28-a7fd7aca-finalization-measurement.json).

### E13 deterministic finalization

Across seven frozen cases, four historical cases were no longer reproducible.
The three reproducible chains produced eight candidate validations and no
promotions. Success@1 and success@3 were both 0/3. Current candidate scorecards
recorded zero derived-projection errors, zero deterministic-dependent scope
violations, zero unsupported-evidence introductions, and zero provenance or
lineage introductions. One Mobile candidate attempted to reintroduce a removed
insight; validation blocked it and the candidate was rolled back.

Four retained, previously rolled-back Mobile and DoubleVerify candidates were
also replayed offline through the current validators with zero provider calls.
That replay found six derived-projection issues, 720 changed-path scope
violations, six provenance findings, one claim-support finding, and one
number/value/unit finding. These retained snapshots are historical fixture
evidence and are separate from the eight newly validated E13 candidates.

The E13 runs used 39 provider calls, 1,021,678 input tokens, 48,875 output
tokens, and estimated cost `$0.120091`. No readiness provider calls occurred.

### Five-report finalization outcome

All five pinned reports were admitted. Two reached final-package readiness:
Deloitte and Emplifi each materialized a final package bound to its final
artifacts. Both were correctly blocked as `not_publishable` with 13 unresolved
factual claims and no unsupported claims. Readiness passed zero reports; it
reported zero `package_missing`, zero `package_invalid`, and made zero provider
calls. There were three typed pre-package failures. Merchant Risk Council
stopped in semantic validation on
`public_editorial_quality.duplicate_insight` before finalization or readiness;
the two other pre-package failures were typed `insight_safe_removal_no_replacement`
outcomes. Thus this run had two eligible reports, two materialized packages,
zero unexplained `package_missing` outcomes, and no publication or handoff.

The cohort used 147 provider calls, 1,520,993 input tokens, 215,865 output
tokens, and estimated cost `$0.256144` over 1,333.021 seconds. The package
hashes and report-level outcomes are in the retained JSON record.

### Isolated IAS canary

The fresh IAS canary stopped before finalization at artifact generation with
typed `artifact_structured_output_invalid`: the summary structured output
referenced missing `source:page:2`. It made 33 provider calls, used 208,921 input
and 39,651 output tokens, and cost an estimated `$0.040717`. Publication was
disabled. This is an artifact-generation failure, not a deterministic
post-repair finalization result.

## Validation

The focused package, readiness, renderer, retained-grounding, and frozen-cohort
suite passed: 144 tests. The A21 full-chain grounding regressions passed 3
tests (1 deselected); the queue stage-builder regression passed 1 test (3
deselected). Contract schemas passed. The scoped Ruff check passed with the
repository's existing `E501`/`I001` baseline findings excluded. The
editorial-output evaluation
also passed: 61 generator/report-quality tests, 34 public-render tests, and
`python scripts/ci/check_public_report_quality.py`.

The earlier five-report run used the command shown above. The full 20-report
cohort was not run. For the 2026-09-28 measurement, the focused deterministic
finalization suite passed 331 tests; formatting, Ruff, forbidden-patching,
architecture imports, role I/O boundaries, service-boundary mapping, contract
schemas, and public-report-quality checks passed. The generated-documentation
check still reports 12 invalid anchors in untouched
`docs/quality/simplification.md`; type checking still reports two unbaselined
errors in untouched `claim_validation_generator.py` and
`publish_readiness_generator.py`. Full raw workflow state remains under ignored
`tmp/`; committed measurements contain only sanitized identities, hashes,
rule IDs, typed outcomes, and scalar metrics.

### 2026-09-28 post-repair finalization rerun

The follow-up ran the unchanged three-manifest E13 frozen corpus, the pinned
five-report cohort, and one isolated IAS canary. It did not run the full
20-report cohort. The exact per-run evidence, identity hashes, package hashes,
and typed outcomes are recorded in
[`2026-09-28-0be495a9-postrepair-finalization-measurement.json`](2026-09-28-0be495a9-postrepair-finalization-measurement.json).

| E13 measure | Before (`a7fd7aca`) | After (`0be495a9`) |
| --- | ---: | ---: |
| Derived-projection errors | 0 | 0 |
| Deterministic-dependent scope violations | 0 | 0 |
| Unsupported-evidence introductions | 0 | 0 |
| Provenance/lineage introductions | 0 | 0 |
| Removed-insight reintroductions | 1, blocked | 1, blocked |
| Candidate validations / promotions | 8 / 0 | 6 / 0 |
| Success@1 / success@3 | 0/3 / 0/3 | 0/3 / 0/3 |
| Calls / input tokens / output tokens / estimated cost | 39 / 1,021,678 / 48,875 / $0.120091 | 35 / 799,767 / 159,178 / $0.154546 |

The live E13 denominator and model output vary between runs, so these are
observations rather than causal estimates. Four retained Mobile and
DoubleVerify candidate snapshots were also replayed without a model: six
projection findings, 720 changed-path scope violations, six provenance
findings, one claim-support finding, and one number/value/unit finding were
detected in the historical rolled-back candidates.

The pinned cohort admitted all five reports. Three were eligible and all three
materialized final packages; two reports ended with typed pre-package failures.
There were zero unexplained `package_missing`, zero `package_invalid`, two
`not_publishable`, one readiness pass, and zero provider calls during
readiness. Merchant Risk Council now has a package bound to its final artifact
and source identity; readiness blocks it for three unresolved factual claims.
Deloitte remains blocked for one unsupported claim, and Emplifi passes
readiness. The cohort used 134 calls, 1,359,596 input tokens, 285,626 output
tokens, and estimated cost `$0.277995`. Publication and handoff were disabled.

The isolated IAS canary stopped at semantic validation with typed
`validation_failed` / `grounding` after bounded recovery failed to produce a
substantive schema-valid artifact. It did not reach package materialization or
readiness. It used 39 calls, 298,365 input tokens, 65,847 output tokens, and
estimated cost `$0.062604`; publication was disabled. This is an upstream
grounding failure and did not exercise finalization.

### 2026-09-28 deterministic post-repair finalization

The atomic source-patch finalizer was measured at
`a211add35acc733fa987b0ef6dbafcaca61e120e`. The unchanged three-manifest E13
corpus, the pinned five-report cohort, and one fresh IAS canary ran with
publication disabled. The full 20-report cohort was not run. Sanitized hashes,
typed outcomes, report counts, usage, and validation results are retained in
[`2026-09-28-a211add3-deterministic-finalization-measurement.json`](2026-09-28-a211add3-deterministic-finalization-measurement.json).

| E13 measure | Before (`0be495a9`) | After (`a211add3`) |
| --- | ---: | ---: |
| Derived-projection errors | 0 | 0 |
| Deterministic-dependent scope violations | 0 | 0 |
| Unsupported-evidence introductions | 0 | 0 |
| Provenance/lineage introductions | 0 | 0 |
| Removed-insight reintroductions | 1, blocked | 0 |
| Candidate validations / promotions | 6 / 0 | 2 / 2 |
| Success@1 / success@3 | 0/3 / 0/3 | 0/2 / 0/2 |
| Calls / input tokens / output tokens / estimated cost | 35 / 799,767 / 159,178 / $0.154546 | 45 / 343,217 / 193,333 / $0.125589 |

Four retained Mobile and DoubleVerify candidates were replayed offline with zero
provider calls. The current finalizer and validators found zero derived
projection errors, scope violations, and provenance findings in those
rebuilds. Their existing source-level claim-support findings remain blocking;
none of the historical candidates was promoted. The previous replay found six
projection findings and 720 scope violations in those same rolled-back
snapshots.

The fresh cohort admitted all five sources. DoubleVerify was the only report
eligible for a final package, and its package was bound to the exact report,
final artifact, evidence, source, validator, configuration, policy, and
publication-projection identities. It was correctly blocked as
`not_publishable` for 22 unresolved factual claims and zero unsupported claims.
The cohort recorded zero unexplained `package_missing`, zero `package_invalid`,
zero readiness passes, and zero provider calls during readiness. Four reports
ended with typed pre-package failures: Merchant Risk Council, Deloitte, and
Emplifi stopped at summary provenance coverage; StackAdapt stopped at semantic
grounding validation. Thus the current run has one eligible report and one
materialized package. The cohort used 170 calls, 1,357,743 input tokens,
402,674 output tokens, and estimated cost `$0.328751`.

The cohort exercised four repair candidates: one DoubleVerify candidate was
promoted and three StackAdapt candidates were rolled back. Candidate scope
checks passed for all four. One blocked candidate had a provenance/source-page
introduction, and another attempted to reintroduce a removed insight; neither
was promoted. No unsupported-claim introduction was recorded. Merchant Risk
Council's typed `soft_copy_claim_provenance_coverage_invalid` failure occurred
during artifact generation before final package materialization, so it is an
explicit pre-package terminal reason rather than an unexplained missing
package.

The IAS canary passed analysis validation and materialized a bound final
package, then stopped at readiness with `publish_readiness_failed` for seven
unresolved factual claims and zero unsupported claims. It used 54 calls,
369,167 input tokens, 114,509 output tokens, and estimated cost `$0.090398`.
Readiness made zero provider calls; publication remained disabled.

Focused deterministic finalization, provenance, candidate-scope, and
regeneration tests passed: 159 tests. The broader focused package/readiness/
lineage suite passed 550 tests. Contract, architecture, service-boundary,
forbidden-patching, public-report-quality, and scoped Ruff checks passed. The
documentation checker still reports 12 pre-existing invalid anchors in the
untouched `docs/quality/simplification.md`.

### 2026-09-28 retained-provenance deduplication rerun

The follow-up implementation is `f9aee1642b89439646017367f56999681f1e9348`.
It reran the unchanged three-manifest E13 corpus, the pinned five-report
cohort, and one isolated IAS canary from fresh state with publication disabled.
The full 20-report cohort was not run. Sanitized per-run counts, identity and
artifact hashes, and terminal reasons are retained in
[`2026-09-28-f9aee164-postrepair-finalization-measurement.json`](2026-09-28-f9aee164-postrepair-finalization-measurement.json).

| E13 measure | Previous (`a211add3`) | Current (`f9aee164`) |
| --- | ---: | ---: |
| Derived-projection errors in live candidate audits | 0 | 0 |
| Deterministic-dependent scope violations | 0 | 0 |
| Unsupported-claim or evidence-lineage introductions | 0 | 0 |
| Provenance/lineage introductions | 0 | 0 |
| Removed-insight reintroductions | 0 | 0 |
| Candidate validations / promotions | 2 / 2 | 2 / 2 |
| Strict success@1 / success@3 | 0/2 / 0/2 | 0/2 / 0/2 |
| Calls / input tokens / output tokens / estimated cost | 45 / 343,217 / 193,333 / $0.125589 | 46 / 366,644 / 199,619 / $0.131074 |

The four retained Mobile and DoubleVerify snapshots were replayed without a
provider. Before finalization, Mobile attempt 2 had two deterministic
projection findings and two dependent-scope violations; after finalization all
four snapshots had zero projection findings, zero scope violations, and zero
provenance-coverage failures. All four reruns were idempotent and reported 65
verified finalized paths in total. The two live E13 candidates passed mutation
scope and evidence-lineage checks and introduced no failure categories, but
their strict E13 success score remained 0/2 because residual historical
fingerprints persisted. These live results vary between runs and are
observations, not causal estimates.

The five-report run admitted all five sources. Deloitte, Emplifi, StackAdapt,
and DoubleVerify each received a final package whose artifact hash matched the
lineage `final_artifact_hash`; all four remain `not_publishable` with unresolved
claims (73 total, zero unsupported claims). Merchant Risk Council terminated
before package materialization with `validation_failed` at semantic grounding.
Thus four package-eligible reports materialized four packages, with zero
unexplained `package_missing`, zero `package_invalid`, zero readiness passes,
and zero provider calls during readiness. All five outcomes were typed; no
publication or handoff was attempted. The run used 187 calls, 1,596,576 input
tokens, 473,571 output tokens, and estimated cost `$0.384146`.

Compared with the prior pinned run at `a211add3`, package-eligible reports and
materialized packages changed from 1/1 to 4/4, while typed pre-package failures
changed from four to one. Four candidates validated in both runs; promotions
changed from one to four. The prior run recorded one provenance/lineage
introduction attempt and one removed-insight reintroduction attempt; the
current candidate audits recorded zero of each. Readiness passes remained zero
because all four current packages retain unresolved claims. Current cohort
usage was 187 calls, 1,596,576 input tokens, 473,571 output tokens, and
`$0.384146`, compared with 170 calls, 1,357,743 input tokens, 402,674 output
tokens, and `$0.328751`. Live provider outputs vary; this is an observation,
not a causal estimate.

The IAS canary passed validation and materialized a package bound to its final
artifact, then stopped at readiness with `publish_readiness_failed`: 15 factual
claims remained unresolved and none were classified unsupported. It used 47
calls, 302,277 input tokens, 101,352 output tokens, and estimated cost
`$0.076993`. Readiness made zero provider calls; publication remained disabled.
The prior IAS canary also passed validation and materialized a bound package,
then stopped at readiness with seven unresolved factual claims. It used 54
calls, 369,167 input tokens, 114,509 output tokens, and `$0.090398`. The current
run's terminal readiness result remains blocking.

The focused deterministic finalization/provenance/scope suite passed 169 tests.
Ruff, formatting, forbidden-patching, architecture-import, and diff checks
passed. The documentation checker still reports 12 invalid heading anchors
in the untouched `docs/quality/simplification.md`; it reported no missing
anchor in this measurement pack. The E13 rerun, five-report cohort, and IAS
canary commands and retained result hashes are in the linked JSON record.

### 2026-09-28 finalization verification at `b1a6a39e`

The finalizer and its regression tests were already present on `main`; this
follow-up verified them at implementation SHA
`b1a6a39e203f045487fda07967e763c12cc77825`. It reran the unchanged three E13
manifests and replayed four retained Mobile/DoubleVerify candidate snapshots
without a model. It reused the fresh five-report cohort and isolated IAS run
at the same SHA. Publication stayed disabled, and the full 20-report cohort
was not run. Sanitized identities, hashes, outcomes, and counts are retained
in [`2026-09-28-b1a6a39e-postrepair-finalization-measurement.json`](2026-09-28-b1a6a39e-postrepair-finalization-measurement.json).

| E13 measure | Previous (`f9aee164`) | Current (`b1a6a39e`) |
| --- | ---: | ---: |
| Derived-projection errors | 0 | 0 |
| Deterministic-dependent scope violations | 0 | 0 |
| Unsupported evidence introduction attempts in repair candidates | 0 | 2, both candidate-scoped |
| Provenance or evidence-lineage introductions | 0 | 0 |
| Removed-insight reintroductions | 0 | 0 |
| Candidate validations / promotions | 2 / 2 | 6 / 2 |
| Strict success@1 / success@3 | 0/2 / 0/2 | 0/3 / 0/3 |
| Calls / input tokens / output tokens / estimated cost | 46 / 366,644 / 199,619 / $0.131074 | 69 / 528,051 / 276,017 / $0.181613 |

Two source-root scope violations in A21 were rejected; they are separate from
deterministic-dependent scope. The four retained historical snapshots had two
canonical projection findings and two dependent-scope violations before
finalization, then zero of each afterward. All four repeated finalizations
were idempotent and verified 65 paths. Claim-support findings already present
in those rolled-back snapshots stayed blocking; finalization introduced no
unsupported claim/evidence lineage, provenance sentence hash, or removed
insight. The offline replay made zero provider calls.

The fresh five-report run at this SHA admitted all five reports and materialized
five final packages bound to their final artifact and readiness hashes. Three
reports passed readiness. Merchant Risk Council and StackAdapt remain blocked
by one and two unresolved factual claims respectively; neither package has an
unsupported factual claim. There were zero typed pre-package failures, zero
unexplained `package_missing`, zero `package_invalid`, and zero readiness
provider calls. Compared with the `f9aee164` run, eligible reports and packages
changed from 4/4 to 5/5, readiness passes from 0 to 3, and unresolved claims
across packages from 73 to 3. The current cohort used 169 calls, 1,409,278
input tokens, 406,635 output tokens, and estimated `$0.331802`.

The isolated IAS run materialized a bound final package, then stopped at
readiness with `publish_readiness_failed` for two unresolved factual claims and
zero unsupported claims. It used 44 calls, 277,313 input tokens, 79,181 output
tokens, and estimated `$0.066176`; readiness used zero provider calls.

The focused deterministic finalization, provenance, candidate-scope, and
regeneration suite passed 117 tests. The E13 scorecard's A21 repair-only usage
attribution was unavailable; the full-run totals above come from its isolated
cost ledger. Provider outcomes and E13 denominators vary between runs and are
reported as observations, not causal estimates.


### 2026-09-29 public grounding evidence measurement at `7494ec43`

The public soft-copy grounding fix was replayed against exactly the pinned five
reports from fresh isolated state, with publication disabled. The full
20-report cohort was not run. The run completed in 3,288.609 seconds with 184
provider calls, 1,450,921 input tokens, 448,333 output tokens, and estimated
cost `$0.356416`. All five reports received typed terminal outcomes; no terminal
report was missing. Sanitized identities, hashes, exact package lineage, and
terminal outcomes are retained in
[`2026-09-29-7494ec43-public-grounding-measurement.json`](2026-09-29-7494ec43-public-grounding-measurement.json).
The raw run remains under the ignored `tmp/` directory; its `cohort_result.json`
SHA-256 is `03fb9e76190cb43637f94afaf063bb7590b4044db102c7495c3245f7c283337e`.

| Measurement | Result |
| --- | ---: |
| Final-package eligible reports | 2 |
| Final packages materialized and bound | 2 |
| Unexplained `package_missing` | 0 |
| `package_invalid` | 0 |
| Report-level readiness `not_publishable` outcomes | 0 |
| Report-level readiness passes | 2 |
| Provider calls during readiness | 0 |
| Typed pre-package failures | 3 |
| Post-package terminal failures | 2 (`report_card_manifest_write_failed`) |
| Provider calls / input tokens / output tokens / estimated cost | 184 / 1,450,921 / 448,333 / `$0.356416` |

Deloitte and StackAdapt each materialized a final package. Package validation
identity and lineage bind the report ID, final artifact hash, source ID/MD5,
evidence-pack hash, validator versions, configuration hash, policy hash, and
semantic execution identity. The readiness record references the matching final
artifact and retained-package hashes. Both passed report-level readiness with
zero unsupported and zero unresolved factual claims. Their overall workflows
later stopped on `report_card_manifest_write_failed`; publication remained
disabled. The other typed pre-package failures were Merchant Risk Council and
DoubleVerify (`validation_failed`) and Emplifi
(`regeneration_deterministic_projection_failed`). Candidate packages for those
reports were not counted as final.

For the numeric-claim question, the 693% claim was supported in Deloitte's
summary and summary soft-copy by deterministic validation, without a semantic
validator call. The current generated LinkedIn post does not contain 693%, so
this run does not reproduce the prior LinkedIn claim discrepancy and cannot
attribute a change on that exact claim to the provenance-span fix. The existing
grounding call path was retained; no additional numeric-only model pass was
added. Thus this measurement gives no evidence that calling an LLM again for
already-supported numeric claims would improve readiness. The usage ledger had
zero readiness-stage provider events.

### 2026-09-30 five-report readiness after summary safe-removal fix

The safe-removal merge failure reproduced in Emplifi was fixed at
`427af8fb3810e2ece49d90b254dfaee2a93c95ee`. A removal planned against a summary
claim-map row had previously been applied through a stale numeric index after
an earlier row was deleted, writing `None` into the promoted row and causing a
`schema_type_mismatch`. The planner now declares the selected item and the
merge removes that exact target from the promoted baseline. Ambiguous alignment
still fails closed.

The exact pinned five-report manifest was run from fresh isolated state through
normal report processing with publication disabled. The full 20-report cohort
was not run. Sanitized package identities, lineage checks, result hashes,
before/after measurements, and the IAS canary are retained in
[`2026-09-30-427af8fb-safe-removal-readiness-measurement.json`](2026-09-30-427af8fb-safe-removal-readiness-measurement.json).

| Measurement | Before (`b6636fdf`) | After (`427af8fb`) |
| --- | ---: | ---: |
| Eligible final reports | 4 | 5 |
| Final packages materialized and bound | 4 | 5 |
| Readiness passes | 4 | 5 |
| Typed pre-package failures | 1 (`schema_type_mismatch`) | 0 |
| Unexplained `package_missing` | 0 | 0 |
| `package_invalid` | 0 | 0 |
| `not_publishable` | 0 | 0 |
| Provider calls / input tokens / output tokens / estimated cost | 170 / 1,444,779 / 409,196 / `$0.338271` | 159 / 1,375,923 / 347,519 / `$0.305623` |

Every final package passes the retained report, artifact, publication
projection, source ID/MD5, evidence-pack, validator, configuration, policy,
and semantic-execution identity checks. All five have zero unsupported and
zero unresolved factual claims. Merchant Risk Council now reproduces the
previous source-backed-value/materialization scenario with a current final
package bound to its exact canonical artifact; readiness passes. The cohort
usage ledger contains zero readiness provider calls. An isolated IAS canary
also materialized a bound package and passed readiness, with zero readiness
provider calls.

All five workflows ended in `awaiting_review`; no report was published. The
unchanged E13 repair corpus remains a separate, non-passing benchmark: the
latest replay has one candidate promotion but strict success remains 0/3. Its
introductions stayed blocking and were rolled back; see the [E13 replay
measurement](2026-09-30-427af8fb-e13-replay-measurement.json). This does not
change the five current reports' readiness results.
