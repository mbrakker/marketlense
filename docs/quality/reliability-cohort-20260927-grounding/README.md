# Retained grounding architecture proof — 2026-09-27

## Decision

**The architecture is not proven complete.** The exact post-fix 20-report cohort admitted all frozen sources, but only 1/20 reached `awaiting_review` and passed publication readiness. Source review found 11 confirmed false-positive claim decisions among the eight reports that had passed the 2026-09-20 cohort. Several additional outcomes remain unresolved because the failed intermediate artifact or exact evidence binding was not retained. No validation rule was weakened to raise cohort pass rate.

Phase 3 semantic-overlap analysis was not performed: Phases 1–2 do not support a consolidation decision. `validation/semantic.py` and legacy semantic behavior were not changed. The required mapping of `runtime.semantic_outcome` consumers, including metric and quote outputs, remains outstanding.

## Implementation change under test

At `55cd01815d9744153539a60fdb2afe4d86e0fb99`, alternative-evidence selection stopped treating an `unknown` protected dimension as compatible when both the claim and candidate explicitly state a value for that dimension. The comparator continues to report `unknown`; the selector simply does not promote that alternative as deterministic support. Missing-dimension evidence can still serve as general context for a rewrite. This was the narrow response to the failed geography-selection probes; it did not alter retained-claim contradiction rules. The red/green regression and protected-fact tests passed, and the post-fix run above is the full cohort evaluation of that exact implementation SHA.

## Exact run identity and controls

- Implementation SHA: `55cd01815d9744153539a60fdb2afe4d86e0fb99` (`main` at cohort execution; the later evidence-only commit does not change this implementation SHA).
- Command: `python scripts/quality/run_frozen_reliability_cohort.py --runs-root tmp/retained-grounding-cohort-20260927-postgeo --max-duration 7200`.
- Run result: [`postfix_cohort_result.json`](postfix_cohort_result.json), SHA-256 `155be30341ee257253628f04c2dac33bc358f71393eb72ba4cc82eed46d83fea`. Same-day pre-fix baseline: [`cohort_result.json`](cohort_result.json), SHA-256 `9be431aed086136bfc1428e311dbdf8976192e2ccc1970b3e6033db970ce8e65`; the previous-vs-pre-fix per-report comparison is [`report_outcomes_comparison.csv`](report_outcomes_comparison.csv).
- Run's frozen manifest: [`postfix_frozen_cohort.json`](postfix_frozen_cohort.json), SHA-256 `4da8f4112f37bf880254fe85dc8784752fda089f0cac59f3989520370ae12286`. It is semantically equal to canonical [`frozen_reliability_cohort_20.json`](../../../scripts/quality/frozen_reliability_cohort_20.json), whose SHA-256 is `21a9a1b995d10b5add412780d96930ecc29bafd082907ecbf0741c80be841a07`; JSON formatting differs. Frozen PDF MD5 and SHA-256 values are in [`frozen_inputs_sha256.csv`](frozen_inputs_sha256.csv). All 20 MD5s matched the manifest and each SHA-256 was recomputed.
- All 20 reports were admitted and run with isolated fresh state. Publication was disabled; processing stopped at publication readiness, with no WordPress publish job. There were zero operator interventions and no manual repair, substitution, or artifact reuse. The benchmark's existing bounded automatic-recovery policy remained enabled.
- This cohort consumes frozen source PDFs and exercises the production report workflow through readiness; it does not perform new live discovery or acquisition. The source cohort intentionally fixes those inputs to make the report-grounding comparison exact.

## Outcomes and comparison

| Measure | 2026-09-20 full cohort (`89b4fc4c1159499806ed16993d76f3684fe3412e`) | 2026-09-27 pre-fix baseline (`8a05e2d`) | 2026-09-27 post-fix (`55cd018`) |
| --- | ---: | ---: | ---: |
| `awaiting_review` and readiness pass | 9/20 (45%) | 0/20 (0%) | 1/20 (5%) |
| Terminal outcomes | 20/20 | 20/20 | 20/20 |
| Operator interventions | 0 | 0 | 0 |
| Provider calls | 644 | 574 | 590 |
| Input tokens | 5,299,676 | 5,900,816 | 6,194,695 |
| Output tokens | 699,778 | 823,384 | 856,988 |
| Estimated model cost | USD 1.869133 | USD 0.998643 | USD 1.035915 |
| Wall-clock runtime | 5,424.234 s | 5,131.846 s | 5,544.482 s |

