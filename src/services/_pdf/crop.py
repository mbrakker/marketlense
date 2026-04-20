from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Iterable, List, Optional, Tuple

import pymupdf as fitz
from PIL import Image

from src.contracts.report_assets import (
    CropRefineBBoxApplyRequest,
    CropRefineBBoxApplyResponse,
    CropRefinePageRenderRequest,
    CropRefinePageRenderResponse,
    CropRequest,
    CropResponse,
    PreviewRequest,
    PreviewResponse,
)
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.path_utils import safe_path_segment
from src.utils.slugify import slugify

from .figures import (
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
    _clamp_top_to_caption,
    _clamp_top_to_heading,
    _clamp_bottom_to_note,
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
from .shared import crop_logger, preview_logger

PDF_CROP_EXCEPTIONS = (RuntimeError, ValueError, TypeError, AttributeError, OSError)
PREVIEW_RENDER_EXCEPTIONS = (AppError,) + PDF_CROP_EXCEPTIONS

# BEGIN PDF CROPPING
CROP_TRIM_MAX_FRAC = 0.08
CROP_TRIM_MIN_PX = 12
CROP_TRIM_KEEP_PX = 8
CROP_TRIM_TOLERANCE = 8
CROP_TRIM_MIN_BG_FRAC = 0.9995
CROP_TRIM_SAMPLES = 60
CROP_STRICT_EDGE_TOUCH_TOL = 1.0
CROP_STRICT_EDGE_MIN_OVERLAP = 0.2
CROP_STRICT_EDGE_TRIM_OVERLAP_RATIO = 0.25
CROP_STRICT_EDGE_TRIM_MARGIN = 1.0
CROP_REFINE_EDGE_MAX_TRIM_FRAC = 0.035
CROP_REFINE_EDGE_MAX_TRIM_PX = 24.0
CROP_FILENAME_ID_MAX_LEN = 96
TABLE_CONTINUATION_MIN_WIDTH_FRAC = 0.82
TABLE_CONTINUATION_MIN_HEIGHT_FRAC = 0.3
TABLE_CONTINUATION_MAX_EDGE_DRIFT_FRAC = 0.08
TABLE_CONTINUATION_MAX_START_Y_FRAC = 0.18
TABLE_CONTINUATION_MIN_END_Y_FRAC = 0.5
TABLE_CONTINUATION_TITLE_PAD = 4.0
TABLE_CONTINUATION_NOTE_PAD = 2.0
TABLE_CONTINUATION_BLOCK_GAP = 24.0
TABLE_CONTINUATION_HEADER_TOKEN_MIN_SHARED = 3
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
_EXPLICIT_TABLE_TITLE_PREFIXES = ("table ", "exhibit ")
_NOTE_LABEL_PREFIXES = ("note:", "notes:", "source:", "sources:", "statlink")
_FOOTNOTE_LINE_RX = re.compile(r"^\s*(?:\*+|\d+\.)\s+")
_HEADER_TOKEN_RX = re.compile(r"[A-Za-z][A-Za-z-]{4,}")


@dataclass(frozen=True)
class _ResolvedCropRegion:
    index: int
    item: CropItem
    rect: fitz.Rect
    filename: str


@dataclass(frozen=True)
class _TableContinuationAugment:
    prepend_page: Optional[int] = None
    prepend_rect: Optional[fitz.Rect] = None
    append_page: Optional[int] = None
    append_rect: Optional[fitz.Rect] = None


def _dominant_border_color(img: Image.Image, box: int = 4) -> tuple[int, int, int]:
    width, height = img.size
    corners = [
        (0, 0),
        (max(0, width - box), 0),
        (0, max(0, height - box)),
        (max(0, width - box), max(0, height - box)),
    ]
    colors: List[tuple[int, int, int]] = []
    for x0, y0 in corners:
        for y in range(y0, min(height, y0 + box)):
            for x in range(x0, min(width, x0 + box)):
                colors.append(img.getpixel((x, y)))
    if not colors:
        return img.getpixel((0, 0))
    counts: dict[tuple[int, int, int], int] = {}
    for color in colors:
        counts[color] = counts.get(color, 0) + 1
    return max(counts, key=lambda color: counts[color])


def _row_is_bg(img: Image.Image, y: int, bg: tuple[int, int, int], tol: int) -> bool:
    width, _ = img.size
    step = 1
    samples = 0
    match = 0
    for x in range(0, width, step):
        samples += 1
        px = img.getpixel((x, y))
        if all(abs(px[i] - bg[i]) <= tol for i in range(3)):
            match += 1
    return (match / max(1, samples)) >= CROP_TRIM_MIN_BG_FRAC


def _col_is_bg(img: Image.Image, x: int, bg: tuple[int, int, int], tol: int) -> bool:
    _, height = img.size
    step = 1
    samples = 0
    match = 0
    for y in range(0, height, step):
        samples += 1
        px = img.getpixel((x, y))
        if all(abs(px[i] - bg[i]) <= tol for i in range(3)):
            match += 1
    return (match / max(1, samples)) >= CROP_TRIM_MIN_BG_FRAC


def _trim_uniform_border(
    img: Image.Image,
    allow_top: bool = True,
    allow_bottom: bool = True,
    allow_left: bool = True,
    allow_right: bool = True,
) -> Image.Image:
    width, height = img.size
    if width == 0 or height == 0:
        return img
    bg = _dominant_border_color(img)
    max_trim_y = int(height * CROP_TRIM_MAX_FRAC)
    max_trim_x = int(width * CROP_TRIM_MAX_FRAC)

    top = 0
    while allow_top and top < max_trim_y and _row_is_bg(img, top, bg, CROP_TRIM_TOLERANCE):
        top += 1
    bottom = 0
    while allow_bottom and bottom < max_trim_y and _row_is_bg(img, height - 1 - bottom, bg, CROP_TRIM_TOLERANCE):
        bottom += 1
    left = 0
    while allow_left and left < max_trim_x and _col_is_bg(img, left, bg, CROP_TRIM_TOLERANCE):
        left += 1
    right = 0
    while allow_right and right < max_trim_x and _col_is_bg(img, width - 1 - right, bg, CROP_TRIM_TOLERANCE):
        right += 1

    if top < CROP_TRIM_MIN_PX:
        top = 0
    if bottom < CROP_TRIM_MIN_PX:
        bottom = 0
    if left < CROP_TRIM_MIN_PX:
        left = 0
    if right < CROP_TRIM_MIN_PX:
        right = 0

    if top == 0 and bottom == 0 and left == 0 and right == 0:
        return img

    top = max(0, top - CROP_TRIM_KEEP_PX)
    bottom = max(0, bottom - CROP_TRIM_KEEP_PX)
    left = max(0, left - CROP_TRIM_KEEP_PX)
    right = max(0, right - CROP_TRIM_KEEP_PX)

    new_left = left
    new_top = top
    new_right = max(new_left + 1, width - right)
    new_bottom = max(new_top + 1, height - bottom)
    return img.crop((new_left, new_top, new_right, new_bottom))


def _uniform_border_trim_amounts(
    img: Image.Image,
    *,
    allow_top: bool = True,
    allow_bottom: bool = True,
    allow_left: bool = True,
    allow_right: bool = True,
) -> tuple[int, int, int, int]:
    width, height = img.size
    if width == 0 or height == 0:
        return (0, 0, 0, 0)
    bg = _dominant_border_color(img)
    max_trim_y = int(height * CROP_TRIM_MAX_FRAC)
    max_trim_x = int(width * CROP_TRIM_MAX_FRAC)

    top = 0
    while allow_top and top < max_trim_y and _row_is_bg(img, top, bg, CROP_TRIM_TOLERANCE):
        top += 1
    bottom = 0
    while allow_bottom and bottom < max_trim_y and _row_is_bg(img, height - 1 - bottom, bg, CROP_TRIM_TOLERANCE):
        bottom += 1
    left = 0
    while allow_left and left < max_trim_x and _col_is_bg(img, left, bg, CROP_TRIM_TOLERANCE):
        left += 1
    right = 0
    while allow_right and right < max_trim_x and _col_is_bg(img, width - 1 - right, bg, CROP_TRIM_TOLERANCE):
        right += 1
    return (top, bottom, left, right)


def _chart_has_internal_top_band(page: fitz.Page, rect: fitz.Rect) -> bool:
    top_limit = rect.y0 + min(LEGACY_CHART_TOP_BAND_MAX_GAP, rect.height * 0.2)
    center_x = rect.x0 + rect.width / 2.0
    for block in page.get_text("blocks"):
        block_rect = fitz.Rect(block[:4])
        text = _table_normalize_text(str(block[4]))
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
        if abs((block_rect.x0 + block_rect.x1) / 2.0 - center_x) > rect.width * LEGACY_CHART_TOP_BAND_CENTER_TOL_FRAC:
            continue
        return True
    return False


def _chart_has_bottom_edge_text(page: fitz.Page, rect: fitz.Rect) -> bool:
    bottom_gap = min(LEGACY_CHART_BOTTOM_EDGE_TEXT_MAX_GAP, rect.height * 0.12)
    lower_bound = rect.y0 + rect.height * 0.45
    page_center_x = page.rect.x0 + page.rect.width / 2.0
    for block in page.get_text("blocks"):
        block_rect = fitz.Rect(block[:4])
        text = _table_normalize_text(str(block[4]))
        if not text:
            continue
        if block_rect.y0 < lower_bound:
            continue
        if block_rect.y1 < rect.y1 - bottom_gap:
            continue
        if block_rect.y1 > rect.y1 + 1.0:
            continue
        if _horizontal_overlap_ratio(block_rect, rect) < LEGACY_CHART_BOTTOM_EDGE_TEXT_MIN_H_OVERLAP:
            continue
        if _is_page_number_text(text):
            block_center_x = block_rect.x0 + block_rect.width / 2.0
            near_page_bottom = block_rect.y0 >= page.rect.y1 - page.rect.height * 0.12
            near_page_left = block_rect.x0 <= page.rect.x0 + page.rect.width * 0.12
            near_page_right = block_rect.x1 >= page.rect.x1 - page.rect.width * 0.12
            near_page_center = abs(block_center_x - page_center_x) <= page.rect.width * 0.08
            if near_page_bottom and (near_page_left or near_page_right or near_page_center):
                continue
        return True
    return False


def _legacy_chart_border_trim(page: fitz.Page, rect: fitz.Rect, img: Image.Image) -> Image.Image:
    top, bottom, left, right = _uniform_border_trim_amounts(
        img,
        allow_top=True,
        allow_bottom=True,
        allow_left=True,
        allow_right=True,
    )
    extra_top_keep = 0
    if (
        top >= CROP_TRIM_MIN_PX
        and _chart_has_internal_top_band(page, rect)
    ):
        extra_top_keep = LEGACY_CHART_TOP_BAND_EXTRA_KEEP_PX
    extra_bottom_keep = 0
    if bottom >= CROP_TRIM_MIN_PX and _chart_has_bottom_edge_text(page, rect):
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


def _expand_chart_top_to_nearby_fill_rect(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
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
        if _horizontal_overlap_ratio(draw_rect, adjusted) < LEGACY_CHART_FILL_MIN_H_OVERLAP:
            continue
        if _vertical_overlap_ratio(draw_rect, adjusted) < LEGACY_CHART_FILL_MIN_V_OVERLAP:
            continue
        adjusted.y0 = min(adjusted.y0, max(page.rect.y0, draw_rect.y0 - LEGACY_CHART_FILL_TOP_EXPAND_PAD))
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


def _tighten_crop_rect_for_strict_mode(page: fitz.Page, rect: fitz.Rect, *, mode: str) -> fitz.Rect:
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
            adjusted = _clamp_bottom_to_note(page, adjusted, note_bottom, page_rect) & page_rect

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
            if not _heading_is_internal_draw_backed_card_text(page, adjusted, head_rect):
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
    if adjusted.width < 1 or adjusted.height < 1:
        return rect & page.rect
    return adjusted


def _normalize_block_text(text: str) -> str:
    return " ".join(str(text or "").split())


def _block_lines(text: str) -> list[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _text_starts_with_explicit_table_title(text: str) -> bool:
    normalized = _normalize_block_text(text).lower()
    return normalized.startswith(_EXPLICIT_TABLE_TITLE_PREFIXES)


def _text_has_note_marker(text: str) -> bool:
    lines = _block_lines(text)
    if not lines:
        return False
    for line in lines:
        lowered = line.lower()
        if lowered.startswith(_NOTE_LABEL_PREFIXES):
            return True
        if _FOOTNOTE_LINE_RX.match(line):
            return True
    return False


def _page_text_blocks(page: fitz.Page) -> list[Tuple[fitz.Rect, str]]:
    try:
        return [
            (fitz.Rect(x0, y0, x1, y1), str(text or ""))
            for x0, y0, x1, y1, text, *_ in page.get_text("blocks")
            if text
        ]
    except PDF_CROP_EXCEPTIONS:
        return []


def _find_explicit_table_title_block(
    page: fitz.Page,
    rect: fitz.Rect,
) -> Optional[fitz.Rect]:
    search_bottom = rect.y0 + min(96.0, rect.height * 0.25)
    candidates: list[fitz.Rect] = []
    for block, text in _page_text_blocks(page):
        if block.y1 < rect.y0 - 1.0 or block.y0 > search_bottom:
            continue
        if _horizontal_overlap_ratio(block, rect) < 0.2:
            continue
        if not _text_starts_with_explicit_table_title(text):
            continue
        candidates.append(block)
    if not candidates:
        return None
    return min(candidates, key=lambda block: (block.y0, block.x0))


def _table_title_strip_rect(page: fitz.Page, rect: fitz.Rect) -> Optional[fitz.Rect]:
    title_block = _find_explicit_table_title_block(page, rect)
    if title_block is None:
        return None
    next_top = min(
        (
            block.y0
            for block, _ in _page_text_blocks(page)
            if block.y0 >= title_block.y1 - 1.0
            and block.y0 <= rect.y0 + min(140.0, rect.height * 0.35)
            and _horizontal_overlap_ratio(block, rect) >= 0.2
        ),
        default=None,
    )
    strip_top = max(rect.y0, title_block.y0 - TABLE_CONTINUATION_TITLE_PAD)
    strip_bottom = title_block.y1 + TABLE_CONTINUATION_TITLE_PAD
    if next_top is not None:
        strip_bottom = min(rect.y1, next_top - 2.0)
    else:
        strip_bottom = min(rect.y1, strip_bottom)
    if strip_bottom <= strip_top + 1.0:
        return None
    return fitz.Rect(rect.x0, strip_top, rect.x1, strip_bottom)


def _table_note_strip_rect(page: fitz.Page, rect: fitz.Rect) -> Optional[fitz.Rect]:
    blocks = sorted(_page_text_blocks(page), key=lambda item: (item[0].y0, item[0].x0))
    lower_band = rect.y0 + rect.height * 0.45
    start_index: Optional[int] = None
    for idx, (block, text) in enumerate(blocks):
        if block.y1 < rect.y0 - 1.0 or block.y0 > rect.y1 + 1.0:
            continue
        if block.y0 < lower_band:
            continue
        if _horizontal_overlap_ratio(block, rect) < 0.2:
            continue
        if _text_has_note_marker(text):
            start_index = idx
            break
    if start_index is None:
        return None
    strip = fitz.Rect(blocks[start_index][0])
    current_bottom = strip.y1
    for block, text in blocks[start_index + 1 :]:
        if block.y0 - current_bottom > TABLE_CONTINUATION_BLOCK_GAP:
            break
        if _horizontal_overlap_ratio(block, rect) < 0.2:
            continue
        if not _text_has_note_marker(text):
            break
        strip |= block
        current_bottom = strip.y1
    strip_top = max(rect.y0, strip.y0 - TABLE_CONTINUATION_NOTE_PAD)
    strip_bottom = min(rect.y1, strip.y1 + TABLE_CONTINUATION_NOTE_PAD)
    if strip_bottom <= strip_top + 1.0:
        return None
    return fitz.Rect(rect.x0, strip_top, rect.x1, strip_bottom)


def _table_header_tokens(page: fitz.Page, rect: fitz.Rect) -> set[str]:
    title_block = _find_explicit_table_title_block(page, rect)
    max_y = rect.y0 + min(140.0, rect.height * 0.35)
    tokens: set[str] = set()
    for block, text in _page_text_blocks(page):
        if block.y1 < rect.y0 - 1.0 or block.y0 > max_y:
            continue
        if _horizontal_overlap_ratio(block, rect) < 0.2:
            continue
        if title_block is not None and block == title_block:
            continue
        normalized = _normalize_block_text(text).lower()
        for token in _HEADER_TOKEN_RX.findall(normalized):
            if token not in {"table", "exhibit"}:
                tokens.add(token)
    return tokens


def _is_wide_table_continuation_region(page_rect: fitz.Rect, rect: fitz.Rect) -> bool:
    if rect.width / max(page_rect.width, 1.0) < TABLE_CONTINUATION_MIN_WIDTH_FRAC:
        return False
    if rect.height / max(page_rect.height, 1.0) < TABLE_CONTINUATION_MIN_HEIGHT_FRAC:
        return False
    if rect.x0 > page_rect.width * TABLE_CONTINUATION_MAX_EDGE_DRIFT_FRAC:
        return False
    if page_rect.x1 - rect.x1 > page_rect.width * TABLE_CONTINUATION_MAX_EDGE_DRIFT_FRAC:
        return False
    return True


def _stack_crop_images(images: list[Image.Image]) -> Image.Image:
    width = max(img.width for img in images)
    height = sum(img.height for img in images)
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    y = 0
    for img in images:
        x = max(0, (width - img.width) // 2)
        canvas.paste(img, (x, y))
        y += img.height
    return canvas


def _render_clip_image(page: fitz.Page, rect: fitz.Rect) -> Image.Image:
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


def _build_table_continuation_augments(
    doc: fitz.Document,
    regions: list[_ResolvedCropRegion],
) -> dict[int, _TableContinuationAugment]:
    augments: dict[int, _TableContinuationAugment] = {}
    tables = [region for region in regions if region.item.type == "table"]
    tables.sort(key=lambda region: (region.item.page, region.rect.y0, region.index))
    for prev, nxt in zip(tables, tables[1:]):
        if nxt.item.page != prev.item.page + 1:
            continue
        prev_page = doc[prev.item.page]
        next_page = doc[nxt.item.page]
        prev_page_rect = prev_page.rect
        next_page_rect = next_page.rect
        if not _is_wide_table_continuation_region(prev_page_rect, prev.rect):
            continue
        if not _is_wide_table_continuation_region(next_page_rect, nxt.rect):
            continue
        if prev.rect.y1 < prev_page_rect.height * TABLE_CONTINUATION_MIN_END_Y_FRAC:
            continue
        if nxt.rect.y0 > next_page_rect.height * TABLE_CONTINUATION_MAX_START_Y_FRAC:
            continue
        if abs(prev.rect.x0 - nxt.rect.x0) > prev_page_rect.width * TABLE_CONTINUATION_MAX_EDGE_DRIFT_FRAC:
            continue
        if abs(prev.rect.x1 - nxt.rect.x1) > prev_page_rect.width * TABLE_CONTINUATION_MAX_EDGE_DRIFT_FRAC:
            continue
        title_strip = _table_title_strip_rect(prev_page, prev.rect)
        note_strip = _table_note_strip_rect(next_page, nxt.rect)
        if title_strip is None or note_strip is None:
            continue
        if _table_title_strip_rect(next_page, nxt.rect) is not None:
            continue
        if _table_note_strip_rect(prev_page, prev.rect) is not None:
            continue
        shared_tokens = _table_header_tokens(prev_page, prev.rect) & _table_header_tokens(
            next_page, nxt.rect
        )
        if len(shared_tokens) < TABLE_CONTINUATION_HEADER_TOKEN_MIN_SHARED:
            continue
        augments[prev.index] = _TableContinuationAugment(
            append_page=nxt.item.page,
            append_rect=note_strip,
        )
        augments[nxt.index] = _TableContinuationAugment(
            prepend_page=prev.item.page,
            prepend_rect=title_strip,
        )
    return augments


def _crop_output_filename(report_name: str, item: CropItem, idx: int) -> str:
    safe_report_name = safe_path_segment(report_name, fallback="report")
    item_slug = slugify(str(item.id or ""))
    if not item_slug:
        item_slug = f"item-{idx}"
    if len(item_slug) > CROP_FILENAME_ID_MAX_LEN:
        item_slug = item_slug[:CROP_FILENAME_ID_MAX_LEN]
    return f"{safe_report_name}-{item_slug}.png"


def crop_regions(request: CropRequest, ctx: RunContext) -> CropResponse:
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_regions_start",
        module=crop_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "count": len(request.items),
            "subdir": request.subdir,
            "mode": request.mode,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    paths = _crop_regions(
        request.pdf_path,
        request.out_dir,
        request.report_name,
        request.subdir,
        request.items,
        pad=request.pad,
        mode=request.mode,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
    )
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_regions_complete",
        module=crop_logger.name,
        fields={"count": len(paths)},
    ))
    return CropResponse(schema_version="1.0", paths=paths)


def _crop_regions(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    subdir: str,
    items: Iterable[CropItem],
    pad: int = 8,
    mode: str = "legacy",
    doc: Optional[fitz.Document] = None,
) -> List[str]:
    safe_report_name = safe_path_segment(report_name, fallback="report")
    safe_subdir = safe_path_segment(subdir or "slices", fallback="slices")
    output_dir = Path(out_dir) / safe_report_name / safe_subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    items_list = list(items)
    local_doc = doc or fitz.open(pdf_path)
    try:
        regions: list[_ResolvedCropRegion] = []
        for idx, it in enumerate(items_list):
            pno = it.page
            x0, y0, x1, y1 = it.bbox
            page = local_doc[pno]
            rect = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad) & page.rect
            if mode == "chart_strict" or it.type == "chart":
                rect = _tighten_chart_crop_rect(page, rect)
            elif mode == "table_strict" or it.type == "table":
                rect = _tighten_table_crop_rect(page, rect)
            if mode in {"table_strict", "chart_strict", "figure_strict"}:
                rect = _tighten_crop_rect_for_strict_mode(
                    page,
                    rect,
                    mode=mode,
                )
            if rect.is_empty:
                continue
            regions.append(
                _ResolvedCropRegion(
                    index=idx,
                    item=it,
                    rect=rect,
                    filename=_crop_output_filename(safe_report_name, it, idx),
                )
            )

        augments = _build_table_continuation_augments(local_doc, regions)

        for region in regions:
            it = region.item
            page = local_doc[it.page]
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=region.rect, alpha=False)
            img: Optional[Image.Image] = None
            if mode == "figure_strict":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    img = _trim_uniform_border(
                        img,
                        allow_top=True,
                        allow_bottom=True,
                        allow_left=True,
                        allow_right=True,
                    )
                except PDF_CROP_EXCEPTIONS:
                    img = None
            elif mode == "table_strict":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    img = _trim_uniform_border(
                        img,
                        allow_top=False,
                        allow_bottom=True,
                        allow_left=True,
                        allow_right=True,
                    )
                except PDF_CROP_EXCEPTIONS:
                    img = None
            elif mode == "chart_strict" or it.type == "chart":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    if mode == "chart_strict":
                        img = _trim_uniform_border(
                            img,
                            allow_top=True,
                            allow_bottom=True,
                            allow_left=True,
                            allow_right=True,
                        )
                    else:
                        img = _legacy_chart_border_trim(page, region.rect, img)
                except PDF_CROP_EXCEPTIONS:
                    img = None

            augment = augments.get(region.index)
            if it.type == "table" and augment is not None:
                try:
                    base_img = img or Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    stack: list[Image.Image] = []
                    if augment.prepend_page is not None and augment.prepend_rect is not None:
                        stack.append(
                            _render_clip_image(local_doc[augment.prepend_page], augment.prepend_rect)
                        )
                    stack.append(base_img)
                    if augment.append_page is not None and augment.append_rect is not None:
                        stack.append(
                            _render_clip_image(local_doc[augment.append_page], augment.append_rect)
                        )
                    img = _stack_crop_images(stack)
                except PDF_CROP_EXCEPTIONS:
                    img = img or Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

            filename = region.filename
            op = output_dir / filename
            if img is not None:
                img.save(op.as_posix())
            else:
                pix.save(op.as_posix())
            rel = Path(safe_report_name) / safe_subdir / filename
            paths.append(rel.as_posix())
    finally:
        if doc is None:
            local_doc.close()
    return paths


