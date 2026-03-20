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
from src.utils.logging import log_event
from src.utils.slugify import slugify

from .shared import candidate_logger, figure_logger

# BEGIN PDF CANDIDATE EXTRACTION
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
TABLE_STREAM_SPARSE_MIN_AREA = 0.6
TABLE_STREAM_SPARSE_MAX_LINES = 15
TABLE_STREAM_SPARSE_MIN_AVG_LINE_LEN = 55
TABLE_STREAM_SPARSE_MAX_NUMERIC_RATIO = 0.05
TABLE_STREAM_SPARSE_MAX_COLS = 5
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
TABLE_REFERENCE_TERMS = (
    "doi.org",
    "journal",
    "working paper",
    "oecd publishing",
    "publishing, paris",
    "vol.",
    "no.",
    "pp.",
    "ssrn",
    "mercatus",
)
TABLE_SECTION_LIST_MIN_ROWS = 8
TABLE_SECTION_LIST_MAX_COLS = 6
TABLE_SECTION_LIST_MAX_NUMERIC_RATIO = 0.15
TABLE_SECTION_LIST_MAX_AVG_WORDS_PER_CELL = 3.5
TABLE_SECTION_LIST_MIN_TEXT_BLOCK_AREA = 0.2
TABLE_SECTION_LIST_MAX_AVG_LINE_LEN = 48.0
TABLE_SECTION_LIST_MIN_SHORT_LINE_RATIO = 0.7
TABLE_SECTION_LIST_MIN_TERMINAL_NUMBER_HITS = 4
TABLE_SECTION_LIST_MAX_AREA_FRAC_WITHOUT_NUMBERS = 0.2
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
TABLE_TOP_SLACK_MAX = 8.0
TABLE_TOP_HEADER_SLACK_MAX = 12.0
TABLE_EXPLICIT_TITLE_MAX_GAP = 72.0
TABLE_EXPLICIT_SUBTITLE_MAX_GAP = 32.0
NOTE_LABEL_PREFIXES = ("note:", "notes:", "source:", "sources:", "statlink")
_PAGE_NUMBER_RX = re.compile(
    r"^\s*[^0-9A-Za-z]*\d{1,4}(?:\s*[-–]\s*\d{1,4})?[^0-9A-Za-z]*\s*$"
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


def _s(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except Exception:
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


def _table_page_text_blocks(page: fitz.Page) -> List[_PageTextBlock]:
    blocks: List[_PageTextBlock] = []
    try:
        text_dict = page.get_text("dict")
    except Exception:
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
                except Exception:
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
    except Exception:
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


def _table_page_body_font_size(blocks: List[_PageTextBlock]) -> float:
    sizes = [block.max_font_size for block in blocks if block.max_font_size > 0.0]
    if not sizes:
        return 0.0
    try:
        return float(statistics.median(sizes))
    except Exception:
        return float(sizes[0])


def _table_fragment_is_numeric(text: str) -> bool:
    compact = _table_normalize_text(text).replace(" ", "")
    if not compact:
        return False
    compact = compact.replace("*", "")
    return _cell_is_numeric(compact)


def _table_page_text_lines(page: fitz.Page) -> List[_PageTextLine]:
    try:
        text_dict = page.get_text("dict")
    except Exception:
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


def _table_text_bands(page: fitz.Page) -> List[_TableTextBand]:
    lines = sorted(
        _table_page_text_lines(page),
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
) -> fitz.Rect:
    page_rect = page.rect
    relevant_bands = [
        band
        for band in _table_text_bands(page)
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
) -> Tuple[float, float, float, float]:
    rect = fitz.Rect(*bbox)
    page_rect = page.rect
    bands = _table_text_bands(page)
    if method == "stream":
        rect = _shrink_stream_table_rect(page, rect)
    blocks = _table_page_text_blocks(page)
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


def _image_block_rects(page: fitz.Page) -> List[fitz.Rect]:
    try:
        text_dict = page.get_text("dict")
    except Exception:
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
        except Exception:
            continue
    return rects


def _collect_chart_rects(page: fitz.Page) -> List[_ChartRect]:
    rects: List[_ChartRect] = []
    for xref, *_ in page.get_images(full=True):
        try:
            image_rects = page.get_image_rects(xref)
        except Exception:
            image_rects = []
        if not image_rects:
            continue
        rects.append(_ChartRect(rect=image_rects[0], kind="xref", xref=xref))
    for rect in _image_block_rects(page):
        rects.append(_ChartRect(rect=rect, kind="block", xref=None))
    for rect, caption, cap_rect in _drawing_caption_rects(page):
        rects.append(
            _ChartRect(
                rect=rect,
                kind="draw",
                xref=None,
                caption=caption,
                caption_rect=cap_rect,
            )
        )
    for rect, caption, cap_rect in _heading_chart_rects(page):
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
    except Exception:
        return []
    page_area = max(1.0, page.rect.get_area())
    rects: List[fitz.Rect] = []
    for drawing in drawings:
        rect = drawing.get("rect")
        if rect is None:
            continue
        try:
            r = fitz.Rect(rect)
        except Exception:
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


def _drawing_caption_rects(page: fitz.Page) -> List[Tuple[fitz.Rect, str, fitz.Rect]]:
    captions = _caption_blocks(page, CHART_CAPTION_HINTS)
    if not captions:
        return []
    drawings = _drawing_rects(page)
    if not drawings:
        return []
    page_rect = page.rect
    bottom_limit = page_rect.y1 - page_rect.height * 0.1
    candidates: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for cap_rect, cap_text in captions:
        band_top = cap_rect.y1 - 2
        band_bot = min(bottom_limit, cap_rect.y1 + page_rect.height * 0.55)
        if band_bot <= band_top:
            continue
        band = fitz.Rect(page_rect.x0, band_top, page_rect.x1, band_bot)
        selected = []
        for r in drawings:
            if not r.intersects(band):
                continue
            if r.y0 < cap_rect.y0 - 4:
                continue
            if r.y1 <= cap_rect.y1:
                continue
            if _horizontal_overlap_ratio(r, cap_rect) < 0.25:
                continue
            selected.append(r)
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
    page: fitz.Page, hints: Tuple[str, ...]
) -> List[Tuple[fitz.Rect, str]]:
    rects: List[Tuple[fitz.Rect, str]] = []
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return rects
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        lines = [
            line.strip().lower() for line in str(text).splitlines() if line.strip()
        ]
        if any(any(line.startswith(hint) for hint in hints) for line in lines):
            first_line = next((line for line in lines if line), "")
            rects.append((fitz.Rect(x0, y0, x1, y1), first_line))
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


def _heading_lines(page: fitz.Page) -> List[Tuple[fitz.Rect, str]]:
    try:
        data = page.get_text("dict")
    except Exception:
        return []
    sizes = []
    lines_data = []
    for block in data.get("blocks", []):
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
    except Exception:
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
) -> bool:
    if chart_rect.y0 <= head_rect.y1:
        return False
    try:
        blocks = page.get_text("blocks")
    except Exception:
        return False
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
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


