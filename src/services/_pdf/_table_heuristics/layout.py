"""Page-layout interpretation used by PDF table heuristics."""

from __future__ import annotations

import statistics
from typing import Any, List, Optional, Tuple

import pdfplumber
import pymupdf as fitz

__all__ = [
    "_extract_text_in_bbox",
    "_table_page_text_blocks",
    "_table_preview",
    "_table_text_bands",
    "_text_stats",
]

from .policy import (
    NOTE_LABEL_PREFIXES,
    PDF_FIGURE_EXCEPTIONS,
    TABLE_EXPAND_HEADING_MAX_AVG_LINE_LEN,
    TABLE_EXPAND_HEADING_MAX_LINES,
    TABLE_EXPAND_HEADING_MAX_SENTENCES,
    TABLE_EXPAND_HEADING_MIN_ALPHA_RATIO,
    TABLE_EXPAND_MIN_H_OVERLAP,
    TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_AVG_LINE_LEN,
    TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_LINES,
    TABLE_NOTE_CONTINUATION_MAX_X_OFFSET,
    TABLE_NOTE_CONTINUATION_MIN_H_OVERLAP,
    TABLE_NOTE_CONTINUATION_MIN_WORDS,
    TABLE_STREAM_CONTINUATION_MAX_BANDS,
    TABLE_STREAM_CONTINUATION_MIN_NUMERIC_FRAGMENTS,
    _FIGURE_CONTEXT_RX,
    _PAGE_NUMBER_RX,
    _TABLE_FOOTNOTE_RX,
)
from .models import (
    _PageTextBlock,
    _PageTextLine,
    _TableTextBand,
)


def _s(value: object) -> str:
    if value is None:
        return ""
    try:
        return str(value)
    except PDF_FIGURE_EXCEPTIONS:
        return ""


