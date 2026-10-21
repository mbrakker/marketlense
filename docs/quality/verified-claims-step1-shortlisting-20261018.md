# MarketLense — Verified Claims Step 1 Shortlisting Evidence

**Date:** 2026-10-18
**Branch:** `codex/fix-retained-insight-evidence-validation`
**Step 0 starting SHA:** `7fcd71bd6b17157d0d4246f8da73ca585532f9ab`
**Step 1 implementation SHA:** `cb5c7396`
**Step 1 correction SHA:** `4596d6dd`
**Step 1 P1 factual-integrity correction:** `a7fc47cd`
**Step 1 P2 provenance/numeric correction:** `25e479d7`
**Step 1 final provenance-consistency correction:** `2ce49d69`
**Frozen manifest SHA-256:** `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`
**Retained producer:** `469c13c15d0d654f60c04a84bb97bf7ee44d1de0`

## Scope and decision

Step 1 changes only deterministic insight shortlisting and its existing fallback/cache boundary. It does not add model calls, change evidence validation, create canonical verified-claim persistence, factualise visuals, publish, or alter editorial authority.

Overall verdict: **PARTIAL**. The implementation and provider-free retained-artifact safeguards pass. The exact retained artifacts prove preservation and deterministic ordering/eligibility, but they do not provide raw pre-selector model pools or independent repeated runs, so this record does not claim a live selection-quality or repeatability improvement.

## Implemented behavior

- Ranking now uses retained evidence binding strength, existing relevance/metric/novelty/score fields, physical pages/spans, and editorial-plan theme priority/coverage. No keyword-based business-relevance score was added.
- Final-stage records are resolved before ranking: a matching stable ID keeps final editorial wording, while candidate metric, evidence ID/text, physical pages, and evidence spans restore the retained factual binding.
- Semantic deduplication is conservative: shared evidence IDs or excerpts alone never establish equivalence. It requires an identical public proposition with compatible protected metric bindings; stable IDs are used to restore and resolve authoritative facts, never as a proposition-equivalence shortcut. Different conclusions, metrics, populations/cohorts, periods, or observation/forecast statuses remain distinct.
- Missing evidence IDs and page-less finding fallbacks are not promoted. An explicit `evidence_fidelity.results` set admits only `supported` findings; absent fidelity data retains the existing findings-pack behavior.
- Fallback pools first cover uncovered editorial themes, then fill from eligible alternatives while excluding source IDs already covered by the current candidate roster. Existing IDs, evidence IDs, pages, spans, and protected metric fields are copied from the winning retained record.
- Same stable IDs are now grouped by compatible source identity and protected metric bindings before any editorial score is used. Conflicting evidence IDs, values, cohorts, periods, or observation statuses fail closed; equivalent source-consistent representations may still use the strongest existing retained signals.
- Same stable IDs also fail closed when their physical page/span bindings are contradictory. Identical excerpts, overlapping spans, and source-consistent multi-page representations remain eligible; unrelated excerpts or disjoint physical bindings cannot be resolved by editorial score.
- Final editorial wording remains authoritative, but the complete candidate protected metric binding is restored, including empty fields. Final-only metric, forecast, cohort, denominator, timeframe, geography, evidence, page, or span additions are removed; a matching final rewrite without a reliable candidate binding is rejected.
- Artifact cache metadata now carries `evidence_backed_shortlisting:5`; the cache matcher rejects the prior `evidence_backed_shortlisting:4`, `evidence_backed_shortlisting:3`, `evidence_backed_shortlisting:2`, `evidence_backed_shortlisting:1`, and `stable_id_unique_selection:2` versions.
- Two independent insights remain a valid generated artifact family result; the downstream report-payload contract still rejects fewer than five populated insight slots unless the family is explicitly abstained.

## Frozen-five before/after replay (initial Step 1 baseline)

Replay input was the local retained real-report artifact set under `tmp/frozen20-next5-systemic-fix-20260930/frozen-reliability-xxcdkw0r/members/ias-first-attempt-7z7shs6j/output`, using each report’s `artifacts.json`, `findings.json`, and `evidence_fidelity.json`. No provider or publication endpoint was called.

