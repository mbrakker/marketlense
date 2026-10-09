# Frozen Five-Report Autonomous MVP Comparison — 2026-10-09

**Recommendation: NO-GO for autonomous publication and merge.** The final exact five-report staging run on implementation SHA `31f6afe9c568be5fc271bff6ec3b56ef3d7f5ee5` completed all five reports on their first workflow attempt, passed validation and readiness 5/5, created and authenticated-read five staging drafts, and replayed all five publication jobs with zero extra writes. No production writes or operator interventions occurred. The paired artifact/source review found no confirmed factual error, but found lower lead specificity in four reports and mixed results in Reuters Institute. Quality is the acceptance gate; the technical success is not a GO.

The run used the exact frozen manifest SHA-256 `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7` and historical baseline commit `0ec3cdff841e16df7044f6645fe8379a464f41ca`. Five report drafts were created as `ml_report` posts with `draft` status on the user-confirmed HTTP staging host `marketlense.medianewsonline.com`. Each was moved to Trash without force deletion after the run; authenticated post-ID/type/status readback confirmed Trash, and active file-ID lookup found none. The report-level `published` terminal state denotes completion of the staging publish handler; the WordPress posts themselves remained drafts.

The current live autonomous-MVP capability preflight was ready (11 bounded provider calls, zero external writes). The local preflight was `degraded` because its four live-provider/WordPress probes are intentionally not checked in local mode; the staging canary and live preflight exercised those boundaries. Signal safety held all 40 single-source candidates for insufficient grounding; no multi-report Signal was eligible. Cross-report Briefing generation and validation succeeded once, while its live publish remained blocked by the existing human-review policy.

The paired review is qualitative and assistant-assisted; the retained rubric has no behavioral anchors for assigning reproducible 1–5 dimension scores, so no new numeric composites are invented. See the final canary and per-report scorecards below. The implementation and redacted result are retained in the linked evidence files. The branch must not be merged while the quality concern remains unresolved.

## Decision summary

- The frozen manifest and all five source MD5s match the historical baseline; the final run retained complete outputs for all five.
- Every final report passed validation and publication readiness, with zero unsupported or unresolved retained claims. The original post-fix validation failure, staging redirects, Briefing-shape failure, and runner-metrics defect are recorded in the historical sections below; the final exact-five run confirms the fixes on one complete unattended cohort.
- All five first-attempt staging draft creates had authenticated readback. Replaying the same jobs preserved their IDs and attempt counts and issued zero additional WordPress writes. All five test posts were later moved to Trash and verified by ID, type, and status; no production write occurred.
- Five report approval records and one Briefing approval record were recorded by the queue readiness path. The Briefing publication job remained blocked as required by `cross_report_publish_live_disabled`.
- The current local autonomous-MVP preflight was `degraded` with four live probes not checked; the bounded live preflight was `ready`, with 11 provider metadata calls and zero writes. The staging-specific preflight verified authentication, reachability, `create_posts`, and draft status.
- All 40 Signal manifests passed readback, replay, and mutation checks and remained held by `signal_grounding_insufficient`; no valid multi-report Signal group was generated. One multi-report Briefing validated on the first attempt.
- The paired review found no confirmed factual error, but weaker top-finding specificity for Capgemini, Activate, KPMG, and Adjust; Reuters was mixed. The final run's unchanged public-quality gate passed with no hard failures, but it does not score commercial distinctiveness.
- Report metrics improved against baseline in calls, tokens, cost, and core batch wall time. The supervisor cap changed from five workers to three, the final run added staging publication, and cross-report analysis was enabled; speed and cost deltas are not attributed to a code optimization or treated as quality improvement.

## Final post-fix exact-five staging canary

The canonical frozen-cohort runner used the unchanged five-source manifest, shared batch, isolated state, WordPress staging, explicit HTTP opt-in, and cross-report analysis. The implementation SHA was `31f6afe9c568be5fc271bff6ec3b56ef3d7f5ee5`; the source-manifest SHA-256 was `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`. The raw runner result remains under ignored `tmp/p5finalsha/frozen-reliability-_w2jy5qt/cohort_result.json`; its SHA-256 is `4c991aa9dd977e882eb001d6d70b45c57102af3ac69c1ab8a1c1d29e06b456f1`. Redacted, committed evidence is [frozen-five-autonomous-mvp-final-canary-20261009.json](frozen-five-autonomous-mvp-final-canary-20261009.json).

