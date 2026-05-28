"""Adjacent-page table continuation augmentation for PDF crops.

This module owns deterministic title, note, and header-token interpretation
used to stitch table crop fragments across neighboring pages.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Optional, Sequence, Tuple

import pymupdf as fitz

from src.services._pdf._crop.image_ops import PDF_CROP_EXCEPTIONS
from src.services._pdf.figures import _horizontal_overlap_ratio
from src.services._pdf.page_artifacts import get_page_text_block_pairs

TABLE_CONTINUATION_MIN_WIDTH_FRAC = 0.82


TABLE_CONTINUATION_MIN_HEIGHT_FRAC = 0.3


TABLE_CONTINUATION_MAX_EDGE_DRIFT_FRAC = 0.08


TABLE_CONTINUATION_MAX_START_Y_FRAC = 0.18


TABLE_CONTINUATION_MIN_END_Y_FRAC = 0.5


TABLE_CONTINUATION_TITLE_PAD = 4.0


TABLE_CONTINUATION_NOTE_PAD = 2.0


TABLE_CONTINUATION_BLOCK_GAP = 24.0


TABLE_CONTINUATION_HEADER_TOKEN_MIN_SHARED = 3


_EXPLICIT_TABLE_TITLE_PREFIXES = ("table ", "exhibit ")


_NOTE_LABEL_PREFIXES = ("note:", "notes:", "source:", "sources:", "statlink")


_FOOTNOTE_LINE_RX = re.compile(r"^\s*(?:\*+|\d+\.)\s+")


_HEADER_TOKEN_RX = re.compile(r"[A-Za-z][A-Za-z-]{4,}")


@dataclass(frozen=True)
class _TableContinuationAugment:
    prepend_page: Optional[int] = None
    prepend_rect: Optional[fitz.Rect] = None
    append_page: Optional[int] = None
    append_rect: Optional[fitz.Rect] = None


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


def _page_text_blocks(
    page: fitz.Page, *, artifact_cache=None
) -> list[Tuple[fitz.Rect, str]]:
    try:
        return get_page_text_block_pairs(page, cache=artifact_cache)
    except PDF_CROP_EXCEPTIONS:
        return []


def _find_explicit_table_title_block(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    artifact_cache=None,
) -> Optional[fitz.Rect]:
    search_bottom = rect.y0 + min(96.0, rect.height * 0.25)
    candidates: list[fitz.Rect] = []
    for block, text in _page_text_blocks(page, artifact_cache=artifact_cache):
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


def _table_title_strip_rect(
    page: fitz.Page, rect: fitz.Rect, *, artifact_cache=None
) -> Optional[fitz.Rect]:
    title_block = _find_explicit_table_title_block(
        page,
        rect,
        artifact_cache=artifact_cache,
    )
    if title_block is None:
        return None
    next_top = min(
        (
            block.y0
            for block, _ in _page_text_blocks(page, artifact_cache=artifact_cache)
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


def _table_note_strip_rect(
    page: fitz.Page, rect: fitz.Rect, *, artifact_cache=None
) -> Optional[fitz.Rect]:
    blocks = sorted(
        _page_text_blocks(page, artifact_cache=artifact_cache),
        key=lambda item: (item[0].y0, item[0].x0),
    )
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


def _table_header_tokens(
    page: fitz.Page, rect: fitz.Rect, *, artifact_cache=None
) -> set[str]:
    title_block = _find_explicit_table_title_block(
        page,
        rect,
        artifact_cache=artifact_cache,
    )
    max_y = rect.y0 + min(140.0, rect.height * 0.35)
    tokens: set[str] = set()
    for block, text in _page_text_blocks(page, artifact_cache=artifact_cache):
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
    if (
        page_rect.x1 - rect.x1
        > page_rect.width * TABLE_CONTINUATION_MAX_EDGE_DRIFT_FRAC
    ):
        return False
    return True


def _build_table_continuation_augments(
    doc: fitz.Document,
    regions: Sequence[Any],
    *,
    artifact_cache=None,
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
        if (
            abs(prev.rect.x0 - nxt.rect.x0)
            > prev_page_rect.width * TABLE_CONTINUATION_MAX_EDGE_DRIFT_FRAC
        ):
            continue
        if (
            abs(prev.rect.x1 - nxt.rect.x1)
            > prev_page_rect.width * TABLE_CONTINUATION_MAX_EDGE_DRIFT_FRAC
        ):
            continue
        title_strip = _table_title_strip_rect(
            prev_page,
            prev.rect,
            artifact_cache=artifact_cache,
        )
        note_strip = _table_note_strip_rect(
            next_page,
            nxt.rect,
            artifact_cache=artifact_cache,
        )
        if title_strip is None or note_strip is None:
            continue
        if (
            _table_title_strip_rect(
                next_page,
                nxt.rect,
                artifact_cache=artifact_cache,
            )
            is not None
        ):
            continue
        if (
            _table_note_strip_rect(
                prev_page,
                prev.rect,
                artifact_cache=artifact_cache,
            )
            is not None
        ):
            continue
        shared_tokens = _table_header_tokens(
            prev_page,
            prev.rect,
            artifact_cache=artifact_cache,
        ) & _table_header_tokens(
            next_page,
            nxt.rect,
            artifact_cache=artifact_cache,
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


__all__ = [
    "TABLE_CONTINUATION_MIN_WIDTH_FRAC",
    "TABLE_CONTINUATION_MIN_HEIGHT_FRAC",
    "TABLE_CONTINUATION_MAX_EDGE_DRIFT_FRAC",
    "TABLE_CONTINUATION_MAX_START_Y_FRAC",
    "TABLE_CONTINUATION_MIN_END_Y_FRAC",
    "TABLE_CONTINUATION_TITLE_PAD",
    "TABLE_CONTINUATION_NOTE_PAD",
    "TABLE_CONTINUATION_BLOCK_GAP",
    "TABLE_CONTINUATION_HEADER_TOKEN_MIN_SHARED",
    "_EXPLICIT_TABLE_TITLE_PREFIXES",
    "_NOTE_LABEL_PREFIXES",
    "_FOOTNOTE_LINE_RX",
    "_HEADER_TOKEN_RX",
    "_TableContinuationAugment",
    "_normalize_block_text",
    "_block_lines",
    "_text_starts_with_explicit_table_title",
    "_text_has_note_marker",
    "_page_text_blocks",
    "_find_explicit_table_title_block",
    "_table_title_strip_rect",
    "_table_note_strip_rect",
    "_table_header_tokens",
    "_is_wide_table_continuation_region",
    "_build_table_continuation_augments",
]