| Report | Before selected IDs | After selected IDs | Count | Theme coverage | Eligible fidelity-approved fallback | Ledger result |
|---|---|---|---:|---|---:|---|
| Activate | `activate-outlook-revenue-models`, `activate-super-user-time-and-spending`, `activate-digital-assistant-access-forecast`, `activate-platform-specific-web-video`, `activate-news-discovery-and-direct-visits`, `activate-ecommerce-capability-stack`, `activate-podcasting-engagement-rationale` | `activate-digital-assistant-access-forecast`, `activate-outlook-revenue-models`, `activate-super-user-time-and-spending`, `activate-platform-specific-web-video`, `activate-news-discovery-and-direct-visits`, `activate-ecommerce-capability-stack`, `activate-podcasting-engagement-rationale` | 7→7 | 7/7→7/7 | 0 | Correction replay preserves the roster and bindings while the evidence-backed ranking leads with the digital-assistant forecast; no unsupported fallback promoted. |
| Capgemini | `value-fairness-transparency`, `online-deal-searching`, `consumer-control-of-ai`, `human-support-remains-important`, `digital-assistants-engagement-recommendation` | `online-deal-searching`, `value-fairness-transparency`, `consumer-control-of-ai`, `human-support-remains-important`, `digital-assistants-engagement-recommendation` | 5→5 | 5/5→5/5 | 2 | Lead moved to the quantified deal-searching finding; value/fairness and AI/human-support coverage retained; the two eligible findings were already represented. |
| KPMG | `buyer-standalone-platform-access`, `execution-governance-value-creation`, `agentic-ai-deal-workflows`, `buyer-appetite-execution-approaches`, `strategic-focus-capability-building` | `execution-governance-value-creation`, `strategic-focus-capability-building`, `agentic-ai-deal-workflows`, `buyer-appetite-execution-approaches`, `buyer-standalone-platform-access` | 5→5 | 5/5→5/5 | 1 | Concrete execution/governance and strategic-focus findings lead; the one eligible fallback was not needed and was not forced into a full, covered roster. |
| Adjust | `cross-channel-measurement-recommendation`, `gaming-benchmark-coverage`, `ecommerce-benchmark-coverage`, `finance-benchmark-coverage`, `ai-marketing-applications`, `benchmark-methodology-context` | `gaming-benchmark-coverage`, `cross-channel-measurement-recommendation`, `ecommerce-benchmark-coverage`, `finance-benchmark-coverage`, `ai-marketing-applications`, `benchmark-methodology-context` | 6→6 | 6/6→6/6 | 0 | Gaming’s distinct metric coverage leads; cross-channel, vertical, AI, and methodology coverage retained; no unapproved fallback was available. |
| Reuters Institute | `ai-search-platform-relationships`, `distinctive-content-response`, `video-platform-discovery-shift`, `newsroom-ai-uses-and-oversight`, `subscription-membership-priority`, `ai-browsers-adaptable-content` | unchanged | 6→6 | 6/6→6/6 | 0 | No ordering or identity change; all existing themes and protected bindings preserved. |

Aggregate result for the initial Step 1 selector comparison: **29→29** selected insights; **29/29** retained evidence IDs, physical-page bindings, and evidence-span bindings before and after; protected evidence/metric payloads changed **0** times; selected theme coverage remained **29/29 theme slots**. The retained selected rosters had zero repeated evidence IDs and zero repeated normalized texts before or after. Synthetic tests removed one same-proposition paraphrase while retaining same-page distinct metrics and changed cohort/period/status variants.

The fallback audit covered **39 retained findings**. Explicit fidelity approval was available for **3** findings total (Capgemini 2, KPMG 1; Activate, Adjust, and Reuters 0); unsupported or unapproved findings were excluded rather than used to manufacture coverage. This is a measurable fail-closed improvement over source-order fallback, but the sparse approval set limits observed fallback replacement gains.

## P1 factual-integrity correction pass against the Step 1 baseline

The provider-free replay loaded the exact retained Capgemini, Activate, KPMG, Reuters Institute, and Adjust artifacts and compared the current selector with the prior Step 1 baseline at `f13eaf8a`. It did not call a provider or publish. The per-report ledger is:

