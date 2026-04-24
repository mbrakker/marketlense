"""Table candidate heuristics.

This module owns PDF candidate heuristics shared by internal extraction capabilities.
It is not a public service boundary; callers enter through pdf_service.
"""

from __future__ import annotations

# ruff: noqa: F401,F841
import io
import logging
import math
import os
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pdfplumber
import pymupdf as fitz
from PIL import Image

from src.contracts.candidates import Candidate
from src.utils.candidate_features import candidate_features
from src.utils.errors import AppError
from src.utils.path_utils import safe_path_segment

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


_PDFMINER_LOGGERS = (
    "pdfminer",
    "pdfminer.pdfinterp",
    "pdfminer.cmapdb",
    "pdfminer.layout",
)


CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph", "source")


TABLE_CAPTION_HINTS = CAPTION_HINTS + ("table",)


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


TABLE_EXPAND_MAX_GAP_FRAC = 0.12


TABLE_EXPAND_HEADING_MAX_LINES = 2


TABLE_EXPAND_HEADING_MAX_AVG_LINE_LEN = 120


TABLE_EXPAND_HEADING_MIN_ALPHA_RATIO = 0.55


TABLE_EXPAND_HEADING_MAX_SENTENCES = 2


TABLE_EXPAND_MIN_H_OVERLAP = 0.2


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


TABLE_TOP_SLACK_MAX = 8.0


TABLE_TOP_HEADER_SLACK_MAX = 12.0


TABLE_EXPLICIT_TITLE_MAX_GAP = 72.0


TABLE_EXPLICIT_SUBTITLE_MAX_GAP = 32.0


NOTE_LABEL_PREFIXES = ("note:", "notes:", "source:", "sources:", "statlink")


EMAIL_ADDRESS_RX = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


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
    text_dict: Optional[dict[str, Any]] = None,
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
    rank_blocks = [block for block in blocks if _table_rank_value(block) is not None]
    if not rank_blocks:
        return []
    x_tol = max(42.0, page_rect.width * TABLE_RANKED_X_CLUSTER_GAP_FRAC)
    max_gap_y = max(32.0, page_rect.height * TABLE_RANKED_MAX_ROW_GAP_FRAC)
    grouped: List[List[_PageTextBlock]] = []
    for block in sorted(rank_blocks, key=lambda item: (item.rect.x0, item.rect.y0)):
        placed = False
        for group in grouped:
            ref = group[0]
            if (
                abs(block.rect.x0 - ref.rect.x0) <= x_tol
                and abs(block.rect.x1 - ref.rect.x1) <= x_tol
            ):
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
        and _horizontal_overlap_ratio(
            block.rect, fitz.Rect(x0, header_rule.y0, x1, row_bottom)
        )
        >= 0.2
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
        sum(1 for block in header_blocks if _table_normalize_text(block.text)),
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
    blocks = (
        page_text_blocks
        if page_text_blocks is not None
        else _table_page_text_blocks(page)
    )
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
        non_empty_cells = max(
            TABLE_MIN_NONEMPTY_CELLS, region.row_count * region.col_count
        )
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
            area_frac=((x1 - x0) * (y1 - y0))
            / max(1.0, page_rect.width * page_rect.height),
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
    text_dict: Optional[dict[str, Any]] = None,
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
            if (
                not parts
                or min_x is None
                or min_y is None
                or max_x is None
                or max_y is None
            ):
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
    text_dict: Optional[dict[str, Any]] = None,
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
    font_large = body_font_size > 0.0 and band.max_font_size >= body_font_size + 0.75
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
        if (
            _horizontal_overlap_ratio(band.rect, rect) < 0.35
            and abs(band.rect.x0 - rect.x0) > 36
        ):
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
        band for band in relevant_bands if _table_band_is_row_like(band, page_rect)
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

    best_index = max(
        range(len(clusters)), key=lambda idx: _cluster_score(clusters[idx])
    )
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
    if (
        block.rect.y0 <= page_rect.y0 + page_rect.height * 0.045
        and len(text_normalized) <= 18
    ):
        return True
    if (
        block.rect.y1 >= page_rect.y1 - page_rect.height * 0.03
        and len(text_normalized) <= 96
    ):
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
        if (
            band.numeric_fragment_count
            < TABLE_STREAM_CONTINUATION_MIN_NUMERIC_FRAGMENTS
        ):
            return False
    return True


def _table_block_is_note_like(block: _PageTextBlock) -> bool:
    normalized = _table_normalize_text(block.text)
    lowered = normalized.lower()
    if not normalized:
        return False
    if _table_text_has_note_marker(block.text):
        return True
    if (
        "statlink" in lowered
        or "doi.org" in lowered
        or "http://" in lowered
        or "https://" in lowered
    ):
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
    font_large = body_font_size > 0.0 and block.max_font_size >= body_font_size + 0.75
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
    if (
        _horizontal_overlap_ratio(block.rect, rect)
        < TABLE_NOTE_CONTINUATION_MIN_H_OVERLAP
    ):
        return False
    if block.rect.x0 > rect.x0 + TABLE_NOTE_CONTINUATION_MAX_X_OFFSET:
        return False
    if (
        len(_table_normalize_text(block.text).split())
        < TABLE_NOTE_CONTINUATION_MIN_WORDS
    ):
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
    if (
        _horizontal_overlap_ratio(band.rect, rect)
        < TABLE_NOTE_CONTINUATION_MIN_H_OVERLAP
    ):
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
        if (
            _horizontal_overlap_ratio(block.rect, rect) < 0.35
            and abs(block.rect.x0 - rect.x0) > 36
        ):
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
        if _table_block_is_heading_like(
            block, body_font_size
        ) or _table_block_is_body_paragraph(block, body_font_size):
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
            and _table_normalize_text(block.text)
            .lower()
            .startswith(("table ", "exhibit "))
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
        if _table_block_is_heading_like(
            block, body_font_size
        ) or _table_block_is_body_paragraph(block, body_font_size):
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
            tail for tail in candidates if tail.rect.y0 >= block.rect.y1 - 1.0
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
    expanded = _table_attach_explicit_title_context(expanded, blocks, body_font_size)
    expanded = _table_extend_overlapping_note_blocks(
        page, expanded, blocks, body_font_size
    )
    if method == "stream":
        expanded = _table_clamp_top_to_internal_title_band(
            expanded, bands, body_font_size
        )
        expanded = _table_clamp_top_to_internal_title(expanded, blocks, body_font_size)
        expanded = _table_clamp_bottom_before_internal_heading(
            expanded, blocks, body_font_size
        )
        expanded = _table_restore_top_slack(page, expanded, blocks, body_font_size)

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


def _candidate_index_from_id(candidate_id: str) -> int:
    try:
        return int(str(candidate_id).rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return 0


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
        if len(line) <= 42
        and any(char.isalpha() for char in line)
        and line == line.upper()
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
            ranked_overlap = containment >= 0.8 and (
                "ranked" in (cand.method, existing.method)
            )
            if iou >= TABLE_DEDUP_IOU or containment >= 0.98 or ranked_overlap:
                preferred = cand
                if containment >= 0.98:
                    area_cand = max(
                        0.0,
                        (cand.bbox[2] - cand.bbox[0]) * (cand.bbox[3] - cand.bbox[1]),
                    )
                    area_existing = max(
                        0.0,
                        (existing.bbox[2] - existing.bbox[0])
                        * (existing.bbox[3] - existing.bbox[1]),
                    )
                    smaller, larger = (
                        (cand, existing)
                        if area_cand <= area_existing
                        else (existing, cand)
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
