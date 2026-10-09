# Frozen Five-Report Autonomous MVP Comparison — 2026-10-09

**Recommendation: NO-GO for autonomous publication.** The final frozen five-report staging canary admitted all five exact sources, but only 1/5 completed staging draft creation, authenticated readback, and duplicate-job replay. Three reports reached report readiness but failed at the WordPress target with `wordpress_target_installation_redirect`; Adjust failed report validation with three unresolved retained factual claims. The separate cross-report Briefing job also failed validation. The site was confirmed as staging at `http://marketlense.medianewsonline.com`; no production publish occurred.

The authoritative unattended run is on source SHA `fca1234ea6bfa6492dbcff0726dd69a423876e15`, using manifest SHA-256 `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`. It reached terminal outcomes for all five reports with zero operator interventions and zero queue retries. One staging draft was created. Initial post-run reads returned a setup redirect; a later authenticated read confirmed the exact draft, and cleanup moved only that verified test post to Trash and verified its status. The Briefing output retry classification was fixed afterward in code commit `5acc7970b1a3005ce869a3dff63457e3c84c162a`; that fix has focused regression coverage but was not exercised in another live Briefing run.

Earlier runs and their detailed scorecards are preserved below for chronology. They do not replace or override the final staging canary.

## Decision summary

- The frozen manifest and all five source checksums match the retained baseline exactly.
- Final report workflow results were: Capgemini, Activate, KPMG, and Reuters Institute passed report validation/readiness; Adjust did not. WordPress staging succeeded only for KPMG.
- The staging preflight on code SHA `5acc7970…` was ready, with 23 workflow statuses ready, WordPress capability ready, 11 metadata calls, and zero external writes. This did not prevent three per-report WordPress publish jobs from receiving `wordpress_target_installation_redirect` during the canary.
- Signal readback/replay/mutation verification passed for all 32 manifests; all remained single-report holds. No multi-report Signal was generated. The only Briefing generation job failed because `executive_takeaways` contained fewer than two populated strings.
- The current Briefing shape failure is now classified as retryable so the existing queue can make its configured bounded second attempt. Evidence remains local: focused generator tests and queue retry tests passed; no live post-fix retry was run.
- Paired review found weaker specificity in the Reuters Institute and KPMG output; Activate retained a broadly equivalent quantified lead with a less specific core signal. Adjust has no final HTML. This review is a single-reviewer warning signal, not formal human scoring.
- The final run used a three-worker supervisor cap versus five at baseline, and Adjust failed before completing. Elapsed-time and token-cost reductions are not evidence of a quality-preserving speed improvement.

## Final shared-batch staging canary

The canonical runner used the frozen manifest with shared batching, WordPress staging enabled, cross-report analysis enabled, and an explicit HTTP opt-in. Configuration targeted the user-confirmed staging host and draft status. The exact source run used SHA `fca1234ea6bfa6492dbcff0726dd69a423876e15`; the later code fix is recorded separately below. The primary result is retained at `tmp/p5final/fca-run/frozen-reliability-3hylkks1/cohort_result.json`.

| Report | Report validation/readiness | Duration | Provider calls | Input/output tokens | Cost USD | Staging outcome |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Capgemini | pass / pass | 569s | 34 | 252,324 / 54,709 | 0.064333 | Failed `wordpress_target_installation_redirect` |
| Activate | pass / pass | 832s | 48 | 269,760 / 59,887 | 0.068501 | Failed `wordpress_target_installation_redirect` |
| KPMG | pass / pass | 488s | 38 | 254,985 / 67,158 | 0.076000 | Draft created, authenticated readback and replay verified; post ID 2050 |
| Reuters Institute | pass / pass | 740s | 30 | 359,957 / 61,476 | 0.085651 | Failed `wordpress_target_installation_redirect` |
| Adjust | fail / fail | 371s, partial | 40 | 289,975 / 77,962 | 0.081402 | Held before WordPress; three unresolved retained factual claims, zero unsupported |

| Cohort measure | Baseline | Final canary | Result |
| --- | ---: | ---: | --- |
| Exact reports admitted / terminal | 5/5 | 5/5 | Same cohort; complete terminal accounting |
| Report validation and readiness | 5/5 | 4/5 | One semantic `claim_support` failure on Adjust |
| Staging draft/readback/replay | Not exercised | 1/5 | KPMG only; 3 target redirects; Adjust held |
| Report provider calls | 215 | 190 | −11.6% |
| Report input/output tokens | 1,879,211 / 399,097 | 1,427,001 / 321,192 | −24.1% / −19.5% |
| Report estimated cost | $0.441918 | $0.375887 | −14.9%; not a quality-adjusted improvement |
| Queue retries / operator interventions | 0 / 0 | 0 / 0 | No manual repair or requeue |

