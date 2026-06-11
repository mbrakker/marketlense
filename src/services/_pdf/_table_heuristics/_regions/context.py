from __future__ import annotations

from typing import List, Optional, Tuple

import pymupdf as fitz

from ..layout import (
    _cluster_is_row_continuation,
    _horizontal_overlap_ratio,
    _table_band_is_body_paragraph,
    _table_band_is_heading_like,
    _table_band_is_margin_noise,
    _table_band_is_note_continuation,
    _table_band_is_note_like,
    _table_band_is_row_like,
    _table_band_is_title_like,
    _table_block_is_body_paragraph,
    _table_block_is_heading_like,
    _table_block_is_margin_noise,
    _table_block_is_mixed_footer_cluster,
    _table_block_is_note_continuation,
    _table_block_is_note_like,
    _table_block_is_title_like,
    _table_block_looks_dense_tabular,
    _table_normalize_text,
    _table_text_bands,
    _table_text_starts_with_footnote_marker,
    _vertical_overlap_ratio,
)
from ..models import _PageTextBlock, _TableTextBand
from ..policy import (
    TABLE_EXPLICIT_SUBTITLE_MAX_GAP,
    TABLE_EXPLICIT_TITLE_MAX_GAP,
    TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_GAP_FRAC,
    TABLE_HORIZONTAL_EXPAND_MAX_GAP_FRAC,
    TABLE_HORIZONTAL_EXPAND_MIN_GAIN,
    TABLE_HORIZONTAL_EXPAND_MIN_V_OVERLAP,
    TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_V_OVERLAP,
    TABLE_OVERLAPPING_NOTE_MAX_GAP,
    TABLE_STREAM_CONTINUATION_MAX_GAP,
    TABLE_STREAM_CONTINUATION_MAX_GAP_FRAC,
)

