# Frozen Five-Report Autonomous MVP Comparison — 2026-10-09 baseline and 2026-10-10 follow-ups

**Recommendation: NO-GO for autonomous publication and merge.** The latest exact-five generation run on `cf4bba4785aa9c3e018441436c364a5e09f9286a` passed validation and publication readiness 5/5 with zero unsupported or unresolved claims. Capgemini and Reuters have specific leads, but Activate loses the baseline’s exact period/CAGR comparison, KPMG remains theme-led, and Adjust leads with broad AI-adoption data instead of its distinctive gaming results. Report cost is 54.9% above baseline and 82.1% above the canary. Reliability remains sound; editorial acceptance and cost do not.

The run used the unchanged manifest SHA-256 `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`; the environment-loaded preflight admitted 5/5 members after source-checksum verification. Shared batching and cross-report analysis used fresh isolated state. The raw result is in ignored `tmp/p5fix23-full-exact-five/frozen-reliability-0voy3fz4/cohort_result.json`, SHA-256 `106d0c087edb23ce6c83fddf8e2dd401cfb8a48663c7bfe9b1750940fd2d9f4f`. No staging, publication, or WordPress writes occurred; the cross-report briefing completed and all 40 Signal manifests remained held for insufficient grounding.

The paired review is qualitative and assistant-assisted. The retained rubric has no behavioral anchors for reproducible 1–5 dimension scores, so no new numeric composites are invented. Exact current excerpts and evidence IDs are paired with the historical baseline and canary below. Keep the branch unmerged while material lead-specificity regressions remain.

## 2026-10-10 findings-retrieval prompt exact-five run

The committed findings prompt asks for section/title/page and metric-scoped body searches, requires the subject/value/period, directs refinement when results contain only introductions or methodology, and allows abstention only after direct body searches. The full cohort used that prompt once, with no report retries or queue retries. A preceding KPMG/Reuters/Adjust screen showed one successful body finding for KPMG but only introduction findings for Adjust and an empty Reuters pack; its cross-report briefing response failed the two-takeaway schema, then the isolated briefing job succeeded on a cache-bypassed retry. The full five-report run below succeeded on its first briefing attempt. The screen is not substituted for or counted as the exact-five result.

### Paired output and first-loss stages

| Report | Baseline → canary lead | Exact-five lead and evidence | First observed loss; assessment |
| --- | --- | --- | --- |
| Capgemini | Baseline: 71% would switch after an undisclosed pack-size or quality reduction. Canary: broad consumer value and fairness. | “In the October 2025 survey, 74% of consumers cited a competitor’s lower regular price as a compelling reason to switch brands or retail stores” (`switching-price`). The retained findings also contain the baseline’s 71% signal (`switching-undisclosed-reduction`). | No material specificity loss: both mechanisms are source-supported and quantified; selection promotes the distinct lower-price response. |
| Activate | Baseline: $302B growth from 2017E–2021E, 4.1% CAGR versus about 3% GDP. Canary: approximately $300B over four years, outpacing GDP. | “Over the next four years, global Internet and media revenues are forecast to grow approximately $300 billion” (`quote-1`). DocMap key point `tech-media-growth-dollars` still records $302B, 2017E–2021E, and 4.1% versus approximately 3% global GDP CAGR. | The findings pack abstained and the retained quote rounds the amount and omits the exact period and GDP comparison; the TLDR therefore loses the baseline’s most useful comparison. |
| KPMG | Baseline: carve-outs as structural portfolio choices. Canary: expected 2026 pipeline expansion amid regulatory, trade, and tax complexity. | “The report’s strategic-focus section contrasts opportunistic expansion with transactions that reinforce clear strategic direction against a fragmented backdrop for M&A.” The DocMap retains 2026 planned deal means of 5.2 for corporates versus 7.3 for private equity (`diverging-risk-appetites-between-buyers`) and portfolio simplification (`portfolio-simplification-as-a-value-creation-strategy`). | Findings retrieval retained only `research-survey-scope`, not the body outcomes. The plan leads with a broad strategic-focus theme; selected insights begin with AI and use broad descriptions for buyer appetite and portfolio choices. The TLDR remains less decision-useful than the baseline. |
| Reuters Institute | Baseline: search/referral exposure, including an expected search-traffic decline above 40%. Canary: AI-answer features may reduce search referrals, qualified by publisher/topic variation. | “Publishers expect traffic from search engines to decline by more than 40% over the next three years” (`quote-005`). | Findings retrieval abstained, but the direct quote candidate retained the forecast and both the selected insight and TLDR used it. No material lead regression in this run. |
| Adjust | Baseline: casino installs +22% with sessions −5%, and slots installs +46% with sessions −5%. Canary: integrated view of users, touchpoints, data quality, attribution, and AI insights. | “As many as 88% of businesses now report using AI in their daily work, up 13% from the previous year and 76% since ChatGPT’s launch in November 2022” (`intro-ai-adoption`). The DocMap retains gaming outcomes in `gaming-finding-keeping-users`: casual +19% installs/+37% sessions, casino +22%/−5%, and slots +46%/−5%. | Findings retrieval retained the introduction’s AI-adoption result and omitted the gaming body results. The plan and selected insights then emphasize AI and integrated measurement; gaming does not appear among the first four insights. This remains a material lead regression. |

