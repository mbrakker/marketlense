from __future__ import annotations

import io
import logging
import math
import os
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

import pdfplumber
import pymupdf as fitz
from PIL import Image

from src.contracts.candidates import Candidate
from src.contracts.report_assets import (
    ExtractCandidatesRequest,
    ExtractCandidatesResponse,
    FigureExtractRequest,
    FigureExtractResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.slugify import slugify

from .page_artifacts import is_full_page_scan_without_text
from .shared import candidate_logger, figure_logger

# BEGIN PDF CANDIDATE EXTRACTION
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
PDF_FIGURE_TRIAGE_EXCEPTIONS = (AppError,) + PDF_FIGURE_EXCEPTIONS
_PDFMINER_LOGGERS = (
    "pdfminer",
    "pdfminer.pdfinterp",
    "pdfminer.cmapdb",
    "pdfminer.layout",
)

CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph", "source")
CHART_CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph", "infographic")
VISUAL_CONTEXT_HINTS = CAPTION_HINTS + ("infographic",)
TABLE_CAPTION_HINTS = CAPTION_HINTS + ("table",)
PANEL_GUIDANCE_TITLE_RX = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:ways?|keys?|steps?|actions?|principles?|tips?|strategies?|takeaways?|lessons?|rules?)\b",
    re.IGNORECASE,
)
PANEL_SHORT_PROPER_NAME_RX = re.compile(
    r"^[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+(?:\s+[A-Z][A-Za-zÀ-ÖØ-öø-ÿ'’.-]+){0,2}$"
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
CROP_REFINE_BBOX_PAD_X_FRAC = 0.012
CROP_REFINE_BBOX_PAD_Y_FRAC = 0.015
CROP_REFINE_BBOX_PAD_MIN = 4.0
CROP_REFINE_BBOX_PAD_MAX = 20.0
CROP_REFINE_EDGE_TOUCH_TOL = 1.5
CROP_REFINE_EDGE_MIN_OVERLAP = 0.2
CROP_REFINE_EDGE_INCLUDE_OVERLAP_RATIO = 0.35
CROP_REFINE_EDGE_TRIM_OVERLAP_RATIO = 0.1
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
TABLE_SETTINGS_LATTICE: Dict[str, object] = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
}
TABLE_SETTINGS_STREAM: Dict[str, object] = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "snap_tolerance": 5,
    "join_tolerance": 5,
    "intersection_tolerance": 10,
    "edge_min_length": 8,
}
TABLE_DEDUP_IOU = 0.8
TABLE_MIN_ROWS = 2
TABLE_MIN_COLS = 2
TABLE_MIN_NONEMPTY_CELLS = 4
TABLE_MIN_TEXT_CHARS = 12
TABLE_MIN_AREA_FRAC = 0.006
TABLE_MIN_WIDTH_FRAC = 0.08
TABLE_MIN_HEIGHT_FRAC = 0.06
TABLE_MIN_ASPECT = 0.15
TABLE_MAX_ASPECT = 6.5
TABLE_TEXT_HEAVY_MAX_NUMERIC_RATIO = 0.05
TABLE_TEXT_HEAVY_MIN_AVG_WORDS = 6.0
TABLE_TEXT_HEAVY_MIN_ROWS = 4
TABLE_INDEX_MIN_ROWS = 6
TABLE_INDEX_MAX_COLS = 3
TABLE_INDEX_PAGE_RATIO = 0.6
TABLE_INDEX_MIN_FIRST_COL_WORDS = 5
TABLE_STREAM_MIN_ROWS_FOR_LIKENESS = 4
TABLE_STREAM_MIN_COLS_FOR_LIKENESS = 4
TABLE_STREAM_MIN_COL_CONSISTENCY = 0.5
TABLE_STREAM_MAX_ROW_LEN_CV = 0.9
TABLE_STREAM_TEXTY_MIN_COLS = 5
TABLE_STREAM_TEXTY_MIN_ROWS = 6
TABLE_STREAM_TEXTY_MIN_LINES = 6
TABLE_STREAM_TEXTY_MIN_AREA = 0.45
TABLE_STREAM_TEXTY_MAX_NUMERIC_RATIO = 0.07
TABLE_STREAM_TEXTY_MIN_AVG_LINE_LEN = 35
TABLE_STREAM_TEXTBLOCK_MIN_AREA = 0.45
TABLE_STREAM_TEXTBLOCK_MIN_LINES = 10
TABLE_STREAM_TEXTBLOCK_MIN_AVG_LINE_LEN = 30
TABLE_STREAM_TEXTBLOCK_MAX_NUMERIC_RATIO = 0.07
TABLE_STREAM_TEXTBLOCK_MAX_FILL_RATIO = 0.6
TABLE_STREAM_TEXTBLOCK_MAX_COL_CONSISTENCY = 0.4
TABLE_STREAM_TEXTBLOCK_MIN_ROW_LEN_CV = 0.6
TABLE_STREAM_INFOBOX_MIN_AREA = 0.3
TABLE_STREAM_INFOBOX_MIN_ROWS = 12
TABLE_STREAM_INFOBOX_MAX_COLS = 6
TABLE_STREAM_INFOBOX_MAX_NUMERIC_RATIO = 0.08
TABLE_STREAM_INFOBOX_MAX_AVG_WORDS = 3.5
TABLE_STREAM_INFOBOX_MIN_LINES = 18
TABLE_STREAM_INFOBOX_MAX_ROW_LEN_CV = 0.7
TABLE_STREAM_LIST_MIN_ROWS = 6
TABLE_STREAM_LIST_MAX_COLS = 3
TABLE_STREAM_LIST_MAX_AVG_WORDS = 2.2
TABLE_STREAM_LIST_MAX_NUMERIC_RATIO = 0.08
TABLE_STREAM_LIST_MAX_AREA_FRAC = 0.12
TABLE_STREAM_PANEL_MIN_AREA_FRAC = 0.25
TABLE_STREAM_PANEL_MIN_ROWS = 8
TABLE_STREAM_PANEL_MAX_COLS = 4
TABLE_STREAM_PANEL_MAX_AVG_WORDS = 2.6
TABLE_STREAM_PANEL_MAX_NUMERIC_RATIO = 0.08
TABLE_STREAM_SLIDE_CARD_MIN_AREA = 0.18
TABLE_STREAM_SLIDE_CARD_MAX_AREA = 0.72
TABLE_STREAM_SLIDE_CARD_MIN_ROWS = 6
TABLE_STREAM_SLIDE_CARD_MAX_COLS = 6
TABLE_STREAM_SLIDE_CARD_MAX_NUMERIC_RATIO = 0.12
TABLE_STREAM_SLIDE_CARD_MIN_AVG_WORDS = 1.2
TABLE_STREAM_SLIDE_CARD_MAX_AVG_WORDS = 4.6
TABLE_STREAM_SLIDE_CARD_MIN_TEXT_BLOCK_AREA = 0.25
TABLE_STREAM_SLIDE_CARD_MIN_AVG_LINE_LEN = 20.0
TABLE_STREAM_SLIDE_CARD_MAX_COL_CONSISTENCY = 0.75
TABLE_STREAM_SLIDE_CARD_MIN_LINES = 14
TABLE_STREAM_SLIDE_CARD_LINE_PAD = 1
TABLE_CONTENTS_GRID_MIN_ROWS = 7
TABLE_CONTENTS_GRID_MIN_COLS = 4
TABLE_CONTENTS_GRID_MAX_COLS = 6
TABLE_CONTENTS_GRID_MIN_AREA = 0.25
TABLE_CONTENTS_GRID_MIN_NUMERIC_RATIO = 0.08
TABLE_CONTENTS_GRID_MAX_NUMERIC_RATIO = 0.18
TABLE_CONTENTS_GRID_MAX_AVG_WORDS = 2.1
TABLE_CONTENTS_GRID_MAX_FIRST_COL_WORDS = 2.0
TABLE_CONTENTS_GRID_MAX_AVG_LINE_LEN = 32.0
TABLE_CONTENTS_GRID_MIN_NUMBERED_LINES = 2
TABLE_CONTENTS_GRID_MIN_UPPERCASE_SHORT_RATIO = 0.45
TABLE_STREAM_SPARSE_MIN_AREA = 0.6
TABLE_STREAM_SPARSE_MAX_LINES = 15
TABLE_STREAM_SPARSE_MIN_AVG_LINE_LEN = 55
TABLE_STREAM_SPARSE_MAX_NUMERIC_RATIO = 0.05
TABLE_STREAM_SPARSE_MAX_COLS = 5
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
PANEL_CHART_LOCAL_TITLE_MAX_WORDS = 6
PANEL_CHART_LOCAL_TITLE_MAX_CHARS = 64
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
TABLE_EXPAND_MAX_GAP_FRAC = 0.12
TABLE_EXPAND_LATTICE_MAX_GAP_FRAC = 0.08
TABLE_EXPAND_MAX_BLOCK_HEIGHT_FRAC = 0.4
TABLE_EXPAND_MAX_LINES = 4
TABLE_EXPAND_MAX_AVG_LINE_LEN = 60
TABLE_EXPAND_HEADING_MAX_LINES = 2
TABLE_EXPAND_HEADING_MAX_AVG_LINE_LEN = 120
TABLE_EXPAND_HEADING_MIN_ALPHA_RATIO = 0.55
TABLE_EXPAND_HEADING_MAX_SENTENCES = 2
TABLE_EXPAND_MIN_H_OVERLAP = 0.2
TABLE_EXPAND_MIN_V_OVERLAP = 0.2
TABLE_EXPAND_STREAM_WIDE_MIN_WIDTH_FRAC = 0.85
TABLE_EXPAND_STREAM_WIDE_MIN_HEIGHT_FRAC = 0.4
TABLE_STREAM_CONTINUATION_MAX_GAP = 28.0
TABLE_STREAM_CONTINUATION_MAX_GAP_FRAC = 0.03
TABLE_STREAM_CONTINUATION_MAX_BANDS = 2
TABLE_STREAM_CONTINUATION_MIN_NUMERIC_FRAGMENTS = 4
TABLE_NOTE_CONTINUATION_MIN_H_OVERLAP = 0.6
TABLE_NOTE_CONTINUATION_MAX_X_OFFSET = 24.0
TABLE_NOTE_CONTINUATION_MIN_WORDS = 5
TEXT_BLOCK_MIN_LINES = 8
TEXT_BLOCK_MIN_AVG_LINE_LEN = 35
TEXT_BLOCK_MIN_AREA_FRAC = 0.55
TEXT_BLOCK_MAX_NUMERIC_RATIO = 0.07
TEXT_BLOCK_LOOSE_MIN_LINES = 18
TEXT_BLOCK_LOOSE_MIN_AVG_LINE_LEN = 24
TEXT_BLOCK_LOOSE_MAX_NUMERIC_RATIO = 0.05
TABLE_PROSE_BOX_MIN_ROWS = 4
TABLE_PROSE_BOX_MIN_COLS = 2
TABLE_PROSE_BOX_MAX_FILLED_CELLS_PER_ROW = 1.75
TABLE_PROSE_BOX_MAX_NUMERIC_RATIO = 0.08
TABLE_PROSE_BOX_MIN_TEXT_BLOCK_AREA = 0.15
TABLE_PROSE_BOX_MIN_TEXT_BLOCK_AVG_LINE_LEN = 45.0
TABLE_PROSE_BOX_MIN_FIRST_COL_WORDS = 3.0
TABLE_PROSE_BOX_MAX_LINECOUNT_ROW_MULT = 1.4
TABLE_PROSE_BOX_LINECOUNT_EXTRA = 4
TABLE_CONTENTS_MIN_ROWS = 12
TABLE_CONTENTS_MIN_COLS = 4
TABLE_CONTENTS_MAX_FILLED_CELLS_PER_ROW = 3.5
TABLE_CONTENTS_MIN_NUMERIC_RATIO = 0.05
TABLE_CONTENTS_MAX_NUMERIC_RATIO = 0.2
TABLE_CONTENTS_MAX_AVG_WORDS_PER_CELL = 2.5
TABLE_CONTENTS_MAX_FIRST_COL_WORDS = 2.0
TABLE_REFERENCE_MIN_ROWS = 6
TABLE_REFERENCE_MAX_COLS = 5
TABLE_REFERENCE_MAX_FILLED_CELLS_PER_ROW = 5.0
TABLE_REFERENCE_MAX_NUMERIC_RATIO = 0.12
TABLE_REFERENCE_MIN_FIRST_COL_WORDS = 1.5
TABLE_REFERENCE_MIN_AVG_LINE_LEN = 60.0
TABLE_REFERENCE_MIN_URL_HITS = 2
TABLE_REFERENCE_MIN_YEAR_HITS = 3
TABLE_REFERENCE_MIN_TERM_HITS = 3
TABLE_REFERENCE_MIN_NUMBERED_HITS = 4
TABLE_REFERENCE_MIN_AVG_WORDS_PER_CELL = 1.8
TABLE_REFERENCE_TERMS = (
    "doi.org",
    "journal",
    "working paper",
    "oecd publishing",
    "publishing, paris",
    "accessed",
    "interview",
    "press release",
    "vol.",
    "no.",
    "pp.",
    "ssrn",
    "mercatus",
)
TABLE_FRONT_MATTER_MAX_COLS = 4
TABLE_FRONT_MATTER_MAX_NUMERIC_RATIO = 0.12
TABLE_FRONT_MATTER_MAX_AVG_WORDS_PER_CELL = 4.0
TABLE_FRONT_MATTER_MIN_AREA_FRAC = 0.08
TABLE_FRONT_MATTER_TERMS = (
    "table of contents",
    "acknowledgments",
    "acknowledgements",
    "endnotes",
)
TABLE_CONTACT_MAX_COLS = 3
TABLE_CONTACT_MAX_NUMERIC_RATIO = 0.05
TABLE_CONTACT_MIN_AREA_FRAC = 0.12
TABLE_CONTACT_MIN_LINES = 6
TABLE_CONTACT_MIN_AVG_LINE_LEN = 28.0
TABLE_VISUAL_QUOTE_MAX_ROWS = 12
TABLE_VISUAL_QUOTE_MAX_COLS = 3
TABLE_VISUAL_QUOTE_MAX_NUMERIC_RATIO = 0.05
TABLE_VISUAL_QUOTE_MAX_AVG_WORDS_PER_CELL = 4.5
TABLE_VISUAL_QUOTE_MAX_TEXT_LEN = 320
TABLE_VISUAL_QUOTE_MAX_ASPECT = 0.45
TABLE_VISUAL_QUOTE_MAX_WIDTH_FRAC = 0.42
TABLE_VISUAL_QUOTE_MIN_HEIGHT_FRAC = 0.55
TABLE_VISUAL_QUOTE_MAX_FILLED_CELLS_PER_ROW = 1.35
TABLE_VISUAL_QUOTE_MAX_TEXT_BLOCK_AREA = 0.2
TABLE_SECTION_LIST_MIN_ROWS = 8
TABLE_SECTION_LIST_MAX_COLS = 6
TABLE_SECTION_LIST_MAX_NUMERIC_RATIO = 0.15
TABLE_SECTION_LIST_MAX_AVG_WORDS_PER_CELL = 3.5
TABLE_SECTION_LIST_MIN_TEXT_BLOCK_AREA = 0.2
TABLE_SECTION_LIST_MAX_AVG_LINE_LEN = 48.0
TABLE_SECTION_LIST_MIN_SHORT_LINE_RATIO = 0.7
TABLE_SECTION_LIST_MIN_TERMINAL_NUMBER_HITS = 4
TABLE_SECTION_LIST_MAX_AREA_FRAC_WITHOUT_NUMBERS = 0.2
TABLE_SECTION_LIST_MIN_FRAGMENTED_DOT_HITS = 4
TABLE_SECTION_LIST_MAX_NARROW_ASPECT = 0.4
TABLE_FIGURE_FRAGMENT_COMPACT_MAX_ROWS = 3
TABLE_FIGURE_FRAGMENT_COMPACT_MAX_AREA_FRAC = 0.03
TABLE_FIGURE_FRAGMENT_MIN_NUMERIC_RATIO = 0.35
TABLE_FIGURE_FRAGMENT_MAX_AVG_WORDS_PER_CELL = 2.5
TABLE_FIGURE_FRAGMENT_MIN_WIDE_COLS = 20
TABLE_FIGURE_FRAGMENT_MAX_FILL_RATIO = 0.18
TABLE_WIDE_FIGURE_CONTEXT_MAX_DIST = 320.0
TABLE_WIDE_FIGURE_CONTEXT_TOP_BAND = 120.0
TABLE_WIDE_FIGURE_CONTEXT_HORIZONTAL_PAD = 140.0
TABLE_HORIZONTAL_EXPAND_MIN_V_OVERLAP = 0.35
TABLE_HORIZONTAL_EXPAND_MAX_GAP_FRAC = 0.08
TABLE_HORIZONTAL_EXPAND_MIN_GAIN = 8.0
TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_V_OVERLAP = 0.8
TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_GAP_FRAC = 0.3
TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_LINES = 6
TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_AVG_LINE_LEN = 18.0
TABLE_OVERLAPPING_NOTE_MAX_GAP = 10.0
TABLE_RANKED_MIN_ROWS = 4
TABLE_RANKED_MAX_RANK = 10
TABLE_RANKED_X_CLUSTER_GAP_FRAC = 0.08
TABLE_RANKED_MAX_ROW_GAP_FRAC = 0.16
TABLE_RANKED_MIN_RULE_WIDTH_FRAC = 0.25
TABLE_RANKED_HEADER_MAX_GAP = 60.0
TABLE_RANKED_HEADER_SEED_MAX_GAP = 90.0
TABLE_RANKED_RULE_X_TOL = 24.0
TABLE_RANKED_BODY_MAX_GAP = 18.0
TABLE_RANKED_NOTE_MAX_GAP = 80.0
TABLE_RANKED_NOTE_X_TOL = 36.0
CHART_RANKED_TABLE_DUP_IOU = 0.65
CHART_RANKED_TABLE_DUP_CONTAINMENT = 0.82
TABLE_TOP_SLACK_MAX = 8.0
TABLE_TOP_HEADER_SLACK_MAX = 12.0
TABLE_EXPLICIT_TITLE_MAX_GAP = 72.0
TABLE_EXPLICIT_SUBTITLE_MAX_GAP = 32.0
NOTE_LABEL_PREFIXES = ("note:", "notes:", "source:", "sources:", "statlink")
EMAIL_ADDRESS_RX = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")
_PAGE_NUMBER_RX = re.compile(
    r"^\s*[^0-9A-Za-z]*\d{1,4}(?:\s*[-–]\s*\d{1,4})?[^0-9A-Za-z]*\s*$"
)
_PANEL_TITLE_EXCLUDE_RX = re.compile(
    r"^\s*(?:figure|fig\.|exhibit|chart|graph|table|source|infographic)\b",
    re.IGNORECASE,
)
_TABLE_FOOTNOTE_RX = re.compile(r"^\s*(?:\*+|\d+\.)\s+")
_FIGURE_CONTEXT_RX = re.compile(r"^\s*(?:figure|fig\.|infographic)\s+\d", re.IGNORECASE)


@dataclass(frozen=True)
class _TableCandidate:
    bbox: Tuple[float, float, float, float]
    method: str
    row_count: int
    col_count: int
    col_consistency: float
    row_len_cv: float
    non_empty_cells: int
    total_cells: int
    numeric_cells: int
    numeric_ratio: float
    avg_words_per_cell: float
    avg_first_col_words: float
    index_page_ratio: float
    preview: str
    text: str
    text_len: int
    line_count: int
    avg_line_len: float
    text_block_area_frac: float
    text_block_line_count: int
    text_block_avg_line_len: float
    caption_hint: bool
    figure_context_hint: bool
    wide_figure_context_hint: bool
    area_frac: float
    width_frac: float
    height_frac: float
    aspect: float


@dataclass(frozen=True)
class _ChartRect:
    rect: fitz.Rect
    kind: str
    xref: Optional[int] = None
    caption: Optional[str] = None
    caption_rect: Optional[fitz.Rect] = None


@dataclass(frozen=True)
class _PageTextBlock:
    rect: fitz.Rect
    text: str
    lines: int
    chars: int
    avg_line_len: float
    max_font_size: float
    min_font_size: float


@dataclass(frozen=True)
class _PageTextLine:
    rect: fitz.Rect
    text: str
    max_font_size: float


@dataclass(frozen=True)
class _TableTextBand:
    rect: fitz.Rect
    text: str
    fragment_count: int
    numeric_fragment_count: int
    word_count: int
    max_font_size: float
    max_gap_x: float


@dataclass(frozen=True)
class _RankedTableRegion:
    bbox: Tuple[float, float, float, float]
    row_count: int
    col_count: int


