# Frozen Five-Report Autonomous MVP Comparison — 2026-10-09

**Recommendation: NO-GO for autonomous publication.** The matching first-attempt batch completed 4/5 report paths; one report failed before render. Readiness passed for the four rendered reports, and the failure passed on a separate diagnostic rerun. Paired output review found lower lead specificity in some current outputs and meaningful variation between runs. The autonomous-MVP preflight is blocked, and no WordPress sandbox was available for create, authenticated readback, or replay evidence.

No production publication was attempted. All cohort runs used fresh isolated state and disabled the WordPress publish queue. The five reports reached terminal outcomes without operator intervention; no queue retry occurred.

## Decision summary

- The cohort identity and source checksums match the retained baseline exactly.
- The crop-boundary fix in source commit `4161d8e5fc4c537f6397c1e51f9f06cd6dda73f7` resolved the four initial crop-refinement failures: rerunning only those four reports produced 4/4 passes. A separate same-SHA, per-report run also completed 5/5.
- In the comparable shared-queue batch on that SHA, Capgemini failed with `card_tldr_compact_invalid`; Activate, KPMG, Reuters Institute, and Adjust reached `awaiting_review` with readiness pass. Capgemini passed a fresh isolated diagnostic, but that does not erase the shared-batch first-attempt failure.
- Deterministic source-fidelity checks passed for every rendered report: zero retained unsupported or unresolved claims, zero hard editorial failures, and all 16 readiness rules passed. Those checks do not measure whether a lead finding is sufficiently specific or useful.
- A paired assistant review of actual HTML found a material lead-quality regression for Activate. A second complete five-report run found lower lead specificity in four reports. Different current runs selected materially different leads for Reuters and Adjust, so this is a quality-variance concern rather than a confirmed deterministic code defect.
- Current primary-batch wall time increased 8.3%, throughput fell 7.6%, and estimated cost fell 1.6%. The current supervisor capacity changed from 5 to 3, and measured queue wait rose substantially, so the timing comparison is not a controlled configuration match.
- Local and bounded live `autonomous_mvp` preflights are blocked. WordPress publish/readback/replay was not run because no sandbox URL was supplied and the only configured URL may target production.

## Cohort identity and retained evidence

| Publisher | Stable report ID | Frozen PDF MD5 |
| --- | --- | --- |
| Capgemini Research Institute | `cohort-81af3890cd84ece81ef1` | `81af3890cd84ece81ef16e1aabda8027` |
| Activate | `cohort-cbb6e7df67412186b8bc` | `cbb6e7df67412186b8bc094a424ac890` |
| KPMG | `cohort-2acb4a56e14add5d7717` | `2acb4a56e14add5d7717f34c378f9091` |
| Reuters Institute | `cohort-4b763ae2286ca69fe8ac` | `4b763ae2286ca69fe8acb63b17508dfb` |
| Adjust | `cohort-b638414df0b1fccea1cd` | `b638414df0b1fccea1cd8a93eaf8f5aa` |

The frozen manifest is `docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json`, SHA-256 `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`. The runner verified all five source MD5s before submission. The historical baseline is preserved at commit `0ec3cdff841e16df7044f6645fe8379a464f41ca`, with its accepted record at `docs/quality/frozen-five-systematic-fixes-baseline-20261005.json`. Its original Temp run directory and HTML outputs were read without modification.

The primary current batch summary is retained at `out/frozen-five-comparable-batch-20261009.stdout.jsonl`; its isolated run is under `tmp/p5b/ias-first-attempt-c9et0s5k/`. The full current per-report-isolated cohort is under `tmp/p5f/`; the Capgemini diagnostic is under `tmp/p5diag/` and its redacted result is at `out/frozen-five-capgemini-diagnostic-20261009.stdout.jsonl`. Redacted preflight records are under `out/`. Render copies and screenshots used for visual comparison are under ignored `tmp/p5evalview-20261009/`. Raw model responses, prompts, source extracts, and credentials are not included in this report or commit.

## Configuration and comparability

