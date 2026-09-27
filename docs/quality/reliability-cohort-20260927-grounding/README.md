# Retained grounding architecture proof — 2026-09-27

## Decision

**Not proven; do not mark the retained-grounding architecture complete.** The initial exact tested source revision reached `awaiting_review` for 0/20 reports and report-level publish readiness for 0/20. Source review confirmed deterministic and semantic false positives among the regressions, while other failures were genuine malformed output or unavailable grounding results. The acceptance target of zero known-valid claims falsely rejected was not met. No retained-claim grounding rule was changed to improve cohort pass rate.

Phase 3 semantic-overlap analysis was not performed because Phase 1 did not pass sufficiently to justify an architectural decision. `validation/semantic.py` was not removed or narrowed.

## Geography mutation follow-up

The initial run at `8a05e2d25a7bc23192b297324fc40df7e4ba37a9` failed two evidence-compatibility mutation tests. `compare_protected_fact_texts("Reach in Europe…", "Reach in the United States…")` correctly returned geography `unknown`, but the alternative-evidence ranker treated every non-`incompatible` dimension as compatible and returned the candidate. That allowed an unproven geography to re-enter deterministic repair selection.

The narrow correction keeps geography `unknown` and excludes an alternative when both the claim and candidate evidence explicitly contain values for the same protected dimension but deterministic equivalence remains unknown. A missing evidence dimension remains eligible as broad context for a repair that can rewrite the claim. The positive quarantine fallback still passes. A regression test asserts both parts of that behavior. Focused result: `tests/test_evidence_compatibility.py tests/contracts/test_protected_facts.py` — 33 passed.

This source change occurred after the full-cohort SHA above. The initial run remains the pre-fix baseline; the evidence pack must be updated with the clean post-fix SHA and a new frozen cohort run before it can describe final implementation behavior.

## Run identity and controls

- Implementation SHA: `8a05e2d25a7bc23192b297324fc40df7e4ba37a9` (`main` at run time).
- Command: `python scripts/quality/run_frozen_reliability_cohort.py --runs-root tmp/retained-grounding-cohort-20260927 --max-duration 7200`.
- Frozen input: 20/20 admitted; run used isolated fresh state; publication was disabled; no operator intervention, manual repair, source substitution, or manual artifact reuse was recorded. The runner reports bounded automatic recovery enabled; this is the benchmark workflow setting.
- The run snapshot [`frozen_cohort.json`](frozen_cohort.json) is semantically equal to the canonical [`frozen_reliability_cohort_20.json`](../../../scripts/quality/frozen_reliability_cohort_20.json). Their file SHA-256 values differ because the run rewrote JSON formatting: snapshot `4da8f4112f37bf880254fe85dc8784752fda089f0cac59f3989520370ae12286`, canonical manifest `21a9a1b995d10b5add412780d96930ecc29bafd082907ecbf0741c80be841a07`.
- Every source PDF's MD5 matched its frozen manifest value. Per-input verified MD5 and SHA-256 values are recorded in [`frozen_inputs_sha256.csv`](frozen_inputs_sha256.csv).
- Authoritative result: [`cohort_result.json`](cohort_result.json), SHA-256 `9be431aed086136bfc1428e311dbdf8976192e2ccc1970b3e6033db970ce8e65`. The report-by-report previous/current comparison is in [`report_outcomes_comparison.csv`](report_outcomes_comparison.csv); final grounding lineage and readiness hashes are in [`retained_grounding_readiness.csv`](retained_grounding_readiness.csv).

## Cohort result and prior comparison

| Measure | 2026-09-20 full cohort | 2026-09-27 current HEAD | Change |
| --- | ---: | ---: | ---: |
| `awaiting_review` | 9/20 (45%) | 0/20 (0%) | -9 reports |
| workflow publish-ready | 9/20 (45%) | 0/20 (0%) | -9 reports |
| typed terminal outcomes | 20/20 | 20/20 | unchanged |
| operator interventions | 0 | 0 | unchanged |
| provider calls | 644 | 574 | -70 |
| input tokens | 5,299,676 | 5,900,816 | +601,140 |
| output tokens | 699,778 | 823,384 | +123,606 |
| estimated validation cost | USD 1.869133 | USD 0.998643 | -USD 0.870490 |
| wall-clock runtime | 5,424.234s | 5,131.846s | -292.388s |