def _int_count(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _table_normalize_text(text: str) -> str:
    normalized = str(text or "").replace("|", " ").replace("\u00a0", " ")
    return " ".join(normalized.split())


def _table_text_lines(text: str) -> List[str]:
    lines: List[str] = []
    for raw_line in str(text or "").splitlines():
        normalized = _table_normalize_text(raw_line)
        if normalized:
            lines.append(normalized)
    return lines


def _starts_with_lower_alpha(text: str) -> bool:
    for char in str(text or ""):
        if not char.isalpha():
            continue
        return char.islower()
    return False


def _table_text_has_note_marker(text: str) -> bool:
    for line in _table_text_lines(text):
        lowered = line.lower()
        if _TABLE_FOOTNOTE_RX.match(line):
            return True
        if lowered.startswith(NOTE_LABEL_PREFIXES):
            return True
    return False


def _table_text_has_figure_context(text: str) -> bool:
    for line in _table_text_lines(text):
        if _FIGURE_CONTEXT_RX.match(line):
            return True
    return False


def _table_text_starts_with_footnote_marker(text: str) -> bool:
    lines = _table_text_lines(text)
    if not lines:
        return False
    return bool(_TABLE_FOOTNOTE_RX.match(lines[0]))


def _table_text_has_embedded_note_marker(text: str) -> bool:
    lines = _table_text_lines(text)
    if len(lines) < 2:
        return False
    for line in lines[1:]:
        lowered = line.lower()
        if _TABLE_FOOTNOTE_RX.match(line):
            return True
        if lowered.startswith(NOTE_LABEL_PREFIXES):
            return True
    return False


def _table_page_text_blocks(
    page: fitz.Page,
    text_dict: Optional[dict[str, Any]] = None,
) -> List[_PageTextBlock]:
    blocks: List[_PageTextBlock] = []
    if text_dict is None:
        try:
            text_dict = page.get_text("dict")
        except PDF_FIGURE_EXCEPTIONS:
            text_dict = {}
    raw_blocks = text_dict.get("blocks") or []
    for raw_block in raw_blocks:
        if raw_block.get("type") != 0:
            continue
        bbox = raw_block.get("bbox")
        if not bbox or len(bbox) != 4:
            continue
        rect = fitz.Rect(*bbox)
        line_texts: List[str] = []
        font_sizes: List[float] = []
        for line in raw_block.get("lines", []):
            span_texts: List[str] = []
            for span in line.get("spans", []):
                span_text = _s(span.get("text")).strip()
                if not span_text:
                    continue
                span_texts.append(span_text)
                try:
                    font_sizes.append(float(span.get("size") or 0.0))
                except (TypeError, ValueError):
                    continue
            if span_texts:
                line_texts.append(" ".join(span_texts).strip())
        text = "\n".join(part for part in line_texts if part).strip()
        if not text:
            continue
        lines, chars = _text_stats(text)
        avg_line_len = chars / max(1, lines)
        blocks.append(
            _PageTextBlock(
                rect=rect,
                text=text,
                lines=lines,
                chars=chars,
                avg_line_len=avg_line_len,
                max_font_size=max(font_sizes) if font_sizes else 0.0,
                min_font_size=min(font_sizes) if font_sizes else 0.0,
            )
        )
    if blocks:
        return blocks
    try:
        fallback_blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        fallback_blocks = []
    for x0, y0, x1, y1, text, *_ in fallback_blocks:
        text_str = str(text or "").strip()
        if not text_str:
            continue
        lines, chars = _text_stats(text_str)
        avg_line_len = chars / max(1, lines)
        blocks.append(
            _PageTextBlock(
                rect=fitz.Rect(float(x0), float(y0), float(x1), float(y1)),
                text=text_str,
                lines=lines,
                chars=chars,
                avg_line_len=avg_line_len,
                max_font_size=0.0,
                min_font_size=0.0,
            )
        )
    return blocks


def _table_page_body_font_size(blocks: List[_PageTextBlock]) -> float:
    sizes = [block.max_font_size for block in blocks if block.max_font_size > 0.0]
    if not sizes:
        return 0.0
    try:
        return float(statistics.median(sizes))
    except statistics.StatisticsError:
        return float(sizes[0])


def _cell_is_numeric(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    for ch in stripped:
        if ch.isdigit():
            continue
        if ch in {".", ",", "%", "+", "-", "–"}:
            continue
        return False
    return any(ch.isdigit() for ch in stripped)


def _table_fragment_is_numeric(text: str) -> bool:
    compact = _table_normalize_text(text).replace(" ", "")
    if not compact:
        return False
    compact = compact.replace("*", "")
    return _cell_is_numeric(compact)


def _table_page_text_lines(
    page: fitz.Page,
    text_dict: Optional[dict[str, Any]] = None,
) -> List[_PageTextLine]:
    if text_dict is None:
        try:
            text_dict = page.get_text("dict")
        except PDF_FIGURE_EXCEPTIONS:
            return []
    lines: List[_PageTextLine] = []
    for block in text_dict.get("blocks") or []:
        if block.get("type") != 0:
            continue
        for line in block.get("lines") or []:
            parts: List[str] = []
            min_x: Optional[float] = None
            min_y: Optional[float] = None
            max_x: Optional[float] = None
            max_y: Optional[float] = None
            max_font_size = 0.0
            for span in line.get("spans") or []:
                text = str(span.get("text") or "")
                if not text.strip():
                    continue
                bbox = span.get("bbox") or []
                if len(bbox) != 4:
                    continue
                x0, y0, x1, y1 = map(float, bbox)
                parts.append(text.strip())
                min_x = x0 if min_x is None else min(min_x, x0)
                min_y = y0 if min_y is None else min(min_y, y0)
                max_x = x1 if max_x is None else max(max_x, x1)
                max_y = y1 if max_y is None else max(max_y, y1)
                max_font_size = max(max_font_size, float(span.get("size") or 0.0))
            if (
                not parts
                or min_x is None
                or min_y is None
                or max_x is None
                or max_y is None
            ):
                continue
            lines.append(
                _PageTextLine(
                    rect=fitz.Rect(
                        float(min_x),
                        float(min_y),
                        float(max_x),
                        float(max_y),
                    ),
                    text=_table_normalize_text(" ".join(parts)),
                    max_font_size=max_font_size,
                )
            )
    return lines


def _table_text_bands(
    page: fitz.Page,
    *,
    text_dict: Optional[dict[str, Any]] = None,
    page_text_lines: Optional[List[_PageTextLine]] = None,
) -> List[_TableTextBand]:
    lines = sorted(
        page_text_lines
        if page_text_lines is not None
        else _table_page_text_lines(page, text_dict=text_dict),
        key=lambda line: (
            round((line.rect.y0 + line.rect.y1) / 2.0, 1),
            line.rect.x0,
            line.rect.x1,
        ),
    )
    if not lines:
        return []

    def _flush(group: List[_PageTextLine], bands: List[_TableTextBand]) -> None:
        ordered = sorted(group, key=lambda line: (line.rect.x0, line.rect.y0))
        rect = fitz.Rect(ordered[0].rect)
        parts = [line.text for line in ordered if line.text]
        max_font_size = max((line.max_font_size for line in ordered), default=0.0)
        max_gap_x = 0.0
        for index in range(1, len(ordered)):
            prev = ordered[index - 1].rect
            cur = ordered[index].rect
            max_gap_x = max(max_gap_x, max(0.0, cur.x0 - prev.x1))
            rect |= cur
        text = _table_normalize_text(" ".join(parts))
        bands.append(
            _TableTextBand(
                rect=rect,
                text=text,
                fragment_count=len(ordered),
                numeric_fragment_count=sum(
                    1 for line in ordered if _table_fragment_is_numeric(line.text)
                ),
                word_count=len(text.split()),
                max_font_size=max_font_size,
                max_gap_x=max_gap_x,
            )
        )

    bands: List[_TableTextBand] = []
    current: List[_PageTextLine] = []
    current_center = 0.0
    tolerance = 3.6
    for line in lines:
        center = (line.rect.y0 + line.rect.y1) / 2.0
        if not current:
            current = [line]
            current_center = center
            continue
        if abs(center - current_center) <= tolerance:
            current.append(line)
            current_center = sum(
                (item.rect.y0 + item.rect.y1) / 2.0 for item in current
            ) / len(current)
            continue
        _flush(current, bands)
        current = [line]
        current_center = center
    if current:
        _flush(current, bands)
    return bands


def _table_band_is_margin_noise(band: _TableTextBand, page_rect: fitz.Rect) -> bool:
    normalized = _table_normalize_text(band.text)
    if _is_page_number_text(normalized):
        return True
    if (
        band.rect.y0 <= page_rect.y0 + page_rect.height * 0.045
        and len(normalized) <= 24
    ):
        return True
    if (
        band.rect.y1 >= page_rect.y1 - page_rect.height * 0.03
        and len(normalized) <= 128
        and ("oecd" in normalized.lower() or "economic outlook" in normalized.lower())
    ):
        return True
    return False


def _table_band_is_note_like(band: _TableTextBand) -> bool:
    normalized = _table_normalize_text(band.text)
    lowered = normalized.lower()
    if not normalized:
        return False
    if _table_text_has_note_marker(band.text):
        return True
    if "statlink" in lowered or "http://" in lowered or "https://" in lowered:
        return True
    return False


def _table_band_is_heading_like(
    band: _TableTextBand,
    body_font_size: float,
) -> bool:
    normalized = _table_normalize_text(band.text)
    if not normalized:
        return False
    word_count = len(normalized.split())
    if word_count == 0 or word_count > 18:
        return False
    if len(normalized) > 160:
        return False
    if normalized.endswith("."):
        return False
    font_large = body_font_size > 0.0 and band.max_font_size >= body_font_size + 0.75
    text_heading = _heading_like_block(normalized, 1, float(len(normalized)))
    return font_large or text_heading


def _table_band_is_body_paragraph(
    band: _TableTextBand,
    body_font_size: float,
) -> bool:
    if _table_band_is_note_like(band):
        return False
    if _table_band_is_heading_like(band, body_font_size):
        return False
    normalized = _table_normalize_text(band.text)
    if band.fragment_count != 1:
        return False
    if band.word_count >= 10:
        return True
    if len(normalized) >= 60 and band.word_count >= 8:
        return True
    return False


def _table_band_is_title_like(
    band: _TableTextBand,
    body_font_size: float,
) -> bool:
    if _table_band_is_note_like(band):
        return False
    normalized = _table_normalize_text(band.text)
    lowered = normalized.lower()
    if lowered.startswith(("table ", "exhibit ")):
        return True
    if ":" in normalized and len(normalized.split()) <= 16:
        return True
    return _table_band_is_heading_like(band, body_font_size)


def _table_band_is_row_like(
    band: _TableTextBand,
    page_rect: fitz.Rect,
) -> bool:
    if _table_band_is_margin_noise(band, page_rect):
        return False
    if _table_band_is_note_like(band):
        return False
    normalized = _table_normalize_text(band.text)
    if not normalized:
        return False
    if band.numeric_fragment_count >= 3:
        return True
    if band.fragment_count >= 4 and band.numeric_fragment_count >= 2:
        return True
    if (
        band.fragment_count >= 3
        and band.numeric_fragment_count >= 1
        and band.max_gap_x >= max(18.0, page_rect.width * 0.03)
        and band.word_count <= 14
    ):
        return True
    if band.fragment_count >= 5 and band.word_count <= 12:
        return True
    return False


def _table_block_is_margin_noise(block: _PageTextBlock, page_rect: fitz.Rect) -> bool:
    text_normalized = _table_normalize_text(block.text)
    if _is_page_number_text(text_normalized):
        return True
    if (
        block.rect.y0 <= page_rect.y0 + page_rect.height * 0.045
        and len(text_normalized) <= 18
    ):
        return True
    if (
        block.rect.y1 >= page_rect.y1 - page_rect.height * 0.03
        and len(text_normalized) <= 96
    ):
        lowered = text_normalized.lower()
        if "oecd" in lowered or "economic outlook" in lowered:
            return True
    return False


def _cluster_is_row_continuation(
    cluster: List[_TableTextBand],
    rect: fitz.Rect,
    page_rect: fitz.Rect,
) -> bool:
    if not cluster or len(cluster) > TABLE_STREAM_CONTINUATION_MAX_BANDS:
        return False
    cluster_rect = fitz.Rect(
        min(band.rect.x0 for band in cluster),
        min(band.rect.y0 for band in cluster),
        max(band.rect.x1 for band in cluster),
        max(band.rect.y1 for band in cluster),
    )
    if _horizontal_overlap_ratio(cluster_rect, rect) < TABLE_EXPAND_MIN_H_OVERLAP:
        return False
    for band in cluster:
        if _table_band_is_margin_noise(band, page_rect):
            return False
        if (
            band.numeric_fragment_count
            < TABLE_STREAM_CONTINUATION_MIN_NUMERIC_FRAGMENTS
        ):
            return False
    return True


def _table_block_is_note_like(block: _PageTextBlock) -> bool:
    normalized = _table_normalize_text(block.text)
    lowered = normalized.lower()
    if not normalized:
        return False
    if _table_text_has_note_marker(block.text):
        return True
    if (
        "statlink" in lowered
        or "doi.org" in lowered
        or "http://" in lowered
        or "https://" in lowered
    ):
        return True
    return False


def _table_block_is_mixed_footer_cluster(block: _PageTextBlock) -> bool:
    if not _table_text_has_embedded_note_marker(block.text):
        return False
    if block.lines > 10:
        return False
    if block.avg_line_len > 85:
        return False
    return True


def _table_block_is_heading_like(
    block: _PageTextBlock,
    body_font_size: float,
) -> bool:
    normalized = _table_normalize_text(block.text)
    if not normalized:
        return False
    word_count = len(normalized.split())
    if word_count == 0 or word_count > 18:
        return False
    if len(normalized) > 140:
        return False
    if normalized.endswith("."):
        return False
    font_large = body_font_size > 0.0 and block.max_font_size >= body_font_size + 0.75
    text_heading = _heading_like_block(
        normalized,
        block.lines,
        block.avg_line_len,
    )
    return font_large or text_heading


def _table_block_is_body_paragraph(
    block: _PageTextBlock,
    body_font_size: float,
) -> bool:
    if _table_block_is_note_like(block):
        return False
    if _table_block_is_heading_like(block, body_font_size):
        return False
    normalized = _table_normalize_text(block.text)
    if block.lines >= 3 and block.avg_line_len >= 24:
        return True
    if block.lines >= 2 and block.avg_line_len >= 42:
        return True
    if len(normalized.split()) >= 18 and block.avg_line_len >= 28:
        return True
    return False


def _table_block_is_note_continuation(
    block: _PageTextBlock,
    rect: fitz.Rect,
    body_font_size: float,
) -> bool:
    if _table_block_is_note_like(block):
        return False
    if _table_block_is_heading_like(block, body_font_size):
        return False
    if not _table_block_is_body_paragraph(block, body_font_size):
        return False
    if (
        _horizontal_overlap_ratio(block.rect, rect)
        < TABLE_NOTE_CONTINUATION_MIN_H_OVERLAP
    ):
        return False
    if block.rect.x0 > rect.x0 + TABLE_NOTE_CONTINUATION_MAX_X_OFFSET:
        return False
    if (
        len(_table_normalize_text(block.text).split())
        < TABLE_NOTE_CONTINUATION_MIN_WORDS
    ):
        return False
    return True


def _table_band_is_note_continuation(
    band: _TableTextBand,
    rect: fitz.Rect,
    body_font_size: float,
) -> bool:
    if _table_band_is_note_like(band):
        return False
    if _table_band_is_heading_like(band, body_font_size):
        return False
    if not _table_band_is_body_paragraph(band, body_font_size):
        return False
    if (
        _horizontal_overlap_ratio(band.rect, rect)
        < TABLE_NOTE_CONTINUATION_MIN_H_OVERLAP
    ):
        return False
    if band.rect.x0 > rect.x0 + TABLE_NOTE_CONTINUATION_MAX_X_OFFSET:
        return False
    if band.word_count < TABLE_NOTE_CONTINUATION_MIN_WORDS:
        return False
    return True


def _table_block_is_title_like(
    block: _PageTextBlock,
    body_font_size: float,
) -> bool:
    if _table_block_is_note_like(block):
        return False
    normalized = _table_normalize_text(block.text)
    lowered = normalized.lower()
    if lowered.startswith(("table ", "exhibit ")):
        return True
    if ":" in normalized and len(normalized.split()) <= 14:
        return True
    return _table_block_is_heading_like(block, body_font_size)


def _table_block_looks_dense_tabular(block: _PageTextBlock) -> bool:
    if block.lines < TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MIN_LINES:
        return False
    if block.avg_line_len > TABLE_HORIZONTAL_EXPAND_DENSE_TABULAR_MAX_AVG_LINE_LEN:
        return False
    normalized = _table_normalize_text(block.text)
    if not normalized:
        return False
    if len(normalized.split()) < block.lines:
        return False
    return True


def _alpha_ratio(text: str) -> float:
    if not text:
        return 0.0
    alpha = sum(1 for ch in text if ch.isalpha())
    total = len(text)
    return alpha / total if total else 0.0


def _is_page_number_text(text: str) -> bool:
    if not text:
        return False
    cleaned = text.strip()
    if not _PAGE_NUMBER_RX.match(cleaned):
        return False
    return _alpha_ratio(cleaned) <= 0.3


def _horizontal_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    left = max(a.x0, b.x0)
    right = min(a.x1, b.x1)
    overlap = max(0.0, right - left)
    if overlap <= 0.0:
        return 0.0
    denom = min(a.width, b.width)
    if denom <= 0.0:
        return 0.0
    return overlap / denom


def _vertical_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    top = max(a.y0, b.y0)
    bot = min(a.y1, b.y1)
    overlap = max(0.0, bot - top)
    if overlap <= 0.0:
        return 0.0
    denom = min(a.height, b.height)
    if denom <= 0.0:
        return 0.0
    return overlap / denom


def _table_preview(rows: List[List[object]]) -> str:
    preview_lines = []
    for row in rows[:3]:
        if not row:
            continue
        preview_lines.append(" | ".join(_s(c) for c in row[:6]))
    return "\n".join(preview_lines)


def _extract_text_in_bbox(
    page: pdfplumber.page.Page, bbox: Tuple[float, float, float, float]
) -> str:
    try:
        return page.within_bbox(bbox).extract_text() or ""
    except (AttributeError, ValueError, RuntimeError, TypeError):
        return ""


def _text_stats(text: str) -> Tuple[int, int]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    char_count = sum(len(line) for line in lines)
    return len(lines), char_count


def _rect_intersection_area(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    return max(0.0, inter.get_area())


def _heading_like_block(text: str, lines: int, avg_line_len: float) -> bool:
    if lines == 0:
        return False
    if lines > TABLE_EXPAND_HEADING_MAX_LINES:
        return False
    if avg_line_len > TABLE_EXPAND_HEADING_MAX_AVG_LINE_LEN:
        return False
    if _alpha_ratio(text) < TABLE_EXPAND_HEADING_MIN_ALPHA_RATIO:
        return False
    sentence_marks = text.count(".") + text.count("!") + text.count("?")
    if sentence_marks > TABLE_EXPAND_HEADING_MAX_SENTENCES:
        return False
    return True


def _text_block_stats(
    page: fitz.Page,
    bbox: Tuple[float, float, float, float],
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> Tuple[float, int, float]:
    rect = fitz.Rect(*bbox)
    rect_area = max(1.0, rect.get_area())
    block_area = 0.0
    line_count = 0
    total_line_len = 0
    if blocks is None:
        try:
            blocks = page.get_text("blocks")
        except PDF_FIGURE_EXCEPTIONS:
            blocks = []
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        block_rect = fitz.Rect(x0, y0, x1, y1)
        inter_area = _rect_intersection_area(rect, block_rect)
        if inter_area <= 0.0:
            continue
        block_area += inter_area
        lines = [line.strip() for line in str(text).splitlines() if line.strip()]
        line_count += len(lines)
        total_line_len += sum(len(line) for line in lines)
    avg_line_len = (total_line_len / line_count) if line_count else 0.0
    return block_area / rect_area, line_count, avg_line_len