| Item | Historical baseline | Current primary batch |
| --- | --- | --- |
| Source revision | `0ec3cdff841e16df7044f6645fe8379a464f41ca` | `4161d8e5fc4c537f6397c1e51f9f06cd6dda73f7` |
| Base `app.yaml` SHA-256 | `462477accb62aeef7f0a40dbabdc86bf22c1146315662bbb3f71da81d1d642c1` | `b90a2242728d985b5695e7faae0e0320714659c41ee9ded9c4a463227da9558d` |
| Isolated runner `app.yaml` SHA-256 | `5359dc341c8027f0a0e60c5379258bd9ddac36fe99344f72dd6f13e0f0e3d0f3` | `c0c9fd9607cad477ce2bfb9b4b09d5e25e9fbc81454fcf4c0e5dfe99cafa99e2` |
| Model/provider | OpenAI `gpt-6-luna` | OpenAI `gpt-6-luna` |
| Model policy hash | `b7743c06f02b644720c2541b317e4adac7093c5f6c522f9078080becd0cdc3e7` | same |
| Supervisor max parallel workers | 5 | 3 |
| WordPress publish queue | Disabled | Disabled |

The static source diff from baseline changes one prompt resource: `src/prompts/rank_candidates/crop_refine/user.yaml`. Report-generation prompt files and the model execution policy were unchanged. The current base config explicitly keeps autonomous publication disabled; `src/config/app.autonomous_mvp.yaml` is a separate opt-in overlay with automatic approval enabled, SHA-256 `290ed79fa086f6e10071fbfb834e97e3b610a9f116ca995a5fe638234fc45d71`. The frozen cohort runner used the base config, not the autonomous overlay, and ended eligible outputs in `awaiting_review`.

Each run used fresh isolated application state; no historical analysis or editorial output was reused. Provider-side cached input tokens were present in both ledgers (117,267 baseline; 168,848 current), so this was a fresh application-cache run, not a provider-cache-free run. The policy hash and model were constant. Rendered prompt hashes also vary with each run's dynamic evidence and optional repair path; they are not treated as static prompt-version changes. Provider request timing was unavailable.

## Comparable shared-queue performance and reliability

Per-report elapsed time is measured from the first `source_ingest` start to the last core-stage completion. It includes queue wait and overlaps across reports. The Capgemini current duration ends at its typed failure and is not a successful-processing timing.

| Report | Processing outcome and readiness, baseline → current | Core elapsed, baseline → current | Provider calls, baseline → current | Input/output tokens, baseline → current | Estimated cost USD, baseline → current |
| --- | --- | ---: | ---: | ---: | ---: |
| Capgemini | pass/pass → **failed / fail** (`card_tldr_compact_invalid`) | 1,178s → 135s, partial; not comparable | 39 → 25, partial | 364,300/79,343 → 210,604/39,177, partial | 0.089357 → 0.053053, partial |
| Activate | pass/pass → awaiting review/pass | 760s → 1,180s (**+55.3%**) | 49 → 55 (**+12.2%**) | 380,564/68,154 → 308,558/82,035 (in −18.9%, out +20.4%) | 0.088718 → 0.078584 (**−11.4%**) |
| KPMG | pass/pass → awaiting review/pass | 748s → 504s (**−32.6%**) | 37 → 35 (**−5.4%**) | 337,873/63,750 → 274,212/63,714 (in −18.8%, out −0.1%) | 0.074580 → 0.088196 (**+18.3%**) |
| Reuters Institute | pass/pass → awaiting review/pass | 1,183s → 669s (**−43.4%**) | 53 → 44 (**−17.0%**) | 478,390/124,566 → 480,302/96,862 (in +0.4%, out −22.2%) | 0.116891 → 0.107485 (**−8.0%**) |
| Adjust | pass/pass → awaiting review/pass | 675s → 1,286s (**+90.5%**) | 37 → 38 (**+2.7%**) | 318,084/63,284 → 442,795/94,938 (in +39.2%, out +50.0%) | 0.072372 → 0.107505 (**+48.5%**) |