Relative to the same-day pre-fix run, the post-fix cohort had one more ready report, 16 more provider calls, 293,879 more input tokens, 33,604 more output tokens, USD 0.037272 higher estimated cost, and 412.636 seconds more runtime. Model outputs and bounded recovery can vary; this result does not establish that the evidence-selector change caused the single-report outcome change. Relative to the previous full cohort, eight previously successful reports now fail. The deterioration is not explained away by overall cost or call reductions.

Post-fix terminal failure counts are: `publish_readiness_failed` 10, `validation_failed` 3, `regeneration_repair_decision_invalid` 2, `report_card_manifest_write_failed` 2, `soft_copy_claim_provenance_coverage_invalid` 1, and `card_tldr_standard_invalid` 1. Per-report results and forensic notes are in [`postfix_report_outcomes.csv`](postfix_report_outcomes.csv).

The cohort result's `validation` field is not report-scoped: the runner reads a shared output directory's lexicographically last `validation.json`. Activate's report-scoped validation artifact passes despite that row showing `fail`. I treated each report's own artifacts, readiness record, and final state as authoritative. Reports without retained exact failed intermediates are marked unresolved instead of accepting the outer error as a valid source-fidelity decision.

## Previously successful reports that regressed

The eight reports below reached `awaiting_review` in the 2026-09-20 cohort and failed in this run. Eleven claim/rule decisions were confirmed false positives by checking the exact linked evidence against the PDF or retained source text. The count is decision records with exact claim IDs, not unique prose; it excludes unbound semantic findings and unresolved diagnoses.

| Report | Current failure and exact claim/evidence | Classification and root cause |
| --- | --- | --- |
| DoubleVerify | `insight:q1-2026-ad-attention-regional:metric` and `insight:q1-2026-engagement-regional:metric`, both linked to `section-7`, PDF p.9. The EMEA row gives Ad Attention Index 110 and Engagement Index 116 in separate columns. | **2 false-positive decisions.** Quantity matching mixes neighboring table metrics and treats index values as count values. The separate duplicate-insight errors are **true positives**: three duplicate pairs are flagged (`q1-2026-brand-suitability-regional` / `q1-2026-authentic-viewable-regional`, `q1-2026-engagement-regional` / `q1-2026-ad-attention-regional`, and `q1-2026-video-viewable-regional` / `q1-2026-authentic-viewable-regional`), with the matching pairs linked to sections 2 or 7. Repair then failed with `decision_contract_invalid`; do not collapse these into one diagnosis. |
| Reuters Institute | `soft_copy:summary:8d92571c5b950823`, linked to DocMap sections 2/3/5/7, is rejected for attribution although those sections describe AI discovery, creator competition, distinctive journalism, and newsroom changes. `summary.tldr` persisted as a 20-word complete sentence ending in a period. | **1 confirmed false positive; terminal TLDR failure unresolved.** The persisted TLDR satisfies the retained length/terminal-punctuation contract, but the exact rejected candidate was not retained, so `card_tldr_standard_invalid` cannot be reproduced. The report's LinkedIn recommendation is MarketLense-authored; its semantic rejection lacks retained evidence IDs and is not included in the false-positive count. |
| Merchant Risk Council | `key_figure:1:figure` and `key_figure:2:figure` in the candidate package are assembled as label/context strings, while the final public `key_figures` fields contain 43% and 63%. Linked source PDF p.2 gives a sample of 1,200+ merchants, 43% accepting real-time payments, and 63% exploring/planning agentic payments. | **Unresolved package/materialization mismatch.** The final values are source-backed, but the candidate claim projection is inconsistent and has no semantic execution. Readiness fails `package_missing`; it does not reject a proven false fact. |
| Bain & Company | `soft_copy:summary:a633bdb9904a1f2d` and `insight:asset-light-and-partnership-actions:text`, linked to `section-4`, reject the exact “asset-light” phrase. Source infographic PDF p.1 recommends an asset-light model and partnerships. | **2 false-positive quote decisions.** Exact source wording is present. A separate malformed key figure omits the 52% value and is a true output defect. |
| Deloitte | `soft_copy:summary:7a3740ee6896e9c4`, `soft_copy:expert_comment:e73b39c5e91295b9`, and `soft_copy:linkedin_post:d039d5abcfa42d08`, linked to `getting-involved`, PDF p.7. | **3 false-positive decisions.** Observation-status logic is applied to claims about a strategic choice. The source describes retailer-owned assistants, control over customer interactions, and LLM partnerships for AI-native shoppers; it does not establish the opposite observation-status proposition. |
| Emplifi | `soft_copy:expert_comment:6798f3e99fda2633` links `behavior` and `trust`; `soft_copy:expert_comment:790a7f54bd7ebc5d` links `authenticity` and `customer_service`. PDF pp.4, 11, 13, and 15 separately support the over-$ / £500 research behavior, 79% review finding, 91% disclosure expectation, and 84% authenticity result. | **2 false-positive decisions.** The validator compares multiple independently linked metrics as though they share one value/unit relationship. |
| Qualtrics | The final figure fields contain 72%, 52%, and 25%; `intro-significant-change-new-hires` and source PDF p.2 support the 72% change finding. The candidate package nevertheless has 17 unresolved factual claims and zero semantic executions. | **Unresolved grounding/materialization gap.** The current final artifact does not prove a false figure; readiness fails `package_missing` because no current accepted package was materialized. |
| StackAdapt Inc. | `insight:display-ctv-programmatic-spend:text`, linked to the chart on PDF p.7, says Display and CTV together account for 77% of programmatic spend. | **1 false-positive category/value decision.** The source chart gives 45.85% Display and 30.83% CTV (76.68%, rounded to 77%) and states the combined share. `metric_label_relationship` incorrectly rejects the combined category. |