The lower estimated cost and call count did not correspond to improved report outcomes. Per-report provider usage attribution and response-reuse/cache rate are unavailable in the retained cohort result. The run's grounding work used report-level batched executions (21 `report_vs/validate/grounding` events); 68 legacy `report_vs/validate/semantic` events were also recorded. Provider-side cached input tokens are not treated as response reuse. No rate is inferred from those counts.

The current failure Pareto is `publish_readiness_failed` 13, `validation_failed` 3, `soft_copy_claim_provenance_bindings_incomplete` 2, `card_tldr_compact_invalid` 1, and `insight_safe_removal_no_replacement` 1. One Criteo readiness artifact says `pass`, but the full report run still failed later on an invalid compact TLDR; it is not counted as a publish-ready report.

### Per-report outcome changes

The linked CSV contains all 20 previous and current outcomes. The prior full-cohort successes are the nine reports below. Every one failed in the current run:

| Report | Previous | Current | Forensic classification and root cause |
| --- | --- | --- | --- |
| Activate | `awaiting_review` | `publish_readiness_failed` | **False positive plus grounding execution gap.** `soft_copy:linkedin_post:143e1ae27fc34464` treats the 2018 report-title year as a fact timeframe and rejects it against the linked retail forecast range 2017–2021. Those years describe the edition and forecast interval, respectively. The linked DocMap page points to the section heading; the source PDF's following page contains the retail finding, so provenance page alignment is also imperfect. The retained package was missing at readiness; candidate claims also had `semantic_result_missing` results despite source support for reviewed examples. |
| DoubleVerify | `awaiting_review` | `validation_failed` | **True positive terminal failure.** The final insights `apac-authentic-viewable-rate` and `apac-fraud-sivt-violation-rate` have identical text and both link to `section-2`; the duplicate-insight rule correctly blocks them. Separately, retained candidate `insight:apac-attention-index:metric` is a **false positive**: the source row explicitly pairs APAC Attention Index with 109 in Q1 2026, but nearby table values cause `index` to be treated as `count`. |
| Reuters Institute | `awaiting_review` | `publish_readiness_failed` | **False positive plus grounding execution gap.** The supported referral-decline/publisher-interest claim is rejected because attribution extraction compares claim `the` with evidence `it`; those are articles/pronouns, not source actors. The PDF reports Facebook/X referral declines and separate publisher plans for video and AI distribution (PDF pp. 18–19). Readiness also finds no final retained package; other source-supported candidate claims have `semantic_result_missing`. |
| Merchant Risk Council | `awaiting_review` | `publish_readiness_failed` | **True positive output defect.** The three retained key-figure fields are malformed label/context concatenations instead of values. Their exact linked evidence gives survey coverage of 1,200+ merchants, 43% real-time-payments acceptance, and 63% agentic-payment exploration/plans. Readiness records 0 unsupported and 3 unresolved factual claims. |
| Bain & Company | `awaiting_review` | `publish_readiness_failed` | **Two false positives and one output defect.** For the 52% born-tech claim, the linked source quote also says “top 20 gainers”; number 20 is incorrectly assigned percent units and conflicts with a matched claim. The `asset-light` wording is present in the one-page source, but quote matching rejects it. A separate key-figure value omits 52%, which is a genuine structured-output defect. The final package is missing, so readiness cannot consume the candidate's counts. |
| Deloitte | `awaiting_review` | `publish_readiness_failed` | **Unresolved grounding execution/mapping, not evidence insufficiency.** Candidate `summary_claim:2` says retailer-owned assistants can use first-party signals while retaining recommendation/customer-interaction/optimization control. Linked `onsite-control` evidence on p. 4 states those points. The candidate result is `semantic_result_missing`; readiness sees no final package. |
| Emplifi | `awaiting_review` | `publish_readiness_failed` | **False positives plus grounding execution gap.** The qualified U.S./U.K. sample claim is rejected because attribution extraction compares `the` with `it`; the PDF's methods section identifies the qualified U.S./U.K. social-platform-user sample. A LinkedIn sentence using 2026 as the report edition is rejected against a 2023 comparison baseline, although they have different roles. The U.S./U.K. sentence remained intact, so this is not a segmentation failure. Other source-supported candidates have `semantic_result_missing`; no final package was materialized. |
| Qualtrics | `awaiting_review` | `validation_failed` | **True positive output defect.** `key_figure:1:figure` contains “Employees experiencing significant change Employees Employees Employees” and omits 72%, while its linked `intro-change-and-connection` evidence gives 72%. A second figure is duplicated narrative rather than a clean key-figure value. The exact grounding rule is rejecting malformed figure fields, not a claim with the correct value. |
| StackAdapt Inc. | `awaiting_review` | `publish_readiness_failed` | **Unresolved grounding execution/mapping, not evidence insufficiency.** `soft_copy:summary:223afe87ac71aecf` describes multi-touchpoint retail discovery and relevance in the right moment/environment. Linked `retail-discovery-everywhere` page 3 supports that framing. The candidate is `semantic_result_missing`; readiness sees no final package. A separate figure's source chart value is not present in its linked DocMap evidence, a genuine evidence-binding gap. |

