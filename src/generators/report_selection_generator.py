from __future__ import annotations

"""Report-selection generator facade.

This module preserves the public import surface while the semantic families
for ranking, crop refinement, and figure-asset selection live under
`src/generators/_report_selection_generator/`.
"""

from ._report_selection_generator.crop_refine import (
    _bbox_tuple,
    _crop_refine_cache_path,
    _crop_refine_entry_key,
    _crop_refine_parallel_workers,
    _crop_refine_profile_key,
    _load_crop_refine_cache,
    _write_crop_refine_cache,
    select_refined_candidate_items,
)
from ._report_selection_generator.figure_selection import (
    _apply_figure_candidate_metadata,
    _asset_from_candidate,
    _build_figure_assets,
    _candidate_crop_path_map,
    _candidate_extraction_output_path,
    _empty_figure_response,
    _legacy_primary_display_caption,
    _load_candidate_crop_path_map,
    _resolve_figure_section_assets,
    _select_fallback_candidate_crop_paths,
    _select_fallback_candidates,
    select_report_figures,
)
from ._report_selection_generator.ranking import (
    _RankBatchResult,
    _candidate_is_obvious_pass,
    _candidate_is_obvious_reject,
    _candidate_meta,
    _candidate_prefilter_priority,
    _candidate_prefilter_reject_reason,
    _candidate_quality_signals,
    _compact_rank_features,
    _compact_rank_row,
    _legacy_rank_row,
    _merge_rank_usage,
    _rank_candidates_batch,
    _rank_feature_value,
    _rank_threshold_pass,
    _split_candidates_by_kind,
    _truncate_prefiltered_candidates,
)

__all__ = [
    "_RankBatchResult",
    "_apply_figure_candidate_metadata",
    "_asset_from_candidate",
    "_bbox_tuple",
    "_build_figure_assets",
    "_candidate_crop_path_map",
    "_candidate_extraction_output_path",
    "_candidate_is_obvious_pass",
    "_candidate_is_obvious_reject",
    "_candidate_meta",
    "_candidate_prefilter_priority",
    "_candidate_prefilter_reject_reason",
    "_candidate_quality_signals",
    "_compact_rank_features",
    "_compact_rank_row",
    "_crop_refine_cache_path",
    "_crop_refine_entry_key",
    "_crop_refine_parallel_workers",
    "_crop_refine_profile_key",
    "_empty_figure_response",
    "_legacy_primary_display_caption",
    "_legacy_rank_row",
    "_load_candidate_crop_path_map",
    "_load_crop_refine_cache",
    "_merge_rank_usage",
    "_rank_candidates_batch",
    "_rank_feature_value",
    "_rank_threshold_pass",
    "_resolve_figure_section_assets",
    "_select_fallback_candidate_crop_paths",
    "_select_fallback_candidates",
    "_split_candidates_by_kind",
    "_truncate_prefiltered_candidates",
    "_write_crop_refine_cache",
    "select_refined_candidate_items",
    "select_report_figures",
]