| Report | Step 1 baseline → corrected IDs | Count / themes | Binding and wording result | Fallback result |
|---|---|---:|---|---|
| Activate | `activate-digital-assistant-access-forecast`, `activate-outlook-revenue-models`, `activate-super-user-time-and-spending`, `activate-platform-specific-web-video`, `activate-news-discovery-and-direct-visits`, `activate-ecommerce-capability-stack`, `activate-podcasting-engagement-rationale` → unchanged | 7→7 / 7→7 | Stable IDs, final wording, evidence IDs/pages/spans, and candidate-supported forecast fields unchanged | 0→0 |
| Capgemini | `online-deal-searching`, `value-fairness-transparency`, `consumer-control-of-ai`, `human-support-remains-important`, `digital-assistants-engagement-recommendation` → `value-fairness-transparency`, `online-deal-searching`, `consumer-control-of-ai`, `human-support-remains-important`, `digital-assistants-engagement-recommendation` | 5→5 / 5→5 | Same IDs and wording; `online-deal-searching` now clears final-only metric fields because its retained candidate has no reliable metric binding. Evidence ID/pages/spans remain unchanged | 2→2 |
| KPMG | `execution-governance-value-creation`, `strategic-focus-capability-building`, `agentic-ai-deal-workflows`, `buyer-appetite-execution-approaches`, `buyer-standalone-platform-access` → unchanged | 5→5 / 5→5 | No output identity, wording, or protected-binding change | 1→1 |
| Adjust | `gaming-benchmark-coverage`, `cross-channel-measurement-recommendation`, `ecommerce-benchmark-coverage`, `finance-benchmark-coverage`, `ai-marketing-applications`, `benchmark-methodology-context` → unchanged | 6→6 / 6→6 | No output identity, wording, or protected-binding change | 0→0 |
| Reuters Institute | `ai-search-platform-relationships`, `distinctive-content-response`, `video-platform-discovery-shift`, `newsroom-ai-uses-and-oversight`, `subscription-membership-priority`, `ai-browsers-adaptable-content` → unchanged | 6→6 / 6→6 | No output identity, wording, or protected-binding change | 0→0 |

Aggregate corrected replay: **29→29** selected insights, the same 29-ID set, **29/29** editorial-plan theme slots, zero repeated evidence IDs, zero repeated normalized public texts, and no evidence ID/page/span changes. The only baseline-to-corrected protected-payload change was Capgemini’s unsupported final-only metric removal; the current output preserves the candidate-authoritative empty binding. The only ordering change is the resulting Capgemini lead change, which is a direct factual-integrity correction rather than an unrelated ranking change. The same three fidelity-approved findings remain available in principle (Capgemini 2, KPMG 1); only KPMG’s `outlook-execution-environment` remains uncovered, and no unsupported finding is promoted.

Focused regressions confirm that conflicting same-ID evidence or protected metric bindings are excluded rather than score-resolved, source-consistent duplicate representations remain valid, final wording survives factual restoration, final-only forecast/cohort/denominator/timeframe/geography fields are removed, and unbound final rewrites fail closed.

The two-insight narrow-plan case remains `generated` at the artifact-family layer without fabricated padding. A separate orchestrator regression confirms that a report payload with two generated insights still fails the existing five-slot completeness gate, so the short artifact is not silently publication-ready.

## P2 provenance and numeric-content correction pass

Commit `25e479d7` compares the current selector with the latest corrected Step 1 baseline at `a7fc47cd` using the exact retained Capgemini, Activate, KPMG, Reuters Institute, and Adjust artifacts. It does not claim a live selection-quality improvement: the retained inputs are already post-selection rosters. The per-report ledger is:

| Report | Selected IDs / wording | Physical and protected bindings | Theme coverage | Fallback alternatives | P2 result |
|---|---|---|---:|---|---|
| Activate | unchanged, 7→7; wording unchanged | pages/spans/metric bindings unchanged | 7/7→7/7 | 0→0 | No provenance ambiguity in the retained candidate roster. |
| Capgemini | unchanged, 5→5; wording unchanged | pages/spans/metric bindings unchanged | 5/5→5/5 | 2 available→2 available | No new change. The corrected replay still omits the unsupported final-only metric binding. |
| KPMG | unchanged, 5→5; wording unchanged | pages/spans/metric bindings unchanged | 5/5→5/5 | `outlook-execution-environment`→unchanged | No provenance ambiguity; the eligible alternative remains available but is not forced. |
| Reuters Institute | unchanged, 6→6; wording unchanged | pages/spans/metric bindings unchanged | 6/6→6/6 | 0→0 | No provenance ambiguity in the retained candidate roster. |
| Adjust | unchanged, 6→6; wording unchanged | pages/spans/metric bindings unchanged | 6/6→6/6 | 0→0 | No provenance ambiguity in the retained candidate roster. |

