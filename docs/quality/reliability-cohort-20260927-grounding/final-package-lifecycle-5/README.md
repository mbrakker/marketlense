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