The **11 confirmed false-positive validator decisions** counted in the review consist of those on Activate, DoubleVerify, and Reuters; two Bain records; three Emplifi records (the duplicated summary and soft-copy records count separately); the semantic KPMG canary; and two Algolia factual attribution records. This count excludes unadjudicated quote failures in reports that were already failing and excludes the true-positive duplicate insight and malformed key figures.

### Recent closure canaries

| Canary | Earlier result | Current result | Classification |
| --- | --- | --- | --- |
| KPMG, closure canary at `0144111c8ef43f2ccc74e4fdaa1c00754ff591c4` | `awaiting_review` | `validation_failed`, grounding on `soft_copy:linkedin_post:f3d2f75ece0eca48` | **False positive.** Claim: “If evaluating a carve-out, MarketLense recommends including separation complexity in the strategic and investment case.” Linked KPMG DocMap section `portfolio-simplification-as-a-value-creation-strategy`, p. 18, says carve-outs are subject to execution complexity. The claim is an explicitly MarketLense-authored recommendation based on that evidence; it does not attribute the recommendation to KPMG. |
| Algolia, closure canary at `0144111c8ef43f2ccc74e4fdaa1c00754ff591c4` | `awaiting_review` | `publish_readiness_failed`, 2 unsupported factual claims | **False positives.** Two identical summary surfaces are rejected because `the report` is not parsed as the respondent attribution; the evidence itself says respondents included CIO, CTO, and CDO officers. A separate nonfactual LinkedIn framing also compares the 2026 report title with 2025/2024 underlying findings as if they were the same timeframe. |
| Criteo, closure canary at `009bb1c6fc139c55610b9b457f888a8180c81427` | Passed with an 18-word TLDR | `card_tldr_compact_invalid` | **True positive output defect.** The current accepted artifact has an empty compact TLDR. Its standalone retained factual package is supported and readiness passes, but the report run fails on the missing public copy. |
| Adjust, fresh canary at `bb693e95b36453bb2111a5ba1b0f1bc83a816c0b` | Passed | `soft_copy_claim_provenance_bindings_incomplete` | **Blocking provenance gap.** Six summary claims lack complete evidence bindings; the first begins “Mobile app trends for 2026 vary by vertical…”. No exact retained evidence ID is attached to those claims, so a source-truth judgment cannot be made from the candidate package. |

### Other reports that were already failing the prior full cohort

These rows did not newly regress from a full-cohort success. Their current primary blocker is recorded without treating an unadjudicated candidate decision as proven false. The `retained_grounding_readiness.csv` ledger contains each exact rule detail and candidate count.

