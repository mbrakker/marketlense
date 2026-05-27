"""Panel candidate coordination behind the PDF visual-heuristics facade."""

from __future__ import annotations

# ruff: noqa: F401,F403

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, TypeAlias

import pymupdf as fitz

from ..visual_heuristics import *
from .chart_layout import *
from .panel_text import *
from .panel_geometry import *

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
        if (
            _panel_caption_looks_metric_stub(other_caption)
            or len(other_caption.split()) < 2
        ):
            continue
        other_rect = other.rect
        boundary_y = (
            other.caption_rect.y0 if other.caption_rect is not None else other_rect.y0
        )
        if boundary_y <= rect.y0 + 8.0 or boundary_y >= rect.y1 - 8.0:
            continue
        if (
            rect_item.caption_rect is not None
            and boundary_y <= rect_item.caption_rect.y0 + 4.0
        ):
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
            right_anchor = (
                other.caption_rect.x0
                if other.caption_rect is not None
                else other_rect.x0
            )
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


def _panel_chart_rects(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, Any]] = None,
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
        if (
            area_frac < (PANEL_CHART_MIN_AREA_FRAC * 0.8)
            or area_frac > PANEL_CHART_MAX_AREA_FRAC
        ):
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
        preferred_title = _panel_preferred_local_title_line(
            page, merged, text_dict=text_dict
        )
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
        component_entries.append(
            (merged, rects, unique_titles, supportive_only, component_text)
        )

    if component_entries:
        updated_entries: List[
            Tuple[fitz.Rect, List[fitz.Rect], List[_PageTextLine], bool, str]
        ] = []
        for component_index, (
            merged,
            rects,
            filtered,
            supportive_only,
            component_text,
        ) in enumerate(component_entries):
            if supportive_only:
                updated_entries.append(
                    (merged, rects, filtered, supportive_only, component_text)
                )
                continue
            shared_title = _shared_row_panel_title_line(
                component_index,
                component_entries,
                titles,
                page_rect=page_rect,
            )
            if shared_title is None:
                updated_entries.append(
                    (merged, rects, filtered, supportive_only, component_text)
                )
                continue
            if filtered and not (
                len(filtered) == 1 and filtered[0].rect.y0 >= merged.y0 - 2.0
            ):
                updated_entries.append(
                    (merged, rects, filtered, supportive_only, component_text)
                )
                continue
            updated_entries.append(
                (merged, rects, [shared_title], supportive_only, component_text)
            )
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
    for component_index, (
        merged,
        rects,
        filtered,
        supportive_only,
        component_text,
    ) in enumerate(component_entries):
        if not filtered and not supportive_only:
            structured_card_signal = _panel_chart_has_structured_card_signal(
                component_text
            )
            compact_stat_card_signal = _panel_chart_has_compact_stat_card_signal(
                component_text
            )
            metric_signal = _panel_chart_has_metric_signal(component_text)
            if (
                structured_card_signal
                or compact_stat_card_signal
                or (
                    metric_signal
                    and (
                        _panel_chart_has_data_signal(component_text)
                        or _panel_component_looks_like_independent_data_panel(
                            component_text
                        )
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
                if (
                    preferred_title is not None
                    and preferred_title.rect.y1 <= panel_rect.y0 + 2.0
                ):
                    panel_rect |= preferred_title.rect
                    candidates.append(
                        (
                            fitz.Rect(panel_rect),
                            preferred_title.text,
                            preferred_title.rect,
                        )
                    )
                    continue
                lead_line = None
                top_band_limit = panel_rect.y0 + min(
                    max(48.0, panel_rect.height * 0.35), 120.0
                )
                for line in _table_page_text_lines(page, text_dict=text_dict):
                    if (
                        line.rect.y0 < panel_rect.y0 - 2.0
                        or line.rect.y1 > top_band_limit
                    ):
                        continue
                    if (
                        _rect_overlap_area(line.rect, panel_rect)
                        < line.rect.get_area() * 0.65
                    ):
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
                    candidates.append(
                        (fitz.Rect(panel_rect), lead_line.text, lead_line.rect)
                    )
                else:
                    fallback_caption = ""
                    preferred_fallback = ""
                    for fallback_line in component_text.splitlines():
                        normalized = fallback_line.strip()
                        if not normalized:
                            continue
                        if not fallback_caption:
                            fallback_caption = normalized[:120]
                        if (
                            any(ch.isalpha() for ch in normalized)
                            and _numeric_token_hits(normalized) < 2
                        ):
                            preferred_fallback = normalized[:120]
                            break
                    if preferred_fallback:
                        fallback_caption = preferred_fallback
                    candidates.append(
                        (fitz.Rect(panel_rect), fallback_caption, fitz.Rect(panel_rect))
                    )
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
            allow_shared_group = (
                same_title_siblings > 0
                or not _stacked_panel_group_has_intervening_text(
                    grouped_indices,
                    component_entries,
                    blocks,
                )
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
                slice_bounds = _panel_title_slice_bounds(
                    page, title.rect, text_dict=text_dict
                )
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
        if any(
            (right - left) < min_center_gap for left, right in zip(centers, centers[1:])
        ):
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

    merged_candidates = _merge_panel_title_band_candidates(
        candidates, page_rect=page_rect
    )
    deduped: List[Tuple[fitz.Rect, str, fitz.Rect]] = []
    for rect, text, title_rect in merged_candidates:
        if not _rect_seen(rect, [existing for existing, _, _ in deduped]):
            deduped.append((rect, text, title_rect))
    return deduped


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
        for title_index, (title_rect, title_text, title_cap_rect) in enumerate(
            candidates
        ):
            if title_index == body_index or title_index in consumed:
                continue
            if title_rect.get_area() <= 0.0:
                continue
            if title_rect.y1 > body_rect.y0:
                continue
            if (
                title_rect.get_area()
                >= body_rect.get_area() * PANEL_CHART_TITLE_BAND_MERGE_MAX_AREA_RATIO
            ):
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
            if (
                _horizontal_overlap_ratio(title_rect, body_rect)
                < PANEL_CHART_TITLE_BAND_MERGE_MIN_H_OVERLAP
            ):
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


__all__ = [
    "_panel_should_clamp_to_internal_caption",
    "_panel_candidate_shadowed_by_heading_candidate",
    "_panel_candidate_shadowed_by_larger_panel",
    "_panel_stacked_bottom_clip_y",
    "_panel_neighbor_x_bounds",
    "_page_looks_like_contents_layout",
    "_panel_chart_rects",
    "_merge_panel_title_band_candidates",
]
