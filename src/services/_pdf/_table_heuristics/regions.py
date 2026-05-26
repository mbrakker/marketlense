"""Table-region detection and bounding-box composition."""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

import pdfplumber
import pymupdf as fitz

# ruff: noqa: F841
__all__ = [
    "_compose_table_bbox",
    "_detect_ranked_table_candidates",
    "_expand_table_bbox",
]

from .policy import (
    PDF_FIGURE_EXCEPTIONS,
    TABLE_EXPAND_MAX_GAP_FRAC,
    TABLE_EXPAND_STREAM_WIDE_MIN_HEIGHT_FRAC,
    TABLE_EXPAND_STREAM_WIDE_MIN_WIDTH_FRAC,
    TABLE_EXPLICIT_SUBTITLE_MAX_GAP,
    TABLE_EXPLICIT_TITLE_MAX_GAP,
    TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_GAP_FRAC,
    TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_V_OVERLAP,
    TABLE_HORIZONTAL_EXPAND_MAX_GAP_FRAC,
    TABLE_HORIZONTAL_EXPAND_MIN_GAIN,
    TABLE_HORIZONTAL_EXPAND_MIN_V_OVERLAP,
    TABLE_MIN_NONEMPTY_CELLS,
    TABLE_MIN_TEXT_CHARS,
    TABLE_OVERLAPPING_NOTE_MAX_GAP,
    TABLE_RANKED_BODY_MAX_GAP,
    TABLE_RANKED_HEADER_MAX_GAP,
    TABLE_RANKED_HEADER_SEED_MAX_GAP,
    TABLE_RANKED_MAX_RANK,
    TABLE_RANKED_MAX_ROW_GAP_FRAC,
    TABLE_RANKED_MIN_ROWS,
    TABLE_RANKED_MIN_RULE_WIDTH_FRAC,
    TABLE_RANKED_NOTE_MAX_GAP,
    TABLE_RANKED_NOTE_X_TOL,
    TABLE_RANKED_RULE_X_TOL,
    TABLE_RANKED_X_CLUSTER_GAP_FRAC,
    TABLE_STREAM_CONTINUATION_MAX_GAP,
    TABLE_STREAM_CONTINUATION_MAX_GAP_FRAC,
    TABLE_TOP_HEADER_SLACK_MAX,
    TABLE_TOP_SLACK_MAX,
)
from .models import (
    _PageTextBlock,
    _RankedTableRegion,
    _TableCandidate,
    _TableTextBand,
)
from .layout import (
    _cluster_is_row_continuation,
    _extract_text_in_bbox,
    _horizontal_overlap_ratio,
    _is_page_number_text,
    _starts_with_lower_alpha,
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
    _table_page_body_font_size,
    _table_page_text_blocks,
    _table_text_bands,
    _table_text_starts_with_footnote_marker,
    _text_block_stats,
    _text_stats,
    _vertical_overlap_ratio,
)
from .screening import (
    _validate_table_candidate,
)

def _table_rank_value(block: _PageTextBlock) -> Optional[int]:
    normalized = _table_normalize_text(block.text)
    if not re.fullmatch(r"\d{1,2}", normalized):
        return None
    try:
        value = int(normalized)
    except ValueError:
        return None
    if value < 1 or value > TABLE_RANKED_MAX_RANK:
        return None
    return value

def _table_horizontal_rule_rects(page: fitz.Page) -> List[fitz.Rect]:
    rules: List[fitz.Rect] = []
    page_rect = page.rect
    min_width = page_rect.width * TABLE_RANKED_MIN_RULE_WIDTH_FRAC
    try:
        drawings = page.get_drawings() or []
    except PDF_FIGURE_EXCEPTIONS:
        drawings = []
    for drawing in drawings:
        if drawing.get("type") != "s":
            continue
        try:
            rect = fitz.Rect(drawing["rect"])
        except PDF_FIGURE_EXCEPTIONS:
            continue
        if rect.width < min_width:
            continue
        if rect.height > 3.5:
            continue
        rules.append(rect)
    return sorted(rules, key=lambda rect: (rect.y0, rect.x0))