The primary pipeline used OpenAI `gpt-6-luna` and model-policy hash `b7743c06f02b644720c2541b317e4adac7093c5f6c522f9078080becd0cdc3e7`, matching the historical baseline. The isolated current `app.yaml` snapshot hash was `e69e45292073ca9334a5ba85d061f4ee9e52cb51aec357588ba094c69040dd32`; it enabled the confirmed staging draft target and cross-report analysis. Supervisor capacity was three parallel workers versus five in the baseline. Both executions used fresh application state; provider-side cached input was present (baseline 117,267 tokens; current 65,426 including the separate Briefing call). Provider request timing was unavailable. The final report-processing metrics below exclude the separate Briefing call and WordPress write operations.

| Report | Validation/readiness; retained claims | Editorial comparison against baseline | Core seconds, baseline → final | Provider calls, baseline → final | Input/output tokens, baseline → final | LLM cost USD, baseline → final | Staging draft; replay |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| Capgemini Research Institute | pass/pass; 0 unsupported, 0 unresolved in both | Insight and executive usefulness down; current lead generalizes the baseline's 71% switching finding | 1,178 → 791 (−32.9%) | 39 → 34 (−12.8%) | 364,300/79,343 → 237,919/54,578 (−34.7%/−31.2%) | 0.089357 → 0.060328 (−32.5%) | Created/read back post 2071 as draft; replay added 0 writes |
| Activate | pass/pass; 0/0 in both | Slightly down in insight and executive usefulness; final core signal drops the baseline's $302B, 2017E–2021E, and GDP comparison, while the summary retains approximately $300B and GDP outperformance | 760 → 989 (+30.1%) | 49 → 49 (0.0%) | 380,564/68,154 → 313,456/75,785 (−17.6%/+11.2%) | 0.088718 → 0.088321 (−0.4%) | Created/read back post 2076 as draft; replay added 0 writes |
| KPMG | pass/pass; 0/0 in both | Modestly down; final lead selects unquantified 2026 pipeline expectations over the baseline's distinctive carve-out thesis; the summary still covers carve-outs and regional differences | 748 → 509 (−32.0%) | 37 → 34 (−8.1%) | 337,873/63,750 → 251,674/64,572 (−25.5%/+1.3%) | 0.074580 → 0.088871 (+19.2%) | Created/read back post 2056 as draft; replay added 0 writes |
| Reuters Institute | pass/pass; 0/0 in both | Mixed; final summary is more qualified about AI referral risk, while the core signal moves to broader revenue-model deterioration and loses the baseline's AI-search lead | 1,183 → 641 (−45.8%) | 53 → 33 (−37.7%) | 478,390/124,566 → 349,440/56,156 (−27.0%/−54.9%) | 0.116891 → 0.079439 (−32.0%) | Created/read back post 2066 as draft; replay added 0 writes |
| Adjust | pass/pass; 0/0 in both | Strongly down in insight and executive usefulness; final top finding describes the e-commerce chapter, while baseline foregrounded the concrete gaming installs-up/sessions-down finding | 675 → 595 (−11.9%) | 37 → 34 (−8.1%) | 318,084/63,284 → 212,888/59,577 (−33.1%/−5.9%) | 0.072372 → 0.059034 (−18.4%) | Created/read back post 2061 as draft; replay added 0 writes |

The paired screen used the retained four dimensions: factual accuracy, insight value, naturalness, and executive usefulness. Reviewer spot-checks against the frozen PDFs supported the report claims summarized above; no factual error was confirmed. The biggest editorial loss is Adjust's change from a concrete measured finding to a section description. The other reports remain readable, and their summaries preserve more evidence than the selected top signals. All five final `public_editorial_quality_after` artifacts passed with zero listed issues; every HTML has one local preview-image reference and that asset exists. Those deterministic checks do not measure the specificity regressions. The review was assistant-assisted and single-reviewer, not blinded human evaluation. The historical report records prior composites, but neither it nor the human-evaluation template defines dimension anchors; new numeric composites are therefore unavailable rather than estimated.

