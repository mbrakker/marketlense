"""Private records used while deriving PDF table candidates."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

import pymupdf as fitz

__all__ = [
    "_PageTextBlock",
    "_PageTextLine",
    "_RankedTableRegion",
    "_TableCandidate",
    "_TableTextBand",
]


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
