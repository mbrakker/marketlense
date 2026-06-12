from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

# ruff: noqa: F401,F403

import re
import statistics
from typing import Any, List, Optional, Tuple

import pymupdf as fitz

from ...visual_heuristics import (
    CHART_CAPTION_HINTS,
    CHART_CAPTION_INTERNAL_TOP_TOL_FRAC,
    CHART_CAPTION_INTERNAL_TOP_TOL_PX,
    CHART_HEADING_TOP_BLOCK_H_OVERLAP,
    CHART_LABEL_COMPACT_TITLE_MAX_AVG_LINE_LEN,
    CHART_LABEL_COMPACT_TITLE_MAX_CHARS,
    CHART_LABEL_COMPACT_TITLE_MAX_LINES,
    CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN,
    CHART_LABEL_PARAGRAPH_MIN_LINES,
    CHART_NEXT_BLOCKER_GUARD_PX,
    INFO_CHART_BAND_FRAC,
    INFO_CHART_CLUSTER_GAP_FRAC,
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
    PANEL_CHART_INTERNAL_CAPTION_MAX_AVG_LINE_LEN,
    PANEL_CHART_INTERNAL_CAPTION_MAX_CHARS,
    PANEL_CHART_INTERNAL_CAPTION_MAX_LINES,
    PANEL_CHART_INTERNAL_CAPTION_MIN_WIDTH_RATIO,
    PANEL_CHART_INTERNAL_CAPTION_TOP_GAP_MAX,
    PDF_FIGURE_EXCEPTIONS,
    TABLE_CAPTION_HINTS,
)
from ..shared import (
    _alpha_ratio,
    _horizontal_overlap_ratio,
    _line_starts_with_caption_hint,
    _pad_rect,
    _rect_seen,
    _table_normalize_text,
    _text_stats,
    _vertical_overlap_ratio,
)
from .geometry import _drawing_rects


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
    if chars == 0 or chars > PANEL_CHART_INTERNAL_CAPTION_MAX_CHARS:
        return False
    avg_line_len = chars / max(1, lines)
    if avg_line_len > PANEL_CHART_INTERNAL_CAPTION_MAX_AVG_LINE_LEN:
        return False
    if rect.height <= 0:
        return False
    if (
        cap_rect.width / max(1.0, rect.width)
        < PANEL_CHART_INTERNAL_CAPTION_MIN_WIDTH_RATIO
    ):
        return False
    return cap_rect.y0 <= rect.y0 + min(
        PANEL_CHART_INTERNAL_CAPTION_TOP_GAP_MAX,
        rect.height * 0.22,
    )


def _drawing_caption_rects(
    page: fitz.Page,
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> List[Tuple[fitz.Rect, str, fitz.Rect]]:
    from .expansion import _clamp_top_to_caption, _extend_with_note_blocks

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
            if (
                next_caption_y0 is not None
                and r.y0 >= next_caption_y0 - caption_top_tol
            ):
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


def _heading_lines(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, Any]] = None,
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
    text_dict: Optional[dict[str, Any]] = None,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> List[Tuple[fitz.Rect, str, fitz.Rect]]:
    from .expansion import _clamp_top_to_caption

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


__all__ = [
    "_compact_top_chart_title_like",
    "_panel_caption_looks_top_band",
    "_drawing_caption_rects",
    "_caption_blocks",
    "_heading_lines",
    "_cluster_rects_by_y",
    "_has_intervening_paragraph",
    "_heading_chart_rects",
]