Aggregate P2 replay: **29→29** selected insights, **29/29** IDs and final wordings unchanged, **29/29** physical page/span bindings unchanged, zero protected-payload changes, zero duplicate evidence IDs, and **29/29** theme slots retained. The frozen cohort contains no duplicate stable-ID candidate groups, so the new provenance guard is exercised by focused synthetic regressions rather than a live-frozen collision.

Numeric-content check: on corrected replay, all five reports still derive **0 metric-spine and 0 key-figure items** from the retained candidate-authoritative selections, matching the latest corrected baseline. The retained Capgemini post-selection artifact contains a 62% `online-deal-searching` metric spine/key figure, but its retained candidate binding has empty protected metric fields; the source prose alone is not promoted into a structured metric. The focused regression confirms that a supported candidate value survives into `metric_spine`, while final-only timeframe/geography values are removed. No safe existing authoritative structured binding was available for the real Capgemini candidate, so fail-closed behavior is retained rather than enriched speculatively.

New regressions cover disjoint page/excerpt/span conflicts, disjoint same-page spans, overlapping alternative spans, legitimate identical multi-page excerpts, cache invalidation from selection version `:2` to `:3`, and downstream numeric preservation. This P2 correction is **PARTIAL** only because the retained replay cannot measure fresh candidate recall, live collision prevalence, or repeated-run stability; it introduces no frozen-cohort regression and does not start Step 2.

## Final provenance-consistency correction

Commit `2ce49d69` compares the selector with baseline `953555f` on the exact retained frozen-five artifacts. Concrete span bindings are now checked before shared top-level evidence text; source-pack/section identity is checked before excerpt equality; incomplete spans remain eligible only when their available location/source metadata is consistent. Cache identity advanced from `evidence_backed_shortlisting:3` to `evidence_backed_shortlisting:4`.

| Report | Selected IDs / wording | Theme coverage | Evidence IDs/pages/spans | Protected metrics | Metric spine / key figures | Fallback | Difference vs `953555f` |
|---|---|---:|---|---|---:|---|---|
| Capgemini | unchanged, 5→5 | 5/5→5/5 | unchanged | unchanged | 0→0 / 0→0 | unchanged | None |
| Activate | unchanged, 7→7 | 7/7→7/7 | unchanged | unchanged | 0→0 / 0→0 | unchanged | None |
| KPMG | unchanged, 5→5 | 5/5→5/5 | unchanged | unchanged | 0→0 / 0→0 | `outlook-execution-environment` unchanged | None |
| Reuters Institute | unchanged, 6→6 | 6/6→6/6 | unchanged | unchanged | 0→0 / 0→0 | unchanged | None |
| Adjust | unchanged, 6→6 | 6/6→6/6 | unchanged | unchanged | 0→0 / 0→0 | unchanged | None |

Aggregate final replay: **29→29** selected identities and editorial wordings unchanged; theme coverage, evidence IDs, physical pages/spans, protected metric bindings, metric-spine/key-figure counts, fallback availability, validation outcomes, and publication-readiness safeguards were unchanged. The retained cohort has no duplicate stable-ID candidate groups, so the new defect is demonstrated by focused regressions rather than a live-frozen collision. No provider calls or publication writes were made. Overall Step 1 remains **PARTIAL** because retained post-selection replay cannot establish fresh live selection effectiveness or repeated-run stability; no further Step 1 corrective work is indicated by this verification, and Step 2 remains unstarted.

## Final P1 factual/editorial-integrity correction

The latest correction closes two independent validation/selection gaps without changing the Step 2 or publication boundaries:

