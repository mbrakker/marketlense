from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

# ruff: noqa: F401,F403

import re
import statistics
from typing import Any, List, Optional, Tuple

import pymupdf as fitz

from ...visual_heuristics import (
    CHART_AXIS_LABEL_BAND_MAX_AVG_LINE_LEN,
    CHART_AXIS_LABEL_BAND_MAX_LINES,
    CHART_AXIS_LABEL_BAND_MIN_ALPHA_RATIO,
    CHART_AXIS_LABEL_BAND_MIN_TOKEN_HITS,
    DRAWING_BACKGROUND_MAX_STROKE,
    DRAWING_BACKGROUND_MIN_AREA_FRAC,
    DRAWING_MIN_RECT_AREA,
    DRAWING_MIN_RECT_DIM,
    PDF_FIGURE_EXCEPTIONS,
)
from ..shared import _alpha_ratio, _table_normalize_text


def _image_block_rects(
    page: fitz.Page,
    text_dict: Optional[dict[str, Any]] = None,
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


def _numeric_token_hits(text: str) -> int:
    return len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))


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


__all__ = [
    "_image_block_rects",
    "_drawing_rects",
    "_chart_axis_label_band_like",
    "_numeric_token_hits",
]
