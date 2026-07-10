"""Geometry refinement for PDF crop rectangles.

This module owns deterministic chart/table crop adjustment and crop-refine
edge guards; it does not coordinate artifact writing or public service calls.
"""

from __future__ import annotations

from typing import Optional

import pymupdf as fitz
from PIL import Image

from src.services._pdf._crop.boundary_detectors import snap_table_rect_to_outer_rules
from src.services._pdf._crop.image_ops import (
    CROP_TRIM_KEEP_PX,
    CROP_TRIM_MIN_PX,
    PDF_CROP_EXCEPTIONS,
    _uniform_border_trim_amounts,
)
from src.services._pdf.figures import (
    CHART_CAPTION_HINTS,
    CROP_REFINE_BBOX_PAD_MAX,
    CROP_REFINE_BBOX_PAD_MIN,
    CROP_REFINE_BBOX_PAD_X_FRAC,
    CROP_REFINE_BBOX_PAD_Y_FRAC,
    CROP_REFINE_EDGE_INCLUDE_OVERLAP_RATIO,
    CROP_REFINE_EDGE_MIN_OVERLAP,
    CROP_REFINE_EDGE_TOUCH_TOL,
    CROP_REFINE_EDGE_TRIM_OVERLAP_RATIO,
    PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD,
    _clamp_bottom_to_note,
    _clamp_top_to_caption,
    _clamp_top_to_heading,
    _horizontal_overlap_ratio,
    _is_page_number_text,
    _nearest_caption_block,
    _nearest_heading_above,
    _note_block_bottom,
    _panel_caption_looks_top_band,
    _table_normalize_text,
    _text_stats,
    _trim_top_page_number,
    _vertical_overlap_ratio,
)
from src.services._pdf.page_artifacts import (
    get_crop_refine_text_block_rects,
    get_page_text_block_pairs,
)

CROP_STRICT_EDGE_TOUCH_TOL = 1.0


CROP_STRICT_EDGE_MIN_OVERLAP = 0.2


CROP_STRICT_EDGE_TRIM_OVERLAP_RATIO = 0.25


CROP_STRICT_EDGE_TRIM_MARGIN = 1.0


CROP_REFINE_EDGE_MAX_TRIM_FRAC = 0.035


CROP_REFINE_EDGE_MAX_TRIM_PX = 24.0


LEGACY_CHART_TOP_BAND_EXTRA_KEEP_PX = 16


LEGACY_CHART_TOP_BAND_MAX_GAP = 48.0


LEGACY_CHART_TOP_BAND_MIN_WIDTH_RATIO = 0.28


LEGACY_CHART_TOP_BAND_MAX_WIDTH_RATIO = 0.9


LEGACY_CHART_TOP_BAND_MAX_LINES = 3


LEGACY_CHART_TOP_BAND_MAX_CHARS = 140


LEGACY_CHART_TOP_BAND_MAX_AVG_LINE_LEN = 60.0


LEGACY_CHART_TOP_BAND_CENTER_TOL_FRAC = 0.22


LEGACY_CHART_FILL_TOP_EXPAND_MAX = 12.0


LEGACY_CHART_FILL_TOP_EXPAND_PAD = 2.0


LEGACY_CHART_FILL_MIN_H_OVERLAP = 0.8


LEGACY_CHART_FILL_MIN_V_OVERLAP = 0.7


LEGACY_CHART_BOTTOM_EDGE_TEXT_MAX_GAP = 28.0


LEGACY_CHART_BOTTOM_EDGE_TEXT_MIN_H_OVERLAP = 0.15


LEGACY_CHART_BOTTOM_EXTRA_KEEP_PX = 10