def _group_rank_blocks_into_sequences(
    blocks: List[_PageTextBlock],
    page_rect: fitz.Rect,
) -> List[List[_PageTextBlock]]:
    rank_blocks = [block for block in blocks if _table_rank_value(block) is not None]
    if not rank_blocks:
        return []
    x_tol = max(42.0, page_rect.width * TABLE_RANKED_X_CLUSTER_GAP_FRAC)
    max_gap_y = max(32.0, page_rect.height * TABLE_RANKED_MAX_ROW_GAP_FRAC)
    grouped: List[List[_PageTextBlock]] = []
    for block in sorted(rank_blocks, key=lambda item: (item.rect.x0, item.rect.y0)):
        placed = False
        for group in grouped:
            ref = group[0]
            if (
                abs(block.rect.x0 - ref.rect.x0) <= x_tol
                and abs(block.rect.x1 - ref.rect.x1) <= x_tol
            ):
                group.append(block)
                placed = True
                break
        if not placed:
            grouped.append([block])

    sequences: List[List[_PageTextBlock]] = []
    for group in grouped:
        current: List[_PageTextBlock] = []
        expected = 1
        last_y: Optional[float] = None
        for block in sorted(group, key=lambda item: item.rect.y0):
            value = _table_rank_value(block)
            if value is None:
                continue
            if value == 1:
                current = [block]
                expected = 2
                last_y = block.rect.y0
                continue
            if not current:
                continue
            if value != expected:
                continue
            if last_y is not None and block.rect.y0 - last_y > max_gap_y:
                continue
            current.append(block)
            expected += 1
            last_y = block.rect.y0
        if len(current) >= TABLE_RANKED_MIN_ROWS:
            sequences.append(current)
    return sequences

def _ranked_table_panel_region(
    page: fitz.Page,
    rank_blocks: List[_PageTextBlock],
    blocks: List[_PageTextBlock],
    rules: List[fitz.Rect],
) -> Optional[_RankedTableRegion]:
    if not rank_blocks:
        return None
    first_rank = rank_blocks[0]
    last_rank = rank_blocks[-1]
    header_rules = [
        rule
        for rule in rules
        if rule.y0 <= first_rank.rect.y0 + 4.0
        and first_rank.rect.y0 - rule.y0 <= TABLE_RANKED_HEADER_MAX_GAP
        and rule.x0 <= first_rank.rect.x0 + TABLE_RANKED_RULE_X_TOL
    ]
    header_rule: Optional[fitz.Rect] = None
    if header_rules:
        header_rule = min(
            header_rules,
            key=lambda rule: (
                max(0.0, first_rank.rect.y0 - rule.y0),
                abs(first_rank.rect.x0 - rule.x0),
                -rule.width,
            ),
        )
    seed_rules = [
        rule
        for rule in rules
        if rule.x0 <= first_rank.rect.x0 + TABLE_RANKED_RULE_X_TOL
        and rule.y0 >= first_rank.rect.y0 - 4.0
        and rule.y0 <= last_rank.rect.y1 + TABLE_RANKED_BODY_MAX_GAP
    ]
    if header_rule is None and seed_rules:
        header_rule = min(
            seed_rules,
            key=lambda rule: (
                abs(first_rank.rect.x0 - rule.x0),
                -rule.width,
            ),
        )
    if header_rule is None:
        return None
    panel_rules = [
        rule
        for rule in rules
        if abs(rule.x0 - header_rule.x0) <= TABLE_RANKED_RULE_X_TOL
        and abs(rule.x1 - header_rule.x1) <= TABLE_RANKED_RULE_X_TOL
        and rule.y0 >= header_rule.y0 - 1.0
        and rule.y0 <= last_rank.rect.y1 + TABLE_RANKED_BODY_MAX_GAP
    ]
    if len(panel_rules) < 3:
        return None

    body_font_size = _table_page_body_font_size(blocks)
    x0 = min(rule.x0 for rule in panel_rules)
    x1 = max(rule.x1 for rule in panel_rules)
    row_top = first_rank.rect.y0
    row_bottom = last_rank.rect.y1
    content_blocks = [
        block
        for block in blocks
        if not _is_page_number_text(_table_normalize_text(block.text))
        and block.rect.y1 >= row_top - 4.0
        and block.rect.y0 <= row_bottom + 4.0
        and block.rect.x1 >= x0
        and block.rect.x0 <= x1
    ]
    if content_blocks:
        row_top = min(row_top, min(block.rect.y0 for block in content_blocks))
        row_bottom = max(row_bottom, max(block.rect.y1 for block in content_blocks))

    header_block_max_gap = (
        TABLE_RANKED_HEADER_MAX_GAP
        if header_rules
        else TABLE_RANKED_HEADER_SEED_MAX_GAP
    )
    header_blocks = [
        block
        for block in blocks
        if not _table_block_is_margin_noise(block, page.rect)
        and block.rect.y1 <= header_rule.y0 + 1.0
        and header_rule.y0 - block.rect.y1 <= header_block_max_gap
        and _horizontal_overlap_ratio(
            block.rect, fitz.Rect(x0, header_rule.y0, x1, row_bottom)
        )
        >= 0.2
    ]
    y0 = min([row_top] + [block.rect.y0 for block in header_blocks])
    if header_rules:
        y0 = min(y0, header_rule.y0)
    y1 = max(row_bottom, max(rule.y0 for rule in panel_rules))

    for block in sorted(blocks, key=lambda item: item.rect.y0):
        if _table_block_is_margin_noise(block, page.rect):
            continue
        if block.rect.y0 < y1 - 1.0:
            continue
        gap = block.rect.y0 - y1
        if gap > TABLE_RANKED_NOTE_MAX_GAP:
            break
        if block.rect.x0 < x0 - TABLE_RANKED_NOTE_X_TOL:
            continue
        if block.rect.x1 > x1 + TABLE_RANKED_NOTE_X_TOL:
            continue
        if _horizontal_overlap_ratio(block.rect, fitz.Rect(x0, y0, x1, y1)) < 0.2:
            continue
        if _table_block_is_note_like(block) or _table_block_is_body_paragraph(
            block, body_font_size
        ):
            y1 = max(y1, block.rect.y1)
            continue
        break

    header_label_count = max(
        1,
        sum(1 for block in header_blocks if _table_normalize_text(block.text)),
    )
    col_count = max(2, min(6, header_label_count + 1))
    rect = fitz.Rect(x0, y0, x1, y1) & page.rect
    if rect.is_empty:
        return None
    return _RankedTableRegion(
        bbox=(rect.x0, rect.y0, rect.x1, rect.y1),
        row_count=len(rank_blocks),
        col_count=col_count,
    )