- A finding's generated `text` is no longer indexed as its own direct evidence. Findings require an independent `evidence`, `quote`, `quote_text`, `snippet`, or `excerpt`, or an independently bound PDF source span during evidence-fidelity validation. `quote_candidates.text` remains source quotation text, and `quote_text` aliases remain supported.
- Duplicate public prose with different protected metric signatures is never resolved by editorial score. Matching stable IDs can use a distinct, same-binding source-backed candidate formulation; when no safe formulation exists, the conflicting prose group is omitted. Candidate-only conflicts fail closed as well. Exact public propositions with compatible protected bindings still deduplicate, while distinct same-source propositions remain separate.

Provider-free replay of the exact retained five-report pack at the current working tree selected **29 insights** with **29/29 editorial-plan theme slots**, zero repeated normalized public texts, and zero repeated evidence IDs:

| Report | Selected count | Theme slots | Duplicate text / evidence IDs | Difference from recorded `953555f` baseline |
|---|---:|---:|---|---|
| Capgemini | 5 | 5/5 | 0 / 0 | No identity, wording, page/span, metric, or fallback change |
| Activate | 7 | 7/7 | 0 / 0 | No change |
| KPMG | 5 | 5/5 | 0 / 0 | No change |
| Reuters Institute | 6 | 6/6 | 0 / 0 | No change |
| Adjust | 6 | 6/6 | 0 / 0 | No change |

The retained Step 0 manifest remains the exact five-report, five-hash cohort. This replay read retained artifacts only; it made no provider calls, publication writes, canonical claim writes, or PDF changes. The cohort contains no same-ID collision or duplicate-metric candidate, so the new behavior is measured by focused adversarial regressions rather than a claim of fresh live-selection improvement. The 15-case / 39-variant Step 0 reference fixture remains unchanged and was not dispatched through Step 2 in this correction.

Focused regressions now cover generated-finding self-support, independent source-page support, source-quotation preservation, duplicate final wording with distinct metric bindings, candidate-only duplicate wording, stable-ID/factual restoration, and existing public-quality blocking. The two-insight artifact-family behavior remains generated without padding; the existing report-payload completeness gate remains authoritative.

Current verification batches pass with **108 claim-validation**, **88 artifact-selection/normalization**, **218 regeneration/contract**, **133 combined public-editorial-quality and Step 2**, and **2,423 contract/schema/prompt** tests. Targeted Ruff check and format checks pass for both changed production modules and the directly edited regression modules. The repository type gate remains blocked only by 11 pre-existing unbaselined errors in `verified_claims_visual_generator.py`; neither changed production module adds a type error. Step 1 remains **PARTIAL**: the retained-artifact replay proves no frozen-cohort regression and fail-closed behavior, but not live pre-selector recall, collision prevalence, or repeated-run selection stability.

## Fifteen frozen reference cases

The following review distinguishes an editorial omission or intentionally broad qualitative selection from a factual error. “No factual regression” means the retained selected record did not promote the held numeric/provenance mutation; it does not mean an unresolved source binding became verified.

