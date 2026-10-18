# MarketLense — Verified Claims: Step 0 Baseline

Audit date: 2026-10-18
Branch: codex/fix-retained-insight-evidence-validation
Starting SHA: ea7419ab55643c7197a721839459802fcdf1645c
Scope: baseline evidence only. No production logic, prompt, configuration, quality-gate, service, database, validator, publication or external-write change was made.

## Outcome

The frozen-cohort source and retained-run checks pass: the five original PDFs match the frozen manifest, and the retained current five-report workflow result has 5/5 admitted, 5/5 validation pass, 5/5 publication-readiness pass, zero operator interventions and zero publication writes. All five stopped at awaiting_review as intended.

Overall Step 0 correction status: PARTIAL. The source truth and fixture coverage pass, but three exact current retained bindings remain explicitly unresolved and the retained findings/doc-map/artifact files are local-only ignored dependencies. The baseline does not close E18 or authorize Steps 1–7. E18 remains Active because the evidence is a source and output baseline, not a repeated current-HEAD generation experiment, a fixed-input validator repeatability baseline, or a human editorial-value study.

The correction at starting SHA ea7419ab55643c7197a721839459802fcdf1645c separates independent source-reference IDs from persisted findings/doc-map IDs and editorial IDs. It contains 39 deterministic candidate variants across the 15 cases: 15 supported, 23 unsupported and 1 unresolved. Four cases have an exact current persisted binding, eight have partial bindings, and three remain unresolved by policy; none is silently promoted through an editorial ID.

The machine-readable source cases and retained artifact identities are in verified-claims-step0-reference-cases-20261018.json. This report intentionally summarizes evidence; it does not copy raw PDFs, prompts or model responses.

## Cohort and retained identity

The canonical manifest is docs/quality/reliability-cohort-20261001-next-five/frozen_cohort.json with SHA-256 744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7. The before and after result hashes are:

- before_cohort_result.json: b6802e8519ee972548c750bfd323309385600acde1e5ab01953ccb567a5802fb
- cohort_result.json: 043bfd0f86dec3880a7c5c9850958ded6d832a49429c8e1043b8ac8f133d6839

| Report | Frozen source MD5 | Frozen source SHA-256 |
| --- | --- | --- |
| Capgemini Research Institute | 81af3890cd84ece81ef16e1aabda8027 | 612f362e1bff3c307e4db4aed38414f7b3ac85dd5cba4742ef78625cd225ef3e |
| Activate | cbb6e7df67412186b8bc094a424ac890 | 5f960886c6d6ee8cf355b4d469a6c1bc12080cd85351b4cb457c8565ae9dd4f2 |
| KPMG | 2acb4a56e14add5d7717f34c378f9091 | a97f4478327c50e9815102de229ad35bc22c3dce8f88cd49a75027e16ea08589 |
| Reuters Institute | 4b763ae2286ca69fe8acb63b17508dfb | f746133b3d66479b716e61cbaf3771b45b035fdf7801251511cc7ba510413a52 |
| Adjust | b638414df0b1fccea1cd8a93eaf8f5aa | ffbaadb6a91b99aec5cfacdbf8b1059046b0fcdeff49fac1eb3a3edfe9f0c7d3 |

The retained current run is frozen-reliability-xxcdkw0r / ias-first-attempt-7z7shs6j at producer SHA 469c13c15d0d654f60c04a84bb97bf7ee44d1de0. The historical accepted systematic-fixes comparison is anchored to 0ec3cdff841e16df7044f6645fe8379a464f41ca. The historical before run used 365c342ba3ffe2cb3b2c8a90fb71938ae9738cf6. These are distinct producer versions and are not a controlled paired causal experiment.

## Report-level evidence flow

The retained current output root is tmp/frozen20-next5-systemic-fix-20260930/frozen-reliability-xxcdkw0r/members/ias-first-attempt-7z7shs6j/output. Each row traces report context and findings through evidence fidelity, final artifacts, retained-claim validation and publication readiness. The full per-file SHA-256 inventory is in the JSON reference set.

| Report | Current report ID | Findings | Candidate-level unsupported rejected by fidelity | Final insights | Topics | Key figures / chart cards | Validation / readiness | Retained unsupported / unresolved |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | --- |
| Capgemini | cohort-81af3890cd84ece81ef1 | 6 | 8 | 5 | 11 | 1 / 1 | pass / pass | 0 / 0 |
| Activate | cohort-cbb6e7df67412186b8bc | 6 | 13 | 7 | 12 | 0 / 0 | pass / pass | 0 / 0 |
| KPMG | cohort-2acb4a56e14add5d7717 | 6 | 10 | 5 | 12 | 0 / 0 | pass / pass | 0 / 0 |
| Adjust | cohort-b638414df0b1fccea1cd | 12 | 17 | 6 | 11 | 0 / 0 | pass / pass | 0 / 0 |
| Reuters Institute | cohort-4b763ae2286ca69fe8ac | 9 | 15 | 6 | 13 | 0 / 0 | pass / pass | 0 / 0 |

