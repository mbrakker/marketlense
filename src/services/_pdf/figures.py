from __future__ import annotations

# ruff: noqa: F401,F811

import io
import logging
import math
import os
import re
import statistics
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pdfplumber
import pymupdf as fitz
from PIL import Image

from src.contracts.candidates import Candidate
from src.contracts.report_assets import (
    ExtractCandidatesRequest,
    ExtractCandidatesResponse,
    FigureExtractRequest,
    FigureExtractResponse,
    PdfCandidatePageTriageRecord,
    PdfCandidateExtractionStats,
    PdfDegradedPage,
)
from src.contracts.run_context import RunContext
from src.utils.candidate_features import candidate_features
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.path_utils import safe_path_segment
from src.utils.slugify import slugify

from .page_artifacts import (
    PdfPageArtifactCache,
    create_page_artifact_cache,
    get_page_artifacts,
)
from .shared import candidate_logger, figure_logger

# Compatibility re-exports for legacy tests and crop helpers. New extraction
# capabilities import shared heuristics from table_heuristics/visual_heuristics.
from .table_heuristics import (
    TABLE_CONTACT_MAX_COLS,
    TABLE_CONTACT_MAX_NUMERIC_RATIO,
    TABLE_CONTACT_MIN_AREA_FRAC,
    TABLE_CONTACT_MIN_AVG_LINE_LEN,
    TABLE_CONTACT_MIN_LINES,
    TABLE_CONTENTS_GRID_MAX_AVG_LINE_LEN,
    TABLE_CONTENTS_GRID_MAX_AVG_WORDS,
    TABLE_CONTENTS_GRID_MAX_COLS,
    TABLE_CONTENTS_GRID_MAX_FIRST_COL_WORDS,
    TABLE_CONTENTS_GRID_MAX_NUMERIC_RATIO,
    TABLE_CONTENTS_GRID_MIN_AREA,
    TABLE_CONTENTS_GRID_MIN_COLS,
    TABLE_CONTENTS_GRID_MIN_NUMBERED_LINES,
    TABLE_CONTENTS_GRID_MIN_NUMERIC_RATIO,
    TABLE_CONTENTS_GRID_MIN_ROWS,
    TABLE_CONTENTS_GRID_MIN_UPPERCASE_SHORT_RATIO,
    TABLE_CONTENTS_MAX_AVG_WORDS_PER_CELL,
    TABLE_CONTENTS_MAX_FILLED_CELLS_PER_ROW,
    TABLE_CONTENTS_MAX_FIRST_COL_WORDS,
    TABLE_CONTENTS_MAX_NUMERIC_RATIO,
    TABLE_CONTENTS_MIN_COLS,
    TABLE_CONTENTS_MIN_NUMERIC_RATIO,
    TABLE_CONTENTS_MIN_ROWS,
    TABLE_DEDUP_IOU,
    TABLE_EXPAND_HEADING_MAX_AVG_LINE_LEN,
    TABLE_EXPAND_HEADING_MAX_LINES,
    TABLE_EXPAND_HEADING_MAX_SENTENCES,
    TABLE_EXPAND_HEADING_MIN_ALPHA_RATIO,
    TABLE_EXPAND_MAX_GAP_FRAC,
    TABLE_EXPAND_MIN_H_OVERLAP,
    TABLE_EXPAND_STREAM_WIDE_MIN_HEIGHT_FRAC,
    TABLE_EXPAND_STREAM_WIDE_MIN_WIDTH_FRAC,
    TABLE_EXPLICIT_SUBTITLE_MAX_GAP,
    TABLE_EXPLICIT_TITLE_MAX_GAP,
    TABLE_FIGURE_FRAGMENT_COMPACT_MAX_AREA_FRAC,
    TABLE_FIGURE_FRAGMENT_COMPACT_MAX_ROWS,
    TABLE_FIGURE_FRAGMENT_MAX_AVG_WORDS_PER_CELL,
    TABLE_FIGURE_FRAGMENT_MAX_FILL_RATIO,
    TABLE_FIGURE_FRAGMENT_MIN_NUMERIC_RATIO,
    TABLE_FIGURE_FRAGMENT_MIN_WIDE_COLS,
    TABLE_FRONT_MATTER_MAX_AVG_WORDS_PER_CELL,
    TABLE_FRONT_MATTER_MAX_COLS,
    TABLE_FRONT_MATTER_MAX_NUMERIC_RATIO,
    TABLE_FRONT_MATTER_MIN_AREA_FRAC,
    TABLE_FRONT_MATTER_TERMS,
    TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_AVG_LINE_LEN,
    TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_GAP_FRAC,
    TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_LINES,
    TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_V_OVERLAP,
    TABLE_HORIZONTAL_EXPAND_MAX_GAP_FRAC,
    TABLE_HORIZONTAL_EXPAND_MIN_GAIN,
    TABLE_HORIZONTAL_EXPAND_MIN_V_OVERLAP,
    TABLE_INDEX_MAX_COLS,
    TABLE_INDEX_MIN_FIRST_COL_WORDS,
    TABLE_INDEX_MIN_ROWS,
    TABLE_INDEX_PAGE_RATIO,
    TABLE_MAX_ASPECT,
    TABLE_MIN_AREA_FRAC,
    TABLE_MIN_ASPECT,
    TABLE_MIN_COLS,
    TABLE_MIN_HEIGHT_FRAC,
    TABLE_MIN_NONEMPTY_CELLS,
    TABLE_MIN_ROWS,
    TABLE_MIN_TEXT_CHARS,
    TABLE_MIN_WIDTH_FRAC,
    TABLE_NOTE_CONTINUATION_MAX_X_OFFSET,
    TABLE_NOTE_CONTINUATION_MIN_H_OVERLAP,
    TABLE_NOTE_CONTINUATION_MIN_WORDS,
    TABLE_OVERLAPPING_NOTE_MAX_GAP,
    TABLE_PROSE_BOX_LINECOUNT_EXTRA,
    TABLE_PROSE_BOX_MAX_FILLED_CELLS_PER_ROW,
    TABLE_PROSE_BOX_MAX_LINECOUNT_ROW_MULT,
    TABLE_PROSE_BOX_MAX_NUMERIC_RATIO,
    TABLE_PROSE_BOX_MIN_COLS,
    TABLE_PROSE_BOX_MIN_FIRST_COL_WORDS,
    TABLE_PROSE_BOX_MIN_ROWS,
    TABLE_PROSE_BOX_MIN_TEXT_BLOCK_AREA,
    TABLE_PROSE_BOX_MIN_TEXT_BLOCK_AVG_LINE_LEN,
    TABLE_RANKED_BODY_MAX_GAP,
    TABLE_RANKED_HEADER_MAX_GAP,
    TABLE_RANKED_HEADER_SEED_MAX_GAP,
    TABLE_RANKED_MAX_RANK,
    TABLE_RANKED_MAX_ROW_GAP_FRAC,
    TABLE_RANKED_MIN_ROWS,
    TABLE_RANKED_MIN_RULE_WIDTH_FRAC,
    TABLE_RANKED_NOTE_MAX_GAP,
    TABLE_RANKED_NOTE_X_TOL,
    TABLE_RANKED_RULE_X_TOL,
    TABLE_RANKED_X_CLUSTER_GAP_FRAC,
    TABLE_REFERENCE_MAX_COLS,
    TABLE_REFERENCE_MAX_FILLED_CELLS_PER_ROW,
    TABLE_REFERENCE_MAX_NUMERIC_RATIO,
    TABLE_REFERENCE_MIN_AVG_LINE_LEN,
    TABLE_REFERENCE_MIN_AVG_WORDS_PER_CELL,
    TABLE_REFERENCE_MIN_FIRST_COL_WORDS,
    TABLE_REFERENCE_MIN_NUMBERED_HITS,
    TABLE_REFERENCE_MIN_ROWS,
    TABLE_REFERENCE_MIN_TERM_HITS,
    TABLE_REFERENCE_MIN_URL_HITS,
    TABLE_REFERENCE_MIN_YEAR_HITS,
    TABLE_REFERENCE_TERMS,
    TABLE_SECTION_LIST_MAX_AREA_FRAC_WITHOUT_NUMBERS,
    TABLE_SECTION_LIST_MAX_AVG_LINE_LEN,
    TABLE_SECTION_LIST_MAX_AVG_WORDS_PER_CELL,
    TABLE_SECTION_LIST_MAX_COLS,
    TABLE_SECTION_LIST_MAX_NARROW_ASPECT,
    TABLE_SECTION_LIST_MAX_NUMERIC_RATIO,
    TABLE_SECTION_LIST_MIN_FRAGMENTED_DOT_HITS,
    TABLE_SECTION_LIST_MIN_ROWS,
    TABLE_SECTION_LIST_MIN_SHORT_LINE_RATIO,
    TABLE_SECTION_LIST_MIN_TERMINAL_NUMBER_HITS,
    TABLE_SECTION_LIST_MIN_TEXT_BLOCK_AREA,
    TABLE_SETTINGS_LATTICE,
    TABLE_SETTINGS_STREAM,
    TABLE_STREAM_CONTINUATION_MAX_BANDS,
    TABLE_STREAM_CONTINUATION_MAX_GAP,
    TABLE_STREAM_CONTINUATION_MAX_GAP_FRAC,
    TABLE_STREAM_CONTINUATION_MIN_NUMERIC_FRAGMENTS,
    TABLE_STREAM_INFOBOX_MAX_AVG_WORDS,
    TABLE_STREAM_INFOBOX_MAX_COLS,
    TABLE_STREAM_INFOBOX_MAX_NUMERIC_RATIO,
    TABLE_STREAM_INFOBOX_MAX_ROW_LEN_CV,
    TABLE_STREAM_INFOBOX_MIN_AREA,
    TABLE_STREAM_INFOBOX_MIN_LINES,
    TABLE_STREAM_INFOBOX_MIN_ROWS,
    TABLE_STREAM_LIST_MAX_AREA_FRAC,
    TABLE_STREAM_LIST_MAX_AVG_WORDS,
    TABLE_STREAM_LIST_MAX_COLS,
    TABLE_STREAM_LIST_MAX_NUMERIC_RATIO,
    TABLE_STREAM_LIST_MIN_ROWS,
    TABLE_STREAM_MAX_ROW_LEN_CV,
    TABLE_STREAM_MIN_COLS_FOR_LIKENESS,
    TABLE_STREAM_MIN_COL_CONSISTENCY,
    TABLE_STREAM_MIN_ROWS_FOR_LIKENESS,
    TABLE_STREAM_PANEL_MAX_AVG_WORDS,
    TABLE_STREAM_PANEL_MAX_COLS,
    TABLE_STREAM_PANEL_MAX_NUMERIC_RATIO,
    TABLE_STREAM_PANEL_MIN_AREA_FRAC,
    TABLE_STREAM_PANEL_MIN_ROWS,
    TABLE_STREAM_SLIDE_CARD_LINE_PAD,
    TABLE_STREAM_SLIDE_CARD_MAX_AREA,
    TABLE_STREAM_SLIDE_CARD_MAX_AVG_WORDS,
    TABLE_STREAM_SLIDE_CARD_MAX_COLS,
    TABLE_STREAM_SLIDE_CARD_MAX_COL_CONSISTENCY,
    TABLE_STREAM_SLIDE_CARD_MAX_NUMERIC_RATIO,
    TABLE_STREAM_SLIDE_CARD_MIN_AREA,
    TABLE_STREAM_SLIDE_CARD_MIN_AVG_LINE_LEN,
    TABLE_STREAM_SLIDE_CARD_MIN_AVG_WORDS,
    TABLE_STREAM_SLIDE_CARD_MIN_LINES,
    TABLE_STREAM_SLIDE_CARD_MIN_ROWS,
    TABLE_STREAM_SLIDE_CARD_MIN_TEXT_BLOCK_AREA,
    TABLE_STREAM_SPARSE_MAX_COLS,
    TABLE_STREAM_SPARSE_MAX_LINES,
    TABLE_STREAM_SPARSE_MAX_NUMERIC_RATIO,
    TABLE_STREAM_SPARSE_MIN_AREA,
    TABLE_STREAM_SPARSE_MIN_AVG_LINE_LEN,
    TABLE_STREAM_TEXTBLOCK_MAX_COL_CONSISTENCY,
    TABLE_STREAM_TEXTBLOCK_MAX_FILL_RATIO,
    TABLE_STREAM_TEXTBLOCK_MAX_NUMERIC_RATIO,
    TABLE_STREAM_TEXTBLOCK_MIN_AREA,
    TABLE_STREAM_TEXTBLOCK_MIN_AVG_LINE_LEN,
    TABLE_STREAM_TEXTBLOCK_MIN_LINES,
    TABLE_STREAM_TEXTBLOCK_MIN_ROW_LEN_CV,
    TABLE_STREAM_TEXTY_MAX_NUMERIC_RATIO,
    TABLE_STREAM_TEXTY_MIN_AREA,
    TABLE_STREAM_TEXTY_MIN_AVG_LINE_LEN,
    TABLE_STREAM_TEXTY_MIN_COLS,
    TABLE_STREAM_TEXTY_MIN_LINES,
    TABLE_STREAM_TEXTY_MIN_ROWS,
    TABLE_TEXT_HEAVY_MAX_NUMERIC_RATIO,
    TABLE_TEXT_HEAVY_MIN_AVG_WORDS,
    TABLE_TEXT_HEAVY_MIN_ROWS,
    TABLE_TOP_HEADER_SLACK_MAX,
    TABLE_TOP_SLACK_MAX,
    TABLE_VISUAL_QUOTE_MAX_ASPECT,
    TABLE_VISUAL_QUOTE_MAX_AVG_WORDS_PER_CELL,
    TABLE_VISUAL_QUOTE_MAX_COLS,
    TABLE_VISUAL_QUOTE_MAX_FILLED_CELLS_PER_ROW,
    TABLE_VISUAL_QUOTE_MAX_NUMERIC_RATIO,
    TABLE_VISUAL_QUOTE_MAX_ROWS,
    TABLE_VISUAL_QUOTE_MAX_TEXT_BLOCK_AREA,
    TABLE_VISUAL_QUOTE_MAX_TEXT_LEN,
    TABLE_VISUAL_QUOTE_MAX_WIDTH_FRAC,
    TABLE_VISUAL_QUOTE_MIN_HEIGHT_FRAC,
    TABLE_WIDE_FIGURE_CONTEXT_HORIZONTAL_PAD,
    TABLE_WIDE_FIGURE_CONTEXT_MAX_DIST,
    TABLE_WIDE_FIGURE_CONTEXT_TOP_BAND,
    TEXT_BLOCK_LOOSE_MAX_NUMERIC_RATIO,
    TEXT_BLOCK_LOOSE_MIN_AVG_LINE_LEN,
    TEXT_BLOCK_LOOSE_MIN_LINES,
    TEXT_BLOCK_MAX_NUMERIC_RATIO,
    TEXT_BLOCK_MIN_AREA_FRAC,
    TEXT_BLOCK_MIN_AVG_LINE_LEN,
    TEXT_BLOCK_MIN_LINES,
    _FIGURE_CONTEXT_RX,
    _PDFMINER_LOGGERS,
    _PageTextBlock,
    _RankedTableRegion,
    _TABLE_FOOTNOTE_RX,
    _TableCandidate,
    _TableTextBand,
    _avg_first_col_words,
    _avg_words_per_cell,
    _cell_is_numeric,
    _cell_is_page_number,
    _cell_words,
    _chart_fragment_like,
    _cluster_is_row_continuation,
    _col_consistency,
    _compose_table_bbox,
    _contact_block_like,
    _contents_grid_like,
    _contents_like,
    _dedupe_table_candidates,
    _detect_ranked_table_candidates,
    _expand_table_bbox,
    _extract_text_in_bbox,
    _filled_cells_per_row,
    _front_matter_like,
    _group_rank_blocks_into_sequences,
    _has_caption_hint,
    _has_figure_context_hint,
    _heading_like_block,
    _index_page_ratio,
    _nonempty_text_lines,
    _numeric_char_ratio,
    _prefer_inner_lattice_table,
    _prose_box_like,
    _ranked_table_panel_region,
    _reference_block_like,
    _row_len_cv,
    _row_nonempty_counts,
    _row_text_lengths,
    _section_list_like,
    _shrink_stream_table_rect,
    _stream_infobox_like,
    _stream_list_like,
    _stream_low_consistency,
    _stream_multilist_infographic_like,
    _stream_panel_like,
    _stream_slide_card_like,
    _stream_sparse_text_like,
    _stream_text_block_like,
    _stream_text_layout_like,
    _suppress_pdfminer_warnings,
    _table_attach_explicit_title_context,
    _table_attach_mixed_footer_blocks,
    _table_attach_note_bands,
    _table_attach_note_blocks,
    _table_attach_title_bands,
    _table_attach_title_blocks,
    _table_band_is_body_paragraph,
    _table_band_is_heading_like,
    _table_band_is_margin_noise,
    _table_band_is_note_continuation,
    _table_band_is_note_like,
    _table_band_is_row_like,
    _table_band_is_title_like,
    _table_block_is_body_paragraph,
    _table_block_is_heading_like,
    _table_block_is_margin_noise,
    _table_block_is_mixed_footer_cluster,
    _table_block_is_note_continuation,
    _table_block_is_note_like,
    _table_block_is_title_like,
    _table_block_looks_dense_tabular,
    _table_clamp_bottom_before_internal_heading,
    _table_clamp_top_to_internal_title,
    _table_clamp_top_to_internal_title_band,
    _table_containment_ratio,
    _table_expand_horizontal_to_content,
    _table_extend_overlapping_note_blocks,
    _table_fragment_is_numeric,
    _table_horizontal_rule_rects,
    _table_iou,
    _table_page_body_font_size,
    _table_page_text_blocks,
    _table_preview,
    _table_quality,
    _table_rank_value,
    _table_restore_top_slack,
    _table_sort_key,
    _table_text_bands,
    _table_text_has_embedded_note_marker,
    _table_text_has_figure_context,
    _table_text_has_note_marker,
    _table_text_lines,
    _table_text_starts_with_footnote_marker,
    _terminal_page_number_hits,
    _text_block_like,
    _text_block_like_loose,
    _text_block_stats,
    _validate_table_candidate,
    _visual_quote_page_like,
)
from .visual_heuristics import (
    CAPTION_HINTS,
    CHART_AXIS_LABEL_BAND_MAX_AVG_LINE_LEN,
    CHART_AXIS_LABEL_BAND_MAX_LINES,
    CHART_AXIS_LABEL_BAND_MIN_ALPHA_RATIO,
    CHART_AXIS_LABEL_BAND_MIN_TOKEN_HITS,
    CHART_CAPTIONED_DRAW_MAX_ASPECT,
    CHART_CAPTION_HINTS,
    CHART_CAPTION_INTERNAL_TOP_TOL_FRAC,
    CHART_CAPTION_INTERNAL_TOP_TOL_PX,
    CHART_CAPTION_MERGE_MAX_GAP_FRAC,
    CHART_CAPTION_TOP_BLOCK_H_OVERLAP,
    CHART_CAPTION_TOP_GUARD_FRAC,
    CHART_CAPTION_TOP_PAD_FRAC,
    CHART_CAPTION_TOP_PAD_PX,
    CHART_CAPTION_TOP_SEARCH_FRAC,
    CHART_CROP_PAD_COMPENSATION,
    CHART_DEDUP_IOU,
    CHART_DENSE_RECOVERY_MIN_CHARS,
    CHART_DENSE_RECOVERY_MIN_LINES,
    CHART_EDGE_TEXT_HEADING_GAP_SCALE,
    CHART_EDGE_TEXT_HEADING_GAP_X_SCALE,
    CHART_EDGE_TEXT_MAX_PAD_FRAC,
    CHART_EDGE_TEXT_MAX_PAD_X_FRAC,
    CHART_EDGE_TEXT_MIN_GAP_FRAC,
    CHART_EDGE_TEXT_MIN_GAP_X_FRAC,
    CHART_HEADING_MERGE_MAX_GAP_FRAC,
    CHART_HEADING_TOP_BLOCK_H_OVERLAP,
    CHART_HEADING_TOP_GUARD_FRAC,
    CHART_HEADING_TOP_MAX_PAD_FRAC,
    CHART_HEADING_TOP_SEARCH_FRAC,
    CHART_LABEL_COMPACT_TITLE_MAX_AVG_LINE_LEN,
    CHART_LABEL_COMPACT_TITLE_MAX_CHARS,
    CHART_LABEL_COMPACT_TITLE_MAX_LINES,
    CHART_LABEL_DENSE_LONG_LINE_LEN,
    CHART_LABEL_DENSE_MAX_AVG_LINE_LEN,
    CHART_LABEL_DENSE_MAX_LONG_LINE_RATIO,
    CHART_LABEL_DENSE_MAX_MEDIAN_LINE_LEN,
    CHART_LABEL_DENSE_MIN_LINES,
    CHART_LABEL_DENSE_MIN_SHORT_LINE_RATIO,
    CHART_LABEL_DENSE_SHORT_LINE_LEN,
    CHART_LABEL_MAX_AVG_LINE_LEN,
    CHART_LABEL_MAX_GAP_FRAC,
    CHART_LABEL_MAX_HEIGHT_FRAC,
    CHART_LABEL_MAX_LINES,
    CHART_LABEL_MAX_V_GAP_FRAC,
    CHART_LABEL_MIN_H_OVERLAP,
    CHART_LABEL_MIN_V_OVERLAP,
    CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN,
    CHART_LABEL_PARAGRAPH_MIN_LINES,
    CHART_MARGIN_FRAC,
    CHART_MARGIN_RELAX_FRAC,
    CHART_NEXT_BLOCKER_GUARD_PX,
    CHART_NEXT_BLOCKER_MIN_GAP_FRAC,
    CHART_NEXT_BLOCKER_MIN_GAP_PX,
    CHART_NEXT_BLOCKER_MIN_H_OVERLAP,
    CHART_NOTE_BELOW_GUARD_PX,
    CHART_NOTE_BELOW_MIN_H_OVERLAP,
    CHART_NOTE_MAX_DIST,
    CHART_NOTE_MAX_GAP_X_FRAC,
    CHART_NOTE_PAD_EXTRA,
    CHART_OVERLAP_CONTAINMENT,
    CHART_OVERLAP_IOU,
    CHART_PAD_X_FRAC,
    CHART_PAD_Y_FRAC,
    CHART_TEXT_MAX_LINES,
    CHART_TEXT_MIN_CHARS,
    CHART_TEXT_RATIO_THRESHOLD,
    CHART_WHITESPACE_GUARD_GAP_FRAC,
    CHART_WHITESPACE_GUARD_GAP_X_FRAC,
    CHART_WHITESPACE_MAX_PAD_FRAC,
    CHART_WHITESPACE_MAX_PAD_X_FRAC,
    CHART_WHITESPACE_MIN_OVERLAP,
    DRAWING_BACKGROUND_MAX_STROKE,
    DRAWING_BACKGROUND_MIN_AREA_FRAC,
    DRAWING_MIN_RECT_AREA,
    DRAWING_MIN_RECT_DIM,
    EMAIL_ADDRESS_RX,
    INFOGRAPHIC_LABEL_DENSE_MAX_AVG_LINE_LEN,
    INFOGRAPHIC_LABEL_DENSE_MAX_LONG_LINE_RATIO,
    INFOGRAPHIC_LABEL_DENSE_MAX_MEDIAN_LINE_LEN,
    INFOGRAPHIC_LABEL_DENSE_MIN_SHORT_LINE_RATIO,
    INFO_CHART_BAND_FRAC,
    INFO_CHART_CLUSTER_GAP_FRAC,
    INFO_CHART_MAX_ASPECT,
    INFO_CHART_MAX_GAP_FRAC,
    INFO_CHART_MIN_AREA_FRAC,
    INFO_CHART_MIN_DRAWINGS,
    INFO_HEADING_MAX_CHARS,
    INFO_HEADING_MAX_SENTENCES,
    INFO_HEADING_MAX_WORDS,
    INFO_HEADING_MERGE_GAP_FRAC,
    INFO_HEADING_MERGE_H_OVERLAP,
    INFO_HEADING_MERGE_SIZE_DELTA,
    INFO_HEADING_MIN_ALPHA_RATIO,
    INFO_HEADING_MIN_SIZE,
    INFO_HEADING_MIN_WORDS,
    INFO_HEADING_SIZE_DELTA,
    NOTE_LABEL_PREFIXES,
    PAGE_FOOTER_BANNER_LINE_RX,
    PANEL_CHART_CONNECT_GAP_FRAC,
    PANEL_CHART_INTERNAL_CAPTION_MAX_AVG_LINE_LEN,
    PANEL_CHART_INTERNAL_CAPTION_MAX_CHARS,
    PANEL_CHART_INTERNAL_CAPTION_MAX_LINES,
    PANEL_CHART_INTERNAL_CAPTION_MIN_WIDTH_RATIO,
    PANEL_CHART_INTERNAL_CAPTION_TOP_GAP_MAX,
    PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD,
    PANEL_CHART_LABEL_ATTACH_MAX_AREA_FRAC,
    PANEL_CHART_LABEL_ATTACH_MAX_AVG_LINE_LEN,
    PANEL_CHART_LABEL_ATTACH_MAX_CHARS,
    PANEL_CHART_LABEL_ATTACH_MAX_GAP_X_FRAC,
    PANEL_CHART_LABEL_ATTACH_MAX_GAP_Y_FRAC,
    PANEL_CHART_LABEL_ATTACH_MAX_LINES,
    PANEL_CHART_LABEL_ATTACH_MIN_H_OVERLAP,
    PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP,
    PANEL_CHART_LABEL_ATTACH_SKIP_OVERLAP_RATIO,
    PANEL_CHART_LOCAL_TITLE_MAX_HEIGHT_RATIO,
    PANEL_CHART_LOCAL_TITLE_MAX_WIDTH_RATIO,
    PANEL_CHART_LOCAL_TITLE_MIN_SIZE,
    PANEL_CHART_LOCAL_TITLE_MIN_WIDTH_RATIO,
    PANEL_CHART_LOCAL_TITLE_TOP_FRAC,
    PANEL_CHART_MAX_AREA_FRAC,
    PANEL_CHART_MIN_AREA_FRAC,
    PANEL_CHART_MIN_NUMERIC_HITS,
    PANEL_CHART_SHARED_COMPONENT_MAX_SIDE_GAP_FRAC,
    PANEL_CHART_SHARED_COMPONENT_MAX_STACK_GAP_FRAC,
    PANEL_CHART_SHARED_COMPONENT_MIN_HEIGHT_RATIO,
    PANEL_CHART_SHARED_COMPONENT_MIN_H_ALIGN,
    PANEL_CHART_SHARED_COMPONENT_MIN_V_OVERLAP,
    PANEL_CHART_SHARED_COMPONENT_MIN_WIDTH_RATIO,
    PANEL_CHART_SPLIT_MIN_CENTER_GAP_FRAC,
    PANEL_CHART_SPLIT_MIN_WIDTH_RATIO,
    PANEL_CHART_SPLIT_SLICE_X_PAD_FRAC,
    PANEL_CHART_TITLE_BAND_MERGE_MAX_AREA_RATIO,
    PANEL_CHART_TITLE_BAND_MERGE_MAX_GAP_FRAC,
    PANEL_CHART_TITLE_BAND_MERGE_MIN_H_OVERLAP,
    PANEL_CHART_TITLE_MAX_CHARS,
    PANEL_CHART_TITLE_MAX_GAP,
    PANEL_CHART_TITLE_MAX_SENTENCES,
    PANEL_CHART_TITLE_MAX_WORDS,
    PANEL_CHART_TITLE_MIN_SIZE,
    PANEL_CHART_TITLE_MIN_WORDS,
    PANEL_CHART_TITLE_NEAREST_TOL,
    PANEL_CHART_TITLE_SLICE_SIZE_TOL,
    PANEL_CHART_TITLE_SLICE_X_PAD_FRAC,
    PANEL_CHART_TITLE_SLICE_Y_TOL,
    PANEL_CHART_TITLE_STACK_MAX_EDGE_DELTA,
    PANEL_CHART_TITLE_STACK_MAX_GAP,
    PANEL_CHART_TITLE_STACK_MIN_H_OVERLAP,
    PANEL_CHART_TITLE_X_PAD,
    PANEL_CHART_TOP_TITLE_ATTACH_COMPONENT_MIN_H_OVERLAP,
    PANEL_CHART_TOP_TITLE_ATTACH_MAX_CENTER_DELTA_FRAC,
    PANEL_CHART_TOP_TITLE_ATTACH_MAX_GAP_FRAC,
    PANEL_CHART_TOP_TITLE_ATTACH_MAX_HEIGHT_RATIO,
    PANEL_CHART_TOP_TITLE_ATTACH_MAX_LEFT_INSET_FRAC,
    PANEL_CHART_TOP_TITLE_ATTACH_MAX_SPILL_X_FRAC,
    PANEL_CHART_TOP_TITLE_ATTACH_MAX_WIDTH_RATIO,
    PANEL_CHART_TOP_TITLE_ATTACH_MIN_WIDTH_RATIO,
    PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MAX_CENTER_DELTA_FRAC,
    PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MAX_WIDTH_RATIO,
    PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MIN_WIDTH_RATIO,
    PANEL_CONTEXT_CARD_MAX_COMPONENT_OVERLAP,
    PANEL_CONTEXT_CARD_MAX_SIDE_GAP_FRAC,
    PANEL_CONTEXT_CARD_MIN_HEIGHT_RATIO,
    PANEL_CONTEXT_CARD_MIN_TEXT_CHARS,
    PANEL_CONTEXT_CARD_MIN_V_OVERLAP,
    PANEL_GUIDANCE_TITLE_RX,
    PDF_FIGURE_EXCEPTIONS,
    TABLE_CAPTION_HINTS,
    _ChartRect,
    _PAGE_NUMBER_RX,
    _PANEL_TITLE_EXCLUDE_RX,
    _PageTextLine,
    _adjust_rect_for_text_margins,
    _alpha_ratio,
    _candidate_index_from_id,
    _caption_blocks,
    _caption_near_top,
    _caption_top_block_limit,
    _chart_axis_label_band_like,
    _chart_candidate_score,
    _chart_is_label_dense_not_prose,
    _chart_text_heavy,
    _clamp_bottom_to_next_chart_blocker,
    _clamp_bottom_to_note,
    _clamp_panel_rect_to_dominant_fill_rect,
    _clamp_top_to_caption,
    _clamp_top_to_heading,
    _cluster_rects_by_y,
    _collect_chart_rects,
    _compact_top_chart_title_like,
    _drawing_caption_rects,
    _drawing_components,
    _drawing_rects,
    _expand_rect_into_whitespace,
    _extend_chart_rect_with_adjacent_drawings,
    _extend_panel_rect_with_adjacent_drawings,
    _extend_panel_rect_with_nearby_label_blocks,
    _extend_panel_with_adjacent_text_blocks,
    _extend_with_adjacent_text_blocks,
    _extend_with_heading_above,
    _extend_with_note_blocks,
    _find_overlapping_kept,
    _has_internal_top_text,
    _has_intervening_paragraph,
    _heading_chart_rects,
    _heading_lines,
    _heading_top_block_limit,
    _horizontal_overlap_ratio,
    _image_block_rects,
    _infographic_is_label_dense_not_prose,
    _int_count,
    _is_page_number_text,
    _line_starts_with_caption_hint,
    _merge_caption_above,
    _merge_panel_title_band_candidates,
    _merge_stats,
    _nearby_text,
    _nearest_caption_block,
    _nearest_heading_above,
    _next_block_top_below,
    _next_chart_blocker_top,
    _note_block_bottom,
    _numeric_token_hits,
    _pad_rect,
    _page_looks_like_contents_layout,
    _panel_candidate_shadowed_by_heading_candidate,
    _panel_candidate_shadowed_by_larger_panel,
    _panel_caption_looks_metric_stub,
    _panel_caption_looks_top_band,
    _panel_chart_has_compact_stat_card_signal,
    _panel_chart_has_data_signal,
    _panel_chart_has_metric_signal,
    _panel_chart_has_structured_card_signal,
    _panel_chart_is_label_dense_not_prose,
    _panel_chart_rects,
    _panel_component_has_chart_signal,
    _panel_component_looks_like_guidance_card,
    _panel_component_looks_like_independent_data_panel,
    _panel_component_text_from_blocks,
    _panel_label_block_looks_like_footer_banner,
    _panel_local_title_line,
    _panel_lowercase_title_has_metric_context,
    _panel_neighbor_x_bounds,
    _panel_preferred_local_title_line,
    _panel_should_clamp_to_internal_caption,
    _panel_stacked_bottom_clip_y,
    _panel_title_lines,
    _panel_title_slice_bounds,
    _panel_titles_form_multiline_band,
    _rect_containment_ratio,
    _rect_intersection_area,
    _rect_iou,
    _rect_overlap_area,
    _rect_seen,
    _resolve_candidate_parallel_workers,
    _s,
    _save_thumb,
    _shared_row_panel_title_line,
    _shared_title_component_group,
    _split_even_chunks,
    _stacked_panel_group_has_intervening_text,
    _starts_with_lower_alpha,
    _table_normalize_text,
    _table_page_text_lines,
    _tally_reason,
    _text_line_lengths,
    _text_stats,
    _trim_top_page_number,
    _vertical_overlap_ratio,
)

