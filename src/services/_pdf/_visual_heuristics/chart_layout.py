from __future__ import annotations

# ruff: noqa: F401,F403

import re
import statistics
from typing import TYPE_CHECKING, Any, List, Optional, Tuple

import pymupdf as fitz

from ..visual_heuristics import *

if TYPE_CHECKING:
    from ..visual_heuristics import (
        CHART_AXIS_LABEL_BAND_MAX_AVG_LINE_LEN,
        CHART_AXIS_LABEL_BAND_MAX_LINES,
        CHART_AXIS_LABEL_BAND_MIN_ALPHA_RATIO,
        CHART_AXIS_LABEL_BAND_MIN_TOKEN_HITS,
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
        CHART_LABEL_MAX_AVG_LINE_LEN,
        CHART_LABEL_MAX_GAP_FRAC,
        CHART_LABEL_MAX_HEIGHT_FRAC,
        CHART_LABEL_MAX_LINES,
        CHART_LABEL_MAX_V_GAP_FRAC,
        CHART_LABEL_MIN_H_OVERLAP,
        CHART_LABEL_MIN_V_OVERLAP,
        CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN,
        CHART_LABEL_PARAGRAPH_MIN_LINES,
        CHART_NEXT_BLOCKER_GUARD_PX,
        CHART_NEXT_BLOCKER_MIN_GAP_FRAC,
        CHART_NEXT_BLOCKER_MIN_GAP_PX,
        CHART_NEXT_BLOCKER_MIN_H_OVERLAP,
        CHART_NOTE_BELOW_GUARD_PX,
        CHART_NOTE_BELOW_MIN_H_OVERLAP,
        CHART_NOTE_MAX_DIST,
        CHART_NOTE_MAX_GAP_X_FRAC,
        CHART_NOTE_PAD_EXTRA,
        CHART_WHITESPACE_GUARD_GAP_FRAC,
        CHART_WHITESPACE_GUARD_GAP_X_FRAC,
        CHART_WHITESPACE_MAX_PAD_FRAC,
        CHART_WHITESPACE_MAX_PAD_X_FRAC,
        CHART_WHITESPACE_MIN_OVERLAP,
        DRAWING_BACKGROUND_MAX_STROKE,
        DRAWING_BACKGROUND_MIN_AREA_FRAC,
        DRAWING_MIN_RECT_AREA,
        DRAWING_MIN_RECT_DIM,
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
        NOTE_LABEL_PREFIXES,
        PANEL_CHART_INTERNAL_CAPTION_MAX_AVG_LINE_LEN,
        PANEL_CHART_INTERNAL_CAPTION_MAX_CHARS,
        PANEL_CHART_INTERNAL_CAPTION_MAX_LINES,
        PANEL_CHART_INTERNAL_CAPTION_MIN_WIDTH_RATIO,
        PANEL_CHART_INTERNAL_CAPTION_TOP_GAP_MAX,
        PDF_FIGURE_EXCEPTIONS,
        TABLE_CAPTION_HINTS,
    )

    _alpha_ratio: Any
    _horizontal_overlap_ratio: Any
    _is_page_number_text: Any
    _line_starts_with_caption_hint: Any
    _pad_rect: Any
    _rect_intersection_area: Any
    _rect_iou: Any
    _rect_seen: Any
    _table_normalize_text: Any
    _text_stats: Any
    _vertical_overlap_ratio: Any


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


def _numeric_token_hits(text: str) -> int:
    return len(re.findall(r"\b\d+(?:\.\d+)?%?\b", text))


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
    text_dict: Optional[dict[str, Any]] = None,
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
        if (
            _horizontal_overlap_ratio(other_rect, rect)
            < CHART_NEXT_BLOCKER_MIN_H_OVERLAP
        ):
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
        if (
            _horizontal_overlap_ratio(head_rect, rect)
            < CHART_NEXT_BLOCKER_MIN_H_OVERLAP
        ):
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
        if (
            lines > CHART_LABEL_MAX_LINES
            and not compact_top_title
            and not axis_label_band
        ):
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
                    or len(re.findall(r"\b(?:19|20)\d{2}[a-z]?\b", normalized_text))
                    >= 3
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
            blocker_top - CHART_NOTE_BELOW_GUARD_PX - CHART_CROP_PAD_COMPENSATION,
        )
    if max_bottom <= rect.y0:
        return rect
    if rect.y1 > max_bottom:
        return fitz.Rect(rect.x0, rect.y0, rect.x1, max_bottom)
    if rect.y1 < max_bottom:
        return fitz.Rect(rect.x0, rect.y0, rect.x1, max_bottom)
    return rect


__all__ = [
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