The 63 candidate-level unsupported results are fail-closed evidence-fidelity rejections, not 63 published factual errors. The evidence-fidelity artifacts therefore report not_publishable at candidate-pack level, while retained_claim_validation reports zero unsupported and zero unresolved factual claims for every retained final artifact. The cohort-level terminal result is awaiting_review, not published.

The current five final artifacts contain Insights, Summary, Expert View and distribution-copy fields. The current selected insight IDs are:

- Capgemini: value-fairness-transparency; online-deal-searching; consumer-control-of-ai; human-support-remains-important; digital-assistants-engagement-recommendation.
- Activate: activate-outlook-revenue-models; activate-super-user-time-and-spending; activate-digital-assistant-access-forecast; activate-platform-specific-web-video; activate-news-discovery-and-direct-visits; activate-ecommerce-capability-stack; activate-podcasting-engagement-rationale.
- KPMG: buyer-standalone-platform-access; execution-governance-value-creation; agentic-ai-deal-workflows; buyer-appetite-execution-approaches; strategic-focus-capability-building.
- Adjust: cross-channel-measurement-recommendation; gaming-benchmark-coverage; ecommerce-benchmark-coverage; finance-benchmark-coverage; ai-marketing-applications; benchmark-methodology-context.
- Reuters: ai-search-platform-relationships; distinctive-content-response; video-platform-discovery-shift; newsroom-ai-uses-and-oversight; subscription-membership-priority; ai-browsers-adaptable-content.

## Factual reference audit

Fifteen source-reference cases were checked against the original rendered pages. All fifteen source propositions are independently confirmed. Three are demonstrated historical defect or false-accept cases: the Activate video inversion, the Activate audio inversion, and the Capgemini 49% motive transfer. The remaining cases distinguish preserved facts, safe editorial omission, source-binding requirements, population/denominator requirements and forecast/observation boundaries.

| Report | Independently confirmed source cases | Main baseline finding |
| --- | --- | --- |
| Activate | 302B forecast; 61%/34% video; 64%/47% audio; platform-specific creator chart | Forecast status and cohort/metric labels are protected. Historical video/audio inversions are rejected. The page-53 source-binding replay rejects platform, metric, cohort and population swaps. |
| Capgemini | 74% lower-price and 71% undisclosed-reduction switching reasons; N=12,000 population; separate 49% and 48% behavior categories; N=3,125 weekly chatbot-user denominator | The switching mechanisms are preserved. The historical 49% motive transfer is a real semantic false accept. Population and chatbot denominators require explicit binding before numeric reuse. |
| KPMG | 5.2 corporate versus 7.3 PE planned deals; qualitative portfolio separation/carve-out thesis; 50/44/6 carve-out expectation | Comparative and qualitative findings must retain cohort and expectation qualifiers; no realized-deal claim is established. |
| Reuters Institute | −43% three-year search-referral expectation; observed channel/period referral figures; Google year-on-year referral figures | Forecast and measured referral traffic are distinct. Current finding text preserves the forecast qualifier; exact numbers require period, channel, geography and observation-status binding. |
| Adjust | Strategy sessions +57% with flat installs; casino +22% installs and −5% sessions; slots +46% installs and −5% sessions | The exact install/session tuple is preserved in findings. The selected public insight is broader; no churn or conversion conclusion is supported by these figures alone. |

The detailed case records contain source page, printed-page, evidence ID, source meaning, qualifiers, observed candidate/editorial state, defect classification and expected verification outcome. Page references are physical PDF pages unless a printed page is shown.

### Identity and fixture contract

The JSON reference set is the executable audit record for the correction. `source_reference_ids` refer only to the independent source-reference document. `persisted_findings_ids` and `persisted_doc_map_ids` are checked against the retained `findings.json` and `doc_map.json`; `canonical_evidence_ids` is their union only. `editorial_ids` are checked against `artifacts.json` and are never treated as evidence. Physical pages are one-based, printed pages are retained when verified, and `zero_based_library_index` is derived as physical page minus one.

