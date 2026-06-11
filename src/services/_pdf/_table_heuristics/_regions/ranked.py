from __future__ import annotations

# ruff: noqa: F841

import re
from typing import List, Optional

import pdfplumber
import pymupdf as fitz

from ..layout import (
    _extract_text_in_bbox,
    _horizontal_overlap_ratio,
    _is_page_number_text,
    _table_block_is_body_paragraph,
    _table_block_is_margin_noise,
    _table_block_is_note_like,
    _table_normalize_text,
    _table_page_body_font_size,
    _table_page_text_blocks,
    _text_block_stats,
    _text_stats,
)
from ..models import _PageTextBlock, _RankedTableRegion, _TableCandidate
from ..policy import (
    PDF_FIGURE_EXCEPTIONS,
    TABLE_MIN_NONEMPTY_CELLS,
    TABLE_MIN_TEXT_CHARS,
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
)
from ..screening import _validate_table_candidate
from .compose import _expand_table_bbox

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
