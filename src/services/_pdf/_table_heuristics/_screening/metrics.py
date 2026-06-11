from __future__ import annotations

import math
from typing import Dict, List, Tuple

import pymupdf as fitz

from ..layout import _is_page_number_text, _s, _table_text_has_figure_context
from ..policy import (
    PDF_FIGURE_EXCEPTIONS,
    TABLE_CAPTION_HINTS,
    TABLE_INDEX_MIN_FIRST_COL_WORDS,
)

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
        text += ""
    try:
        text += " " + (page.get_text("text", clip=below) or "")
    except PDF_FIGURE_EXCEPTIONS:
        text += ""
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