def _heading_chart_rects(page: fitz.Page) -> List[Tuple[fitz.Rect, str, fitz.Rect]]:
    headings = _heading_lines(page)
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
        if _has_intervening_paragraph(page, head_rect, merged):
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
) -> Tuple[Optional[fitz.Rect], str]:
    candidates = _caption_blocks(page, hints)
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
) -> fitz.Rect:
    pad = max(
        CHART_CAPTION_TOP_PAD_PX, cap_rect.height * CHART_CAPTION_TOP_PAD_FRAC, 0.0
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.height > rect.height * CHART_LABEL_MAX_HEIGHT_FRAC:
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
        if lines > CHART_LABEL_MAX_LINES:
            continue
        if avg_line_len > CHART_LABEL_MAX_AVG_LINE_LEN:
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
        if h_overlap >= CHART_LABEL_MIN_H_OVERLAP:
            if block.y1 <= rect.y0 and rect.y0 - block.y1 <= max_v_gap:
                expanded |= block
            elif block.y0 >= rect.y1 and block.y0 - rect.y1 <= max_v_gap:
                expanded |= block
            elif block.y0 < rect.y0 and rect.y0 - block.y0 <= max_v_gap:
                expanded |= block
            elif block.y1 > rect.y1 and block.y1 - rect.y1 <= max_v_gap:
                expanded |= block
    return expanded


def _has_internal_top_text(
    page: fitz.Page,
    rect: fitz.Rect,
    head_rect: fitz.Rect,
) -> bool:
    search = page.rect.height * CHART_HEADING_TOP_SEARCH_FRAC
    try:
        blocks = page.get_text("blocks")
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
    except Exception:
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
) -> Tuple[float, float, float, float]:
    if method not in ("stream", "lattice"):
        return bbox
    return _compose_table_bbox(page, bbox, method)


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


