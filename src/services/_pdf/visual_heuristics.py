"""Chart and infographic candidate heuristics facade.

This module keeps `visual_heuristics.py` as the discoverable internal boundary
while moving panel detection and chart-layout families into `_visual_heuristics/`.
It is not a public service boundary; callers enter through `pdf_service`.
"""

from __future__ import annotations

# ruff: noqa: E402,F401,F403,F405,F821

# ruff: noqa: F401,F841
import io
import logging
import math
import os
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, List, Optional, Tuple

import pdfplumber
import pymupdf as fitz
from PIL import Image

from src.contracts.candidates import Candidate
from src.utils.candidate_features import candidate_features
from src.utils.errors import AppError
from src.utils.path_utils import bounded_artifact_filename, safe_path_segment

PDF_FIGURE_EXCEPTIONS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    IndexError,
    KeyError,
    OSError,
    statistics.StatisticsError,
)


CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph", "source")


CHART_CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph", "infographic")


TABLE_CAPTION_HINTS = CAPTION_HINTS + ("table",)


PANEL_GUIDANCE_TITLE_RX = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:ways?|keys?|steps?|actions?|principles?|tips?|strategies?|takeaways?|lessons?|rules?)\b",
    re.IGNORECASE,
)


PAGE_FOOTER_BANNER_LINE_RX = re.compile(
    r"(?:\b20\d{2}\b\s*[|/]\s*\d{1,3}\b)|(?:[|/]\s*\d{1,3}\s*$)"
)


CHART_TEXT_MAX_LINES = 6


CHART_TEXT_MIN_CHARS = 60


CHART_TEXT_RATIO_THRESHOLD = 0.35


CHART_LABEL_DENSE_MIN_LINES = 20


CHART_LABEL_DENSE_MAX_AVG_LINE_LEN = 18.0


CHART_LABEL_DENSE_MAX_MEDIAN_LINE_LEN = 10.0


CHART_LABEL_DENSE_LONG_LINE_LEN = 32


CHART_LABEL_DENSE_MAX_LONG_LINE_RATIO = 0.2


CHART_LABEL_DENSE_SHORT_LINE_LEN = 12


CHART_LABEL_DENSE_MIN_SHORT_LINE_RATIO = 0.4


PANEL_CHART_MIN_NUMERIC_HITS = 2


PANEL_CHART_LABEL_ATTACH_MAX_GAP_X_FRAC = 0.1


PANEL_CHART_LABEL_ATTACH_MAX_GAP_Y_FRAC = 0.08


PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP = 0.15


PANEL_CHART_LABEL_ATTACH_MIN_H_OVERLAP = 0.15


PANEL_CHART_LABEL_ATTACH_SKIP_OVERLAP_RATIO = 0.85


PANEL_CHART_LABEL_ATTACH_MAX_LINES = 6


PANEL_CHART_LABEL_ATTACH_MAX_AVG_LINE_LEN = 34.0


PANEL_CHART_LABEL_ATTACH_MAX_CHARS = 180


PANEL_CHART_LABEL_ATTACH_MAX_AREA_FRAC = 0.08


PANEL_CHART_TOP_TITLE_ATTACH_MAX_SPILL_X_FRAC = 0.16


PANEL_CHART_TOP_TITLE_ATTACH_MAX_CENTER_DELTA_FRAC = 0.20


PANEL_CHART_TOP_TITLE_ATTACH_MAX_GAP_FRAC = 0.32


PANEL_CHART_TOP_TITLE_ATTACH_MIN_WIDTH_RATIO = 0.45


PANEL_CHART_TOP_TITLE_ATTACH_MAX_WIDTH_RATIO = 0.95


PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MIN_WIDTH_RATIO = 0.10


PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MAX_WIDTH_RATIO = 0.22


PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MAX_CENTER_DELTA_FRAC = 0.18


PANEL_CHART_TOP_TITLE_ATTACH_MAX_HEIGHT_RATIO = 0.26


PANEL_CHART_TOP_TITLE_ATTACH_MAX_LEFT_INSET_FRAC = 0.22


PANEL_CHART_TOP_TITLE_ATTACH_COMPONENT_MIN_H_OVERLAP = 0.08


PANEL_CHART_TITLE_BAND_MERGE_MAX_GAP_FRAC = 0.28


PANEL_CHART_TITLE_BAND_MERGE_MAX_AREA_RATIO = 0.65