The renderer is not the cause: the generated HTML for all five reports contains the same TLDR as `artifacts.json`. The earliest observed losses are in evidence retrieval for Activate, KPMG, and Adjust; Reuters recovers through its quote pack, and Capgemini’s findings pack retains both switching mechanisms. The retrieval prompt improves one route but has not made body-finding retention consistent: the three-report screen found a KPMG comparison while the exact-five run retained only KPMG survey scope. This is evidence of remaining model/File Search variability, not a validated restoration. The rule changes below remain advisory; the exact run still produced 12 `artifact_quality` warnings and passed readiness.

### Exact-five reliability, runtime, and cost

| Measure | Baseline `0ec3cdff` | Canary `31f6afe9` | Prior run `b8d61633` | Current `cf4bba47` |
| --- | ---: | ---: | ---: | ---: |
| Admitted / validation / readiness | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 |
| Unsupported / unresolved claims | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Report provider calls | 215 | 184 | 200 | 225 |
| Report input / output tokens | 1,879,211 / 399,097 | 1,365,377 / 310,668 | 2,170,908 / 451,725 | 2,686,451 / 481,717 |
| Report LLM cost | $0.441918 | $0.375993 | $0.515708 | $0.684732 |
| Core report batch wall time | 1,201.190s | 1,011.413s | 1,253.144s | 1,224.651s |
| Automatic repairs / workflow retries | 6 / — | 0 / — | 9 / 0 | 9 / 0 |

Compared with baseline, the current run used 4.7% more report calls, 43.0% more input tokens, 20.7% more output tokens, 54.9% more report cost, and 2.0% more core time. Compared with the canary, calls rose 22.3%, input/output tokens 96.8%/55.0%, report cost 82.1%, and core time 21.1%. Compared with `b8d61633`, report cost rose 32.8% while core time fell 2.3%. These are measured comparisons, not causal attribution. Cross-report briefing added one call (6,336 input / 4,225 output tokens; $0.002746), for combined use of 226 calls, 2,692,787 input tokens, 485,942 output tokens, and $0.687478. All five reports awaited review, none were published, and the report workflows had zero retries or operator interventions.

### Verification

`python -m pytest -q tests/test_validation_generator.py` passed (80 tests), and the updated prompt contract check `python -m pytest -q tests/test_prompt_service.py::test_findings_prompt_retains_substantive_central_forecasts` passed (1 test). The canonical `python scripts/ci/run_quality_gate.py` completed with exit code 1: its non-pytest checks passed, while the public-site SEO/performance checks were skipped. Pytest reported 7,175 passed, 1 skipped, 31 deselected, and 1 failed in 832.54 seconds. The sole failure was `tests/test_long_test_file_ownership.py::test_first_party_test_modules_stay_below_long_file_threshold`: unchanged `tests/test_soft_copy_finalization.py` is 1,023 lines against the existing 1,000-line limit. The initial gate also caught the stale prompt wording assertion; that assertion was updated and passed in the completed rerun. No test threshold or gate was changed.

GitHub Actions `ci` run `38057057642` on `3004f79d` also exited 1 at the default pytest step. It reported 7,176 passed and the same single long-test-file failure in 481.90 seconds; all preceding CI steps passed. Because pytest returned nonzero, subsequent coverage, mutation, and release-evidence steps did not run. This hosted result adds no failure beyond the local gate’s pre-existing line-limit failure.

## 2026-10-10 post-fix exact-five nonpublication follow-up