| Cohort metric | Baseline | Current primary batch | Delta |
| --- | ---: | ---: | ---: |
| Reports reaching terminal state | 5/5 | 5/5 | Same |
| Successful report paths | 5/5 (100%) | 4/5 (80%) | −1 report; 20% failure rate |
| Readiness pass | 5/5 | 4/5 | −1 report |
| Wall-clock to all terminal | 1,201.190s | 1,300.681s | +99.491s (+8.3%) |
| Effective throughput | 14.985 reports/hour | 13.839 reports/hour | −7.6% |
| Provider calls | 215 | 197 | −18 (−8.4%) |
| Input/output tokens | 1,879,211 / 399,097 | 1,716,471 / 376,726 | −8.7% / −5.6% |
| Estimated total cost | $0.441918 | $0.434823 | −$0.007095 (−1.6%) |
| File Search calls | 26 | 36 | +10 (+38.5%) |
| Automatic repairs | 6 | 9 | +3 (+50%) |
| Structured-output repair calls | 1 | 0 | −1 |
| Queue retries / operator interventions / publication writes | 0 / 0 / 0 | 0 / 0 / 0 | Same |

Stage totals are cumulative worker execution and queue-wait seconds, not wall time; totals overlap across concurrent jobs.

| Stage | Baseline execution / wait (samples) | Current execution / wait (samples) |
| --- | ---: | ---: |
| Source ingest | 20.1s / 19s (5) | 23.3s / 27s (5) |
| Report selection | 1,037.9s / 10s (5) | 788.8s / 271s (5) |
| Report analysis | 3,066.2s / 9s (5) | 2,262.9s / 899s (5) |
| Report render | 21.8s / 0s (5) | 152.6s / 2s (4) |
| Publication readiness | 2.3s / 374s (5) | 5.7s / 7s (4) |

Current report-analysis jobs reached at most three concurrent workers, versus five at baseline. Queue controls still allowed five workers per queue, but the supervisor cap was three. Current report-selection and report-analysis queue wait totaled 1,170 seconds, versus 19 seconds at baseline. External provider latency was not separately measured, and the concurrency change prevents attributing the wall-time result to an implementation speed change.

The same-SHA full per-report-isolated run completed all five reports with readiness pass, zero queue retries, zero interventions, 200 calls, 1,509,808 input tokens, 380,925 output tokens, estimated cost $0.402331, and 2,115.447 seconds summed across five independent executions. This sum is not a batch wall-time comparison. The separate Capgemini diagnostic passed in 411.317 seconds, with 32 calls, 267,068 input tokens, 59,730 output tokens, and estimated cost $0.068152.

## Paired factual, grounding, editorial, and visual review

Baseline and current retained outputs were reviewed side by side against the same source identities. Deterministic validation is reported separately from editorial judgement; a validator-version or readiness pass is not treated as proof of editorial improvement.

The editorial screen uses the repository's four dimensions: factual accuracy, insight value, naturalness, and executive usefulness. The displayed composite below is the mean of the three editorial dimensions (insight value, naturalness, executive usefulness); factual accuracy and grounding remain tied to the deterministic evidence outcomes below. These are single-reviewer, assistant-assisted ratings of the rendered lead summary/core signal, not formal independent human scores. The repository's 30-report blinded human procedure was not run, and no historical human scorecards were retained. Treat the ratings as a paired warning signal, not release-acceptance evidence.

| Report | Baseline → current isolated-run editorial composite | Primary shared-batch rendered lead | Review finding |
| --- | ---: | ---: | --- |
| Capgemini | 4.7 → 2.7 | No current HTML; failed before render | The isolated output replaced the baseline's quantified switching-intent lead with a broad statement. The primary failure remains the cohort outcome. |
| Activate | 4.7 → 2.7 | 2.7 | The primary output leads with a description of the podcasting section rather than a quantified commercial finding. This is a clear usefulness/specificity regression. |
| KPMG | 4.0 → 3.3 | 3.3 | The current lead changes from a strategic carve-out insight to 2026 pipeline expectations; the primary summary retains cost and return uncertainty, but the signal is less distinctive. |
| Reuters Institute | 4.7 → 2.7 | 4.7 | The primary output has a specific AI-search/referral-risk lead; the isolated output generalized to publishers' revenue sources. The difference across current runs is material. |
| Adjust | 4.7 → 3.3 | 4.7 | The primary output has a specific, qualified 2030 forecast; the isolated output generalized to cross-platform measurement. The difference across current runs is material. |

For the four HTML reports in the primary shared batch, the paired editorial composite averaged 4.5 baseline versus 3.9 current (−0.7 points). The complete secondary isolated cohort averaged 4.6 baseline versus 2.9 current (−1.6 points). These different results expose output variability; the isolated rerun is not used to overwrite the primary failure or selectively replace primary HTML.