PANEL_CHART_TITLE_BAND_MERGE_MIN_H_OVERLAP = 0.35


PANEL_CHART_INTERNAL_CAPTION_TOP_GAP_MAX = 32.0


PANEL_CHART_INTERNAL_CAPTION_MIN_WIDTH_RATIO = 0.30


PANEL_CHART_INTERNAL_CAPTION_MAX_LINES = 3


PANEL_CHART_INTERNAL_CAPTION_MAX_CHARS = 140


PANEL_CHART_INTERNAL_CAPTION_MAX_AVG_LINE_LEN = 60.0


PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD = 8.0


INFOGRAPHIC_LABEL_DENSE_MAX_AVG_LINE_LEN = 20.0


INFOGRAPHIC_LABEL_DENSE_MAX_MEDIAN_LINE_LEN = 12.0


INFOGRAPHIC_LABEL_DENSE_MAX_LONG_LINE_RATIO = 0.35


INFOGRAPHIC_LABEL_DENSE_MIN_SHORT_LINE_RATIO = 0.3


CHART_DENSE_RECOVERY_MIN_LINES = 12


CHART_DENSE_RECOVERY_MIN_CHARS = 400


CHART_DEDUP_IOU = 0.9


CHART_OVERLAP_IOU = 0.85


CHART_OVERLAP_CONTAINMENT = 0.88


CHART_MARGIN_FRAC = 0.12


CHART_MARGIN_RELAX_FRAC = 0.05


CHART_PAD_X_FRAC = 0.01


CHART_PAD_Y_FRAC = 0.008


CHART_NOTE_MAX_DIST = 140


CHART_NOTE_MAX_GAP_X_FRAC = 0.25


CHART_CAPTION_TOP_PAD_PX = 16.0


CHART_CAPTION_TOP_PAD_FRAC = 0.35


CHART_CAPTION_TOP_SEARCH_FRAC = 0.2


CHART_CAPTION_TOP_GUARD_FRAC = 0.01


CHART_CAPTION_TOP_BLOCK_H_OVERLAP = 0.3


CHART_CAPTION_MERGE_MAX_GAP_FRAC = 0.18


CHART_CAPTION_INTERNAL_TOP_TOL_PX = 18.0


CHART_CAPTION_INTERNAL_TOP_TOL_FRAC = 0.02


CHART_CAPTIONED_DRAW_MAX_ASPECT = 3.4


CHART_CROP_PAD_COMPENSATION = 8


CHART_NOTE_PAD_EXTRA = 24


CHART_NOTE_BELOW_GUARD_PX = 3


CHART_NOTE_BELOW_MIN_H_OVERLAP = 0.2


CHART_LABEL_MAX_GAP_FRAC = 0.06


CHART_LABEL_MAX_V_GAP_FRAC = 0.05


CHART_LABEL_MIN_V_OVERLAP = 0.35


CHART_LABEL_MIN_H_OVERLAP = 0.35


CHART_LABEL_PARAGRAPH_MIN_LINES = 3


CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN = 32


CHART_LABEL_MAX_LINES = 6


CHART_LABEL_MAX_AVG_LINE_LEN = 40


CHART_LABEL_MAX_HEIGHT_FRAC = 0.5


CHART_LABEL_COMPACT_TITLE_MAX_LINES = 2


CHART_LABEL_COMPACT_TITLE_MAX_AVG_LINE_LEN = 72


CHART_LABEL_COMPACT_TITLE_MAX_CHARS = 120


CHART_NEXT_BLOCKER_MIN_GAP_FRAC = 0.08


CHART_NEXT_BLOCKER_MIN_GAP_PX = 48.0


CHART_NEXT_BLOCKER_MIN_H_OVERLAP = 0.3


CHART_NEXT_BLOCKER_GUARD_PX = 4.0


CHART_EDGE_TEXT_MIN_GAP_FRAC = 0.08


CHART_EDGE_TEXT_MAX_PAD_FRAC = 0.12


CHART_EDGE_TEXT_MIN_GAP_X_FRAC = 0.04


CHART_EDGE_TEXT_MAX_PAD_X_FRAC = 0.06


CHART_EDGE_TEXT_HEADING_GAP_SCALE = 0.4


CHART_EDGE_TEXT_HEADING_GAP_X_SCALE = 0.5


CHART_WHITESPACE_GUARD_GAP_FRAC = 0.02


CHART_WHITESPACE_GUARD_GAP_X_FRAC = 0.02