def _chart_has_internal_top_band(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    artifact_cache=None,
) -> bool:
    top_limit = rect.y0 + min(LEGACY_CHART_TOP_BAND_MAX_GAP, rect.height * 0.2)
    center_x = rect.x0 + rect.width / 2.0
    for block_rect, raw_text in get_page_text_block_pairs(
        page,
        cache=artifact_cache,
    ):
        text = _table_normalize_text(str(raw_text))
        if not text:
            continue
        if block_rect.y0 < rect.y0 - 1.0:
            continue
        if block_rect.y0 > top_limit:
            continue
        width_ratio = block_rect.width / max(1.0, rect.width)
        if width_ratio < LEGACY_CHART_TOP_BAND_MIN_WIDTH_RATIO:
            continue
        if width_ratio > LEGACY_CHART_TOP_BAND_MAX_WIDTH_RATIO:
            continue
        if _horizontal_overlap_ratio(block_rect, rect) < 0.5:
            continue
        lines, chars = _text_stats(text)
        if lines == 0 or lines > LEGACY_CHART_TOP_BAND_MAX_LINES:
            continue
        if chars > LEGACY_CHART_TOP_BAND_MAX_CHARS:
            continue
        if (chars / max(1, lines)) > LEGACY_CHART_TOP_BAND_MAX_AVG_LINE_LEN:
            continue
        if (
            abs((block_rect.x0 + block_rect.x1) / 2.0 - center_x)
            > rect.width * LEGACY_CHART_TOP_BAND_CENTER_TOL_FRAC
        ):
            continue
        return True
    return False


def _chart_has_bottom_edge_text(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    artifact_cache=None,
) -> bool:
    bottom_gap = min(LEGACY_CHART_BOTTOM_EDGE_TEXT_MAX_GAP, rect.height * 0.12)
    lower_bound = rect.y0 + rect.height * 0.45
    page_center_x = page.rect.x0 + page.rect.width / 2.0
    for block_rect, raw_text in get_page_text_block_pairs(
        page,
        cache=artifact_cache,
    ):
        text = _table_normalize_text(str(raw_text))
        if not text:
            continue
        if block_rect.y0 < lower_bound:
            continue
        if block_rect.y1 < rect.y1 - bottom_gap:
            continue
        if block_rect.y1 > rect.y1 + 1.0:
            continue
        if (
            _horizontal_overlap_ratio(block_rect, rect)
            < LEGACY_CHART_BOTTOM_EDGE_TEXT_MIN_H_OVERLAP
        ):
            continue
        if _is_page_number_text(text):
            block_center_x = block_rect.x0 + block_rect.width / 2.0
            near_page_bottom = block_rect.y0 >= page.rect.y1 - page.rect.height * 0.12
            near_page_left = block_rect.x0 <= page.rect.x0 + page.rect.width * 0.12
            near_page_right = block_rect.x1 >= page.rect.x1 - page.rect.width * 0.12
            near_page_center = (
                abs(block_center_x - page_center_x) <= page.rect.width * 0.08
            )
            if near_page_bottom and (
                near_page_left or near_page_right or near_page_center
            ):
                continue
        return True
    return False


