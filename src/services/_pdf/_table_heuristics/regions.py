"""Compatibility surface for table-region detection and bounding boxes."""

from __future__ import annotations

# ruff: noqa: F401

__all__ = [
    "_compose_table_bbox",
    "_detect_ranked_table_candidates",
    "_expand_table_bbox",
]

from ._regions.compose import (
    _compose_table_bbox,
    _expand_table_bbox,
    _table_clamp_bottom_before_internal_heading,
    _table_clamp_top_to_internal_title,
    _table_clamp_top_to_internal_title_band,
    _table_restore_top_slack,
)
from ._regions.context import (
    _shrink_stream_table_rect,
    _table_attach_explicit_title_context,
    _table_attach_mixed_footer_blocks,
    _table_attach_note_bands,
    _table_attach_note_blocks,
    _table_attach_title_bands,
    _table_attach_title_blocks,
    _table_expand_horizontal_to_content,
    _table_extend_overlapping_note_blocks,
)
from ._regions.ranked import (
    _detect_ranked_table_candidates,
    _group_rank_blocks_into_sequences,
    _ranked_table_panel_region,
    _table_horizontal_rule_rects,
    _table_rank_value,
)
