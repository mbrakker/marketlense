# Frozen cohort batch 3 — post-repair finalization

This measurement used exactly the next five reports in the frozen 20-report
corpus: Algolia, Bain & Company, Bigcommerce, Criteo, and DHL eCommerce. The
source manifest is retained in [`frozen_cohort.json`](frozen_cohort.json).
The full 20-report cohort was not run.

The latest follow-up for this same manifest is retained in
[`report-agnostic-prompt-repair-20261001/`](report-agnostic-prompt-repair-20261001/README.md).
At implementation `eae746de7a6595b6dbddfcc69d7ad9ca8b26d2b6`, it restored
both validation and readiness to 5/5 after the immediate predecessor at
`9db7f2e19b697517485926c0611e1126e5382343` regressed to 2/5 readiness passes.
The follow-up retains new final-package lineage hashes and current usage
metrics; the original package-materialization result below remains a separate
historical measurement.

The runner used fresh isolated state and the normal production report workflow.
Publication was disabled; every report stopped at the human review boundary.
The full workflow database, generated report text, prompts, and provider
responses remain under the ignored `tmp/` run directory. This pack retains the
manifest, typed cohort outcomes, hashes, package-lineage checks, and scalar
usage metrics only.

## Original package-materialization result

The following two runs bracket the original package-materialization fix;
later report-copy changes are recorded in the follow-up linked above. The
first run passed readiness for four reports; Criteo ended with
`validation_failed`. In the fresh run at `11ca2ce3e73cfc56741a140da52eba82b1882068`,
all five passed validation and report-level publication readiness. Each has a
current final `retained_claim_validation` package referenced by its readiness
record and bound to its final artifact and lineage identities.

| Report | Validation | Readiness | Final package | Terminal state |
| --- | --- | --- | --- | --- |
| Algolia | pass | pass | materialized and bound | `awaiting_review` |
| Bain & Company | pass | pass | materialized and bound | `awaiting_review` |
| Bigcommerce | pass | pass | materialized and bound | `awaiting_review` |
| Criteo | pass | pass | materialized and bound | `awaiting_review` |
| DHL eCommerce | pass | pass | materialized and bound | `awaiting_review` |

| Package/readiness measure | Result |
| --- | ---: |
| Eligible final reports | 5/5 |
| Final packages materialized and lineage-bound | 5/5 |
| Unexplained `package_missing` | 0 |
| `package_invalid` | 0 |
| `not_publishable` | 0 |
| Report-level readiness passes | 5/5 |
| Unsupported / unresolved factual claims in final packages | 0 / 0 |
| Public editorial-quality passes / hard failures / issues / waivers | 5 / 0 / 0 / 0 |
| Provider calls during readiness | 0 |
| Publication attempts | 0 |
| Operator interventions | 0 |

Each package's `lineage.final_artifact_hash` equals the readiness record's
`artifact_hashes.artifacts`, and its `package_hash` equals
`artifact_hashes.retained_claim_validation`. The retained identity checks also
match report ID, source ID and source checksum, evidence-pack identity,
publication projection, claim and grounding validators, configuration,
policy, and semantic execution identity. Full SHA-256 values and the per-report
check results are in
[`final_package_lineage.json`](final_package_lineage.json). The readiness
record is report-scoped; no candidate package is counted as final.

The report-level readiness outcome is `pass`; the package status and terminal
workflow state are `awaiting_review`. No report was published.

## Before and after

| Measure | Before | After | Change |
| --- | ---: | ---: | ---: |
| Readiness passes | 4/5 | 5/5 | +1 report |
| Typed report failures | 1 (`validation_failed`) | 0 | -1 |
| Provider calls | 169 | 198 | +29 |
| Input tokens | 1,425,979 | 1,445,780 | +19,801 |
| Output tokens | 380,710 | 446,850 | +66,140 |
| Estimated cost | $0.325997 | $0.356166 | +$0.030169 |
| Duration | 3,044.011 s | 3,305.977 s | +261.966 s |

The before and after provider usage and duration are cohort totals; the runner
does not attribute them to individual reports. These are two stochastic
production runs, not a controlled causal estimate. In particular, Criteo
passed in the after run, but its run did not require a regeneration candidate;
the direct repair-path regression is therefore evidenced by the retained
fixture replay and focused tests, not inferred from that run's pass alone.

The residual failure came from a safe-removal path that removed an entire
insight after bounded implication rewrites failed, then introduced a different
fallback claim. A candidate also recomputed an already accepted Summary
abstention from unchanged blank Summary fields and converted it to a blocking
regenerate state. The report-agnostic fix now clears only the exact unsupported
`so_what` or `now_what` implication when all target issues are grounding issues
on those leaves, preserving factual insight text and evidence bindings. During
finalization, it retains a validated prior Summary `generated` or `abstained`
status when the Summary root is byte-identical. Changed Summary input still
recomputes normally.

The retained Criteo production fixture replay in
[`retained_criteo_fixture_replay.json`](retained_criteo_fixture_replay.json)
verified that the exact failed
`now_what` implication is cleared while the insight text, evidence identity,
evidence spans, and sibling `so_what` remain unchanged. It made zero provider
calls. The existing insight and evidence contract remains intact; no
publisher-specific allowlist or readiness relaxation was added.

## Run identity and invocation

- Implementation SHA: `11ca2ce3e73cfc56741a140da52eba82b1882068`
- Run identity: `frozen-reliability-sktxs0y6` / `ias-first-attempt-75jfcz6s`
- Started and completed: 2026-10-01, approximately 09:02–09:57 UTC
- Manifest SHA-256: `fccce9143558f20b3f277f03e79c1b3cd78699fb3237f0336e1364a4cc1cda6d`
- Before result SHA-256: `26b1412dc2ecb7f81fb383d7a5998fdc934cd008d9d8ecb318f72b97b83aec2b`
- After result SHA-256: `a2498b3c11c73a4d3c6f50a2cfd1336dcac1776b236b03deae39caf9bc488ff5`
- Input / output tokens: `1,445,780 / 446,850`
- Estimated provider cost: `$0.356166`
- Duration: `3,305.977 seconds`
- Provider calls in complete processing workflow: `198`
- Provider calls during readiness: `0`
- Publication: disabled; no publication attempt

The exact production command was:

```powershell
python scripts/quality/run_frozen_reliability_cohort.py `
  --sources-manifest tmp/frozen20-next5-batch3-20261001/frozen-reliability-ueq7j3cu/frozen_cohort.json `
  --runs-root tmp/frozen20-next5-batch3-finalization-fix-20261001 `
  --max-duration 7200
```

The source manifest SHA-256 is identical for the before and after runs. The
cohort runner uses a new isolated state directory for each run.

## Focused verification

The focused deterministic projection, provenance, scope, package, and
readiness selection passed **286 tests**:

```text
python -m pytest -q tests/test_report_regeneration_generator.py tests/test_regeneration_finalization.py tests/test_regeneration_candidate.py tests/test_report_analysis_orchestrator_decomposition.py tests/test_artifact_normalization.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_render_service_public_advisory.py tests/test_render_service_public_prose.py
286 passed
```

`python scripts/ci/check_public_report_quality.py` and `git diff --check`
passed. Scoped Ruff diagnostics were unchanged from the existing baseline; the
repository-wide format check still reports pre-existing files that would be
reformatted. No validator or readiness rule was weakened.
