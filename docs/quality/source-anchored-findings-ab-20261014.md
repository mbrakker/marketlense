# Source-Anchored Findings A/B/B2/B3/B4 Experiment

> **Archived experiment evidence — 2026-10-14.** B1–B4 completed in shadow mode on experimental commit [`586d35d`](https://github.com/mbrakker/marketlense/commit/586d35d19fb8a9f7c9dc2eb0f74c8150392f3c03). **Final architectural decision: NO-GO** for the one-call or context-assisted replacements as tested; the production pipeline remains unchanged. This report preserves the measured outcomes, limitations, reviewed source identities, cost accounting, and saved-artifact checksums. It is **not** a validated production regression baseline or a complete, independently replayable dataset.
> **Archival limits:** The experiment-specific runner, YAML prompts, tests, and prompt-fixture modifications are deliberately not integrated into `main`; historical reproduction commands below refer to that discarded experimental code. The raw B1–B4 result JSON and local PDF/source artifacts were stored in Git-ignored `tmp/`/`out/` locations and are **not included in this archive**. Their recorded hashes document provenance but cannot by themselves recreate or independently regrade the original outputs. E18 remains active and no production acceptance criteria were closed.

**Date:** 2026-10-14

**Base:** main at a053733caa20bbe9b9d519bc010af118b03a5b82

**Disposition:** **NO-GO** for production integration or the proposed one-call architecture. B4 reused source-verified report context but still omitted the material 519-corporate / 181-PE respondent split from its qualifications and findings, despite receiving it explicitly. It added one p. 21 carve-out objective finding over B3, but remained concentrated on the same narrow themes and omitted regional and AI findings. All six B4 claims were visually supported; the unchanged validator rejected two chart claims and retained four. Retained A was broader but also has readiness failures, two page-anchor errors, and three wording qualifications from independent review. B4 is one exploratory run, not a stability result; all work remained in shadow mode.

## Scope and comparison limits

The frozen cohort manifest is [reliability-cohort-20261001-next-five/frozen_cohort.json](reliability-cohort-20261001-next-five/frozen_cohort.json), SHA-256 744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7. Reuters and Adjust PDFs matched its source hashes:

| Source | PDF SHA-256 | B input coverage |
| --- | --- | --- |
| Reuters Institute, *Trends and Predictions 2026* | f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52 | 47 physical pages, 46 with text; 104,913 characters |
| Adjust, *Mobile App Trends 2026* | ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3 | 41 physical pages, all with text; 51,085 characters |

A reuses the retained multi-stage pipeline artifacts under tmp/verify2-replay-9eeb47aa; B received all locally extracted pages in one bounded prompt per call. No end-to-end production ingestion workflow was run, but the shadow model call did receive the complete extracted source text. B did not receive A's findings or reference answers. A's retrieved evidence, producer/configuration and run context differ from B's, so this is exploratory rather than a matched causal comparison. The original B1 blind assessment compared only the initial outputs; repeats were checked separately against the PDF. The B2 section records a fresh blinded comparison of all four Adjust sets.

## Architecture and quality results

| | A — retained pipeline | B — isolated shadow prototype |
| --- | --- | --- |
| Generation path | Existing multi-stage findings pipeline, with retained retrieval/analysis artifacts and downstream validation | One GPT-6 Luna structured call for each report; complete source text, no File Search, no workflow rerun |
| Boundaries reused | Existing pipeline artifacts and validators | pdf_service, prompt_service, llm_service, config_service, FindingsPack, validate_evidence_fidelity() and exclude_untrusted_evidence() |
| Output | Existing findings artifacts and downstream editorial stages | Existing findings-pack shape plus an experiment-only sidecar for metric relationships, significance and commercial category |
| Downstream compatibility | Retained public-quality/readiness artifacts exist | Pack conversion and fidelity filtering ran; no editorial/readiness or publication stage was run, so end-to-end compatibility is unverified |

The B1 prompt was limited to source-grounded propositions, exact metric relationships, physical page references and concise commercial significance, with an eight-finding maximum; each successful B1 call returned seven findings. B2 retained the eight-finding maximum and added a separate scope excerpt plus a breadth instruction; its one call returned eight candidates. No production prompt, validator, or publication behavior changed; the B2 result is an ignored experiment artifact.

The prompt-fixture corpus baseline was regenerated with its canonical builder to include the B1–B4 test-only experiment namespaces. Unchanged fixture measurements were preserved; the B4 namespace and report-family aggregates were added. Existing regression tolerances and allowlist entries were not changed.

**Reuters.** The initial B set surfaced the three-year −43% search-traffic expectation (physical p. 12), Chartbeat's global −33% Google Search referrals year-on-year (p. 13), the AI licensing expectation distribution 20% significant / 49% minor / 20% none / 11% don't know (Q8, base 272; p. 15), video/audio investment intentions 79% / 71% (p. 18), platform net-effort scores +74 YouTube / +61 AI / +56 TikTok / −52 X (p. 21), and other source-specific results on creator advertising, creator-style journalism and revenue priorities (pp. 25–26, 38). The blind review rated all seven initial B items fully supported and page-specific. It rated retained A's nine items as zero fully supported, eight partial and one unsupported, principally because A findings were broader and less tightly bound to page evidence. This favors B for Reuters traceability, not for breadth: A covered confidence, social referrals, distinctive journalism, creator competition, newsroom AI, revenue priorities and survey scope.

The repeat again selected the −43% and −33% referral findings, the 28% e-commerce revenue priority and the $37bn creator-advertising estimate. Its other picks shifted to subscriptions (76%), native advertising (64%) and the 76% creator-style journalism intention (p. 25). Four of seven concepts recurred; the alternatives were source-supported, but the slate was not stable.

**Adjust.** Initial B covered global e-commerce installs/sessions (−10% / +5%) and LATAM (+17% / +30%, p. 27), global e-commerce CPI ($1.00 → $0.98) versus deal-discovery CPI ($1.44 → $2.26, p. 29), and four finance-app findings across installs, sessions, CPI and paid/organic ratios (pp. 34–38). Its repeat selected only e-commerce: it repeated the global and LATAM install/session relationships, then added Europe (−22% / +6%, p. 27), session length (10.04 → 9.6 minutes, p. 28), marketplace/classifieds retention (24% / 14% / 11% / 8% on days 1/7/14/30, p. 29), and paid/organic ratio (0.48 → 0.54, p. 30). Three of seven concepts recurred; the second run dropped finance and selected additional e-commerce measures.

The blind review rated A's 12 Adjust items fully supported, versus zero fully supported and seven partial for initial B. The central gap was scope: every B Adjust cohort_or_population value was empty, and its wording did not say these were Adjust-tracked apps. The report cautions that its aggregate dataset may not represent the whole app market (physical p. 13). B's numbers were source-supported, but the missing population qualification makes its global-sounding claims incomplete. A also covered AI, gaming, methodology and market context that neither B run selected. B's analytical-significance text was present but often generic.

### Adjust B2 — scope excerpt and selection breadth

Offline review of both retained B1 slates against physical page 13 found the same material qualification gap in every finding: the metric pages (pp. 27–30 and 34–38) do not restate that the figures are aggregated, anonymized data from apps tracked by Adjust, or that the dataset may not represent the whole global app market. Page 13 also describes a mix of Adjust's top 5,000 apps and all apps it tracks, a January 2024–January 2026 date range, and two source datasets covering 45 and approximately 250 countries/territories. The report does not bind an individual metric to one of those two dataset members, so B2 did not assign either member or country count to a specific finding. All selected metric pages are covered by the report-wide “unless otherwise noted” Adjust-source statement. Each metric's stated geography, timeframe, and observed comparison still need to come from its own page.

This is a generation defect in B1, distinct from validator behavior: the values were supported, but B1 omitted a material population qualifier. Adding the page-13 context manually to the old outputs would be a counterfactual only and is not counted as B1 or autonomous generation success.

The eight-finding ceiling did not force B1's narrower slates. Both B1 Adjust runs returned seven findings, below the cap; B1 initial covered e-commerce and finance, while B1 repeat selected only e-commerce despite substantive gaming, AI, measurement, and retention material elsewhere in the source. Two runs cannot identify why selection varied, but the cap itself does not explain the single-vertical repeat. B2 returned eight findings across e-commerce, finance, and gaming after receiving an explicit breadth instruction; no quota or historical claim was supplied.

B2 used the existing extracted source plus a separately identified excerpt selected from physical p. 13. All eight candidate propositions match their cited metric pages, and each finding's text and `cohort_or_population` field states the aggregated, anonymized Adjust-tracked-app scope and market-representativeness caveat. Each cites the metric page and p. 13. The set spans three verticals and acquisition, activity/session length, and CPI metrics. It is broader than either B1 slate, while still narrower than retained A's 12 items: it omits retention, including flat gaming retention (p. 21) and post-install retention comparisons (pp. 29 and 37), and does not cover the report's AI or cross-platform measurement findings (pp. 9 and 11). Most B2 significance notes are useful but generic; p. 28 itself gives a more decision-relevant interpretation of shorter sessions as either faster purchases or lost attention. One B2 evidence snippet (f7) omits the p. 34 chart title that binds “Global”; the cited physical page and visual chart check support it, but the snippet is less self-contained than the other claims.

The fresh blinded four-set assessment rated B2 **8 fully supported / 0 partial / 0 unsupported**. It rated B1 initial and repeat **0 / 7 / 0** each because their figures matched but every finding omitted the population qualification. It rated retained A **11 / 1 / 0**: the partial item states ATT uptake without the source's denominator of iOS users who permit tracking requests. A previous A-only blind assessment rated all 12 fully supported; the fresh review's denominator finding is recorded as a reviewer difference, not silently reconciled. Both assessments found A broader than B2. B2 improves the diagnosed Adjust scope defect and broadens B1 selection; it does not establish that B2 matches A's breadth or downstream editorial quality.

### KPMG B3 — autonomous scope and finding generation

B3 used one publisher-neutral GPT-6 Luna structured call over all 42 extracted pages of the frozen KPMG *2026 Global M&A Outlook* (108,500 characters). The prompt received the complete source text, with no manually selected methodology excerpt or publisher-specific page instruction. The PDF matched the frozen manifest (MD5 `2acb4a56e14add5d7717f34c378f9091`; SHA-256 `a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589`); source-context SHA-256 was `03ca9201eed8253f0a9e47edd7b3171a9652fb93f57e1374f3a37796ccc9b200`.

The output contained five survey findings, all manually checked against their cited original PDF charts/pages by an independent reviewer: pipeline expectations (p. 8), mean planned deal counts (p. 15), carve-out acquisitions under consideration (p. 17), carve-out activity expectations (p. 19), and anticipated carve-out challenges (p. 31). The statements preserve the distinction between survey expectations/plans/consideration and realized activity. The independent reviewer confirmed all five figures and page anchors. Four of the five findings were rejected by the unchanged validator for `quantity_not_entailed`; those are chart false rejections, not observed value errors.

Scope capture was incomplete. Q2 identified 700 dealmakers, 20 countries/jurisdictions, field dates, and respondent roles/sectors, but its evidence snippet only supports the sample size, jurisdictions, and dates. The source's p. 4 methodology also reports 519 corporate and 181 private-equity respondents; B3 omitted that composition even though F2 and F3 compare those groups. Page 4 reports regional composition (55% Americas, 31% EMEA, 13% APAC), also omitted. Q1 captured the general professional-advice disclaimer on p. 42; the reviewer found it report-wide but not a material qualifier for these descriptive statistics. No item-level denominators or weighting were supplied by the cited charts, so the displayed values should not be presented as independently verified population estimates.

The five findings are narrow: three concern carve-outs, with the remaining two about pipeline/deal cadence. The slate omitted useful regional planned-deal means on p. 7, AI findings on pp. 24 and 26, and execution themes on pp. 28–33. All findings were survey-derived; none covered the qualitative advisor themes. B3 demonstrates that a generic prompt can find relevant charts and produce careful status language in one run, but does not meet scope-completeness or breadth expectations. Its FindingsPack v1.0 conversion and evidence filtering ran; only one item passed the unchanged validator and therefore would remain after the experiment's trust filter. No downstream editorial, readiness, or publication stage ran, so compatibility beyond pack conversion/filtering is unverified.

The same anonymized independent source review inspected retained A and B3 against the original PDF. It found A broader across regional outlook, buyer differences, carve-outs, AI, and execution, but identified two material page-anchor errors: A finding 8's cited pp. 31–32 should be p. 33, and finding 9's five-part buyer lens is on p. 33 rather than p. 38. A finding 3 should say PE respondents were more likely to be *considering* deal types, rather than implying completed activity; finding 6 generalizes an AI statement specifically about leading deal teams; and finding 9 should preserve that its five-part buyer lens is report synthesis, not a quantified survey result. The retained A `evidence_fidelity.json` independently marks readiness `not_publishable` with 13 unsupported factual claims and zero unresolved factual claims. In the separate offline check of only A's nine findings against the recovered page spans, the unchanged validator returned 0 supported / 1 unsupported / 8 unresolved; this is a different artifact/check from A's retained 13-claim readiness result. A remains a breadth reference, not a publishable alternative.

### KPMG B4 — source-verified existing context plus independent finding generation

B4 received the same 42-page extracted KPMG source as B3 and a minimal projection of the retained `scope.json`, `methods.json`, `limitations.json`, and `report_context.json`. The context was bound to report id `cohort-2acb4a56e14add5d7717`, PDF MD5 `2acb4a56e14add5d7717f34c378f9091`, PDF SHA-256 `a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589`, and source-context SHA-256 `03ca9201eed8253f0a9e47edd7b3171a9652fb93f57e1374f3a37796ccc9b200`. The projection hash is `a07a37f047fdcfc32e8f2461abce8bcabd858b3a9a3e8a07d857473894aa205e`.

The projection includes the survey population (700 M&A dealmakers across 20 countries and jurisdictions), field dates (19 December 2025–27 January 2026), respondent profile (senior executives across 10 sectors involved in M&A decisions), sample composition (519 corporate and 181 private-equity respondents), geographic composition (55% Americas, 31% EMEA, 13% APAC, preserved as printed), and the distinction between survey responses and qualitative interpretation from senior transaction advisors, all bound to physical p. 4. It also includes the report-wide professional-advice disclaimer from p. 42 and the section-specific transaction-process and AI-regulatory qualifications from pp. 27–28. Context artifact hashes are embedded in the projection. `report_context.json` historical findings, overview, and section conclusions were excluded. The generator was told not to treat sample counts as item denominators, weights, or evidence of representativeness; original PDF pages remained authoritative.

An offline check against B3 confirmed that neither 519 nor 181 appeared in B3's findings or scope qualifications. This establishes that the projection supplied missing context; manually adding it to B3 would only be a counterfactual and is not counted as generation success. B4 then received the context but still did not state either sample count in its qualification output or findings. Its Q2 evidence excerpt quotes the survey size, geography, and field dates but omits the same-page respondent profile included in Q2's statement. Thus B4 did not fix the central qualification defect. It did avoid treating the respondent counts as per-question denominators.

B4 returned six candidates: the p. 8 pipeline expectation, p. 15 planned deal means by respondent group, p. 17 carve-out acquisition consideration, p. 19 carve-out activity expectations, p. 31 anticipated execution challenges, and a new p. 21 distribution of stated carve-out objectives (52% efficiency, 42% remaining-business valuation, 35% risk reduction, 33% reinvestment). Independent visual checks of all six cited charts/pages confirmed their values, cohorts, periods, and expectation/plan/selection/objective status. B4 omitted the p. 8 12% “much higher” / 44% “slightly higher” breakdown included in B3. It still did not select regional or AI findings. Four of six candidates are carve-out-specific, so the added objective finding is a modest increment, not material thematic broadening. The commercial-significance notes remain mostly generic.

The unchanged validator returned **4 supported / 2 unsupported / 0 unresolved**; the trust filter retained four findings without intervention. Visual review confirmed both rejected claims: F1's p. 8 56% pipeline comparison was marked `protected_fact_timeframe_incompatible`, and F3's p. 19 50% / 44% / 6% activity distribution was marked `quantity_not_entailed`. These are validator false rejections, not observed value errors. All six candidate claims are source-supported; no claim was force-passed. The FindingsPack v1.0 conversion, metric relationship sidecar, scope binding checks, validator, and trust filter ran. The deterministic public-editorial-quality gate evaluates summary, insight, figure, and rendered-HTML artifacts that this findings-only shadow run did not produce. No paid editorial generation, production readiness stage, or publication was run.

| Dimension | Retained production A | B3 one-call shadow run | B4 context-assisted shadow run |
| --- | --- | --- | --- |
| Breadth | Nine findings span regional outlook, buyer differences, carve-outs, AI, and execution. | Five findings; three concern carve-outs, with regional and AI themes missed. | Six candidates, adding a p. 21 carve-out-objective distribution; still concentrated on pipeline, buyer plans, and carve-outs, with regional and AI themes missed. |
| Scope | Separate scope/methods artifacts include survey composition; reviewer noted imprecise wording in A's PE comparison. | Found survey size/date but omitted the 519 corporate / 181 PE split from scope and findings. | Received verified 519/181 context but still omitted both counts from generated qualifications/findings; Q2's evidence excerpt also omits its respondent-profile clause. |
| Source review | Two incorrect page anchors and three wording qualifications were identified. | All five finding values and cited pages checked out visually. | All six finding values and cited pages checked out visually; F1 omits B3's 12%/44% breakdown. |
| Existing trust/readiness evidence | Retained readiness is `not_publishable`; the separate nine-finding offline validator check was 0 / 1 / 8. | Validator was 1 / 4 / 0; the four rejected chart claims are visual false negatives, leaving one finding in the trust-filter output. | Validator was 4 / 2 / 0; both rejections are visual false negatives, leaving four findings in the trust-filter output. |
| Cost and downstream | Per-report token/cost attribution is unavailable in retained A artifacts. | One call cost $0.003919; FindingsPack/filter compatibility checked, downstream editorial/readiness not run. | One call cost $0.004346; FindingsPack/filter compatibility checked, downstream editorial/readiness not run; upstream A context cost is unavailable. |

The checks use different retained evidence surfaces and are not a head-to-head quality score. A is broader but has material grounding/readiness defects. B3/B4 are more directly source-anchored, but neither satisfies context completeness, breadth, and downstream-quality acceptance criteria.

### Validator and independent source checks

Counts below use the same unchanged validate_evidence_fidelity() and exclude_untrusted_evidence() code. A was rechecked offline against recovered canonical page spans; B1, B2, B3, and B4 ran the validator in the experiment. Counts are supported / unsupported / unresolved. This validator evaluates the FindingsPack claims and evidence; it does not semantically validate experiment-only sidecars, whose dimensions were checked during the source review.

| Source | A retained findings | B initial | B repeat | B2 | B3 | B4 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Reuters | 3 / 0 / 6 | 4 / 2 / 1 | 5 / 2 / 0 | — | — |
| Adjust | 8 / 3 / 1 | 7 / 0 / 0 | 6 / 1 / 0 | 7 / 1 / 0 | — |
| KPMG | 0 / 1 / 8 | — | — | — | 1 / 4 / 0 | 4 / 2 / 0 |

KPMG A's row covers its nine findings only and is distinct from the retained readiness artifact's 13 unsupported claims across evidence packs. All five B3 and all six B4 claim texts were visually checked against their cited original PDF pages. B3's four quantity rejections and B4's two rejections are visually confirmed false negatives. The unchanged trust filter retained one B3 and four B4 findings; neither set was forced through it.

Manual checks of the cited original PDF pages found validator false rejections in B: Reuters' −43% (p. 12) and −33% (p. 13) were marked quantity_not_entailed in both runs, despite matching the chart/page; the initial +74 / +61 / +56 / −52 platform finding (p. 21) was unresolved despite matching the chart. The unchanged Adjust validator rejected the B1 repeat session-length comparison and the B2 session-length finding (p. 28) for timeframe incompatibility. The original chart is titled 2024–2025 and labels the global values 10.04 minutes for 2024 and 9.6 for 2025; visual review confirms the B2 claim. Thus B2's 7/1/0 machine count is not evidence that one of its values is wrong. No validator rule was changed. The population omission in B1 remains a separate generation/content-quality defect.

The original A/B1 blind review used page text and could miss chart/layout context. The fresh four-set review inspected the original PDF and relevant charts visually, including p. 28; a separate direct visual check also covered the B2 cited pages. The anonymized KPMG review inspected retained A and B3 against the original PDF. The B4 review additionally inspected pp. 8, 15, 17, 19, 21, and 31 visually. These reviews assessed source fit and usefulness, not downstream editorial readiness.

## Usage, cost and runtime

The experiment's overall accounted-spend cap was **$0.20**; this remains below the user's $3 total budget. Each provider attempt carried a nominal reservation of at most $0.025344. The seven successful saved B calls used:

| Call | Input / output tokens | Estimated cost | Call wall time |
| --- | ---: | ---: | ---: |
| Reuters initial | 28,272 / 2,402 | $0.004028 | 16.995 s |
| Reuters repeat | 28,272 / 1,738 | $0.003696 | 15.843 s |
| Adjust initial | 12,823 / 2,063 | $0.002314 | 14.479 s |
| Adjust repeat | 12,823 / 2,004 | $0.002284 | 15.191 s |
| Adjust B2 | 13,293 / 2,889 | $0.002774 | 22.893 s |
| KPMG B3 | 23,387 / 3,161 | $0.003919 | 27.580 s |
| KPMG B4 | 24,446 / 3,802 | $0.004346 | 20.882 s |
| **Saved-call total** | **143,316 / 18,059** | **$0.023361** | **133.863 s** |

One earlier Reuters response returned without attributable usage; its full $0.025344 reservation is charged in the accounted upper bound. A failed Adjust provider attempt was recorded with zero input/output tokens and $0.00. Two request-construction failures occurred before any provider call and cost $0.00. Before B2, six provider attempts had a $0.037666 accounted upper bound. B2's preflight reserved $0.025344 against its **$0.04 incremental cap**; it completed at $0.002774, with no retry or provider failover. The post-B2 accounted upper bound was **$0.040440**. B3's preflight reserved $0.025344 against its **$0.04 incremental cap**; prior upper bound plus reservation was $0.065784. B3 completed at $0.003919 with no retry or provider failover. B4 used the same GPT-6 Luna temperature, reasoning effort, output limit, and single-provider request path as B3. Its pre-call reservation was $0.025344 against its **$0.04 incremental cap**; the projected total upper bound was $0.069703. One B4 provider call completed at $0.004346 with 24,446 input / 3,802 output tokens and 20.882 seconds wall time. No retry or provider failover occurred. Final actual/unknown accounted upper bound is **$0.048705**, including the earlier unknown Reuters usage; this is not an invoice amount. Across nine provider attempts, nominal reservations sum to $0.228096; that reservation sum is not the cap-accounting measure, which counts actual estimated usage plus a full reservation only for usage-unknown attempts. The final accounted bound remains below the $0.20 experiment cap and the user's $3 budget. B4's context was reused from retained artifacts; the cost of producing those upstream artifacts cannot be attributed from the retained A records. The local projection and extraction reuse made no provider call. The historical five-report total is not comparable to the seven direct B calls.

## Decision

**NO-GO for production integration, for the proposed hybrid as tested, and for expansion to other reports under this experiment.** B4 used existing context without another extraction stage and increased the unchanged trust-filter survivors from one to four. However, it still omitted the 519/181 respondent split from generated qualifications/findings, its qualification evidence excerpt was incomplete, and the slate's breadth did not materially improve over B3. One additional p. 21 carve-out objective finding is not enough to meet the breadth gate; both runs omitted regional and AI themes. Retained A was broader but has independent grounding/readiness defects. No downstream editorial/readiness stage ran. The hybrid does not meet the required qualification-completeness, breadth, and downstream-quality criteria. No integration point or follow-up experiment is recommended.

## Reproduction and retained evidence

Inputs and outputs are isolated under ignored tmp/source-anchored-findings-ab-20261014/. These saved B hashes are the canonical result_sha256 values in the JSON artifacts (computed over canonical JSON content, excluding that hash field):

```text
python scripts/experiments/run_source_anchored_findings_ab.py --preflight-only
python scripts/experiments/run_source_anchored_findings_ab.py
python scripts/experiments/run_source_anchored_findings_ab.py --repeat-once
python scripts/experiments/run_source_anchored_findings_ab.py --preflight-b2-adjust
python scripts/experiments/run_source_anchored_findings_ab.py --b2-adjust
python scripts/experiments/run_source_anchored_findings_ab.py --preflight-b3-kpmg
python scripts/experiments/run_source_anchored_findings_ab.py --b3-kpmg
python scripts/experiments/run_source_anchored_findings_ab.py --preflight-b4-kpmg
python scripts/experiments/run_source_anchored_findings_ab.py --b4-kpmg
pytest -q tests/_test_source_anchored_findings_ab/test_budget_guards.py
python -m py_compile scripts/experiments/run_source_anchored_findings_ab.py
python scripts/quality/build_prompt_fixture_corpus_baseline.py
python -m pytest -q tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py
python scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3
```

| Artifact | SHA-256 |
| --- | --- |
| reuters_run1.json | 21e77cb47dc40033b0b337ce6e6a933f29cf3110518244d0ed64bd8150b5d369 |
| reuters_run2.json | 0f4daa774c6710537a4ae7c8cab51faac423ea0b82a3b6f24f0c17011364df9f |
| adjust_run1.json | d9c15094678b64dbe8d8173c421ed138259f6bf68a3d14230d9a12fc350f54e2 |
| adjust_run2.json | 83be9d66e9657656d9fa377cb7b77d349cb70e3de4a9e90606c4faead7ab7b41 |
| adjust_b2.json (`result_sha256`) | 51601ab733b193479af6b36227b24a4a52f7a97ecaef4b39e7339e250d262f33 |
| kpmg_b3.json (`result_sha256`) | fb6db6afde889018b3f2423caca5e86c19ab2ec77b4623292c71b8201defab38 |
| kpmg_b4.json (`result_sha256`) | 254f1d5ee0c51db1b86bdbdaa1c984d3406d784964c24add3d0fe91f5983c261 |

B2 metadata: source-context SHA-256 `87e1c07c465cf0ff7bbc427498f91c4d9c36a97904f736fe996dbc1f9d8310a9`; prompt-content SHA-256 `6ceb9a36e05c7c54b36dca88673684f1726eaaf1f7b3c68729580aef24e8966a`; rendered-prompt SHA-256 `d0ce936fe94aaa95c65e6e96e79e5df5abc2ce173ad22c79aef632f8b149ff0c`; page-13 excerpt SHA-256 `8585fb735522a297fcb9d3f183b14c48f125a8afbb5944a59bc7113e71fd7aa9`. The B1 Adjust artifact file hashes remain `96b3630f55d9fcb22e8a2baba2e8c93a9df194bb70d7e9f6954fbe07d276af13` (run 1) and `43c60f8b6645351a3f09b4ae07ef3c565b67d0af1ee1f7b32860416ac8c4541e` (run 2). The eight pre-B2 budget records are byte-for-byte unchanged; the ledger SHA-256 changed from `89a8c13e179f4aafec210a581618324ccc6aa2172b8d718d52a0b2f68b16f1e5` to `38f31669136508266ca8a8414adaf60af62474990665f15e6319caf374d2645a` after one B2 record was appended.

B3 metadata: source-context SHA-256 `03ca9201eed8253f0a9e47edd7b3171a9652fb93f57e1374f3a37796ccc9b200`; prompt-content SHA-256 `d156612f3ea5e2d2d0ff514199b3fc31aa9b88d1556ba67a62b3a040b85bcf0e`; rendered-prompt SHA-256 `4a5a77169b7610a3aa077acf3bf1e101d07e2a8284da9b9ba7a50423aa5cecd7`. The saved result is `tmp/source-anchored-findings-ab-20261014/kpmg_b3.json`; the full source-page extraction is `tmp/source-anchored-findings-ab-20261014/kpmg_b3_source_pages.json`.

B4 metadata: reused source-context SHA-256 `03ca9201eed8253f0a9e47edd7b3171a9652fb93f57e1374f3a37796ccc9b200`; context projection SHA-256 `a07a37f047fdcfc32e8f2461abce8bcabd858b3a9a3e8a07d857473894aa205e`; prompt-content SHA-256 `4db98b7c42b299eb49a230bd462250bc47c149506a9ca68fc307884bd26ef347`; rendered-prompt SHA-256 `bd6abd9e490d1622d1756d91e48636b186468f853b1d3b812c40ce4c825bc99a`. The saved context is `tmp/source-anchored-findings-ab-20261014/kpmg_b4_context.json`; the result is `tmp/source-anchored-findings-ab-20261014/kpmg_b4.json`. Its preflight estimated 45,966 input tokens with margin; the one call used 24,446 input / 3,802 output tokens, cost $0.004346, and took 20.882 seconds. The budget ledger has nine provider attempts; its final accounted upper bound is $0.048705 and SHA-256 is `538ec673a2859d61c40d6560bc82fd34e5f6baca82224f12ed9a600789994bbc`. B1–B3 result hashes and retained source identities were rechecked unchanged before B4.

Focused final verification passed:

```text
.venv\Scripts\python.exe -m pytest -q tests/_test_source_anchored_findings_ab/test_budget_guards.py  # 20 passed
.venv\Scripts\python.exe -m pytest -q tests/test_prompt_service.py tests/test_prompt_dry_run_validation.py tests/test_prompt_fixture_corpus_regression.py  # 78 passed
.venv\Scripts\python.exe -m py_compile scripts/experiments/run_source_anchored_findings_ab.py  # passed
.venv\Scripts\ruff.exe check scripts/experiments/run_source_anchored_findings_ab.py tests/_test_source_anchored_findings_ab/test_budget_guards.py  # passed
.venv\Scripts\ruff.exe format --check scripts/experiments/run_source_anchored_findings_ab.py tests/_test_source_anchored_findings_ab/test_budget_guards.py  # passed
.venv\Scripts\python.exe scripts/ci/check_prompt_fixture_regression.py --baseline docs/quality/prompt_fixture_corpus_baseline_2026-04-26.json --config src/config/app.yaml --iterations 3  # passed
```

The prompt dry-run suite first exposed a missing B2 test fixture; the fixture was added without runtime execution settings and all 78 prompt tests then passed. The full pipeline, downstream editorial/readiness stages, and publication were not run. No remaining failures were observed in the focused checks above.

B3 additions were checked with `--preflight-b3-kpmg` and one `--b3-kpmg` run. B4 additions passed `--preflight-b4-kpmg` without credential resolution or a provider call; `--b4-kpmg` then made exactly one GPT-6 Luna call with no automatic retry or provider failover. The focused budget/context suite passed 20 tests, the prompt service/dry-run/fixture suite passed 78 tests, Ruff check and format passed, Python compilation passed, and the prompt fixture regression gate passed. No production pipeline, downstream editorial/readiness stage, or publication was run.

The historical A findings.json / evidence_fidelity.json file SHA-256 values are 88441bcc52ba442a5c91867352d57597fd4bcf9810dd9d83791ce665f9c0b43e / 8a5264634eece9da3d1646a84a5699ca84abea7bd67fa3ab0ebd753b963432e7 for Reuters, and a5ff080266f90956f7704d79b4d38a4fb87baafe804145074251d76eed5cb07e / adeeb2200164ffc02065670360f81343b29f7eef31b481cb0b68d7a15d5cd634 for Adjust, under tmp/verify2-replay-9eeb47aa.