| Deterministic quality evidence | Baseline | Primary current | Full isolated current |
| --- | ---: | ---: | ---: |
| Validation and readiness pass | 5/5 | 4/5; Capgemini failed before render | 5/5 |
| Unsupported / unresolved retained claims | 0 / 0 | 0 / 0 among the four ready outputs | 0 / 0 |
| `public_editorial_quality_after` hard failures | 0 across rendered reports | 0 across the four ready outputs | 0 across all five |
| Readiness rules passed per ready report | 16/16 | 16/16 | 16/16 |

All generated reports that reached final readiness passed the source-fidelity gates. No false statement was confirmed in the lead surfaces reviewed. The quality artifact's issue list was empty, but its measurements do not score whether a lead is commercially distinctive; rendered report-quality score fields were `N/A`. Capgemini's primary batch failure had no final HTML and cannot receive a primary editorial score.

Playwright opened the retained baseline and current HTML in a loopback-only viewer. Every checked page had one preview-image reference, and each referenced asset was present in its retained output directory; a representative lazy-loaded preview decoded successfully at 2,560 px wide. No horizontal overflow appeared in the baseline five, current primary four, or current isolated five. The HTML outputs contained no source chart-card/SVG rendering in these runs. A key-figure module appeared for Capgemini and Activate in the baseline, Adjust in the primary current batch, and Capgemini in the isolated current run. This selection varied by run; no chart-card tuple was available for a visual fidelity check.

The review supports a **possible editorial-quality regression and a confirmed run-to-run variability concern**, not a confirmed factual regression. Report-generation prompt files and the model policy were unchanged. The likely cause is model-output variability and changed execution topology; this is an inference, not a proven cause. No prompt tuning was applied.

## Crop regression, diagnosis, and code changes

The first post-baseline current attempt at base SHA `f8e1758cb6147935b6f0c2ec21849a35d1e112f0` failed four report-selection paths with `crop_refine_original_bbox_invalid`. The cause was PyMuPDF intersection precision rejecting valid fractional boxes, plus candidate expansion that could emit slightly out-of-page boxes.

Commit `4161d8e5fc4c537f6397c1e51f9f06cd6dda73f7` replaced the precision-sensitive equality check with direct coordinate bounds checks, clips partially visible candidate boxes to cropbox bounds, drops fully invisible candidates, and records scalar clip/drop counts. It preserves rejection of source boxes genuinely outside the page. Only the four previously failing reports were rerun first; all four passed. A complete isolated five-report run then passed 5/5. The later comparable shared batch had one different typed failure: `card_tldr_compact_invalid` in Capgemini `report_analysis`, stating that `summary.card_tldr_compact` was not a complete sentence of 1–18 words. The separate fresh Capgemini diagnostic passed on the same SHA, so this failure was not reproducible. It was not manually requeued in the original batch and no prompt change was made.

The frozen cohort PDFs have no rotated pages. The rotated-page coordinate-frame path was therefore not exercised by this cohort; the present evidence establishes the crop fix for these five sources, not rotated-page coverage generally.

Verification on source SHA `4161d8e5fc4c537f6397c1e51f9f06cd6dda73f7`:

- `python -m pytest -q tests/test_pdf_crop_service.py tests/test_pdf_figures_service` — 192 passed.
- `python -m pytest -q tests/test_autonomous_publication_approval.py tests/test_publish_queue_orchestrator.py tests/test_signal_workflow_handoff.py tests/test_signal_candidate_orchestrator.py tests/test_signal_post_orchestrator.py` — 40 passed.
- `python -m pytest -q -m integration tests/integration/test_signal_candidate_store_service.py` — 5 passed.
- `python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_render_service_public_advisory.py tests/test_render_service_public_prose.py` — 106 passed.
- `python scripts/ci/check_public_report_quality.py` — passed.
- `python scripts/ci/check_formatting.py` and `python scripts/ci/check_ruff_lint.py` — passed.
- `python scripts/ci/check_pdf_candidate_benchmark.py --output-root tmp/prompt5-frozen-five-autonomous-mvp-20261009-candidate-benchmark --output-json out/frozen-five-autonomous-mvp-20261009/pdf-candidate-benchmark.json` — passed; golden signatures unchanged.
- `python scripts/ci/check_pdf_crop_refine_benchmark.py --output-json out/frozen-five-autonomous-mvp-20261009/pdf-crop-refine-benchmark.json` — passed; golden signatures unchanged.
- Full GitHub CI for source SHA `4161d8e5fc4c537f6397c1e51f9f06cd6dda73f7` passed: [run 37892129872](https://github.com/mbrakker/marketlense/actions/runs/37892129872).

## Autonomous approval, WordPress, Signal, and Briefing

The current-SHA local `autonomous_mvp` capability preflight is **blocked** with 11 blocking checks: isolated state, Signal-store, and reports databases are missing; the isolated LLM-usage database has an incompatible schema; and the required Drive OAuth token is absent. The bounded live preflight is **blocked** with 6 checks, 5 read-only provider metadata calls, and 0 external writes. The WordPress site URL was explicitly blanked for this probe because the available configured URL may target production; WordPress capability consequently reported `publish_configuration_invalid`. The frozen runner separately admitted the exact 5/5 cohort under its isolated admission path.

The automated-publication tests passed and cover checksum-bound approval, readiness/grounding holds, changed or stale packages, override-based manual approval, and duplicate ready-report replay leaving one approval/outbox record. This is local test evidence only. The current cohort itself used the base profile and all successful reports remained `awaiting_review`; no live autonomous approval event was produced.

No approved WordPress sandbox URL or sandbox credentials were available. No WordPress create, authenticated readback, or durable-job replay was attempted. The publish queue was disabled in baseline and current runs; both recorded zero WordPress writes. A local duplicate-approval test is not evidence of zero-write replay against WordPress.

In the current isolated five-report cohort, 37 immutable Signal candidate manifests were read back through the canonical service and passed hash/contract validation; all 37 groups referenced one report and remained held with `signal_grounding_insufficient`. The primary batch had 32/32 such manifests pass readback; all were single-report holds. No Signal post was generated or published, preserving the human-review restriction. The baseline had 38 Signal-generation dead letters (`signal_grounding_insufficient`) and 2 pending Signal-generation jobs.

Briefing opportunity handoffs succeeded for the rendered current reports. The current batch's only Briefing-generation job ended in `cross_report_analysis_disabled`, matching the baseline hold. No valid multi-report Briefing or Signal generation ran because cross-report analysis is disabled in the base config. Integration and unit tests verify immutable Signal snapshots, mutation rejection, held single-source candidates, and idempotent readback; they do not substitute for an enabled live multi-report generation run. Neither current batch had a transient queue failure or retry, so bounded retry/recovery behavior was not exercised live.

## Remaining blockers and acceptance status

| Priority | Blocker | Effect |
| --- | --- | --- |
| P0 | No confirmed WordPress sandbox URL/account; the only known URL may target production | Cannot safely demonstrate fresh create, authenticated readback, or zero-write replay. |
| P1 | Local/live `autonomous_mvp` preflight blocked on isolated databases/schema, Drive OAuth, and WordPress configuration | Autonomous operation is not ready in the tested environment. |
| P1 | Primary shared batch completed 4/5 successfully; Capgemini failed before render | First-attempt reliability and readiness did not match the baseline 5/5. |
| P1 | Assistant paired review found lower lead specificity in several current outputs, and current run variants disagree | Equivalent editorial quality is not established; formal blind human scoring is still required. |
| P1 | Cross-report analysis remains disabled; no live multi-report Signal/Briefing generation or publication ran | Those end-to-end handoffs remain unverified. |
| P2 | Current supervisor capacity is 3 versus baseline 5; wall time rose 8.3% and queue wait increased | Current speed result is not a controlled apples-to-apples implementation comparison. |

The evidence supports **NO-GO for autonomous MVP publication**. The tested implementation can produce reviewable reports with passing readiness on successful attempts, and the crop regression is fixed for this frozen cohort. It does not yet demonstrate first-attempt 5/5 reliability, equivalent editorial quality, unblocked autonomous capability preflight, or safe sandbox publication/readback/replay. Do not use production WordPress for the missing sandbox acceptance step.