def render_page_for_crop_refine(request: CropRefinePageRenderRequest, ctx: RunContext) -> CropRefinePageRenderResponse:
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_refine_page_render_start",
        module=crop_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "report_name": request.report_name,
            "page": request.page,
            "dpi": request.dpi,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    local_doc = request.pdf_context.fitz_doc if request.pdf_context else None
    owns_doc = local_doc is None
    if local_doc is None:
        local_doc = fitz.open(request.pdf_path)
    try:
        if request.page < 0 or request.page >= local_doc.page_count:
            raise AppError(
                code="crop_refine_page_out_of_range",
                message=f"Crop refine page out of range: {request.page}",
                retryable=False,
                context={"page_count": local_doc.page_count},
            )
        page = local_doc[request.page]
        zoom = max(float(request.dpi), 72.0) / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        safe_report_name = safe_path_segment(request.report_name, fallback="report")
        out_dir = Path(request.out_dir) / safe_report_name / "crop_refine_pages"
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"page-{request.page}.png"
        abs_path = out_dir / filename
        pix.save(abs_path.as_posix())
        rel = (Path(safe_report_name) / "crop_refine_pages" / filename).as_posix()
        page_width = float(page.rect.width)
        page_height = float(page.rect.height)
        scale_x = (float(pix.width) / page_width) if page_width > 0 else 0.0
        scale_y = (float(pix.height) / page_height) if page_height > 0 else 0.0
        response = CropRefinePageRenderResponse(
            schema_version="1.0",
            image_path=rel,
            page=request.page,
            image_width=int(pix.width),
            image_height=int(pix.height),
            page_width=page_width,
            page_height=page_height,
            scale_x=scale_x,
            scale_y=scale_y,
        )
    finally:
        if owns_doc and local_doc is not None:
            local_doc.close()
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_refine_page_render_complete",
        module=crop_logger.name,
        fields={
            "page": response.page,
            "image_path": response.image_path,
            "image_width": response.image_width,
            "image_height": response.image_height,
        },
    ))
    return response


