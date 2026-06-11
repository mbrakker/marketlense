from __future__ import annotations

# ruff: noqa: E402,F401,F403,F405,F821

from ._chart_layout.geometry import *
from ._chart_layout.text_blocks import *
from ._chart_layout.expansion import *

__all__ = [
    "_image_block_rects",
    "_drawing_rects",
    "_chart_axis_label_band_like",
    "_numeric_token_hits",
    "_compact_top_chart_title_like",
    "_panel_caption_looks_top_band",
    "_drawing_caption_rects",
    "_caption_blocks",
    "_heading_lines",
    "_cluster_rects_by_y",
    "_has_intervening_paragraph",
    "_heading_chart_rects",
    "_nearest_caption_block",
    "_clamp_top_to_caption",
    "_clamp_top_to_heading",
    "_heading_top_block_limit",
    "_caption_top_block_limit",
    "_extend_with_note_blocks",
    "_next_chart_blocker_top",
    "_clamp_bottom_to_next_chart_blocker",
    "_extend_with_adjacent_text_blocks",
    "_extend_chart_rect_with_adjacent_drawings",
    "_has_internal_top_text",
    "_extend_with_heading_above",
    "_adjust_rect_for_text_margins",
    "_expand_rect_into_whitespace",
    "_caption_near_top",
    "_merge_caption_above",
    "_nearest_heading_above",
    "_note_block_bottom",
    "_next_block_top_below",
    "_clamp_bottom_to_note",
]