| Cohort measure | Historical baseline | Final exact-five run | Delta / interpretation |
| --- | ---: | ---: | --- |
| Exact reports; terminal successes | 5/5; 5/5 | 5/5; 5/5 | Same frozen cohort and complete terminal accounting |
| Validation/readiness | 5/5 | 5/5 | Same |
| Unsupported/unresolved retained claims | 0/0 | 0/0 | Same automated evidence result; not proof of editorial equivalence |
| Report-only provider calls | 215 | 184 | −14.4% |
| Report-only input/output tokens | 1,879,211 / 399,097 | 1,365,377 / 310,668 | −27.3% / −22.2% |
| Report-only LLM cost | $0.441918 | $0.375993 | −14.9%; report-only scope |
| Core report batch wall time | 1,201.190s | 1,011.413s | −15.8%; supervisor cap and publication configuration differed |
| Core report throughput | 14.985 reports/hour | 17.799 reports/hour | +18.8% measured; not attributed to an implementation optimization |
| File Search calls | 26 | 36 | +38.5% |
| Automatic repairs | 6 | 0 | −6; current outputs completed without repair |
| Queue retries / operator interventions | 0 / 0 | 0 / 0 | Same; no transient queue failure occurred to exercise live recovery |
| Staging draft creates/readbacks | Not exercised | 5/5 | Five first-attempt authenticated staging drafts; no production writes |

The final run used 184 report provider calls, 1,365,377 input tokens, 310,668 output tokens, and estimated report cost $0.375993. Briefing added one call (6,592 input / 4,951 output tokens; $0.003135), so combined model usage was 185 calls, 1,371,969 input tokens, 315,619 output tokens, and $0.379128. Cross-report Signal/Briefing and WordPress publication costs are separate from the historical report-only comparison. Current runner wall time to every report and handoff terminal was 1,019.169s; the 1,011.413s core measure above ends at all five report paths terminal, before the remaining staging handoff drain. The baseline had the WordPress queue disabled and no cross-report generation; the final run enabled both, with Briefing's live publication held by policy.

The live autonomous-MVP preflight on this SHA was ready after 11 bounded provider metadata calls and zero writes. The local-only preflight reported `degraded` because its four live capability probes (LLM, embedding, browser, WordPress) were `not_checked`; it made zero provider calls and zero writes. The staging-specific preflight was authenticated and reachable, verified `create_posts`, and required `ml_report` draft status. This distinction is retained in the JSON evidence.

The durable store recorded five report approval actions and one Briefing approval through deterministic queue readiness, with zero operator interventions. The five publication jobs each succeeded on attempt one and were read back as the exact report ID, post type, draft status, metadata, and content. Replay verified the same job IDs, unchanged attempt counts and publication rows, no duplicate jobs, and zero additional WordPress writes. The separate Briefing publish job was blocked by `cross_report_publish_live_disabled`, an expected policy hold; the queue reported zero dead letters, zero nonterminal outbox entries, and zero unclassified terminal failures.

All 40 Signal manifests passed readback, replay, and mutation rejection. All 40 candidates remained held with `signal_grounding_insufficient`; there were zero unsafe groups and zero valid multi-report Signal groups. The five-source Briefing generated and validated on its first attempt; its cross-report publish remained held. The live run had zero queue retries and no transient failure, so live retry recovery was not exercised; bounded retry behavior is covered by the existing queue/generator regression checks and full quality gate below.

After evidence capture, the five exact posts (2056, 2061, 2066, 2071, 2076) were moved to Trash with non-force requests. Each post's exact report ID, draft status, and `ml_report` type were checked before cleanup; authenticated post-ID/type/status readback confirmed each in Trash, and canonical active file-ID lookup excluded all five. The WordPress REST site's DELETE response did not include the cleanup helper's expected `deleted` envelope, so success was established by the postcondition readback; no delete request was retried.

## Original exact-five staging canary (pre-fix, superseded)

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

### Post-fix follow-up diagnostics