The canonical runner completed all five frozen PDFs on implementation SHA `b8d61633107a4b5c4936e20a048461de0383abaa`. The source manifest is unchanged; its SHA-256 is `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`. The raw result remains in ignored `tmp/p5fix22-full-exact-five-confirm/frozen-reliability-nzqdzimp/cohort_result.json`, SHA-256 `c16f3543981bcd9cfee199f8aebdbc43307eb42ea5776f5221462efcd103131e`.

### Paired lead review and first observed loss

| Report | Baseline → canary lead | Latest lead and retained evidence | First observed loss; assessment |
| --- | --- | --- | --- |
| Capgemini | Baseline: 71% would switch after an undisclosed pack-size or quality reduction. Canary: broad consumer value and fairness. | “74% of consumers say they would switch brands if they found a lower regular price elsewhere” (`value-switch-lower-price`). The baseline’s 71% alternative remains in the candidate set as `value-switch-reduced-quality-or-pack-size` (candidate scores 0.91 vs 0.90). | Finding selection ranks the lower-price response first. This is a different but equally measurable commercial switching signal, and is a clear improvement over the canary; the report’s quality-change mechanism is not the lead. No material lead regression established. |
| Activate | Baseline: $302B growth from 2017E–2021E, 4.1% CAGR versus about 3% GDP. Canary: approximately $300B over four years, outpacing GDP. | “Approximately $300 billion from 2017E to 2021E, with a 4.1% CAGR versus global GDP CAGR of approximately 3%” (`internet-media-growth-forecast`). The DocMap key point `tech-media-growth-dollars` retains the exact $302B. | The finding/candidate rounds the exact amount to approximately $300B; the TLDR restores the period and CAGR comparison. This materially improves on the canary and nearly matches the baseline, with a small exact-value loss. |
| KPMG | Baseline: carve-outs as structural portfolio choices. Canary: many organizations expected 2026 pipelines to expand amid regulatory, trade, and tax complexity. | TLDR: “The report reviews the 2025 M&A context, presenting a dealmaking outlook for 2026 that connects the retrospective with expectations for the 2026 M&A environment.” The first insight is “AI raises the bar for governance, integration readiness, and institutional discipline” (`ai-driven-transformation-of-deal-execution`). | The findings pack abstains. The DocMap’s `portfolio-simplification-as-a-value-creation-strategy` reduces carve-outs to a general structural value lever; the plan prioritizes 2025 momentum first and portfolio simplification third. Candidate scores rank AI at 0.84 and portfolio simplification at 0.77. The lead remains broad and misses the baseline mechanism. |
| Reuters Institute | Baseline: AI-answer/search referral exposure, including an expected search-traffic decline above 40%. Canary: “AI answer features may reduce publishers’ search referrals,” qualified by variation across publishers and topics. | TLDR: “The report expects publishers that thrive to be clear about the value they create for specific audiences and able to embrace change.” `search-referral-exposure` remains the second insight, bound to `answer-engines-and-traffic`; the first is `distinctive-editorial-positioning`. The expert comment retains +91 net for original investigations and −42 net for service journalism, plus the search forecast. | The DocMap retains the >40% search forecast and Facebook/X referral declines, but the findings pack abstains. The editorial plan puts search first while candidate ranking selects distinctive editorial positioning (0.77) over search exposure (0.76). The lead regresses from the canary and baseline despite useful detail later in the artifact. |
| Adjust | Baseline: casino installs +22% with sessions −5%, and slots installs +46% with sessions −5%. Canary: an integrated view of users, touchpoints, data quality, attribution, and AI insights. | TLDR: “The conclusion argues that increasingly connected app journeys make isolated channel strategies inadequate, calling for integrated measurement, attribution, AI insights, and optimization.” The first insight is cross-platform measurement; the third, `gaming-genre-engagement-variation`, describes genre-level engagement but omits the retained figures. | The DocMap retains casual games at +19% installs/+37% sessions, casino at +22%/−5%, and slots at +46%/−5% in `gaming-finding-keeping-users`; the findings pack abstains. The plan prioritizes cross-platform measurement first and gaming third. The gaming signal is therefore weakened at findings retrieval and further deprioritized by plan/candidate selection. The current lead remains below baseline and stays on the canary’s integrated-strategy theme without restoring the gaming evidence. |