def _legacy_chart_border_trim(
    page: fitz.Page,
    rect: fitz.Rect,
    img: Image.Image,
    *,
    artifact_cache=None,
) -> Image.Image:
    top, bottom, left, right = _uniform_border_trim_amounts(
        img,
        allow_top=True,
        allow_bottom=True,
        allow_left=True,
        allow_right=True,
    )
    extra_top_keep = 0
    if top >= CROP_TRIM_MIN_PX and _chart_has_internal_top_band(
        page, rect, artifact_cache=artifact_cache
    ):
        extra_top_keep = LEGACY_CHART_TOP_BAND_EXTRA_KEEP_PX
    extra_bottom_keep = 0
    if bottom >= CROP_TRIM_MIN_PX and _chart_has_bottom_edge_text(
        page,
        rect,
        artifact_cache=artifact_cache,
    ):
        extra_bottom_keep = LEGACY_CHART_BOTTOM_EXTRA_KEEP_PX
    if (
        top >= CROP_TRIM_MIN_PX
        and bottom >= CROP_TRIM_MIN_PX
        and left >= CROP_TRIM_MIN_PX
        and right >= CROP_TRIM_MIN_PX
    ):
        top = max(0, top - (CROP_TRIM_KEEP_PX + extra_top_keep))
        bottom = max(0, bottom - (CROP_TRIM_KEEP_PX + extra_bottom_keep))
        left = max(0, left - CROP_TRIM_KEEP_PX)
        right = max(0, right - CROP_TRIM_KEEP_PX)
        new_left = left
        new_top = top
        width, height = img.size
        new_right = max(new_left + 1, width - right)
        new_bottom = max(new_top + 1, height - bottom)
        return img.crop((new_left, new_top, new_right, new_bottom))
    if top >= CROP_TRIM_MIN_PX:
        top = max(0, top - (CROP_TRIM_KEEP_PX + extra_top_keep))
    else:
        top = 0
    left = max(0, left - CROP_TRIM_KEEP_PX) if left >= CROP_TRIM_MIN_PX else 0
    width, height = img.size
    new_left = left
    new_top = top
    new_right = width
    new_bottom = height
    return img.crop((new_left, new_top, new_right, new_bottom))


def _expand_chart_top_to_nearby_fill_rect(
    page: fitz.Page, rect: fitz.Rect
) -> fitz.Rect:
    adjusted = fitz.Rect(rect)
    for draw in page.get_drawings():
        if draw.get("type") not in {"f", "fs"}:
            continue
        draw_rect = fitz.Rect(draw["rect"])
        if draw_rect.is_empty:
            continue
        # Keep plain charts stable: only grow upward when the fill-backed card
        # genuinely starts above the current crop, not when it is already aligned.
        if draw_rect.y0 >= adjusted.y0 - 0.25:
            continue
        if adjusted.y0 - draw_rect.y0 > LEGACY_CHART_FILL_TOP_EXPAND_MAX:
            continue
        if (
            _horizontal_overlap_ratio(draw_rect, adjusted)
            < LEGACY_CHART_FILL_MIN_H_OVERLAP
        ):
            continue
        if (
            _vertical_overlap_ratio(draw_rect, adjusted)
            < LEGACY_CHART_FILL_MIN_V_OVERLAP
        ):
            continue
        adjusted.y0 = min(
            adjusted.y0,
            max(page.rect.y0, draw_rect.y0 - LEGACY_CHART_FILL_TOP_EXPAND_PAD),
        )
    return adjusted


def _heading_is_internal_draw_backed_card_text(
    page: fitz.Page,
    rect: fitz.Rect,
    head_rect: fitz.Rect,
) -> bool:
    if head_rect.is_empty:
        return False
    if head_rect.y0 > rect.y0 + rect.height * 0.45:
        return False
    for draw in page.get_drawings():
        if draw.get("type") not in {"f", "fs"}:
            continue
        draw_rect = fitz.Rect(draw["rect"])
        if draw_rect.is_empty:
            continue
        if draw_rect.y0 > rect.y0 + 20.0:
            continue
        if rect.y0 - draw_rect.y0 > (LEGACY_CHART_FILL_TOP_EXPAND_MAX + 8.0):
            continue
        if _horizontal_overlap_ratio(draw_rect, rect) < LEGACY_CHART_FILL_MIN_H_OVERLAP:
            continue
        if _vertical_overlap_ratio(draw_rect, rect) < LEGACY_CHART_FILL_MIN_V_OVERLAP:
            continue
        if _horizontal_overlap_ratio(head_rect, draw_rect) < 0.55:
            continue
        inter = head_rect & draw_rect
        if inter.is_empty:
            continue
        if inter.get_area() < head_rect.get_area() * 0.65:
            continue
        top_band_limit = draw_rect.y0 + min(max(draw_rect.height * 0.45, 48.0), 120.0)
        if head_rect.y1 > top_band_limit:
            continue
        return True
    return False