| Report | Current primary blocker | Root-cause status |
| --- | --- | --- |
| Capgemini Research Institute | `insight_safe_removal_no_replacement` before readiness | Pipeline does not retain a claim-level failure diagnostic for the removal/replacement decision. Candidate grounding also contains an unsupported numeric/relationship result on the methodology claim; that is not established as the pipeline's primary cause. Root cause remains unresolved. |
| Bigcommerce | Readiness `package_missing`; 4 unsupported and 14 unresolved factual candidates | Candidate fields include a malformed wallet metric whose linked evidence states 40%; the field also includes the survey date range, which appears in the extracted quantity set. That candidate needs a dedicated source-bound repair, but the report's retained final package is missing and readiness correctly blocks it. |
| DHL eCommerce | Readiness `package_missing`; 1 unsupported and 20 unresolved factual candidates | The unsupported checkout-tactics claim links to evidence about shopper abandonment and available options, not the claimed business-reported tactics. This is insufficient exact linked evidence for that claim; do not classify the attribution check as a false positive. Other candidate results lack semantic results. |
| Robeco | `soft_copy_claim_provenance_bindings_incomplete` during artifact generation | Required summary evidence bindings were not retained. Without exact linked evidence IDs, factual adjudication is unavailable. |
| SimilarWeb | Readiness `package_missing`; 0 unsupported and 23 unresolved factual candidates | Candidate LinkedIn quote check fails on the “sales signal” wording; that exact source passage was not adjudicated in this cohort review. Other candidates have no accepted semantic result. |
| Contentstack | Readiness `package_missing`; 0 unsupported and 9 unresolved factual candidates | Candidate factual claims are unresolved with `semantic_result_missing`; the final current package was not materialized. |
| Mintel | Readiness `package_missing`; 4 unsupported and 14 unresolved factual candidates | Four quote-match decisions involving the “maxxing” wording remain source-unadjudicated; additional claims have no accepted semantic result. The missing package blocks readiness independently of whether those quote decisions are valid. |

## Mutation probes

The two focused test commands below exercised supported controls and mutated claims. All selected cases passed; the result is limited to the explicit fixtures and does not counter the cohort false positives above.

| Mutation | Supported control and rejected mutation | Expected authoritative layer | Evidence |
| --- | --- | --- | --- |
| Numeric value | Equivalent value passes; 42% → 43% fails | Quantity / deterministic evidence fidelity | `test_evidence_fidelity_rejects_a_generated_finding_with_the_wrong_number`; `test_numeric_grounding_rejects_changed_quantity_primitives` |
| Unit, currency, magnitude | Canonical displays match; unit/currency/magnitude changes fail | Quantity semantics | `test_currency_magnitude_forms_match`; `test_financial_magnitude_abbreviations_match_their_canonical_forms`; `test_evidence_fidelity_rejects_wrong_unit_and_recovers_exact_page_provenance` |
| Timeframe | Same period passes; 2025 → 2026 or wrong period fails | Protected facts / period relationship | `test_evidence_fidelity_rejects_a_matching_value_with_the_wrong_period`; `test_public_numeric_validation_keeps_value_unit_and_period_mismatches_blocking` |
| Direction | Relevant direction in mixed evidence passes; explicit inversion fails | Protected-fact direction | `test_protected_direction_matches_the_relevant_fact_in_mixed_evidence`; `test_protected_direction_rejects_an_explicit_inversion` |
| Geography | U.S./U.K. canonical aliases pass; different geography fails | Protected geography | `test_protected_geography_accepts_only_canonical_country_aliases`; `test_evidence_fidelity_rejects_a_matching_value_with_the_wrong_geography` |
| Population/cohort | Matching cohort passes; wrong cohort/denominator fails | Evidence relationship | `test_relationship_check_rejects_wrong_cohort_and_denominator`; `test_wrong_cohort_and_wrong_denominator_are_rejected` |
| Attribution | Matching source actor passes; actor inversion fails | Protected attribution | `test_evidence_fidelity_rejects_direction_and_attribution_inversions` |
| Comparison baseline | Explicit 2024 vs 2023 mismatch fails; ambiguous “prior year” stays unknown | Protected comparison | `test_protected_comparison_rejects_different_explicit_year_baselines`; `test_protected_comparison_leaves_ambiguous_baseline_wording_unknown` |
| Forecast vs observed | Matching status passes; observed/forecast inversion fails | Observation-status invariant | `test_evidence_fidelity_rejects_subject_rank_and_comparison_inversions`; `test_wrong_period_and_forecast_alternatives_are_rejected` |
| Evidence ID | Linked evidence passes; missing/unknown IDs block | Provenance contract | `test_retained_claim_validation_fails_closed_for_unknown_soft_copy_evidence`; `test_retained_claim_validation_fails_closed_for_missing_soft_copy_evidence` |
| Quote wording | Normalized exact quote passes; fabricated quote fails | Exact quote fidelity | `test_evidence_fidelity_rejects_fabricated_quote_and_missing_provenance`; `test_evidence_fidelity_accepts_a_normalized_quote_and_keeps_unknown_unknown` |
| Provenance/text hash | Current hash passes; mismatched/stale provenance fails | Provenance contract | `test_retained_claim_validation_rejects_soft_copy_provenance_hash_mismatch`; `test_retained_claim_validation_requires_current_soft_copy_provenance` |
| Stale artifact/evidence binding | Current package passes; changed artifact/evidence/source/validator/config identity fails | Publish readiness lineage | `test_stale_final_artifact_hash_blocks_retained_grounding_readiness`; `test_stale_evidence_and_source_identity_block_readiness`; `test_stale_validator_and_configuration_identity_block_readiness` |