The renderer is not the first-loss stage: it carries the generated TLDR and selected insights into the public artifact. The latest summary prompt already directs TLDRs to lead with the strongest supported body outcome and says the plan guides selection; the historical prompt instead tied the executive-summary lead to the priority-one theme’s direct measure. The latest outputs show that empty findings packs and candidate/plan ranking remain the main observed losses. The prompt comparison does not establish that the summary prompt caused them, so no further summary-prompt rewrite is claimed as a fix. Model variability and File Search result quality remain possible contributors; retained artifacts identify where each loss first appears, not its stochastic cause.

At the b8 checkpoint, the KPMG, Reuters, and Adjust artifacts showed empty findings packs even though their DocMaps retained specific body outcomes, and the retrieval adjustment had not yet been model-evaluated. The controlled exact-five run above evaluated that prompt change. It improved retrieval inconsistently and did not restore Activate, KPMG, and Adjust lead specificity, so no restoration of those leads is claimed.

### Advisory quality-check follow-up

Inspection found that the qualitative relationship regex treated the noun in “the value they create” as a concrete relationship, while it missed ordinary inflections such as “gaining,” “declines,” and “raises.” The rule now recognizes those forms, treats AI as a possible actor, and recognizes “consumers value…” only in a subject-plus-verb form. The warning remains non-blocking, carries the exact summary/insight identity and retained evidence ID, and adds no model call. Three regression tests were added for the Reuters-style false negative, a valid qualitative “value” verb, and the Adjust-style gaming relationship; the targeted validation suite passes 7/7.

Applying the revised pure rule directly to the five retained `artifacts.json` files produced eight advisory lead warnings: two summary fields for KPMG, three lead fields for Reuters, and three for Adjust. The evidence IDs are respectively `ai-driven-transformation-of-deal-execution`, `answer-engines-and-traffic`, and `gaming-finding-and-keeping-users`. Capgemini and Activate produced no lead warning. This replay checks only the artifact-quality rule; it does not replace a full workflow or readiness rerun. Warnings remain advisory and do not regenerate prose by themselves, so this is improved detection, not restoration of the three weaker leads.

### Reliability, runtime, and cost

| Measure | Baseline `0ec3cdff` | Canary `31f6afe9` | Prior prompt-fix `d101b55a` | Latest run `b8d61633` |
| --- | ---: | ---: | ---: | ---: |
| Reports admitted / validation / readiness | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 |
| Unsupported / unresolved retained claims | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Report provider calls | 215 | 184 | 215 | 200 |
| Report input / output tokens | 1,879,211 / 399,097 | 1,365,377 / 310,668 | 2,212,902 / 460,705 | 2,170,908 / 451,725 |
| Report LLM cost | $0.441918 | $0.375993 | $0.548714 | $0.515708 |
| Core report batch wall time | 1,201.190s | 1,011.413s | 1,273.216s | 1,253.144s |
| Automatic repairs | 6 | 0 | 9 | 9 |

Against baseline, the latest run used 7.0% fewer report calls but 15.5% more input tokens, 13.2% more output tokens, 16.7% more report cost, and 4.3% more core wall time. Against the canary, calls rose 8.7%, input/output tokens 59.0%/45.4%, report cost 37.2%, and core time 23.9%. Against the prior prompt-fix run, report cost fell 6.0% and core time 1.6%. The baseline supervisor used five workers versus three in current runs, and the canary included staging writes; these are measured differences, not causal performance claims.

Cross-report Briefing added one call (13,068 input / 5,210 output tokens; $0.003912), for combined usage of 201 calls, 2,183,976 input tokens, 456,935 output tokens, and $0.519620. The report batch recorded nine automatic repairs, zero workflow/queue retries, and zero operator interventions. Briefing generated and validated once. All 40 Signal manifests passed readback/replay/mutation checks and remained held for insufficient grounding. No publication jobs or WordPress writes occurred. The current paired review is single-reviewer and qualitative; no material factual error or grounding regression was found, but the baseline-specific KPMG, Reuters, and Adjust lead gaps remain. **Recommendation remains NO-GO; do not merge or enable autonomous publication.**

## Previous 2026-10-10 exact-five prompt-fix run (historical: `d101b55a`)

