# Remaining Four Finalization Regression — 2026-10-03

## Scope

This measurement covers only the same four selected frozen-cohort reports:

| Publisher | Report ID |
| --- | --- |
| KPMG | `cohort-2acb4a56e14add5d7717` |
| DHL eCommerce | `cohort-9b97626fc83c086961a7` |
| Reuters Institute | `cohort-4b763ae2286ca69fe8ac` |
| Robeco | `cohort-5ceb3b4498de7288ce5a` |

The full 20-report cohort was not run. Both runs used fresh isolated report state, the same frozen manifest, and publication disabled. The raw runner results were projected through `scripts/quality/export_reliability_run_evidence.py`; the sanitized exports are in [before](before/) and [after](after/). [measurement.json](measurement.json) retains the exact revisions, per-report outcomes, usage, costs, and durations without local artifact paths or source content.

## Defect and correction

On revision `e462c285`, KPMG's safe summary-claim removal was rolled back with `regeneration_removed_summary_claim_reintroduced`. The removed row was idless. After its deletion, the next row shifted into array index 0 and reused the validator's positional fallback identity `claim_1`, even though it was a different claim. The retained-package readiness lineage mismatch affecting the other three reports had already been corrected by `e462c285`; those three passed readiness in the before run.

Revision `9466f4c0` keeps the planned mutation bound to its exact original array path, but tracks an idless removed claim by normalized claim text when checking for reintroduction. A shifted sibling no longer aliases the removed claim. The same idless claim remains blocking if it appears at another index; explicit identities remain checked by ID. Tests cover both behaviors.

## Before and after

| Measure | Before (`e462c285`) | After (`9466f4c0`) |
| --- | ---: | ---: |
| Reports admitted | 4/4 | 4/4 |
| Validation passes | 3/4 | 4/4 |
| Publication-readiness passes | 3/4 | 4/4 |
| Awaiting human review | 3 | 4 |
| Typed terminal outcomes | 4/4 | 4/4 |
| Unexplained terminal failures | 0 | 0 |
| Provider calls, whole workflow | 142 | 134 |
| Input tokens | 1,456,857 | 1,374,991 |
| Output tokens | 295,812 | 263,131 |
| Estimated cost | $0.280942 | $0.262450 |
| Duration | 2,373.748 s | 2,084.567 s |
| Provider calls during readiness | 0 | 0 |

The KPMG terminal failure was removed. DHL eCommerce, Reuters Institute, and Robeco passed readiness in both runs; all four passed in the final run. Every final report is in `awaiting_review`, which means the publication gate passed and human review remains pending. Nothing was published.

The final per-report production measurements are:

| Publisher | Readiness | Calls | Input tokens | Output tokens | Cost | Duration |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| KPMG | Pass | 37 | 345,745 | 62,462 | $0.064872 | 448.855 s |
| DHL eCommerce | Pass | 40 | 316,848 | 77,307 | $0.066691 | 696.189 s |
| Reuters Institute | Pass | 30 | 341,935 | 57,613 | $0.062068 | 431.527 s |
| Robeco | Pass | 27 | 370,463 | 65,749 | $0.068819 | 507.996 s |

The zero-call result is from the retained `workflow_job_attempts.provider_usage_json` values: all four final `publication_readiness.v1` attempts contain `{}`. On the before run, KPMG failed before readiness; the other three readiness attempts also contain `{}`.

The outcome exporter currently labels its `audit_findings.json` view `failed_reliability_targets` and records that publication was not performed. That exporter label is separate from the authoritative per-report `publication_readiness` outcomes above; the final cohort result records four readiness passes.

## Verification

Focused deterministic candidate, analysis-planner, regeneration, and atomic-scope suites passed:

```text
pytest -q tests/test_regeneration_candidate.py tests/test_report_analysis_generator.py tests/test_report_regeneration_generator.py tests/test_atomic_regeneration_contract.py
233 passed
```

The focused Ruff check, contract schema snapshot gate, documentation checks, and `git diff --check` also passed. The exact production run results are summarized in [measurement.json](measurement.json); the runner used the existing frozen-cohort manifest and only the four IDs listed above.