def apply_crop_refine_bbox(request: CropRefineBBoxApplyRequest, ctx: RunContext) -> CropRefineBBoxApplyResponse:
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_refine_bbox_apply_start",
        module=crop_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "page": request.page,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    local_doc = request.pdf_context.fitz_doc if request.pdf_context else None
    owns_doc = local_doc is None
    if local_doc is None:
        local_doc = fitz.open(request.pdf_path)
    try:
        if request.page < 0 or request.page >= local_doc.page_count:
            raise AppError(
                code="crop_refine_page_out_of_range",
                message=f"Crop refine page out of range: {request.page}",
                retryable=False,
                context={"page_count": local_doc.page_count},
            )
        page = local_doc[request.page]
        x0, y0, x1, y1 = request.bbox
        input_rect = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
        rect = input_rect & page.rect
        if rect.is_empty:
            rect = page.rect
        rect = _crop_refine_edge_guard_rect(page, rect)
        if rect.width < 1:
            rect = fitz.Rect(rect.x0, rect.y0, min(page.rect.x1, rect.x0 + 1), rect.y1)
        if rect.height < 1:
            rect = fitz.Rect(rect.x0, rect.y0, rect.x1, min(page.rect.y1, rect.y0 + 1))
        response = CropRefineBBoxApplyResponse(
            schema_version="1.0",
            page=request.page,
            bbox=(float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)),
        )
    finally:
        if owns_doc and local_doc is not None:
            local_doc.close()
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_refine_bbox_apply_complete",
        module=crop_logger.name,
        fields={
            "page": response.page,
            "bbox": response.bbox,
            "input_bbox": (float(input_rect.x0), float(input_rect.y0), float(input_rect.x1), float(input_rect.y1)),
        },
    ))
    return response