| Case / physical page | Step 0 source-verified issue | Retained selected editorial identity | Step 1 assessment |
|---|---|---|---|
| ACT-001 / p.5 | Forecast `$302B`, 4.1% CAGR, scope and 2017E–2021E must stay qualified. | `activate-outlook-revenue-models` | Retained as broad outlook context; no forecast numeric upgrade. No factual regression. |
| ACT-002 / p.15 | Reject inverted 61%/34% time-versus-spend relation and preserve cohort labels. | `activate-super-user-time-and-spending` | Broad Super Users comparison retained; the rejected inverted tuple was not promoted. No factual regression. |
| ACT-003 / p.17 | Reject inverted 64%/47% time-versus-spend relation and preserve cohort labels. | `activate-super-user-time-and-spending` | Same guarded broad selection; no inverted numeric tuple promoted. No factual regression. |
| ACT-004 / p.53 | Platform/cohort/metric/population tuple requires exact visual binding. | `activate-platform-specific-web-video` | Broad platform comparison retained; exact unsupported numeric tuple remains unpromoted and fail-closed. |
| CAP-001 / p.11 | Preserve reported switching reasons and survey scope. | `value-fairness-transparency` (`value-fairness-quality`) | Exact findings binding retained with scoped qualitative wording. No factual regression. |
| CAP-002 / p.11 | Do not expand the N=12,000 survey percentages to the whole population. | `value-fairness-transparency` (`value-fairness-quality`) | Numeric population-expansion mutation not promoted; retained qualitative selection remains review-scoped. |
| CAP-003 / pp.21–22 | Keep deal-searching and non-essential-spending motives separate. | `online-deal-searching` | Retained only the supported 62% deal-searching proposition; the merged motive transfer was not promoted. No factual regression. |
| CAP-004 / p.34 | Do not attach chatbot denominator/willingness-to-pay values to another population. | `digital-assistants-engagement-recommendation` | Qualitative recommendation retained; unbound denominator and willingness-to-pay values omitted. |
| KPM-001 / p.15 | Keep private-equity/corporate cohorts, means, and forward-looking status bound. | `buyer-appetite-execution-approaches` | Broad cohort contrast retained; exact unbound means were not promoted. |
| KPM-002 / pp.12–13 | Preserve qualitative capability thesis; reject numeric/realized-outcome upgrades. | `strategic-focus-capability-building` | Qualitative strategic thesis retained; no unsupported numeric or realized outcome promoted. |
| KPM-003 / p.19 | Carve-out increase is an expectation over 12–24 months, not a realized outcome. | omitted | Deliberate editorial omission/held alternative; no factual error. |
| REU-001 / p.12 | Search decline is a publisher forecast over three years, not an observed result. | `ai-search-platform-relationships` | Broad risk mechanism retained; the unbound 40% forecast was not promoted. |
| REU-002 / p.13 | Keep platform, referral measure, signs, and both comparison periods exact. | `video-platform-discovery-shift` | Broad discovery shift retained; exact unbound period/channel values were not promoted. |
| REU-003 / pp.12–13 | Google Search year-on-year geography/period alternative requires exact binding. | omitted | Explicit editorial omission/held alternative; no factual error. |
| ADJ-001 / p.19 | Keep gaming category, install/session measures, direction, and 2024–2025 period bound. | `gaming-benchmark-coverage` | Broad benchmark coverage retained; no churn/conversion inference was added. No factual regression. |

No Step 0 unresolved reference case was promoted by the fallback path. The source-verified examples remain distinct from editorial omission, and the retained final-claim validation/readiness safeguards were not changed.

## Verification

Passed:

- `python -m pytest -q tests/test_artifact_insight_shortlisting.py tests/test_artifact_normalization_source_fidelity.py` — **35 passed** after the P2 correction.
- `python -m pytest -q tests/test_artifact_insight_shortlisting.py tests/test_artifact_normalization_source_fidelity.py` — **39 passed** after the final provenance correction.
- `python -m pytest -q tests/test_artifact_generator.py` — **109 passed**.
- `python -m pytest -q tests/test_report_regeneration_generator.py` — **90 passed**.
- `python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_render_service_public_advisory.py tests/test_render_service_public_prose.py` — **115 passed**.
- `python -m pytest -q tests/test_report_analysis_orchestrator_decomposition.py tests/test_a21_historical_semantic_residuals.py` — **17 passed**.
- `python -m pytest -q tests/test_claim_validation_source_pages.py tests/test_claim_validation_source_excerpts.py` — **13 passed**.
- `python -m pytest -q tests/test_retained_claim_grounding.py` — **23 passed**.
- `python -m pytest -q tests/test_publish_readiness_gate.py` — **49 passed**.
- `python -m pytest -q tests/test_report_queue_publication.py` — **2 passed**.
- `python -m pytest -q tests/test_source_identity_provenance.py` — **8 passed**.
- `python -m ruff check src/generators/artifact_normalization.py tests/test_artifact_insight_shortlisting.py tests/_test_artifact_generator/cases_05_advisory_and_claim_ledger.py` and `python -m ruff format --check ...` — passed.
- Provider-free replay of the exact frozen five-report cohort — **29/29 IDs and theme slots retained**, no evidence ID/page/span loss, one intentional protected-metric correction.

The full repository CI gates were not rerun in this correction slice; no provider or publication writes were made.

No paid provider calls, database writes, WordPress/publication writes, raw-PDF additions, raw model-response additions, visual factualisation, or canonical verified-claim persistence were performed. Step 2 remains unstarted.

## Remaining limitations

