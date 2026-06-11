"""Deterministic text and signal interpretation for PDF panel candidates."""

from __future__ import annotations

# ruff: noqa: E402,F401,F403,F405,F821

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, TypeAlias

import pymupdf as fitz

from ..visual_heuristics import *
from .chart_layout import *

if TYPE_CHECKING:
    from ..visual_heuristics import (
        CHART_CAPTION_HINTS,
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
        EMAIL_ADDRESS_RX,
        INFO_HEADING_MIN_ALPHA_RATIO,
        PAGE_FOOTER_BANNER_LINE_RX,
        PANEL_CHART_CONNECT_GAP_FRAC,
        PANEL_CHART_INTERNAL_CAPTION_MAX_AVG_LINE_LEN,
        PANEL_CHART_INTERNAL_CAPTION_MAX_CHARS,
        PANEL_CHART_INTERNAL_CAPTION_MAX_LINES,
        PANEL_CHART_INTERNAL_CAPTION_MIN_WIDTH_RATIO,
        PANEL_CHART_INTERNAL_CAPTION_TOP_GAP_MAX,
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
        _PANEL_TITLE_EXCLUDE_RX,
    )

    _ChartRect: TypeAlias = Any
    _PageTextLine: TypeAlias = Any
    _alpha_ratio: Any
    _horizontal_overlap_ratio: Any
    _is_page_number_text: Any
    _line_starts_with_caption_hint: Any
    _rect_containment_ratio: Any
    _rect_iou: Any
    _rect_overlap_area: Any
    _rect_seen: Any
    _s: Any
    _starts_with_lower_alpha: Any
    _table_normalize_text: Any
    _table_page_text_lines: Any
    _text_stats: Any
    _vertical_overlap_ratio: Any

    def _drawing_rects(page: fitz.Page) -> List[fitz.Rect]: ...

    def _caption_blocks(
        page: fitz.Page,
        hints: Tuple[str, ...],
        *,
        blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
    ) -> List[Tuple[fitz.Rect, str]]: ...

    def _compact_top_chart_title_like(
        text: str,
        *,
        block: fitz.Rect,
        rect: fitz.Rect,
        max_v_gap: float,
        lines: int,
        chars: int,
        avg_line_len: float,
    ) -> bool: ...

    def _chart_axis_label_band_like(
        text: str,
        *,
        lines: int,
        chars: int,
        avg_line_len: float,
    ) -> bool: ...


def _panel_title_lines(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, Any]] = None,
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
        if abs(other_center_y - line_center_y) > max(
            40.0, component_rect.height * 0.18
        ):
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
    text_dict: Optional[dict[str, Any]] = None,
) -> Optional[_PageTextLine]:
    best: Optional[_PageTextLine] = None
    best_key: tuple[float, float, float] | None = None
    top_limit = (
        component_rect.y0 + component_rect.height * PANEL_CHART_LOCAL_TITLE_TOP_FRAC
    )
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
        if (
            line.rect.height
            > component_rect.height * PANEL_CHART_LOCAL_TITLE_MAX_HEIGHT_RATIO
        ):
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
    text_dict: Optional[dict[str, Any]] = None,
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
        seen_key = (
            round(line.rect.x0, 1),
            round(line.rect.y0, 1),
            round(line.rect.x1, 1),
            round(line.rect.y1, 1),
            _s(line.text).strip(),
        )
        if seen_key in seen_keys:
            continue
        seen_keys.add(seen_key)
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
        if (
            line.rect.height
            > component_rect.height * PANEL_CHART_LOCAL_TITLE_MAX_HEIGHT_RATIO
        ):
            continue
        if line.rect.y1 > component_rect.y0 + 2.0:
            continue
        gap_above = max(0.0, component_rect.y0 - line.rect.y1)
        if gap_above > max_gap_above_px:
            continue
        width_ratio = line.rect.width / max(1.0, component_rect.width)
        center_delta = abs(((line.rect.x0 + line.rect.x1) / 2.0) - component_center_x)
        close_above = line.rect.y1 <= component_rect.y0 + 2.0 and gap_above <= min(
            24.0, max_gap_above_px * 0.4
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
        ranking_key = (
            0 if close_above else (1 if centered_above else 2),
            gap_above,
            center_delta,
            line.rect.y0,
        )
        if best_key is None or ranking_key < best_key:
            best = line
            best_key = ranking_key
    return best


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
        if (
            _numeric_token_hits(text) >= 1
            or "%" in text
            or _starts_with_lower_alpha(text)
        ):
            numeric_or_fragment_hits += 1
    if numeric_or_fragment_hits < max(1, len(sorted_titles) - 1):
        return False
    return (
        band_rect.width / max(1.0, component_rect.width)
    ) >= 0.35 and _horizontal_overlap_ratio(band_rect, component_rect) >= 0.45


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
    for index, (
        candidate_rect,
        _rects,
        _titles,
        supportive_only,
        _component_text,
    ) in enumerate(component_entries):
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
    text_dict: Optional[dict[str, Any]] = None,
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
        if (
            abs(line.max_font_size - target_line.max_font_size)
            > PANEL_CHART_TITLE_SLICE_SIZE_TOL
        ):
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
    peers = sorted(
        peers, key=lambda item: ((item.rect.x0 + item.rect.x1) / 2.0, item.rect.x0)
    )
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
    alpha_lines = [
        line
        for line in lines
        if _alpha_ratio(line) >= 0.55 and not _is_page_number_text(line)
    ]
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
        max(
            component_rect.x1,
            max(
                (block[2] for block in blocks),
                default=component_rect.x1,
            ),
        ),
        max(
            component_rect.y1,
            max(
                (block[3] for block in blocks),
                default=component_rect.y1,
            ),
        ),
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
    if (
        percent_hits == 0
        and raw_numbers
        and all(len(token) >= 4 for token in raw_numbers)
    ):
        return False
    if not any(any(ch.isalpha() for ch in line) for line in lines):
        return False
    if len(lines[0]) > 48:
        return False
    sentence_marks = text.count(".") + text.count("!") + text.count("?")
    return sentence_marks <= 2


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
    if (
        cap_rect.width / max(1.0, rect.width)
    ) < PANEL_CHART_INTERNAL_CAPTION_MIN_WIDTH_RATIO:
        return False
    if not any(ch.isalpha() for ch in normalized):
        return False
    return True


__all__ = [
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
    "_panel_caption_looks_metric_stub",
    "_panel_chart_has_compact_stat_card_signal",
    "_panel_caption_looks_top_band",
]