def _tighten_crop_rect_for_strict_mode(
    page: fitz.Page, rect: fitz.Rect, *, mode: str
) -> fitz.Rect:
    adjusted = fitz.Rect(rect)
    page_rect = page.rect
    blocks = _crop_refine_text_blocks(page)

    if blocks:
        for _ in range(2):
            changed = False
            for block in blocks:
                inter = adjusted & block
                if inter.is_empty:
                    continue
                overlap_ratio = inter.get_area() / max(block.get_area(), 1.0)
                if overlap_ratio > CROP_STRICT_EDGE_TRIM_OVERLAP_RATIO:
                    continue
                h_overlap = _horizontal_overlap_ratio(block, adjusted)
                crosses_bottom = (
                    block.y0 < adjusted.y1 - CROP_STRICT_EDGE_TOUCH_TOL
                    and block.y1 > adjusted.y1 + CROP_STRICT_EDGE_TOUCH_TOL
                    and h_overlap >= CROP_STRICT_EDGE_MIN_OVERLAP
                )
                if not crosses_bottom:
                    continue
                new_bottom = min(adjusted.y1, block.y0 - CROP_STRICT_EDGE_TRIM_MARGIN)
                if new_bottom > adjusted.y0 + 1:
                    adjusted.y1 = new_bottom
                    changed = True
            adjusted &= page_rect
            if not changed:
                break

    # For strict table/chart crops keep note/source/statlink lines but
    # clamp away the next prose section that often follows immediately.
    if mode in {"table_strict", "chart_strict"}:
        note_min_y0_frac = 0.25 if mode == "table_strict" else 0.35
        note_bottom = _note_block_bottom(page, adjusted, min_y0_frac=note_min_y0_frac)
        if note_bottom is not None:
            adjusted = (
                _clamp_bottom_to_note(page, adjusted, note_bottom, page_rect)
                & page_rect
            )

    if adjusted.width < 1 or adjusted.height < 1:
        return rect & page_rect
    return adjusted


