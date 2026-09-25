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

The findings recorded at the key-figure projection closure were:

- Error: `public_editorial_quality.metric_label_relationship:insights:q1-2026-emea-engagement-index` (also reproduced unchanged by the public editorial quality evaluator after replay).
- Warning: `family_confidence:quotes`.
- Warning: `artifact_quality:summary.tldr`.
- Info: `metrics:insights:q1-2026-emea-engagement-index`.

## Editorial relationship follow-up

The residual metric relationship issue was a deterministic validator false
positive. The retained insight and metric spine both bind metric
`q1-2026-emea-engagement-index` to `EMEA Engagement Index = 116 index`,
`evidence_id=s7`, page 9. The public text says: “The regional table reports
EMEA's Engagement Index at 116; the index is normalized to 100, DV's average
for a 28-day rolling window.” The metric timeframe is `Q1 2026; DV-average
normalization uses a 28-day rolling window`; geography is EMEA, segment is
Engagement, subject is Engagement Index, and cohort and denominator are empty.
The retained candidate counterpart has the same insight ID, public text,
metric object, evidence ID, and page-9 `doc_map` evidence span.

The retained page 9 table headings are “Ad Attention Index”, “Exposure Index”,
and “Engagement Index”; its rows include `APAC | 109 | 112 | 107`,
`EMEA | 110 | 104 | 116`, `LATAM | 101 | 106 | 96`, and
`North America | 99 | 98 | 99`. The source-backed relationship is the third
column in the EMEA row: Engagement Index = 116. The existing category parser
read `EMEA: 110` as an EMEA/category pair but did not bind the remaining
positional cells. That partial interpretation caused it to reject the correct
claim as “attaches a retained metric value to a different source category”.

Before the fix, the relationship extractors returned these relevant sets:

- `_period_value_pairs`: evidence `{}`; public text `{}`.
- `_structured_category_value_pairs`: evidence `{('ad attention', '101'),
  ('ad attention', '109'), ('emea', '110'), ('engagement', '107'),
  ('engagement', '96'), ('exposure', '106'), ('exposure', '112'),
  ('north america', '99')}`; public text returned
  `{('engagement index', '116')}`.
- `_subject_value_relationships`: evidence `{}`; public text `{}`.

The exact failing comparison was the source category `emea` with allowed
values `{'110'}` versus `_values_near_label(public_text, 'emea') == {'116'}`.
Since `116` was absent from the partial category set, the validator reported a
category mismatch even though the ordered row binds it to EMEA's third column.

The validator now uses a positional row only after a preceding row establishes
unique category labels and the row has exactly the matching number of numeric
cells. This repairs the EMEA/Engagement/116 interpretation while retaining
rejection for swapped regions, categories, periods, cohorts, denominators, and
values from adjacent rows. The sanitized retained regression is
`tests/fixtures/editorial_relationships/doubleverify_emea_engagement.json`.

Deterministic replay of the retained `artifacts.json` and candidate 3 with the
current public-editorial-quality evaluator returns `pass` with no issue IDs.
The retained pre-fix diagnostic had only
`public_editorial_quality.metric_label_relationship:insights:q1-2026-emea-engagement-index`
as a public-editorial-quality issue. Replaying the retained candidate through
`validate_report` in `inline_deterministic` mode, with its retained evidence
packs and the already-closed invalid 50% key figure removed, returns `pass`
with warning-only `family_confidence:quotes` and `artifact_quality:summary.tldr`
plus informational `deferred_grounding_required:validation`. No provider call
was made.

## Verification

- `python -m pytest -q tests/test_key_figure_selection.py tests/test_quantity_utils.py tests/test_validation_soft_copy_numbers.py tests/test_report_regeneration_identity_and_failures.py tests/test_report_regeneration_generator.py tests/test_regeneration_candidate.py` — **145 passed**.
- `python -m pytest -q tests/test_key_figure_selection.py::test_doubleverify_threshold_projection_is_omitted_from_its_bound_evidence tests/test_key_figure_selection.py::test_unrelated_evidence_number_does_not_support_key_figure tests/test_validation_soft_copy_numbers.py::test_number_validation_still_rejects_exact_key_figure_from_threshold_evidence tests/test_report_regeneration_generator.py::test_regenerate_artifacts_rebuilds_only_key_figures_without_model_calls tests/test_report_regeneration_identity_and_failures.py::test_key_figure_ladder_has_one_deterministic_rebuild_strategy` — **5 passed**.
- `python -m ruff check src/generators/_artifact_generator/storage.py src/orchestrators/_report_analysis_orchestrator/regeneration_plan.py tests/test_key_figure_selection.py tests/test_report_regeneration_identity_and_failures.py tests/test_validation_soft_copy_numbers.py --ignore E501` — **passed**.
- `git diff --check` — **passed**.
- `python -m pytest -q tests/test_public_editorial_quality_generator.py tests/test_public_editorial_quality_provenance.py tests/test_public_editorial_quality_key_figure_labels.py tests/test_public_report_quality_gate.py` — **54 passed**.
- `python -m pytest -q tests/contracts/test_protected_facts.py tests/test_grounding_protected_facts.py tests/test_validation_soft_copy_numbers.py tests/test_quantity_utils.py` — **58 passed**.
- `python -m pytest -q tests/test_artifact_normalization_source_fidelity.py tests/test_key_figure_selection.py tests/test_report_regeneration_generator.py tests/test_report_regeneration_identity_and_failures.py tests/test_regeneration_candidate.py` — **121 passed**.
- Ruff passed for the changed generator and editorial-quality tests; the changed contract file passed with pre-existing `E501` lines excluded.