The shared handoffs added one Briefing provider call (9,987 input / 5,006 output tokens; $0.003502). Combined report-plus-Briefing totals were 191 calls, 1,436,988 input tokens, 326,198 output tokens, and $0.379389. Report workflow wall time was 851.491 seconds; it is not comparable as a throughput win because the supervisor cap differed from baseline and Adjust ended early. Six bounded automatic report repairs occurred; 32 File Search calls were recorded.

### Staging effects and cross-report handoffs

The KPMG staging draft used post type `ml_report` and draft status. Its in-run authenticated readback succeeded, and replaying the same durable job preserved the job ID and attempt count with `additional_wordpress_writes=0`. Initial post-run collection and by-ID reads returned HTTP 302 to the site's setup route (`wordpress_target_installation_redirect`). A later read returned HTTP 200 and verified post ID 2050 as `ml_report`, status `draft`, with the exact KPMG report ID in `ml_file_id`. The corrected canonical file-ID lookup then found that same post. Cleanup moved it to Trash without force deletion; authenticated Trash readback succeeded and active file-ID lookup no longer returned it. No production write occurred.

All 32 immutable Signal candidate manifests passed readback, replay, and mutation verification. All 32 were held with `signal_grounding_insufficient`; there were zero unsafe or multi-report Signal groups. The single Briefing generation job dead-lettered on `cross_report_analysis_output_invalid` because the model returned fewer than two populated `executive_takeaways`. No validated multi-report Briefing was produced.

The local fix makes only that exact output-cardinality/populated-string failure retryable. Existing `briefing_generation` queue policy allows two total attempts; grounding or evidence failures remain non-retryable. Added regression coverage verifies the typed error and bounded queue retry mechanics; the live canary predates the fix, so successful post-fix Briefing generation remains unproven.

The live KPMG post exposed a separate idempotency-lookup defect: the REST request combined exact `ml_file_id` metadata filtering with a text `search`, which made WordPress require both filters and return no match for a post whose metadata was correct. The canonical lookup now sends the exact metadata filter without the contradictory search filter. Before cleanup, the old lookup returned not-found while authenticated by-ID readback showed matching metadata; after the fix, the canonical lookup found the same post. `tests/test_wordpress_service.py` now covers a metadata match whose rendered content does not contain the file ID. Focused service and public-render tests passed (32 passed).

A separate one-report Adjust diagnostic on code SHA `5acc7970b1a3005ce869a3dff63457e3c84c162a` first hit the runner's output-path budget. Its required failing-process rerun used the unused short root `C:\p5adj5`, completed the report workflow, and retained `validation.json` with `status=pass`. The wrapper nevertheless recorded `frozen_cohort_runner_defect` and omitted report metrics. That diagnostic is not counted as an end-to-end success or used to replace the primary cohort result.

### Paired output review

| Report | Paired review finding |
| --- | --- |
| Capgemini | The current lead retains the 71% brand-switch finding; its core signal is broader than the baseline's quantified switching-intent signal. |
| Activate | Both runs lead with roughly $300B revenue growth over four years outpacing GDP; the current core signal omits the baseline's more exact amount and period. |
| KPMG | The current lead broadly covers execution and 2026 themes; the baseline more clearly identifies carve-outs and the 2025 M&A pipeline. |
| Reuters Institute | The current recommendation is broad (clarify value/adapt formats); the baseline's AI-search and referral-traffic risk was more specific and decision-relevant. |
| Adjust | Validation failed before final HTML; no paired rendered-output judgement is possible for this canary. |

This is a paired assistant-assisted review of retained output, not the repository's formal blinded human score procedure. Deterministic readiness does not measure decision value or editorial distinctiveness.

## Cohort identity and retained evidence

| Publisher | Stable report ID | Frozen PDF MD5 |
| --- | --- | --- |
| Capgemini Research Institute | `cohort-81af3890cd84ece81ef1` | `81af3890cd84ece81ef16e1aabda8027` |
| Activate | `cohort-cbb6e7df67412186b8bc` | `cbb6e7df67412186b8bc094a424ac890` |
| KPMG | `cohort-2acb4a56e14add5d7717` | `2acb4a56e14add5d7717f34c378f9091` |
| Reuters Institute | `cohort-4b763ae2286ca69fe8ac` | `4b763ae2286ca69fe8acb63b17508dfb` |
| Adjust | `cohort-b638414df0b1fccea1cd` | `b638414df0b1fccea1cd8a93eaf8f5aa` |

The frozen manifest is `docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json`, SHA-256 `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`. The runner verified all five source MD5s before submission. The historical baseline is preserved at commit `0ec3cdff841e16df7044f6645fe8379a464f41ca`, with its accepted record at `docs/quality/frozen-five-systematic-fixes-baseline-20261005.json`. Its original Temp run directory and HTML outputs were read without modification.

The earlier comparison's primary batch summary is retained at `out/frozen-five-comparable-batch-20261009.stdout.jsonl`; its isolated run is under `tmp/p5b/ias-first-attempt-c9et0s5k/`. The earlier full per-report-isolated cohort is under `tmp/p5f/`; its Capgemini diagnostic is under `tmp/p5diag/` and redacted result at `out/frozen-five-capgemini-diagnostic-20261009.stdout.jsonl`. Redacted preflight records are under `out/`. Render copies and screenshots used for that visual comparison are under ignored `tmp/p5evalview-20261009/`. Raw model responses, prompts, source extracts, and credentials are not included in this report or commit.