CHART_WHITESPACE_MAX_PAD_FRAC = 0.06


CHART_WHITESPACE_MAX_PAD_X_FRAC = 0.05


CHART_WHITESPACE_MIN_OVERLAP = 0.3


CHART_HEADING_TOP_MAX_PAD_FRAC = 0.0


CHART_HEADING_TOP_SEARCH_FRAC = 0.25


CHART_HEADING_TOP_GUARD_FRAC = 0.01


CHART_HEADING_TOP_BLOCK_H_OVERLAP = 0.3


CHART_HEADING_MERGE_MAX_GAP_FRAC = 0.08


DRAWING_MIN_RECT_DIM = 6.0


DRAWING_MIN_RECT_AREA = 200.0


DRAWING_BACKGROUND_MIN_AREA_FRAC = 0.9


DRAWING_BACKGROUND_MAX_STROKE = 1.0


INFO_HEADING_MIN_WORDS = 3


INFO_HEADING_MIN_ALPHA_RATIO = 0.55


INFO_HEADING_MIN_SIZE = 12.0


INFO_HEADING_SIZE_DELTA = 2.0


INFO_HEADING_MAX_WORDS = 30


INFO_HEADING_MAX_CHARS = 160


INFO_HEADING_MAX_SENTENCES = 2


INFO_HEADING_MERGE_GAP_FRAC = 0.012


INFO_HEADING_MERGE_SIZE_DELTA = 2.0


INFO_HEADING_MERGE_H_OVERLAP = 0.4


INFO_CHART_MIN_DRAWINGS = 5


INFO_CHART_MIN_AREA_FRAC = 0.04


INFO_CHART_BAND_FRAC = 0.6


INFO_CHART_MAX_GAP_FRAC = 0.25


INFO_CHART_CLUSTER_GAP_FRAC = 0.05


INFO_CHART_MAX_ASPECT = 4.0


PANEL_CHART_MIN_AREA_FRAC = 0.035


PANEL_CHART_MAX_AREA_FRAC = 0.75


PANEL_CHART_CONNECT_GAP_FRAC = 0.015


PANEL_CHART_TITLE_MIN_SIZE = 15.0


PANEL_CHART_TITLE_MIN_WORDS = 2


PANEL_CHART_TITLE_MAX_WORDS = 12


PANEL_CHART_TITLE_MAX_CHARS = 120


PANEL_CHART_TITLE_MAX_SENTENCES = 1


PANEL_CHART_LOCAL_TITLE_MIN_SIZE = 10.5


PANEL_CHART_LOCAL_TITLE_TOP_FRAC = 0.38


PANEL_CHART_LOCAL_TITLE_MAX_HEIGHT_RATIO = 0.22


PANEL_CHART_LOCAL_TITLE_MIN_WIDTH_RATIO = 0.18


PANEL_CHART_LOCAL_TITLE_MAX_WIDTH_RATIO = 0.75


PANEL_CHART_TITLE_SLICE_Y_TOL = 14.0


PANEL_CHART_TITLE_SLICE_SIZE_TOL = 3.0


PANEL_CHART_TITLE_SLICE_X_PAD_FRAC = 0.03


CHART_AXIS_LABEL_BAND_MAX_LINES = 48


CHART_AXIS_LABEL_BAND_MAX_AVG_LINE_LEN = 12.0


CHART_AXIS_LABEL_BAND_MIN_TOKEN_HITS = 4


CHART_AXIS_LABEL_BAND_MIN_ALPHA_RATIO = 0.45


PANEL_CHART_TITLE_MAX_GAP = 72.0


PANEL_CHART_TITLE_NEAREST_TOL = 24.0


PANEL_CHART_TITLE_X_PAD = 72.0


PANEL_CHART_SPLIT_MIN_CENTER_GAP_FRAC = 0.12


PANEL_CHART_SPLIT_SLICE_X_PAD_FRAC = 0.025


PANEL_CHART_SPLIT_MIN_WIDTH_RATIO = 0.6


PANEL_CHART_TITLE_STACK_MAX_GAP = 20.0


PANEL_CHART_TITLE_STACK_MIN_H_OVERLAP = 0.45


PANEL_CHART_TITLE_STACK_MAX_EDGE_DELTA = 72.0


PANEL_CHART_SHARED_COMPONENT_MAX_SIDE_GAP_FRAC = 0.08


PANEL_CHART_SHARED_COMPONENT_MIN_V_OVERLAP = 0.55