# BEGIN PDF CANDIDATE EXTRACTION
PDF_FIGURE_TRIAGE_EXCEPTIONS = (AppError,) + PDF_FIGURE_EXCEPTIONS

VISUAL_CONTEXT_HINTS = CAPTION_HINTS + ("infographic",)
PANEL_SHORT_PROPER_NAME_RX = re.compile(
    r"^[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+){0,2}$"
)
CROP_REFINE_BBOX_PAD_X_FRAC = 0.012
CROP_REFINE_BBOX_PAD_Y_FRAC = 0.015
CROP_REFINE_BBOX_PAD_MIN = 4.0
CROP_REFINE_BBOX_PAD_MAX = 20.0
CROP_REFINE_EDGE_TOUCH_TOL = 1.5
CROP_REFINE_EDGE_MIN_OVERLAP = 0.2
CROP_REFINE_EDGE_INCLUDE_OVERLAP_RATIO = 0.35
CROP_REFINE_EDGE_TRIM_OVERLAP_RATIO = 0.1
TABLE_CHART_SHADOW_IOU = 0.6
TABLE_CHART_SHADOW_CONTAINMENT = 0.85
TABLE_CHART_SHADOW_TOTAL_OVERLAP_RATIO = 0.75
TABLE_CHART_SHADOW_STREAM_MIN_AREA = 0.18
TABLE_CHART_SHADOW_STREAM_MIN_ROWS = 8
TABLE_CHART_SHADOW_STREAM_MIN_COLS = 4
TABLE_CHART_SHADOW_STREAM_MAX_NUMERIC_RATIO = 0.05
TABLE_CHART_SHADOW_STREAM_MAX_AVG_WORDS = 2.5
TABLE_CHART_SHADOW_LATTICE_MIN_AREA = 0.08
TABLE_CHART_SHADOW_LATTICE_MAX_ROWS = 4
TABLE_CHART_SHADOW_LATTICE_MAX_COLS = 4
TABLE_CHART_SHADOW_LATTICE_MAX_NUMERIC_RATIO = 0.08
TABLE_CHART_SHADOW_LATTICE_MIN_AVG_WORDS = 4.0
PANEL_CHART_LOCAL_TITLE_MAX_WORDS = 6
PANEL_CHART_LOCAL_TITLE_MAX_CHARS = 64
TABLE_EXPAND_LATTICE_MAX_GAP_FRAC = 0.08
TABLE_EXPAND_MAX_BLOCK_HEIGHT_FRAC = 0.4
TABLE_EXPAND_MAX_LINES = 4
TABLE_EXPAND_MAX_AVG_LINE_LEN = 60
TABLE_EXPAND_MIN_V_OVERLAP = 0.2
CHART_RANKED_TABLE_DUP_IOU = 0.65
CHART_RANKED_TABLE_DUP_CONTAINMENT = 0.82