def _detect_ranked_table_candidates(
    plumber_page: pdfplumber.page.Page,
    page: fitz.Page,
    *,
    page_text_blocks: Optional[List[_PageTextBlock]] = None,
) -> List[_TableCandidate]:
    blocks = (
        page_text_blocks
        if page_text_blocks is not None
        else _table_page_text_blocks(page)
    )
    if not blocks:
        return []
    rules = _table_horizontal_rule_rects(page)
    if not rules:
        return []
    candidates: List[_TableCandidate] = []
    page_rect = page.rect
    body_font_size = _table_page_body_font_size(blocks)
    for rank_sequence in _group_rank_blocks_into_sequences(blocks, page_rect):
        region = _ranked_table_panel_region(page, rank_sequence, blocks, rules)
        if region is None:
            continue
        expanded_bbox = _expand_table_bbox(
            page,
            region.bbox,
            "ranked",
            page_text_blocks=blocks,
        )
        x0, y0, x1, y1 = expanded_bbox
        text = _extract_text_in_bbox(plumber_page, expanded_bbox)
        text_len = len(text.strip())
        if text_len < TABLE_MIN_TEXT_CHARS:
            continue
        line_count, text_chars = _text_stats(text)
        avg_line_len = (text_chars / line_count) if line_count else 0.0
        text_block_area_frac, text_block_line_count, text_block_avg_line_len = (
            _text_block_stats(
                page,
                expanded_bbox,
                blocks=[
                    (
                        block.rect.x0,
                        block.rect.y0,
                        block.rect.x1,
                        block.rect.y1,
                        block.text,
                    )
                    for block in blocks
                ],
            )
        )
        normalized = _table_normalize_text(text)
        word_count = len(normalized.split())
        non_empty_cells = max(
            TABLE_MIN_NONEMPTY_CELLS, region.row_count * region.col_count
        )
        total_cells = non_empty_cells
        numeric_chars = sum(1 for char in text if char.isdigit())
        alpha_num_chars = sum(1 for char in text if char.isalnum())
        numeric_ratio = numeric_chars / max(1, alpha_num_chars)
        candidate = _TableCandidate(
            bbox=(x0, y0, x1, y1),
            method="ranked",
            row_count=region.row_count,
            col_count=region.col_count,
            col_consistency=1.0,
            row_len_cv=0.0,
            non_empty_cells=non_empty_cells,
            total_cells=total_cells,
            numeric_cells=min(non_empty_cells, numeric_chars),
            numeric_ratio=numeric_ratio,
            avg_words_per_cell=word_count / max(1, non_empty_cells),
            avg_first_col_words=1.0,
            index_page_ratio=0.0,
            preview=text[:400],
            text=text,
            text_len=text_len,
            line_count=line_count,
            avg_line_len=avg_line_len,
            text_block_area_frac=text_block_area_frac,
            text_block_line_count=text_block_line_count,
            text_block_avg_line_len=text_block_avg_line_len,
            caption_hint=False,
            figure_context_hint=False,
            wide_figure_context_hint=False,
            area_frac=((x1 - x0) * (y1 - y0))
            / max(1.0, page_rect.width * page_rect.height),
            width_frac=(x1 - x0) / max(1.0, page_rect.width),
            height_frac=(y1 - y0) / max(1.0, page_rect.height),
            aspect=(x1 - x0) / max(1.0, y1 - y0),
        )
        ok, _reason = _validate_table_candidate(candidate)
        if ok:
            candidates.append(candidate)
    return candidates

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