These 11 source-supported failures alone violate the zero-false-positive acceptance criterion. Among other reports, reviewed false-positive findings also include Adjust's complete “Scope matters.” sentence rejected as a fragment and edition year 2026 treated as a 2025 data timeframe; Criteo's linked 94% survey finding; Algolia's 42%/34% comparison and scope attribution; KPMG's explicit distinction between expected and completed carve-out activity; and Capgemini/Robeco attribution findings. These are detailed in the per-report outcome ledger; incomplete exact evidence bindings remain unresolved.

The claim-level inventory with validator rule, affected artifact section, exact retained evidence ID/page, expected result, observed baseline result, and semantic root-cause category is [`false_positive_failure_matrix.csv`](false_positive_failure_matrix.csv). Rows that contain both a confirmed supported subclaim and an unlinked additional number remain marked partial; they do not authorize accepting the unsupported number. Other unlinked quote or sample-size cases remain explicitly unresolved.

## Recent closure canaries

| Report | Recent targeted result | Post-fix frozen-cohort result | Assessment |
| --- | --- | --- | --- |
| Criteo | [Passed closure canary](../closure-canary-criteo-adjust-20260925.json) at `009bb1c6fc139c55610b9b457f888a8180c81427` on 2026-09-25 | `publish_readiness_failed`; candidate has unsupported and unresolved findings | Deterioration. The 94% finding on source PDF p.5 is supported; value attachment to other quantities is a false positive. |
| Adjust | [Passed final canary](../closure-canary-criteo-adjust-20260925.json) at `bb693e95b36453bb2111a5ba1b0f1bc83a816c0b` on 2026-09-25 | `validation_failed`, `public_editorial_quality.sentence_fragment`, `soft_copy:linkedin_post:8cf86eac6bb2cb73` | Deterioration. “Scope matters.” is a complete sentence. The separate 2026 edition vs 2025 data-year conflict is also a false positive. |
| DoubleVerify | [Existing closure canary](../doubleverify-closure-canary-20260925.json) was `failed_not_closed` | `regeneration_repair_decision_invalid` after duplicate-insight validation | Not a new regression against its targeted canary; current source-supported metric false positives still require correction. |
| Mintel | [Existing residual canary](../a21-mintel-residual-canary-20260925.json) failed readiness | `regeneration_repair_decision_invalid`, `protected_field_changed` | Not a new regression against its targeted canary. Protected-field change remains a blocking invariant. |
| KPMG / Algolia | [Prompt 1 replay evidence](../prompt1-closure-replays-20260925.md) records passing targeted runs | Current frozen run fails readiness or validation | Deterioration. KPMG's expectation/completed-activity distinction is source-supported; Algolia has false-positive value/unit and attribution decisions plus malformed key figures. |