def _panel_title_looks_short_proper_name(text: str) -> bool:
    normalized = _s(text).strip()
    if not normalized or len(normalized) > 28:
        return False
    if any(ch.isdigit() for ch in normalized):
        return False
    words = normalized.split()
    if not (1 <= len(words) <= 3):
        return False
    if normalized.upper() == normalized:
        return False
    return PANEL_SHORT_PROPER_NAME_RX.fullmatch(normalized) is not None


def _extract_charts_sequential(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    pages: Optional[List[int]] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from .visual_candidates import _extract_visuals_sequential

    return _extract_visuals_sequential(
        pdf_path,
        thumbs_dir,
        report_name,
        save_thumbs=save_thumbs,
        doc=doc,
        pages=pages,
        artifact_cache=artifact_cache,
    )


def _extract_charts(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    parallel_workers: int = 1,
    pages: Optional[List[int]] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from .visual_candidates import extract_visual_candidates

    return extract_visual_candidates(
        pdf_path,
        thumbs_dir,
        report_name,
        save_thumbs=save_thumbs,
        doc=doc,
        parallel_workers=parallel_workers,
        pages=pages,
        artifact_cache=artifact_cache,
    )


def _extract_tables_sequential(
    pdf_path: str,
    max_candidates: int = 0,
    pages: Optional[List[int]] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from .table_candidates import _extract_tables_sequential as _run_tables_sequential

    return _run_tables_sequential(
        pdf_path,
        max_candidates=max_candidates,
        pages=pages,
        artifact_cache=artifact_cache,
    )


def _extract_tables(
    pdf_path: str,
    max_candidates: int = 0,
    parallel_workers: int = 1,
    pages: Optional[List[int]] = None,
    doc: Optional[fitz.Document] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from .table_candidates import extract_table_candidates

    return extract_table_candidates(
        pdf_path,
        max_candidates=max_candidates,
        parallel_workers=parallel_workers,
        pages=pages,
        doc=doc,
        artifact_cache=artifact_cache,
    )


def _prune_charts_overlapping_ranked_tables(
    charts: List[Candidate], tables: List[Candidate]
) -> Tuple[List[Candidate], int]:
    ranked_tables_by_page: Dict[int, List[Candidate]] = {}
    table_overlap_candidates_by_page: Dict[int, List[Candidate]] = {}
    for table in tables:
        if table.kind != "table":
            continue
        method = _s(candidate_features(table).method).strip().lower()
        if method != "ranked":
            if _table_candidate_looks_like_chart_shadow(table):
                continue
            table_overlap_candidates_by_page.setdefault(int(table.page), []).append(
                table
            )
            continue
        ranked_tables_by_page.setdefault(int(table.page), []).append(table)
    if not ranked_tables_by_page and not table_overlap_candidates_by_page:
        return charts, 0

    kept: List[Candidate] = []
    pruned = 0
    for chart in charts:
        page_tables = ranked_tables_by_page.get(int(chart.page), [])
        overlap_tables = table_overlap_candidates_by_page.get(int(chart.page), [])
        if not page_tables and not overlap_tables:
            kept.append(chart)
            continue
        should_prune = False
        for table in page_tables:
            iou = _table_iou(chart.bbox, table.bbox)
            containment = _table_containment_ratio(chart.bbox, table.bbox)
            if (
                iou >= CHART_RANKED_TABLE_DUP_IOU
                or containment >= CHART_RANKED_TABLE_DUP_CONTAINMENT
            ):
                should_prune = True
                break
        if not should_prune and _chart_candidate_looks_like_table_shadow(chart):
            for table in overlap_tables:
                iou = _table_iou(chart.bbox, table.bbox)
                containment = _table_containment_ratio(chart.bbox, table.bbox)
                if iou >= CHART_RANKED_TABLE_DUP_IOU or containment >= 0.9:
                    should_prune = True
                    break
        if should_prune:
            pruned += 1
            continue
        kept.append(chart)
    return kept, pruned


def _chart_candidate_looks_like_table_shadow(chart: Candidate) -> bool:
    if chart.kind != "chart":
        return False
    caption = _s(chart.caption or chart.preview_text).strip().lower()
    if re.match(r"^\s*(?:figure|fig\.|chart|graph|exhibit|infographic)\b", caption):
        return False
    features = candidate_features(chart)
    text_lines = int(features.text_lines or 0)
    text_chars = int(features.text_chars or 0)
    text_ratio = float(features.text_ratio or 0.0)
    return (
        text_lines >= 16 and text_chars >= 240 and text_ratio >= 0.1
    ) or text_lines >= 40


def _table_candidate_looks_like_chart_shadow(table: Candidate) -> bool:
    if table.kind != "table":
        return False
    features = candidate_features(table)
    method = _s(features.method).strip().lower()
    rows = int(features.rows or 0)
    cols = int(features.cols or 0)
    numeric_ratio = float(features.numeric_ratio or 0.0)
    avg_words_per_cell = float(features.avg_words_per_cell or 0.0)
    area_frac = float(features.area_frac or 0.0)
    if method == "lattice":
        return (
            area_frac >= TABLE_CHART_SHADOW_LATTICE_MIN_AREA
            and rows <= TABLE_CHART_SHADOW_LATTICE_MAX_ROWS
            and cols <= TABLE_CHART_SHADOW_LATTICE_MAX_COLS
            and numeric_ratio <= TABLE_CHART_SHADOW_LATTICE_MAX_NUMERIC_RATIO
            and avg_words_per_cell >= TABLE_CHART_SHADOW_LATTICE_MIN_AVG_WORDS
        )
    if method == "stream":
        return (
            area_frac >= TABLE_CHART_SHADOW_STREAM_MIN_AREA
            and rows >= TABLE_CHART_SHADOW_STREAM_MIN_ROWS
            and cols >= TABLE_CHART_SHADOW_STREAM_MIN_COLS
            and numeric_ratio <= TABLE_CHART_SHADOW_STREAM_MAX_NUMERIC_RATIO
            and avg_words_per_cell <= TABLE_CHART_SHADOW_STREAM_MAX_AVG_WORDS
        )
    return False


def _prune_tables_overlapping_chart_panels(
    tables: List[Candidate], charts: List[Candidate]
) -> Tuple[List[Candidate], int]:
    charts_by_page: Dict[int, List[Candidate]] = {}
    for chart in charts:
        if chart.kind != "chart":
            continue
        charts_by_page.setdefault(int(chart.page), []).append(chart)
    if not charts_by_page:
        return tables, 0

    kept: List[Candidate] = []
    pruned = 0
    for table in tables:
        page_charts = charts_by_page.get(int(table.page), [])
        if not page_charts or not _table_candidate_looks_like_chart_shadow(table):
            kept.append(table)
            continue
        should_prune = False
        table_rect = fitz.Rect(*table.bbox)
        table_area = max(1.0, table_rect.get_area())
        total_overlap = 0.0
        for chart in page_charts:
            iou = _table_iou(chart.bbox, table.bbox)
            containment = _table_containment_ratio(chart.bbox, table.bbox)
            total_overlap += _rect_overlap_area(fitz.Rect(*chart.bbox), table_rect)
            if (
                iou >= TABLE_CHART_SHADOW_IOU
                or containment >= TABLE_CHART_SHADOW_CONTAINMENT
            ):
                should_prune = True
                break
        if (
            not should_prune
            and (total_overlap / table_area) >= TABLE_CHART_SHADOW_TOTAL_OVERLAP_RATIO
        ):
            should_prune = True
        if should_prune:
            pruned += 1
            continue
        kept.append(table)
    return kept, pruned


def _final_chart_candidate_looks_heading_slice(
    candidate: Candidate,
    text: str,
) -> bool:
    caption = _s(candidate.caption or "").strip()
    if not caption or FIGURE_LINE_RX.search(caption):
        return False
    if any(ch.isdigit() for ch in caption):
        return False
    if not FINAL_CHART_BARE_TITLE_RX.fullmatch(caption):
        return False
    if FINAL_CHART_SOURCE_OR_STATLINK_RX.search(text):
        return False
    x0, y0, x1, y1 = candidate.bbox
    if (y1 - y0) > 96.0:
        return False
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if not lines or len(lines) > 2:
        return False
    normalized = [re.sub(r"\s+", " ", line) for line in lines]
    return all(line == caption for line in normalized)


def _final_chart_candidate_looks_forecast_table(
    candidate: Candidate,
    text: str,
) -> bool:
    caption = _s(candidate.caption or "").strip()
    if not caption or FIGURE_LINE_RX.search(caption):
        return False
    lines = [line.strip() for line in str(text or "").splitlines() if line.strip()]
    if len(lines) < 6:
        return False
    lower_lines = [line.lower() for line in lines]
    lower_text = "\n".join(lower_lines)
    dense_year_header = any(
        len(FINAL_CHART_YEAR_RX.findall(line)) >= 3
        for line in lines[: min(4, len(lines))]
    )
    if not dense_year_header:
        dense_year_header = (
            sum(
                len(FINAL_CHART_YEAR_RX.findall(line))
                for line in lines[: min(12, len(lines))]
            )
            >= 4
        )
    numeric_row_hits = sum(
        1 for line in lines if len(FINAL_CHART_NUMBER_RX.findall(line)) >= 3
    )
    return (
        dense_year_header
        and any("current prices" in line for line in lower_lines)
        and (
            any("percentage changes" in line for line in lower_lines)
            or any("volume" in line for line in lower_lines)
        )
        and (
            numeric_row_hits >= 1
            or "memorandum items" in lower_text
            or len(lines) >= 10
        )
    )


def _final_chart_header_reanchor_line(
    candidate: Candidate,
    page: fitz.Page,
    text: str,
) -> Optional[_PageTextLine]:
    if candidate.kind != "chart":
        return None
    caption = _s(candidate.caption or "").strip()
    if not caption or FIGURE_LINE_RX.search(caption):
        return None
    words = caption.split()
    if len(words) < 8 and not caption[:1].islower():
        return None
    lower_text = str(text or "").lower()
    if "source:" not in lower_text and "statlink" not in lower_text:
        return None
    rect = fitz.Rect(candidate.bbox)
    best: Optional[_PageTextLine] = None
    best_key: tuple[float, float, float] | None = None
    for line in _table_page_text_lines(page):
        line_text = _s(line.text).strip()
        if not _panel_title_looks_short_proper_name(line_text):
            continue
        if line.rect.y1 > rect.y0 + 2.0:
            continue
        gap = rect.y0 - line.rect.y1
        if gap > 72.0:
            continue
        if line.rect.x0 > rect.x0 + rect.width * 0.2:
            continue
        key = (gap, abs(line.rect.x0 - rect.x0), line.rect.y0)
        if best_key is None or key < best_key:
            best = line
            best_key = key
    return best


def _prune_final_chart_candidates(
    charts: List[Candidate],
    *,
    doc: fitz.Document,
) -> tuple[List[Candidate], int, int]:
    kept: List[Candidate] = []
    pruned = 0
    adjusted = 0
    for candidate in charts:
        if candidate.kind != "chart":
            kept.append(candidate)
            continue
        try:
            page = doc[int(candidate.page)]
            text = page.get_text("text", clip=fitz.Rect(candidate.bbox))
        except PDF_FIGURE_EXCEPTIONS:
            kept.append(candidate)
            continue
        header_line = _final_chart_header_reanchor_line(candidate, page, text)
        if header_line is not None:
            x0, y0, x1, y1 = candidate.bbox
            candidate = Candidate(
                schema_version=candidate.schema_version,
                id=candidate.id,
                kind=candidate.kind,
                page=candidate.page,
                bbox=(
                    min(x0, header_line.rect.x0),
                    min(y0, header_line.rect.y0),
                    x1,
                    y1,
                ),
                preview_text=header_line.text,
                caption=header_line.text,
                thumb_path=candidate.thumb_path,
                meta=candidate.meta,
                features=candidate.features,
            )
            adjusted += 1
            try:
                text = page.get_text("text", clip=fitz.Rect(candidate.bbox))
            except PDF_FIGURE_EXCEPTIONS:
                text = ""
        if _final_chart_candidate_looks_forecast_table(candidate, text):
            pruned += 1
            continue
        if _final_chart_candidate_looks_heading_slice(candidate, text):
            pruned += 1
            continue
        kept.append(candidate)
    return kept, pruned, adjusted


@dataclass(frozen=True)
class _CandidatePagePlan:
    chart_pages: Optional[List[int]]
    table_pages: Optional[List[int]]
    excluded_count: int
    triaged_full_scan_pages: int
    page_triage_records: List[PdfCandidatePageTriageRecord]
    page_triage_skipped_pages: int
    degraded_pages: List[PdfDegradedPage]


@dataclass(frozen=True)
class _CandidatePageScore:
    page: int
    score: float
    reasons: tuple[str, ...]
    text_chars: int
    text_blocks: int
    image_blocks: int
    drawing_count: int


@dataclass
class _CandidateExtractionArtifacts:
    charts: List[Candidate]
    tables: List[Candidate]
    chart_stats: Dict[str, object]
    table_stats: Dict[str, object]
    chart_ranked_overlap_pruned: int = 0
    table_chart_overlap_pruned: int = 0
    final_chart_fragment_pruned: int = 0
    final_chart_header_reanchored: int = 0


def _initial_chart_candidate_stats() -> Dict[str, object]:
    return {"raw": 0, "kept": 0, "rejected": 0, "reasons": {}}


def _initial_table_candidate_stats() -> Dict[str, object]:
    return {
        "raw_lattice": 0,
        "raw_stream": 0,
        "validated": 0,
        "deduped": 0,
        "rejected": 0,
        "reasons": {},
    }


def _open_candidate_triage_doc(
    pdf_path: str,
    shared_doc: Optional[fitz.Document],
) -> tuple[Optional[fitz.Document], bool]:
    if shared_doc is not None:
        return shared_doc, False
    try:
        return fitz.open(pdf_path), True
    except PDF_FIGURE_EXCEPTIONS:
        return None, False


def _candidate_page_text(artifacts) -> str:
    return "\n".join(
        str(block[4] or "").strip()
        for block in artifacts.text_blocks
        if str(block[4] or "").strip()
    )


def _candidate_page_drawing_count(page: fitz.Page) -> int:
    try:
        return len(page.get_drawings() or [])
    except PDF_FIGURE_TRIAGE_EXCEPTIONS:
        return 0


def _candidate_page_image_area_fraction(page: fitz.Page, artifacts) -> float:
    page_area = max(1.0, float(page.rect.get_area()))
    image_area = sum(max(0.0, float(rect.get_area())) for rect in artifacts.image_block_rects)
    return min(1.0, image_area / page_area)


def _candidate_page_numeric_line_count(text: str) -> int:
    numeric_lines = 0
    for line in str(text or "").splitlines():
        numeric_tokens = re.findall(r"\b\d+(?:[.,]\d+)?%?\b", line)
        if len(numeric_tokens) >= 2:
            numeric_lines += 1
    return numeric_lines


def _score_candidate_page(
    page: fitz.Page,
    artifacts,
) -> _CandidatePageScore:
    text = _candidate_page_text(artifacts)
    text_lower = text.casefold()
    drawing_count = _candidate_page_drawing_count(page)
    image_area_frac = _candidate_page_image_area_fraction(page, artifacts)
    numeric_line_count = _candidate_page_numeric_line_count(text)
    score = 0.0
    reasons: list[str] = []

    if drawing_count > 0:
        score += min(0.36, 0.08 + drawing_count * 0.035)
        reasons.append("visual_drawing_signal")
    if image_area_frac >= 0.03:
        score += min(0.28, image_area_frac * 0.55)
        reasons.append("image_area_signal")
    if re.search(
        r"\b(fig(?:ure)?|chart|exhibit|table|source|market|growth|forecast|revenue|cagr)\b",
        text_lower,
    ):
        score += 0.18
        reasons.append("visual_or_table_text_marker")
    if numeric_line_count >= 2:
        score += min(0.3, 0.14 + numeric_line_count * 0.035)
        reasons.append("tabular_text_signal")
    elif numeric_line_count == 1:
        score += 0.08
        reasons.append("numeric_text_signal")
    if artifacts.text_block_count >= 3 and artifacts.text_char_count >= 180:
        score += 0.04
        reasons.append("structured_text_density")

    if not reasons:
        reasons.append("low_signal")
    return _CandidatePageScore(
        page=int(getattr(page, "number", 0) or 0),
        score=round(min(1.0, max(0.0, score)), 3),
        reasons=tuple(reasons),
        text_chars=int(artifacts.text_char_count),
        text_blocks=int(artifacts.text_block_count),
        image_blocks=len(artifacts.image_block_rects),
        drawing_count=int(drawing_count),
    )


def _page_triage_record(
    score: _CandidatePageScore,
    *,
    threshold: float,
    action: str,
) -> PdfCandidatePageTriageRecord:
    return PdfCandidatePageTriageRecord(
        schema_version="1.0",
        page=score.page,
        score=score.score,
        threshold=round(float(threshold), 3),
        action=action,
        reasons=list(score.reasons),
        text_chars=score.text_chars,
        text_blocks=score.text_blocks,
        image_blocks=score.image_blocks,
        drawing_count=score.drawing_count,
    )


def _resolve_page_gate_recall_floor(
    requested_count: int,
    *,
    min_recall_pages: int,
    min_recall_page_fraction: float,
) -> int:
    if requested_count <= 0:
        return 0
    fraction = min(1.0, max(0.0, float(min_recall_page_fraction)))
    page_count_floor = max(0, int(min_recall_pages))
    fraction_floor = math.ceil(requested_count * fraction)
    return min(requested_count, max(page_count_floor, fraction_floor))


def _plan_candidate_pages(
    triage_doc: fitz.Document,
    excluded_pages: set[int],
    *,
    artifact_cache: PdfPageArtifactCache,
    degraded_page_policy: str = "include_with_warning",
    page_gate_enabled: bool = True,
    page_gate_min_score: float = 0.2,
    page_gate_min_recall_pages: int = 12,
    page_gate_min_recall_page_fraction: float = 0.65,
) -> _CandidatePagePlan:
    requested_pages = [
        index for index in range(len(triage_doc)) if index not in excluded_pages
    ]
    triaged_pages: list[int] = []
    table_pages: list[int] = []
    triaged_full_scan_pages = 0
    degraded_pages: list[PdfDegradedPage] = []
    page_triage_records: list[PdfCandidatePageTriageRecord] = []
    skipped_score_candidates: list[tuple[int, _CandidatePageScore]] = []
    threshold = min(1.0, max(0.0, float(page_gate_min_score)))
    for index in requested_pages:
        try:
            page = triage_doc[index]
            artifacts = get_page_artifacts(
                page,
                cache=artifact_cache,
            )
            score = _score_candidate_page(page, artifacts)
            if not page_gate_enabled:
                triaged_pages.append(index)
                table_pages.append(index)
                page_triage_records.append(
                    _page_triage_record(
                        score,
                        threshold=threshold,
                        action="include_disabled",
                    )
                )
                continue
            if artifacts.full_page_scan_without_text:
                triaged_full_scan_pages += 1
                table_pages.append(index)
                page_triage_records.append(
                    _page_triage_record(
                        score,
                        threshold=threshold,
                        action="include_table_only_full_scan",
                    )
                )
                continue
        except PDF_FIGURE_TRIAGE_EXCEPTIONS as exc:
            degraded_page = _degraded_page_record(
                page=index,
                stage="triage",
                reason_code="pdf_candidate_page_triage_failed",
                policy=degraded_page_policy,
                message=str(exc),
            )
            action = _resolve_degraded_page_action(
                degraded_page=degraded_page,
            )
            degraded_pages.append(degraded_page)
            if action == "fail":
                raise AppError(
                    code=degraded_page.reason_code,
                    message="PDF candidate page triage failed",
                    cause=exc,
                    retryable=False,
                    context={
                        "page": index,
                        "policy": degraded_page.policy,
                        "stage": degraded_page.stage,
                    },
                ) from exc
            if action == "skip":
                page_triage_records.append(
                    PdfCandidatePageTriageRecord(
                        schema_version="1.0",
                        page=index,
                        score=0.0,
                        threshold=round(threshold, 3),
                        action="degraded_skip",
                        reasons=["triage_failed"],
                    )
                )
                continue
            page_triage_records.append(
                PdfCandidatePageTriageRecord(
                    schema_version="1.0",
                    page=index,
                    score=0.0,
                    threshold=round(threshold, 3),
                    action="degraded_include",
                    reasons=["triage_failed"],
                )
            )
            table_pages.append(index)
            triaged_pages.append(index)
            continue
        if score.score >= threshold:
            triaged_pages.append(index)
            table_pages.append(index)
            page_triage_records.append(
                _page_triage_record(
                    score,
                    threshold=threshold,
                    action="include_score",
                )
            )
            continue
        skipped_score_candidates.append((index, score))
        page_triage_records.append(
            _page_triage_record(
                score,
                threshold=threshold,
                action="skip_low_score",
            )
        )
    recall_floor = _resolve_page_gate_recall_floor(
        len(requested_pages),
        min_recall_pages=page_gate_min_recall_pages,
        min_recall_page_fraction=page_gate_min_recall_page_fraction,
    )
    included_pages = set(triaged_pages) | set(table_pages)
    if page_gate_enabled and len(included_pages) < recall_floor:
        need = recall_floor - len(included_pages)
        recall_candidates = sorted(
            skipped_score_candidates,
            key=lambda item: (-item[1].score, item[0]),
        )[:need]
        record_by_page = {record.page: idx for idx, record in enumerate(page_triage_records)}
        for index, score in recall_candidates:
            if index not in triaged_pages:
                triaged_pages.append(index)
            if index not in table_pages:
                table_pages.append(index)
            record_index = record_by_page.get(index)
            if record_index is not None:
                page_triage_records[record_index] = replace(
                    page_triage_records[record_index],
                    action="include_recall_floor",
                    reasons=list(score.reasons) + ["recall_floor"],
                )
    triaged_pages.sort()
    table_pages.sort()
    page_triage_skipped_pages = sum(
        1 for record in page_triage_records if record.action == "skip_low_score"
    )
    return _CandidatePagePlan(
        chart_pages=triaged_pages,
        table_pages=table_pages,
        excluded_count=max(0, len(triage_doc) - len(requested_pages)),
        triaged_full_scan_pages=triaged_full_scan_pages,
        page_triage_records=page_triage_records,
        page_triage_skipped_pages=page_triage_skipped_pages,
        degraded_pages=degraded_pages,
    )


def _degraded_page_record(
    *,
    page: int,
    stage: str,
    reason_code: str,
    policy: str,
    message: str,
) -> PdfDegradedPage:
    return PdfDegradedPage(
        schema_version="1.0",
        page=int(page),
        stage=str(stage or "").strip() or "unknown",
        reason_code=str(reason_code or "").strip() or "pdf_candidate_degraded",
        policy=str(policy or "").strip() or "include_with_warning",
        message=str(message or "").strip()[:500],
    )


def _resolve_degraded_page_action(*, degraded_page: PdfDegradedPage) -> str:
    policy = str(degraded_page.policy or "").strip().lower()
    if policy == "fail":
        return "fail"
    if policy == "skip_with_warning":
        return "skip"
    if policy == "include_with_warning":
        return "include"
    raise AppError(
        code="pdf_candidate_degraded_policy_invalid",
        message="Unsupported PDF candidate degraded-page policy",
        retryable=False,
        context={"policy": degraded_page.policy},
    )


def _extract_candidate_artifacts(
    request: ExtractCandidatesRequest,
    *,
    triage_doc: Optional[fitz.Document],
    parallel_workers: int,
    page_plan: _CandidatePagePlan,
    artifact_cache: PdfPageArtifactCache,
) -> _CandidateExtractionArtifacts:
    artifacts = _CandidateExtractionArtifacts(
        charts=[],
        tables=[],
        chart_stats=_initial_chart_candidate_stats(),
        table_stats=_initial_table_candidate_stats(),
    )
    if page_plan.chart_pages == [] and page_plan.table_pages == []:
        return artifacts
    safe_report_name = safe_path_segment(request.report_name, fallback="report")
    thumbs = Path(request.out_dir) / safe_report_name / "thumbs"
    artifacts.charts, artifacts.chart_stats = _extract_charts(
        request.pdf_path,
        thumbs.as_posix(),
        safe_report_name,
        save_thumbs=False,
        doc=triage_doc if parallel_workers <= 1 else None,
        parallel_workers=parallel_workers,
        pages=page_plan.chart_pages,
        artifact_cache=artifact_cache,
    )
    artifacts.tables, artifacts.table_stats = _extract_tables(
        request.pdf_path,
        parallel_workers=parallel_workers,
        pages=page_plan.table_pages,
        doc=triage_doc if parallel_workers <= 1 else None,
        artifact_cache=artifact_cache,
    )
    (
        artifacts.charts,
        artifacts.chart_ranked_overlap_pruned,
    ) = _prune_charts_overlapping_ranked_tables(artifacts.charts, artifacts.tables)
    if artifacts.chart_ranked_overlap_pruned:
        artifacts.chart_stats["ranked_table_overlap_pruned"] = (
            artifacts.chart_ranked_overlap_pruned
        )
    (
        artifacts.tables,
        artifacts.table_chart_overlap_pruned,
    ) = _prune_tables_overlapping_chart_panels(artifacts.tables, artifacts.charts)
    if artifacts.table_chart_overlap_pruned:
        artifacts.table_stats["chart_overlap_pruned"] = (
            artifacts.table_chart_overlap_pruned
        )
    return artifacts


def _finalize_chart_collection(
    pdf_path: str,
    *,
    triage_doc: Optional[fitz.Document],
    charts: List[Candidate],
) -> tuple[List[Candidate], int, int]:
    final_doc = triage_doc
    close_doc = False
    if final_doc is None:
        final_doc = fitz.open(pdf_path)
        close_doc = True
    try:
        return _prune_final_chart_candidates(charts, doc=final_doc)
    finally:
        if close_doc and final_doc is not None:
            try:
                final_doc.close()
            except PDF_FIGURE_EXCEPTIONS:
                final_doc = None


def _annotate_degraded_candidates(
    candidates: List[Candidate],
    degraded_pages: List[PdfDegradedPage],
) -> List[Candidate]:
    if not degraded_pages:
        return candidates
    degraded_by_page: Dict[int, List[PdfDegradedPage]] = {}
    for page in degraded_pages:
        degraded_by_page.setdefault(int(page.page), []).append(page)
    annotated: List[Candidate] = []
    for candidate in candidates:
        page_reasons = degraded_by_page.get(int(candidate.page), [])
        if not page_reasons:
            annotated.append(candidate)
            continue
        existing_meta = dict(candidate.meta or {})
        existing_meta["degraded_page_reasons"] = [
            {
                "stage": reason.stage,
                "reason_code": reason.reason_code,
                "policy": reason.policy,
                "message": reason.message,
            }
            for reason in page_reasons
        ]
        annotated.append(
            Candidate(
                schema_version=candidate.schema_version,
                id=candidate.id,
                kind=candidate.kind,
                page=candidate.page,
                bbox=candidate.bbox,
                preview_text=candidate.preview_text,
                caption=candidate.caption,
                thumb_path=candidate.thumb_path,
                meta=existing_meta,
                features=candidate.features,
            )
        )
    return annotated


def collect_candidates(
    request: ExtractCandidatesRequest, ctx: RunContext
) -> ExtractCandidatesResponse:
    parallel_workers = _resolve_candidate_parallel_workers(request.parallel_workers, 8)
    excluded_pages = {
        int(page)
        for page in (request.exclude_page_indices or [])
        if isinstance(page, int) and page >= 0
    }
    candidate_logger.info(
        log_event(
            ctx,
            role="service",
            event="extract_candidates_start",
            module=candidate_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.fitz_doc
                ),
                "parallel_workers": parallel_workers,
                "exclude_page_indices": sorted(excluded_pages),
                "page_gate_enabled": bool(request.page_gate_enabled),
                "page_gate_min_score": round(float(request.page_gate_min_score), 3),
                "page_gate_min_recall_pages": int(
                    request.page_gate_min_recall_pages
                ),
                "page_gate_min_recall_page_fraction": round(
                    float(request.page_gate_min_recall_page_fraction), 3
                ),
            },
        )
    )
    shared_doc = (
        request.pdf_context.fitz_doc
        if request.pdf_context and parallel_workers <= 1
        else None
    )
    triage_doc: Optional[fitz.Document] = None
    close_doc = False
    page_plan = _CandidatePagePlan(
        chart_pages=None,
        table_pages=None,
        excluded_count=0,
        triaged_full_scan_pages=0,
        page_triage_records=[],
        page_triage_skipped_pages=0,
        degraded_pages=[],
    )
    artifact_cache = (
        getattr(request.pdf_context, "page_artifact_cache", None)
        if request.pdf_context is not None
        else None
    ) or create_page_artifact_cache()
    artifacts = _CandidateExtractionArtifacts(
        charts=[],
        tables=[],
        chart_stats=_initial_chart_candidate_stats(),
        table_stats=_initial_table_candidate_stats(),
    )
    candidates: List[Candidate] = []
    try:
        triage_doc, close_doc = _open_candidate_triage_doc(request.pdf_path, shared_doc)
        if triage_doc is not None:
            page_plan = _plan_candidate_pages(
                triage_doc,
                excluded_pages,
                artifact_cache=artifact_cache,
                degraded_page_policy=request.degraded_page_policy,
                page_gate_enabled=request.page_gate_enabled,
                page_gate_min_score=request.page_gate_min_score,
                page_gate_min_recall_pages=request.page_gate_min_recall_pages,
                page_gate_min_recall_page_fraction=(
                    request.page_gate_min_recall_page_fraction
                ),
            )
        artifacts = _extract_candidate_artifacts(
            request,
            triage_doc=triage_doc,
            parallel_workers=parallel_workers,
            page_plan=page_plan,
            artifact_cache=artifact_cache,
        )
        (
            artifacts.charts,
            artifacts.final_chart_fragment_pruned,
            artifacts.final_chart_header_reanchored,
        ) = _finalize_chart_collection(
            request.pdf_path,
            triage_doc=triage_doc,
            charts=artifacts.charts,
        )
        if artifacts.final_chart_fragment_pruned:
            artifacts.chart_stats["final_fragment_pruned"] = (
                artifacts.final_chart_fragment_pruned
            )
        if artifacts.final_chart_header_reanchored:
            artifacts.chart_stats["final_header_reanchored"] = (
                artifacts.final_chart_header_reanchored
            )
        candidates = _annotate_degraded_candidates(
            artifacts.charts + artifacts.tables,
            page_plan.degraded_pages,
        )
    finally:
        if close_doc and triage_doc is not None:
            try:
                triage_doc.close()
            except PDF_FIGURE_EXCEPTIONS as exc:
                page_plan.degraded_pages.append(
                    _degraded_page_record(
                        page=-1,
                        stage="cleanup",
                        reason_code="pdf_candidate_triage_doc_close_failed",
                        policy="include_with_warning",
                        message=str(exc),
                    )
                )
    chart_count = sum(1 for candidate in candidates if candidate.kind == "chart")
    table_count = sum(1 for candidate in candidates if candidate.kind == "table")
    candidate_logger.info(
        log_event(
            ctx,
            role="service",
            event="extract_candidates_complete",
            module=candidate_logger.name,
            fields={
                "count": len(candidates),
                "chart_count": chart_count,
                "table_count": table_count,
                "chart_stats": artifacts.chart_stats,
                "table_stats": artifacts.table_stats,
                "ranked_table_overlap_pruned": artifacts.chart_ranked_overlap_pruned,
                "table_chart_overlap_pruned": artifacts.table_chart_overlap_pruned,
                "excluded_count": page_plan.excluded_count,
                "triaged_full_scan_pages": page_plan.triaged_full_scan_pages,
                "page_triage_evaluated_count": len(page_plan.page_triage_records),
                "page_triage_skipped_count": page_plan.page_triage_skipped_pages,
                "page_triage_threshold": round(float(request.page_gate_min_score), 3),
                "page_triage_recall_floor": _resolve_page_gate_recall_floor(
                    len(page_plan.page_triage_records),
                    min_recall_pages=request.page_gate_min_recall_pages,
                    min_recall_page_fraction=(
                        request.page_gate_min_recall_page_fraction
                    ),
                ),
                "page_triage_records": [
                    {
                        "page": item.page,
                        "score": item.score,
                        "threshold": item.threshold,
                        "action": item.action,
                        "reasons": item.reasons,
                    }
                    for item in page_plan.page_triage_records
                ],
                "degraded_page_count": len(page_plan.degraded_pages),
                "degraded_pages": [
                    {
                        "page": item.page,
                        "stage": item.stage,
                        "reason_code": item.reason_code,
                        "policy": item.policy,
                    }
                    for item in page_plan.degraded_pages
                ],
                "page_artifact_cache": artifact_cache.stats(),
            },
        )
    )
    return ExtractCandidatesResponse(
        schema_version="1.0",
        candidates=candidates,
        stats=PdfCandidateExtractionStats(
            schema_version="1.0",
            degraded_pages=page_plan.degraded_pages,
            triage_failure_count=len(
                [item for item in page_plan.degraded_pages if item.stage == "triage"]
            ),
            extraction_failure_count=len(
                [item for item in page_plan.degraded_pages if item.stage != "triage"]
            ),
            page_triage_records=page_plan.page_triage_records,
            page_triage_evaluated_count=len(page_plan.page_triage_records),
            page_triage_skipped_count=page_plan.page_triage_skipped_pages,
        ),
    )


# BEGIN PDF FIGURE EXTRACTION
def extract_best_figure(
    request: FigureExtractRequest, ctx: RunContext
) -> FigureExtractResponse:
    figure_logger.info(
        log_event(
            ctx,
            role="service",
            event="figure_extract_start",
            module=figure_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.fitz_doc
                ),
            },
        )
    )
    img_path, caption, page = _extract_best_figure_png(
        request.pdf_path,
        request.out_dir,
        request.report_name,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
    )
    figure_logger.info(
        log_event(
            ctx,
            role="service",
            event="figure_extract_complete",
            module=figure_logger.name,
            fields={"image_path": img_path or ""},
        )
    )
    return FigureExtractResponse(
        schema_version="1.0",
        image_path=img_path,
        caption=caption,
        page=page,
    )


