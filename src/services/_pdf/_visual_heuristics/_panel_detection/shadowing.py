from __future__ import annotations

# ruff: noqa: E402,F401,F403,F405,F821

import re
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, TypeAlias

import pymupdf as fitz

from ...visual_heuristics import *
from ..chart_layout import *
from ..panel_text import *
from ..panel_geometry import *


if TYPE_CHECKING:
    from ...visual_heuristics import (
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
    _VisualCandidateRelationships: TypeAlias = Any
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
    *,
    relationships: Optional[_VisualCandidateRelationships] = None,
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
    related_candidates = (
        relationships.candidates_in_y_range(
            ("panel",),
            rect.y0 + rect.height * 0.12,
            rect.y0 + rect.height * 0.45,
        )
        if relationships is not None
        else candidates
    )
    for other in related_candidates:
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
    *,
    relationships: Optional[_VisualCandidateRelationships] = None,
) -> bool:
    if rect_item.kind != "panel":
        return False
    caption = str(rect_item.caption or "").strip()
    if not _panel_caption_looks_like_compact_metric(caption):
        return False
    rect = rect_item.rect
    related_candidates = (
        relationships.candidates_in_y_range(
            ("heading",),
            rect.y0 - max(28.0, rect.height * 0.18),
            rect.y1,
        )
        if relationships is not None
        else candidates
    )
    for other in related_candidates:
        if other is rect_item or other.kind != "heading":
            continue
        other_caption = str(other.caption or "").strip()
        if not other_caption or _panel_caption_looks_like_compact_metric(other_caption):
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
    *,
    relationships: Optional[_VisualCandidateRelationships] = None,
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
    related_candidates = (
        relationships.candidates_in_y_range(
            ("panel",),
            rect.y1 - 4.0,
            rect.y1 + max(36.0, rect.height * 0.5),
        )
        if relationships is not None
        else candidates
    )
    for other in related_candidates:
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
        if _panel_caption_looks_like_compact_metric(other_caption):
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
    *,
    relationships: Optional[_VisualCandidateRelationships] = None,
) -> Optional[float]:
    if rect_item.kind != "panel":
        return None
    caption = str(rect_item.caption or "").strip()
    if not caption or _line_starts_with_caption_hint(caption, CHART_CAPTION_HINTS):
        return None
    rect = rect_item.rect
    compact_stat_caption = _panel_caption_looks_like_compact_metric(caption)
    candidate_y: Optional[float] = None
    related_candidates = (
        relationships.candidates_in_y_range(
            ("panel",),
            rect.y0 + 8.0,
            rect.y1 - 8.0,
        )
        if relationships is not None
        else candidates
    )
    for other in related_candidates:
        if other is rect_item or other.kind != "panel":
            continue
        other_caption = str(other.caption or "").strip()
        if other_caption and _line_starts_with_caption_hint(
            other_caption, CHART_CAPTION_HINTS
        ):
            continue
        if (
            _panel_caption_looks_like_compact_metric(other_caption)
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
    *,
    relationships: Optional[_VisualCandidateRelationships] = None,
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
    related_candidates = (
        relationships.candidates_intersecting_y(("panel",), rect)
        if relationships is not None
        else candidates
    )
    for other in related_candidates:
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