def _table_attach_title_bands(
    page: fitz.Page,
    rect: fitz.Rect,
    bands: List[_TableTextBand],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = max(24.0, page_rect.height * 0.055)
    current_top = expanded.y0
    candidates = sorted(bands, key=lambda band: band.rect.y1, reverse=True)
    for band in candidates:
        if band.rect.y1 > current_top:
            continue
        gap = current_top - band.rect.y1
        if gap > max_gap_y:
            continue
        if _table_band_is_margin_noise(band, page_rect):
            continue
        if (
            _horizontal_overlap_ratio(band.rect, rect) < 0.35
            and abs(band.rect.x0 - rect.x0) > 36
        ):
            continue
        if not _table_band_is_title_like(band, body_font_size):
            continue
        expanded |= band.rect
        current_top = band.rect.y0
    return expanded


def _table_attach_note_bands(
    page: fitz.Page,
    rect: fitz.Rect,
    bands: List[_TableTextBand],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = max(30.0, page_rect.height * 0.032)
    current_bottom = expanded.y1
    note_started = False
    note_continuation_allowed = False
    candidates = sorted(bands, key=lambda band: band.rect.y0)
    for band in candidates:
        if band.rect.y0 < current_bottom - 1:
            continue
        gap = band.rect.y0 - current_bottom
        if gap > max_gap_y:
            if note_started:
                break
            continue
        if _table_band_is_margin_noise(band, page_rect):
            continue
        h_overlap = _horizontal_overlap_ratio(band.rect, rect)
        if h_overlap < 0.2 and not _table_band_is_note_like(band):
            continue
        if _table_band_is_note_like(band):
            expanded |= band.rect
            current_bottom = band.rect.y1
            note_started = True
            note_continuation_allowed = _table_text_starts_with_footnote_marker(
                band.text
            )
            continue
        if note_continuation_allowed and _table_band_is_note_continuation(
            band, rect, body_font_size
        ):
            expanded |= band.rect
            current_bottom = band.rect.y1
            continue
        if _table_band_is_heading_like(
            band, body_font_size
        ) or _table_band_is_body_paragraph(band, body_font_size):
            break
    return expanded


def _shrink_stream_table_rect(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    bands: Optional[List[_TableTextBand]] = None,
) -> fitz.Rect:
    page_rect = page.rect
    relevant_bands = [
        band
        for band in (bands if bands is not None else _table_text_bands(page))
        if band.rect.y1 >= rect.y0
        and band.rect.y0 <= rect.y1
        and _horizontal_overlap_ratio(band.rect, rect) >= 0.2
    ]
    if not relevant_bands:
        return rect

    row_bands = [
        band for band in relevant_bands if _table_band_is_row_like(band, page_rect)
    ]
    if not row_bands:
        return rect

    row_bands = sorted(row_bands, key=lambda band: (band.rect.y0, band.rect.x0))
    gap_limit = max(18.0, page_rect.height * 0.02)
    clusters: List[List[_TableTextBand]] = []
    current: List[_TableTextBand] = []
    for band in row_bands:
        if not current:
            current = [band]
            continue
        gap = band.rect.y0 - current[-1].rect.y1
        if gap <= gap_limit:
            current.append(band)
            continue
        clusters.append(current)
        current = [band]
    if current:
        clusters.append(current)
    if not clusters:
        return rect

    def _cluster_score(cluster: List[_TableTextBand]) -> float:
        return float(
            sum(
                band.fragment_count + band.numeric_fragment_count * 3
                for band in cluster
            )
        )

    def _cluster_bounds(cluster: List[_TableTextBand]) -> Tuple[float, float]:
        return (
            min(band.rect.y0 for band in cluster),
            max(band.rect.y1 for band in cluster),
        )

    best_index = max(
        range(len(clusters)), key=lambda idx: _cluster_score(clusters[idx])
    )
    best_cluster = list(clusters[best_index])
    continuation_gap_limit = max(
        TABLE_STREAM_CONTINUATION_MAX_GAP,
        page_rect.height * TABLE_STREAM_CONTINUATION_MAX_GAP_FRAC,
    )
    cluster_top, cluster_bottom = _cluster_bounds(best_cluster)
    for cluster in clusters[best_index + 1 :]:
        next_top, next_bottom = _cluster_bounds(cluster)
        if next_top - cluster_bottom > continuation_gap_limit:
            break
        if not _cluster_is_row_continuation(cluster, rect, page_rect):
            break
        best_cluster.extend(cluster)
        cluster_bottom = next_bottom

    cluster_top, cluster_bottom = _cluster_bounds(best_cluster)
    included = [
        band
        for band in relevant_bands
        if band.rect.y0 >= cluster_top - 2.0
        and band.rect.y1 <= cluster_bottom + 2.0
        and not _table_band_is_margin_noise(band, page_rect)
    ]
    if included:
        cluster_top = min(band.rect.y0 for band in included)
        cluster_bottom = max(band.rect.y1 for band in included)
    if cluster_bottom <= cluster_top:
        return rect
    return fitz.Rect(rect.x0, cluster_top, rect.x1, cluster_bottom)


def _table_attach_title_blocks(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = max(24.0, page_rect.height * 0.055)
    current_top = expanded.y0
    candidates = sorted(blocks, key=lambda block: block.rect.y1, reverse=True)
    for block in candidates:
        if block.rect.y1 > current_top:
            continue
        gap = current_top - block.rect.y1
        if gap > max_gap_y:
            continue
        if _table_block_is_margin_noise(block, page_rect):
            continue
        if (
            _horizontal_overlap_ratio(block.rect, rect) < 0.35
            and abs(block.rect.x0 - rect.x0) > 36
        ):
            continue
        if not _table_block_is_title_like(block, body_font_size):
            continue
        expanded |= block.rect
        current_top = block.rect.y0
    return expanded


def _table_attach_note_blocks(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = max(30.0, page_rect.height * 0.032)
    current_bottom = expanded.y1
    note_started = False
    candidates = sorted(blocks, key=lambda block: block.rect.y0)
    for block in candidates:
        if block.rect.y0 < current_bottom - 1:
            continue
        gap = block.rect.y0 - current_bottom
        if gap > max_gap_y:
            if note_started:
                break
            continue
        if _table_block_is_margin_noise(block, page_rect):
            continue
        h_overlap = _horizontal_overlap_ratio(block.rect, rect)
        if h_overlap < 0.2 and not _table_block_is_note_like(block):
            continue
        if _table_block_is_note_like(block):
            expanded |= block.rect
            current_bottom = block.rect.y1
            note_started = True
            continue
        if _table_block_is_heading_like(
            block, body_font_size
        ) or _table_block_is_body_paragraph(block, body_font_size):
            break
    return expanded


def _table_attach_explicit_title_context(
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    expanded = fitz.Rect(rect)
    title_candidates = sorted(
        (
            block
            for block in blocks
            if block.rect.y1 <= rect.y0 + 1.0
            and rect.y0 - block.rect.y1 <= TABLE_EXPLICIT_TITLE_MAX_GAP
            and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
            and _table_normalize_text(block.text)
            .lower()
            .startswith(("table ", "exhibit "))
        ),
        key=lambda block: block.rect.y1,
        reverse=True,
    )
    if not title_candidates:
        return rect
    title_block = title_candidates[0]
    expanded |= title_block.rect
    current_bottom = title_block.rect.y1
    subtitle_candidates = sorted(
        (
            block
            for block in blocks
            if block.rect.y0 >= title_block.rect.y1 - 1.0
            and block.rect.y1 <= rect.y0 + 1.0
            and _horizontal_overlap_ratio(block.rect, rect) >= 0.2
            and _table_block_is_body_paragraph(block, body_font_size)
        ),
        key=lambda block: block.rect.y0,
    )
    for block in subtitle_candidates:
        if block.rect.y0 - current_bottom > TABLE_EXPLICIT_SUBTITLE_MAX_GAP:
            break
        expanded |= block.rect
        current_bottom = block.rect.y1
    return expanded


def _table_attach_mixed_footer_blocks(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = max(30.0, page_rect.height * 0.032)
    current_bottom = expanded.y1
    footer_started = False
    candidates = sorted(blocks, key=lambda block: block.rect.y0)
    for block in candidates:
        if block.rect.y0 < current_bottom - 1:
            continue
        gap = block.rect.y0 - current_bottom
        if gap > max_gap_y:
            if footer_started:
                break
            continue
        if _table_block_is_margin_noise(block, page_rect):
            continue
        if _horizontal_overlap_ratio(block.rect, rect) < 0.2:
            continue
        if _table_block_is_mixed_footer_cluster(block):
            expanded |= block.rect
            current_bottom = block.rect.y1
            footer_started = True
            continue
        if footer_started:
            break
        if _table_block_is_heading_like(
            block, body_font_size
        ) or _table_block_is_body_paragraph(block, body_font_size):
            break
    return expanded


def _table_expand_horizontal_to_content(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_x = max(18.0, page_rect.width * TABLE_HORIZONTAL_EXPAND_MAX_GAP_FRAC)
    dense_tabular_max_gap_x = max(
        max_gap_x,
        page_rect.width * TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_GAP_FRAC,
    )
    for block in blocks:
        if _table_block_is_margin_noise(block, page_rect):
            continue
        v_overlap = _vertical_overlap_ratio(block.rect, rect)
        if v_overlap < TABLE_HORIZONTAL_EXPAND_MIN_V_OVERLAP:
            continue
        dense_tabular = (
            v_overlap >= TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_V_OVERLAP
            and _table_block_looks_dense_tabular(block)
            and block.rect.x1 >= expanded.x1 - 4.0
        )
        allowed_gap_x = dense_tabular_max_gap_x if dense_tabular else max_gap_x
        if block.rect.x1 < expanded.x0 - max_gap_x:
            continue
        if block.rect.x0 > expanded.x1 + allowed_gap_x:
            continue
        left_gain = expanded.x0 - block.rect.x0
        right_gain = block.rect.x1 - expanded.x1
        if (
            block.rect.x0 < expanded.x0
            and left_gain <= allowed_gap_x
            and left_gain >= TABLE_HORIZONTAL_EXPAND_MIN_GAIN
        ):
            expanded = fitz.Rect(block.rect.x0, expanded.y0, expanded.x1, expanded.y1)
        if (
            block.rect.x1 > expanded.x1
            and right_gain <= allowed_gap_x
            and right_gain >= TABLE_HORIZONTAL_EXPAND_MIN_GAIN
        ):
            expanded = fitz.Rect(expanded.x0, expanded.y0, block.rect.x1, expanded.y1)
    return expanded


def _table_extend_overlapping_note_blocks(
    page: fitz.Page,
    rect: fitz.Rect,
    blocks: List[_PageTextBlock],
    body_font_size: float,
) -> fitz.Rect:
    page_rect = page.rect
    expanded = fitz.Rect(rect)
    max_gap_y = TABLE_OVERLAPPING_NOTE_MAX_GAP
    note_started = False
    candidates = sorted(blocks, key=lambda block: block.rect.y0)
    for block in candidates:
        if _table_block_is_margin_noise(block, page_rect):
            continue
        if _horizontal_overlap_ratio(block.rect, rect) < 0.2:
            continue
        if block.rect.y0 > expanded.y1 + max_gap_y:
            if note_started:
                break
            continue
        if block.rect.y1 <= expanded.y1 + 1.0:
            continue
        if _table_block_is_note_like(block):
            missing_height = block.rect.y1 - expanded.y1
            if block.lines <= 1 and missing_height <= 18.0:
                continue
            expanded |= block.rect
            note_started = True
            continue
        if note_started and _table_block_is_note_continuation(
            block, rect, body_font_size
        ):
            expanded |= block.rect
            continue
        if note_started:
            break
    return expanded