## Earlier configuration and comparability

The configuration and table in this section describe the `4161d8e5…` comparison, not the final staging canary above.

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

## Earlier comparable shared-queue performance and reliability

This section records the earlier source SHA `4161d8e5fc4c537f6397c1e51f9f06cd6dda73f7` comparison. The later live staging canary and the acceptance decision are recorded above; its outcomes supersede this section for final Prompt 5 acceptance.

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

## Earlier paired factual, grounding, editorial, and visual review

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

## Earlier autonomous approval, WordPress, Signal, and Briefing evidence

The blocked preflight and no-sandbox statements below describe the earlier `4161d8e5…` validation. The later confirmed staging target, live preflight, draft/readback/replay, route redirects, and cross-report outcome are documented in the final-canary section above.

In the earlier run, the local `autonomous_mvp` capability preflight was **blocked** with 11 blocking checks: isolated state, Signal-store, and reports databases were missing; the isolated LLM-usage database had an incompatible schema; and the required Drive OAuth token was absent. Its bounded live preflight was **blocked** with 6 checks, 5 read-only provider metadata calls, and 0 external writes. The WordPress site URL was explicitly blanked for that probe because the available configured URL could target production; WordPress capability consequently reported `publish_configuration_invalid`. The frozen runner separately admitted the exact 5/5 cohort under its isolated admission path.

The automated-publication tests passed and cover checksum-bound approval, readiness/grounding holds, changed or stale packages, override-based manual approval, and duplicate ready-report replay leaving one approval/outbox record. This is local test evidence only. The earlier cohort used the base profile and all successful reports remained `awaiting_review`; no live autonomous approval event was produced in that run.

At the time of that earlier run, no approved WordPress sandbox URL or sandbox credentials were available. No WordPress create, authenticated readback, or durable-job replay was attempted, and the publish queue was disabled in baseline and current runs. A local duplicate-approval test is not evidence of zero-write replay against WordPress.

In the earlier isolated five-report cohort, 37 immutable Signal candidate manifests were read back through the canonical service and passed hash/contract validation; all 37 groups referenced one report and remained held with `signal_grounding_insufficient`. Its primary batch had 32/32 such manifests pass readback; all were single-report holds. No Signal post was generated or published, preserving the human-review restriction. The baseline had 38 Signal-generation dead letters (`signal_grounding_insufficient`) and 2 pending Signal-generation jobs.

In the earlier run, Briefing opportunity handoffs succeeded for the rendered reports, but its only Briefing-generation job ended in `cross_report_analysis_disabled`, matching the baseline hold. No valid multi-report Briefing or Signal generation ran in that run because cross-report analysis was disabled in the base config. Integration and unit tests verify immutable Signal snapshots, mutation rejection, held single-source candidates, and idempotent readback; they do not substitute for the enabled live multi-report run recorded above. Neither earlier batch had a transient queue failure or retry, so bounded retry/recovery behavior was not exercised live there.

## Remaining blockers and acceptance status

| Priority | Blocker | Effect |
| --- | --- | --- |
| P0 | Three of four ready-report jobs received `wordpress_target_installation_redirect` during the canary, although later read-only requests recovered and the KPMG test draft was verified and moved to Trash | Staging target stability during a full cohort remains unproven; those original terminal failures still count. |
| P0 | Adjust failed validation with three unresolved retained factual claims; the separate short-path diagnostic's wrapper returned `frozen_cohort_runner_defect` despite a persisted validation artifact of `pass` | The complete first-attempt report path remains 4/5; the auxiliary diagnostic cannot be counted as a recovered end-to-end pass. |
| P1 | Cross-report Briefing generation dead-lettered on malformed `executive_takeaways`; no multi-report Signal group was eligible | No valid Briefing was produced. The bounded retry classification was fixed locally but not confirmed in a post-fix live run. |
| P1 | Paired output review found less decision-specific content for Reuters Institute and KPMG; no formal blinded human scoring was run | Editorial equivalence and value remain unproven. |
| P2 | Live capability preflight was ready with zero writes, while local autonomous preflight remained degraded; report run used supervisor capacity 3 versus baseline 5 | Preflight readiness does not establish reliable report publication or controlled performance equivalence. |

The evidence supports **NO-GO for autonomous MVP publication**. The run demonstrated one safe staging draft, readback, and duplicate-job replay with no additional write, but three other report publishes failed and the successful post's current status cannot now be verified. Report validation/readiness passed for four of five reports, the Briefing did not validate, and the primary outputs do not establish equivalent editorial decision value. The staging target is authorized only for reversible draft testing; no production publication was attempted. Do not merge this branch until the Prompt 5 GO criteria are met.
