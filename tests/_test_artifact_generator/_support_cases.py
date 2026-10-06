# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.generators.artifact_normalization import normalize_artifact_insights

from ._shared import *  # noqa: F401,F403

__all__ = [
    "test_metric_label_survives_candidate_to_final_insight_to_key_figure",
    "test_iab_19_2_key_figure_uses_its_explicit_digital_video_label",
    "test_activate_2026_128_million_key_figure_uses_its_explicit_metric_label",
    "test_legacy_metric_label_never_truncates_us_or_uk_abbreviations",
    "test_legacy_multi_metric_insight_uses_sentence_for_its_metric_not_first",
    "test_legacy_metric_omits_key_figure_when_no_metric_specific_label_is_reliable",
    "test_legacy_metric_uses_its_complete_clause_when_supporting_metrics_follow",
    "test_legacy_metric_omits_a_lowercase_clause_without_a_complete_subject",
    "test_derive_metric_spine_from_insights_uses_embedded_metric_contract",
    "test_metric_spine_label_does_not_split_a_decimal_display",
    "test_metric_spine_label_keeps_leading_abbreviation_with_its_sentence",
    "test_metric_spine_label_keeps_a_complete_long_source_sentence",
    "test_metric_spine_renders_one_clean_primary_metric",
    "test_metric_spine_omits_iab_semicolon_packed_metric_but_preserves_insight",
    "test_metric_spine_omits_metric_when_no_clean_display_is_available",
    "test_metric_spine_preserves_source_display_and_exposes_complete_numeric_metadata",
    "test_build_executive_advisory_artifacts_surfaces_not_found_states",
    "test_build_executive_advisory_artifacts_separates_decision_roles",
    "test_build_executive_advisory_artifacts_omits_unsupported_decision_fields",
    "test_assemble_artifacts_builds_universal_claim_ledger",
    "test_claim_ledger_preserves_typed_evidence_source_identity",
    "test_assemble_artifacts_builds_topics_key_figures_and_chart_cards",
    "test_generate_artifacts_passes_metric_spine_to_editorial_prompts",
]


__all__ = [name for name in globals() if not name.startswith("__")]