## Retained grounding and readiness evidence

Only three current final `retained_claim_validation.json` packages were materialized: Activate, Bain, and Algolia. Their actual package, artifact, public projection, evidence, source, validator, configuration, semantic execution, model/prompt, and readiness hashes are recorded in [`postfix_retained_grounding_lineage.csv`](postfix_retained_grounding_lineage.csv). Activate is the only package with `readiness_status=awaiting_review`: it has zero unsupported and zero unresolved factual claims, and its package identity matches its source, final artifact, evidence, validator, configuration, and policy. Bain and Algolia are `not_publishable` and readiness fails with unsupported factual counts 2 and 5 respectively (Algolia also has 2 unresolved claims).

The other 17 reports do not have a current final package for readiness to consume. Candidate packages are not treated as final retained packages. In particular, MRC and Qualtrics have report-scoped validation artifacts with status `pass` and correct visible source-backed figure values, but their candidate grounding packages report 17 unresolved claims, zero semantic executions, and readiness detail `package_missing`; those are incomplete grounding/materialization cases, not demonstrated false facts. No `publish_readiness=pass` was observed alongside a current package marked `not_publishable`; the single pass is backed by a current fully supported package. No semantic provider call occurred inside readiness. Package materialization coverage is still a major architecture gap.

### Canonical sentence segmentation and display-equivalence checks

For Contentstack, the current retained summary has 8 canonical material sentences and 8 matching provenance hashes; expert comments have 3/3 and LinkedIn has 9/9. This audit used the canonical `soft_copy_material_sentences()` grid, including the retained `U.K.` / `U.S.` text. No current retained segmentation mismatch was found. The terminal provenance-coverage error came from an intermediate candidate that was not retained, so it remains an unresolved diagnostic rather than proof of a geography/initialism segmentation false positive. The `50%` / `50.0%` quantity equivalence and `42%` → `43%`, `18%` → `$18m`, and `2025` → `2026` mismatch cases are covered by the focused quantity/evidence-fidelity tests; all asserted the expected result.

## Mutation probes

The focused deterministic mutation fixtures passed. They cover supported controls and altered inputs; the expected authoritative check is recorded for each case. This proves the listed fixtures only; it does not override the source-backed false positives in the real cohort.

| Mutation | Supported control and rejected mutation | Expected layer / regression coverage |
| --- | --- | --- |
| Numeric value | Equivalent quantity passes; 42% → 43% fails | `extract_quantities` / evidence fidelity: `test_evidence_fidelity_rejects_a_generated_finding_with_the_wrong_number`; `test_numeric_grounding_rejects_changed_quantity_primitives` |
| Unit, currency, magnitude | Canonical equivalent displays pass; unit/currency/magnitude changes fail | Quantity semantics: `test_currency_magnitude_forms_match`; `test_financial_magnitude_abbreviations_match_their_canonical_forms`; `test_evidence_fidelity_rejects_wrong_unit_and_recovers_exact_page_provenance` |
| Timeframe | Same period passes; 2025 → 2026 and wrong period fail | Period/protected facts: `test_evidence_fidelity_rejects_a_matching_value_with_the_wrong_period`; `test_public_numeric_validation_keeps_value_unit_and_period_mismatches_blocking` |
| Direction | Relevant direction in mixed evidence passes; explicit inversion fails | Protected direction: `test_protected_direction_matches_the_relevant_fact_in_mixed_evidence`; `test_protected_direction_rejects_an_explicit_inversion` |
| Geography | U.S./U.K. aliases pass; different geography fails | Protected geography: `test_protected_geography_accepts_only_canonical_country_aliases`; `test_evidence_fidelity_rejects_a_matching_value_with_the_wrong_geography` |
| Population/cohort | Matching cohort passes; wrong cohort/denominator fails | Relationship validation: `test_relationship_check_rejects_wrong_cohort_and_denominator`; `test_wrong_cohort_and_wrong_denominator_are_rejected` |
| Attribution | Matching actor passes; actor inversion fails | Evidence fidelity: `test_evidence_fidelity_rejects_direction_and_attribution_inversions` |
| Comparison baseline | Same explicit baseline passes; 2024 → 2023 fails; ambiguous wording remains unknown | Protected comparison: `test_protected_comparison_rejects_different_explicit_year_baselines`; `test_protected_comparison_leaves_ambiguous_baseline_wording_unknown` |
| Forecast vs observed | Matching status passes; forecast/observed inversion fails | Observation status: `test_evidence_fidelity_rejects_subject_rank_and_comparison_inversions`; `test_wrong_period_and_forecast_alternatives_are_rejected` |
| Evidence ID | Correct linked ID passes; missing/unknown ID blocks | Provenance: `test_retained_claim_validation_fails_closed_for_unknown_soft_copy_evidence`; `test_retained_claim_validation_fails_closed_for_missing_soft_copy_evidence` |
| Quote wording | Normalized exact wording passes; fabricated wording fails | Exact quote fidelity: `test_evidence_fidelity_rejects_fabricated_quote_and_missing_provenance`; `test_evidence_fidelity_accepts_a_normalized_quote_and_keeps_unknown_unknown` |
| Provenance/text hash | Current hash passes; mismatched/stale provenance blocks | Provenance: `test_retained_claim_validation_rejects_soft_copy_provenance_hash_mismatch`; `test_retained_claim_validation_requires_current_soft_copy_provenance` |
| Stale artifact/evidence binding | Current identity passes; changed artifact/evidence/source/validator/config identity blocks | Publish readiness lineage: `test_stale_final_artifact_hash_blocks_retained_grounding_readiness`; `test_stale_evidence_and_source_identity_block_readiness`; `test_stale_validator_and_configuration_identity_block_readiness` |