The canonical frozen-cohort runner completed all five reports on implementation SHA `d101b55aa22e9bb91c4c1bd0b757455830462621`. Source MD5s matched the baseline manifest. The raw local result remains under ignored `tmp/p5fix12-final-prompts/frozen-reliability-mimts8jz/cohort_result.json` (SHA-256 `ff9e5734a739d25fb420a77da1017cfcfedcbde385c1917709bca241598c0786`); only the redacted findings and metrics below are committed here.

### Paired review and first-divergence matrix

| Report | Historical baseline → 2026-10-09 canary | 2026-10-10 output and earliest observed loss | Assessment |
| --- | --- | --- | --- |
| Capgemini Research Institute | Baseline lead used the 71% switching response to undisclosed pack-size or quality reductions; the canary generalized consumer value. | DocMap retains 74% and 71% switching results in `executive-summary` (pp. 4–6), but `findings.json` is empty. The selected insight describes the switching mechanism from `value-redefined` (pp. 8–19) without the 71% figure, and the TLDR returns to broad value themes. First loss: findings retrieval after DocMap. | The insight is more concrete than the canary, but the baseline's measured lead is not restored. The generic-lead warning cannot compare against a finding that the pack omitted. |
| Activate | Baseline lead preserved $302B over 2017E–2021E and 4.1% CAGR against roughly 3% GDP growth; the canary retained only an approximate $300B and GDP outperformance. | DocMap section `s01` (pp. 3–6) records a $300B headline but omits the exact baseline value, period, and CAGR comparison. `quote-1` (p. 4), the first insight, and the TLDR repeat an approximate $300B over the next four years. First loss: DocMap key-point specificity, followed by candidate/summary rounding. | No material restoration against either prior result. |
| KPMG | Baseline emphasized carve-outs as structural portfolio choices; the canary led with pipeline expectations. | The body DocMap entry `portfolio-simplification` (pp. 18–22) reduces the section to a general value-creation theme. A separate finding, `portfolio-separation-structural` (p. 2), retains the structural-versus-byproduct contrast, but the editorial plan ranks portfolio separation fifth and the final insight remains fifth (score 0.77). The lead instead selects a concrete tax, supply-chain, and regulatory pricing-certainty mechanism (score 0.88). | More specific than the canary's pipeline lead, but the baseline structural carve-out thesis is still not promoted. First loss: body DocMap coverage and plan priority. |
| Reuters Institute | Baseline foregrounded AI-search/referral exposure, including the forecast of a greater-than-40% search-traffic decline; the canary broadened to revenue-model deterioration. | DocMap retains the forecast and referral movements in `executive-summary` (pp. 3–6) and `section-2` (pp. 10–14), but `findings.json` is empty. The plan ranks AI discovery first, yet candidates rank distinctive editorial focus (0.72) above AI discovery (0.68); the top insight and TLDR stay broad. First loss: findings retrieval, then candidate ranking. | Partial thematic improvement over the canary, but the historical referral-specific lead is not restored. Validation now warns that the summary and core signal are broader than retained evidence `section-2`. |
| Adjust | Baseline led with gaming acquisition/engagement divergence: casino installs +22% with sessions −5%, and slots installs +46% with sessions −5%; the canary led with an e-commerce chapter description. | DocMap retains the gaming results in `gaming-finding-and-keeping-users` (pp. 17–24), but the findings pack contains only the AI-adoption finding from page 4. The plan ranks integrated cross-platform journeys first and gaming second; the first insight is 88% reported daily AI use. First loss: findings retrieval, reinforced by plan and insight ranking. | More measurable than the canary's section description, but it still suppresses the report's distinctive app-performance evidence and does not match the baseline. |

The first observable loss is upstream of rendering in all five reports: three findings packs omit stronger source material, Activate's DocMap loses the exact comparison, and KPMG's body map/plan underweights the structural mechanism. The renderer carried each final TLDR into the corresponding HTML in all five reports, so field selection or HTML rendering did not cause these gaps. These stage attributions follow retained artifacts; they do not establish whether model variability or search-result quality caused each omission.

The traced code boundaries are `src/generators/evidence_packs/doc_map_strategy.py` and `src/generators/evidence_pack_generator.py` for DocMap/evidence-pack materialization; `src/generators/evidence_packs/findings_strategy.py` for findings normalization; `src/generators/artifact_generator.py` for candidate, final-insight, and summary generation; `src/services/render_service.py` for HTML rendering; and `src/generators/validation/quality.py` for the new advisory checks.

### Code and prompt changes