Every case has source truth for the metric, population, denominator, geography, period and observation/forecast status, plus valid, mutated or ambiguous candidates with an expected `supported`, `unsupported` or `unresolved` result, correction and promotion decision. The exact candidate counts are 15 supported, 23 unsupported and 1 unresolved across 39 variants; all 15 top-level cases have both positive and non-positive variants.

The persisted artifact catalog records 15 local-only `findings.json`, `doc_map.json` and `artifacts.json` dependencies with SHA-256 hashes and ID fields. The frozen manifest hash is 744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7. These local files are reproducibility inputs, not committed raw artifacts; missing or incompatible files must remain unresolved rather than being regenerated or inferred.

### Preserved, changed, duplicated, misinterpreted, omitted and rejected

- Preserved: source-supported switching, forecast, comparative, qualitative and app-growth propositions remain in findings or source-linked editorial themes. Current retained validation found zero unsupported or unresolved final factual claims.
- Changed: the Activate chart value is rendered as approximately 300B in current finding/editorial text while the chart displays 302B; this is source-consistent rounding only when the forecast and period remain attached. Several exact source metrics are generalized into broader selected insights.
- Duplicated: no current exact-five final factual duplicate was confirmed; the public-quality evaluator reports repeated-syntax value 0.0 for all five. The separate October Reuters diagnostic found one supported candidate duplicated an initiative already in final copy; that diagnostic is not treated as a current-five duplicate rate.
- Misinterpreted: the historical Activate video/audio cohort and metric inversions and the historical Capgemini 49% motive transfer are confirmed failure examples. They were rejected or later guarded; they are not current published claims.
- Omitted: current selected text does not repeat several independently confirmed exact alternatives, including Adjust casino/slots percentages, KPMG 5.2/7.3 means, Reuters Google referral figures, and some Capgemini denominators. These are editorial coverage/selection observations, not factual errors.
- Rejected: 63 current candidate-level unsupported results were excluded by evidence fidelity. This is a useful failure-closed baseline and must not be counted as published-error volume.

## Editorial and quality baseline

All five current public-editorial-quality artifacts pass with zero hard failures. Their retained measurements are:

| Report | Role diversity | Average insight words | Repeated syntax | Source-note completeness | Action specificity | Figure-to-evidence linkage |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Capgemini | 2 | 16.00 | 0.00 | 1.00 | 1.00 | 0.00 |
| Activate | 3 | 17.57 | 0.00 | 1.00 | 1.00 | 0.00 |
| KPMG | 3 | 14.80 | 0.00 | 1.00 | 1.00 | 0.00 |
| Adjust | 3 | 17.17 | 0.00 | 1.00 | 1.00 | 0.00 |
| Reuters Institute | 4 | 14.83 | 0.00 | 1.00 | 1.00 | 0.00 |

Validation warnings remain non-blocking and are retained in the per-report validation files: Capgemini 9, Activate 4, KPMG 3, Adjust 2 and Reuters 4. The baseline records them rather than treating pass as absence of editorial follow-up. No anchored human usefulness or distinctive-insight score exists in the retained artifacts.

## Performance and reliability baseline

The exact frozen-five result records cohort-level usage only. Report-level calls, tokens, cost and wall time are unavailable in cohort_result.json and must not be reverse-attributed.

| Measure | Before run, producer 365c342b | Current retained run, producer 469c13c | Difference |
| --- | ---: | ---: | ---: |
| Readiness passes | 3/5 | 5/5 | +2 reports |
| Provider calls | 193 | 222 | +29 |
| Input tokens | 1,804,228 | 2,129,080 | +324,852 |
| Output tokens | 393,169 | 492,778 | +99,609 |
| Estimated cost | 0.366703 USD | 0.435683 USD | +0.068980 USD |
| Duration | 2,809.573 s | 3,714.445 s | +904.872 s |
| Operator interventions | 0 | 0 | unchanged |

The accepted systematic-fixes record at baseline commit 0ec3cdff records 215 calls, 1,879,211 input tokens, 399,097 output tokens, 0.441918 USD estimated cost, 1,201.19 seconds, 6 automatic repairs and 26 file-search calls. Its previous comparator used 184 calls, 1,696,787 input tokens, 299,363 output tokens, 0.389098 USD, 1,083.927 seconds and zero repairs. That comparison changed concurrency from 3 to 5 and is explicitly non-causal. It is retained as context, not a measured verified-claims improvement.

The October 9 autonomous-MVP comparison records no confirmed factual errors in its paired retained-HTML review but a failed editorial acceptance decision because lead specificity declined in four reports and Reuters was mixed. It has no reproducible numeric human-value rubric. This baseline preserves that limitation.

## Steps 1–7 comparison protocol

