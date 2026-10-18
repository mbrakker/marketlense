# MarketLense — Verified Claims Step 1 Shortlisting Evidence

**Date:** 2026-10-18
**Branch:** `codex/fix-retained-insight-evidence-validation`
**Step 0 starting SHA:** `7fcd71bd6b17157d0d4246f8da73ca585532f9ab`
**Step 1 implementation SHA:** `cb5c7396`
**Step 1 correction SHA:** `4596d6dd`
**Frozen manifest SHA-256:** `744de32ef0d200ced0904b4f44868084b29e4d923f75e78ca106c3c3549d22a7`
**Retained producer:** `469c13c15d0d654f60c04a84bb97bf7ee44d1de0`

## Scope and decision

Step 1 changes only deterministic insight shortlisting and its existing fallback/cache boundary. It does not add model calls, change evidence validation, create canonical verified-claim persistence, factualise visuals, publish, or alter editorial authority.

Overall verdict: **PARTIAL**. The implementation and provider-free retained-artifact safeguards pass. The exact retained artifacts prove preservation and deterministic ordering/eligibility, but they do not provide raw pre-selector model pools or independent repeated runs, so this record does not claim a live selection-quality or repeatability improvement.

## Implemented behavior

- Ranking now uses retained evidence binding strength, existing relevance/metric/novelty/score fields, physical pages/spans, and editorial-plan theme priority/coverage. No keyword-based business-relevance score was added.
- Final-stage records are resolved before ranking: a matching stable ID keeps final editorial wording, while candidate metric, evidence ID/text, physical pages, and evidence spans restore the retained factual binding.
- Semantic deduplication is conservative: shared evidence IDs or excerpts alone never establish equivalence. It requires an explicit stable-ID/source match or identical public proposition with compatible protected metric bindings. Different conclusions, metrics, populations/cohorts, periods, or observation/forecast statuses remain distinct.
- Missing evidence IDs and page-less finding fallbacks are not promoted. An explicit `evidence_fidelity.results` set admits only `supported` findings; absent fidelity data retains the existing findings-pack behavior.
- Fallback pools first cover uncovered editorial themes, then fill from eligible alternatives while excluding source IDs already covered by the current candidate roster. Existing IDs, evidence IDs, pages, spans, and protected metric fields are copied from the winning retained record.
- Artifact cache metadata now carries `evidence_backed_shortlisting:1`; the cache matcher rejects the previous `stable_id_unique_selection:2` version explicitly.
- Two independent insights remain a valid generated artifact family result; the downstream report-payload contract still rejects fewer than five populated insight slots unless the family is explicitly abstained.

## Frozen-five before/after replay (corrected selector)

Replay input was the local retained real-report artifact set under `tmp/frozen20-next5-systemic-fix-20260930/frozen-reliability-xxcdkw0r/members/ias-first-attempt-7z7shs6j/output`, using each report’s `artifacts.json`, `findings.json`, and `evidence_fidelity.json`. No provider or publication endpoint was called.

| Report | Before selected IDs | After selected IDs | Count | Theme coverage | Eligible fidelity-approved fallback | Ledger result |
|---|---|---|---:|---|---:|---|
| Activate | `activate-outlook-revenue-models`, `activate-super-user-time-and-spending`, `activate-digital-assistant-access-forecast`, `activate-platform-specific-web-video`, `activate-news-discovery-and-direct-visits`, `activate-ecommerce-capability-stack`, `activate-podcasting-engagement-rationale` | `activate-digital-assistant-access-forecast`, `activate-outlook-revenue-models`, `activate-super-user-time-and-spending`, `activate-platform-specific-web-video`, `activate-news-discovery-and-direct-visits`, `activate-ecommerce-capability-stack`, `activate-podcasting-engagement-rationale` | 7→7 | 7/7→7/7 | 0 | Correction replay preserves the roster and bindings while the evidence-backed ranking leads with the digital-assistant forecast; no unsupported fallback promoted. |
| Capgemini | `value-fairness-transparency`, `online-deal-searching`, `consumer-control-of-ai`, `human-support-remains-important`, `digital-assistants-engagement-recommendation` | `online-deal-searching`, `value-fairness-transparency`, `consumer-control-of-ai`, `human-support-remains-important`, `digital-assistants-engagement-recommendation` | 5→5 | 5/5→5/5 | 2 | Lead moved to the quantified deal-searching finding; value/fairness and AI/human-support coverage retained; the two eligible findings were already represented. |
| KPMG | `buyer-standalone-platform-access`, `execution-governance-value-creation`, `agentic-ai-deal-workflows`, `buyer-appetite-execution-approaches`, `strategic-focus-capability-building` | `execution-governance-value-creation`, `strategic-focus-capability-building`, `agentic-ai-deal-workflows`, `buyer-appetite-execution-approaches`, `buyer-standalone-platform-access` | 5→5 | 5/5→5/5 | 1 | Concrete execution/governance and strategic-focus findings lead; the one eligible fallback was not needed and was not forced into a full, covered roster. |
| Adjust | `cross-channel-measurement-recommendation`, `gaming-benchmark-coverage`, `ecommerce-benchmark-coverage`, `finance-benchmark-coverage`, `ai-marketing-applications`, `benchmark-methodology-context` | `gaming-benchmark-coverage`, `cross-channel-measurement-recommendation`, `ecommerce-benchmark-coverage`, `finance-benchmark-coverage`, `ai-marketing-applications`, `benchmark-methodology-context` | 6→6 | 6/6→6/6 | 0 | Gaming’s distinct metric coverage leads; cross-channel, vertical, AI, and methodology coverage retained; no unapproved fallback was available. |
| Reuters Institute | `ai-search-platform-relationships`, `distinctive-content-response`, `video-platform-discovery-shift`, `newsroom-ai-uses-and-oversight`, `subscription-membership-priority`, `ai-browsers-adaptable-content` | unchanged | 6→6 | 6/6→6/6 | 0 | No ordering or identity change; all existing themes and protected bindings preserved. |

