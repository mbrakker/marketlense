# Five-report grounding regression — 2026-10-02

This record covers only the pinned five-report subset in
[`frozen_cohort.json`](frozen_cohort.json): Capgemini Research Institute,
DoubleVerify, Adjust, Bain & Company, and Bigcommerce. The full 20-report cohort
was not run. Both measurements used the canonical production reliability
workflow with fresh isolated state and publication disabled; reports stopped
at `awaiting_review`.

The before and after runs used identical frozen source identities. The manifest
SHA-256 is
`e6cd2e7dcfb886ffd142cf0056ba64685e17fcafe03254869a021f48d88b83a5`. Their
retained per-report outcomes and performance counters are in
[`measurement.json`](measurement.json). The before run used
`3f01562e0fdb162bb58df84280d9e54a5f76c9a9`; the after run used the grounding
fix at `cb6b9de5878601e9b1acb5e6dc399abdf7e63e4d`.

## Outcomes

| Report | Before validation/readiness | After validation/readiness | After terminal state |
| --- | --- | --- | --- |
| Capgemini Research Institute | pass / pass | pass / pass | `awaiting_review` |
| DoubleVerify | fail / fail | pass / pass | `awaiting_review` |
| Adjust | pass / pass | pass / pass | `awaiting_review` |
| Bain & Company | pass / pass | pass / pass | `awaiting_review` |
| Bigcommerce | pass / pass | pass / pass | `awaiting_review` |

DoubleVerify was the only before-run failure. It terminated as
`no_material_repair_available`: grounding received the isolated value `8.0%`
without its APAC region and Q1 2026 period, although the retained direct finding
on page 3 contained the scoped rate. The fix now sends the canonical composite
key-figure claim, including its scope, cohort/denominator, geography, timeframe,
and status, and binds grounding to existing direct finding evidence when
available. Public cards preserve cohort and denominator context. The grounding
validator version change also prevents reuse of semantic results from the
previous contract. Readiness rules were not relaxed.

## Performance comparison

| Measure | Before | After | Change |
| --- | ---: | ---: | ---: |
| Readiness passes | 4/5 | 5/5 | +1 report |
| Typed report failures | 1 | 0 | -1 |
| Provider calls during readiness | 0 | 0 | unchanged |
| Provider calls across report workflows | 171 | 155 | -16 |
| Input tokens | 1,517,933 | 1,373,256 | -144,677 |
| Output tokens | 372,793 | 295,149 | -77,644 |
| Estimated provider cost | $0.329355 | $0.280567 | -$0.048788 |
| Sum of report durations | 2,936.034 s | 2,275.525 s | -660.509 s |
| Operator interventions | 0 | 0 | unchanged |
| Publication jobs | 0 | 0 | unchanged |

These are results from two stochastic production runs, not a controlled causal
estimate. The five final readiness results and zero provider calls during
readiness were checked against each report's readiness artifact and isolated
usage database. No publication job was present in either run. Report generation
itself used 155 provider calls in the after run.

## Verification

The implementation's focused regression suite passed (268 tests), including
retained-claim grounding, public rendering, claim validation, grounding
outcomes, protected facts, editorial interpretation, readiness, and report
rendering. The public report quality gate, formatting, forbidden-patching,
architecture-import, Ruff, and `git diff --check` gates passed. The
documentation checker still reports 12 stale anchors in the pre-existing
`simplification.md`; that file was not changed by this work.

The production cohort was run with the frozen reliability runner using the
checked-in five-report manifest and a 1,512-second per-report maximum. Its
isolated run directory is retained outside the repository under
`C:\mlv\target-five-keyfigure-cb6b9de5-20261002\frozen-reliability-pjkdz5v_`.
The committed `measurement.json` keeps the source identities, pass/fail result,
usage, timing, manifest hash, implementation revisions, and bounded
publication evidence without retaining prompts or raw provider responses.