FIGURE_CAPTION_HINTS = {
    "figure",
    "fig.",
    "exhibit",
    "chart",
    "graph",
    "source",
    "panel",
    "table",
}
FIGURE_METRIC_HINTS = {
    "%",
    "$",
    "growth",
    "share",
    "yoy",
    "cagr",
    "roi",
    "roas",
    "ctr",
    "conversion",
    "revenue",
    "impressions",
    "spend",
    "units",
}
FIGURE_LINE_RX = re.compile(r"\\b(fig(?:ure)?|exhibit|chart)\\b\\s*\\d+", re.I)
FINAL_CHART_BARE_TITLE_RX = re.compile(
    r"^[A-Z][A-Za-z'’.-]*(?:\s+[A-Z][A-Za-z'’.-]*){0,2}$"
)
FINAL_CHART_SOURCE_OR_STATLINK_RX = re.compile(
    r"(?im)(?:^|\n)\s*(?:source:|statlink\b)"
)
FINAL_CHART_YEAR_RX = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
FINAL_CHART_NUMBER_RX = re.compile(r"\b\d+(?:\.\d+)?\b")


def _figure_score_text(text: str) -> int:
    if not text:
        return 0
    t = text.lower()
    s = 0
    s += sum(2 for k in FIGURE_CAPTION_HINTS if k in t)
    s += sum(1 for k in FIGURE_METRIC_HINTS if k in t)
    s += min(3, len(re.findall(r"\\d", t)) // 4)
    return s


def _figure_nearest_block_text(
    page: fitz.Page, bbox: fitz.Rect, max_dist: float = 90.0
) -> str:
    best = ("", 0, 1e9)
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if not text or text.isspace():
            continue
        rect = fitz.Rect(x0, y0, x1, y1)
        dy = rect.y0 - bbox.y1
        distance = dy if dy >= 0 else abs(dy) + 24
        if distance > max_dist:
            continue
        sc = _figure_score_text(text)
        if sc > best[1] or (sc == best[1] and distance < best[2]):
            best = (text.strip(), sc, distance)
    return best[0]


def _figure_line_targets(page: fitz.Page) -> List[fitz.Rect]:
    targets = []
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
        if not text:
            continue
        if FIGURE_LINE_RX.search(text):
            targets.append(fitz.Rect(x0, y0, x1, y1))
    return targets


def _figure_distance(a: fitz.Rect, b: fitz.Rect) -> float:
    ac = a.tl + (a.br - a.tl) * 0.5
    bc = b.tl + (b.br - b.tl) * 0.5
    return (ac - bc).magnitude


def _extract_best_figure_png(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    min_page_area_frac: float = 0.06,
    doc: Optional[fitz.Document] = None,
) -> Tuple[Optional[str], Optional[str], int]:
    try:
        out_root = Path(out_dir)
        safe_report_name = safe_path_segment(report_name, fallback="report")
        img_dir = out_root / safe_report_name / "assets"
        img_dir.mkdir(parents=True, exist_ok=True)
        best = (None, 0.0, "", -1)

        local_doc = doc or fitz.open(pdf_path)
        try:
            for pno, page in enumerate(local_doc):
                page_rect = page.rect
                page_area = page_rect.get_area()
                top_cut = page_rect.y0 + page_rect.height * 0.12
                bot_cut = page_rect.y1 - page_rect.height * 0.12

                figure_targets = _figure_line_targets(page)

                for xref, *_ in page.get_images(full=True):
                    rects = page.get_image_rects(xref)
                    if not rects:
                        continue
                    bbox = rects[0]
                    if bbox.y0 < top_cut or bbox.y1 > bot_cut:
                        continue

                    area = bbox.get_area()
                    if area / page_area < min_page_area_frac:
                        continue

                    aspect = bbox.width / max(1, bbox.height)
                    if not (0.6 <= aspect <= 2.2):
                        continue

                    caption = _figure_nearest_block_text(page, bbox)
                    cap_score = _figure_score_text(caption)

                    prox_bonus = 0
                    if figure_targets:
                        d = min(_figure_distance(bbox, t) for t in figure_targets)
                        if d < 200:
                            prox_bonus = 3
                        elif d < 350:
                            prox_bonus = 1

                    score = (area**0.9) * (1 + 0.15 * cap_score + 0.10 * prox_bonus)

                    if score > best[1]:
                        pix = fitz.Pixmap(local_doc, xref)
                        if pix.width * pix.height < 80_000:
                            continue
                        if pix.n >= 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                        best = (
                            pix,
                            score,
                            caption or f"Auto-selected image from page {pno + 1}",
                            pno,
                        )
        finally:
            if doc is None and "local_doc" in locals():
                local_doc.close()

        if best[0] is None:
            return None, None, -1

        out_path = img_dir / f"{safe_report_name}.png"
        best[0].save(out_path.as_posix())
        rel = Path(safe_report_name) / "assets" / out_path.name
        return rel.as_posix(), best[2], int(best[3])
    except PDF_FIGURE_EXCEPTIONS:
        return None, None, -1