def _s(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except PDF_FIGURE_EXCEPTIONS:
        return ""


def _int_count(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _rect_iou(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    union = a.get_area() + b.get_area() - inter.get_area()
    if union <= 0.0:
        return 0.0
    return inter.get_area() / union


def _table_normalize_text(text: str) -> str:
    normalized = str(text or "").replace("|", " ").replace("\u00a0", " ")
    return " ".join(normalized.split())


def _table_text_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw_line in str(text or "").splitlines():
        normalized = _table_normalize_text(raw_line)
        if normalized:
            lines.append(normalized)
    return lines


def _starts_with_lower_alpha(text: str) -> bool:
    for char in str(text or ""):
        if not char.isalpha():
            continue
        return char.islower()
    return False


def _table_text_has_note_marker(text: str) -> bool:
    for line in _table_text_lines(text):
        lowered = line.lower()
        if _TABLE_FOOTNOTE_RX.match(line):
            return True
        if lowered.startswith(NOTE_LABEL_PREFIXES):
            return True
    return False


def _table_text_has_figure_context(text: str) -> bool:
    for line in _table_text_lines(text):
        if _FIGURE_CONTEXT_RX.match(line):
            return True
    return False


def _table_text_starts_with_footnote_marker(text: str) -> bool:
    lines = _table_text_lines(text)
    if not lines:
        return False
    return bool(_TABLE_FOOTNOTE_RX.match(lines[0]))


def _table_text_has_embedded_note_marker(text: str) -> bool:
    lines = _table_text_lines(text)
    if len(lines) < 2:
        return False
    for line in lines[1:]:
        lowered = line.lower()
        if _TABLE_FOOTNOTE_RX.match(line):
            return True
        if lowered.startswith(NOTE_LABEL_PREFIXES):
            return True
    return False


def _table_page_text_blocks(
    page: fitz.Page,
    text_dict: Optional[dict[str, object]] = None,
) -> List[_PageTextBlock]:
    blocks: List[_PageTextBlock] = []
    if text_dict is None:
        try:
            text_dict = page.get_text("dict")
        except PDF_FIGURE_EXCEPTIONS:
            text_dict = {}
    raw_blocks = text_dict.get("blocks") or []
    for raw_block in raw_blocks:
        if raw_block.get("type") != 0:
            continue
        bbox = raw_block.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        rect = fitz.Rect(*bbox)
        line_texts: List[str] = []
        font_sizes: List[float] = []
        for line in raw_block.get("lines", []):
            span_texts: List[str] = []
            for span in line.get("spans", []):
                span_text = _s(span.get("text")).strip()
                if not span_text:
                    continue
                span_texts.append(span_text)
                try:
                    font_sizes.append(float(span.get("size") or 0.0))
                except (TypeError, ValueError):
                    continue
            if span_texts:
                line_texts.append(" ".join(span_texts).strip())
        text = "\n".join(part for part in line_texts if part).strip()
        if not text:
            continue
        lines, chars = _text_stats(text)
        avg_line_len = chars / max(1, lines)
        blocks.append(
            _PageTextBlock(
                rect=rect,
                text=text,
                lines=lines,
                chars=chars,
                avg_line_len=avg_line_len,
                max_font_size=max(font_sizes) if font_sizes else 0.0,
                min_font_size=min(font_sizes) if font_sizes else 0.0,
            )
        )
    if blocks:
        return blocks
    try:
        fallback_blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        fallback_blocks = []
    for x0, y0, x1, y1, text, *_ in fallback_blocks:
        text_str = str(text or "").strip()
        if not text_str:
            continue
        lines, chars = _text_stats(text_str)
        avg_line_len = chars / max(1, lines)
        blocks.append(
            _PageTextBlock(
                rect=fitz.Rect(float(x0), float(y0), float(x1), float(y1)),
                text=text_str,
                lines=lines,
                chars=chars,
                avg_line_len=avg_line_len,
                max_font_size=0.0,
                min_font_size=0.0,
            )
        )
    return blocks


def _table_rank_value(block: _PageTextBlock) -> Optional[int]:
    normalized = _table_normalize_text(block.text)
    if not re.fullmatch(r"\d{1,2}", normalized):
        return None
    try:
        value = int(normalized)
    except ValueError:
        return None
    if value < 1 or value > TABLE_RANKED_MAX_RANK:
        return None
    return value


def _table_horizontal_rule_rects(page: fitz.Page) -> List[fitz.Rect]:
    rules: List[fitz.Rect] = []
    page_rect = page.rect
    min_width = page_rect.width * TABLE_RANKED_MIN_RULE_WIDTH_FRAC
    try:
        drawings = page.get_drawings() or []
    except PDF_FIGURE_EXCEPTIONS:
        drawings = []
    for drawing in drawings:
        if drawing.get("type") != "s":
            continue
        try:
            rect = fitz.Rect(drawing["rect"])
        except PDF_FIGURE_EXCEPTIONS:
            continue
        if rect.width < min_width:
            continue
        if rect.height > 3.5:
            continue
        rules.append(rect)
    return sorted(rules, key=lambda rect: (rect.y0, rect.x0))


def _group_rank_blocks_into_sequences(
    blocks: List[_PageTextBlock],
    page_rect: fitz.Rect,
) -> List[List[_PageTextBlock]]:
    rank_blocks = [
        block
        for block in blocks
        if _table_rank_value(block) is not None
    ]
    if not rank_blocks:
        return []
    x_tol = max(42.0, page_rect.width * TABLE_RANKED_X_CLUSTER_GAP_FRAC)
    max_gap_y = max(32.0, page_rect.height * TABLE_RANKED_MAX_ROW_GAP_FRAC)
    grouped: List[List[_PageTextBlock]] = []
    for block in sorted(rank_blocks, key=lambda item: (item.rect.x0, item.rect.y0)):
        placed = False
        for group in grouped:
            ref = group[0]
            if abs(block.rect.x0 - ref.rect.x0) <= x_tol and abs(block.rect.x1 - ref.rect.x1) <= x_tol:
                group.append(block)
                placed = True
                break
        if not placed:
            grouped.append([block])

    sequences: List[List[_PageTextBlock]] = []
    for group in grouped:
        current: List[_PageTextBlock] = []
        expected = 1
        last_y: Optional[float] = None
        for block in sorted(group, key=lambda item: item.rect.y0):
            value = _table_rank_value(block)
            if value is None:
                continue
            if value == 1:
                current = [block]
                expected = 2
                last_y = block.rect.y0
                continue
            if not current:
                continue
            if value != expected:
                continue
            if last_y is not None and block.rect.y0 - last_y > max_gap_y:
                continue
            current.append(block)
            expected += 1
            last_y = block.rect.y0
        if len(current) >= TABLE_RANKED_MIN_ROWS:
            sequences.append(current)
    return sequences


def _ranked_table_panel_region(
    page: fitz.Page,
    rank_blocks: List[_PageTextBlock],
    blocks: List[_PageTextBlock],
    rules: List[fitz.Rect],
) -> Optional[_RankedTableRegion]:
    if not rank_blocks:
        return None
    first_rank = rank_blocks[0]
    last_rank = rank_blocks[-1]
    header_rules = [
        rule
        for rule in rules
        if rule.y0 <= first_rank.rect.y0 + 4.0
        and first_rank.rect.y0 - rule.y0 <= TABLE_RANKED_HEADER_MAX_GAP
        and rule.x0 <= first_rank.rect.x0 + TABLE_RANKED_RULE_X_TOL
    ]
    header_rule: Optional[fitz.Rect] = None
    if header_rules:
        header_rule = min(
            header_rules,
            key=lambda rule: (
                max(0.0, first_rank.rect.y0 - rule.y0),
                abs(first_rank.rect.x0 - rule.x0),
                -rule.width,
            ),
        )
    seed_rules = [
        rule
        for rule in rules
        if rule.x0 <= first_rank.rect.x0 + TABLE_RANKED_RULE_X_TOL
        and rule.y0 >= first_rank.rect.y0 - 4.0
        and rule.y0 <= last_rank.rect.y1 + TABLE_RANKED_BODY_MAX_GAP
    ]
    if header_rule is None and seed_rules:
        header_rule = min(
            seed_rules,
            key=lambda rule: (
                abs(first_rank.rect.x0 - rule.x0),
                -rule.width,
            ),
        )
    if header_rule is None:
        return None
    panel_rules = [
        rule
        for rule in rules
        if abs(rule.x0 - header_rule.x0) <= TABLE_RANKED_RULE_X_TOL
        and abs(rule.x1 - header_rule.x1) <= TABLE_RANKED_RULE_X_TOL
        and rule.y0 >= header_rule.y0 - 1.0
        and rule.y0 <= last_rank.rect.y1 + TABLE_RANKED_BODY_MAX_GAP
    ]
    if len(panel_rules) < 3:
        return None

    body_font_size = _table_page_body_font_size(blocks)
    x0 = min(rule.x0 for rule in panel_rules)
    x1 = max(rule.x1 for rule in panel_rules)
    row_top = first_rank.rect.y0
    row_bottom = last_rank.rect.y1
    content_blocks = [
        block
        for block in blocks
        if not _is_page_number_text(_table_normalize_text(block.text))
        and block.rect.y1 >= row_top - 4.0
        and block.rect.y0 <= row_bottom + 4.0
        and block.rect.x1 >= x0
        and block.rect.x0 <= x1
    ]
    if content_blocks:
        row_top = min(row_top, min(block.rect.y0 for block in content_blocks))
        row_bottom = max(row_bottom, max(block.rect.y1 for block in content_blocks))

    header_block_max_gap = (
        TABLE_RANKED_HEADER_MAX_GAP
        if header_rules
        else TABLE_RANKED_HEADER_SEED_MAX_GAP
    )
    header_blocks = [
        block
        for block in blocks
        if not _table_block_is_margin_noise(block, page.rect)
        and block.rect.y1 <= header_rule.y0 + 1.0
        and header_rule.y0 - block.rect.y1 <= header_block_max_gap
        and _horizontal_overlap_ratio(block.rect, fitz.Rect(x0, header_rule.y0, x1, row_bottom)) >= 0.2
    ]
    y0 = min([row_top] + [block.rect.y0 for block in header_blocks])
    if header_rules:
        y0 = min(y0, header_rule.y0)
    y1 = max(row_bottom, max(rule.y0 for rule in panel_rules))

    for block in sorted(blocks, key=lambda item: item.rect.y0):
        if _table_block_is_margin_noise(block, page.rect):
            continue
        if block.rect.y0 < y1 - 1.0:
            continue
        gap = block.rect.y0 - y1
        if gap > TABLE_RANKED_NOTE_MAX_GAP:
            break
        if block.rect.x0 < x0 - TABLE_RANKED_NOTE_X_TOL:
            continue
        if block.rect.x1 > x1 + TABLE_RANKED_NOTE_X_TOL:
            continue
        if _horizontal_overlap_ratio(block.rect, fitz.Rect(x0, y0, x1, y1)) < 0.2:
            continue
        if _table_block_is_note_like(block) or _table_block_is_body_paragraph(
            block, body_font_size
        ):
            y1 = max(y1, block.rect.y1)
            continue
        break

    header_label_count = max(
        1,
        sum(
            1
            for block in header_blocks
            if _table_normalize_text(block.text)
        ),
    )
    col_count = max(2, min(6, header_label_count + 1))
    rect = fitz.Rect(x0, y0, x1, y1) & page.rect
    if rect.is_empty:
        return None
    return _RankedTableRegion(
        bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
        row_count=len(rank_blocks),
        col_count=col_count,
    )


def _detect_ranked_table_candidates(
    plumber_page: pdfplumber.page.Page,
    page: fitz.Page,
    *,
    page_text_blocks: Optional[List[_PageTextBlock]] = None,
) -> List[_TableCandidate]:
    blocks = page_text_blocks if page_text_blocks is not None else _table_page_text_blocks(page)
    if not blocks:
        return []
    rules = _table_horizontal_rule_rects(page)
    if not rules:
        return []
    candidates: List[_TableCandidate] = []
    page_rect = page.rect
    body_font_size = _table_page_body_font_size(blocks)
    for rank_sequence in _group_rank_blocks_into_sequences(blocks, page_rect):
        region = _ranked_table_panel_region(page, rank_sequence, blocks, rules)
        if region is None:
            continue
        expanded_bbox = _expand_table_bbox(
            page,
            region.bbox,
            "ranked",
            page_text_blocks=blocks,
        )
        x0, y0, x1, y1 = expanded_bbox
        text = _extract_text_in_bbox(plumber_page, expanded_bbox)
        text_len = len(text.strip())
        if text_len < TABLE_MIN_TEXT_CHARS:
            continue
        line_count, text_chars = _text_stats(text)
        avg_line_len = (text_chars / line_count) if line_count else 0.0
        text_block_area_frac, text_block_line_count, text_block_avg_line_len = (
            _text_block_stats(
                page,
                expanded_bbox,
                blocks=[
                    (
                        block.rect.x0,
                        block.rect.y0,
                        block.rect.x1,
                        block.rect.y1,
                        block.text,
                    )
                    for block in blocks
                ],
            )
        )
        normalized = _table_normalize_text(text)
        word_count = len(normalized.split())
        non_empty_cells = max(TABLE_MIN_NONEMPTY_CELLS, region.row_count * region.col_count)
        total_cells = non_empty_cells
        numeric_chars = sum(1 for char in text if char.isdigit())
        alpha_num_chars = sum(1 for char in text if char.isalnum())
        numeric_ratio = numeric_chars / max(1, alpha_num_chars)
        candidate = _TableCandidate(
            bbox=(x0, y0, x1, y1),
            method="ranked",
            row_count=region.row_count,
            col_count=region.col_count,
            col_consistency=1.0,
            row_len_cv=0.0,
            non_empty_cells=non_empty_cells,
            total_cells=total_cells,
            numeric_cells=min(non_empty_cells, numeric_chars),
            numeric_ratio=numeric_ratio,
            avg_words_per_cell=word_count / max(1, non_empty_cells),
            avg_first_col_words=1.0,
            index_page_ratio=0.0,
            preview=text[:400],
            text=text,
            text_len=text_len,
            line_count=line_count,
            avg_line_len=avg_line_len,
            text_block_area_frac=text_block_area_frac,
            text_block_line_count=text_block_line_count,
            text_block_avg_line_len=text_block_avg_line_len,
            caption_hint=False,
            figure_context_hint=False,
            wide_figure_context_hint=False,
            area_frac=((x1 - x0) * (y1 - y0)) / max(1.0, page_rect.width * page_rect.height),
            width_frac=(x1 - x0) / max(1.0, page_rect.width),
            height_frac=(y1 - y0) / max(1.0, page_rect.height),
            aspect=(x1 - x0) / max(1.0, y1 - y0),
        )
        ok, _reason = _validate_table_candidate(candidate)
        if ok:
            candidates.append(candidate)
    return candidates


def _table_page_body_font_size(blocks: List[_PageTextBlock]) -> float:
    sizes = [block.max_font_size for block in blocks if block.max_font_size > 0.0]
    if not sizes:
        return 0.0
    try:
        return float(statistics.median(sizes))
    except statistics.StatisticsError:
        return float(sizes[0])


def _table_fragment_is_numeric(text: str) -> bool:
    compact = _table_normalize_text(text).replace(" ", "")
    if not compact:
        return False
    compact = compact.replace("*", "")
    return _cell_is_numeric(compact)


def _table_page_text_lines(
    page: fitz.Page,
    text_dict: Optional[dict[str, object]] = None,
) -> List[_PageTextLine]:
    if text_dict is None:
        try:
            text_dict = page.get_text("dict")
        except PDF_FIGURE_EXCEPTIONS:
            return []
    lines: List[_PageTextLine] = []
    for block in text_dict.get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            parts: List[str] = []
            min_x: Optional[float] = None
            min_y: Optional[float] = None
            max_x: Optional[float] = None
            max_y: Optional[float] = None
            max_font_size = 0.0
            for span in line.get("spans") or []:
                text = str(span.get("text") or "")
                if not text.strip():
                    continue
                bbox = span.get("bbox") or []
                if len(bbox) != 4:
                    continue
                x0, y0, x1, y1 = map(float, bbox)
                parts.append(text.strip())
                min_x = x0 if min_x is None else min(min_x, x0)
                min_y = y0 if min_y is None else min(min_y, y0)
                max_x = x1 if max_x is None else max(max_x, x1)
                max_y = y1 if max_y is None else max(max_y, y1)
                max_font_size = max(max_font_size, float(span.get("size") or 0.0))
            if not parts or None in {min_x, min_y, max_x, max_y}:
                continue
            lines.append(
                _PageTextLine(
                    rect=fitz.Rect(
                        float(min_x),
                        float(min_y),
                        float(max_x),
                        float(max_y),
                    ),
                    text=_table_normalize_text(" ".join(parts)),
                    max_font_size=max_font_size,
                )
            )
    return lines


def _table_text_bands(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, object]] = None,
    page_text_lines: Optional[List[_PageTextLine]] = None,
) -> List[_TableTextBand]:
    lines = sorted(
        page_text_lines
        if page_text_lines is not None
        else _table_page_text_lines(page, text_dict=text_dict),
        key=lambda line: (
            round((line.rect.y0 + line.rect.y1) / 2.0, 1),
            line.rect.x0,
            line.rect.x1,
        ),
    )
    if not lines:
        return []

    def _flush(group: List[_PageTextLine], bands: List[_TableTextBand]) -> None:
        ordered = sorted(group, key=lambda line: (line.rect.x0, line.rect.y0))
        rect = fitz.Rect(ordered[0].rect)
        parts = [line.text for line in ordered if line.text]
        max_font_size = max((line.max_font_size for line in ordered), default=0.0)
        max_gap_x = 0.0
        for index in range(1, len(ordered)):
            prev = ordered[index - 1].rect
            cur = ordered[index].rect
            max_gap_x = max(max_gap_x, max(0.0, cur.x0 - prev.x1))
            rect |= cur
        text = _table_normalize_text(" ".join(parts))
        bands.append(
            _TableTextBand(
                rect=rect,
                text=text,
                fragment_count=len(ordered),
                numeric_fragment_count=sum(
                    1 for line in ordered if _table_fragment_is_numeric(line.text)
                ),
                word_count=len(text.split()),
                max_font_size=max_font_size,
                max_gap_x=max_gap_x,
            )
        )

    bands: List[_TableTextBand] = []
    current: List[_PageTextLine] = []
    current_center = 0.0
    tolerance = 3.6
    for line in lines:
        center = (line.rect.y0 + line.rect.y1) / 2.0
        if not current:
            current = [line]
            current_center = center
            continue
        if abs(center - current_center) <= tolerance:
            current.append(line)
            current_center = sum(
                (item.rect.y0 + item.rect.y1) / 2.0 for item in current
            ) / len(current)
            continue
        _flush(current, bands)
        current = [line]
        current_center = center
    if current:
        _flush(current, bands)
    return bands


def _table_band_is_margin_noise(band: _TableTextBand, page_rect: fitz.Rect) -> bool:
    normalized = _table_normalize_text(band.text)
    if _is_page_number_text(normalized):
        return True
    if (
        band.rect.y0 <= page_rect.y0 + page_rect.height * 0.045
        and len(normalized) <= 24
    ):
        return True
    if (
        band.rect.y1 >= page_rect.y1 - page_rect.height * 0.03
        and len(normalized) <= 128
        and ("oecd" in normalized.lower() or "economic outlook" in normalized.lower())
    ):
        return True
    return False


def _table_band_is_note_like(band: _TableTextBand) -> bool:
    normalized = _table_normalize_text(band.text)
    lowered = normalized.lower()
    if not normalized:
        return False
    if _table_text_has_note_marker(band.text):
        return True
    if "statlink" in lowered or "http://" in lowered or "https://" in lowered:
        return True
    return False


def _table_band_is_heading_like(
    band: _TableTextBand,
    body_font_size: float,
) -> bool:
    normalized = _table_normalize_text(band.text)
    if not normalized:
        return False
    word_count = len(normalized.split())
    if word_count == 0 or word_count > 18:
        return False
    if len(normalized) > 160:
        return False
    if normalized.endswith("."):
        return False
    font_large = (
        body_font_size > 0.0 and band.max_font_size >= body_font_size + 0.75
    )
    text_heading = _heading_like_block(normalized, 1, float(len(normalized)))
    return font_large or text_heading


def _table_band_is_body_paragraph(
    band: _TableTextBand,
    body_font_size: float,
) -> bool:
    if _table_band_is_note_like(band):
        return False
    if _table_band_is_heading_like(band, body_font_size):
        return False
    normalized = _table_normalize_text(band.text)
    if band.fragment_count != 1:
        return False
    if band.word_count >= 10:
        return True
    if len(normalized) >= 60 and band.word_count >= 8:
        return True
    return False


def _table_band_is_title_like(
    band: _TableTextBand,
    body_font_size: float,
) -> bool:
    if _table_band_is_note_like(band):
        return False
    normalized = _table_normalize_text(band.text)
    lowered = normalized.lower()
    if lowered.startswith(("table ", "exhibit ")):
        return True
    if ":" in normalized and len(normalized.split()) <= 16:
        return True
    return _table_band_is_heading_like(band, body_font_size)


def _table_band_is_row_like(
    band: _TableTextBand,
    page_rect: fitz.Rect,
) -> bool:
    if _table_band_is_margin_noise(band, page_rect):
        return False
    if _table_band_is_note_like(band):
        return False
    normalized = _table_normalize_text(band.text)
    if not normalized:
        return False
    if band.numeric_fragment_count >= 3:
        return True
    if band.fragment_count >= 4 and band.numeric_fragment_count >= 2:
        return True
    if (
        band.fragment_count >= 3
        and band.numeric_fragment_count >= 1
        and band.max_gap_x >= max(18.0, page_rect.width * 0.03)
        and band.word_count <= 14
    ):
        return True
    if band.fragment_count >= 5 and band.word_count <= 12:
        return True
    return False


def _table_attach_title_bands(
    page: fitz.Page,
    rect: fitz.Rect,
    bands: List[_TableTextBand],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = max(24.0, page_rect.height * 0.055)
    current_top = expanded.y0
    candidates = sorted(bands, key=lambda band: band.rect.y1, reverse=True)
    for band in candidates:
        if band.rect.y1 > current_top:
            continue
        gap = current_top - band.rect.y1
        if gap > max_gap_y:
            continue
        if _table_band_is_margin_noise(band, page_rect):
            continue
        if _horizontal_overlap_ratio(band.rect, rect) < 0.35 and abs(
            band.rect.x0 - rect.x0
        ) > 36:
            continue
        if not _table_band_is_title_like(band, body_font_size):
            continue
        expanded |= band.rect
        current_top = band.rect.y0
    return expanded


def _table_attach_note_bands(
    page: fitz.Page,
    rect: fitz.Rect,
    bands: List[_TableTextBand],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = max(30.0, page_rect.height * 0.032)
    current_bottom = expanded.y1
    note_started = False
    note_continuation_allowed = False
    candidates = sorted(bands, key=lambda band: band.rect.y0)
    for band in candidates:
        if band.rect.y0 < current_bottom - 1:
            continue
        gap = band.rect.y0 - current_bottom
        if gap > max_gap_y:
            if note_started:
                break
            continue
        if _table_band_is_margin_noise(band, page_rect):
            continue
        h_overlap = _horizontal_overlap_ratio(band.rect, rect)
        if h_overlap < 0.2 and not _table_band_is_note_like(band):
            continue
        if _table_band_is_note_like(band):
            expanded |= band.rect
            current_bottom = band.rect.y1
            note_started = True
            note_continuation_allowed = _table_text_starts_with_footnote_marker(
                band.text
            )
            continue
        if note_continuation_allowed and _table_band_is_note_continuation(
            band, rect, body_font_size
        ):
            expanded |= band.rect
            current_bottom = band.rect.y1
            continue
        if _table_band_is_heading_like(
            band, body_font_size
        ) or _table_band_is_body_paragraph(band, body_font_size):
            break
    return expanded


def _shrink_stream_table_rect(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    bands: Optional[List[_TableTextBand]] = None,
) -> fitz.Rect:
    page_rect = page.rect
    relevant_bands = [
        band
        for band in (bands if bands is not None else _table_text_bands(page))
        if band.rect.y1 >= rect.y0
        and band.rect.y0 <= rect.y1
        and _horizontal_overlap_ratio(band.rect, rect) >= 0.2
    ]
    if not relevant_bands:
        return rect

    row_bands = [
        band
        for band in relevant_bands
        if _table_band_is_row_like(band, page_rect)
    ]
    if not row_bands:
        return rect

    row_bands = sorted(row_bands, key=lambda band: (band.rect.y0, band.rect.x0))
    gap_limit = max(18.0, page_rect.height * 0.02)
    clusters: List[List[_TableTextBand]] = []
    current: List[_TableTextBand] = []
    for band in row_bands:
        if not current:
            current = [band]
            continue
        gap = band.rect.y0 - current[-1].rect.y1
        if gap <= gap_limit:
            current.append(band)
            continue
        clusters.append(current)
        current = [band]
    if current:
        clusters.append(current)
    if not clusters:
        return rect

    def _cluster_score(cluster: List[_TableTextBand]) -> float:
        return float(
            sum(
                band.fragment_count + band.numeric_fragment_count * 3
                for band in cluster
            )
        )

    def _cluster_bounds(cluster: List[_TableTextBand]) -> Tuple[float, float]:
        return (
            min(band.rect.y0 for band in cluster),
            max(band.rect.y1 for band in cluster),
        )

    best_index = max(range(len(clusters)), key=lambda idx: _cluster_score(clusters[idx]))
    best_cluster = list(clusters[best_index])
    continuation_gap_limit = max(
        TABLE_STREAM_CONTINUATION_MAX_GAP,
        page_rect.height * TABLE_STREAM_CONTINUATION_MAX_GAP_FRAC,
    )
    cluster_top, cluster_bottom = _cluster_bounds(best_cluster)
    for cluster in clusters[best_index + 1 :]:
        next_top, next_bottom = _cluster_bounds(cluster)
        if next_top - cluster_bottom > continuation_gap_limit:
            break
        if not _cluster_is_row_continuation(cluster, rect, page_rect):
            break
        best_cluster.extend(cluster)
        cluster_bottom = next_bottom

    cluster_top, cluster_bottom = _cluster_bounds(best_cluster)
    included = [
        band
        for band in relevant_bands
        if band.rect.y0 >= cluster_top - 2.0
        and band.rect.y1 <= cluster_bottom + 2.0
        and not _table_band_is_margin_noise(band, page_rect)
    ]
    if included:
        cluster_top = min(band.rect.y0 for band in included)
        cluster_bottom = max(band.rect.y1 for band in included)
    if cluster_bottom <= cluster_top:
        return rect
    return fitz.Rect(rect.x0, cluster_top, rect.x1, cluster_bottom)


def _table_block_is_margin_noise(block: _PageTextBlock, page_rect: fitz.Rect) -> bool:
    text_normalized = _table_normalize_text(block.text)
    if _is_page_number_text(text_normalized):
        return True
    if block.rect.y0 <= page_rect.y0 + page_rect.height * 0.045 and len(text_normalized) <= 18:
        return True
    if block.rect.y1 >= page_rect.y1 - page_rect.height * 0.03 and len(text_normalized) <= 96:
        lowered = text_normalized.lower()
        if "oecd" in lowered or "economic outlook" in lowered:
            return True
    return False


def _cluster_is_row_continuation(
    cluster: List[_TableTextBand],
    rect: fitz.Rect,
    page_rect: fitz.Rect,
) -> bool:
    if not cluster or len(cluster) > TABLE_STREAM_CONTINUATION_MAX_BANDS:
        return False
    cluster_rect = fitz.Rect(
        min(band.rect.x0 for band in cluster),
        min(band.rect.y0 for band in cluster),
        max(band.rect.x1 for band in cluster),
        max(band.rect.y1 for band in cluster),
    )
    if _horizontal_overlap_ratio(cluster_rect, rect) < TABLE_EXPAND_MIN_H_OVERLAP:
        return False
    for band in cluster:
        if _table_band_is_margin_noise(band, page_rect):
            return False
        if band.numeric_fragment_count < TABLE_STREAM_CONTINUATION_MIN_NUMERIC_FRAGMENTS:
            return False
    return True


def _table_block_is_note_like(block: _PageTextBlock) -> bool:
    normalized = _table_normalize_text(block.text)
    lowered = normalized.lower()
    if not normalized:
        return False
    if _table_text_has_note_marker(block.text):
        return True
    if "statlink" in lowered or "doi.org" in lowered or "http://" in lowered or "https://" in lowered:
        return True
    return False


def _table_block_is_mixed_footer_cluster(block: _PageTextBlock) -> bool:
    if not _table_text_has_embedded_note_marker(block.text):
        return False
    if block.lines > 10:
        return False
    if block.avg_line_len > 85:
        return False
    return True


def _table_block_is_heading_like(
    block: _PageTextBlock,
    body_font_size: float,
) -> bool:
    normalized = _table_normalize_text(block.text)
    if not normalized:
        return False
    word_count = len(normalized.split())
    if word_count == 0 or word_count > 18:
        return False
    if len(normalized) > 140:
        return False
    if normalized.endswith("."):
        return False
    font_large = (
        body_font_size > 0.0 and block.max_font_size >= body_font_size + 0.75
    )
    text_heading = _heading_like_block(
        normalized,
        block.lines,
        block.avg_line_len,
    )
    return font_large or text_heading


def _table_block_is_body_paragraph(
    block: _PageTextBlock,
    body_font_size: float,
) -> bool:
    if _table_block_is_note_like(block):
        return False
    if _table_block_is_heading_like(block, body_font_size):
        return False
    normalized = _table_normalize_text(block.text)
    if block.lines >= 3 and block.avg_line_len >= 24:
        return True
    if block.lines >= 2 and block.avg_line_len >= 42:
        return True
    if len(normalized.split()) >= 18 and block.avg_line_len >= 28:
        return True
    return False


def _table_block_is_note_continuation(
    block: _PageTextBlock,
    rect: fitz.Rect,
    body_font_size: float,
) -> bool:
    if _table_block_is_note_like(block):
        return False
    if _table_block_is_heading_like(block, body_font_size):
        return False
    if not _table_block_is_body_paragraph(block, body_font_size):
        return False
    if _horizontal_overlap_ratio(block.rect, rect) < TABLE_NOTE_CONTINUATION_MIN_H_OVERLAP:
        return False
    if block.rect.x0 > rect.x0 + TABLE_NOTE_CONTINUATION_MAX_X_OFFSET:
        return False
    if len(_table_normalize_text(block.text).split()) < TABLE_NOTE_CONTINUATION_MIN_WORDS:
        return False
    return True


def _table_band_is_note_continuation(
    band: _TableTextBand,
    rect: fitz.Rect,
    body_font_size: float,
) -> bool:
    if _table_band_is_note_like(band):
        return False
    if _table_band_is_heading_like(band, body_font_size):
        return False
    if not _table_band_is_body_paragraph(band, body_font_size):
        return False
    if _horizontal_overlap_ratio(band.rect, rect) < TABLE_NOTE_CONTINUATION_MIN_H_OVERLAP:
        return False
    if band.rect.x0 > rect.x0 + TABLE_NOTE_CONTINUATION_MAX_X_OFFSET:
        return False
    if band.word_count < TABLE_NOTE_CONTINUATION_MIN_WORDS:
        return False
    return True


def _table_block_is_title_like(
    block: _PageTextBlock,
    body_font_size: float,
) -> bool:
    if _table_block_is_note_like(block):
        return False
    normalized = _table_normalize_text(block.text)
    lowered = normalized.lower()
    if lowered.startswith(("table ", "exhibit ")):
        return True
    if ":" in normalized and len(normalized.split()) <= 14:
        return True
    return _table_block_is_heading_like(block, body_font_size)


def _table_block_looks_dense_tabular(block: _PageTextBlock) -> bool:
    if block.lines < TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_LINES:
        return False
    if block.avg_line_len > TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_AVG_LINE_LEN:
        return False
    normalized = _table_normalize_text(block.text)
    if not normalized:
        return False
    if len(normalized.split()) < block.lines:
        return False
    return True


def _table_attach_title_blocks(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = max(24.0, page_rect.height * 0.055)
    current_top = expanded.y0
    candidates = sorted(blocks, key=lambda block: block.rect.y1, reverse=True)
    for block in candidates:
        if block.rect.y1 > current_top:
            continue
        gap = current_top - block.rect.y1
        if gap > max_gap_y:
            continue
        if _table_block_is_margin_noise(block, page_rect):
            continue
        if _horizontal_overlap_ratio(block.rect, rect) < 0.35 and abs(block.rect.x0 - rect.x0) > 36:
            continue
        if not _table_block_is_title_like(block, body_font_size):
            continue
        expanded |= block.rect
        current_top = block.rect.y0
    return expanded


def _table_attach_note_blocks(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = max(30.0, page_rect.height * 0.032)
    current_bottom = expanded.y1
    note_started = False
    candidates = sorted(blocks, key=lambda block: block.rect.y0)
    for block in candidates:
        if block.rect.y0 < current_bottom - 1:
            continue
        gap = block.rect.y0 - current_bottom
        if gap > max_gap_y:
            if note_started:
                break
            continue
        if _table_block_is_margin_noise(block, page_rect):
            continue
        h_overlap = _horizontal_overlap_ratio(block.rect, rect)
        if h_overlap < 0.2 and not _table_block_is_note_like(block):
            continue
        if _table_block_is_note_like(block):
            expanded |= block.rect
            current_bottom = block.rect.y1
            note_started = True
            continue
        if _table_block_is_heading_like(block, body_font_size) or _table_block_is_body_paragraph(
            block, body_font_size
        ):
            break
    return expanded


def _table_attach_explicit_title_context(
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    expanded = fitz.Rect(rect)
    title_candidates = sorted(
        (
            block
            for block in blocks
            if block.rect.y1 <= rect.y0 + 1.0
            and rect.y0 - block.rect.y1 <= TABLE_EXPLICIT_TITLE_MAX_GAP
            and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
            and _table_normalize_text(block.text).lower().startswith(("table ", "exhibit "))
        ),
        key=lambda block: block.rect.y1,
        reverse=True,
    )
    if not title_candidates:
        return rect
    title_block = title_candidates[0]
    expanded |= title_block.rect
    current_bottom = title_block.rect.y1
    subtitle_candidates = sorted(
        (
            block
            for block in blocks
            if block.rect.y0 >= title_block.rect.y1 - 1.0
            and block.rect.y1 <= rect.y0 + 1.0
            and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
            and _table_block_is_body_paragraph(block, body_font_size)
        ),
        key=lambda block: block.rect.y0,
    )
    for block in subtitle_candidates:
        if block.rect.y0 - current_bottom > TABLE_EXPLICIT_SUBTITLE_MAX_GAP:
            break
        expanded |= block.rect
        current_bottom = block.rect.y1
    return expanded


def _table_attach_mixed_footer_blocks(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = max(30.0, page_rect.height * 0.032)
    current_bottom = expanded.y1
    footer_started = False
    candidates = sorted(blocks, key=lambda block: block.rect.y0)
    for block in candidates:
        if block.rect.y0 < current_bottom - 1:
            continue
        gap = block.rect.y0 - current_bottom
        if gap > max_gap_y:
            if footer_started:
                break
            continue
        if _table_block_is_margin_noise(block, page_rect):
            continue
        if _horizontal_overlap_ratio(block.rect, rect) < 0.2:
            continue
        if _table_block_is_mixed_footer_cluster(block):
            expanded |= block.rect
            current_bottom = block.rect.y1
            footer_started = True
            continue
        if footer_started:
            break
        if _table_block_is_heading_like(block, body_font_size) or _table_block_is_body_paragraph(
            block, body_font_size
        ):
            break
    return expanded


def _table_expand_horizontal_to_content(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_x = max(18.0, page_rect.width * TABLE_HORIZONTAL_EXPAND_MAX_GAP_FRAC)
    dense_tabular_max_gap_x = max(
        max_gap_x,
        page_rect.width * TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_GAP_FRAC,
    )
    for block in blocks:
        if _table_block_is_margin_noise(block, page_rect):
            continue
        v_overlap = _vertical_overlap_ratio(block.rect, rect)
        if v_overlap < TABLE_HORIZONTAL_EXPAND_MIN_V_OVERLAP:
            continue
        dense_tabular = (
            v_overlap >= TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_V_OVERLAP
            and _table_block_looks_dense_tabular(block)
            and block.rect.x1 >= expanded.x1 - 4.0
        )
        allowed_gap_x = dense_tabular_max_gap_x if dense_tabular else max_gap_x
        if block.rect.x1 < expanded.x0 - max_gap_x:
            continue
        if block.rect.x0 > expanded.x1 + allowed_gap_x:
            continue
        left_gain = expanded.x0 - block.rect.x0
        right_gain = block.rect.x1 - expanded.x1
        if (
            block.rect.x0 < expanded.x0
            and left_gain <= allowed_gap_x
            and left_gain >= TABLE_HORIZONTAL_EXPAND_MIN_GAIN
        ):
            expanded = fitz.Rect(block.rect.x0, expanded.y0, expanded.x1, expanded.y1)
        if (
            block.rect.x1 > expanded.x1
            and right_gain <= allowed_gap_x
            and right_gain >= TABLE_HORIZONTAL_EXPAND_MIN_GAIN
        ):
            expanded = fitz.Rect(expanded.x0, expanded.y0, block.rect.x1, expanded.y1)
    return expanded


def _table_extend_overlapping_note_blocks(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = TABLE_OVERLAPPING_NOTE_MAX_GAP
    note_started = False
    candidates = sorted(blocks, key=lambda block: block.rect.y0)
    for block in candidates:
        if _table_block_is_margin_noise(block, page_rect):
            continue
        if _horizontal_overlap_ratio(block.rect, rect) < 0.2:
            continue
        if block.rect.y0 > expanded.y1 + max_gap_y:
            if note_started:
                break
            continue
        if block.rect.y1 <= expanded.y1 + 1.0:
            continue
        if _table_block_is_note_like(block):
            missing_height = block.rect.y1 - expanded.y1
            if block.lines <= 1 and missing_height <= 18.0:
                continue
            expanded |= block.rect
            note_started = True
            continue
        if note_started and _table_block_is_note_continuation(
            block, rect, body_font_size
        ):
            expanded |= block.rect
            continue
        if note_started:
            break
    return expanded


def _table_restore_top_slack(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    candidates = [
        block
        for block in blocks
        if not _table_block_is_margin_noise(block, page_rect)
        and block.rect.y1 >= rect.y0 - 1.0
        and block.rect.y0 <= rect.y0 + rect.height * 0.25
        and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
    ]
    if not candidates:
        return rect
    first = min(candidates, key=lambda block: (block.rect.y0, block.rect.x0))
    normalized = _table_normalize_text(first.text).lower()
    if first.rect.y0 > rect.y0 + 2.0:
        return rect
    if normalized.startswith(("table ", "exhibit ")):
        return rect
    if _table_block_is_title_like(first, body_font_size):
        left_edge_guard = rect.x0 + rect.width * 0.18
        if first.rect.x0 <= left_edge_guard:
            return rect
    nearest_above = min(
        (
            rect.y0 - block.rect.y1
            for block in blocks
            if not _table_block_is_margin_noise(block, page_rect)
            and block.rect.y1 <= rect.y0 + 1.0
            and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
        ),
        default=None,
    )
    if nearest_above is not None and nearest_above <= 18.0:
        return rect
    slack_limit = TABLE_TOP_SLACK_MAX
    if _table_block_is_title_like(first, body_font_size):
        slack_limit = TABLE_TOP_HEADER_SLACK_MAX
    slack = min(slack_limit, rect.y0 - page_rect.y0)
    if slack <= 0.0:
        return rect
    return fitz.Rect(rect.x0, rect.y0 - slack, rect.x1, rect.y1)


def _table_clamp_top_to_internal_title_band(
    rect: fitz.Rect,
    bands: List[_TableTextBand],
    body_font_size: float,
) -> fitz.Rect:
    candidates = [
        band
        for band in bands
        if band.rect.y0 >= rect.y0 - 1.0
        and band.rect.y1 <= rect.y0 + rect.height * 0.45
        and _horizontal_overlap_ratio(band.rect, rect) >= 0.2
    ]
    if not candidates:
        return rect
    title_bands = [
        band
        for band in candidates
        if _table_band_is_title_like(band, body_font_size)
        and not _starts_with_lower_alpha(band.text)
    ]
    if not title_bands:
        return rect
    title_band = min(title_bands, key=lambda band: band.rect.y0)
    explicit_table_title_above = any(
        band is not title_band
        and band.rect.y1 <= title_band.rect.y0 + 1.0
        and _table_band_is_title_like(band, body_font_size)
        and _table_normalize_text(band.text).lower().startswith(("table ", "exhibit "))
        for band in candidates
    )
    if explicit_table_title_above:
        return rect
    paragraph_above = any(
        band.rect.y1 <= title_band.rect.y0 + 1.0
        and _table_band_is_body_paragraph(band, body_font_size)
        for band in candidates
    )
    if not paragraph_above:
        return rect
    if title_band.rect.y0 <= rect.y0 + 6.0:
        return rect
    return fitz.Rect(rect.x0, title_band.rect.y0, rect.x1, rect.y1)


def _table_clamp_top_to_internal_title(
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    explicit_title_in_top_band = any(
        block.rect.y1 >= rect.y0 - 1.0
        and block.rect.y0 <= rect.y0 + TABLE_EXPLICIT_TITLE_MAX_GAP
        and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
        and _table_normalize_text(block.text).lower().startswith(("table ", "exhibit "))
        for block in blocks
    )
    if explicit_title_in_top_band:
        return rect
    explicit_title_nearby = any(
        block.rect.y1 <= rect.y0 + 1.0
        and rect.y0 - block.rect.y1 <= TABLE_EXPLICIT_TITLE_MAX_GAP
        and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
        and _table_normalize_text(block.text).lower().startswith(("table ", "exhibit "))
        for block in blocks
    )
    if explicit_title_nearby:
        return rect
    candidates = [
        block
        for block in blocks
        if block.rect.y0 >= rect.y0 - 1.0
        and block.rect.y1 <= rect.y0 + rect.height * 0.45
        and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
    ]
    if not candidates:
        return rect
    title_blocks = [
        block
        for block in candidates
        if _table_block_is_title_like(block, body_font_size)
        and not _starts_with_lower_alpha(block.text)
    ]
    if not title_blocks:
        return rect
    title_block = min(title_blocks, key=lambda block: block.rect.y0)
    explicit_table_title_above = any(
        block is not title_block
        and block.rect.y1 <= title_block.rect.y0 + 1.0
        and _table_block_is_title_like(block, body_font_size)
        and _table_normalize_text(block.text).lower().startswith(("table ", "exhibit "))
        for block in candidates
    )
    if explicit_table_title_above:
        return rect
    paragraph_above = any(
        block.rect.y1 <= title_block.rect.y0 + 1.0
        and _table_block_is_body_paragraph(block, body_font_size)
        for block in candidates
    )
    if not paragraph_above:
        return rect
    if title_block.rect.y0 <= rect.y0 + 6.0:
        return rect
    return fitz.Rect(rect.x0, title_block.rect.y0, rect.x1, rect.y1)


def _table_clamp_bottom_before_internal_heading(
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    candidates = [
        block
        for block in blocks
        if block.rect.y0 >= rect.y0 + rect.height * 0.55
        and block.rect.y1 <= rect.y1 + 1.0
        and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
    ]
    if not candidates:
        return rect
    for block in sorted(candidates, key=lambda item: item.rect.y0):
        normalized = _table_normalize_text(block.text)
        if len(normalized.split()) > 4:
            continue
        if not _table_block_is_heading_like(block, body_font_size):
            continue
        trailing_blocks = [
            tail
            for tail in candidates
            if tail.rect.y0 >= block.rect.y1 - 1.0
        ]
        if not trailing_blocks:
            continue
        if not any(
            _table_block_is_body_paragraph(tail, body_font_size)
            or _table_block_is_note_like(tail)
            for tail in trailing_blocks
        ):
            continue
        return fitz.Rect(rect.x0, rect.y0, rect.x1, max(rect.y0, block.rect.y0 - 2.0))
    return rect


def _compose_table_bbox(
    page: fitz.Page,
    bbox: Tuple[float, float, float, float],
    method: str,
    *,
    page_text_blocks: Optional[List[_PageTextBlock]] = None,
    page_text_bands: Optional[List[_TableTextBand]] = None,
) -> Tuple[float, float, float, float]:
    rect = fitz.Rect(*bbox)
    page_rect = page.rect
    bands = page_text_bands if page_text_bands is not None else _table_text_bands(page)
    if method == "stream":
        rect = _shrink_stream_table_rect(page, rect, bands=bands)
    blocks = (
        page_text_blocks
        if page_text_blocks is not None
        else _table_page_text_blocks(page)
    )
    body_font_size = _table_page_body_font_size(blocks)
    if method == "stream" and bands:
        expanded = _table_attach_title_bands(page, rect, bands, body_font_size)
        expanded = _table_attach_explicit_title_context(
            expanded, blocks, body_font_size
        )
        expanded = _table_attach_note_bands(page, expanded, bands, body_font_size)
        expanded = _table_attach_mixed_footer_blocks(
            page, expanded, blocks, body_font_size
        )
    else:
        expanded = _table_attach_title_blocks(page, rect, blocks, body_font_size)
        expanded = _table_attach_explicit_title_context(
            expanded, blocks, body_font_size
        )
        expanded = _table_attach_note_blocks(page, expanded, blocks, body_font_size)
    expanded = _table_expand_horizontal_to_content(page, expanded, blocks)
    expanded = _table_attach_explicit_title_context(
        expanded, blocks, body_font_size
    )
    expanded = _table_extend_overlapping_note_blocks(
        page, expanded, blocks, body_font_size
    )
    if method == "stream":
        expanded = _table_clamp_top_to_internal_title_band(
            expanded, bands, body_font_size
        )
        expanded = _table_clamp_top_to_internal_title(
            expanded, blocks, body_font_size
        )
        expanded = _table_clamp_bottom_before_internal_heading(
            expanded, blocks, body_font_size
        )
        expanded = _table_restore_top_slack(
            page, expanded, blocks, body_font_size
        )

    if method == "stream":
        width_frac = expanded.width / max(1.0, page_rect.width)
        height_frac = expanded.height / max(1.0, page_rect.height)
        max_gap_x = page_rect.width * TABLE_EXPAND_MAX_GAP_FRAC
        if (
            width_frac >= TABLE_EXPAND_STREAM_WIDE_MIN_WIDTH_FRAC
            and height_frac >= TABLE_EXPAND_STREAM_WIDE_MIN_HEIGHT_FRAC
        ):
            if page_rect.x1 - expanded.x1 <= max_gap_x:
                expanded = fitz.Rect(
                    expanded.x0, expanded.y0, page_rect.x1, expanded.y1
                )
            if expanded.x0 - page_rect.x0 <= max_gap_x:
                expanded = fitz.Rect(
                    page_rect.x0, expanded.y0, expanded.x1, expanded.y1
                )

    expanded &= page_rect
    if expanded.is_empty:
        return bbox
    return (expanded.x0, expanded.y0, expanded.x1, expanded.y1)


def _rect_containment_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    inter_area = inter.get_area()
    if inter_area <= 0.0:
        return 0.0
    denom = min(a.get_area(), b.get_area())
    if denom <= 0.0:
        return 0.0
    return inter_area / denom


def _rect_seen(rect: fitz.Rect, seen: List[fitz.Rect]) -> bool:
    for existing in seen:
        if _rect_iou(rect, existing) >= CHART_DEDUP_IOU:
            return True
    return False


def _chart_candidate_score(
    area_frac: float,
    has_hint: bool,
    caption: str,
    note_included: bool,
) -> float:
    score = area_frac
    if has_hint:
        score += 0.2
    if caption:
        score += min(0.2, len(caption) / 200.0)
    if note_included:
        score += 0.1
    return score


def _find_overlapping_kept(
    rect: fitz.Rect,
    kept: List[Tuple[fitz.Rect, float, int]],
) -> Optional[int]:
    for idx, (existing, _score, _out_idx) in enumerate(kept):
        if _rect_iou(rect, existing) >= CHART_OVERLAP_IOU:
            return idx
        if _rect_containment_ratio(rect, existing) >= CHART_OVERLAP_CONTAINMENT:
            return idx
        if _rect_containment_ratio(existing, rect) >= CHART_OVERLAP_CONTAINMENT:
            return idx
    return None


def _panel_should_clamp_to_internal_caption(
    rect_item: _ChartRect,
    candidates: List[_ChartRect],
) -> bool:
    if rect_item.kind != "panel":
        return False
    cap_rect = rect_item.caption_rect
    if cap_rect is None:
        return False
    caption = str(rect_item.caption or "").strip()
    if not caption or _line_starts_with_caption_hint(caption, CHART_CAPTION_HINTS):
        return False
    rect = rect_item.rect
    if cap_rect.y0 <= rect.y0 + rect.height * 0.18:
        return False
    for other in candidates:
        if other is rect_item or other.kind != "panel":
            continue
        other_rect = other.rect
        if _horizontal_overlap_ratio(other_rect, rect) < 0.75:
            continue
        if other_rect.height >= rect.height * 0.82:
            continue
        if other_rect.y0 > rect.y0 + rect.height * 0.45:
            continue
        if other_rect.y1 < rect.y0 + rect.height * 0.12:
            continue
        return True
    return False


def _panel_candidate_shadowed_by_heading_candidate(
    rect_item: _ChartRect,
    candidates: List[_ChartRect],
) -> bool:
    if rect_item.kind != "panel":
        return False
    caption = str(rect_item.caption or "").strip()
    if not _panel_caption_looks_metric_stub(caption):
        return False
    rect = rect_item.rect
    for other in candidates:
        if other is rect_item or other.kind != "heading":
            continue
        other_caption = str(other.caption or "").strip()
        if not other_caption or _panel_caption_looks_metric_stub(other_caption):
            continue
        other_rect = other.rect
        if _rect_containment_ratio(rect, other_rect) < 0.92:
            continue
        if _horizontal_overlap_ratio(rect, other_rect) < 0.94:
            continue
        if other_rect.height < rect.height * 1.12:
            continue
        if other_rect.y0 > rect.y0 - max(28.0, rect.height * 0.18):
            continue
        other_cap_rect = other.caption_rect
        if (
            other_cap_rect is not None
            and other_cap_rect.y1 > rect.y0 + rect.height * 0.2
        ):
            continue
        return True
    return False


def _panel_candidate_shadowed_by_larger_panel(
    rect_item: _ChartRect,
    candidates: List[_ChartRect],
    panel_text: str,
) -> bool:
    if rect_item.kind != "panel":
        return False
    rect = rect_item.rect
    aspect = rect.width / max(1.0, rect.height)
    if aspect < 3.0:
        return False
    lines, chars = _text_stats(panel_text)
    if lines < 2 or lines > 6:
        return False
    if chars < 40 or chars > 220:
        return False
    percent_hits = len(re.findall(r"\b\d+(?:\.\d+)?%", panel_text))
    if percent_hits < 1 or percent_hits > 2:
        return False
    if _numeric_token_hits(panel_text) > 3:
        return False
    for other in candidates:
        if other is rect_item or other.kind != "panel":
            continue
        other_rect = other.rect
        if other_rect.y0 < rect.y1 - 4.0:
            continue
        if other_rect.y0 - rect.y1 > max(36.0, rect.height * 0.5):
            continue
        if _horizontal_overlap_ratio(rect, other_rect) < 0.88:
            continue
        if other_rect.width < rect.width * 0.9:
            continue
        if other_rect.height < rect.height * 1.8:
            continue
        other_caption = str(other.caption or "").strip()
        other_cap_rect = other.caption_rect
        if not other_caption or other_cap_rect is None:
            continue
        if _panel_caption_looks_metric_stub(other_caption):
            continue
        if not _panel_caption_looks_top_band(
            other_caption,
            rect=other_rect,
            cap_rect=other_cap_rect,
        ):
            continue
        return True
    return False


def _panel_stacked_bottom_clip_y(
    page: fitz.Page,
    rect_item: _ChartRect,
    candidates: List[_ChartRect],
) -> Optional[float]:
    if rect_item.kind != "panel":
        return None
    caption = str(rect_item.caption or "").strip()
    if not caption or _line_starts_with_caption_hint(caption, CHART_CAPTION_HINTS):
        return None
    rect = rect_item.rect
    compact_stat_caption = _panel_caption_looks_metric_stub(caption)
    candidate_y: Optional[float] = None
    for other in candidates:
        if other is rect_item or other.kind != "panel":
            continue
        other_caption = str(other.caption or "").strip()
        if other_caption and _line_starts_with_caption_hint(
            other_caption, CHART_CAPTION_HINTS
        ):
            continue
        if _panel_caption_looks_metric_stub(other_caption) or len(other_caption.split()) < 2:
            continue
        other_rect = other.rect
        boundary_y = (
            other.caption_rect.y0 if other.caption_rect is not None else other_rect.y0
        )
        if boundary_y <= rect.y0 + 8.0 or boundary_y >= rect.y1 - 8.0:
            continue
        if rect_item.caption_rect is not None and boundary_y <= rect_item.caption_rect.y0 + 4.0:
            continue
        if _horizontal_overlap_ratio(other_rect, rect) < 0.3:
            continue
        if other_rect.width < rect.width * 0.18:
            continue
        if not compact_stat_caption and rect.height < other_rect.height * 1.5:
            banner_over_main = (
                rect.height <= other_rect.height * 0.6
                and rect_item.caption_rect is not None
                and other.caption_rect is not None
                and rect_item.caption_rect.y0 + 20.0 < other.caption_rect.y0
                and boundary_y >= rect.y0 + rect.height * 0.55
            )
            if not banner_over_main:
                continue
        if candidate_y is None or boundary_y < candidate_y:
            candidate_y = boundary_y
    if candidate_y is None:
        return None
    if candidate_y >= rect.y0 + rect.height * 0.72:
        for line in _table_page_text_lines(page):
            text = _s(line.text).strip()
            if not text or _is_page_number_text(text):
                continue
            if line.rect.y0 < candidate_y - 3.0 or line.rect.y1 > rect.y1 + 2.0:
                continue
            if _horizontal_overlap_ratio(line.rect, rect) < 0.15:
                continue
            if line.rect.height > rect.height * 0.18:
                continue
            lines, chars = _text_stats(text)
            if lines == 0:
                continue
            avg_line_len = chars / max(1, lines)
            if chars > 56 and avg_line_len > 26.0:
                continue
            return None
        try:
            drawings = page.get_drawings()
        except PDF_FIGURE_EXCEPTIONS:
            drawings = []
        for drawing in drawings:
            if drawing.get("type") not in {"f", "fs"}:
                continue
            draw_rect = fitz.Rect(drawing.get("rect", (0, 0, 0, 0)))
            if draw_rect.is_empty:
                continue
            if draw_rect.y0 < candidate_y - 3.0 or draw_rect.y1 > rect.y1 + 2.0:
                continue
            if _horizontal_overlap_ratio(draw_rect, rect) < 0.08:
                continue
            if (
                draw_rect.width > rect.width * 0.25
                and draw_rect.height > rect.height * 0.18
            ):
                continue
            if draw_rect.get_area() < max(28.0, rect.get_area() * 0.002):
                continue
            return None
    return candidate_y


def _panel_neighbor_x_bounds(
    rect_item: _ChartRect,
    candidates: List[_ChartRect],
    page_rect: fitz.Rect,
) -> Tuple[Optional[float], Optional[float]]:
    if rect_item.kind != "panel":
        return None, None
    rect = rect_item.rect
    if (rect.width / max(1.0, page_rect.width)) >= 0.75:
        return None, None
    cap_rect = rect_item.caption_rect
    center_x = (rect.x0 + rect.x1) / 2.0
    min_x: Optional[float] = None
    max_x: Optional[float] = None
    for other in candidates:
        if other is rect_item or other.kind != "panel":
            continue
        other_rect = other.rect
        if _rect_containment_ratio(other_rect, rect) >= 0.65:
            continue
        if _rect_containment_ratio(rect, other_rect) >= 0.65:
            continue
        if _vertical_overlap_ratio(other_rect, rect) < 0.35:
            continue
        if _horizontal_overlap_ratio(other_rect, rect) >= 0.45:
            shared_left_edge = abs(other_rect.x0 - rect.x0) <= page_rect.width * 0.04
            shared_right_edge = abs(other_rect.x1 - rect.x1) <= page_rect.width * 0.04
            if (shared_left_edge or shared_right_edge) and (
                other_rect.width >= rect.width * 1.25
                or other_rect.width <= rect.width * 0.45
            ):
                continue
        other_center_x = (other_rect.x0 + other_rect.x1) / 2.0
        if other_center_x > center_x:
            right_anchor = other.caption_rect.x0 if other.caption_rect is not None else other_rect.x0
            if right_anchor <= rect.x0 + rect.width * 0.2:
                continue
            candidate_max = min(page_rect.x1, (rect.x1 + right_anchor) / 2.0)
            max_x = candidate_max if max_x is None else min(max_x, candidate_max)
        elif other_center_x < center_x:
            left_anchor = cap_rect.x0 if cap_rect is not None else rect.x0
            if other_rect.x1 >= rect.x1 - rect.width * 0.2:
                continue
            candidate_min = max(page_rect.x0, (other_rect.x1 + left_anchor) / 2.0)
            min_x = candidate_min if min_x is None else max(min_x, candidate_min)
    return min_x, max_x


def _image_block_rects(
    page: fitz.Page,
    text_dict: Optional[dict[str, object]] = None,
) -> List[fitz.Rect]:
    if text_dict is None:
        try:
            text_dict = page.get_text("dict")
        except PDF_FIGURE_EXCEPTIONS:
            return []
    blocks = text_dict.get("blocks") or []
    rects: List[fitz.Rect] = []
    for block in blocks:
        if block.get("type") != 1:
            continue
        bbox = block.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        try:
            rects.append(fitz.Rect(*bbox))
        except PDF_FIGURE_EXCEPTIONS:
            continue
    return rects


def _collect_chart_rects(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, object]] = None,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> List[_ChartRect]:
    rects: List[_ChartRect] = []
    for xref, *_ in page.get_images(full=True):
        try:
            image_rects = page.get_image_rects(xref)
        except PDF_FIGURE_EXCEPTIONS:
            image_rects = []
        if not image_rects:
            continue
        rects.append(_ChartRect(rect=image_rects[0], kind="xref", xref=xref))
    for rect in _image_block_rects(page, text_dict=text_dict):
        rects.append(_ChartRect(rect=rect, kind="block", xref=None))
    for rect, caption, cap_rect in _drawing_caption_rects(page, blocks=blocks):
        rects.append(
            _ChartRect(
                rect=rect,
                kind="draw",
                xref=None,
                caption=caption,
                caption_rect=cap_rect,
            )
        )
    for rect, caption, cap_rect in _panel_chart_rects(
        page,
        text_dict=text_dict,
        blocks=blocks,
    ):
        rects.append(
            _ChartRect(
                rect=rect,
                kind="panel",
                xref=None,
                caption=caption,
                caption_rect=cap_rect,
            )
        )
    for rect, caption, cap_rect in _heading_chart_rects(
        page,
        text_dict=text_dict,
        blocks=blocks,
    ):
        rects.append(
            _ChartRect(
                rect=rect,
                kind="heading",
                xref=None,
                caption=caption,
                caption_rect=cap_rect,
            )
        )
    return rects


def _drawing_rects(page: fitz.Page) -> List[fitz.Rect]:
    try:
        drawings = page.get_drawings()
    except PDF_FIGURE_EXCEPTIONS:
        return []
    page_area = max(1.0, page.rect.get_area())
    rects: List[fitz.Rect] = []
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None:
            continue
        try:
            r = fitz.Rect(rect)
        except PDF_FIGURE_EXCEPTIONS:
            continue
        if r.width < DRAWING_MIN_RECT_DIM and r.height < DRAWING_MIN_RECT_DIM:
            continue
        if r.get_area() < DRAWING_MIN_RECT_AREA:
            continue
        area_frac = r.get_area() / page_area
        if area_frac >= DRAWING_BACKGROUND_MIN_AREA_FRAC:
            fill = drawing.get("fill")
            width = drawing.get("width")
            if fill is not None and (
                width is None or float(width) <= DRAWING_BACKGROUND_MAX_STROKE
            ):
                continue
        rects.append(r)
    return rects


def _panel_title_lines(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, object]] = None,
) -> List[_PageTextLine]:
    titles: List[_PageTextLine] = []
    for line in _table_page_text_lines(page, text_dict=text_dict):
        text = _s(line.text).strip()
        if not text:
            continue
        if _is_page_number_text(text):
            continue
        if _PANEL_TITLE_EXCLUDE_RX.match(text):
            continue
        if line.max_font_size < PANEL_CHART_TITLE_MIN_SIZE:
            continue
        if _alpha_ratio(text) < INFO_HEADING_MIN_ALPHA_RATIO:
            continue
        words = text.split()
        if len(words) < PANEL_CHART_TITLE_MIN_WORDS:
            continue
        if len(words) > PANEL_CHART_TITLE_MAX_WORDS:
            continue
        if len(text) > PANEL_CHART_TITLE_MAX_CHARS:
            continue
        sentence_marks = text.count(".") + text.count("!") + text.count("?")
        if sentence_marks > PANEL_CHART_TITLE_MAX_SENTENCES:
            continue
        titles.append(line)
    titles = sorted(titles, key=lambda item: (item.rect.y0, item.rect.x0))
    if len(titles) < 2:
        return titles
    merged_titles: List[_PageTextLine] = []
    index = 0
    while index < len(titles):
        current = titles[index]
        merged_rect = fitz.Rect(current.rect)
        merged_text = [current.text.strip()]
        max_font_size = current.max_font_size
        index += 1
        while index < len(titles):
            nxt = titles[index]
            gap = nxt.rect.y0 - merged_rect.y1
            if gap > PANEL_CHART_TITLE_STACK_MAX_GAP:
                break
            horizontal_overlap = _horizontal_overlap_ratio(merged_rect, nxt.rect)
            edge_delta = min(
                abs(nxt.rect.x0 - merged_rect.x0),
                abs(nxt.rect.x1 - merged_rect.x1),
            )
            if (
                horizontal_overlap < PANEL_CHART_TITLE_STACK_MIN_H_OVERLAP
                and edge_delta > PANEL_CHART_TITLE_STACK_MAX_EDGE_DELTA
            ):
                break
            merged_rect |= nxt.rect
            merged_text.append(nxt.text.strip())
            max_font_size = max(max_font_size, nxt.max_font_size)
            index += 1
        merged_titles.append(
            _PageTextLine(
                rect=merged_rect,
                text=" ".join(part for part in merged_text if part),
                max_font_size=max_font_size,
            )
        )
    return merged_titles


def _panel_lowercase_title_has_metric_context(
    line: _PageTextLine,
    component_rect: fitz.Rect,
    *,
    lines: List[_PageTextLine],
) -> bool:
    if line.rect.y0 > component_rect.y0 + component_rect.height * 0.35:
        return False
    line_center_y = (line.rect.y0 + line.rect.y1) / 2.0
    for other in lines:
        if other is line:
            continue
        other_text = _s(other.text).strip()
        if not other_text:
            continue
        if _numeric_token_hits(other_text) < 1 and "%" not in other_text:
            continue
        if other.max_font_size < line.max_font_size * 1.35:
            continue
        if other.rect.x1 > line.rect.x0 + component_rect.width * 0.12:
            continue
        other_center_y = (other.rect.y0 + other.rect.y1) / 2.0
        if abs(other_center_y - line_center_y) > max(40.0, component_rect.height * 0.18):
            continue
        if _vertical_overlap_ratio(other.rect, line.rect) < 0.15:
            continue
        if _horizontal_overlap_ratio(other.rect, component_rect) < 0.08:
            continue
        return True
    return False


def _panel_local_title_line(
    page: fitz.Page,
    component_rect: fitz.Rect,
    *,
    text_dict: Optional[dict[str, object]] = None,
) -> Optional[_PageTextLine]:
    best: Optional[_PageTextLine] = None
    best_key: tuple[float, float, float] | None = None
    top_limit = component_rect.y0 + component_rect.height * PANEL_CHART_LOCAL_TITLE_TOP_FRAC
    component_center_x = (component_rect.x0 + component_rect.x1) / 2.0
    max_width_ratio = max(PANEL_CHART_LOCAL_TITLE_MAX_WIDTH_RATIO, 0.95)
    lines = _table_page_text_lines(page, text_dict=text_dict)
    for line in lines:
        text = _s(line.text).strip()
        if not text or _is_page_number_text(text):
            continue
        metric_context = _panel_lowercase_title_has_metric_context(
            line,
            component_rect,
            lines=lines,
        )
        if _starts_with_lower_alpha(text) and not re.match(r"^\s*\d", text):
            if not metric_context:
                continue
        if line.max_font_size < PANEL_CHART_LOCAL_TITLE_MIN_SIZE:
            continue
        if _alpha_ratio(text) < INFO_HEADING_MIN_ALPHA_RATIO:
            continue
        words = text.split()
        if len(words) < 2 or len(words) > PANEL_CHART_TITLE_MAX_WORDS:
            continue
        if len(text) > PANEL_CHART_TITLE_MAX_CHARS:
            continue
        if line.rect.height > component_rect.height * PANEL_CHART_LOCAL_TITLE_MAX_HEIGHT_RATIO:
            continue
        if line.rect.y1 < component_rect.y0 - 2.0:
            continue
        if line.rect.y0 > top_limit:
            continue
        width_ratio = line.rect.width / max(1.0, component_rect.width)
        if width_ratio < PANEL_CHART_LOCAL_TITLE_MIN_WIDTH_RATIO:
            continue
        if width_ratio > max_width_ratio:
            continue
        h_overlap = _horizontal_overlap_ratio(line.rect, component_rect)
        if h_overlap < 0.25:
            continue
        center_delta = abs(((line.rect.x0 + line.rect.x1) / 2.0) - component_center_x)
        digit_led = bool(re.match(r"^\s*\d", text))
        if (
            center_delta > component_rect.width * 0.2
            and not metric_context
            and not digit_led
            and width_ratio < 0.45
        ):
            continue
        key = (
            line.rect.y0,
            center_delta,
            -line.max_font_size,
        )
        if best_key is None or key < best_key:
            best = line
            best_key = key
    return best


def _panel_preferred_local_title_line(
    page: fitz.Page,
    component_rect: fitz.Rect,
    *,
    text_dict: Optional[dict[str, object]] = None,
    max_gap_above_px: float = 96.0,
) -> Optional[_PageTextLine]:
    internal_title = _panel_local_title_line(
        page,
        component_rect,
        text_dict=text_dict,
    )
    if internal_title is not None:
        return internal_title
    best: Optional[_PageTextLine] = None
    best_key: tuple[int, float, float, float] | None = None
    component_center_x = (component_rect.x0 + component_rect.x1) / 2.0
    candidate_lines: List[_PageTextLine] = []
    seen_keys: set[tuple[float, float, float, float, str]] = set()
    for line in _table_page_text_lines(page, text_dict=text_dict):
        key = (
            round(line.rect.x0, 1),
            round(line.rect.y0, 1),
            round(line.rect.x1, 1),
            round(line.rect.y1, 1),
            _s(line.text).strip(),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        candidate_lines.append(line)
    for line in _panel_title_lines(page, text_dict=text_dict):
        key = (
            round(line.rect.x0, 1),
            round(line.rect.y0, 1),
            round(line.rect.x1, 1),
            round(line.rect.y1, 1),
            _s(line.text).strip(),
        )
        if key in seen_keys:
            continue
        seen_keys.add(key)
        candidate_lines.append(line)
    for line in candidate_lines:
        text = _s(line.text).strip()
        if not text or _is_page_number_text(text):
            continue
        if line.max_font_size < PANEL_CHART_LOCAL_TITLE_MIN_SIZE:
            continue
        if _alpha_ratio(text) < INFO_HEADING_MIN_ALPHA_RATIO:
            continue
        words = text.split()
        if len(words) < 2 or len(words) > PANEL_CHART_TITLE_MAX_WORDS:
            continue
        if len(text) > PANEL_CHART_TITLE_MAX_CHARS:
            continue
        if line.rect.height > component_rect.height * PANEL_CHART_LOCAL_TITLE_MAX_HEIGHT_RATIO:
            continue
        if line.rect.y1 > component_rect.y0 + 2.0:
            continue
        gap_above = max(0.0, component_rect.y0 - line.rect.y1)
        if gap_above > max_gap_above_px:
            continue
        width_ratio = line.rect.width / max(1.0, component_rect.width)
        center_delta = abs(((line.rect.x0 + line.rect.x1) / 2.0) - component_center_x)
        close_above = (
            line.rect.y1 <= component_rect.y0 + 2.0
            and gap_above <= min(24.0, max_gap_above_px * 0.4)
        )
        centered_above = (
            line.rect.y1 <= component_rect.y0 + 2.0
            and center_delta <= component_rect.width * 0.24
            and width_ratio >= 0.18
            and width_ratio <= 1.6
        )
        if width_ratio < PANEL_CHART_LOCAL_TITLE_MIN_WIDTH_RATIO and not centered_above:
            continue
        if width_ratio > PANEL_CHART_LOCAL_TITLE_MAX_WIDTH_RATIO and not centered_above:
            continue
        h_overlap = _horizontal_overlap_ratio(line.rect, component_rect)
        if h_overlap < 0.25 and not centered_above:
            continue
        key = (
            0 if close_above else (1 if centered_above else 2),
            gap_above,
            center_delta,
            line.rect.y0,
        )
        if best_key is None or key < best_key:
            best = line
            best_key = key
    return best


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


def _panel_titles_form_multiline_band(
    titles: List[_PageTextLine],
    component_rect: fitz.Rect,
) -> bool:
    if len(titles) < 2:
        return False
    sorted_titles = sorted(titles, key=lambda item: (item.rect.y0, item.rect.x0))
    y_spread = max(title.rect.y0 for title in sorted_titles) - min(
        title.rect.y0 for title in sorted_titles
    )
    if y_spread < PANEL_CHART_TITLE_SLICE_Y_TOL * 1.5:
        return False
    band_rect = fitz.Rect(sorted_titles[0].rect)
    numeric_or_fragment_hits = 0
    for title in sorted_titles[1:]:
        band_rect |= title.rect
    for title in sorted_titles:
        text = _s(title.text).strip()
        if _numeric_token_hits(text) >= 1 or "%" in text or _starts_with_lower_alpha(text):
            numeric_or_fragment_hits += 1
    if numeric_or_fragment_hits < max(1, len(sorted_titles) - 1):
        return False
    return (
        (band_rect.width / max(1.0, component_rect.width)) >= 0.35
        and _horizontal_overlap_ratio(band_rect, component_rect) >= 0.45
    )


def _shared_row_panel_title_line(
    component_index: int,
    component_entries: List[
        Tuple[fitz.Rect, List[fitz.Rect], List[_PageTextLine], bool, str]
    ],
    titles: List[_PageTextLine],
    *,
    page_rect: fitz.Rect,
) -> Optional[_PageTextLine]:
    component_rect = fitz.Rect(component_entries[component_index][0])
    sibling_rects: List[fitz.Rect] = [component_rect]
    for index, (candidate_rect, _rects, _titles, supportive_only, _component_text) in enumerate(component_entries):
        if index == component_index or supportive_only:
            continue
        if _vertical_overlap_ratio(candidate_rect, component_rect) < 0.5:
            continue
        width_ratio = candidate_rect.width / max(1.0, component_rect.width)
        if width_ratio < 0.55 or width_ratio > 1.8:
            continue
        sibling_rects.append(fitz.Rect(candidate_rect))
    if len(sibling_rects) < 2:
        return None
    group_rect = fitz.Rect(sibling_rects[0])
    for sibling_rect in sibling_rects[1:]:
        group_rect |= sibling_rect
    best: Optional[_PageTextLine] = None
    best_key: tuple[float, float, float] | None = None
    for title in titles:
        if title.rect.y1 > group_rect.y0:
            continue
        gap = group_rect.y0 - title.rect.y1
        if gap > PANEL_CHART_TITLE_MAX_GAP:
            continue
        width_ratio = title.rect.width / max(1.0, group_rect.width)
        if width_ratio < 0.3:
            continue
        if _horizontal_overlap_ratio(title.rect, group_rect) < 0.18:
            continue
        center_delta = abs(
            ((title.rect.x0 + title.rect.x1) / 2.0)
            - ((group_rect.x0 + group_rect.x1) / 2.0)
        )
        key = (gap, center_delta, -title.rect.width)
        if best_key is None or key < best_key:
            best = title
            best_key = key
    return best


def _panel_title_slice_bounds(
    page: fitz.Page,
    title_rect: fitz.Rect,
    *,
    text_dict: Optional[dict[str, object]] = None,
) -> Optional[Tuple[float, float]]:
    lines = _table_page_text_lines(page, text_dict=text_dict)
    if not lines:
        return None
    target_line: Optional[_PageTextLine] = None
    target_overlap = 0.0
    for line in lines:
        overlap = _rect_overlap_area(line.rect, title_rect)
        if overlap <= 0.0:
            continue
        if overlap > target_overlap:
            target_overlap = overlap
            target_line = line
    if target_line is None:
        return None
    target_center_y = (target_line.rect.y0 + target_line.rect.y1) / 2.0
    peers: List[_PageTextLine] = []
    for line in lines:
        text = _s(line.text).strip()
        if not text or _is_page_number_text(text):
            continue
        center_y = (line.rect.y0 + line.rect.y1) / 2.0
        if abs(center_y - target_center_y) > PANEL_CHART_TITLE_SLICE_Y_TOL:
            continue
        if abs(line.max_font_size - target_line.max_font_size) > PANEL_CHART_TITLE_SLICE_SIZE_TOL:
            continue
        if _alpha_ratio(text) < INFO_HEADING_MIN_ALPHA_RATIO:
            continue
        words = text.split()
        if len(words) < 2 or len(words) > PANEL_CHART_TITLE_MAX_WORDS:
            continue
        if len(text) > max(PANEL_CHART_TITLE_MAX_CHARS, 160):
            continue
        peers.append(line)
    if len(peers) < 2:
        return None
    peers = sorted(peers, key=lambda item: ((item.rect.x0 + item.rect.x1) / 2.0, item.rect.x0))
    target_index = min(
        range(len(peers)),
        key=lambda idx: abs(_rect_iou(peers[idx].rect, target_line.rect) - 1.0),
    )
    boundaries = [page.rect.x0]
    for left, right in zip(peers, peers[1:]):
        left_center = (left.rect.x0 + left.rect.x1) / 2.0
        right_center = (right.rect.x0 + right.rect.x1) / 2.0
        boundaries.append((left_center + right_center) / 2.0)
    boundaries.append(page.rect.x1)
    pad = page.rect.width * PANEL_CHART_TITLE_SLICE_X_PAD_FRAC
    return (
        max(page.rect.x0, boundaries[target_index] - pad),
        min(page.rect.x1, boundaries[target_index + 1] + pad),
    )


def _panel_chart_is_label_dense_not_prose(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 8:
        return False
    chars = sum(len(line) for line in lines)
    avg_line_len = chars / max(1, len(lines))
    if avg_line_len > 22.0:
        return False
    long_lines = sum(1 for line in lines if len(line) >= 32)
    long_line_ratio = long_lines / max(1, len(lines))
    if long_line_ratio > 0.25:
        return False
    short_lines = sum(1 for line in lines if len(line) <= 14)
    short_line_ratio = short_lines / max(1, len(lines))
    return short_line_ratio >= 0.3


def _numeric_token_hits(text: str) -> int:
    return len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))


def _panel_chart_has_metric_signal(text: str) -> bool:
    if re.search(r"\b\d+(?:\.\d+)?%", text):
        return True
    if re.search(r"\b\d+\.\d+\b", text):
        return True
    return len(re.findall(r"\b\d{2,}\b", text)) >= 2


def _extend_panel_rect_with_nearby_label_blocks(
    rect: fitz.Rect,
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
    page_rect: fitz.Rect,
    min_x: Optional[float] = None,
    max_x: Optional[float] = None,
) -> fitz.Rect:
    if not blocks:
        return fitz.Rect(rect)
    expanded = fitz.Rect(rect)
    bottom_label_attached = False
    max_gap_x = page_rect.width * PANEL_CHART_LABEL_ATTACH_MAX_GAP_X_FRAC
    max_gap_y = page_rect.height * PANEL_CHART_LABEL_ATTACH_MAX_GAP_Y_FRAC
    max_area = page_rect.get_area() * PANEL_CHART_LABEL_ATTACH_MAX_AREA_FRAC
    horizontal_guard_pad = page_rect.width * PANEL_CHART_LABEL_ATTACH_MAX_GAP_X_FRAC
    title_spill_pad = page_rect.width * PANEL_CHART_TOP_TITLE_ATTACH_MAX_SPILL_X_FRAC
    changed = True
    while changed:
        changed = False
        for x0, y0, x1, y1, text, *_ in blocks:
            compact = " ".join(str(text or "").split())
            if not compact:
                continue
            if EMAIL_ADDRESS_RX.search(compact):
                continue
            block_rect = fitz.Rect(x0, y0, x1, y1)
            if _panel_label_block_looks_like_footer_banner(
                block_rect,
                str(text or ""),
                page_rect=page_rect,
            ):
                continue
            if min_x is not None and block_rect.x1 < (min_x - horizontal_guard_pad):
                continue
            if max_x is not None and block_rect.x0 > (max_x + horizontal_guard_pad):
                continue
            numeric_label_like = (
                _numeric_token_hits(compact) >= 1
                and len(compact) <= 16
            )
            if _is_page_number_text(compact):
                near_page_bottom = block_rect.y0 >= (
                    page_rect.y1 - page_rect.height * 0.08
                )
                block_center_x = (block_rect.x0 + block_rect.x1) / 2.0
                near_page_side = (
                    block_rect.x0 <= page_rect.x0 + page_rect.width * 0.12
                    or block_rect.x1 >= page_rect.x1 - page_rect.width * 0.12
                )
                near_page_center = abs(block_center_x - (page_rect.x0 + page_rect.width / 2.0)) <= (
                    page_rect.width * 0.08
                )
                if not numeric_label_like or (near_page_bottom and (near_page_side or near_page_center)):
                    continue
            if (
                _rect_overlap_area(block_rect, expanded)
                >= block_rect.get_area() * PANEL_CHART_LABEL_ATTACH_SKIP_OVERLAP_RATIO
            ):
                continue
            if block_rect.get_area() > max_area:
                continue
            lines, chars = _text_stats(compact)
            if lines == 0 or lines > PANEL_CHART_LABEL_ATTACH_MAX_LINES:
                continue
            avg_line_len = chars / max(1, lines)
            if chars > PANEL_CHART_LABEL_ATTACH_MAX_CHARS:
                continue
            if avg_line_len > PANEL_CHART_LABEL_ATTACH_MAX_AVG_LINE_LEN:
                continue
            numeric_label_like = numeric_label_like and lines <= 2 and avg_line_len <= 12.0
            if _alpha_ratio(compact) < 0.45 and not numeric_label_like:
                continue
            sentence_marks = compact.count(".") + compact.count("!") + compact.count("?")
            if sentence_marks > 1:
                continue

            attach = False
            v_overlap = _vertical_overlap_ratio(block_rect, expanded)
            h_overlap = _horizontal_overlap_ratio(block_rect, expanded)
            if block_rect.x0 >= expanded.x1:
                attach = (
                    (block_rect.x0 - expanded.x1) <= max_gap_x
                    and v_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP
                )
            elif block_rect.x1 <= expanded.x0:
                attach = (
                    (expanded.x0 - block_rect.x1) <= max_gap_x
                    and v_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP
                )
            elif block_rect.y1 <= expanded.y0:
                attach = (
                    (expanded.y0 - block_rect.y1) <= max_gap_y
                    and h_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_H_OVERLAP
                )
            elif block_rect.y0 >= expanded.y1:
                attach = (
                    (block_rect.y0 - expanded.y1) <= max_gap_y
                    and h_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_H_OVERLAP
                )
            if not attach:
                if (
                    block_rect.x1 > expanded.x1
                    and block_rect.x0 < expanded.x1
                    and (
                        (block_rect.x1 - expanded.x1) <= max_gap_x
                        or (
                            lines <= 4
                            and avg_line_len <= 35.0
                            and v_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP
                        )
                    )
                    and v_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP
                ):
                    attach = True
                elif (
                    block_rect.x0 < expanded.x0
                    and block_rect.x1 > expanded.x0
                    and (
                        (expanded.x0 - block_rect.x0) <= max_gap_x
                        or (
                            lines <= 4
                            and avg_line_len <= 35.0
                            and v_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP
                        )
                    )
                    and v_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP
                ):
                    attach = True
                elif (
                    block_rect.y0 < expanded.y0
                    and block_rect.y1 > expanded.y0
                    and (expanded.y0 - block_rect.y0) <= max_gap_y
                    and h_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_H_OVERLAP
                ):
                    attach = True
                elif (
                    block_rect.y0 < expanded.y1
                    and block_rect.y1 > expanded.y1
                    and (block_rect.y1 - expanded.y1) <= max_gap_y
                    and h_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_H_OVERLAP
                ):
                    attach = True
            if not attach:
                continue
            if (
                block_rect.y0 <= expanded.y0 + 2.0
                and block_rect.y1 <= expanded.y0 + max_gap_y
            ):
                if min_x is not None and block_rect.x0 < min_x - title_spill_pad:
                    continue
                if max_x is not None and block_rect.x1 > max_x + title_spill_pad:
                    continue
            if block_rect.y0 >= expanded.y1 - 0.5 or block_rect.y1 > expanded.y1 + 0.5:
                bottom_label_attached = True
            expanded |= block_rect
            changed = True
    if bottom_label_attached:
        extra_bottom_pad = max(10.0, min(28.0, rect.height * 0.12))
        expanded.y1 = min(page_rect.y1, expanded.y1 + extra_bottom_pad)
    if min_x is not None:
        expanded.x0 = max(expanded.x0, min_x)
    if max_x is not None:
        expanded.x1 = min(expanded.x1, max_x)
    return expanded


def _panel_label_block_looks_like_footer_banner(
    block_rect: fitz.Rect,
    text: str,
    *,
    page_rect: fitz.Rect,
) -> bool:
    normalized = _table_normalize_text(text)
    if not normalized:
        return False
    lines = [line.strip() for line in str(text).splitlines() if line.strip()]
    if not lines or len(lines) > 3:
        return False
    if block_rect.y0 < page_rect.y1 - page_rect.height * 0.12:
        return False
    if block_rect.height > page_rect.height * 0.09:
        return False
    if block_rect.width > page_rect.width * 0.45:
        return False
    if len(normalized) > 72:
        return False
    if (
        len(lines) == 1
        and PAGE_FOOTER_BANNER_LINE_RX.search(lines[0])
        and any(ch.isalpha() for ch in lines[0])
    ):
        return True
    page_number_lines = [
        line
        for line in lines
        if _is_page_number_text(line)
        or PAGE_FOOTER_BANNER_LINE_RX.search(str(line).strip())
    ]
    if not page_number_lines:
        return False
    alpha_lines = [line for line in lines if _alpha_ratio(line) >= 0.55 and not _is_page_number_text(line)]
    if not alpha_lines:
        return False
    if any(len(line) > 40 for line in alpha_lines):
        return False
    if sum(len(line.split()) for line in alpha_lines) > 8:
        return False
    return True


def _panel_chart_has_data_signal(text: str) -> bool:
    percent_hits = bool(re.search(r"\b\d+(?:\.\d+)?%", text))
    decimal_hits = bool(re.search(r"\b\d+\.\d+\b", text))
    numeric_hits = _numeric_token_hits(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if _panel_chart_is_label_dense_not_prose(text):
        if percent_hits or decimal_hits or numeric_hits >= PANEL_CHART_MIN_NUMERIC_HITS:
            return True
        medium_label_hits = sum(1 for line in lines if 10 <= len(line) <= 28)
        legend_stub_hits = sum(
            1
            for line in lines
            if len(line) <= 6 or bool(re.fullmatch(r"[A-Z0-9/&-]{2,8}", line))
        )
        if len(lines) >= 12 and medium_label_hits >= 8 and legend_stub_hits >= 1:
            return True
        return False
    if _panel_chart_has_structured_card_signal(text):
        return True
    if percent_hits:
        return True
    if decimal_hits:
        return True
    raw_numbers = re.findall(r"\b\d+(?:\.\d+)?", text)
    if raw_numbers and all(len(token) >= 4 for token in raw_numbers):
        return False
    if not lines:
        return False
    avg_line_len = sum(len(line) for line in lines) / max(1, len(lines))
    return numeric_hits >= 3 and len(lines) >= 4 and avg_line_len <= 32.0


def _panel_component_text_from_blocks(
    component_rect: fitz.Rect,
    blocks: List[Tuple[float, float, float, float, str]],
) -> str:
    component_page_rect = fitz.Rect(
        0.0,
        0.0,
        max(component_rect.x1, max((x1 for _, _, x1, _, _text, *rest in blocks), default=component_rect.x1)),
        max(component_rect.y1, max((y1 for _, _, _, y1, _text, *rest in blocks), default=component_rect.y1)),
    )
    parts: List[str] = []
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        block_rect = fitz.Rect(x0, y0, x1, y1)
        if _panel_label_block_looks_like_footer_banner(
            block_rect,
            str(text or ""),
            page_rect=component_page_rect,
        ):
            continue
        overlap_area = _rect_overlap_area(block_rect, component_rect)
        if overlap_area < block_rect.get_area() * 0.45:
            h_overlap = _horizontal_overlap_ratio(block_rect, component_rect)
            v_overlap = _vertical_overlap_ratio(block_rect, component_rect)
            above_gap = component_rect.y0 - block_rect.y1
            below_gap = block_rect.y0 - component_rect.y1
            left_gap = component_rect.x0 - block_rect.x1
            right_gap = block_rect.x0 - component_rect.x1
            attached = False
            if (
                above_gap >= -2.0
                and above_gap
                <= max(
                    PANEL_CHART_TITLE_MAX_GAP,
                    min(120.0, component_rect.height * 0.95),
                )
                and h_overlap >= 0.22
            ):
                attached = True
            elif (
                below_gap >= -2.0
                and below_gap <= max(24.0, component_rect.height * 0.18)
                and h_overlap >= 0.2
            ):
                attached = True
            elif (
                left_gap >= -2.0
                and left_gap <= max(20.0, component_rect.width * 0.12)
                and v_overlap >= 0.5
            ):
                attached = True
            elif (
                right_gap >= -2.0
                and right_gap <= max(20.0, component_rect.width * 0.12)
                and v_overlap >= 0.5
            ):
                attached = True
            if not attached:
                continue
        parts.append(str(text))
    return "\n".join(parts)


def _panel_component_has_chart_signal(
    text: str,
    *,
    drawing_count: int = 0,
    titled: bool = False,
) -> bool:
    return (
        _panel_chart_has_data_signal(text)
        or _panel_component_looks_like_guidance_card(text)
        or _panel_chart_has_compact_stat_card_signal(text)
        or _panel_component_looks_like_independent_data_panel(text)
        or (titled and drawing_count >= 5)
    )


def _panel_component_looks_like_independent_data_panel(text: str) -> bool:
    numeric_hits = _numeric_token_hits(text)
    has_numeric_measurement = bool(re.search(r"\b\d+(?:\.\d+)?%", text)) or bool(
        re.search(r"\b\d+\.\d+\b", text)
    )
    if _panel_chart_is_label_dense_not_prose(text):
        if has_numeric_measurement or numeric_hits >= PANEL_CHART_MIN_NUMERIC_HITS:
            return True
        return False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return False
    if numeric_hits < 3:
        return False
    avg_line_len = sum(len(line) for line in lines) / max(1, len(lines))
    if numeric_hits >= 6:
        return True
    return len(lines) >= 8 and avg_line_len <= 28.0


def _panel_component_looks_like_guidance_card(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 4 or len(lines) > 40:
        return False
    if EMAIL_ADDRESS_RX.search(text):
        return False
    title = lines[0]
    if not PANEL_GUIDANCE_TITLE_RX.search(title):
        return False
    chars = sum(len(line) for line in lines)
    if chars < 80 or chars > 1200:
        return False
    numbered_step_hits = sum(
        1
        for line in lines
        if re.match(r"^\s*(?:0?\d{1,2}[.)-]?)\s*$", line)
        or re.match(r"^\s*(?:0?\d{1,2}[.)-])\s+\S", line)
    )
    colon_heading_hits = sum(
        1
        for line in lines
        if ":" in line
        and len(line.split(":", 1)[0].strip()) <= 24
        and any(ch.isalpha() for ch in line.split(":", 1)[0])
    )
    short_heading_hits = sum(
        1
        for line in lines[1:]
        if 2 <= len(line.split()) <= 6
        and len(line) <= 34
        and any(ch.isalpha() for ch in line)
        and ":" not in line
    )
    return (
        numbered_step_hits >= 2
        or colon_heading_hits >= 2
        or (colon_heading_hits >= 1 and short_heading_hits >= 2)
    )


def _panel_chart_has_structured_card_signal(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 6 or len(lines) > 36:
        return False
    chars = sum(len(line) for line in lines)
    if chars < 140:
        return False
    avg_line_len = chars / max(1, len(lines))
    if avg_line_len > 42.0:
        return False
    first_line = lines[0]
    if len(first_line) > 120 or len(first_line.split()) > 16:
        return False
    if EMAIL_ADDRESS_RX.search(text):
        return False
    colon_hits = sum(1 for line in lines if ":" in line and len(line) <= 100)
    short_line_ratio = sum(1 for line in lines if len(line) <= 28) / max(1, len(lines))
    numbered_hits = len(re.findall(r"\b0?\d{1,2}\b", text))
    if colon_hits >= 2 and short_line_ratio >= 0.2:
        return True
    return numbered_hits >= 3 and short_line_ratio >= 0.3 and avg_line_len <= 38.0


def _panel_caption_looks_metric_stub(text: str) -> bool:
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if _line_starts_with_caption_hint(normalized, CHART_CAPTION_HINTS):
        return False
    words = normalized.split()
    if len(words) > 12 or len(normalized) > 96:
        return False
    numeric_hits = _numeric_token_hits(normalized)
    if numeric_hits == 0:
        return False
    return "%" in normalized or normalized[:4].strip().isdigit()


def _panel_chart_has_compact_stat_card_signal(text: str) -> bool:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) < 2 or len(lines) > 8:
        return False
    chars = sum(len(line) for line in lines)
    percent_hits = len(re.findall(r"\b\d+(?:\.\d+)?%", text))
    min_chars = 16 if percent_hits >= 1 else 36
    if chars < min_chars or chars > 220:
        return False
    avg_line_len = chars / max(1, len(lines))
    if avg_line_len > 60.0:
        return False
    if EMAIL_ADDRESS_RX.search(text):
        return False
    numeric_hits = _numeric_token_hits(text)
    if percent_hits == 0 and numeric_hits < 2:
        return False
    raw_numbers = re.findall(r"\b\d+(?:\.\d+)?", text)
    if percent_hits == 0 and raw_numbers and all(len(token) >= 4 for token in raw_numbers):
        return False
    if not any(any(ch.isalpha() for ch in line) for line in lines):
        return False
    if len(lines[0]) > 48:
        return False
    sentence_marks = text.count(".") + text.count("!") + text.count("?")
    return sentence_marks <= 2


def _page_looks_like_contents_layout(
    page: fitz.Page,
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> bool:
    try:
        source_blocks = blocks or page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return False
    top_limit = page.rect.height * 0.35
    top_lines: List[str] = []
    numeric_hits = 0
    short_heading_hits = 0
    for x0, y0, x1, y1, text, *_ in source_blocks:
        if not text or y1 > top_limit:
            continue
        compact = " ".join(str(text).split())
        if not compact:
            continue
        top_lines.append(compact.lower())
        numeric_hits += len(re.findall(r"\b0?\d{1,2}\b", compact))
        if len(compact) <= 40 and any(ch.isalpha() for ch in compact):
            short_heading_hits += 1
    if not top_lines:
        return False
    top_text = "\n".join(top_lines)
    if "table of contents" in top_text:
        return True
    if top_text.startswith("contents") or "\ncontents" in top_text:
        return numeric_hits >= 4 and short_heading_hits >= 3
    return False


def _chart_axis_label_band_like(
    text: str,
    *,
    lines: int,
    chars: int,
    avg_line_len: float,
) -> bool:
    if lines == 0 or chars == 0:
        return False
    if lines > CHART_AXIS_LABEL_BAND_MAX_LINES:
        return False
    if avg_line_len > CHART_AXIS_LABEL_BAND_MAX_AVG_LINE_LEN:
        return False
    normalized = _table_normalize_text(text)
    if not normalized or re.search(r"[.!?;:]{2,}", normalized):
        return False
    numeric_hits = _numeric_token_hits(normalized)
    year_hits = len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", normalized))
    alpha_ratio = _alpha_ratio(normalized)
    return (
        year_hits >= 3
        or numeric_hits >= CHART_AXIS_LABEL_BAND_MIN_TOKEN_HITS
        or (
            lines >= 8
            and alpha_ratio >= CHART_AXIS_LABEL_BAND_MIN_ALPHA_RATIO
            and not re.search(r"https?://|@", normalized)
        )
    )


def _rect_overlap_area(left: fitz.Rect, right: fitz.Rect) -> float:
    overlap = fitz.Rect(left)
    overlap &= right
    if overlap.x1 <= overlap.x0 or overlap.y1 <= overlap.y0:
        return 0.0
    return overlap.get_area()


def _compact_top_chart_title_like(
    text: str,
    *,
    block: fitz.Rect,
    rect: fitz.Rect,
    max_v_gap: float,
    lines: int,
    chars: int,
    avg_line_len: float,
) -> bool:
    normalized = _table_normalize_text(text)
    if block.height > max(36.0, rect.height * 0.24):
        return False
    if lines == 0 or lines > CHART_LABEL_COMPACT_TITLE_MAX_LINES:
        return False
    if chars > CHART_LABEL_COMPACT_TITLE_MAX_CHARS:
        return False
    if avg_line_len > CHART_LABEL_COMPACT_TITLE_MAX_AVG_LINE_LEN:
        return False
    if normalized.endswith("."):
        return False
    if not any(ch.isalpha() for ch in text):
        return False
    if block.y1 > rect.y0:
        return False
    allowed_gap = max(max_v_gap * 1.8, 36.0)
    return rect.y0 - block.y1 <= allowed_gap


def _drawing_components(page: fitz.Page) -> List[Tuple[fitz.Rect, List[fitz.Rect]]]:
    rects = list(_drawing_rects(page))
    if not rects:
        return []
    gap = max(8.0, page.rect.height * PANEL_CHART_CONNECT_GAP_FRAC)
    remaining = list(rects)
    components: List[Tuple[fitz.Rect, List[fitz.Rect]]] = []
    while remaining:
        current = [remaining.pop(0)]
        changed = True
        while changed:
            merged = fitz.Rect(current[0])
            for rect in current[1:]:
                merged |= rect
            grown = fitz.Rect(
                merged.x0 - gap,
                merged.y0 - gap,
                merged.x1 + gap,
                merged.y1 + gap,
            )
            next_remaining: List[fitz.Rect] = []
            changed = False
            for rect in remaining:
                expanded = fitz.Rect(
                    rect.x0 - gap,
                    rect.y0 - gap,
                    rect.x1 + gap,
                    rect.y1 + gap,
                )
                if grown.intersects(expanded):
                    current.append(rect)
                    changed = True
                else:
                    next_remaining.append(rect)
            remaining = next_remaining
        merged = fitz.Rect(current[0])
        for rect in current[1:]:
            merged |= rect
        components.append((merged, current))
    return sorted(components, key=lambda item: item[0].get_area(), reverse=True)


def _shared_title_component_group(
    component_index: int,
    title: _PageTextLine,
    component_entries: List[
        Tuple[fitz.Rect, List[fitz.Rect], List[_PageTextLine], bool, str]
    ],
    *,
    page_rect: fitz.Rect,
) -> List[int]:
    grouped = [component_index]
    grouped_set = {component_index}
    merged_group_rect = fitz.Rect(component_entries[component_index][0])
    max_side_gap = page_rect.width * PANEL_CHART_SHARED_COMPONENT_MAX_SIDE_GAP_FRAC
    max_stack_gap = page_rect.height * PANEL_CHART_SHARED_COMPONENT_MAX_STACK_GAP_FRAC
    changed = True
    while changed:
        changed = False
        for index, (candidate_rect, _, candidate_titles, _supportive_only, _component_text) in enumerate(
            component_entries
        ):
            if index in grouped_set:
                continue
            same_shared_title = (
                len(candidate_titles) == 1 and candidate_titles[0] is title
            )
            if same_shared_title:
                if (
                    _vertical_overlap_ratio(candidate_rect, merged_group_rect)
                    < PANEL_CHART_SHARED_COMPONENT_MIN_V_OVERLAP
                ):
                    continue
                if candidate_rect.x0 > merged_group_rect.x1:
                    side_gap = candidate_rect.x0 - merged_group_rect.x1
                elif merged_group_rect.x0 > candidate_rect.x1:
                    side_gap = merged_group_rect.x0 - candidate_rect.x1
                else:
                    side_gap = 0.0
                if side_gap > max_side_gap:
                    continue
            elif not candidate_titles:
                if candidate_rect.y0 < merged_group_rect.y0 - 1.0:
                    continue
                if (
                    _horizontal_overlap_ratio(candidate_rect, merged_group_rect)
                    < PANEL_CHART_SHARED_COMPONENT_MIN_H_ALIGN
                ):
                    continue
                width_ratio = candidate_rect.width / max(1.0, merged_group_rect.width)
                if width_ratio < PANEL_CHART_SHARED_COMPONENT_MIN_WIDTH_RATIO:
                    continue
                height_ratio = candidate_rect.height / max(1.0, merged_group_rect.height)
                if height_ratio < PANEL_CHART_SHARED_COMPONENT_MIN_HEIGHT_RATIO:
                    continue
                if candidate_rect.y0 >= merged_group_rect.y1:
                    stack_gap = candidate_rect.y0 - merged_group_rect.y1
                elif merged_group_rect.y0 >= candidate_rect.y1:
                    stack_gap = merged_group_rect.y0 - candidate_rect.y1
                else:
                    stack_gap = 0.0
                if stack_gap > max_stack_gap:
                    continue
            else:
                continue
            grouped.append(index)
            grouped_set.add(index)
            merged_group_rect |= candidate_rect
            changed = True
    return sorted(grouped)


def _stacked_panel_group_has_intervening_text(
    grouped_indices: Tuple[int, ...],
    component_entries: List[
        Tuple[fitz.Rect, List[fitz.Rect], List[_PageTextLine], bool, str]
    ],
    blocks: Optional[List[Tuple[float, float, float, float, str]]],
) -> bool:
    if not blocks or len(grouped_indices) < 2:
        return False
    group_rects = sorted(
        (fitz.Rect(component_entries[index][0]) for index in grouped_indices),
        key=lambda item: (item.y0, item.x0),
    )
    for upper, lower in zip(group_rects, group_rects[1:]):
        if lower.y0 <= upper.y1:
            continue
        gap_rect = fitz.Rect(
            min(upper.x0, lower.x0),
            max(upper.y1 - 2.0, 0.0),
            max(upper.x1, lower.x1),
            lower.y0 + 12.0,
        )
        for x0, y0, x1, y1, text in blocks:
            block_rect = fitz.Rect(x0, y0, x1, y1)
            if not block_rect.intersects(gap_rect):
                continue
            if _horizontal_overlap_ratio(block_rect, gap_rect) < 0.2:
                continue
            compact = " ".join(str(text or "").split())
            if not compact or _is_page_number_text(compact):
                continue
            _lines, chars = _text_stats(compact)
            if chars < 8:
                continue
            return True
    return False


def _panel_chart_rects(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, object]] = None,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> List[Tuple[fitz.Rect, str, fitz.Rect]]:
    if _page_looks_like_contents_layout(page, blocks=blocks):
        return []
    if _caption_blocks(page, CHART_CAPTION_HINTS, blocks=blocks):
        return []
    components = _drawing_components(page)
    if not components:
        return []
    titles = _panel_title_lines(page, text_dict=text_dict)
    page_area = max(1.0, page.rect.get_area())
    page_rect = page.rect
    component_entries: List[
        Tuple[fitz.Rect, List[fitz.Rect], List[_PageTextLine], bool, str]
    ] = []
    for merged, rects in components:
        area_frac = merged.get_area() / page_area
        if area_frac < (PANEL_CHART_MIN_AREA_FRAC * 0.8) or area_frac > PANEL_CHART_MAX_AREA_FRAC:
            continue
        supportive_only = area_frac < PANEL_CHART_MIN_AREA_FRAC
        component_text = _panel_component_text_from_blocks(merged, blocks or [])
        nearby: List[Tuple[float, _PageTextLine]] = []
        for title in titles:
            gap = merged.y0 - title.rect.y1
            if gap < -2.0 or gap > PANEL_CHART_TITLE_MAX_GAP:
                continue
            if title.rect.x1 < merged.x0 - PANEL_CHART_TITLE_X_PAD:
                continue
            if title.rect.x0 > merged.x1 + PANEL_CHART_TITLE_X_PAD:
                continue
            nearby.append((gap, title))
        filtered: List[_PageTextLine] = []
        if nearby:
            nearest_gap = min(gap for gap, _ in nearby)
            filtered = [
                title
                for gap, title in nearby
                if gap <= nearest_gap + PANEL_CHART_TITLE_NEAREST_TOL
            ]
            filtered.sort(
                key=lambda item: ((item.rect.x0 + item.rect.x1) / 2.0, item.rect.y0)
            )
        unique_titles: List[_PageTextLine] = []
        for title in filtered:
            if unique_titles and _rect_iou(unique_titles[-1].rect, title.rect) >= 0.8:
                continue
            unique_titles.append(title)
        preferred_title = _panel_preferred_local_title_line(page, merged, text_dict=text_dict)
        if preferred_title is not None:
            if not unique_titles:
                unique_titles = [preferred_title]
            elif len(unique_titles) > 1:
                component_center_x = (merged.x0 + merged.x1) / 2.0
                preferred_delta = abs(
                    ((preferred_title.rect.x0 + preferred_title.rect.x1) / 2.0)
                    - component_center_x
                )
                other_delta = min(
                    abs(((title.rect.x0 + title.rect.x1) / 2.0) - component_center_x)
                    for title in unique_titles
                    if not (
                        title.text == preferred_title.text
                        and _rect_iou(title.rect, preferred_title.rect) >= 0.98
                    )
                )
                if preferred_delta + merged.width * 0.18 < other_delta:
                    unique_titles = [preferred_title]
        component_entries.append((merged, rects, unique_titles, supportive_only, component_text))

    if component_entries:
        updated_entries: List[
            Tuple[fitz.Rect, List[fitz.Rect], List[_PageTextLine], bool, str]
        ] = []
        for component_index, (merged, rects, filtered, supportive_only, component_text) in enumerate(component_entries):
            if supportive_only:
                updated_entries.append((merged, rects, filtered, supportive_only, component_text))
                continue
            shared_title = _shared_row_panel_title_line(
                component_index,
                component_entries,
                titles,
                page_rect=page_rect,
            )
            if shared_title is None:
                updated_entries.append((merged, rects, filtered, supportive_only, component_text))
                continue
            if filtered and not (
                len(filtered) == 1 and filtered[0].rect.y0 >= merged.y0 - 2.0
            ):
                updated_entries.append((merged, rects, filtered, supportive_only, component_text))
                continue
            updated_entries.append((merged, rects, [shared_title], supportive_only, component_text))
        component_entries = updated_entries

    title_usage: Dict[int, int] = {}
    for _, _, filtered, _supportive_only, _component_text in component_entries:
        seen_titles: set[int] = set()
        for title in filtered:
            key = id(title)
            if key in seen_titles:
                continue
            title_usage[key] = title_usage.get(key, 0) + 1
            seen_titles.add(key)

    candidates: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    seen_shared_groups: set[Tuple[int, ...]] = set()
    for component_index, (merged, rects, filtered, supportive_only, component_text) in enumerate(
        component_entries
    ):
        if not filtered and not supportive_only:
            structured_card_signal = _panel_chart_has_structured_card_signal(component_text)
            compact_stat_card_signal = _panel_chart_has_compact_stat_card_signal(component_text)
            metric_signal = _panel_chart_has_metric_signal(component_text)
            if (
                structured_card_signal
                or compact_stat_card_signal
                or (
                    metric_signal
                    and (
                        _panel_chart_has_data_signal(component_text)
                        or _panel_component_looks_like_independent_data_panel(component_text)
                    )
                )
            ):
                panel_rect = _extend_panel_rect_with_nearby_label_blocks(
                    fitz.Rect(merged),
                    blocks=blocks,
                    page_rect=page_rect,
                )
                panel_rect = _extend_panel_rect_with_adjacent_drawings(
                    page,
                    panel_rect,
                )
                panel_rect = _clamp_panel_rect_to_dominant_fill_rect(
                    page,
                    panel_rect,
                    text=component_text,
                )
                preferred_title = _panel_preferred_local_title_line(
                    page,
                    panel_rect,
                    text_dict=text_dict,
                )
                if preferred_title is not None and preferred_title.rect.y1 <= panel_rect.y0 + 2.0:
                    panel_rect |= preferred_title.rect
                    candidates.append((fitz.Rect(panel_rect), preferred_title.text, preferred_title.rect))
                    continue
                lead_line = None
                top_band_limit = panel_rect.y0 + min(max(48.0, panel_rect.height * 0.35), 120.0)
                for line in _table_page_text_lines(page, text_dict=text_dict):
                    if line.rect.y0 < panel_rect.y0 - 2.0 or line.rect.y1 > top_band_limit:
                        continue
                    if _rect_overlap_area(line.rect, panel_rect) < line.rect.get_area() * 0.65:
                        continue
                    text = _s(line.text).strip()
                    if not text or _is_page_number_text(text):
                        continue
                    if EMAIL_ADDRESS_RX.search(text):
                        continue
                    if len(text) > 140:
                        continue
                    lead_line = line
                    break
                if lead_line is not None:
                    candidates.append((fitz.Rect(panel_rect), lead_line.text, lead_line.rect))
                else:
                    fallback_caption = ""
                    preferred_fallback = ""
                    for line in component_text.splitlines():
                        normalized = line.strip()
                        if not normalized:
                            continue
                        if not fallback_caption:
                            fallback_caption = normalized[:120]
                        if any(ch.isalpha() for ch in normalized) and _numeric_token_hits(normalized) < 2:
                            preferred_fallback = normalized[:120]
                            break
                    if preferred_fallback:
                        fallback_caption = preferred_fallback
                    candidates.append((fitz.Rect(panel_rect), fallback_caption, fitz.Rect(panel_rect)))
            continue
        if not filtered or supportive_only:
            continue
        if len(filtered) == 1:
            if not _panel_component_has_chart_signal(
                component_text,
                drawing_count=len(rects),
                titled=True,
            ):
                continue
            title = filtered[0]
            grouped_indices = tuple(
                _shared_title_component_group(
                    component_index,
                    title,
                    component_entries,
                    page_rect=page_rect,
                )
            )
            same_title_siblings = sum(
                1
                for group_index in grouped_indices
                if group_index != component_index and component_entries[group_index][2]
            )
            allow_shared_group = same_title_siblings > 0 or not _stacked_panel_group_has_intervening_text(
                grouped_indices,
                component_entries,
                blocks,
            )
            if len(grouped_indices) > 1 and allow_shared_group:
                if grouped_indices in seen_shared_groups:
                    continue
                seen_shared_groups.add(grouped_indices)
                candidate_rect = fitz.Rect(component_entries[grouped_indices[0]][0])
                for group_index in grouped_indices[1:]:
                    candidate_rect |= component_entries[group_index][0]
            elif title_usage.get(id(title), 0) > 1:
                if grouped_indices in seen_shared_groups:
                    continue
                seen_shared_groups.add(grouped_indices)
                candidate_rect = fitz.Rect(component_entries[grouped_indices[0]][0])
                for group_index in grouped_indices[1:]:
                    candidate_rect |= component_entries[group_index][0]
            else:
                candidate_rect = fitz.Rect(merged)
            title_is_internal = title.rect.y0 >= merged.y0 - 1.0
            candidate_rect |= title.rect
            slice_min_x = None
            slice_max_x = None
            slice_bounds = None
            if title.rect.y1 <= merged.y0 + 2.0:
                slice_bounds = _panel_title_slice_bounds(page, title.rect, text_dict=text_dict)
            if slice_bounds is not None:
                slice_min_x, slice_max_x = slice_bounds
                bound_pad = max(page_rect.width * 0.015, candidate_rect.width * 0.12)
                slice_min_x = max(page_rect.x0, min(slice_min_x, candidate_rect.x0))
                slice_min_x = max(slice_min_x, candidate_rect.x0 - bound_pad)
                slice_max_x = min(page_rect.x1, max(slice_max_x, candidate_rect.x1))
                slice_max_x = min(slice_max_x, candidate_rect.x1 + bound_pad)
            candidate_rect = _extend_panel_rect_with_nearby_label_blocks(
                candidate_rect,
                blocks=blocks,
                page_rect=page_rect,
                min_x=slice_min_x,
                max_x=slice_max_x,
            )
            candidate_rect = _extend_panel_rect_with_adjacent_drawings(
                page,
                candidate_rect,
                min_x=slice_min_x,
                max_x=slice_max_x,
            )
            candidate_rect = _clamp_panel_rect_to_dominant_fill_rect(
                page,
                candidate_rect,
                text=component_text,
            )
            if title_is_internal:
                candidate_rect.y0 = max(candidate_rect.y0, merged.y0)
            candidates.append((candidate_rect, title.text, title.rect))
            continue

        if _panel_titles_form_multiline_band(filtered, merged):
            if not _panel_component_has_chart_signal(
                component_text,
                drawing_count=len(rects),
                titled=True,
            ):
                continue
            title_band_rect = fitz.Rect(filtered[0].rect)
            for title in filtered[1:]:
                title_band_rect |= title.rect
            title = max(
                filtered,
                key=lambda item: (
                    item.rect.width,
                    item.max_font_size,
                    -item.rect.y0,
                ),
            )
            candidate_rect = fitz.Rect(merged)
            title_is_internal = title_band_rect.y0 >= merged.y0 - 1.0
            candidate_rect |= title_band_rect
            candidate_rect = _extend_panel_rect_with_nearby_label_blocks(
                candidate_rect,
                blocks=blocks,
                page_rect=page_rect,
            )
            candidate_rect = _extend_panel_rect_with_adjacent_drawings(
                page,
                candidate_rect,
            )
            candidate_rect = _clamp_panel_rect_to_dominant_fill_rect(
                page,
                candidate_rect,
                text=component_text,
            )
            if title_is_internal:
                candidate_rect.y0 = max(candidate_rect.y0, merged.y0)
            candidates.append((candidate_rect, title.text, title.rect))
            continue

        centers = [((title.rect.x0 + title.rect.x1) / 2.0) for title in filtered]
        min_center_gap = page.rect.width * PANEL_CHART_SPLIT_MIN_CENTER_GAP_FRAC
        if any((right - left) < min_center_gap for left, right in zip(centers, centers[1:])):
            title = min(
                filtered,
                key=lambda item: (
                    merged.y0 - item.rect.y1 if item.rect.y1 <= merged.y0 else 1e9,
                    item.rect.x0,
                ),
            )
            candidate_rect = fitz.Rect(merged)
            candidate_rect |= title.rect
            candidates.append((candidate_rect, title.text, title.rect))
            continue

        boundaries = [merged.x0]
        for left, right in zip(centers, centers[1:]):
            boundaries.append((left + right) / 2.0)
        boundaries.append(merged.x1)
        for idx, title in enumerate(filtered):
            slice_x0 = boundaries[idx]
            slice_x1 = boundaries[idx + 1]
            panel_rects = [
                rect
                for rect in rects
                if ((rect.x0 + rect.x1) / 2.0) >= slice_x0 - 6.0
                and ((rect.x0 + rect.x1) / 2.0) <= slice_x1 + 6.0
            ]
            if not panel_rects:
                continue
            panel_rect = fitz.Rect(panel_rects[0])
            for rect in panel_rects[1:]:
                panel_rect |= rect
            if (panel_rect.get_area() / page_area) < (PANEL_CHART_MIN_AREA_FRAC * 0.6):
                continue
            if panel_rect.x1 <= panel_rect.x0 or panel_rect.y1 <= panel_rect.y0:
                continue
            candidate_rect = fitz.Rect(panel_rect)
            candidate_rect |= title.rect
            slice_pad = page_rect.width * PANEL_CHART_SPLIT_SLICE_X_PAD_FRAC
            min_width = max(
                title.rect.width,
                (slice_x1 - slice_x0) * PANEL_CHART_SPLIT_MIN_WIDTH_RATIO,
            )
            clamped_x0 = max(page_rect.x0, slice_x0 - slice_pad)
            clamped_x1 = min(page_rect.x1, slice_x1 + slice_pad)
            candidate_width = clamped_x1 - clamped_x0
            if candidate_width < min_width:
                deficit = min_width - candidate_width
                clamped_x0 = max(page_rect.x0, clamped_x0 - deficit / 2.0)
                clamped_x1 = min(page_rect.x1, clamped_x1 + deficit / 2.0)
            candidate_rect.x0 = max(candidate_rect.x0, clamped_x0)
            candidate_rect.x1 = min(candidate_rect.x1, clamped_x1)
            candidate_rect.x0 = max(page_rect.x0, min(candidate_rect.x0, title.rect.x0))
            candidate_rect.x1 = min(page_rect.x1, max(candidate_rect.x1, title.rect.x1))
            title_is_internal = title.rect.y0 >= panel_rect.y0 - 1.0
            candidate_rect = _extend_panel_rect_with_nearby_label_blocks(
                candidate_rect,
                blocks=blocks,
                page_rect=page_rect,
                min_x=clamped_x0,
                max_x=clamped_x1,
            )
            candidate_rect = _extend_panel_rect_with_adjacent_drawings(
                page,
                candidate_rect,
                min_x=clamped_x0,
                max_x=clamped_x1,
            )
            candidate_rect = _clamp_panel_rect_to_dominant_fill_rect(
                page,
                candidate_rect,
                text=component_text,
            )
            if title_is_internal:
                candidate_rect.y0 = max(candidate_rect.y0, panel_rect.y0)
            candidates.append((candidate_rect, title.text, title.rect))

    merged_candidates = _merge_panel_title_band_candidates(candidates, page_rect=page_rect)
    deduped: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for rect, text, title_rect in merged_candidates:
        if not _rect_seen(rect, [existing for existing, _, _ in deduped]):
            deduped.append((rect, text, title_rect))
    return deduped


def _line_starts_with_caption_hint(text: str, hints: Tuple[str, ...]) -> bool:
    normalized = _s(text).strip().lower()
    if not normalized:
        return False
    for hint in hints:
        if hint in {"chart", "graph"}:
            if re.match(rf"^{re.escape(hint)}\s*(?:\d|[ivxlcdm]+\b|[a-z]\b|[:.\-])", normalized):
                return True
            continue
        if normalized.startswith(hint):
            return True
    return False


def _merge_panel_title_band_candidates(
    candidates: List[Tuple[fitz.Rect, str, fitz.Rect]],
    *,
    page_rect: fitz.Rect,
) -> List[Tuple[fitz.Rect, str, fitz.Rect]]:
    if len(candidates) < 2:
        return candidates
    consumed: set[int] = set()
    merged_by_index: Dict[int, Tuple[fitz.Rect, str, fitz.Rect]] = {}
    max_gap = page_rect.height * PANEL_CHART_TITLE_BAND_MERGE_MAX_GAP_FRAC
    order = sorted(
        range(len(candidates)),
        key=lambda idx: candidates[idx][0].get_area(),
        reverse=True,
    )
    for body_index in order:
        if body_index in consumed:
            continue
        body_rect, body_text, body_title_rect = candidates[body_index]
        if body_rect.get_area() <= 0.0:
            continue
        _body_lines, body_chars = _text_stats(body_text)
        body_caption_is_weak = (
            body_chars == 0
            or body_chars <= 12
            or (_numeric_token_hits(body_text) >= 1 and body_chars <= 24)
        )
        if not body_caption_is_weak:
            continue
        best_title_index: Optional[int] = None
        best_gap = float("inf")
        for title_index, (title_rect, title_text, title_cap_rect) in enumerate(candidates):
            if title_index == body_index or title_index in consumed:
                continue
            if title_rect.get_area() <= 0.0:
                continue
            if title_rect.y1 > body_rect.y0:
                continue
            if title_rect.get_area() >= body_rect.get_area() * PANEL_CHART_TITLE_BAND_MERGE_MAX_AREA_RATIO:
                continue
            gap = body_rect.y0 - title_rect.y1
            if gap > max_gap:
                continue
            lines, chars = _text_stats(title_text)
            if lines == 0:
                continue
            avg_line_len = chars / max(1, lines)
            if not _compact_top_chart_title_like(
                title_text,
                block=title_cap_rect,
                rect=body_rect,
                max_v_gap=max_gap,
                lines=lines,
                chars=chars,
                avg_line_len=avg_line_len,
            ):
                continue
            if _horizontal_overlap_ratio(title_rect, body_rect) < PANEL_CHART_TITLE_BAND_MERGE_MIN_H_OVERLAP:
                continue
            if gap < best_gap:
                best_gap = gap
                best_title_index = title_index
        if best_title_index is None:
            continue
        title_rect, title_text, title_cap_rect = candidates[best_title_index]
        merged_rect = fitz.Rect(body_rect)
        merged_rect |= title_rect
        merged_by_index[body_index] = (merged_rect, title_text, title_cap_rect)
        consumed.add(best_title_index)

    out: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for index, candidate in enumerate(candidates):
        if index in consumed:
            continue
        out.append(merged_by_index.get(index, candidate))
    return out


def _panel_caption_looks_top_band(
    text: str,
    *,
    rect: fitz.Rect,
    cap_rect: fitz.Rect,
) -> bool:
    normalized = _table_normalize_text(text)
    lines, chars = _text_stats(normalized)
    if lines == 0 or lines > PANEL_CHART_INTERNAL_CAPTION_MAX_LINES:
        return False
    if chars > PANEL_CHART_INTERNAL_CAPTION_MAX_CHARS:
        return False
    avg_line_len = chars / max(1, lines)
    if avg_line_len > PANEL_CHART_INTERNAL_CAPTION_MAX_AVG_LINE_LEN:
        return False
    if cap_rect.y0 < rect.y0 - 1.0:
        return False
    if (cap_rect.y0 - rect.y0) > max(
        PANEL_CHART_INTERNAL_CAPTION_TOP_GAP_MAX,
        rect.height * 0.12,
    ):
        return False
    if (cap_rect.width / max(1.0, rect.width)) < PANEL_CHART_INTERNAL_CAPTION_MIN_WIDTH_RATIO:
        return False
    if not any(ch.isalpha() for ch in normalized):
        return False
    return True


def _drawing_caption_rects(
    page: fitz.Page,
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> List[Tuple[fitz.Rect, str, fitz.Rect]]:
    captions = _caption_blocks(page, CHART_CAPTION_HINTS, blocks=blocks)
    if not captions:
        return []
    drawings = _drawing_rects(page)
    if not drawings:
        return []
    page_rect = page.rect
    bottom_limit = page_rect.y1 - page_rect.height * 0.1
    candidates: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    caption_top_tol = max(
        CHART_CAPTION_INTERNAL_TOP_TOL_PX,
        page_rect.height * CHART_CAPTION_INTERNAL_TOP_TOL_FRAC,
    )
    captions_sorted = sorted(captions, key=lambda item: (item[0].y0, item[0].x0))
    for index, (cap_rect, cap_text) in enumerate(captions_sorted):
        next_caption_y0: Optional[float] = None
        for other_rect, _other_text in captions_sorted[index + 1 :]:
            if other_rect.y0 > cap_rect.y0 + 1.0:
                next_caption_y0 = other_rect.y0
                break
        band_top = cap_rect.y1 - 2
        band_bot = min(bottom_limit, cap_rect.y1 + page_rect.height * 0.55)
        if next_caption_y0 is not None:
            band_bot = min(
                band_bot,
                next_caption_y0 - CHART_NEXT_BLOCKER_GUARD_PX,
            )
        if band_bot <= band_top:
            continue
        band = fitz.Rect(page_rect.x0, band_top, page_rect.x1, band_bot)
        strict_selected = []
        relaxed_selected = []
        for r in drawings:
            if not r.intersects(band):
                continue
            if r.y1 <= cap_rect.y1:
                continue
            if next_caption_y0 is not None and r.y0 >= next_caption_y0 - caption_top_tol:
                continue
            if _horizontal_overlap_ratio(r, cap_rect) < 0.25:
                continue
            if r.y0 >= cap_rect.y0 - 4.0:
                strict_selected.append(r)
            elif r.y0 >= cap_rect.y0 - caption_top_tol:
                relaxed_selected.append(r)
        selected = strict_selected or relaxed_selected
        if not selected:
            continue
        merged = selected[0]
        for r in selected[1:]:
            merged |= r
        if merged.width / max(1.0, page_rect.width) < 0.6:
            expanded = list(selected)
            for r in drawings:
                if not r.intersects(band):
                    continue
                if _vertical_overlap_ratio(r, merged) < 0.3:
                    continue
                expanded.append(r)
            merged = expanded[0]
            for r in expanded[1:]:
                merged |= r
        merged |= cap_rect
        merged = _pad_rect(merged, page_rect)
        merged = _clamp_top_to_caption(merged, cap_rect, page, page_rect)
        merged = _extend_with_note_blocks(page, merged)
        if merged.get_area() <= 0:
            continue
        candidates.append((merged, cap_text, cap_rect))
    deduped: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for rect, cap_text, cap_rect in candidates:
        if not _rect_seen(rect, [r for r, _, _ in deduped]):
            deduped.append((rect, cap_text, cap_rect))
    return deduped


def _caption_blocks(
    page: fitz.Page,
    hints: Tuple[str, ...],
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> List[Tuple[fitz.Rect, str]]:
    rects: List[Tuple[fitz.Rect, str]] = []
    if blocks is None:
        try:
            blocks = page.get_text("blocks")
        except PDF_FIGURE_EXCEPTIONS:
            return rects
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        lines = [
            line.strip().lower() for line in str(text).splitlines() if line.strip()
        ]
        match_line = next(
            (line for line in lines if _line_starts_with_caption_hint(line, hints)),
            "",
        )
        if match_line:
            rects.append((fitz.Rect(x0, y0, x1, y1), match_line))
    return rects


def _alpha_ratio(text: str) -> float:
    if not text:
        return 0.0
    alpha = sum(1 for ch in text if ch.isalpha())
    total = len(text)
    return alpha / total if total else 0.0


def _is_page_number_text(text: str) -> bool:
    if not text:
        return False
    cleaned = text.strip()
    if not _PAGE_NUMBER_RX.match(cleaned):
        return False
    return _alpha_ratio(cleaned) <= 0.3


def _heading_lines(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, object]] = None,
) -> List[Tuple[fitz.Rect, str]]:
    if text_dict is None:
        try:
            text_dict = page.get_text("dict")
        except PDF_FIGURE_EXCEPTIONS:
            return []
    sizes = []
    lines_data = []
    for block in text_dict.get("blocks", []):
        block_lines: List[Tuple[fitz.Rect, str, float]] = []
        block_chars = 0
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            if not spans:
                continue
            text = "".join(span.get("text", "") for span in spans).strip()
            if not text:
                continue
            size_vals = [
                float(span.get("size", 0.0)) for span in spans if span.get("text")
            ]
            size = sum(size_vals) / max(1, len(size_vals))
            bbox = line.get("bbox")
            if bbox and len(bbox) == 4:
                block_lines.append((fitz.Rect(*bbox), text, size))
            if _alpha_ratio(text) >= INFO_HEADING_MIN_ALPHA_RATIO:
                sizes.append(size)
            block_chars += len(text)
        if not block_lines:
            continue
        block_line_count = len(block_lines)
        avg_block_line_len = block_chars / max(1, block_line_count)
        if (
            block_line_count >= CHART_LABEL_PARAGRAPH_MIN_LINES
            and avg_block_line_len > CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN
        ):
            continue
        lines_data.extend(block_lines)
    if not sizes:
        return []
    try:
        median_size = statistics.median(sizes)
    except statistics.StatisticsError:
        median_size = 0.0
    min_size = max(INFO_HEADING_MIN_SIZE, median_size + INFO_HEADING_SIZE_DELTA)
    headings: List[Tuple[fitz.Rect, str, float]] = []
    for rect, text, size in lines_data:
        if size < min_size:
            continue
        if _alpha_ratio(text) < INFO_HEADING_MIN_ALPHA_RATIO:
            continue
        if len(text.split()) < INFO_HEADING_MIN_WORDS:
            continue
        if len(text) > INFO_HEADING_MAX_CHARS:
            continue
        if len(text.split()) > INFO_HEADING_MAX_WORDS:
            continue
        sentence_marks = text.count(".") + text.count("!") + text.count("?")
        if sentence_marks > INFO_HEADING_MAX_SENTENCES:
            continue
        lowered = text.lower()
        if any(hint in lowered for hint in TABLE_CAPTION_HINTS):
            continue
        headings.append((rect, text, size))
    if not headings:
        return []
    headings_sorted = sorted(headings, key=lambda item: (item[0].y0, item[0].x0))
    gap_thresh = max(page.rect.height * INFO_HEADING_MERGE_GAP_FRAC, 2.0)
    merged: List[Tuple[fitz.Rect, str, float]] = []
    for rect, text, size in headings_sorted:
        if merged:
            last_rect, last_text, last_size = merged[-1]
            if (
                abs(size - last_size) <= INFO_HEADING_MERGE_SIZE_DELTA
                and _horizontal_overlap_ratio(rect, last_rect)
                >= INFO_HEADING_MERGE_H_OVERLAP
                and rect.y0 - last_rect.y1 <= gap_thresh
            ):
                merged[-1] = (
                    last_rect | rect,
                    f"{last_text} {text}".strip(),
                    max(last_size, size),
                )
                continue
        merged.append((rect, text, size))
    return [(rect, text) for rect, text, _ in merged]


def _cluster_rects_by_y(rects: List[fitz.Rect], gap: float) -> List[List[fitz.Rect]]:
    if not rects:
        return []
    rects_sorted = sorted(rects, key=lambda r: r.y0)
    clusters: List[List[fitz.Rect]] = []
    current = [rects_sorted[0]]
    current_bottom = rects_sorted[0].y1
    for r in rects_sorted[1:]:
        if r.y0 - current_bottom <= gap:
            current.append(r)
            current_bottom = max(current_bottom, r.y1)
        else:
            clusters.append(current)
            current = [r]
            current_bottom = r.y1
    clusters.append(current)
    return clusters


def _has_intervening_paragraph(
    page: fitz.Page,
    head_rect: fitz.Rect,
    chart_rect: fitz.Rect,
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> bool:
    if chart_rect.y0 <= head_rect.y1:
        return False
    if blocks is None:
        try:
            blocks = page.get_text("blocks")
        except PDF_FIGURE_EXCEPTIONS:
            return False
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        normalized_text = _table_normalize_text(str(text))
        lowered_text = normalized_text.lower()
        block = fitz.Rect(x0, y0, x1, y1)
        if block.y0 < head_rect.y1 or block.y1 > chart_rect.y0:
            continue
        if (
            _horizontal_overlap_ratio(block, chart_rect)
            < CHART_HEADING_TOP_BLOCK_H_OVERLAP
        ):
            continue
        lines, chars = _text_stats(str(text))
        if lines == 0:
            continue
        avg_line_len = chars / max(1, lines)
        if (
            lines >= CHART_LABEL_PARAGRAPH_MIN_LINES
            and avg_line_len > CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN
        ):
            return True
    return False


def _heading_chart_rects(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, object]] = None,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> List[Tuple[fitz.Rect, str, fitz.Rect]]:
    headings = _heading_lines(page, text_dict=text_dict)
    if not headings:
        return []
    drawings = _drawing_rects(page)
    if not drawings:
        return []
    page_rect = page.rect
    max_gap = page_rect.height * INFO_CHART_MAX_GAP_FRAC
    band_height = page_rect.height * INFO_CHART_BAND_FRAC
    cluster_gap = page_rect.height * INFO_CHART_CLUSTER_GAP_FRAC
    candidates: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for head_rect, head_text in headings:
        band = fitz.Rect(
            page_rect.x0,
            head_rect.y1,
            page_rect.x1,
            min(page_rect.y1, head_rect.y1 + band_height),
        )
        selected = [
            r for r in drawings if r.intersects(band) and r.y0 >= head_rect.y1 - 2
        ]
        if len(selected) < INFO_CHART_MIN_DRAWINGS:
            continue
        clusters = _cluster_rects_by_y(selected, cluster_gap)
        if not clusters:
            continue
        primary = max(clusters, key=lambda cluster: sum(r.get_area() for r in cluster))
        if len(primary) < INFO_CHART_MIN_DRAWINGS:
            continue
        merged = primary[0]
        for r in primary[1:]:
            merged |= r
        if (
            merged.get_area() / max(1.0, page_rect.get_area())
            < INFO_CHART_MIN_AREA_FRAC
        ):
            continue
        gap = merged.y0 - head_rect.y1
        if gap > max_gap:
            continue
        if _has_intervening_paragraph(page, head_rect, merged, blocks=blocks):
            continue
        merged |= head_rect
        merged = _pad_rect(merged, page_rect)
        merged = _clamp_top_to_caption(merged, head_rect, page, page_rect)
        candidates.append((merged, head_text, head_rect))
    deduped: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for rect, text, head_rect in candidates:
        if not _rect_seen(rect, [r for r, _, _ in deduped]):
            deduped.append((rect, text, head_rect))
    return deduped


def _nearest_caption_block(
    page: fitz.Page,
    rect: fitz.Rect,
    hints: Tuple[str, ...],
    max_dist: float = 180.0,
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> Tuple[Optional[fitz.Rect], str]:
    candidates = _caption_blocks(page, hints, blocks=blocks)
    if not candidates:
        return None, ""
    best_penalty = 2
    best_dist = 1e9
    best_rect: Optional[fitz.Rect] = None
    best_text = ""
    for cap_rect, cap_text in candidates:
        if _horizontal_overlap_ratio(cap_rect, rect) < 0.3:
            continue
        if cap_rect.y1 <= rect.y0:
            dist = rect.y0 - cap_rect.y1
            penalty = 0
        elif cap_rect.y0 >= rect.y1:
            dist = cap_rect.y0 - rect.y1
            penalty = 1
        else:
            dist = 0.0
            penalty = 0
        if dist > max_dist:
            continue
        if (penalty, dist) < (best_penalty, best_dist):
            best_penalty = penalty
            best_dist = dist
            best_rect = cap_rect
            best_text = cap_text
    if best_rect is None:
        return None, ""
    return best_rect, best_text


def _horizontal_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    left = max(a.x0, b.x0)
    right = min(a.x1, b.x1)
    overlap = max(0.0, right - left)
    if overlap <= 0.0:
        return 0.0
    denom = min(a.width, b.width)
    if denom <= 0.0:
        return 0.0
    return overlap / denom


def _vertical_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    top = max(a.y0, b.y0)
    bot = min(a.y1, b.y1)
    overlap = max(0.0, bot - top)
    if overlap <= 0.0:
        return 0.0
    denom = min(a.height, b.height)
    if denom <= 0.0:
        return 0.0
    return overlap / denom


def _pad_rect(rect: fitz.Rect, page_rect: fitz.Rect) -> fitz.Rect:
    pad_x = max(page_rect.width * CHART_PAD_X_FRAC, 2.0)
    pad_y = max(page_rect.height * CHART_PAD_Y_FRAC, 2.0)
    x0 = max(page_rect.x0, rect.x0 - pad_x)
    y0 = max(page_rect.y0, rect.y0 - pad_y)
    x1 = min(page_rect.x1, rect.x1 + pad_x)
    y1 = min(page_rect.y1, rect.y1 + pad_y)
    return fitz.Rect(x0, y0, x1, y1)


def _clamp_top_to_caption(
    rect: fitz.Rect,
    cap_rect: fitz.Rect,
    page: fitz.Page,
    page_rect: fitz.Rect,
    *,
    extra_pad: float = 0.0,
) -> fitz.Rect:
    pad = max(
        CHART_CAPTION_TOP_PAD_PX + extra_pad,
        cap_rect.height * CHART_CAPTION_TOP_PAD_FRAC + extra_pad,
        0.0,
    )
    target_top = max(page_rect.y0, cap_rect.y0 - pad)
    block_limit = _caption_top_block_limit(page, cap_rect, page_rect)
    if block_limit is not None:
        target_top = max(
            target_top,
            min(cap_rect.y0 - 2.0, block_limit + CHART_CROP_PAD_COMPENSATION),
        )
    if rect.y0 != target_top:
        return fitz.Rect(rect.x0, target_top, rect.x1, rect.y1)
    return rect


def _clamp_top_to_heading(
    rect: fitz.Rect,
    head_rect: fitz.Rect,
    page: fitz.Page,
    page_rect: fitz.Rect,
) -> fitz.Rect:
    if _has_internal_top_text(page, rect, head_rect):
        return rect
    max_pad = max(page_rect.height * CHART_HEADING_TOP_MAX_PAD_FRAC, 0.0)
    min_top = max(page_rect.y0, head_rect.y0 - max_pad)
    block_limit = _heading_top_block_limit(page, head_rect, page_rect)
    if block_limit is not None:
        min_top = max(min_top, block_limit)
    if rect.y0 < min_top:
        return fitz.Rect(rect.x0, min_top, rect.x1, rect.y1)
    return rect


def _heading_top_block_limit(
    page: fitz.Page,
    head_rect: fitz.Rect,
    page_rect: fitz.Rect,
) -> Optional[float]:
    search = page_rect.height * CHART_HEADING_TOP_SEARCH_FRAC
    guard = max(page_rect.height * CHART_HEADING_TOP_GUARD_FRAC, 2.0)
    best_y1 = None
    try:
        blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return None
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if _is_page_number_text(text):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.y1 > head_rect.y0:
            continue
        if head_rect.y0 - block.y1 > search:
            continue
        if (
            _horizontal_overlap_ratio(block, head_rect)
            < CHART_HEADING_TOP_BLOCK_H_OVERLAP
        ):
            continue
        if best_y1 is None or block.y1 > best_y1:
            best_y1 = block.y1
    if best_y1 is None:
        return None
    return min(page_rect.y1, best_y1 + guard)


def _caption_top_block_limit(
    page: fitz.Page,
    cap_rect: fitz.Rect,
    page_rect: fitz.Rect,
) -> Optional[float]:
    search = page_rect.height * CHART_CAPTION_TOP_SEARCH_FRAC
    guard = max(page_rect.height * CHART_CAPTION_TOP_GUARD_FRAC, 2.0)
    best_y1 = None
    try:
        blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return None
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if _is_page_number_text(text):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.y1 > cap_rect.y0:
            continue
        if cap_rect.y0 - block.y1 > search:
            continue
        if (
            _horizontal_overlap_ratio(block, cap_rect)
            < CHART_CAPTION_TOP_BLOCK_H_OVERLAP
        ):
            continue
        if best_y1 is None or block.y1 > best_y1:
            best_y1 = block.y1
    if best_y1 is None:
        return None
    return min(page_rect.y1, best_y1 + guard)


def _extend_with_note_blocks(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    page_rect = page.rect
    limit = min(page_rect.y1, rect.y1 + CHART_NOTE_MAX_DIST)
    max_gap_x = page_rect.width * CHART_NOTE_MAX_GAP_X_FRAC
    expanded = rect
    try:
        blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if y1 < rect.y1 - 2 or y0 > limit:
            continue
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        if not lines:
            continue
        first = lines[0].lower()
        if not first.startswith(NOTE_LABEL_PREFIXES):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        h_overlap = _horizontal_overlap_ratio(block, rect)
        gap_ok = (block.x0 >= rect.x1 and block.x0 - rect.x1 <= max_gap_x) or (
            block.x1 <= rect.x0 and rect.x0 - block.x1 <= max_gap_x
        )
        if h_overlap < 0.3 and not gap_ok:
            continue
        expanded |= block
    return expanded


def _next_chart_blocker_top(
    page: fitz.Page,
    rect: fitz.Rect,
    cap_rect: Optional[fitz.Rect],
) -> Optional[float]:
    start_y = cap_rect.y1 if cap_rect is not None else rect.y0
    min_gap = max(
        page.rect.height * CHART_NEXT_BLOCKER_MIN_GAP_FRAC,
        CHART_NEXT_BLOCKER_MIN_GAP_PX,
    )
    best_y0: Optional[float] = None

    for other_rect, _other_text in _caption_blocks(page, CHART_CAPTION_HINTS):
        if cap_rect is not None and abs(other_rect.y0 - cap_rect.y0) < 1.0:
            continue
        if other_rect.y0 <= start_y + min_gap:
            continue
        if other_rect.y0 >= rect.y1 - 1.0:
            continue
        if _horizontal_overlap_ratio(other_rect, rect) < CHART_NEXT_BLOCKER_MIN_H_OVERLAP:
            continue
        if best_y0 is None or other_rect.y0 < best_y0:
            best_y0 = other_rect.y0

    for head_rect, head_text in _heading_lines(page):
        lowered = head_text.strip().lower()
        if any(lowered.startswith(hint) for hint in CHART_CAPTION_HINTS):
            continue
        if head_rect.y0 <= start_y + min_gap:
            continue
        if head_rect.y0 >= rect.y1 - 1.0:
            continue
        if _horizontal_overlap_ratio(head_rect, rect) < CHART_NEXT_BLOCKER_MIN_H_OVERLAP:
            continue
        if best_y0 is None or head_rect.y0 < best_y0:
            best_y0 = head_rect.y0

    return best_y0


def _clamp_bottom_to_next_chart_blocker(
    page: fitz.Page,
    rect: fitz.Rect,
    cap_rect: Optional[fitz.Rect],
) -> fitz.Rect:
    blocker_top = _next_chart_blocker_top(page, rect, cap_rect)
    if blocker_top is None:
        return rect
    new_bottom = min(rect.y1, blocker_top - CHART_NEXT_BLOCKER_GUARD_PX)
    if new_bottom <= rect.y0 + 1.0:
        return rect
    return fitz.Rect(rect.x0, rect.y0, rect.x1, new_bottom)


def _extend_with_adjacent_text_blocks(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    page_rect = page.rect
    max_gap = page_rect.width * CHART_LABEL_MAX_GAP_FRAC
    max_v_gap = page_rect.height * CHART_LABEL_MAX_V_GAP_FRAC
    expanded = rect
    try:
        blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        normalized_text = _table_normalize_text(str(text))
        lowered_text = normalized_text.lower()
        block = fitz.Rect(x0, y0, x1, y1)
        if block.height > rect.height * CHART_LABEL_MAX_HEIGHT_FRAC:
            continue
        lines, chars = _text_stats(str(text))
        if lines == 0:
            continue
        avg_line_len = chars / max(1, lines)
        compact_top_title = _compact_top_chart_title_like(
            str(text),
            block=block,
            rect=rect,
            max_v_gap=max_v_gap,
            lines=lines,
            chars=chars,
            avg_line_len=avg_line_len,
        )
        axis_label_band = _chart_axis_label_band_like(
            str(text),
            lines=lines,
            chars=chars,
            avg_line_len=avg_line_len,
        )
        if (
            lines >= CHART_LABEL_PARAGRAPH_MIN_LINES
            and avg_line_len > CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN
            and not compact_top_title
            and not axis_label_band
        ):
            continue
        if lines > CHART_LABEL_MAX_LINES and not compact_top_title and not axis_label_band:
            continue
        if (
            avg_line_len > CHART_LABEL_MAX_AVG_LINE_LEN
            and not compact_top_title
            and not axis_label_band
        ):
            continue
        v_overlap = _vertical_overlap_ratio(block, rect)
        h_overlap = _horizontal_overlap_ratio(block, rect)
        if v_overlap >= CHART_LABEL_MIN_V_OVERLAP:
            if block.x0 >= rect.x1 and block.x0 - rect.x1 <= max_gap:
                expanded |= block
            elif block.x1 <= rect.x0 and rect.x0 - block.x1 <= max_gap:
                expanded |= block
            elif block.x1 > rect.x1 and block.x1 - rect.x1 <= max_gap:
                expanded |= block
            elif block.x0 < rect.x0 and rect.x0 - block.x0 <= max_gap:
                expanded |= block
            elif axis_label_band and block.y0 >= rect.y0 + rect.height * 0.35:
                expanded |= block
            elif (
                block.y0 >= rect.y0 + rect.height * 0.45
                and block.y1 <= rect.y1 + max_v_gap
                and lines <= 3
                and avg_line_len <= 72.0
                and (
                    _numeric_token_hits(normalized_text) >= 4
                    or len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", normalized_text)) >= 3
                )
            ):
                expanded |= block
        if h_overlap >= CHART_LABEL_MIN_H_OVERLAP:
            if block.y1 <= rect.y0 and (
                rect.y0 - block.y1 <= max_v_gap or compact_top_title
            ):
                expanded |= block
            elif block.y0 >= rect.y1 and block.y0 - rect.y1 <= max_v_gap:
                expanded |= block
            elif block.y0 < rect.y0 and rect.y0 - block.y0 <= max_v_gap:
                expanded |= block
            elif block.y1 > rect.y1 and block.y1 - rect.y1 <= max_v_gap:
                expanded |= block
    return expanded


def _extend_chart_rect_with_adjacent_drawings(
    page: fitz.Page,
    rect: fitz.Rect,
) -> fitz.Rect:
    page_rect = page.rect
    max_gap_x = max(18.0, page_rect.width * 0.08)
    max_gap_y = max(12.0, page_rect.height * 0.03)
    expanded = fitz.Rect(rect)
    lower_band_top = rect.y0 + rect.height * 0.2
    baseline_top = rect.y0 + rect.height * 0.45
    try:
        drawings = page.get_drawings()
    except PDF_FIGURE_EXCEPTIONS:
        return rect
    changed = True
    while changed:
        changed = False
        for drawing in drawings:
            draw_rect = fitz.Rect(drawing.get("rect", (0, 0, 0, 0)))
            if draw_rect.is_empty:
                continue
            if draw_rect.y1 < lower_band_top:
                continue
            if draw_rect.y0 > expanded.y1 + max_gap_y:
                continue
            if draw_rect.x0 > expanded.x1 + max_gap_x:
                continue
            if draw_rect.x1 < expanded.x0 - max_gap_x:
                continue
            attach = False
            if (
                draw_rect.x0 >= expanded.x1 - 1.0
                and (draw_rect.x0 - expanded.x1) <= max_gap_x
                and (
                    _vertical_overlap_ratio(draw_rect, expanded) >= 0.08
                    or draw_rect.y0 >= baseline_top
                )
            ):
                attach = True
            elif (
                draw_rect.x1 > expanded.x1
                and draw_rect.x0 <= expanded.x1 + max_gap_x
                and draw_rect.y0 >= baseline_top - 8.0
            ):
                attach = True
            elif (
                draw_rect.width >= expanded.width * 0.55
                and draw_rect.y0 >= baseline_top - 8.0
                and draw_rect.y1 <= expanded.y1 + max_gap_y
            ):
                attach = True
            if not attach:
                continue
            new_rect = expanded | draw_rect
            if _rect_iou(new_rect, expanded) >= 0.999:
                continue
            expanded = new_rect
            changed = True
    return expanded


def _extend_panel_rect_with_adjacent_drawings(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    min_x: Optional[float] = None,
    max_x: Optional[float] = None,
) -> fitz.Rect:
    page_rect = page.rect
    max_gap_x = max(14.0, page_rect.width * 0.05)
    max_gap_y = max(10.0, page_rect.height * 0.025)
    bound_spill = max(10.0, page_rect.width * 0.02)
    expanded = fitz.Rect(rect)
    try:
        drawings = page.get_drawings()
    except PDF_FIGURE_EXCEPTIONS:
        return rect
    changed = True
    while changed:
        changed = False
        for drawing in drawings:
            if drawing.get("type") not in {"f", "fs"}:
                continue
            draw_rect = fitz.Rect(drawing.get("rect", (0, 0, 0, 0)))
            if draw_rect.is_empty:
                continue
            if min_x is not None and draw_rect.x0 < min_x - bound_spill:
                continue
            if max_x is not None and draw_rect.x1 > max_x + bound_spill:
                continue
            if draw_rect.get_area() >= expanded.get_area() * 0.55:
                continue
            if draw_rect.y0 > expanded.y1 + max_gap_y:
                continue
            if draw_rect.y1 < expanded.y0 - max_gap_y:
                continue
            if draw_rect.x0 > expanded.x1 + max_gap_x:
                continue
            if draw_rect.x1 < expanded.x0 - max_gap_x:
                continue
            attach = False
            if (
                draw_rect.x0 >= expanded.x1 - 1.0
                and (draw_rect.x0 - expanded.x1) <= max_gap_x
                and _vertical_overlap_ratio(draw_rect, expanded) >= 0.18
            ):
                attach = True
            elif (
                draw_rect.x1 <= expanded.x0 + 1.0
                and (expanded.x0 - draw_rect.x1) <= max_gap_x
                and _vertical_overlap_ratio(draw_rect, expanded) >= 0.18
            ):
                attach = True
            elif (
                draw_rect.x1 > expanded.x1
                and draw_rect.x0 <= expanded.x1 + max_gap_x
                and draw_rect.width <= expanded.width * 0.4
                and _vertical_overlap_ratio(draw_rect, expanded) >= 0.14
            ):
                attach = True
            elif (
                draw_rect.x0 < expanded.x0
                and draw_rect.x1 >= expanded.x0 - max_gap_x
                and draw_rect.width <= expanded.width * 0.4
                and _vertical_overlap_ratio(draw_rect, expanded) >= 0.14
            ):
                attach = True
            if not attach:
                continue
            new_rect = expanded | draw_rect
            if _rect_iou(new_rect, expanded) >= 0.999:
                continue
            expanded = new_rect
            changed = True
    if min_x is not None:
        expanded.x0 = max(expanded.x0, min_x)
    if max_x is not None:
        expanded.x1 = min(expanded.x1, max_x)
    return expanded


def _clamp_panel_rect_to_dominant_fill_rect(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    text: str,
) -> fitz.Rect:
    global_compact_signal = _panel_chart_has_compact_stat_card_signal(text)
    overshoot = max(20.0, min(rect.width, rect.height) * 0.14)
    best_rect: Optional[fitz.Rect] = None
    best_key: tuple[int, float, float] | None = None
    overlap_fill_count = 0
    try:
        drawings = page.get_drawings()
    except PDF_FIGURE_EXCEPTIONS:
        return rect
    rect_texts: dict[tuple[float, float, float, float], str] = {}
    for drawing in drawings:
        if drawing.get("type") not in {"f", "fs"}:
            continue
        draw_rect = fitz.Rect(drawing.get("rect", (0, 0, 0, 0)))
        if draw_rect.is_empty:
            continue
        if _horizontal_overlap_ratio(draw_rect, rect) < 0.75:
            continue
        if _vertical_overlap_ratio(draw_rect, rect) < 0.45:
            continue
        overlap_fill_count += 1
        area_ratio = draw_rect.get_area() / max(1.0, rect.get_area())
        if area_ratio < 0.35 or area_ratio > 1.15:
            continue
        if draw_rect.x0 < rect.x0 - overshoot or draw_rect.x1 > rect.x1 + overshoot:
            continue
        if draw_rect.y0 < rect.y0 - overshoot or draw_rect.y1 > rect.y1 + overshoot:
            continue
        rect_key = (
            round(draw_rect.x0, 1),
            round(draw_rect.y0, 1),
            round(draw_rect.x1, 1),
            round(draw_rect.y1, 1),
        )
        if rect_key not in rect_texts:
            try:
                rect_texts[rect_key] = page.get_text("text", clip=draw_rect) or ""
            except PDF_FIGURE_EXCEPTIONS:
                rect_texts[rect_key] = ""
        clipped_text = rect_texts[rect_key]
        local_signal = _panel_chart_has_compact_stat_card_signal(clipped_text)
        if not local_signal and not global_compact_signal:
            continue
        key = (
            0 if local_signal else 1,
            abs(area_ratio - 0.6),
            -draw_rect.get_area(),
        )
        if best_key is None or key < best_key:
            best_key = key
            best_rect = draw_rect
    if best_rect is None or overlap_fill_count < 2:
        return rect
    return fitz.Rect(
        max(page.rect.x0, best_rect.x0 - 2.0),
        max(page.rect.y0, best_rect.y0 - 2.0),
        min(page.rect.x1, best_rect.x1 + 2.0),
        min(page.rect.y1, best_rect.y1 + 2.0),
    )


def _extend_panel_with_adjacent_text_blocks(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    min_x: Optional[float] = None,
    max_x: Optional[float] = None,
) -> fitz.Rect:
    page_rect = page.rect
    max_gap = page_rect.width * CHART_LABEL_MAX_GAP_FRAC
    max_v_gap = page_rect.height * CHART_LABEL_MAX_V_GAP_FRAC
    expanded = rect
    bottom_label_attached = False
    try:
        components = _drawing_components(page)
    except PDF_FIGURE_EXCEPTIONS:
        components = []

    def _panel_compact_top_title_like(
        text: str,
        *,
        block_rect: fitz.Rect,
        line_count: int,
        char_count: int,
        avg_line_len: float,
    ) -> bool:
        return (
            line_count > 0
            and line_count <= CHART_LABEL_COMPACT_TITLE_MAX_LINES
            and char_count <= CHART_LABEL_COMPACT_TITLE_MAX_CHARS
            and avg_line_len <= CHART_LABEL_COMPACT_TITLE_MAX_AVG_LINE_LEN
            and any(ch.isalpha() for ch in text)
            and not _starts_with_lower_alpha(text)
            and block_rect.y1 <= expanded.y0
        )

    def _has_title_band_component_support(block_rect: fitz.Rect) -> bool:
        for component_rect, _component_parts in components:
            if component_rect.y1 < block_rect.y0 - 24.0:
                continue
            if component_rect.y0 > block_rect.y1 + 24.0:
                continue
            if (
                _horizontal_overlap_ratio(component_rect, expanded)
                < PANEL_CHART_TOP_TITLE_ATTACH_COMPONENT_MIN_H_OVERLAP
            ):
                continue
            return True
        return False

    def _allow_top_title_spill(block_rect: fitz.Rect) -> bool:
        if block_rect.y1 > expanded.y0:
            return False
        extra_spill_x = page_rect.width * PANEL_CHART_TOP_TITLE_ATTACH_MAX_SPILL_X_FRAC
        block_center_x = (block_rect.x0 + block_rect.x1) / 2.0
        rect_center_x = (expanded.x0 + expanded.x1) / 2.0
        center_delta = abs(block_center_x - rect_center_x)
        width_ratio = block_rect.width / max(1.0, expanded.width)
        gap = expanded.y0 - block_rect.y1
        left_inset = max(0.0, block_rect.x0 - expanded.x0)
        narrow_centered_title = (
            width_ratio >= PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MIN_WIDTH_RATIO
            and width_ratio <= PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MAX_WIDTH_RATIO
            and center_delta
            <= expanded.width
            * PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MAX_CENTER_DELTA_FRAC
        )
        if block_rect.height > expanded.height * PANEL_CHART_TOP_TITLE_ATTACH_MAX_HEIGHT_RATIO:
            return False
        if (
            left_inset > expanded.width * PANEL_CHART_TOP_TITLE_ATTACH_MAX_LEFT_INSET_FRAC
            and not narrow_centered_title
        ):
            return False
        if gap > max_v_gap and not _has_title_band_component_support(block_rect) and not narrow_centered_title:
            return False
        if min_x is not None and block_rect.x0 < min_x - extra_spill_x:
            return False
        if max_x is not None and block_rect.x1 > max_x + extra_spill_x:
            return False
        return (
            gap
            <= max(
                page_rect.height * PANEL_CHART_TOP_TITLE_ATTACH_MAX_GAP_FRAC,
                expanded.height * 1.1,
                36.0,
            )
            and center_delta
            <= page_rect.width * PANEL_CHART_TOP_TITLE_ATTACH_MAX_CENTER_DELTA_FRAC
            and (
                (
                    width_ratio >= PANEL_CHART_TOP_TITLE_ATTACH_MIN_WIDTH_RATIO
                    and width_ratio <= PANEL_CHART_TOP_TITLE_ATTACH_MAX_WIDTH_RATIO
                )
                or narrow_centered_title
            )
            and block_rect.x0 >= expanded.x0 - extra_spill_x
            and block_rect.x1 <= expanded.x1 + extra_spill_x
        )

    try:
        blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        normalized_text = _table_normalize_text(str(text))
        lowered_text = normalized_text.lower()
        block = fitz.Rect(x0, y0, x1, y1)
        active_rect = fitz.Rect(expanded)
        if min_x is not None and block.x1 < min_x - max_gap:
            continue
        if max_x is not None and block.x0 > max_x + max_gap:
            continue
        if block.height > active_rect.height * CHART_LABEL_MAX_HEIGHT_FRAC:
            continue
        lines, chars = _text_stats(str(text))
        if lines == 0:
            continue
        avg_line_len = chars / max(1, lines)
        compact_top_title = _compact_top_chart_title_like(
            str(text),
            block=block,
            rect=active_rect,
            max_v_gap=max_v_gap,
            lines=lines,
            chars=chars,
            avg_line_len=avg_line_len,
        )
        panel_compact_top_title = _panel_compact_top_title_like(
            str(text),
            block_rect=block,
            line_count=lines,
            char_count=chars,
            avg_line_len=avg_line_len,
        )
        axis_label_band = _chart_axis_label_band_like(
            str(text),
            lines=lines,
            chars=chars,
            avg_line_len=avg_line_len,
        )
        compact_top_anchor_ok = (
            compact_top_title
            and block.x0
            <= active_rect.x0 + active_rect.width * PANEL_CHART_TOP_TITLE_ATTACH_MAX_LEFT_INSET_FRAC
        )
        v_overlap = _vertical_overlap_ratio(block, active_rect)
        h_overlap = _horizontal_overlap_ratio(block, active_rect)
        compact_side_spill = (
            lines <= 4
            and avg_line_len <= 35.0
            and v_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP
            and block.width <= active_rect.width * 0.55
            and (
                (block.x0 < active_rect.x0 and block.x1 > active_rect.x0)
                or (block.x1 > active_rect.x1 and block.x0 < active_rect.x1)
            )
        )
        spill_overlap_width = max(
            0.0,
            min(block.x1, active_rect.x1) - max(block.x0, active_rect.x0),
        )
        compact_side_spill = compact_side_spill and (
            spill_overlap_width <= active_rect.width * 0.10
        )
        if (
            lines >= CHART_LABEL_PARAGRAPH_MIN_LINES
            and avg_line_len > CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN
            and not compact_top_title
            and not panel_compact_top_title
            and not axis_label_band
        ):
            continue
        if (
            lines > CHART_LABEL_MAX_LINES
            and not compact_top_title
            and not panel_compact_top_title
            and not axis_label_band
        ):
            continue
        if (
            avg_line_len > CHART_LABEL_MAX_AVG_LINE_LEN
            and not compact_top_title
            and not panel_compact_top_title
            and not axis_label_band
        ):
            continue
        allow_top_title_spill = (compact_top_title or panel_compact_top_title) and _allow_top_title_spill(block)
        # Panel charts on slide decks often sit beside sibling panels; reject
        # candidate text blocks that spill too far beyond the panel's own width.
        if (
            not allow_top_title_spill
            and (block.x0 < active_rect.x0 - max_gap or block.x1 > active_rect.x1 + max_gap)
            and not compact_side_spill
        ):
            continue
        if compact_side_spill and v_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP:
            expanded |= block
        elif v_overlap >= CHART_LABEL_MIN_V_OVERLAP:
            if block.x0 >= active_rect.x1 and block.x0 - active_rect.x1 <= max_gap:
                expanded |= block
            elif block.x1 <= active_rect.x0 and active_rect.x0 - block.x1 <= max_gap:
                expanded |= block
            elif block.x1 > active_rect.x1 and block.x1 - active_rect.x1 <= max_gap:
                expanded |= block
            elif block.x0 < active_rect.x0 and active_rect.x0 - block.x0 <= max_gap:
                expanded |= block
            elif axis_label_band and block.y0 >= active_rect.y0 + active_rect.height * 0.35:
                expanded |= block
        if h_overlap >= CHART_LABEL_MIN_H_OVERLAP:
            if block.y1 <= active_rect.y0 and (
                compact_top_anchor_ok or allow_top_title_spill
            ):
                expanded |= block
            elif (
                axis_label_band
                and block.y0 >= active_rect.y1
                and block.y0 - active_rect.y1 <= max_v_gap
            ):
                expanded |= block
            elif (
                block.y0 >= active_rect.y1
                and block.y0 - active_rect.y1 <= max_v_gap
                and lowered_text.startswith(("source", "note", "notes", "statlink"))
            ):
                expanded |= block
            elif (
                block.y0 < active_rect.y0
                and active_rect.y0 - block.y0 <= max_v_gap
                and (compact_top_anchor_ok or allow_top_title_spill)
            ):
                expanded |= block
            elif (
                block.y1 > active_rect.y1
                and block.y1 - active_rect.y1 <= max_v_gap
                and lowered_text.startswith(("source", "note", "notes", "statlink"))
            ):
                expanded |= block
        if expanded.y1 > active_rect.y1 + 0.5 and not lowered_text.startswith(
            ("source", "note", "notes", "statlink")
        ):
            bottom_label_attached = True
    for line in _table_page_text_lines(page):
        text = _s(line.text).strip()
        if not text or _is_page_number_text(text):
            continue
        block = fitz.Rect(line.rect)
        if block.height > rect.height * CHART_LABEL_MAX_HEIGHT_FRAC:
            continue
        if (
            _rect_overlap_area(block, expanded)
            >= block.get_area() * PANEL_CHART_LABEL_ATTACH_SKIP_OVERLAP_RATIO
        ):
            continue
        lines, chars = _text_stats(text)
        if lines == 0:
            continue
        avg_line_len = chars / max(1, lines)
        compact_top_title = _compact_top_chart_title_like(
            text,
            block=block,
            rect=expanded,
            max_v_gap=max_v_gap,
            lines=lines,
            chars=chars,
            avg_line_len=avg_line_len,
        )
        panel_compact_top_title = _panel_compact_top_title_like(
            text,
            block_rect=block,
            line_count=lines,
            char_count=chars,
            avg_line_len=avg_line_len,
        )
        if not (compact_top_title or panel_compact_top_title) or not _allow_top_title_spill(block):
            continue
        expanded |= block
    side_gap = page_rect.width * PANEL_CONTEXT_CARD_MAX_SIDE_GAP_FRAC
    for component_rect, _component_parts in components:
        if component_rect.get_area() <= 0:
            continue
        if min_x is not None and component_rect.x1 < min_x - side_gap:
            continue
        if max_x is not None and component_rect.x0 > max_x + side_gap:
            continue
        overlap_ratio = _rect_overlap_area(component_rect, expanded) / max(
            1.0, component_rect.get_area()
        )
        if overlap_ratio >= PANEL_CONTEXT_CARD_MAX_COMPONENT_OVERLAP:
            continue
        if _vertical_overlap_ratio(component_rect, expanded) < PANEL_CONTEXT_CARD_MIN_V_OVERLAP:
            continue
        if component_rect.height < expanded.height * PANEL_CONTEXT_CARD_MIN_HEIGHT_RATIO:
            continue
        on_right = (
            component_rect.x1 > expanded.x1
            and component_rect.x0 <= expanded.x1 + side_gap
            and ((component_rect.x0 + component_rect.x1) / 2.0)
            >= ((expanded.x0 + expanded.x1) / 2.0)
        )
        on_left = (
            component_rect.x0 < expanded.x0
            and component_rect.x1 >= expanded.x0 - side_gap
            and ((component_rect.x0 + component_rect.x1) / 2.0)
            <= ((expanded.x0 + expanded.x1) / 2.0)
        )
        if not (on_left or on_right):
            continue
        component_text_parts: List[str] = []
        for x0, y0, x1, y1, text, *_ in blocks:
            if not text:
                continue
            block = fitz.Rect(x0, y0, x1, y1)
            if _rect_overlap_area(block, component_rect) < block.get_area() * 0.5:
                continue
            component_text_parts.append(str(text))
        component_text = "\n".join(component_text_parts)
        _lines, chars = _text_stats(component_text)
        if chars < PANEL_CONTEXT_CARD_MIN_TEXT_CHARS:
            continue
        if _panel_component_looks_like_independent_data_panel(component_text):
            continue
        expanded |= component_rect
    if bottom_label_attached:
        extra_bottom_pad = max(10.0, min(28.0, rect.height * 0.12))
        expanded.y1 = min(page_rect.y1, expanded.y1 + extra_bottom_pad)
    if min_x is not None:
        expanded.x0 = max(expanded.x0, min_x)
    if max_x is not None:
        expanded.x1 = min(expanded.x1, max_x)
    return expanded


def _has_internal_top_text(
    page: fitz.Page,
    rect: fitz.Rect,
    head_rect: fitz.Rect,
) -> bool:
    search = page.rect.height * CHART_HEADING_TOP_SEARCH_FRAC
    try:
        blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return False
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if _is_page_number_text(text):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if not block.intersects(rect):
            continue
        if block.y0 >= head_rect.y0:
            continue
        if head_rect.y0 - block.y1 > search:
            continue
        if _horizontal_overlap_ratio(block, rect) < CHART_HEADING_TOP_BLOCK_H_OVERLAP:
            continue
        lines, chars = _text_stats(str(text))
        if lines == 0:
            continue
        avg_line_len = chars / max(1, lines)
        if (
            lines >= CHART_LABEL_PARAGRAPH_MIN_LINES
            and avg_line_len > CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN
        ):
            continue
        return True
    return False


def _extend_with_heading_above(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    head_rect = _nearest_heading_above(page, rect)
    if head_rect is None:
        return rect
    return rect | head_rect


def _adjust_rect_for_text_margins(
    page: fitz.Page,
    rect: fitz.Rect,
    gap_scale: float = 1.0,
    gap_scale_x: float = 1.0,
) -> fitz.Rect:
    page_rect = page.rect
    min_gap = page_rect.height * CHART_EDGE_TEXT_MIN_GAP_FRAC * gap_scale
    max_pad = page_rect.height * CHART_EDGE_TEXT_MAX_PAD_FRAC
    min_gap_x = page_rect.width * CHART_EDGE_TEXT_MIN_GAP_X_FRAC * gap_scale_x
    max_pad_x = page_rect.width * CHART_EDGE_TEXT_MAX_PAD_X_FRAC
    top_text = None
    bottom_text = None
    left_text = None
    right_text = None
    try:
        blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if _rect_intersection_area(block, rect) <= 0.0:
            continue
        top_text = y0 if top_text is None else min(top_text, y0)
        bottom_text = y1 if bottom_text is None else max(bottom_text, y1)
        left_text = x0 if left_text is None else min(left_text, x0)
        right_text = x1 if right_text is None else max(right_text, x1)
    if top_text is not None:
        gap = top_text - rect.y0
        if gap < min_gap:
            pad = min(max_pad, min_gap - gap)
            rect = fitz.Rect(
                rect.x0, max(page_rect.y0, rect.y0 - pad), rect.x1, rect.y1
            )
    if bottom_text is not None:
        gap = rect.y1 - bottom_text
        if gap < min_gap:
            pad = min(max_pad, min_gap - gap)
            rect = fitz.Rect(
                rect.x0, rect.y0, rect.x1, min(page_rect.y1, rect.y1 + pad)
            )
    if left_text is not None:
        gap = left_text - rect.x0
        if gap < min_gap_x:
            pad = min(max_pad_x, min_gap_x - gap)
            rect = fitz.Rect(
                max(page_rect.x0, rect.x0 - pad), rect.y0, rect.x1, rect.y1
            )
    if right_text is not None:
        gap = rect.x1 - right_text
        if gap < min_gap_x:
            pad = min(max_pad_x, min_gap_x - gap)
            rect = fitz.Rect(
                rect.x0, rect.y0, min(page_rect.x1, rect.x1 + pad), rect.y1
            )
    return rect


def _expand_rect_into_whitespace(
    page: fitz.Page,
    rect: fitz.Rect,
    allow_top: bool = True,
    allow_bottom: bool = True,
    allow_left: bool = True,
    allow_right: bool = True,
) -> fitz.Rect:
    page_rect = page.rect
    guard_y = page_rect.height * CHART_WHITESPACE_GUARD_GAP_FRAC
    guard_x = page_rect.width * CHART_WHITESPACE_GUARD_GAP_X_FRAC
    max_pad_y = page_rect.height * CHART_WHITESPACE_MAX_PAD_FRAC
    max_pad_x = page_rect.width * CHART_WHITESPACE_MAX_PAD_X_FRAC
    top_dist = None
    bottom_dist = None
    left_dist = None
    right_dist = None

    blockers: List[fitz.Rect] = []
    try:
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
            if not text:
                continue
            blockers.append(fitz.Rect(x0, y0, x1, y1))
    except PDF_FIGURE_EXCEPTIONS:
        blockers = []

    blockers.extend(_drawing_rects(page))
    blockers.extend(_image_block_rects(page))

    for block in blockers:
        if _rect_intersection_area(block, rect) > 0.0:
            continue
        if _horizontal_overlap_ratio(block, rect) >= CHART_WHITESPACE_MIN_OVERLAP:
            if block.y1 <= rect.y0:
                dist = rect.y0 - block.y1
                top_dist = dist if top_dist is None else min(top_dist, dist)
            elif block.y0 >= rect.y1:
                dist = block.y0 - rect.y1
                bottom_dist = dist if bottom_dist is None else min(bottom_dist, dist)
        if _vertical_overlap_ratio(block, rect) >= CHART_WHITESPACE_MIN_OVERLAP:
            if block.x1 <= rect.x0:
                dist = rect.x0 - block.x1
                left_dist = dist if left_dist is None else min(left_dist, dist)
            elif block.x0 >= rect.x1:
                dist = block.x0 - rect.x1
                right_dist = dist if right_dist is None else min(right_dist, dist)

    top_limit = rect.y0 - page_rect.y0
    if top_dist is None:
        top_pad = min(max_pad_y, top_limit)
    else:
        top_pad = min(max_pad_y, max(0.0, top_dist - guard_y))
    bottom_limit = page_rect.y1 - rect.y1
    if bottom_dist is None:
        bottom_pad = min(max_pad_y, bottom_limit)
    else:
        bottom_pad = min(max_pad_y, max(0.0, bottom_dist - guard_y))
    left_limit = rect.x0 - page_rect.x0
    if left_dist is None:
        left_pad = min(max_pad_x, left_limit)
    else:
        left_pad = min(max_pad_x, max(0.0, left_dist - guard_x))
    right_limit = page_rect.x1 - rect.x1
    if right_dist is None:
        right_pad = min(max_pad_x, right_limit)
    else:
        right_pad = min(max_pad_x, max(0.0, right_dist - guard_x))

    if not allow_top:
        top_pad = 0.0
    if not allow_bottom:
        bottom_pad = 0.0
    if not allow_left:
        left_pad = 0.0
    if not allow_right:
        right_pad = 0.0

    return fitz.Rect(
        max(page_rect.x0, rect.x0 - left_pad),
        max(page_rect.y0, rect.y0 - top_pad),
        min(page_rect.x1, rect.x1 + right_pad),
        min(page_rect.y1, rect.y1 + bottom_pad),
    )


def _caption_near_top(rect: fitz.Rect, cap_rect: fitz.Rect, frac: float = 0.35) -> bool:
    if rect.height <= 0:
        return False
    return cap_rect.y0 <= rect.y0 + rect.height * frac


def _merge_caption_above(
    rect: fitz.Rect,
    cap_rect: fitz.Rect,
    page_rect: fitz.Rect,
) -> fitz.Rect:
    max_gap = page_rect.height * CHART_CAPTION_MERGE_MAX_GAP_FRAC
    if cap_rect.y1 <= rect.y0 and rect.y0 - cap_rect.y1 <= max_gap:
        return rect | cap_rect
    if cap_rect.y0 < rect.y0 and cap_rect.y1 > rect.y0:
        return rect | cap_rect
    return rect


def _nearest_heading_above(page: fitz.Page, rect: fitz.Rect) -> Optional[fitz.Rect]:
    headings = _heading_lines(page)
    if not headings:
        return None
    page_rect = page.rect
    max_gap = page_rect.height * CHART_HEADING_MERGE_MAX_GAP_FRAC
    best_rect: Optional[fitz.Rect] = None
    best_dist = 1e9
    for head_rect, _ in headings:
        if (
            _horizontal_overlap_ratio(head_rect, rect)
            < CHART_HEADING_TOP_BLOCK_H_OVERLAP
        ):
            continue
        if head_rect.y1 <= rect.y0:
            if rect.y0 - head_rect.y1 <= max_gap:
                if _has_intervening_paragraph(page, head_rect, rect):
                    continue
                dist = rect.y0 - head_rect.y1
                if dist < best_dist:
                    best_rect = head_rect
                    best_dist = dist
            continue
        if head_rect.intersects(rect) and head_rect.y0 <= rect.y0 + rect.height * 0.4:
            if 0.0 < best_dist:
                best_rect = head_rect
                best_dist = 0.0
    return best_rect


def _note_block_bottom(
    page: fitz.Page, rect: fitz.Rect, *, min_y0_frac: float = 0.45
) -> Optional[float]:
    min_y0 = rect.y0 + rect.height * min_y0_frac
    best: Optional[float] = None
    page_rect = page.rect
    max_gap_x = page_rect.width * CHART_NOTE_MAX_GAP_X_FRAC
    try:
        blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return None
    for x0, y0, x1, y1, text, *_ in blocks:
        if y0 < min_y0 or y0 > rect.y1 + CHART_NOTE_MAX_DIST:
            continue
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        if not lines:
            continue
        first = lines[0].lower()
        if not first.startswith(NOTE_LABEL_PREFIXES):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        h_overlap = _horizontal_overlap_ratio(block, rect)
        gap_ok = (block.x0 >= rect.x1 and block.x0 - rect.x1 <= max_gap_x) or (
            block.x1 <= rect.x0 and rect.x0 - block.x1 <= max_gap_x
        )
        if h_overlap < 0.3 and not gap_ok:
            continue
        if best is None or y1 > best:
            best = y1
    return best


def _next_block_top_below(
    page: fitz.Page,
    rect: fitz.Rect,
    min_y: float,
    max_y: float,
) -> Optional[float]:
    best: Optional[float] = None
    blocks: List[fitz.Rect] = []
    try:
        for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
            if not text:
                continue
            blocks.append(fitz.Rect(x0, y0, x1, y1))
    except PDF_FIGURE_EXCEPTIONS:
        blocks = []
    blocks.extend(_drawing_rects(page))
    blocks.extend(_image_block_rects(page))
    for block in blocks:
        if block.y0 < min_y or block.y0 > max_y:
            continue
        if _horizontal_overlap_ratio(block, rect) < CHART_NOTE_BELOW_MIN_H_OVERLAP:
            continue
        if best is None or block.y0 < best:
            best = block.y0
    return best


def _clamp_bottom_to_note(
    page: fitz.Page,
    rect: fitz.Rect,
    note_bottom: float,
    page_rect: fitz.Rect,
) -> fitz.Rect:
    search_bottom = min(
        page_rect.y1,
        note_bottom + CHART_NOTE_PAD_EXTRA + CHART_NOTE_BELOW_GUARD_PX,
    )
    max_bottom = min(
        page_rect.y1,
        note_bottom - CHART_CROP_PAD_COMPENSATION + CHART_NOTE_PAD_EXTRA,
    )
    blocker_top = _next_block_top_below(
        page,
        rect,
        note_bottom + 1,
        search_bottom,
    )
    if blocker_top is not None:
        max_bottom = min(
            max_bottom,
            blocker_top
            - CHART_NOTE_BELOW_GUARD_PX
            - CHART_CROP_PAD_COMPENSATION,
        )
    if max_bottom <= rect.y0:
        return rect
    if rect.y1 > max_bottom:
        return fitz.Rect(rect.x0, rect.y0, rect.x1, max_bottom)
    if rect.y1 < max_bottom:
        return fitz.Rect(rect.x0, rect.y0, rect.x1, max_bottom)
    return rect


def _expand_table_bbox(
    page: fitz.Page,
    bbox: Tuple[float, float, float, float],
    method: str,
    *,
    page_text_blocks: Optional[List[_PageTextBlock]] = None,
    page_text_bands: Optional[List[_TableTextBand]] = None,
) -> Tuple[float, float, float, float]:
    if method not in ("stream", "lattice", "ranked"):
        return bbox
    return _compose_table_bbox(
        page,
        bbox,
        method,
        page_text_blocks=page_text_blocks,
        page_text_bands=page_text_bands,
    )


def _save_thumb(
    pix: fitz.Pixmap, out_dir: str, report_name: str, index: int, max_w: int = 480
) -> str:
    if pix.alpha:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    elif pix.colorspace and pix.colorspace != fitz.csRGB:
        pix = fitz.Pixmap(fitz.csRGB, pix)

    png_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    if img.width > max_w:
        new_h = int(img.height * max_w / img.width)
        img = img.resize((max_w, new_h), Image.LANCZOS)

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    if index == 0:
        filename = f"{report_name}.png"
    else:
        filename = f"{report_name}{index}.png"
    p = Path(out_dir) / filename
    img.save(p.as_posix(), format="PNG")
    return p.as_posix()


def _nearby_text(
    page: fitz.Page,
    rect: fitz.Rect,
    max_dist: float = 90,
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> str:
    best = ("", 1e9)
    if blocks is None:
        try:
            blocks = page.get_text("blocks")
        except PDF_FIGURE_EXCEPTIONS:
            return ""
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if _is_page_number_text(text):
            continue
        r = fitz.Rect(x0, y0, x1, y1)
        dy = r.y0 - rect.y1
        dist = dy if dy >= 0 else abs(dy) + 24
        if dist <= max_dist and dist < best[1]:
            best = (text.strip(), dist)
    return best[0]


def _extract_charts_sequential(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    pages: Optional[List[int]] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from .visual_candidates import _extract_visuals_sequential

    return _extract_visuals_sequential(
        pdf_path,
        thumbs_dir,
        report_name,
        save_thumbs=save_thumbs,
        doc=doc,
        pages=pages,
    )


def _candidate_index_from_id(candidate_id: str) -> int:
    try:
        return int(str(candidate_id).rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return 0


def _merge_stats(
    base: Dict[str, object], extra: Dict[str, object]
) -> Dict[str, object]:
    merged = dict(base)
    for key, value in extra.items():
        if key == "reasons":
            reasons = value if isinstance(value, dict) else {}
            for reason, count in reasons.items():
                for _ in range(max(0, _int_count(count))):
                    _tally_reason(merged, str(reason))
            continue
        merged[key] = _int_count(merged.get(key, 0)) + _int_count(value)
    return merged


def _split_even_chunks(values: List[int], chunk_count: int) -> List[List[int]]:
    if not values:
        return []
    chunk_count = max(1, min(int(chunk_count), len(values)))
    chunks: List[List[int]] = [[] for _ in range(chunk_count)]
    for idx, value in enumerate(values):
        chunks[idx % chunk_count].append(value)
    return [chunk for chunk in chunks if chunk]


def _resolve_candidate_parallel_workers(requested_workers: int, unit_count: int) -> int:
    if unit_count <= 1:
        return 1
    workers = 0
    try:
        workers = int(requested_workers)
    except (TypeError, ValueError):
        workers = 0
    if workers <= 0:
        env_value = os.getenv("INGEST_REPORT_WORKER_LIMIT")
        if env_value:
            try:
                workers = int(env_value)
            except (TypeError, ValueError):
                workers = 0
    if workers <= 0:
        workers = max(2, min(6, (os.cpu_count() or 2)))
    return max(1, min(workers, unit_count, 8))


def _extract_charts(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    parallel_workers: int = 1,
    pages: Optional[List[int]] = None,
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
    )


def _extract_tables_sequential(
    pdf_path: str,
    max_candidates: int = 0,
    pages: Optional[List[int]] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from .table_candidates import _extract_tables_sequential as _run_tables_sequential

    return _run_tables_sequential(
        pdf_path,
        max_candidates=max_candidates,
        pages=pages,
    )


def _extract_tables(
    pdf_path: str,
    max_candidates: int = 0,
    parallel_workers: int = 1,
    pages: Optional[List[int]] = None,
    doc: Optional[fitz.Document] = None,
) -> Tuple[List[Candidate], Dict[str, object]]:
    from .table_candidates import extract_table_candidates

    return extract_table_candidates(
        pdf_path,
        max_candidates=max_candidates,
        parallel_workers=parallel_workers,
        pages=pages,
        doc=doc,
    )


def _table_preview(rows: List[List[object]]) -> str:
    preview_lines = []
    for row in rows[:3]:
        if not row:
            continue
        preview_lines.append(" | ".join(_s(c) for c in row[:6]))
    return "\n".join(preview_lines)


def _extract_text_in_bbox(
    page: pdfplumber.page.Page, bbox: Tuple[float, float, float, float]
) -> str:
    try:
        return page.within_bbox(bbox).extract_text() or ""
    except (AttributeError, ValueError, RuntimeError, TypeError):
        return ""


def _text_stats(text: str) -> Tuple[int, int]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    char_count = sum(len(line) for line in lines)
    return len(lines), char_count


def _text_line_lengths(text: str) -> List[int]:
    return [len(line.strip()) for line in text.splitlines() if line.strip()]


def _chart_text_heavy(lines: int, chars: int, ratio: float) -> bool:
    if lines <= CHART_TEXT_MAX_LINES:
        return False
    if chars < CHART_TEXT_MIN_CHARS:
        return False
    return ratio >= CHART_TEXT_RATIO_THRESHOLD


def _chart_is_label_dense_not_prose(text: str) -> bool:
    lengths = _text_line_lengths(text)
    if len(lengths) < CHART_LABEL_DENSE_MIN_LINES:
        return False
    avg_line_len = sum(lengths) / max(1, len(lengths))
    median_line_len = statistics.median(lengths)
    long_line_ratio = sum(
        1 for length in lengths if length >= CHART_LABEL_DENSE_LONG_LINE_LEN
    ) / max(1, len(lengths))
    short_line_ratio = sum(
        1 for length in lengths if length <= CHART_LABEL_DENSE_SHORT_LINE_LEN
    ) / max(1, len(lengths))
    return (
        avg_line_len <= CHART_LABEL_DENSE_MAX_AVG_LINE_LEN
        and median_line_len <= CHART_LABEL_DENSE_MAX_MEDIAN_LINE_LEN
        and long_line_ratio <= CHART_LABEL_DENSE_MAX_LONG_LINE_RATIO
        and short_line_ratio >= CHART_LABEL_DENSE_MIN_SHORT_LINE_RATIO
    )


def _infographic_is_label_dense_not_prose(text: str) -> bool:
    lengths = _text_line_lengths(text)
    if len(lengths) < CHART_LABEL_DENSE_MIN_LINES:
        return False
    avg_line_len = sum(lengths) / max(1, len(lengths))
    median_line_len = statistics.median(lengths)
    long_line_ratio = sum(
        1 for length in lengths if length >= CHART_LABEL_DENSE_LONG_LINE_LEN
    ) / max(1, len(lengths))
    short_line_ratio = sum(
        1 for length in lengths if length <= CHART_LABEL_DENSE_SHORT_LINE_LEN
    ) / max(1, len(lengths))
    return (
        avg_line_len <= INFOGRAPHIC_LABEL_DENSE_MAX_AVG_LINE_LEN
        and median_line_len <= INFOGRAPHIC_LABEL_DENSE_MAX_MEDIAN_LINE_LEN
        and long_line_ratio <= INFOGRAPHIC_LABEL_DENSE_MAX_LONG_LINE_RATIO
        and short_line_ratio >= INFOGRAPHIC_LABEL_DENSE_MIN_SHORT_LINE_RATIO
    )


def _cell_is_numeric(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    for ch in stripped:
        if ch.isdigit():
            continue
        if ch in {".", ",", "%", "+", "-", "–"}:
            continue
        return False
    return any(ch.isdigit() for ch in stripped)


def _cell_words(text: str) -> int:
    return len([w for w in text.split() if w.strip()])


def _numeric_char_ratio(rows: List[List[object]]) -> Tuple[int, int]:
    numeric_chars = 0
    total_chars = 0
    for row in rows:
        for cell in row:
            text = _s(cell).strip()
            if not text:
                continue
            total_chars += len(text)
            numeric_chars += sum(1 for ch in text if ch.isdigit())
    return numeric_chars, total_chars


def _avg_words_per_cell(rows: List[List[object]]) -> float:
    words = 0
    cells = 0
    for row in rows:
        for cell in row:
            text = _s(cell).strip()
            if not text:
                continue
            cells += 1
            words += _cell_words(text)
    return (words / cells) if cells else 0.0


def _avg_first_col_words(rows: List[List[object]]) -> float:
    words = 0
    rows_counted = 0
    for row in rows:
        for cell in row:
            text = _s(cell).strip()
            if not text:
                continue
            rows_counted += 1
            words += _cell_words(text)
            break
    return (words / rows_counted) if rows_counted else 0.0


def _row_nonempty_counts(rows: List[List[object]]) -> List[int]:
    counts = []
    for row in rows:
        if not row:
            continue
        count = sum(1 for c in row if _s(c).strip())
        if count:
            counts.append(count)
    return counts


def _row_text_lengths(rows: List[List[object]]) -> List[int]:
    lengths = []
    for row in rows:
        if not row:
            continue
        texts = [_s(c).strip() for c in row]
        if not any(texts):
            continue
        lengths.append(sum(len(t) for t in texts))
    return lengths


def _col_consistency(row_counts: List[int]) -> float:
    if not row_counts:
        return 0.0
    counts: Dict[int, int] = {}
    for count in row_counts:
        counts[count] = counts.get(count, 0) + 1
    return max(counts.values()) / max(1, len(row_counts))


def _row_len_cv(lengths: List[int]) -> float:
    if len(lengths) < 2:
        return 0.0
    mean = sum(lengths) / len(lengths)
    if mean <= 0:
        return 0.0
    var = sum((length - mean) ** 2 for length in lengths) / len(lengths)
    return math.sqrt(var) / mean


def _cell_is_page_number(text: str) -> bool:
    return _is_page_number_text(text)


def _trim_top_page_number(
    rect: fitz.Rect,
    page: fitz.Page,
    cap_rect: Optional[fitz.Rect],
) -> fitz.Rect:
    page_rect = page.rect
    top_band = page_rect.height * 0.15
    left_band = page_rect.x0 + page_rect.width * 0.25
    right_band = page_rect.x0 + page_rect.width * 0.55
    guard = max(page_rect.height * 0.008, 6.0)
    best_y1: Optional[float] = None
    try:
        blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if not _is_page_number_text(text):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.y0 > page_rect.y0 + top_band:
            continue
        in_left_corner = block.x1 <= left_band
        in_right_corner = block.x0 >= right_band
        if not in_left_corner and not in_right_corner:
            continue
        if not block.intersects(rect):
            continue
        if cap_rect is not None and block.y1 >= cap_rect.y0 - guard:
            continue
        if best_y1 is None or block.y1 > best_y1:
            best_y1 = block.y1
    if best_y1 is None:
        return rect
    new_top = max(rect.y0, best_y1 + guard)
    if new_top >= rect.y1:
        return rect
    return fitz.Rect(rect.x0, new_top, rect.x1, rect.y1)


def _index_page_ratio(rows: List[List[object]]) -> float:
    index_rows = 0
    total_rows = 0
    for row in rows:
        row_cells = [c for c in row if _s(c).strip()]
        if len(row_cells) < 2:
            continue
        total_rows += 1
        first_text = _s(row_cells[0]).strip()
        last_text = _s(row_cells[-1]).strip()
        if _cell_words(
            first_text
        ) >= TABLE_INDEX_MIN_FIRST_COL_WORDS and _cell_is_page_number(last_text):
            index_rows += 1
    return (index_rows / total_rows) if total_rows else 0.0


def _rect_intersection_area(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    return max(0.0, inter.get_area())


def _heading_like_block(text: str, lines: int, avg_line_len: float) -> bool:
    if lines == 0:
        return False
    if lines > TABLE_EXPAND_HEADING_MAX_LINES:
        return False
    if avg_line_len > TABLE_EXPAND_HEADING_MAX_AVG_LINE_LEN:
        return False
    if _alpha_ratio(text) < TABLE_EXPAND_HEADING_MIN_ALPHA_RATIO:
        return False
    sentence_marks = text.count(".") + text.count("!") + text.count("?")
    if sentence_marks > TABLE_EXPAND_HEADING_MAX_SENTENCES:
        return False
    return True


def _text_block_stats(
    page: fitz.Page,
    bbox: Tuple[float, float, float, float],
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> Tuple[float, int, float]:
    rect = fitz.Rect(*bbox)
    rect_area = max(1.0, rect.get_area())
    block_area = 0.0
    line_count = 0
    total_line_len = 0
    if blocks is None:
        try:
            blocks = page.get_text("blocks")
        except PDF_FIGURE_EXCEPTIONS:
            blocks = []
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        block_rect = fitz.Rect(x0, y0, x1, y1)
        inter_area = _rect_intersection_area(rect, block_rect)
        if inter_area <= 0.0:
            continue
        block_area += inter_area
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        line_count += len(lines)
        total_line_len += sum(len(line) for line in lines)
    avg_line_len = (total_line_len / line_count) if line_count else 0.0
    return block_area / rect_area, line_count, avg_line_len


def _has_caption_hint(
    page: fitz.Page, bbox: Tuple[float, float, float, float], max_dist: float = 60
) -> bool:
    rect = fitz.Rect(*bbox)
    page_rect = page.rect
    above = fitz.Rect(rect.x0, max(page_rect.y0, rect.y0 - max_dist), rect.x1, rect.y0)
    below = fitz.Rect(rect.x0, rect.y1, rect.x1, min(page_rect.y1, rect.y1 + max_dist))
    text = ""
    try:
        text += page.get_text("text", clip=above) or ""
    except PDF_FIGURE_EXCEPTIONS:
        pass
    try:
        text += " " + (page.get_text("text", clip=below) or "")
    except PDF_FIGURE_EXCEPTIONS:
        pass
    lowered = text.lower()
    return any(hint in lowered for hint in TABLE_CAPTION_HINTS)


def _has_figure_context_hint(
    page: fitz.Page,
    bbox: Tuple[float, float, float, float],
    max_dist: float = 72,
    top_band_height: float = 44,
    horizontal_pad: float = 36,
) -> bool:
    rect = fitz.Rect(*bbox)
    page_rect = page.rect
    clip = fitz.Rect(
        max(page_rect.x0, rect.x0 - horizontal_pad),
        max(page_rect.y0, rect.y0 - max_dist),
        min(page_rect.x1, rect.x1 + horizontal_pad),
        min(page_rect.y1, rect.y0 + top_band_height),
    )
    if clip.is_empty or clip.y1 <= clip.y0:
        return False
    try:
        text = page.get_text("text", clip=clip) or ""
    except PDF_FIGURE_EXCEPTIONS:
        text = ""
    if _table_text_has_figure_context(text):
        return True
    full_width_clip = fitz.Rect(
        page_rect.x0,
        max(page_rect.y0, rect.y0 - max_dist),
        page_rect.x1,
        min(page_rect.y1, rect.y0 + top_band_height),
    )
    if full_width_clip.is_empty or full_width_clip.y1 <= full_width_clip.y0:
        return False
    try:
        full_width_text = page.get_text("text", clip=full_width_clip) or ""
    except PDF_FIGURE_EXCEPTIONS:
        return False
    return _table_text_has_figure_context(full_width_text)


def _validate_table_candidate(cand: _TableCandidate) -> Tuple[bool, str]:
    if cand.method == "image":
        if cand.area_frac < 0.75:
            return False, "image_table_too_small"
        if cand.row_count < 20 or cand.col_count < 5:
            return False, "image_table_too_few_grid_groups"
        if cand.aspect < 1.2 or cand.aspect > 3.5:
            return False, "image_table_extreme_aspect"
        return True, ""
    if cand.row_count < TABLE_MIN_ROWS or cand.col_count < TABLE_MIN_COLS:
        return False, "too_few_rows_cols"
    if cand.non_empty_cells < TABLE_MIN_NONEMPTY_CELLS:
        return False, "too_few_cells"
    if cand.text_len < TABLE_MIN_TEXT_CHARS:
        return False, "no_text"
    if (
        cand.area_frac < TABLE_MIN_AREA_FRAC
        and cand.text_len < TABLE_MIN_TEXT_CHARS * 2
    ):
        return False, "too_small"
    if (
        cand.aspect < TABLE_MIN_ASPECT or cand.aspect > TABLE_MAX_ASPECT
    ) and cand.text_len < TABLE_MIN_TEXT_CHARS * 3:
        return False, "extreme_aspect"
    if (
        cand.width_frac < TABLE_MIN_WIDTH_FRAC
        and cand.text_len < TABLE_MIN_TEXT_CHARS * 2
    ):
        return False, "too_narrow"
    if (
        cand.height_frac < TABLE_MIN_HEIGHT_FRAC
        and cand.text_len < TABLE_MIN_TEXT_CHARS * 2
    ):
        return False, "too_short"
    if _contents_like(cand):
        return False, "contents_like"
    if _section_list_like(cand):
        return False, "section_list"
    if _contents_grid_like(cand):
        return False, "contents_grid"
    if _reference_block_like(cand):
        return False, "reference_block"
    if _front_matter_like(cand):
        return False, "front_matter"
    if _contact_block_like(cand):
        return False, "contact_block"
    if _prose_box_like(cand):
        return False, "prose_box"
    if _visual_quote_page_like(cand):
        return False, "visual_quote_page"
    if cand.figure_context_hint:
        return False, "figure_caption_context"
    if _chart_fragment_like(cand):
        return False, "figure_chart_fragment"
    if cand.method == "stream":
        if (
            cand.row_count >= TABLE_TEXT_HEAVY_MIN_ROWS
            and cand.col_count <= TABLE_INDEX_MAX_COLS
            and cand.numeric_ratio <= TABLE_TEXT_HEAVY_MAX_NUMERIC_RATIO
            and cand.avg_words_per_cell >= TABLE_TEXT_HEAVY_MIN_AVG_WORDS
        ):
            return False, "text_heavy_stream"
        if (
            cand.row_count >= TABLE_INDEX_MIN_ROWS
            and cand.col_count <= TABLE_INDEX_MAX_COLS
            and cand.index_page_ratio >= TABLE_INDEX_PAGE_RATIO
            and cand.avg_first_col_words >= TABLE_INDEX_MIN_FIRST_COL_WORDS
        ):
            return False, "index_like"
        if _stream_slide_card_like(cand):
            return False, "stream_slide_card"
        if _stream_text_layout_like(cand):
            return False, "stream_text_layout"
        if _stream_text_block_like(cand):
            return False, "stream_text_block"
        if _stream_infobox_like(cand):
            return False, "stream_infobox"
        if _stream_list_like(cand):
            return False, "stream_list"
        if _stream_panel_like(cand):
            return False, "stream_panel"
        if _stream_sparse_text_like(cand):
            return False, "stream_sparse_text"
        if _stream_multilist_infographic_like(cand):
            return False, "stream_multilist_infographic"
        if _stream_low_consistency(cand):
            return False, "stream_low_consistency"
        if _text_block_like_loose(cand):
            return False, "text_block_like_loose"
        if _text_block_like(cand):
            return False, "text_block_like"
    return True, ""


def _stream_text_layout_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if (
        cand.row_count < TABLE_STREAM_TEXTY_MIN_ROWS
        or cand.col_count < TABLE_STREAM_TEXTY_MIN_COLS
    ):
        return False
    if cand.area_frac < TABLE_STREAM_TEXTY_MIN_AREA:
        return False
    if cand.numeric_ratio > TABLE_STREAM_TEXTY_MAX_NUMERIC_RATIO:
        return False
    if cand.line_count < TABLE_STREAM_TEXTY_MIN_LINES:
        return False
    if cand.avg_line_len < TABLE_STREAM_TEXTY_MIN_AVG_LINE_LEN:
        return False
    return True


def _stream_text_block_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_TEXTBLOCK_MIN_AREA:
        return False
    if cand.numeric_ratio > TABLE_STREAM_TEXTBLOCK_MAX_NUMERIC_RATIO:
        return False
    if cand.line_count < TABLE_STREAM_TEXTBLOCK_MIN_LINES:
        return False
    if cand.avg_line_len < TABLE_STREAM_TEXTBLOCK_MIN_AVG_LINE_LEN:
        return False
    if cand.col_consistency > TABLE_STREAM_TEXTBLOCK_MAX_COL_CONSISTENCY:
        return False
    if cand.row_len_cv < TABLE_STREAM_TEXTBLOCK_MIN_ROW_LEN_CV:
        return False
    fill_ratio = cand.non_empty_cells / max(1, cand.total_cells)
    if fill_ratio > TABLE_STREAM_TEXTBLOCK_MAX_FILL_RATIO:
        return False
    return True


def _stream_infobox_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_INFOBOX_MIN_AREA:
        return False
    if cand.row_count < TABLE_STREAM_INFOBOX_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_INFOBOX_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_INFOBOX_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_INFOBOX_MAX_AVG_WORDS:
        return False
    if cand.line_count < TABLE_STREAM_INFOBOX_MIN_LINES:
        return False
    if cand.row_len_cv > TABLE_STREAM_INFOBOX_MAX_ROW_LEN_CV:
        return False
    return True


def _stream_list_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.row_count < TABLE_STREAM_LIST_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_LIST_MAX_COLS:
        return False
    if cand.area_frac > TABLE_STREAM_LIST_MAX_AREA_FRAC:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_LIST_MAX_AVG_WORDS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_LIST_MAX_NUMERIC_RATIO:
        return False
    return True


def _stream_panel_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_PANEL_MIN_AREA_FRAC:
        return False
    if cand.row_count < TABLE_STREAM_PANEL_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_PANEL_MAX_COLS:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_PANEL_MAX_AVG_WORDS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_PANEL_MAX_NUMERIC_RATIO:
        return False
    return True


def _stream_slide_card_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_SLIDE_CARD_MIN_AREA:
        return False
    if cand.area_frac > TABLE_STREAM_SLIDE_CARD_MAX_AREA:
        return False
    if cand.row_count < TABLE_STREAM_SLIDE_CARD_MIN_ROWS:
        return False
    if cand.col_count > TABLE_STREAM_SLIDE_CARD_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_STREAM_SLIDE_CARD_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell < TABLE_STREAM_SLIDE_CARD_MIN_AVG_WORDS:
        return False
    if cand.avg_words_per_cell > TABLE_STREAM_SLIDE_CARD_MAX_AVG_WORDS:
        return False
    if cand.text_block_area_frac < TABLE_STREAM_SLIDE_CARD_MIN_TEXT_BLOCK_AREA:
        return False
    if cand.avg_line_len < TABLE_STREAM_SLIDE_CARD_MIN_AVG_LINE_LEN:
        return False
    if cand.col_consistency > TABLE_STREAM_SLIDE_CARD_MAX_COL_CONSISTENCY:
        return False
    return cand.line_count >= max(
        TABLE_STREAM_SLIDE_CARD_MIN_LINES,
        cand.row_count + TABLE_STREAM_SLIDE_CARD_LINE_PAD,
    )


def _stream_sparse_text_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.area_frac < TABLE_STREAM_SPARSE_MIN_AREA:
        return False
    if cand.line_count > TABLE_STREAM_SPARSE_MAX_LINES:
        return False
    if cand.avg_line_len < TABLE_STREAM_SPARSE_MIN_AVG_LINE_LEN:
        return False
    if cand.numeric_ratio > TABLE_STREAM_SPARSE_MAX_NUMERIC_RATIO:
        return False
    if cand.col_count > TABLE_STREAM_SPARSE_MAX_COLS:
        return False
    return True


def _stream_multilist_infographic_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.area_frac < 0.4:
        return False
    if cand.row_count < 12 or cand.col_count < 5:
        return False
    if cand.avg_words_per_cell > 2.5:
        return False
    if cand.numeric_ratio > 0.12:
        return False
    if cand.line_count < 18 or cand.avg_line_len > 16.0:
        return False
    lines = _nonempty_text_lines(cand.text)
    if len(lines) < 12:
        return False
    numbered_list_hits = len(re.findall(r"\b[1-5]\.\s+\w", cand.text))
    if numbered_list_hits < 6:
        return False
    heading_hits = 0
    for line in lines:
        words = line.split()
        if 1 <= len(words) <= 3 and line[:1].isalpha() and line[:1].isupper():
            heading_hits += 1
    return heading_hits >= 3


def _stream_low_consistency(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if (
        cand.row_count < TABLE_STREAM_MIN_ROWS_FOR_LIKENESS
        or cand.col_count < TABLE_STREAM_MIN_COLS_FOR_LIKENESS
    ):
        return False
    if cand.col_consistency >= TABLE_STREAM_MIN_COL_CONSISTENCY:
        return False
    if cand.row_len_cv <= TABLE_STREAM_MAX_ROW_LEN_CV:
        return False
    return True


def _text_block_like(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.text_block_area_frac < TEXT_BLOCK_MIN_AREA_FRAC:
        return False
    if cand.text_block_line_count < TEXT_BLOCK_MIN_LINES:
        return False
    if cand.text_block_avg_line_len < TEXT_BLOCK_MIN_AVG_LINE_LEN:
        return False
    if cand.numeric_ratio > TEXT_BLOCK_MAX_NUMERIC_RATIO:
        return False
    return True


def _text_block_like_loose(cand: _TableCandidate) -> bool:
    if cand.caption_hint:
        return False
    if cand.text_block_area_frac < TEXT_BLOCK_MIN_AREA_FRAC:
        return False
    if cand.text_block_line_count < TEXT_BLOCK_LOOSE_MIN_LINES:
        return False
    if cand.text_block_avg_line_len < TEXT_BLOCK_LOOSE_MIN_AVG_LINE_LEN:
        return False
    if cand.numeric_ratio > TEXT_BLOCK_LOOSE_MAX_NUMERIC_RATIO:
        return False
    return True


def _filled_cells_per_row(cand: _TableCandidate) -> float:
    return cand.non_empty_cells / max(1, cand.row_count)


def _nonempty_text_lines(text: str) -> List[str]:
    return [line.strip() for line in text.splitlines() if line.strip()]


def _terminal_page_number_hits(lines: List[str]) -> int:
    hits = 0
    for line in lines:
        if re.search(r"\b\d{1,3}\s*$", line):
            hits += 1
    return hits


def _contents_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.row_count < TABLE_CONTENTS_MIN_ROWS:
        return False
    if cand.col_count < TABLE_CONTENTS_MIN_COLS:
        return False
    if _filled_cells_per_row(cand) > TABLE_CONTENTS_MAX_FILLED_CELLS_PER_ROW:
        return False
    if cand.numeric_ratio < TABLE_CONTENTS_MIN_NUMERIC_RATIO:
        return False
    if cand.numeric_ratio > TABLE_CONTENTS_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_CONTENTS_MAX_AVG_WORDS_PER_CELL:
        return False
    if cand.avg_first_col_words > TABLE_CONTENTS_MAX_FIRST_COL_WORDS:
        return False
    lines = _nonempty_text_lines(cand.text)
    if len(lines) < TABLE_CONTENTS_MIN_ROWS:
        return False
    terminal_page_hits = 0
    for line in lines:
        if not re.search(r"\b\d{1,3}\s*$", line):
            continue
        numeric_tokens = re.findall(r"\b\d+(?:\.\d+)?\b", line)
        if len(numeric_tokens) != 1:
            continue
        if "." in numeric_tokens[0]:
            continue
        title = re.sub(r"\b\d{1,3}\s*$", "", line).strip(" .\t")
        if not title:
            continue
        terminal_page_hits += 1
    required_hits = max(6, math.ceil(len(lines) * 0.45))
    return terminal_page_hits >= required_hits


def _section_list_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.row_count < TABLE_SECTION_LIST_MIN_ROWS:
        return False
    if cand.col_count > TABLE_SECTION_LIST_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_SECTION_LIST_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_SECTION_LIST_MAX_AVG_WORDS_PER_CELL:
        return False
    lines = _nonempty_text_lines(cand.text)
    if len(lines) < TABLE_SECTION_LIST_MIN_ROWS:
        return False
    avg_line_len = sum(len(line) for line in lines) / max(1, len(lines))
    if avg_line_len > TABLE_SECTION_LIST_MAX_AVG_LINE_LEN:
        return False
    short_line_ratio = sum(1 for line in lines if len(line) <= 60) / max(1, len(lines))
    if short_line_ratio < TABLE_SECTION_LIST_MIN_SHORT_LINE_RATIO:
        return False
    terminal_hits = _terminal_page_number_hits(lines)
    if terminal_hits >= TABLE_SECTION_LIST_MIN_TERMINAL_NUMBER_HITS:
        return True
    dot_leader_hits = len(re.findall(r"(?:^|\n)\s*\d{1,2}\s*\.\s*\.\s*\.", cand.text))
    if dot_leader_hits >= 3:
        return True
    fragmented_dot_hits = len(re.findall(r"\.\s*\.", cand.text))
    if (
        fragmented_dot_hits >= TABLE_SECTION_LIST_MIN_FRAGMENTED_DOT_HITS
        and cand.area_frac <= TABLE_SECTION_LIST_MAX_AREA_FRAC_WITHOUT_NUMBERS
        and cand.aspect <= TABLE_SECTION_LIST_MAX_NARROW_ASPECT
    ):
        return True
    if cand.text_block_area_frac < TABLE_SECTION_LIST_MIN_TEXT_BLOCK_AREA:
        return False
    return (
        cand.numeric_ratio <= TABLE_CONTENTS_MIN_NUMERIC_RATIO / 2.0
        and cand.area_frac <= TABLE_SECTION_LIST_MAX_AREA_FRAC_WITHOUT_NUMBERS
    )


def _contents_grid_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.row_count < TABLE_CONTENTS_GRID_MIN_ROWS:
        return False
    if cand.col_count < TABLE_CONTENTS_GRID_MIN_COLS:
        return False
    if cand.col_count > TABLE_CONTENTS_GRID_MAX_COLS:
        return False
    if cand.area_frac < TABLE_CONTENTS_GRID_MIN_AREA:
        return False
    if cand.numeric_ratio < TABLE_CONTENTS_GRID_MIN_NUMERIC_RATIO:
        return False
    if cand.numeric_ratio > TABLE_CONTENTS_GRID_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_CONTENTS_GRID_MAX_AVG_WORDS:
        return False
    if cand.avg_first_col_words > TABLE_CONTENTS_GRID_MAX_FIRST_COL_WORDS:
        return False
    if cand.avg_line_len > TABLE_CONTENTS_GRID_MAX_AVG_LINE_LEN:
        return False
    lines = _nonempty_text_lines(cand.text)
    if len(lines) < TABLE_CONTENTS_GRID_MIN_ROWS:
        return False
    numbered_line_hits = sum(
        1 for line in lines if len(re.findall(r"\b\d{1,2}\b", line)) >= 2
    )
    if numbered_line_hits < TABLE_CONTENTS_GRID_MIN_NUMBERED_LINES:
        return False
    uppercase_short_ratio = sum(
        1
        for line in lines
        if len(line) <= 42 and any(char.isalpha() for char in line) and line == line.upper()
    ) / max(1, len(lines))
    return uppercase_short_ratio >= TABLE_CONTENTS_GRID_MIN_UPPERCASE_SHORT_RATIO


def _reference_block_like(cand: _TableCandidate) -> bool:
    lowered = cand.text.lower()
    url_hits = len(re.findall(r"https?://|doi\.org|www\.", lowered))
    year_hits = len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", lowered))
    term_hits = sum(lowered.count(term) for term in TABLE_REFERENCE_TERMS)
    numbered_hits = len(re.findall(r"(?:^|\n)\s*\d+\.\s+", cand.text))
    if cand.method != "stream":
        return False
    if (
        numbered_hits >= TABLE_REFERENCE_MIN_NUMBERED_HITS
        and year_hits >= TABLE_REFERENCE_MIN_YEAR_HITS
        and (url_hits >= 1 or term_hits >= 1)
        and cand.numeric_ratio <= TABLE_REFERENCE_MAX_NUMERIC_RATIO
        and cand.avg_words_per_cell >= TABLE_REFERENCE_MIN_AVG_WORDS_PER_CELL
    ):
        return True
    if (
        url_hits >= TABLE_REFERENCE_MIN_URL_HITS
        and year_hits >= TABLE_REFERENCE_MIN_YEAR_HITS
        and cand.col_count <= TABLE_REFERENCE_MAX_COLS
    ):
        return True
    if cand.row_count < TABLE_REFERENCE_MIN_ROWS:
        return False
    if cand.col_count > TABLE_REFERENCE_MAX_COLS:
        return False
    if _filled_cells_per_row(cand) > TABLE_REFERENCE_MAX_FILLED_CELLS_PER_ROW:
        return False
    if cand.numeric_ratio > TABLE_REFERENCE_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_first_col_words < TABLE_REFERENCE_MIN_FIRST_COL_WORDS:
        return False
    if cand.avg_line_len < TABLE_REFERENCE_MIN_AVG_LINE_LEN:
        return False
    if url_hits >= TABLE_REFERENCE_MIN_URL_HITS:
        return year_hits >= TABLE_REFERENCE_MIN_YEAR_HITS
    return (
        year_hits >= TABLE_REFERENCE_MIN_YEAR_HITS
        and term_hits >= TABLE_REFERENCE_MIN_TERM_HITS
    )


def _front_matter_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    lowered = cand.text.lower()
    if not any(term in lowered for term in TABLE_FRONT_MATTER_TERMS):
        return False
    if cand.col_count > TABLE_FRONT_MATTER_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_FRONT_MATTER_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_FRONT_MATTER_MAX_AVG_WORDS_PER_CELL:
        return False
    return cand.area_frac >= TABLE_FRONT_MATTER_MIN_AREA_FRAC


def _contact_block_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.col_count > TABLE_CONTACT_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_CONTACT_MAX_NUMERIC_RATIO:
        return False
    if cand.area_frac < TABLE_CONTACT_MIN_AREA_FRAC:
        return False
    if cand.line_count < TABLE_CONTACT_MIN_LINES:
        return False
    if cand.avg_line_len < TABLE_CONTACT_MIN_AVG_LINE_LEN:
        return False
    return EMAIL_ADDRESS_RX.search(cand.text) is not None


def _prose_box_like(cand: _TableCandidate) -> bool:
    if cand.row_count < TABLE_PROSE_BOX_MIN_ROWS:
        return False
    if cand.col_count < TABLE_PROSE_BOX_MIN_COLS:
        return False
    filled_cells_per_row = _filled_cells_per_row(cand)
    if filled_cells_per_row > TABLE_PROSE_BOX_MAX_FILLED_CELLS_PER_ROW:
        return False
    if cand.numeric_ratio > TABLE_PROSE_BOX_MAX_NUMERIC_RATIO:
        return False
    if cand.text_block_area_frac < TABLE_PROSE_BOX_MIN_TEXT_BLOCK_AREA:
        return False
    if cand.text_block_avg_line_len < TABLE_PROSE_BOX_MIN_TEXT_BLOCK_AVG_LINE_LEN:
        return False
    if cand.avg_first_col_words < TABLE_PROSE_BOX_MIN_FIRST_COL_WORDS:
        return False
    max_line_count = max(
        cand.row_count + TABLE_PROSE_BOX_LINECOUNT_EXTRA,
        int(cand.row_count * TABLE_PROSE_BOX_MAX_LINECOUNT_ROW_MULT),
    )
    if cand.line_count > max_line_count:
        return False
    return True


def _visual_quote_page_like(cand: _TableCandidate) -> bool:
    if cand.method != "stream":
        return False
    if cand.row_count > TABLE_VISUAL_QUOTE_MAX_ROWS:
        return False
    if cand.col_count > TABLE_VISUAL_QUOTE_MAX_COLS:
        return False
    if cand.numeric_ratio > TABLE_VISUAL_QUOTE_MAX_NUMERIC_RATIO:
        return False
    if cand.avg_words_per_cell > TABLE_VISUAL_QUOTE_MAX_AVG_WORDS_PER_CELL:
        return False
    if cand.text_len > TABLE_VISUAL_QUOTE_MAX_TEXT_LEN:
        return False
    if cand.aspect > TABLE_VISUAL_QUOTE_MAX_ASPECT:
        return False
    if cand.width_frac > TABLE_VISUAL_QUOTE_MAX_WIDTH_FRAC:
        return False
    if cand.height_frac < TABLE_VISUAL_QUOTE_MIN_HEIGHT_FRAC:
        return False
    if _filled_cells_per_row(cand) > TABLE_VISUAL_QUOTE_MAX_FILLED_CELLS_PER_ROW:
        return False
    if cand.text_block_area_frac > TABLE_VISUAL_QUOTE_MAX_TEXT_BLOCK_AREA:
        return False
    return True


def _chart_fragment_like(cand: _TableCandidate) -> bool:
    if cand.method != "lattice":
        return False
    if not cand.wide_figure_context_hint:
        return False
    if cand.caption_hint:
        return False
    if cand.avg_words_per_cell > TABLE_FIGURE_FRAGMENT_MAX_AVG_WORDS_PER_CELL:
        return False
    fill_ratio = cand.non_empty_cells / max(1, cand.total_cells)
    compact_numeric_fragment = (
        cand.row_count <= TABLE_FIGURE_FRAGMENT_COMPACT_MAX_ROWS
        and cand.area_frac <= TABLE_FIGURE_FRAGMENT_COMPACT_MAX_AREA_FRAC
        and cand.numeric_ratio >= TABLE_FIGURE_FRAGMENT_MIN_NUMERIC_RATIO
    )
    wide_sparse_fragment = (
        cand.col_count >= TABLE_FIGURE_FRAGMENT_MIN_WIDE_COLS
        and cand.row_count <= TABLE_FIGURE_FRAGMENT_COMPACT_MAX_ROWS + 5
        and cand.numeric_ratio >= TABLE_FIGURE_FRAGMENT_MIN_NUMERIC_RATIO
        and fill_ratio <= TABLE_FIGURE_FRAGMENT_MAX_FILL_RATIO
    )
    return compact_numeric_fragment or wide_sparse_fragment


def _table_sort_key(cand: _TableCandidate) -> Tuple[float, float]:
    return (cand.bbox[1], cand.bbox[0])


def _table_quality(cand: _TableCandidate) -> Tuple[int, int, int, int]:
    method_bonus = 100 if cand.method == "ranked" else 0
    return (
        method_bonus,
        cand.row_count * cand.col_count,
        cand.non_empty_cells,
        cand.text_len,
    )


def _table_iou(
    a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    inter_w = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    inter_h = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, (ax1 - ax0)) * max(0.0, (ay1 - ay0))
    area_b = max(0.0, (bx1 - bx0)) * max(0.0, (by1 - by0))
    union = area_a + area_b - inter
    if union <= 0.0:
        return 0.0
    return inter / union


def _table_containment_ratio(
    a: Tuple[float, float, float, float], b: Tuple[float, float, float, float]
) -> float:
    ax0, ay0, ax1, ay1 = a
    bx0, by0, bx1, by1 = b
    inter_w = max(0.0, min(ax1, bx1) - max(ax0, bx0))
    inter_h = max(0.0, min(ay1, by1) - max(ay0, by0))
    inter = inter_w * inter_h
    if inter <= 0.0:
        return 0.0
    area_a = max(0.0, (ax1 - ax0)) * max(0.0, (ay1 - ay0))
    area_b = max(0.0, (bx1 - bx0)) * max(0.0, (by1 - by0))
    smaller = min(area_a, area_b)
    if smaller <= 0.0:
        return 0.0
    return inter / smaller


def _prune_charts_overlapping_ranked_tables(
    charts: List[Candidate], tables: List[Candidate]
) -> Tuple[List[Candidate], int]:
    ranked_tables_by_page: Dict[int, List[Candidate]] = {}
    table_overlap_candidates_by_page: Dict[int, List[Candidate]] = {}
    for table in tables:
        if table.kind != "table":
            continue
        method = _s((table.meta or {}).get("method")).strip().lower()
        if method != "ranked":
            if _table_candidate_looks_like_chart_shadow(table):
                continue
            table_overlap_candidates_by_page.setdefault(int(table.page), []).append(table)
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
    meta = chart.meta or {}
    text_lines = int(meta.get("text_lines") or 0)
    text_chars = int(meta.get("text_chars") or 0)
    text_ratio = float(meta.get("text_ratio") or 0.0)
    return (
        text_lines >= 16
        and text_chars >= 240
        and text_ratio >= 0.1
    ) or text_lines >= 40


def _table_candidate_looks_like_chart_shadow(table: Candidate) -> bool:
    if table.kind != "table":
        return False
    meta = table.meta or {}
    method = _s(meta.get("method")).strip().lower()
    rows = int(meta.get("rows") or 0)
    cols = int(meta.get("cols") or 0)
    numeric_ratio = float(meta.get("numeric_ratio") or 0.0)
    avg_words_per_cell = float(meta.get("avg_words_per_cell") or 0.0)
    area_frac = float(meta.get("area_frac") or 0.0)
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
        if not should_prune and (total_overlap / table_area) >= TABLE_CHART_SHADOW_TOTAL_OVERLAP_RATIO:
            should_prune = True
        if should_prune:
            pruned += 1
            continue
        kept.append(table)
    return kept, pruned


def _prefer_inner_lattice_table(
    smaller: _TableCandidate, larger: _TableCandidate
) -> bool:
    if smaller.method != "lattice" or larger.method != "stream":
        return False
    sx0, sy0, sx1, sy1 = smaller.bbox
    lx0, ly0, lx1, ly1 = larger.bbox
    smaller_width = max(1.0, sx1 - sx0)
    smaller_height = max(1.0, sy1 - sy0)
    larger_width = max(1.0, lx1 - lx0)
    larger_height = max(1.0, ly1 - ly0)
    width_ratio = smaller_width / larger_width
    height_ratio = smaller_height / larger_height
    return width_ratio >= 0.7 and height_ratio >= 0.75


def _dedupe_table_candidates(
    candidates: List[_TableCandidate],
) -> List[_TableCandidate]:
    kept: List[_TableCandidate] = []
    for cand in candidates:
        replaced = False
        for idx, existing in enumerate(kept):
            iou = _table_iou(cand.bbox, existing.bbox)
            containment = _table_containment_ratio(cand.bbox, existing.bbox)
            ranked_overlap = (
                containment >= 0.8
                and ("ranked" in (cand.method, existing.method))
            )
            if iou >= TABLE_DEDUP_IOU or containment >= 0.98 or ranked_overlap:
                preferred = cand
                if containment >= 0.98:
                    area_cand = max(
                        0.0, (cand.bbox[2] - cand.bbox[0]) * (cand.bbox[3] - cand.bbox[1])
                    )
                    area_existing = max(
                        0.0,
                        (existing.bbox[2] - existing.bbox[0])
                        * (existing.bbox[3] - existing.bbox[1]),
                    )
                    smaller, larger = (
                        (cand, existing) if area_cand <= area_existing else (existing, cand)
                    )
                    if _prefer_inner_lattice_table(smaller, larger):
                        preferred = smaller
                    elif _table_quality(cand) <= _table_quality(existing):
                        preferred = existing
                elif _table_quality(cand) <= _table_quality(existing):
                    preferred = existing
                kept[idx] = preferred
                replaced = True
                break
        if not replaced:
            kept.append(cand)
    return kept


def _tally_reason(stats: Dict[str, object], reason: str) -> None:
    reasons = stats.get("reasons")
    if not isinstance(reasons, dict):
        reasons = {}
        stats["reasons"] = reasons
    reasons[reason] = int(reasons.get(reason, 0)) + 1


def _suppress_pdfminer_warnings() -> None:
    """Force pdfminer loggers to ERROR to avoid noisy color warnings."""
    for name in _PDFMINER_LOGGERS:
        try:
            logging.getLogger(name).setLevel(logging.ERROR)
        except (OSError, ValueError):
            continue


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
            sum(len(FINAL_CHART_YEAR_RX.findall(line)) for line in lines[: min(12, len(lines))])
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
            )
            adjusted += 1
            try:
                text = page.get_text("text", clip=fitz.Rect(candidate.bbox))
            except PDF_FIGURE_EXCEPTIONS:
                pass
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


def _plan_candidate_pages(
    triage_doc: fitz.Document,
    excluded_pages: set[int],
) -> _CandidatePagePlan:
    requested_pages = [
        index for index in range(len(triage_doc)) if index not in excluded_pages
    ]
    triaged_pages: list[int] = []
    triaged_full_scan_pages = 0
    for index in requested_pages:
        try:
            if is_full_page_scan_without_text(triage_doc[index]):
                triaged_full_scan_pages += 1
                continue
        except PDF_FIGURE_TRIAGE_EXCEPTIONS:
            pass
        triaged_pages.append(index)
    return _CandidatePagePlan(
        chart_pages=triaged_pages,
        table_pages=requested_pages,
        excluded_count=max(0, len(triage_doc) - len(requested_pages)),
        triaged_full_scan_pages=triaged_full_scan_pages,
    )


def _extract_candidate_artifacts(
    request: ExtractCandidatesRequest,
    *,
    triage_doc: Optional[fitz.Document],
    parallel_workers: int,
    page_plan: _CandidatePagePlan,
) -> _CandidateExtractionArtifacts:
    artifacts = _CandidateExtractionArtifacts(
        charts=[],
        tables=[],
        chart_stats=_initial_chart_candidate_stats(),
        table_stats=_initial_table_candidate_stats(),
    )
    if page_plan.chart_pages == [] and page_plan.table_pages == []:
        return artifacts
    thumbs = Path(request.out_dir) / request.report_name / "thumbs"
    artifacts.charts, artifacts.chart_stats = _extract_charts(
        request.pdf_path,
        thumbs.as_posix(),
        request.report_name,
        save_thumbs=False,
        doc=triage_doc if parallel_workers <= 1 else None,
        parallel_workers=parallel_workers,
        pages=page_plan.chart_pages,
    )
    artifacts.tables, artifacts.table_stats = _extract_tables(
        request.pdf_path,
        parallel_workers=parallel_workers,
        pages=page_plan.table_pages,
        doc=triage_doc if parallel_workers <= 1 else None,
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
                pass


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
            },
        )
    )
    shared_doc = (
        request.pdf_context.fitz_doc if request.pdf_context and parallel_workers <= 1 else None
    )
    triage_doc: Optional[fitz.Document] = None
    close_doc = False
    page_plan = _CandidatePagePlan(
        chart_pages=None,
        table_pages=None,
        excluded_count=0,
        triaged_full_scan_pages=0,
    )
    artifacts = _CandidateExtractionArtifacts(
        charts=[],
        tables=[],
        chart_stats=_initial_chart_candidate_stats(),
        table_stats=_initial_table_candidate_stats(),
    )
    candidates: List[Candidate] = []
    try:
        triage_doc, close_doc = _open_candidate_triage_doc(
            request.pdf_path, shared_doc
        )
        if triage_doc is not None:
            page_plan = _plan_candidate_pages(triage_doc, excluded_pages)
        artifacts = _extract_candidate_artifacts(
            request,
            triage_doc=triage_doc,
            parallel_workers=parallel_workers,
            page_plan=page_plan,
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
        candidates = artifacts.charts + artifacts.tables
    finally:
        if close_doc and triage_doc is not None:
            try:
                triage_doc.close()
            except PDF_FIGURE_EXCEPTIONS:
                pass
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
            },
        )
    )
    return ExtractCandidatesResponse(schema_version="1.0", candidates=candidates)


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
        img_dir = out_root / report_name / "assets"
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

        out_path = img_dir / f"{report_name}.png"
        best[0].save(out_path.as_posix())
        rel = Path(report_name) / "assets" / out_path.name
        return rel.as_posix(), best[2], int(best[3])
    except PDF_FIGURE_EXCEPTIONS:
        return None, None, -1