def _crop_refine_text_blocks(page: fitz.Page) -> list[fitz.Rect]:
    blocks: list[fitz.Rect] = []
    try:
        raw_blocks = page.get_text("blocks")
    except PDF_CROP_EXCEPTIONS:
        return blocks
    for x0, y0, x1, y1, text, *_ in raw_blocks:
        text_str = str(text or "").strip()
        if not text_str:
            continue
        if _is_page_number_text(text_str):
            continue
        blocks.append(fitz.Rect(float(x0), float(y0), float(x1), float(y1)))
    return blocks


def _crop_refine_edge_guard_rect(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    page_rect = page.rect
    pad_x = min(max(page_rect.width * CROP_REFINE_BBOX_PAD_X_FRAC, CROP_REFINE_BBOX_PAD_MIN), CROP_REFINE_BBOX_PAD_MAX)
    pad_y = min(max(page_rect.height * CROP_REFINE_BBOX_PAD_Y_FRAC, CROP_REFINE_BBOX_PAD_MIN), CROP_REFINE_BBOX_PAD_MAX)
    adjusted = fitz.Rect(rect.x0 - pad_x, rect.y0 - pad_y, rect.x1 + pad_x, rect.y1 + pad_y) & page_rect
    blocks = _crop_refine_text_blocks(page)
    if not blocks:
        return adjusted

    def _edge_cross(block: fitz.Rect, target: fitz.Rect) -> tuple[bool, bool, bool, bool]:
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
        crosses_left, crosses_right, crosses_top, crosses_bottom = _edge_cross(block, adjusted)
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
    max_trim_x = min(CROP_REFINE_EDGE_MAX_TRIM_PX, adjusted.width * CROP_REFINE_EDGE_MAX_TRIM_FRAC)
    max_trim_y = min(CROP_REFINE_EDGE_MAX_TRIM_PX, adjusted.height * CROP_REFINE_EDGE_MAX_TRIM_FRAC)
    for block in blocks:
        inter = adjusted & block
        if inter.is_empty:
            continue
        overlap_ratio = inter.get_area() / max(block.get_area(), 1.0)
        if overlap_ratio > CROP_REFINE_EDGE_TRIM_OVERLAP_RATIO:
            continue
        crosses_left, crosses_right, crosses_top, crosses_bottom = _edge_cross(block, adjusted)
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


# BEGIN PDF PREVIEW
def render_preview(request: PreviewRequest, ctx: RunContext) -> PreviewResponse:
    preview_logger.info(log_event(
        ctx,
        role="service",
        event="preview_render_start",
        module=preview_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "dpi": request.dpi,
            "page_number": request.page_number,
            "variant": request.variant,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    try:
        img_path = _page_png(
            request.pdf_path,
            request.out_dir,
            request.report_name,
            page_number=max(request.page_number, 0),
            dpi=request.dpi,
            variant=request.variant,
            doc=request.pdf_context.fitz_doc if request.pdf_context else None,
        )
    except PREVIEW_RENDER_EXCEPTIONS as exc:
        preview_logger.info(log_event(
            ctx,
            role="service",
            event="preview_render_failed",
            module=preview_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "page_number": request.page_number,
                "error": str(exc),
            },
        ))
        img_path = None
    preview_logger.info(log_event(
        ctx,
        role="service",
        event="preview_render_complete",
        module=preview_logger.name,
        fields={"image_path": img_path or "", "page_number": request.page_number},
    ))
    return PreviewResponse(schema_version="1.1", image_path=img_path, page_number=max(request.page_number, 0))


def _page_png(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    page_number: int = 0,
    dpi: int = 144,
    variant: str | None = None,
    doc: Optional[fitz.Document] = None,
) -> Optional[str]:
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    safe_report_name = safe_path_segment(report_name, fallback="report")
    img_dir = out_root / safe_report_name / "assets"
    img_dir.mkdir(parents=True, exist_ok=True)

    variant_slug = slugify(variant) if variant else ""
    suffix = f"-{variant_slug}" if variant_slug else ""
    abs_png = img_dir / f"{safe_report_name}{suffix}.png"

    local_doc = doc or fitz.open(pdf_path)
    try:
        if local_doc.page_count == 0 or page_number >= local_doc.page_count:
            return None
        page = local_doc.load_page(page_number)
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(abs_png.as_posix())
    finally:
        if doc is None:
            local_doc.close()

    rel_png = Path(safe_report_name) / "assets" / abs_png.name
    return rel_png.as_posix()