The following protocol is the reusable comparison contract for later verified-claims work. No later step was executed in this baseline.

1. Identity freeze: bind every run to the exact five-member manifest, source MD5/SHA-256, source identity IDs, producer SHA, prompt/model/policy/configuration hashes, cache mode and publication-disabled state.
2. Evidence ledger: compare source-bound evidence IDs and immutable tuples of page, subject, cohort, denominator, metric label, value, unit, direction, period, geography and observation status. Recheck source pages for every changed tuple.
3. Deterministic replay: with identical persisted inputs and code, compare hashes, evidence IDs, tuples, validation findings, selected IDs and retained-claim ledgers. Prose byte equality is not required; semantic identity and protected fields are.
4. Stochastic generation: run at least three independent isolated generations per report when live measurement is justified, with cache reuse disabled or isolated. Keep producer/configuration changes separate from stochastic variation.
5. Outcome measures: record false accepts, false rejects, unsupported and unresolved claims, protected-field fidelity, important-topic retention, selected insight identity, duplication, distinctiveness/usefulness review, validation/readiness, repairs/promotions, calls, tokens, cost, wall time and provenance completeness.
6. Surface audit: inspect findings, candidates, final Insights, Summary, Key Figures, Expert View, distribution copy, final HTML and retained-claim validation. Attribute the first loss stage and distinguish omitted alternatives from factual defects.
7. Decision gate: accept a change only when the exact source identity and comparable producer/configuration are pinned, genuine factual failures decrease without new false accepts, important evidence is not lost, readiness/publication safeguards remain intact, and time/cost regressions are justified. Otherwise retain the baseline and record the open hypothesis.

## Acceptance checks and open evidence gaps

Passed in Step 0:

- exact requested branch and starting SHA verified; starting worktree was clean;
- frozen manifest SHA verified;
- all five source paths existed and matched manifest MD5 and computed SHA-256;
- original source pages for all 15 reference cases were checked visually;
- current retained workflow result: 5/5 admitted, validation pass and readiness pass;
- publication disabled, zero publication writes and zero operator interventions;
- 15 cases, 39 candidate variants and explicit supported/unsupported/unresolved expected outcomes validated against the retained artifact IDs;
- source-reference, persisted-evidence and editorial identity semantics validated, with 4 exact, 8 partial and 3 unresolved current bindings;
- all 15 retained artifact-catalog hashes and the frozen manifest hash reverified;
- no raw PDF, credential, prompt or raw model response added to the commit.

Verification executed for this correction:

- `python -m pytest -q tests/test_pdf_text_quality.py tests/test_report_analysis_source_evidence.py tests/test_artifact_evidence_binding.py tests/test_validation_doc_map_evidence.py tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py` — 112 passed in 10.40s.
- `python scripts/ci/check_backlog_source.py` — passed: 33 active register items, 33 detailed active sections, zero duplicate/missing/orphan/title-mismatch issues.
- `python scripts/ci/check_documentation.py --check-generated` — passed.
- `python scripts/ci/check_repository_hygiene.py` — passed.
- `git diff --check` — passed.
- Read-only JSON identity/fixture, retained-artifact SHA-256, frozen-manifest SHA-256 and PyMuPDF page-marker checks — passed: 15 cases, 38 candidates, all 15 catalog hashes, manifest `744de32e…d22a7`, and all required page markers present. These checks made no provider calls or external writes.

Open:

- no three-run current-HEAD generation baseline per report;
- no three-run fixed-input semantic-validator baseline;
- no anchored or blinded human usefulness/distinctiveness rubric;
- no report-level attribution for current calls, tokens, cost, duration or repair counts;
- the 63 candidate-level evidence-fidelity rejections need future classification into genuine unsupported claims versus false rejections, without weakening fail-closed behavior;
- the exact current persisted binding remains unavailable for CAP-003, CAP-004 and REU-003; their source truth and editorial context are retained, but their canonical evidence arrays are intentionally empty and promotion is held;
- current findings, doc-map and editorial artifact files are ignored local retained evidence; the committed record contains IDs, hashes and summaries, not the raw artifacts, so portability requires the same retained files or an explicitly compatible artifact pack;
- Steps 1–7 of the verified-claims implementation remain unstarted.

## Canonical backlog evidence

E18 remains Active. The new evidence is recorded in docs/backlog/E-evidence.md and CONSOLIDATED_TODO.md. The existing E18.1 audit, docs/quality/e18-1-provider-free-findings-audit-20261013.md, and the source reference set, docs/quality/docmap-discovery-ab-20261014/source-reference-findings.md, remain supporting evidence; they are not replaced or treated as current repeated-run proof.
