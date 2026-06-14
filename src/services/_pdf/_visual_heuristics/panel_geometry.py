"""Deterministic geometry assembly and bounds adjustment for PDF panels."""

from __future__ import annotations

# ruff: noqa: E402,F401,F403,F405,F821

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

import pymupdf as fitz

from ..visual_heuristics import *
from .chart_layout import *
from .panel_text import *

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
    from .type_declarations import (
        _ChartRect,
        _PageTextLine,
        _alpha_ratio,
        _caption_blocks,
        _chart_axis_label_band_like,
        _compact_top_chart_title_like,
        _drawing_rects,
        _horizontal_overlap_ratio,
        _is_page_number_text,
        _line_starts_with_caption_hint,
        _rect_containment_ratio,
        _rect_iou,
        _rect_overlap_area,
        _rect_seen,
        _s,
        _starts_with_lower_alpha,
        _table_normalize_text,
        _table_page_text_lines,
        _text_stats,
        _vertical_overlap_ratio,
    )


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
                _numeric_token_hits(compact) >= 1 and len(compact) <= 16
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
                near_page_center = abs(
                    block_center_x - (page_rect.x0 + page_rect.width / 2.0)
                ) <= (page_rect.width * 0.08)
                if not numeric_label_like or (
                    near_page_bottom and (near_page_side or near_page_center)
                ):
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
            numeric_label_like = (
                numeric_label_like and lines <= 2 and avg_line_len <= 12.0
            )
            if _alpha_ratio(compact) < 0.45 and not numeric_label_like:
                continue
            sentence_marks = (
                compact.count(".") + compact.count("!") + compact.count("?")
            )
            if sentence_marks > 1:
                continue

            attach = False
            v_overlap = _vertical_overlap_ratio(block_rect, expanded)
            h_overlap = _horizontal_overlap_ratio(block_rect, expanded)
            if block_rect.x0 >= expanded.x1:
                attach = (
                    block_rect.x0 - expanded.x1
                ) <= max_gap_x and v_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP
            elif block_rect.x1 <= expanded.x0:
                attach = (
                    expanded.x0 - block_rect.x1
                ) <= max_gap_x and v_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP
            elif block_rect.y1 <= expanded.y0:
                attach = (
                    expanded.y0 - block_rect.y1
                ) <= max_gap_y and h_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_H_OVERLAP
            elif block_rect.y0 >= expanded.y1:
                attach = (
                    block_rect.y0 - expanded.y1
                ) <= max_gap_y and h_overlap >= PANEL_CHART_LABEL_ATTACH_MIN_H_OVERLAP
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
        for index, (
            candidate_rect,
            _,
            candidate_titles,
            _supportive_only,
            _component_text,
        ) in enumerate(component_entries):
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
                height_ratio = candidate_rect.height / max(
                    1.0, merged_group_rect.height
                )
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
        if (
            block_rect.height
            > expanded.height * PANEL_CHART_TOP_TITLE_ATTACH_MAX_HEIGHT_RATIO
        ):
            return False
        if (
            left_inset
            > expanded.width * PANEL_CHART_TOP_TITLE_ATTACH_MAX_LEFT_INSET_FRAC
            and not narrow_centered_title
        ):
            return False
        if (
            gap > max_v_gap
            and not _has_title_band_component_support(block_rect)
            and not narrow_centered_title
        ):
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
            <= active_rect.x0
            + active_rect.width * PANEL_CHART_TOP_TITLE_ATTACH_MAX_LEFT_INSET_FRAC
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
        allow_top_title_spill = (
            compact_top_title or panel_compact_top_title
        ) and _allow_top_title_spill(block)
        # Panel charts on slide decks often sit beside sibling panels; reject
        # candidate text blocks that spill too far beyond the panel's own width.
        if (
            not allow_top_title_spill
            and (
                block.x0 < active_rect.x0 - max_gap
                or block.x1 > active_rect.x1 + max_gap
            )
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
            elif (
                axis_label_band
                and block.y0 >= active_rect.y0 + active_rect.height * 0.35
            ):
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
        if not (
            compact_top_title or panel_compact_top_title
        ) or not _allow_top_title_spill(block):
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
        if (
            _vertical_overlap_ratio(component_rect, expanded)
            < PANEL_CONTEXT_CARD_MIN_V_OVERLAP
        ):
            continue
        if (
            component_rect.height
            < expanded.height * PANEL_CONTEXT_CARD_MIN_HEIGHT_RATIO
        ):
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


__all__ = [
    "_extend_panel_rect_with_nearby_label_blocks",
    "_drawing_components",
    "_shared_title_component_group",
    "_stacked_panel_group_has_intervening_text",
    "_extend_panel_rect_with_adjacent_drawings",
    "_clamp_panel_rect_to_dominant_fill_rect",
    "_extend_panel_with_adjacent_text_blocks",
]