- `src/generators/validation/quality.py` now treats generic topic language as insufficient on its own and warns when the first retained insight is broader than a later evidence-backed, concrete insight. It also warns on generic lead copy and identifies the exact artifact/claim plus supporting evidence ID for the existing repair pathway. The warning is non-blocking; it adds no model call.
- Regression tests cover generic leads, strong quantitative leads, strong qualitative leads, and cases with no stronger retained alternative. The warning remained a warning in the exact cohort: Reuters had specific `summary.card_tldr_compact` and `insights_final[0].text` warnings tied to `section-2`; validation/readiness still passed. The validator cannot catch a source finding that the evidence pack failed to retain, as seen in Capgemini and the empty packs.
- `src/prompts/report_vs/doc_map/user.yaml` directs each section's strongest result and strategic contrast to `key_points`; `evidence_packs/findings/user.yaml` directs metric- and section-scoped body searches and restricts empty findings to cases with no direct body support.
- Candidate, final-insight, and summary prompts put direct evidence strength and source specificity ahead of abstract context, preserve subjects/periods/comparisons, and allow a section-scoped DocMap fallback without unsupported numbers. A redundant final ranking sentence was removed from `editorial_plan/user.yaml`; its report-breadth, decision-tension, and evidence-ID rules remain.

### Reliability, runtime, and cost

| Measure | Historical baseline `0ec3cdff` | Previous canary `31f6afe9` | Prompt-fix run `d101b55a` |
| --- | ---: | ---: | ---: |
| Reports admitted / validation / readiness | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 | 5/5 / 5/5 / 5/5 |
| Unsupported / unresolved retained claims | 0 / 0 | 0 / 0 | 0 / 0 |
| Report provider calls | 215 | 184 | 215 |
| Report input / output tokens | 1,879,211 / 399,097 | 1,365,377 / 310,668 | 2,212,902 / 460,705 |
| Report LLM cost | $0.441918 | $0.375993 | $0.548714 |
| Core report batch wall time | 1,201.190s | 1,011.413s | 1,273.216s |
| File Search calls | 26 | 36 | 46 |
| Automatic repairs | 6 | 0 | 9 |

Against baseline, the latest run used the same number of provider calls but 17.8% more input tokens, 15.4% more output tokens, and 24.2% more report cost; core batch time was 6.0% higher. Against the previous canary, calls rose 16.8%, input/output tokens 62.1%/48.3%, cost 45.9%, and core time 25.9%. The baseline used a five-worker supervisor versus three in current runs; the canary also enabled staging publication, while this follow-up did not. These are measured differences, not a performance claim.

The prompt-fix run took 1,279.437s from runner entry to all report and handoff terminals. Cross-report Briefing used one additional call (5,864 input / 4,612 output tokens; $0.002892), for combined usage of 216 calls, 2,218,766 input tokens, 465,317 output tokens, and $0.551606. It recorded 9 bounded repairs (2 structured-output repairs), 0 workflow/queue retries, 46 File Search calls, and 0 operator interventions. Reuters logged a retryable `llm_circuit_open` during analysis, then recovered through three targeted repairs; its report completed and passed. Cross-report Briefing validated once. All 37 Signal candidates remained held for insufficient grounding. WordPress was disabled for this run; no external writes occurred.

The paired review remains qualitative and single-reviewer. All five `public_editorial_quality_after` artifacts passed with zero issues, but that deterministic gate does not measure distinctiveness. The current run therefore passes reliability and grounding checks while failing the editorial acceptance criterion. **Recommendation remains NO-GO; do not merge.**

## 2026-10-09 staging canary summary (historical)

- The 2026-10-09 staging canary used the frozen manifest and matching source MD5s; its full details are in the historical canary section below.
- Every report in that canary passed validation and publication readiness, with zero unsupported or unresolved retained claims. The current 2026-10-10 run is summarized above; it also passed all five reports.
- All five first-attempt staging draft creates had authenticated readback. Replaying the same jobs preserved their IDs and attempt counts and issued zero additional WordPress writes. All five test posts were later moved to Trash and verified by ID, type, and status; no production write occurred.
- Five report approval records and one Briefing approval record were recorded by the queue readiness path. The Briefing publication job remained blocked as required by `cross_report_publish_live_disabled`.
- The current local autonomous-MVP preflight was `degraded` with four live probes not checked; the bounded live preflight was `ready`, with 11 provider metadata calls and zero writes. The staging-specific preflight verified authentication, reachability, `create_posts`, and draft status.
- All 40 Signal manifests passed readback, replay, and mutation checks and remained held by `signal_grounding_insufficient`; no valid multi-report Signal group was generated. One multi-report Briefing validated on the first attempt.
- The 2026-10-09 paired review found no confirmed factual error, but weaker top-finding specificity for Capgemini, Activate, KPMG, and Adjust; Reuters was mixed. Its public-quality gate passed with no hard failures, but it does not score commercial distinctiveness.
- In that canary, report metrics improved against baseline in calls, tokens, cost, and core batch wall time. The supervisor cap changed from five workers to three, staging publication was enabled, and cross-report analysis ran; those deltas are not attributed to a code optimization. The latest prompt-fix run's cost and token deltas are reported above.