- The provider-free replay starts from retained post-selection `insights_final` rosters, not raw pre-selector model output; it proves deterministic re-selection, preservation, and fail-closed fallback behavior, not live candidate-recall lift.
- No three-run current-HEAD generation or fixed-input semantic-validator baseline was run; model repeatability remains open.
- The retained evidence-fidelity packs approve only three finding fallbacks. Their sparse/contradictory historical support decisions require future classification, without weakening fail-closed behavior.
- No anchored human usefulness/distinctiveness rubric exists yet. That remains outside Step 1 and is not inferred from ordering changes.
- The correction replay still begins from retained post-selection rosters; it cannot establish the prevalence of stable-ID collisions or candidate recall in fresh model output.
- Retained findings, DocMap, and artifact files are local and hash-pinned by the Step 0 record; portability requires the same retained artifact pack.

**Subsequent Step 2 handoff (2026-10-18):** A shadow-only visual claim
correction and independent-verification boundary is implemented on this branch.
The provider-free frozen-five replay preserved the 29 selected identities,
wording, themes, pages, spans, and protected bindings. A bounded GPT-6 Luna
High replay of the exact 15 reference cases / 39 variants verified 38, left
one wrong-page case unresolved, and exposed one unsupported-metric false accept;
it did not change retained artifacts or establish fresh candidate recall. The
separate evidence record is
`docs/quality/verified-claims-step2-visual-shadow-20261018.md`; Step 2 remains
**PARTIAL** because of the false accept and lack of human editorial review;
Step 3 remains unstarted.

## Exact frozen ten-report E18 acceptance replay — 2026-10-21

The exact frozen ten-report cohort (DoubleVerify, KPMG, Reuters Institute, Adjust, Algolia, Bain & Company, Criteo, Deloitte, Emplifi, and StackAdapt Inc.) was run in isolated fresh state. All ten source identities were admitted and reached terminal workflow records; 59 retained Step 1 candidates were available to the live Step 2 shadow replay. The source manifest verified all ten expected PDF SHA-256 values. No canonical claim, readiness override, publication, or WordPress write occurred.

The first isolated run produced 385 provider calls, 4,116,807 input tokens, 829,903 output tokens, estimated cost $0.968736, and 7,752.966 seconds. Two reports ended with downstream validation failures (Reuters `expert_comment`/metric-label relationship and Criteo public-grounding); their retained selection artifacts remain included and are not silently counted as clean publication outcomes. The explicit Step 2 replay evaluated 59/59 retained claims: 58 verified first pass, 0 verified after retry, 1 failed verification, 0 unresolved, and 0 skipped.

A second shared-batch run terminated all ten reports (8 `ias_canary_timeout`, 2 validation failures) and reused one run directory, so it is not a valid independent selection repetition. A clean supplemental isolated rerun completed the five missing reports (KPMG, Reuters Institute, Algolia, Criteo and Deloitte): 168 provider calls, 1,896,381 input tokens, 352,004 output tokens, estimated cost $0.431351, 2,929.71 seconds, and 5/5 terminal validation-pass records. Its selected-ID overlap with the first run was 0 for KPMG, Reuters, Algolia and Deloitte and 1/9 for Criteo; the other five reports still lack a clean independent repetition. The evidence package deliberately does not convert failed or reused-run artifacts into identity-overlap claims. The independent reviewer assessed 58 claims and recorded 57 approved, 1 revision-required (Algolia population qualifier), and 1 unresolved (the failed Criteo claim). This is claim-level LLM review, not P6 human acceptance.

No deterministic selector, deduplication, fallback-theme or cache defect was reproduced in the current run. The existing selector version remains `evidence_backed_shortlisting:5`, with focused regression coverage for stable IDs, semantic proposition preservation, provenance conflicts, fallback coverage and cache invalidation. The observed Criteo qualifier/timeframe drift originated during candidate construction/metric binding and was correctly rejected downstream; a selector-only patch was not justified. The deep-root Windows policy-matrix path correction and explicit-ten reviewer-roster validation were supporting execution/evaluation fixes, not ranking or evidence-safety changes.

The complete ledger, source hashes, per-report selection records, Step 2 attempts, independent scorecard and repeatability limitations are in [`docs/quality/verified-claims-ten-report-acceptance-202610/`](verified-claims-ten-report-acceptance-202610/). Step 1/E18 remains **PARTIAL**: the first live cohort is complete, but two clean independent Step 1 evaluations per eligible report and a source-recall oracle were not established. Step 3 and P6 remain open.
