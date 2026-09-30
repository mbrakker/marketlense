# Frozen next-five readiness regression — 2026-10-01

This measurement reran only the pinned next-five subset of the frozen 20-report
corpus: Capgemini Research Institute, Activate, KPMG, Reuters Institute, and
Adjust. It used fresh isolated state and the production validation workflow.
Publication was disabled; each report stopped in `awaiting_review`. The full
20-report cohort was not run.

The exact source manifest and production-derived results are retained in
[`frozen_cohort.json`](frozen_cohort.json),
[`before_cohort_result.json`](before_cohort_result.json), and
[`cohort_result.json`](cohort_result.json). The safe outcome projection is in
[`evidence-export/`](evidence-export/). The source manifest SHA-256 is
`744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`; the
before-result SHA-256 is
`b6802e8519ee972548c750bfd323309385600acde1e5ab01953ccb567a5802fb`, and the
after-result SHA-256 is
`043bfd0f86dec3880a7c5c9850958ded6d832a49429c8e1043b8ac8f133d6839`.

## Outcome

All five reports were admitted, validated, and passed publication readiness on
their first workflow attempt. They reached the human-review boundary; none was
published.

| Report | Validation | Publication readiness | Terminal state |
| --- | --- | --- | --- |
| Capgemini Research Institute | pass | pass | `awaiting_review` |
| Activate | pass | pass | `awaiting_review` |
| KPMG | pass | pass | `awaiting_review` |
| Reuters Institute | pass | pass | `awaiting_review` |
| Adjust | pass | pass | `awaiting_review` |

| Measure | Result |
| --- | ---: |
| Admitted | 5/5 |
| First-attempt readiness passes | 5/5 |
| Typed report failures | 0 |
| Missing terminal outcomes | 0 |
| Operator interventions | 0 |
| Report workflow failure rate | 0% |
| Provider calls during readiness | 0 |
| Publication attempts | 0 |

The readiness value is the report-level result. `awaiting_review` is the final
state because this validation run deliberately did not publish.

## Before and after

The preceding fresh-state run used the same five-source manifest at
`365c342ba3ffe2cb3b2c8a90fb71938ae9738cf6`. It passed 3/5 reports; Capgemini
failed semantic grounding after copy joined a source recommendation with a
separate consumer preference, and Adjust failed deterministic finalization
after a compact `2024–2025` timeframe was misread. The current run used
`469c13c15d0d654f60c04a84bb97bf7ee44d1de0` and passed 5/5.

| Measure | Before | After |
| --- | ---: | ---: |
| Readiness passes | 3/5 | 5/5 |
| Provider calls | 193 | 222 |
| Input tokens | 1,804,228 | 2,129,080 |
| Output tokens | 393,169 | 492,778 |
| Estimated cost | $0.366703 | $0.435683 |
| Duration | 2,809.573 s | 3,714.445 s |

These are observations from two stochastic production runs, not a controlled
causal estimate. Batch usage and duration are retained at cohort scope; the
runner does not attribute them to individual reports. The final run recorded
bounded automatic repair and no operator intervention.

The source changes address the two reproduced failure mechanisms. The shared
editorial constitution now keeps source recommendations attributed and
prevents combining them with separate evidence or preferences. Protected-fact
timeframe parsing recognizes compact hyphen and en-dash year ranges. Candidate
finalization also rebuilds canonical soft-copy provenance when validated
candidate provenance changed, even when the public text itself did not change.
Readiness and grounding rules remain unchanged.

## Run identity and workflow notes

- Implementation: `469c13c15d0d654f60c04a84bb97bf7ee44d1de0`
- Run identity: `frozen-reliability-xxcdkw0r` / `ias-first-attempt-7z7shs6j`
- Started: 2026-09-30 21:21 UTC; completed: 2026-09-30 22:23 UTC
- Provider calls: 222
- Input/output tokens: 2,129,080 / 492,778
- Estimated provider cost: $0.435683
- Duration: 3,714.445 seconds
- Readiness jobs: 5 succeeded; no provider call was made during readiness
- Publication: disabled; no report was published

The isolated workflow database also recorded auxiliary cross-report and signal
jobs outside the report-readiness denominator: one
`cross_report_analysis_disabled`, two `cross_report_no_projected_sources`, and
two `signal_grounding_insufficient` dead letters, with 14 signal-generation
jobs still pending at cohort completion. These did not change the five report
readiness outcomes. They remain auxiliary workflow follow-up, not publication
readiness failures.

## Verification

Focused tests passed on the implementation commit:

```text
python -m pytest -q tests/test_grounding_cohort_false_positive_regressions.py tests/contracts/test_protected_facts.py tests/test_grounding_protected_facts.py
106 passed

python -m pytest -q tests/test_regeneration_finalization.py tests/test_report_regeneration_generator.py
84 passed

python -m pytest -q tests/test_prompt_service.py
21 passed
```

The prompt fixture regression gate passed with 98,594 tokens and estimated
cost `$0.022585`, matching the regenerated baseline. The added editorial rule
accounts for 340 additional fixture tokens and `$0.000030`; expected OCR calls
(1) and browser attempts (7) did not change. Ruff and `git diff --check` passed
for the changed code and tests.

The regression command used only the five pinned sources:

```powershell
python scripts/quality/run_frozen_reliability_cohort.py `
  --sources-manifest tmp/frozen20-next5-20260930/frozen_next_five.json `
  --runs-root tmp/frozen20-next5-systemic-fix-20260930
```

The ignored `tmp/` directory retains the isolated SQLite state and generated
artifacts for local audit. The committed result and manifest preserve the
cohort outcome and frozen source identities without retaining prompts or model
responses.