Aggregate result: **29→29** selected insights; **29/29** retained evidence IDs, physical-page bindings, and evidence-span bindings before and after; protected evidence/metric payloads changed **0** times; selected theme coverage remained **29/29 theme slots**. The retained selected rosters had zero repeated evidence IDs and zero repeated normalized texts before or after. Synthetic tests removed one same-proposition paraphrase while retaining same-page distinct metrics and changed cohort/period/status variants.

The fallback audit covered **39 retained findings**. Explicit fidelity approval was available for **3** findings total (Capgemini 2, KPMG 1; Activate, Adjust, and Reuters 0); unsupported or unapproved findings were excluded rather than used to manufacture coverage. This is a measurable fail-closed improvement over source-order fallback, but the sparse approval set limits observed fallback replacement gains.

## Correction pass against the Step 1 baseline

The correction replay used the same retained post-selection artifacts and compared with the prior Step 1 ledger. Selected roster sets remained unchanged: 29→29 insights, 29/29 theme slots, zero repeated evidence IDs, and zero repeated normalized public texts. Activate’s deterministic lead order changed from `activate-super-user-time-and-spending` to `activate-digital-assistant-access-forecast`; Capgemini, KPMG, Adjust, and Reuters retained their prior leads. This is an ordering correction, not evidence loss or a live-quality claim.

The fallback audit now distinguishes availability from uncovered need. The same three fidelity-approved findings remain available in principle (Capgemini 2, KPMG 1), but Capgemini’s two are already covered by the candidate roster, so the uncovered replacement pool contains only KPMG’s `outlook-execution-environment`; no unsupported finding is promoted. Synthetic regressions confirm that same-source different propositions survive, exact public duplicates across evidence IDs collapse, and protected metric differences survive.

The two-insight narrow-plan case remains `generated` at the artifact-family layer without fabricated padding. A separate orchestrator regression confirms that a report payload with two generated insights still fails the existing five-slot completeness gate, so the short artifact is not silently publication-ready.

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

- `python -m pytest -q tests/test_artifact_insight_shortlisting.py tests/test_artifact_generator.py tests/test_artifact_normalization_source_fidelity.py` — **130 passed**.
- `python -m pytest -q tests/test_report_analysis_orchestrator_decomposition.py tests/test_a21_historical_semantic_residuals.py` — **17 passed**.
- `python -m pytest -q tests/test_report_regeneration_generator.py` — **90 passed**.
- `python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_public_report_quality_gate.py tests/test_render_service_public_advisory.py tests/test_render_service_public_prose.py` — **115 passed**.
- `python scripts/ci/check_public_report_quality.py` — passed.
- `python scripts/ci/check_ruff_lint.py` — passed.
- `python scripts/ci/check_formatting.py` — passed.
- `python scripts/ci/check_forbidden_patching.py` — passed.
- `python scripts/ci/check_repository_hygiene.py` — passed.
- `git diff --check` — passed on the final correction/documentation diff.

No paid provider calls, database writes, WordPress/publication writes, raw-PDF additions, raw model-response additions, visual factualisation, or canonical verified-claim persistence were performed. Step 2 remains unstarted.

## Remaining limitations

- The provider-free replay starts from retained post-selection `insights_final` rosters, not raw pre-selector model output; it proves deterministic re-selection, preservation, and fail-closed fallback behavior, not live candidate-recall lift.
- No three-run current-HEAD generation or fixed-input semantic-validator baseline was run; model repeatability remains open.
- The retained evidence-fidelity packs approve only three finding fallbacks. Their sparse/contradictory historical support decisions require future classification, without weakening fail-closed behavior.
- No anchored human usefulness/distinctiveness rubric exists yet. That remains outside Step 1 and is not inferred from ordering changes.
- The correction replay still begins from retained post-selection rosters; it cannot establish the prevalence of stable-ID collisions or candidate recall in fresh model output.
- Retained findings, DocMap, and artifact files are local and hash-pinned by the Step 0 record; portability requires the same retained artifact pack.

**Step 2 status:** not started.