Focused test results:

```text
python -m pytest -q tests/contracts/test_protected_facts.py tests/test_evidence_compatibility.py tests/test_quantity_utils.py tests/test_retained_claim_grounding.py tests/test_grounding_protected_facts.py tests/test_grounding_editorial_interpretation.py tests/test_publish_readiness_gate.py tests/test_validation_number_temporal_context.py tests/test_claim_validation_generator.py tests/_test_claim_validation_generator/cases_01_evidence_fidelity.py tests/_test_claim_validation_generator/cases_03_hybrid_grounding.py tests/_test_public_editorial_quality_generator/cases_01_temporal_and_relationship_rules.py
276 passed in 5.42s

python -m pytest -q tests/test_regeneration_candidate.py tests/test_report_regeneration_generator.py tests/test_public_editorial_quality_generator.py
181 passed in 12.30s
```

The tests include the retained-claim identity/cache reuse and stale-result rejection cases. No provider call was made by readiness tests. The full frozen cohort remains the deciding result: deterministic fixture probes do not establish a zero false-positive rate on real reports.

## Retained grounding and semantic-overlap decision

- Three final `retained_claim_validation.json` artifacts were present in the run: Merchant Risk Council, Algolia, and Criteo. The linked readiness ledger records their package hashes, final artifact hashes, and counts.
- Readiness found a current package missing on 11 reports; several candidate results existed but carried `semantic_result_missing`. Candidate output and retained final package are not interchangeable. The readiness gate correctly failed missing/stale packages, so this is a materialization/result-mapping gap rather than a reason to weaken the gate.
- Merchant Risk Council's current package is not publishable because it has 3 unresolved factual figures; Algolia's is not publishable because 2 factual candidate surfaces are unsupported; Criteo's factual package is supported. No case was found where a `publish_readiness=pass` artifact coexisted with a current retained factual package marked `not_publishable`.
- Phase 3 was gated off by the Phase 1 regressions. No legacy semantic behavior was removed. Remaining `runtime.semantic_outcome` dependencies, including metrics and quotes, have not been mapped to final-public grounding. Current usage showed 68 legacy semantic executions alongside 21 batched report-grounding events; there is no evidence here that consolidation would reduce calls or preserve every output contract.

## Completion assessment

Acceptance is **not met** on the initial measured revision: known valid claims are falsely rejected; the cohort fell from 9/20 to 0/20; several previously ready reports lack materialized current packages or complete semantic result mappings; and recent successful canaries regressed. Exact numeric, timeframe, direction, quote, provenance, and stale-lineage mutation cases passed their focused tests. The geography alternative-selection failure was separately reproduced, fixed without changing the `unknown` classification, and covered by the 33-pass regression run. A clean full-cohort run is still required on the committed fix before drawing a final cohort conclusion.