## 2026-10-09 post-fix exact-five staging canary (historical)

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

## 2026-10-10 Step 1: DocMap-guided findings retrieval correction

This retrieval-only follow-up used the unchanged Activate, KPMG, Adjust, Capgemini, and Reuters PDFs through `generate_evidence_packs` and its existing evidence-fidelity validator. It did not run the autonomous publication canary or change editorial selection, summary generation, readiness, or publication gates. The final-code five-report artifacts are under ignored `tmp/substantive-findings-retrieval-eval/correction-final-coverage/`; Reuters was rerun once with isolated state under `correction-final-reuters-repeat/` after its first targeted fallback returned invalid structured output.

The primary cause was a page-coordinate mismatch: DocMap `pages` are printed page labels, while extracted source spans use physical PDF indexes. Activate's printed page 4 therefore pointed at the contents page at physical page 4 instead of the chart at physical page 5. Broad suffix matching could also mistake contents entries for labels. Retrieval now resolves labels with the existing header/footer matcher, recognizes KPMG's copyright footer, infers a missing label only from a consistent offset across at least two resolved labels, and ranks bounded physical-page excerpts by target wording and numbers. It aggregates all spans on a page and retains source-span provenance.

The bounded fallback also checks all eight selected DocMap targets, preserves complete numeric relationships and their subjects/periods, and searches no more than two missing targets in one pass. Introductory statistics remain eligible when substantive, while reader-profile, author, methodology, survey-scope, and similar metadata are excluded as retrieval targets. DocMap only guides retrieval: independently extracted PDF evidence must pass the existing fidelity checks before it is retained. The fallback response that failed structured validation was rejected; no DocMap-only or unsupported claim was promoted.

### Exact-PDF retrieval results

| Report | Validated result | Grounding / qualification |
| --- | --- | --- |
| Activate | Global Internet and media revenues: $1.7T in 2017E to $2.0T in 2021E, +$302B, 4.1% CAGR versus about 3% global GDP CAGR. | Physical p. 5; supported. Segment CAGRs also passed. |
| KPMG | 2026 planned M&A means: 5.2 deals for corporates versus 7.3 for private equity. | Combined finding on physical p. 15; supported. A portfolio-simplification candidate was proposed but did not enter the validated pack, so it is not claimed as recovered. |
| Adjust | Global 2025 casino installs +22% with sessions −5%; slots installs +46% with sessions −5%. | Each subject, paired measures, and period are preserved on physical p. 19; both supported. The same 46-finding pack retains substantive body results alongside the introductory AI-adoption statistics; no methodology evidence was promoted. |
| Capgemini control | The lower-price switching result remains. The pack also retains 63%/56% personalization/data-sharing and 74%/54%, 66%/40% human-interaction loyalty comparisons. | 22 final findings, all supported; physical pp. 11, 41, and 45. No reader-profile finding was retained. Some fallback findings duplicate the primary wording. |
| Reuters control | A fresh repeat supports publishers' expected search-traffic change of −43% over three years, alongside other report-body findings. | Physical p. 12; the source labels this as the average expected score, not observed traffic. A separate first final-code run returned invalid fallback JSON and did not retain this target. The successful repeat did not retain the historical Facebook/X referral decline finding. |

The Reuters run-to-run result is a material variability caveat: the source supports the target, one bounded fallback failed structured validation, and a fresh isolated run recovered it with a supported claim. A prior retained retrieval run also recovered the historical Facebook/X referral decline from physical p. 20. The latest repeat did not, so this evidence does not establish identical Reuters pack membership across runs.