def _nearby_text(page: fitz.Page, rect: fitz.Rect, max_dist: float = 90) -> str:
    best = ("", 1e9)
    for x0, y0, x1, y1, text, *_ in page.get_text("blocks"):
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
) -> Tuple[List[Candidate], Dict[str, object]]:
    from .visual_candidates import extract_visual_candidates

    return extract_visual_candidates(
        pdf_path,
        thumbs_dir,
        report_name,
        save_thumbs=save_thumbs,
        doc=doc,
        parallel_workers=parallel_workers,
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
) -> Tuple[List[Candidate], Dict[str, object]]:
    from .table_candidates import extract_table_candidates

    return extract_table_candidates(
        pdf_path,
        max_candidates=max_candidates,
        parallel_workers=parallel_workers,
    )


def _find_tables_safe(page: pdfplumber.page.Page, settings: Dict[str, object]):
    try:
        return page.find_tables(table_settings=settings) or []
    except Exception:
        return []


def _build_table_candidate(
    page: pdfplumber.page.Page,
    table: pdfplumber.table.Table,
    method: str,
    fitz_page: Optional[fitz.Page] = None,
) -> Optional[_TableCandidate]:
    try:
        x0, y0, x1, y1 = map(float, table.bbox)
    except Exception:
        return None
    rows: list[list[object]] = []
    try:
        rows = table.extract() or []
    except Exception:
        rows = []
    non_empty_rows = [row for row in rows if row and any(_s(c).strip() for c in row)]
    row_count = len(non_empty_rows)
    col_count = max((len(row) for row in non_empty_rows), default=0)
    row_col_counts = _row_nonempty_counts(rows)
    col_consistency = _col_consistency(row_col_counts)
    row_len_cv = _row_len_cv(_row_text_lengths(rows))
    non_empty_cells = sum(1 for row in non_empty_rows for c in row if _s(c).strip())
    total_cells = sum(len(row) for row in non_empty_rows)
    numeric_cells = sum(
        1 for row in non_empty_rows for c in row if _cell_is_numeric(_s(c))
    )
    numeric_chars, total_chars = _numeric_char_ratio(non_empty_rows)
    numeric_ratio = numeric_chars / max(1, total_chars)
    avg_words_per_cell = _avg_words_per_cell(non_empty_rows)
    avg_first_col_words = _avg_first_col_words(non_empty_rows)
    index_page_ratio = _index_page_ratio(non_empty_rows)
    preview = _table_preview(rows)
    text = _extract_text_in_bbox(page, (x0, y0, x1, y1))
    line_count, text_chars = _text_stats(text)
    avg_line_len = (text_chars / line_count) if line_count else 0.0
    text_len = len(text.strip())
    page_area = max(1.0, float(page.width * page.height))
    width = max(1.0, x1 - x0)
    height = max(1.0, y1 - y0)
    area_frac = (width * height) / page_area
    width_frac = width / max(1.0, float(page.width))
    height_frac = height / max(1.0, float(page.height))
    aspect = width / max(1.0, height)
    text_block_area_frac = 0.0
    text_block_line_count = 0
    text_block_avg_line_len = 0.0
    caption_hint = False
    figure_context_hint = False
    wide_figure_context_hint = False
    if fitz_page is not None:
        caption_hint = _has_caption_hint(fitz_page, (x0, y0, x1, y1))
        figure_context_hint = _has_figure_context_hint(fitz_page, (x0, y0, x1, y1))
        wide_figure_context_hint = _has_figure_context_hint(
            fitz_page,
            (x0, y0, x1, y1),
            max_dist=TABLE_WIDE_FIGURE_CONTEXT_MAX_DIST,
            top_band_height=TABLE_WIDE_FIGURE_CONTEXT_TOP_BAND,
            horizontal_pad=TABLE_WIDE_FIGURE_CONTEXT_HORIZONTAL_PAD,
        )
        text_block_area_frac, text_block_line_count, text_block_avg_line_len = (
            _text_block_stats(
                fitz_page,
                (x0, y0, x1, y1),
            )
        )
    return _TableCandidate(
        bbox=(x0, y0, x1, y1),
        method=method,
        row_count=row_count,
        col_count=col_count,
        col_consistency=col_consistency,
        row_len_cv=row_len_cv,
        non_empty_cells=non_empty_cells,
        total_cells=total_cells,
        numeric_cells=numeric_cells,
        numeric_ratio=numeric_ratio,
        avg_words_per_cell=avg_words_per_cell,
        avg_first_col_words=avg_first_col_words,
        index_page_ratio=index_page_ratio,
        preview=preview[:400],
        text=text,
        text_len=text_len,
        line_count=line_count,
        avg_line_len=avg_line_len,
        text_block_area_frac=text_block_area_frac,
        text_block_line_count=text_block_line_count,
        text_block_avg_line_len=text_block_avg_line_len,
        caption_hint=caption_hint,
        figure_context_hint=figure_context_hint,
        wide_figure_context_hint=wide_figure_context_hint,
        area_frac=area_frac,
        width_frac=width_frac,
        height_frac=height_frac,
        aspect=aspect,
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
    except Exception:
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
    except Exception:
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
    page: fitz.Page, bbox: Tuple[float, float, float, float]
) -> Tuple[float, int, float]:
    rect = fitz.Rect(*bbox)
    rect_area = max(1.0, rect.get_area())
    block_area = 0.0
    line_count = 0
    total_line_len = 0
    try:
        blocks = page.get_text("blocks")
    except Exception:
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
    except Exception:
        pass
    try:
        text += " " + (page.get_text("text", clip=below) or "")
    except Exception:
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
    except Exception:
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
    except Exception:
        return False
    return _table_text_has_figure_context(full_width_text)