PANEL_CHART_SHARED_COMPONENT_MAX_STACK_GAP_FRAC = 0.10


PANEL_CHART_SHARED_COMPONENT_MIN_H_ALIGN = 0.65


PANEL_CHART_SHARED_COMPONENT_MIN_WIDTH_RATIO = 0.55


PANEL_CHART_SHARED_COMPONENT_MIN_HEIGHT_RATIO = 0.18


PANEL_CONTEXT_CARD_MAX_SIDE_GAP_FRAC = 0.06


PANEL_CONTEXT_CARD_MIN_V_OVERLAP = 0.55


PANEL_CONTEXT_CARD_MIN_HEIGHT_RATIO = 0.55


PANEL_CONTEXT_CARD_MIN_TEXT_CHARS = 60


PANEL_CONTEXT_CARD_MAX_COMPONENT_OVERLAP = 0.35


NOTE_LABEL_PREFIXES = ("note:", "notes:", "source:", "sources:", "statlink")


EMAIL_ADDRESS_RX = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


_PAGE_NUMBER_RX = re.compile(
    r"^\s*[^0-9A-Za-z]*\d{1,4}(?:\s*[-–]\s*\d{1,4})?[^0-9A-Za-z]*\s*$"
)


_PANEL_TITLE_EXCLUDE_RX = re.compile(
    r"^\s*(?:figure|fig\.|exhibit|chart|graph|table|source|infographic)\b",
    re.IGNORECASE,
)


from ._visual_heuristics.shared import *