The prior isolated comparison artifacts were `current16` for Activate, KPMG, Adjust, and Capgemini, and `current17` for Reuters. Counts below are evidence-pack generation only. File Search calls count provider tool calls. Wall time includes measured provider latency and local validation; it is not a causal code-performance benchmark.

| Report | Queries, prior → final | File Search calls, prior → final | Input/output tokens, prior → final | Cost, prior → final | Wall seconds, prior → final |
| --- | ---: | ---: | ---: | ---: | ---: |
| Activate | 20 → 20 | 4 → 4 | 39,399/7,223 → 44,556/12,721 | $0.017552 → $0.020815 | 66.399 → 133.073 |
| KPMG | 15 → 25 | 3 → 5 | 23,165/3,303 → 26,373/2,987 | $0.011469 → $0.016631 | 37.210 → 47.265 |
| Adjust | 15 → 10 | 3 → 2 | 35,159/6,788 → 27,192/10,658 | $0.014411 → $0.013047 | 55.726 → 103.165 |
| Capgemini | 15 → 15 | 3 → 3 | 40,322/4,885 → 45,600/9,719 | $0.013975 → $0.016919 | 38.974 → 94.803 |
| Reuters | 10 → 10 | 2 → 2 | 35,900/10,932 → 43,424/15,206 | $0.014056 → $0.016945 | 110.239 → 144.747 |
| **Total** | **75 → 80** | **15 → 16** | **173,945/33,131 → 187,145/51,291** | **$0.071463 → $0.084357** | **308.548 → 523.053** |

The selected final runs cost 18.0% more than `current16/current17`, used 6.7% more File Search calls, 7.6% more input tokens and 54.8% more output tokens, and took 69.5% more aggregate wall time. They recovered the requested Activate, KPMG buyer-comparison, and Adjust findings; the cost and latency increase is measured, while the benefit is the retention of those source-supported body findings. Provider elapsed time accounts for most of the measured wall time; this cohort does not establish local-code slowdown. Reuters required a separate repeat, which cost $0.016945 and took 144.747 seconds; that repeat is excluded from the per-report final table above.

Focused verification after the final code changes: `python -m pytest -q tests/test_evidence_pack_generator.py tests/test_claim_validation_source_pages.py` passed (76 tests); Ruff passed for the changed source and test modules; `python scripts/ci/run_type_check.py` passed with zero tracked baseline errors; `git diff --check` passed. `tests/test_long_test_file_ownership.py::test_first_party_test_modules_stay_below_long_file_threshold` still fails only on the unchanged `tests/test_soft_copy_finalization.py` at 1,023 lines (HEAD is also 1,023 lines); no limit or allowlist was changed. The full five-report autonomous publication canary remains unrun by design.

## Remaining blockers and acceptance status

| Priority | Remaining issue | Effect |
| --- | --- | --- |
| P0 | The latest paired review still finds baseline lead gaps in Capgemini, Activate, KPMG, Reuters, and especially Adjust. Review was assistant-assisted and single-reviewer. | **NO-GO for merge and autonomous publication.** Passing validation does not establish editorial equivalence. |
| P1 | No blinded human evaluation was run, and the repository rubric does not anchor reproducible numeric dimension scores. | Treat the paired review as a documented quality warning, not a population-level score. |
| P2 | Provider request timing is unavailable; the supervisor capacity differs from baseline. The latest prompt-fix run disabled WordPress staging. | Runtime/cost differences are measured but not causal; the latest run adds no new WordPress evidence. |
| P2 | No queue retry occurred. Reuters did recover from a transient `llm_circuit_open` through the existing bounded repair path. | Report-level recovery was exercised; queue-level retry/recovery remains untested live. |

The 2026-10-09 staging canary passed report validation/readiness, first-attempt staging draft creation and authenticated readback, durable replay, Briefing generation, and Signal safety checks. All five staging posts were subsequently moved to Trash and verified by ID, post type, and status. The cleanup helper did not receive its expected DELETE response envelope for the first post; authenticated postcondition readback confirmed it was in Trash, and no DELETE was retried. The latest 2026-10-10 run passed report validation/readiness but made no WordPress writes. No production write or operator intervention occurred in either run. The specific unresolved acceptance blocker is editorial quality: the latest run still misses several baseline-specific leads, and report cost is materially higher. Keep this branch unmerged until a controlled paired evaluation demonstrates acceptable editorial quality under a predeclared rubric.
