# DoubleVerify Key Figure numeric-projection closure

**Status:** Closed
**Verified code SHA:** `76b8b5013869a621f43f24d107484e92d0cc8b85`
**Provider calls / live report runs:** 0

## Original failure and root cause

The retained candidate projected `50%` as figure ID
`display-viewability-duration-criterion-retained-5`, bound to `s4`. Its source
on pages 5–6 says “at least 50%”; the quantitative parser returns `50%` as
`eq` and the bound evidence as `gte`. The literal is present, but the projection
lost the comparator. This was an invalid generated projection, not a validator
false positive. `quantity_supported(..., numeric_only=True)` correctly returns
false for the pair.

## Deterministic replay

Replay used `tests/fixtures/key_figure_selection/doubleverify_threshold_projection.json`
and retained candidate 3 at
`tmp/doubleverify-safe-removal-verified-20260925/ias-first-attempt-kw2clmny/`.
The candidate-integrity gate passed and verified the `key_figures` derived
root. Evidence scoping was checked with a matching quantity present only under
an unrelated evidence ID; that figure was omitted.

| State | Key Figure IDs |
| --- | --- |
| Before | `q1-2026-apac-authentic-viewable-rate`, `q1-2026-north-america-video-viewable-rate`, `q1-2026-apac-authentic-viewable-rate-retained-3`, `display-viewability-duration-criterion-retained-5` |
| After | `q1-2026-apac-authentic-viewable-rate`, `q1-2026-north-america-video-viewable-rate`, `q1-2026-apac-authentic-viewable-rate-retained-3` |

All three retained figure records compare equal before and after. The `s4`
evidence and its sibling insight remain in the candidate. Manually injecting
the removed `50%` figure against “at least 50%” evidence is still rejected by
the downstream `numbers` rule.

## Validation and strategy

Re-running canonical `inline_deterministic` validation on the retained
candidate removed only `numbers:key_figures:4.figure`; it introduced no issue.
The same-mode `deferred_grounding_required:validation` informational issue
appears both before and after. The deterministic candidate-integrity gate
passed with no issues.

- Before validation issue IDs: `family_confidence:quotes`, `artifact_quality:summary.tldr`, `numbers:key_figures:4.figure`, `deferred_grounding_required:validation`.
- After validation issue IDs: `family_confidence:quotes`, `artifact_quality:summary.tldr`, `deferred_grounding_required:validation`.

The Key Figure planner offers `REGENERATE_ITEM/current_evidence`. After that
strategy fingerprint is rejected, the planner returns `skip`; it does not offer
an equivalent `REMOVE_CLAIM/safe_removal`. Targeted regeneration is model-free.

The remaining findings in the retained canonical DoubleVerify validation are:

- Error: `public_editorial_quality.metric_label_relationship:insights:q1-2026-emea-engagement-index` (also reproduced unchanged by the public editorial quality evaluator after replay).
- Warning: `family_confidence:quotes`.
- Warning: `artifact_quality:summary.tldr`.
- Info: `metrics:insights:q1-2026-emea-engagement-index`.

## Verification

- `python -m pytest -q tests/test_key_figure_selection.py tests/test_quantity_utils.py tests/test_validation_soft_copy_numbers.py tests/test_report_regeneration_identity_and_failures.py tests/test_report_regeneration_generator.py tests/test_regeneration_candidate.py` — **145 passed**.
- `python -m pytest -q tests/test_key_figure_selection.py::test_doubleverify_threshold_projection_is_omitted_from_its_bound_evidence tests/test_key_figure_selection.py::test_unrelated_evidence_number_does_not_support_key_figure tests/test_validation_soft_copy_numbers.py::test_number_validation_still_rejects_exact_key_figure_from_threshold_evidence tests/test_report_regeneration_generator.py::test_regenerate_artifacts_rebuilds_only_key_figures_without_model_calls tests/test_report_regeneration_identity_and_failures.py::test_key_figure_ladder_has_one_deterministic_rebuild_strategy` — **5 passed**.
- `python -m ruff check src/generators/_artifact_generator/storage.py src/orchestrators/_report_analysis_orchestrator/regeneration_plan.py tests/test_key_figure_selection.py tests/test_report_regeneration_identity_and_failures.py tests/test_validation_soft_copy_numbers.py --ignore E501` — **passed**.
- `git diff --check` — **passed**.