def _validate_table_candidate(cand: _TableCandidate) -> Tuple[bool, str]:
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
    if _reference_block_like(cand):
        return False, "reference_block"
    if _prose_box_like(cand):
        return False, "prose_box"
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
    if cand.text_block_area_frac < TABLE_SECTION_LIST_MIN_TEXT_BLOCK_AREA:
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
    return (
        cand.numeric_ratio <= TABLE_CONTENTS_MIN_NUMERIC_RATIO / 2.0
        and cand.area_frac <= TABLE_SECTION_LIST_MAX_AREA_FRAC_WITHOUT_NUMBERS
    )


def _reference_block_like(cand: _TableCandidate) -> bool:
    lowered = cand.text.lower()
    url_hits = len(re.findall(r"https?://|doi\.org|www\.", lowered))
    year_hits = len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", lowered))
    term_hits = sum(lowered.count(term) for term in TABLE_REFERENCE_TERMS)
    if cand.method != "stream":
        return False
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


def _table_quality(cand: _TableCandidate) -> Tuple[int, int, int]:
    return (cand.row_count * cand.col_count, cand.non_empty_cells, cand.text_len)


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
            if iou >= TABLE_DEDUP_IOU or containment >= 0.98:
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
        except Exception:
            continue


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
    thumbs = Path(request.out_dir) / request.report_name / "thumbs"
    charts, chart_stats = _extract_charts(
        request.pdf_path,
        thumbs.as_posix(),
        request.report_name,
        save_thumbs=False,
        doc=request.pdf_context.fitz_doc
        if request.pdf_context and parallel_workers <= 1
        else None,
        parallel_workers=parallel_workers,
    )
    tables, table_stats = _extract_tables(
        request.pdf_path,
        parallel_workers=parallel_workers,
    )
    candidates = charts + tables
    excluded_count = 0
    if excluded_pages:
        before_count = len(candidates)
        candidates = [
            candidate
            for candidate in candidates
            if int(candidate.page) not in excluded_pages
        ]
        excluded_count = max(0, before_count - len(candidates))
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
                "chart_stats": chart_stats,
                "table_stats": table_stats,
                "excluded_count": excluded_count,
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
    except Exception:
        return None, None, -1