_LOCAL_PRIVATE_EXPORTS = [
    "_ChartRect",
    "_VisualCandidateRelationships",
    "_PageTextLine",
    "_s",
    "_int_count",
    "_rect_iou",
    "_table_normalize_text",
    "_starts_with_lower_alpha",
    "_table_page_text_lines",
    "_rect_containment_ratio",
    "_rect_seen",
    "_chart_candidate_score",
    "_find_overlapping_kept",
    "_rect_overlap_area",
    "_line_starts_with_caption_hint",
    "_alpha_ratio",
    "_is_page_number_text",
    "_horizontal_overlap_ratio",
    "_vertical_overlap_ratio",
    "_pad_rect",
    "_save_thumb",
    "_nearby_text",
    "_candidate_index_from_id",
    "_merge_stats",
    "_split_even_chunks",
    "_resolve_candidate_parallel_workers",
    "_text_stats",
    "_text_line_lengths",
    "_chart_text_heavy",
    "_chart_is_label_dense_not_prose",
    "_infographic_is_label_dense_not_prose",
    "_trim_top_page_number",
    "_rect_intersection_area",
    "_tally_reason",
]
_CHART_LAYOUT_EXPORTS = [
    "_image_block_rects",
    "_drawing_rects",
    "_chart_axis_label_band_like",
    "_compact_top_chart_title_like",
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
_PANEL_TEXT_EXPORTS = [
    "_panel_title_lines",
    "_panel_lowercase_title_has_metric_context",
    "_panel_local_title_line",
    "_panel_preferred_local_title_line",
    "_panel_titles_form_multiline_band",
    "_shared_row_panel_title_line",
    "_panel_title_slice_bounds",
    "_panel_chart_is_label_dense_not_prose",
    "_numeric_token_hits",
    "_panel_chart_has_metric_signal",
    "_panel_label_block_looks_like_footer_banner",
    "_panel_chart_has_data_signal",
    "_panel_component_text_from_blocks",
    "_panel_component_has_chart_signal",
    "_panel_component_looks_like_independent_data_panel",
    "_panel_component_looks_like_guidance_card",
    "_panel_chart_has_structured_card_signal",
    "_panel_caption_looks_like_compact_metric",
    "_panel_chart_has_compact_stat_card_signal",
    "_panel_caption_looks_top_band",
]
_PANEL_GEOMETRY_EXPORTS = [
    "_extend_panel_rect_with_nearby_label_blocks",
    "_drawing_components",
    "_shared_title_component_group",
    "_stacked_panel_group_has_intervening_text",
    "_extend_panel_rect_with_adjacent_drawings",
    "_clamp_panel_rect_to_dominant_fill_rect",
    "_extend_panel_with_adjacent_text_blocks",
]
_PANEL_DETECTION_EXPORTS = [
    "_panel_should_clamp_to_internal_caption",
    "_panel_candidate_shadowed_by_heading_candidate",
    "_panel_candidate_shadowed_by_larger_panel",
    "_panel_stacked_bottom_clip_y",
    "_panel_neighbor_x_bounds",
    "_page_looks_like_contents_layout",
    "_panel_chart_rects",
    "_merge_panel_title_band_candidates",
]
_COLLECTOR_EXPORTS = ["_collect_chart_rects"]

if TYPE_CHECKING:
    _adjust_rect_for_text_margins: Any
    _caption_blocks: Any
    _caption_near_top: Any
    _caption_top_block_limit: Any
    _chart_axis_label_band_like: Any
    _clamp_bottom_to_next_chart_blocker: Any
    _clamp_bottom_to_note: Any
    _clamp_panel_rect_to_dominant_fill_rect: Any
    _clamp_top_to_caption: Any
    _clamp_top_to_heading: Any
    _cluster_rects_by_y: Any
    _collect_chart_rects: Any
    _compact_top_chart_title_like: Any
    _drawing_caption_rects: Any
    _drawing_components: Any
    _drawing_rects: Any
    _expand_rect_into_whitespace: Any
    _extend_chart_rect_with_adjacent_drawings: Any
    _extend_panel_rect_with_adjacent_drawings: Any
    _extend_panel_rect_with_nearby_label_blocks: Any
    _extend_panel_with_adjacent_text_blocks: Any
    _extend_with_adjacent_text_blocks: Any
    _extend_with_heading_above: Any
    _extend_with_note_blocks: Any
    _has_internal_top_text: Any
    _has_intervening_paragraph: Any
    _heading_chart_rects: Any
    _heading_lines: Any
    _heading_top_block_limit: Any
    _image_block_rects: Any
    _merge_caption_above: Any
    _merge_panel_title_band_candidates: Any
    _nearest_caption_block: Any
    _nearest_heading_above: Any
    _next_block_top_below: Any
    _next_chart_blocker_top: Any
    _note_block_bottom: Any
    _numeric_token_hits: Any
    _page_looks_like_contents_layout: Any
    _panel_candidate_shadowed_by_heading_candidate: Any
    _panel_candidate_shadowed_by_larger_panel: Any
    _panel_caption_looks_like_compact_metric: Any
    _panel_caption_looks_top_band: Any
    _panel_chart_has_compact_stat_card_signal: Any
    _panel_chart_has_data_signal: Any
    _panel_chart_has_metric_signal: Any
    _panel_chart_has_structured_card_signal: Any
    _panel_chart_is_label_dense_not_prose: Any
    _panel_chart_rects: Any
    _panel_component_has_chart_signal: Any
    _panel_component_looks_like_guidance_card: Any
    _panel_component_looks_like_independent_data_panel: Any
    _panel_component_text_from_blocks: Any
    _panel_label_block_looks_like_footer_banner: Any
    _panel_local_title_line: Any
    _panel_lowercase_title_has_metric_context: Any
    _panel_neighbor_x_bounds: Any
    _panel_preferred_local_title_line: Any
    _panel_should_clamp_to_internal_caption: Any
    _panel_stacked_bottom_clip_y: Any
    _panel_title_lines: Any
    _panel_title_slice_bounds: Any
    _panel_titles_form_multiline_band: Any
    _shared_row_panel_title_line: Any
    _shared_title_component_group: Any
    _stacked_panel_group_has_intervening_text: Any

__all__ = [
    name
    for name in globals()
    if not name.startswith("__")
    and name
    not in {
        "TYPE_CHECKING",
        "_LOCAL_PRIVATE_EXPORTS",
        "_CHART_LAYOUT_EXPORTS",
        "_PANEL_TEXT_EXPORTS",
        "_PANEL_GEOMETRY_EXPORTS",
        "_PANEL_DETECTION_EXPORTS",
        "_COLLECTOR_EXPORTS",
    }
]
__all__ += _LOCAL_PRIVATE_EXPORTS

from ._visual_heuristics.chart_layout import *
from ._visual_heuristics.panel_text import *
from ._visual_heuristics.panel_geometry import *
from ._visual_heuristics.panel_detection import *
from ._visual_heuristics.collectors import *

__all__ += (
    _CHART_LAYOUT_EXPORTS
    + _PANEL_TEXT_EXPORTS
    + _PANEL_GEOMETRY_EXPORTS
    + _PANEL_DETECTION_EXPORTS
    + _COLLECTOR_EXPORTS
)