The first exact five-source post-fix shared-batch attempt used source SHA `dc78a08ed2f7137a12ae28f1d26a98aaf6393027`, the pinned manifest, staging drafts, HTTP opt-in, and cross-report analysis. All five ingests and selections completed; three report-analysis jobs completed, Adjust analysis remained active at attempt 1/2, Reuters analysis was pending, and the Briefing job succeeded on its first attempt. The Python runner disappeared about 44 minutes after launch, well before its two-hour per-report drain bound. No `cohort_members.json` or `cohort_result.json` was written, so this attempt has no terminal cohort result and is excluded from acceptance metrics. Its queue had two WordPress jobs pending and no WordPress writes had occurred. Retained state is under ignored `tmp/p5postfix/frozen-reliability-ibyz0gx5/`; the missing process exit/stderr record prevents a more specific cause for that abrupt termination.

One-report diagnostics on the same SHA exposed a separate deterministic result-reporting bug for runs with cross-report draining disabled. `_drain_report_paths` passed `0.0` as `round()` precision, raising `TypeError` after the report queues reached terminal state and masking their outcomes and usage metrics as `frozen_cohort_runner_defect`. The fix moves the conditional outside `round()`. A production-queue regression test first failed on zero reported provider calls, then passed after the fix. The code and test are in commit `16c8dbd4c9016cffa830f349094078a1a1dc008f`.

The required failing-process Adjust rerun on that clean implementation SHA used the pinned source and an isolated, non-staging queue. It completed in 505.713 seconds end to end (497.000 seconds core), with report validation/readiness pass, `awaiting_review`, zero unsupported and unresolved retained factual claims, three bounded repairs, zero queue retries, and zero operator interventions. It used 39 provider calls, 326,912 input tokens, 79,078 output tokens, and estimated cost $0.082817. Its `cohort_result.json` is retained under ignored `tmp/p5adjustpostfix/frozen-reliability-pbpsrdt5/`. This single-report diagnostic confirms Adjust can complete on the fixed implementation, but it is not a substitute for the required five-report shared-batch staging canary.

### Paired output review

| Report | Paired review finding |
| --- | --- |
| Capgemini | The current lead retains the 71% brand-switch finding; its core signal is broader than the baseline's quantified switching-intent signal. |
| Activate | Both runs lead with roughly $300B revenue growth over four years outpacing GDP; the current core signal omits the baseline's more exact amount and period. |
| KPMG | The current lead broadly covers execution and 2026 themes; the baseline more clearly identifies carve-outs and the 2025 M&A pipeline. |
| Reuters Institute | The current recommendation is broad (clarify value/adapt formats); the baseline's AI-search and referral-traffic risk was more specific and decision-relevant. |
| Adjust | The authoritative shared-batch canary failed before final HTML. A later one-report diagnostic on the fixed implementation passed validation/readiness and rendered, but is not substituted into the primary scorecard. |

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

| Priority | Remaining issue | Effect |
| --- | --- | --- |
| P0 | Final paired review found reduced lead specificity in Capgemini, Activate, KPMG, and especially Adjust; Reuters was mixed. Review was assistant-assisted and single-reviewer. | **NO-GO for merge and autonomous publication.** Technical readiness does not establish editorial equivalence. |
| P1 | No blinded human evaluation was run, and the repository rubric does not anchor reproducible numeric dimension scores. | Treat the paired review as a documented quality warning, not a population-level score. |
| P2 | Local capability preflight leaves four live probes unchecked; the live preflight and staging canary were ready. Provider request timing was unavailable and the worker cap differed from baseline. | The evidence does not establish provider-cache-free behavior or a causal performance improvement. |
| P2 | The canary had no transient queue failure. | Existing bounded retry behavior passed regression checks, but live recovery was not exercised. |

The final exact-five run passed report validation/readiness, first-attempt staging draft creation and authenticated readback, durable replay, Briefing generation, and Signal safety checks. All five staging posts were subsequently moved to Trash and verified by ID, post type, and status. The cleanup helper did not receive its expected DELETE response envelope for the first post; authenticated postcondition readback confirmed it was in Trash, and no DELETE was retried. No production write or operator intervention occurred. The specific unresolved acceptance blocker is editorial quality: no false claim was confirmed, but decision-useful lead specificity regressed in four reports and Reuters was mixed. Keep this branch unmerged until a controlled follow-up demonstrates acceptable paired editorial quality under a predeclared evaluation rubric.