The focused commands were rerun on implementation SHA `55cd01815d9744153539a60fdb2afe4d86e0fb99`:

```text
python -m pytest -q tests/contracts/test_protected_facts.py tests/test_evidence_compatibility.py tests/test_quantity_utils.py tests/test_retained_claim_grounding.py tests/test_grounding_protected_facts.py tests/test_grounding_editorial_interpretation.py tests/test_publish_readiness_gate.py tests/test_validation_number_temporal_context.py tests/test_claim_validation_generator.py tests/_test_claim_validation_generator/cases_01_evidence_fidelity.py tests/_test_claim_validation_generator/cases_03_hybrid_grounding.py tests/_test_public_editorial_quality_generator/cases_01_temporal_and_relationship_rules.py
276 passed in 4.34s

python -m pytest -q tests/test_regeneration_candidate.py tests/test_report_regeneration_generator.py tests/test_public_editorial_quality_generator.py
181 passed in 12.08s
```

No test used a live provider call for the mutation decisions. The test suite includes readiness's current-identity and stale-result checks and does not make a semantic provider call during readiness.

## Provider reuse and cost evidence

The cohort measured 590 provider calls, 6,194,695 input tokens, 856,988 output tokens, USD 1.035915 estimated cost, and 5,544.482 seconds. Per-report provider attribution and grounding response-reuse/cache rate were unavailable in the retained run result. The three final packages share one semantic execution identity; this is lineage evidence, not a provider-call reuse rate. The same-day pre-fix baseline recorded 21 report-level grounding events and 68 legacy semantic events; an equivalent post-fix execution-event count was not retained, so no cache or reuse rate is inferred.

## Semantic overlap decision and completion status

Phase 3 did not run because the real-source cohort failed the Phase 1 bar and the source-supported false positives invalidate any consolidation safety conclusion. No legacy semantic function was removed or narrowed. Remaining dependencies include `runtime.semantic_outcome` uses for metrics and quotes; their equivalence to final-public grounding, mutation coverage, provider-call effect, and output-contract coverage remain unproven.

Acceptance is **not met**: 11 confirmed false-positive claim decisions occurred among reports that were previously ready; eight prior successes regressed; only one report is currently ready; 17 reports lack a final retained grounding package; and targeted Criteo/Adjust/KPMG/Algolia canaries show further deterioration. Fixture mutations passed, including value, unit/currency/magnitude, timeframe, direction, attribution, evidence-ID/provenance, quotes, and stale-lineage checks. There were zero operator interventions and zero observed readiness passes with an unsupported current package. Remaining diagnostics and per-report classifications are retained in the linked CSVs; unresolved cases are not relabeled as true positives.