def _tighten_chart_crop_rect(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    adjusted = fitz.Rect(rect) & page.rect
    if adjusted.is_empty:
        return adjusted
    page_rect = page.rect
    ref_rect: Optional[fitz.Rect] = None

    cap_rect, cap_text = _nearest_caption_block(page, adjusted, CHART_CAPTION_HINTS)
    if cap_rect is not None:
        caption_lower = str(cap_text or "").strip().lower()
        caption_has_figure_hint = any(
            caption_lower.startswith(hint) for hint in CHART_CAPTION_HINTS
        )
        panel_caption_is_top_band = _panel_caption_looks_top_band(
            cap_text or "",
            rect=adjusted,
            cap_rect=cap_rect,
        )
        panel_caption_is_internal_label = (
            cap_rect.y0 >= adjusted.y0 + 1.0
            and not caption_has_figure_hint
            and not panel_caption_is_top_band
        )
        if not panel_caption_is_internal_label:
            adjusted = _clamp_top_to_caption(
                adjusted,
                cap_rect,
                page,
                page_rect,
                extra_pad=(
                    PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD
                    if panel_caption_is_top_band
                    else 0.0
                ),
            )
        ref_rect = cap_rect
    else:
        head_rect = _nearest_heading_above(page, adjusted)
        if head_rect is not None:
            if not _heading_is_internal_draw_backed_card_text(
                page, adjusted, head_rect
            ):
                adjusted = _clamp_top_to_heading(adjusted, head_rect, page, page_rect)
                ref_rect = head_rect

    adjusted = _trim_top_page_number(adjusted, page, ref_rect) & page_rect
    if ref_rect is None:
        adjusted = _expand_chart_top_to_nearby_fill_rect(page, adjusted) & page_rect
    if adjusted.width < 1 or adjusted.height < 1:
        return rect & page_rect
    return adjusted


def _tighten_table_crop_rect(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    adjusted = fitz.Rect(rect) & page.rect
    if adjusted.is_empty:
        return adjusted
    adjusted = _trim_top_page_number(adjusted, page, None) & page.rect
    adjusted = snap_table_rect_to_outer_rules(page, adjusted) & page.rect
    if adjusted.width < 1 or adjusted.height < 1:
        return rect & page.rect
    return adjusted


def _crop_refine_text_blocks(
    page: fitz.Page, *, artifact_cache=None
) -> list[fitz.Rect]:
    try:
        return get_crop_refine_text_block_rects(
            page,
            cache=artifact_cache,
            is_page_number_text=_is_page_number_text,
        )
    except PDF_CROP_EXCEPTIONS:
        return []


def _crop_refine_edge_guard_rect(
    page: fitz.Page, rect: fitz.Rect, *, artifact_cache=None
) -> fitz.Rect:
    page_rect = page.rect
    pad_x = min(
        max(page_rect.width * CROP_REFINE_BBOX_PAD_X_FRAC, CROP_REFINE_BBOX_PAD_MIN),
        CROP_REFINE_BBOX_PAD_MAX,
    )
    pad_y = min(
        max(page_rect.height * CROP_REFINE_BBOX_PAD_Y_FRAC, CROP_REFINE_BBOX_PAD_MIN),
        CROP_REFINE_BBOX_PAD_MAX,
    )
    adjusted = (
        fitz.Rect(rect.x0 - pad_x, rect.y0 - pad_y, rect.x1 + pad_x, rect.y1 + pad_y)
        & page_rect
    )
    blocks = _crop_refine_text_blocks(page, artifact_cache=artifact_cache)
    if not blocks:
        return adjusted

    def _edge_cross(
        block: fitz.Rect, target: fitz.Rect
    ) -> tuple[bool, bool, bool, bool]:
        tol = CROP_REFINE_EDGE_TOUCH_TOL
        v_overlap = _vertical_overlap_ratio(block, target)
        h_overlap = _horizontal_overlap_ratio(block, target)
        crosses_left = (
            block.x0 < target.x0 - tol
            and block.x1 > target.x0 + tol
            and v_overlap >= CROP_REFINE_EDGE_MIN_OVERLAP
        )
        crosses_right = (
            block.x0 < target.x1 - tol
            and block.x1 > target.x1 + tol
            and v_overlap >= CROP_REFINE_EDGE_MIN_OVERLAP
        )
        crosses_top = (
            block.y0 < target.y0 - tol
            and block.y1 > target.y0 + tol
            and h_overlap >= CROP_REFINE_EDGE_MIN_OVERLAP
        )
        crosses_bottom = (
            block.y0 < target.y1 - tol
            and block.y1 > target.y1 + tol
            and h_overlap >= CROP_REFINE_EDGE_MIN_OVERLAP
        )
        return crosses_left, crosses_right, crosses_top, crosses_bottom

    # Pass 1: if a text block is meaningfully intersected, expand to include full text.
    for block in blocks:
        inter = adjusted & block
        if inter.is_empty:
            continue
        overlap_ratio = inter.get_area() / max(block.get_area(), 1.0)
        if overlap_ratio < CROP_REFINE_EDGE_INCLUDE_OVERLAP_RATIO:
            continue
        crosses_left, crosses_right, crosses_top, crosses_bottom = _edge_cross(
            block, adjusted
        )
        if crosses_left:
            adjusted.x0 = min(adjusted.x0, block.x0)
        if crosses_right:
            adjusted.x1 = max(adjusted.x1, block.x1)
        if crosses_top:
            adjusted.y0 = min(adjusted.y0, block.y0)
        if crosses_bottom:
            adjusted.y1 = max(adjusted.y1, block.y1)
    adjusted &= page_rect

    # Pass 2: if only a tiny fraction of a text block is clipped at the edge, trim it away.
    # Guardrail: never allow this cleanup pass to carve out a large share of the crop.
    max_trim_x = min(
        CROP_REFINE_EDGE_MAX_TRIM_PX, adjusted.width * CROP_REFINE_EDGE_MAX_TRIM_FRAC
    )
    max_trim_y = min(
        CROP_REFINE_EDGE_MAX_TRIM_PX, adjusted.height * CROP_REFINE_EDGE_MAX_TRIM_FRAC
    )
    for block in blocks:
        inter = adjusted & block
        if inter.is_empty:
            continue
        overlap_ratio = inter.get_area() / max(block.get_area(), 1.0)
        if overlap_ratio > CROP_REFINE_EDGE_TRIM_OVERLAP_RATIO:
            continue
        crosses_left, crosses_right, crosses_top, crosses_bottom = _edge_cross(
            block, adjusted
        )
        if crosses_left and (block.x1 - adjusted.x0) <= max_trim_x:
            adjusted.x0 = max(adjusted.x0, block.x1)
        if crosses_right and (adjusted.x1 - block.x0) <= max_trim_x:
            adjusted.x1 = min(adjusted.x1, block.x0)
        if crosses_top and (block.y1 - adjusted.y0) <= max_trim_y:
            adjusted.y0 = max(adjusted.y0, block.y1)
        if crosses_bottom and (adjusted.y1 - block.y0) <= max_trim_y:
            adjusted.y1 = min(adjusted.y1, block.y0)
    adjusted &= page_rect

    if adjusted.width < 1 or adjusted.height < 1:
        return rect & page_rect
    return adjusted


__all__ = [
    "CROP_STRICT_EDGE_TOUCH_TOL",
    "CROP_STRICT_EDGE_MIN_OVERLAP",
    "CROP_STRICT_EDGE_TRIM_OVERLAP_RATIO",
    "CROP_STRICT_EDGE_TRIM_MARGIN",
    "CROP_REFINE_EDGE_MAX_TRIM_FRAC",
    "CROP_REFINE_EDGE_MAX_TRIM_PX",
    "LEGACY_CHART_TOP_BAND_EXTRA_KEEP_PX",
    "LEGACY_CHART_TOP_BAND_MAX_GAP",
    "LEGACY_CHART_TOP_BAND_MIN_WIDTH_RATIO",
    "LEGACY_CHART_TOP_BAND_MAX_WIDTH_RATIO",
    "LEGACY_CHART_TOP_BAND_MAX_LINES",
    "LEGACY_CHART_TOP_BAND_MAX_CHARS",
    "LEGACY_CHART_TOP_BAND_MAX_AVG_LINE_LEN",
    "LEGACY_CHART_TOP_BAND_CENTER_TOL_FRAC",
    "LEGACY_CHART_FILL_TOP_EXPAND_MAX",
    "LEGACY_CHART_FILL_TOP_EXPAND_PAD",
    "LEGACY_CHART_FILL_MIN_H_OVERLAP",
    "LEGACY_CHART_FILL_MIN_V_OVERLAP",
    "LEGACY_CHART_BOTTOM_EDGE_TEXT_MAX_GAP",
    "LEGACY_CHART_BOTTOM_EDGE_TEXT_MIN_H_OVERLAP",
    "LEGACY_CHART_BOTTOM_EXTRA_KEEP_PX",
    "_chart_has_internal_top_band",
    "_chart_has_bottom_edge_text",
    "_legacy_chart_border_trim",
    "_expand_chart_top_to_nearby_fill_rect",
    "_heading_is_internal_draw_backed_card_text",
    "_tighten_crop_rect_for_strict_mode",
    "_tighten_chart_crop_rect",
    "_tighten_table_crop_rect",
    "_crop_refine_text_blocks",
    "_crop_refine_edge_guard_rect",
]
