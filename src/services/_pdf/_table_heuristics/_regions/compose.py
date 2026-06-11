from __future__ import annotations

from typing import List, Optional, Tuple

import pymupdf as fitz

from ..layout import (
    _horizontal_overlap_ratio,
    _starts_with_lower_alpha,
    _table_band_is_body_paragraph,
    _table_band_is_title_like,
    _table_block_is_body_paragraph,
    _table_block_is_heading_like,
    _table_block_is_margin_noise,
    _table_block_is_note_like,
    _table_block_is_title_like,
    _table_normalize_text,
    _table_page_body_font_size,
    _table_page_text_blocks,
    _table_text_bands,
)
from ..models import _PageTextBlock, _TableTextBand
from ..policy import (
    TABLE_EXPAND_MAX_GAP_FRAC,
    TABLE_EXPAND_STREAM_WIDE_MIN_HEIGHT_FRAC,
    TABLE_EXPAND_STREAM_WIDE_MIN_WIDTH_FRAC,
    TABLE_EXPLICIT_TITLE_MAX_GAP,
    TABLE_TOP_HEADER_SLACK_MAX,
    TABLE_TOP_SLACK_MAX,
)
from .context import (
    _shrink_stream_table_rect,
    _table_attach_explicit_title_context,
    _table_attach_mixed_footer_blocks,
    _table_attach_note_bands,
    _table_attach_note_blocks,
    _table_attach_title_bands,
    _table_attach_title_blocks,
    _table_expand_horizontal_to_content,
    _table_extend_overlapping_note_blocks,
)

