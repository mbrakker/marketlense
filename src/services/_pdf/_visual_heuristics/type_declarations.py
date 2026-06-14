"""Shared static declarations for split PDF visual-heuristic modules."""

from __future__ import annotations

from typing import Any, Callable, List, Tuple, TypeAlias

import pymupdf as fitz

_ChartRect: TypeAlias = Any
_PageTextLine: TypeAlias = Any
_VisualCandidateRelationships: TypeAlias = Any
_alpha_ratio: Any
_horizontal_overlap_ratio: Any
_is_page_number_text: Any
_line_starts_with_caption_hint: Any
_rect_containment_ratio: Any
_rect_iou: Any
_rect_overlap_area: Any
_rect_seen: Any
_s: Any
_starts_with_lower_alpha: Any
_table_normalize_text: Any
_table_page_text_lines: Any
_text_stats: Any
_vertical_overlap_ratio: Any


_drawing_rects: Any
_caption_blocks: Callable[..., List[Tuple[fitz.Rect, str]]]
_compact_top_chart_title_like: Callable[..., bool]
_chart_axis_label_band_like: Callable[..., bool]