def _table_restore_top_slack(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    candidates = [
        block
        for block in blocks
        if not _table_block_is_margin_noise(block, page_rect)
        and block.rect.y1 >= rect.y0 - 1.0
        and block.rect.y0 <= rect.y0 + rect.height * 0.25
        and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
    ]
    if not candidates:
        return rect
    first = min(candidates, key=lambda block: (block.rect.y0, block.rect.x0))
    normalized = _table_normalize_text(first.text).lower()
    if first.rect.y0 > rect.y0 + 2.0:
        return rect
    if normalized.startswith(("table ", "exhibit ")):
        return rect
    if _table_block_is_title_like(first, body_font_size):
        left_edge_guard = rect.x0 + rect.width * 0.18
        if first.rect.x0 <= left_edge_guard:
            return rect
    nearest_above = min(
        (
            rect.y0 - block.rect.y1
            for block in blocks
            if not _table_block_is_margin_noise(block, page_rect)
            and block.rect.y1 <= rect.y0 + 1.0
            and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
        ),
        default=None,
    )
    if nearest_above is not None and nearest_above <= 18.0:
        return rect
    slack_limit = TABLE_TOP_SLACK_MAX
    if _table_block_is_title_like(first, body_font_size):
        slack_limit = TABLE_TOP_HEADER_SLACK_MAX
    slack = min(slack_limit, rect.y0 - page_rect.y0)
    if slack <= 0.0:
        return rect
    return fitz.Rect(rect.x0, rect.y0 - slack, rect.x1, rect.y1)


def _table_clamp_top_to_internal_title_band(
    rect: fitz.Rect,
    bands: List[_TableTextBand],
    body_font_size: float,
) -> fitz.Rect:
    candidates = [
        band
        for band in bands
        if band.rect.y0 >= rect.y0 - 1.0
        and band.rect.y1 <= rect.y0 + rect.height * 0.45
        and _horizontal_overlap_ratio(band.rect, rect) >= 0.2
    ]
    if not candidates:
        return rect
    title_bands = [
        band
        for band in candidates
        if _table_band_is_title_like(band, body_font_size)
        and not _starts_with_lower_alpha(band.text)
    ]
    if not title_bands:
        return rect
    title_band = min(title_bands, key=lambda band: band.rect.y0)
    explicit_table_title_above = any(
        band is not title_band
        and band.rect.y1 <= title_band.rect.y0 + 1.0
        and _table_band_is_title_like(band, body_font_size)
        and _table_normalize_text(band.text).lower().startswith(("table ", "exhibit "))
        for band in candidates
    )
    if explicit_table_title_above:
        return rect
    paragraph_above = any(
        band.rect.y1 <= title_band.rect.y0 + 1.0
        and _table_band_is_body_paragraph(band, body_font_size)
        for band in candidates
    )
    if not paragraph_above:
        return rect
    if title_band.rect.y0 <= rect.y0 + 6.0:
        return rect
    return fitz.Rect(rect.x0, title_band.rect.y0, rect.x1, rect.y1)


def _table_clamp_top_to_internal_title(
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    explicit_title_in_top_band = any(
        block.rect.y1 >= rect.y0 - 1.0
        and block.rect.y0 <= rect.y0 + TABLE_EXPLICIT_TITLE_MAX_GAP
        and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
        and _table_normalize_text(block.text).lower().startswith(("table ", "exhibit "))
        for block in blocks
    )
    if explicit_title_in_top_band:
        return rect
    explicit_title_nearby = any(
        block.rect.y1 <= rect.y0 + 1.0
        and rect.y0 - block.rect.y1 <= TABLE_EXPLICIT_TITLE_MAX_GAP
        and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
        and _table_normalize_text(block.text).lower().startswith(("table ", "exhibit "))
        for block in blocks
    )
    if explicit_title_nearby:
        return rect
    candidates = [
        block
        for block in blocks
        if block.rect.y0 >= rect.y0 - 1.0
        and block.rect.y1 <= rect.y0 + rect.height * 0.45
        and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
    ]
    if not candidates:
        return rect
    title_blocks = [
        block
        for block in candidates
        if _table_block_is_title_like(block, body_font_size)
        and not _starts_with_lower_alpha(block.text)
    ]
    if not title_blocks:
        return rect
    title_block = min(title_blocks, key=lambda block: block.rect.y0)
    explicit_table_title_above = any(
        block is not title_block
        and block.rect.y1 <= title_block.rect.y0 + 1.0
        and _table_block_is_title_like(block, body_font_size)
        and _table_normalize_text(block.text).lower().startswith(("table ", "exhibit "))
        for block in candidates
    )
    if explicit_table_title_above:
        return rect
    paragraph_above = any(
        block.rect.y1 <= title_block.rect.y0 + 1.0
        and _table_block_is_body_paragraph(block, body_font_size)
        for block in candidates
    )
    if not paragraph_above:
        return rect
    if title_block.rect.y0 <= rect.y0 + 6.0:
        return rect
    return fitz.Rect(rect.x0, title_block.rect.y0, rect.x1, rect.y1)


def _table_clamp_bottom_before_internal_heading(
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    candidates = [
        block
        for block in blocks
        if block.rect.y0 >= rect.y0 + rect.height * 0.55
        and block.rect.y1 <= rect.y1 + 1.0
        and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
    ]
    if not candidates:
        return rect
    for block in sorted(candidates, key=lambda item: item.rect.y0):
        normalized = _table_normalize_text(block.text)
        if len(normalized.split()) > 4:
            continue
        if not _table_block_is_heading_like(block, body_font_size):
            continue
        trailing_blocks = [
            tail for tail in candidates if tail.rect.y0 >= block.rect.y1 - 1.0
        ]
        if not trailing_blocks:
            continue
        if not any(
            _table_block_is_body_paragraph(tail, body_font_size)
            or _table_block_is_note_like(tail)
            for tail in trailing_blocks
        ):
            continue
        return fitz.Rect(rect.x0, rect.y0, rect.x1, max(rect.y0, block.rect.y0 - 2.0))
    return rect


def _compose_table_bbox(
    page: fitz.Page,
    bbox: Tuple[float, float, float, float],
    method: str,
    *,
    page_text_blocks: Optional[List[_PageTextBlock]] = None,
    page_text_bands: Optional[List[_TableTextBand]] = None,
) -> Tuple[float, float, float, float]:
    rect = fitz.Rect(*bbox)
    page_rect = page.rect
    bands = page_text_bands if page_text_bands is not None else _table_text_bands(page)
    if method == "stream":
        rect = _shrink_stream_table_rect(page, rect, bands=bands)
    blocks = (
        page_text_blocks
        if page_text_blocks is not None
        else _table_page_text_blocks(page)
    )
    body_font_size = _table_page_body_font_size(blocks)
    if method == "stream" and bands:
        expanded = _table_attach_title_bands(page, rect, bands, body_font_size)
        expanded = _table_attach_explicit_title_context(
            expanded, blocks, body_font_size
        )
        expanded = _table_attach_note_bands(page, expanded, bands, body_font_size)
        expanded = _table_attach_mixed_footer_blocks(
            page, expanded, blocks, body_font_size
        )
    else:
        expanded = _table_attach_title_blocks(page, rect, blocks, body_font_size)
        expanded = _table_attach_explicit_title_context(
            expanded, blocks, body_font_size
        )
        expanded = _table_attach_note_blocks(page, expanded, blocks, body_font_size)
    expanded = _table_expand_horizontal_to_content(page, expanded, blocks)
    expanded = _table_attach_explicit_title_context(expanded, blocks, body_font_size)
    expanded = _table_extend_overlapping_note_blocks(
        page, expanded, blocks, body_font_size
    )
    if method == "stream":
        expanded = _table_clamp_top_to_internal_title_band(
            expanded, bands, body_font_size
        )
        expanded = _table_clamp_top_to_internal_title(expanded, blocks, body_font_size)
        expanded = _table_clamp_bottom_before_internal_heading(
            expanded, blocks, body_font_size
        )
        expanded = _table_restore_top_slack(page, expanded, blocks, body_font_size)

    if method == "stream":
        width_frac = expanded.width / max(1.0, page_rect.width)
        height_frac = expanded.height / max(1.0, page_rect.height)
        max_gap_x = page_rect.width * TABLE_EXPAND_MAX_GAP_FRAC
        if (
            width_frac >= TABLE_EXPAND_STREAM_WIDE_MIN_WIDTH_FRAC
            and height_frac >= TABLE_EXPAND_STREAM_WIDE_MIN_HEIGHT_FRAC
        ):
            if page_rect.x1 - expanded.x1 <= max_gap_x:
                expanded = fitz.Rect(
                    expanded.x0, expanded.y0, page_rect.x1, expanded.y1
                )
            if expanded.x0 - page_rect.x0 <= max_gap_x:
                expanded = fitz.Rect(
                    page_rect.x0, expanded.y0, expanded.x1, expanded.y1
                )

    expanded &= page_rect
    if expanded.is_empty:
        return bbox
    return (expanded.x0, expanded.y0, expanded.x1, expanded.y1)


def _expand_table_bbox(
    page: fitz.Page,
    bbox: Tuple[float, float, float, float],
    method: str,
    *,
    page_text_blocks: Optional[List[_PageTextBlock]] = None,
    page_text_bands: Optional[List[_TableTextBand]] = None,
) -> Tuple[float, float, float, float]:
    if method not in ("stream", "lattice", "ranked"):
        return bbox
    return _compose_table_bbox(
        page,
        bbox,
        method,
        page_text_blocks=page_text_blocks,
        page_text_bands=page_text_bands,
    )
