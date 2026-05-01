"""Chart and infographic candidate heuristics facade.

This module keeps `visual_heuristics.py` as the discoverable internal boundary
while moving panel detection and chart-layout families into `_visual_heuristics/`.
It is not a public service boundary; callers enter through `pdf_service`.
"""

from __future__ import annotations

# ruff: noqa: F401,F841
import io
import logging
import math
import os
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pdfplumber
import pymupdf as fitz
from PIL import Image

from src.contracts.candidates import Candidate
from src.utils.candidate_features import candidate_features
from src.utils.errors import AppError
from src.utils.path_utils import safe_path_segment

PDF_FIGURE_EXCEPTIONS = (
    RuntimeError,
    ValueError,
    TypeError,
    AttributeError,
    IndexError,
    KeyError,
    OSError,
    statistics.StatisticsError,
)


CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph", "source")


CHART_CAPTION_HINTS = ("figure", "fig.", "exhibit", "chart", "graph", "infographic")


TABLE_CAPTION_HINTS = CAPTION_HINTS + ("table",)


PANEL_GUIDANCE_TITLE_RX = re.compile(
    r"\b(?:\d+|one|two|three|four|five|six|seven|eight|nine|ten)\s+"
    r"(?:ways?|keys?|steps?|actions?|principles?|tips?|strategies?|takeaways?|lessons?|rules?)\b",
    re.IGNORECASE,
)


PAGE_FOOTER_BANNER_LINE_RX = re.compile(
    r"(?:\b20\d{2}\b\s*[|/]\s*\d{1,3}\b)|(?:[|/]\s*\d{1,3}\s*$)"
)


CHART_TEXT_MAX_LINES = 6


CHART_TEXT_MIN_CHARS = 60


CHART_TEXT_RATIO_THRESHOLD = 0.35


CHART_LABEL_DENSE_MIN_LINES = 20


CHART_LABEL_DENSE_MAX_AVG_LINE_LEN = 18.0


CHART_LABEL_DENSE_MAX_MEDIAN_LINE_LEN = 10.0


CHART_LABEL_DENSE_LONG_LINE_LEN = 32


CHART_LABEL_DENSE_MAX_LONG_LINE_RATIO = 0.2


CHART_LABEL_DENSE_SHORT_LINE_LEN = 12


CHART_LABEL_DENSE_MIN_SHORT_LINE_RATIO = 0.4


PANEL_CHART_MIN_NUMERIC_HITS = 2


PANEL_CHART_LABEL_ATTACH_MAX_GAP_X_FRAC = 0.1


PANEL_CHART_LABEL_ATTACH_MAX_GAP_Y_FRAC = 0.08


PANEL_CHART_LABEL_ATTACH_MIN_V_OVERLAP = 0.15


PANEL_CHART_LABEL_ATTACH_MIN_H_OVERLAP = 0.15


PANEL_CHART_LABEL_ATTACH_SKIP_OVERLAP_RATIO = 0.85


PANEL_CHART_LABEL_ATTACH_MAX_LINES = 6


PANEL_CHART_LABEL_ATTACH_MAX_AVG_LINE_LEN = 34.0


PANEL_CHART_LABEL_ATTACH_MAX_CHARS = 180


PANEL_CHART_LABEL_ATTACH_MAX_AREA_FRAC = 0.08


PANEL_CHART_TOP_TITLE_ATTACH_MAX_SPILL_X_FRAC = 0.16


PANEL_CHART_TOP_TITLE_ATTACH_MAX_CENTER_DELTA_FRAC = 0.20


PANEL_CHART_TOP_TITLE_ATTACH_MAX_GAP_FRAC = 0.32


PANEL_CHART_TOP_TITLE_ATTACH_MIN_WIDTH_RATIO = 0.45


PANEL_CHART_TOP_TITLE_ATTACH_MAX_WIDTH_RATIO = 0.95


PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MIN_WIDTH_RATIO = 0.10


PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MAX_WIDTH_RATIO = 0.22


PANEL_CHART_TOP_TITLE_ATTACH_NARROW_MAX_CENTER_DELTA_FRAC = 0.18


PANEL_CHART_TOP_TITLE_ATTACH_MAX_HEIGHT_RATIO = 0.26


PANEL_CHART_TOP_TITLE_ATTACH_MAX_LEFT_INSET_FRAC = 0.22


PANEL_CHART_TOP_TITLE_ATTACH_COMPONENT_MIN_H_OVERLAP = 0.08


PANEL_CHART_TITLE_BAND_MERGE_MAX_GAP_FRAC = 0.28


PANEL_CHART_TITLE_BAND_MERGE_MAX_AREA_RATIO = 0.65


PANEL_CHART_TITLE_BAND_MERGE_MIN_H_OVERLAP = 0.35


PANEL_CHART_INTERNAL_CAPTION_TOP_GAP_MAX = 32.0


PANEL_CHART_INTERNAL_CAPTION_MIN_WIDTH_RATIO = 0.30


PANEL_CHART_INTERNAL_CAPTION_MAX_LINES = 3


PANEL_CHART_INTERNAL_CAPTION_MAX_CHARS = 140


PANEL_CHART_INTERNAL_CAPTION_MAX_AVG_LINE_LEN = 60.0


PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD = 8.0


INFOGRAPHIC_LABEL_DENSE_MAX_AVG_LINE_LEN = 20.0


INFOGRAPHIC_LABEL_DENSE_MAX_MEDIAN_LINE_LEN = 12.0


INFOGRAPHIC_LABEL_DENSE_MAX_LONG_LINE_RATIO = 0.35


INFOGRAPHIC_LABEL_DENSE_MIN_SHORT_LINE_RATIO = 0.3


CHART_DENSE_RECOVERY_MIN_LINES = 12


CHART_DENSE_RECOVERY_MIN_CHARS = 400


CHART_DEDUP_IOU = 0.9


CHART_OVERLAP_IOU = 0.85


CHART_OVERLAP_CONTAINMENT = 0.88


CHART_MARGIN_FRAC = 0.12


CHART_MARGIN_RELAX_FRAC = 0.05


CHART_PAD_X_FRAC = 0.01


CHART_PAD_Y_FRAC = 0.008


CHART_NOTE_MAX_DIST = 140


CHART_NOTE_MAX_GAP_X_FRAC = 0.25


CHART_CAPTION_TOP_PAD_PX = 16.0


CHART_CAPTION_TOP_PAD_FRAC = 0.35


CHART_CAPTION_TOP_SEARCH_FRAC = 0.2


CHART_CAPTION_TOP_GUARD_FRAC = 0.01


CHART_CAPTION_TOP_BLOCK_H_OVERLAP = 0.3


CHART_CAPTION_MERGE_MAX_GAP_FRAC = 0.18


CHART_CAPTION_INTERNAL_TOP_TOL_PX = 18.0


CHART_CAPTION_INTERNAL_TOP_TOL_FRAC = 0.02


CHART_CAPTIONED_DRAW_MAX_ASPECT = 3.4


CHART_CROP_PAD_COMPENSATION = 8


CHART_NOTE_PAD_EXTRA = 24


CHART_NOTE_BELOW_GUARD_PX = 3


CHART_NOTE_BELOW_MIN_H_OVERLAP = 0.2


CHART_LABEL_MAX_GAP_FRAC = 0.06


CHART_LABEL_MAX_V_GAP_FRAC = 0.05


CHART_LABEL_MIN_V_OVERLAP = 0.35


CHART_LABEL_MIN_H_OVERLAP = 0.35


CHART_LABEL_PARAGRAPH_MIN_LINES = 3


CHART_LABEL_PARAGRAPH_MAX_AVG_LINE_LEN = 32


CHART_LABEL_MAX_LINES = 6


CHART_LABEL_MAX_AVG_LINE_LEN = 40


CHART_LABEL_MAX_HEIGHT_FRAC = 0.5


CHART_LABEL_COMPACT_TITLE_MAX_LINES = 2


CHART_LABEL_COMPACT_TITLE_MAX_AVG_LINE_LEN = 72


CHART_LABEL_COMPACT_TITLE_MAX_CHARS = 120


CHART_NEXT_BLOCKER_MIN_GAP_FRAC = 0.08


CHART_NEXT_BLOCKER_MIN_GAP_PX = 48.0


CHART_NEXT_BLOCKER_MIN_H_OVERLAP = 0.3


CHART_NEXT_BLOCKER_GUARD_PX = 4.0


CHART_EDGE_TEXT_MIN_GAP_FRAC = 0.08


CHART_EDGE_TEXT_MAX_PAD_FRAC = 0.12


CHART_EDGE_TEXT_MIN_GAP_X_FRAC = 0.04


CHART_EDGE_TEXT_MAX_PAD_X_FRAC = 0.06


CHART_EDGE_TEXT_HEADING_GAP_SCALE = 0.4


CHART_EDGE_TEXT_HEADING_GAP_X_SCALE = 0.5


CHART_WHITESPACE_GUARD_GAP_FRAC = 0.02


CHART_WHITESPACE_GUARD_GAP_X_FRAC = 0.02


CHART_WHITESPACE_MAX_PAD_FRAC = 0.06


CHART_WHITESPACE_MAX_PAD_X_FRAC = 0.05


CHART_WHITESPACE_MIN_OVERLAP = 0.3


CHART_HEADING_TOP_MAX_PAD_FRAC = 0.0


CHART_HEADING_TOP_SEARCH_FRAC = 0.25


CHART_HEADING_TOP_GUARD_FRAC = 0.01


CHART_HEADING_TOP_BLOCK_H_OVERLAP = 0.3


CHART_HEADING_MERGE_MAX_GAP_FRAC = 0.08


DRAWING_MIN_RECT_DIM = 6.0


DRAWING_MIN_RECT_AREA = 200.0


DRAWING_BACKGROUND_MIN_AREA_FRAC = 0.9


DRAWING_BACKGROUND_MAX_STROKE = 1.0


INFO_HEADING_MIN_WORDS = 3


INFO_HEADING_MIN_ALPHA_RATIO = 0.55


INFO_HEADING_MIN_SIZE = 12.0


INFO_HEADING_SIZE_DELTA = 2.0


INFO_HEADING_MAX_WORDS = 30


INFO_HEADING_MAX_CHARS = 160


INFO_HEADING_MAX_SENTENCES = 2


INFO_HEADING_MERGE_GAP_FRAC = 0.012


INFO_HEADING_MERGE_SIZE_DELTA = 2.0


INFO_HEADING_MERGE_H_OVERLAP = 0.4


INFO_CHART_MIN_DRAWINGS = 5


INFO_CHART_MIN_AREA_FRAC = 0.04


INFO_CHART_BAND_FRAC = 0.6


INFO_CHART_MAX_GAP_FRAC = 0.25


INFO_CHART_CLUSTER_GAP_FRAC = 0.05


INFO_CHART_MAX_ASPECT = 4.0


PANEL_CHART_MIN_AREA_FRAC = 0.035


PANEL_CHART_MAX_AREA_FRAC = 0.75


PANEL_CHART_CONNECT_GAP_FRAC = 0.015


PANEL_CHART_TITLE_MIN_SIZE = 15.0


PANEL_CHART_TITLE_MIN_WORDS = 2


PANEL_CHART_TITLE_MAX_WORDS = 12


PANEL_CHART_TITLE_MAX_CHARS = 120


PANEL_CHART_TITLE_MAX_SENTENCES = 1


PANEL_CHART_LOCAL_TITLE_MIN_SIZE = 10.5


PANEL_CHART_LOCAL_TITLE_TOP_FRAC = 0.38


PANEL_CHART_LOCAL_TITLE_MAX_HEIGHT_RATIO = 0.22


PANEL_CHART_LOCAL_TITLE_MIN_WIDTH_RATIO = 0.18


PANEL_CHART_LOCAL_TITLE_MAX_WIDTH_RATIO = 0.75


PANEL_CHART_TITLE_SLICE_Y_TOL = 14.0


PANEL_CHART_TITLE_SLICE_SIZE_TOL = 3.0


PANEL_CHART_TITLE_SLICE_X_PAD_FRAC = 0.03


CHART_AXIS_LABEL_BAND_MAX_LINES = 48


CHART_AXIS_LABEL_BAND_MAX_AVG_LINE_LEN = 12.0


CHART_AXIS_LABEL_BAND_MIN_TOKEN_HITS = 4


CHART_AXIS_LABEL_BAND_MIN_ALPHA_RATIO = 0.45


PANEL_CHART_TITLE_MAX_GAP = 72.0


PANEL_CHART_TITLE_NEAREST_TOL = 24.0


PANEL_CHART_TITLE_X_PAD = 72.0


PANEL_CHART_SPLIT_MIN_CENTER_GAP_FRAC = 0.12


PANEL_CHART_SPLIT_SLICE_X_PAD_FRAC = 0.025


PANEL_CHART_SPLIT_MIN_WIDTH_RATIO = 0.6


PANEL_CHART_TITLE_STACK_MAX_GAP = 20.0


PANEL_CHART_TITLE_STACK_MIN_H_OVERLAP = 0.45


PANEL_CHART_TITLE_STACK_MAX_EDGE_DELTA = 72.0


PANEL_CHART_SHARED_COMPONENT_MAX_SIDE_GAP_FRAC = 0.08


PANEL_CHART_SHARED_COMPONENT_MIN_V_OVERLAP = 0.55


PANEL_CHART_SHARED_COMPONENT_MAX_STACK_GAP_FRAC = 0.10


PANEL_CHART_SHARED_COMPONENT_MIN_H_ALIGN = 0.65


PANEL_CHART_SHARED_COMPONENT_MIN_WIDTH_RATIO = 0.55


PANEL_CHART_SHARED_COMPONENT_MIN_HEIGHT_RATIO = 0.18


PANEL_CONTEXT_CARD_MAX_SIDE_GAP_FRAC = 0.06


PANEL_CONTEXT_CARD_MIN_V_OVERLAP = 0.55


PANEL_CONTEXT_CARD_MIN_HEIGHT_RATIO = 0.55


PANEL_CONTEXT_CARD_MIN_TEXT_CHARS = 60


PANEL_CONTEXT_CARD_MAX_COMPONENT_OVERLAP = 0.35


NOTE_LABEL_PREFIXES = ("note:", "notes:", "source:", "sources:", "statlink")


EMAIL_ADDRESS_RX = re.compile(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b")


_PAGE_NUMBER_RX = re.compile(
    r"^\s*[^0-9A-Za-z]*\d{1,4}(?:\s*[-–]\s*\d{1,4})?[^0-9A-Za-z]*\s*$"
)


_PANEL_TITLE_EXCLUDE_RX = re.compile(
    r"^\s*(?:figure|fig\.|exhibit|chart|graph|table|source|infographic)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class _ChartRect:
    rect: fitz.Rect
    kind: str
    xref: Optional[int] = None
    caption: Optional[str] = None
    caption_rect: Optional[fitz.Rect] = None


@dataclass(frozen=True)
class _PageTextLine:
    rect: fitz.Rect
    text: str
    max_font_size: float


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


def _rect_iou(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    union = a.get_area() + b.get_area() - inter.get_area()
    if union <= 0.0:
        return 0.0
    return inter.get_area() / union


def _table_normalize_text(text: str) -> str:
    normalized = str(text or "").replace("|", " ").replace("\u00a0", " ")
    return " ".join(normalized.split())


def _starts_with_lower_alpha(text: str) -> bool:
    for char in str(text or ""):
        if not char.isalpha():
            continue
        return char.islower()
    return False


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


def _rect_containment_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    inter_area = inter.get_area()
    if inter_area <= 0.0:
        return 0.0
    denom = min(a.get_area(), b.get_area())
    if denom <= 0.0:
        return 0.0
    return inter_area / denom


def _rect_seen(rect: fitz.Rect, seen: List[fitz.Rect]) -> bool:
    for existing in seen:
        if _rect_iou(rect, existing) >= CHART_DEDUP_IOU:
            return True
    return False


def _chart_candidate_score(
    area_frac: float,
    has_hint: bool,
    caption: str,
    note_included: bool,
) -> float:
    score = area_frac
    if has_hint:
        score += 0.2
    if caption:
        score += min(0.2, len(caption) / 200.0)
    if note_included:
        score += 0.1
    return score


def _find_overlapping_kept(
    rect: fitz.Rect,
    kept: List[Tuple[fitz.Rect, float, int]],
) -> Optional[int]:
    for idx, (existing, _score, _out_idx) in enumerate(kept):
        if _rect_iou(rect, existing) >= CHART_OVERLAP_IOU:
            return idx
        if _rect_containment_ratio(rect, existing) >= CHART_OVERLAP_CONTAINMENT:
            return idx
        if _rect_containment_ratio(existing, rect) >= CHART_OVERLAP_CONTAINMENT:
            return idx
    return None

def _rect_overlap_area(left: fitz.Rect, right: fitz.Rect) -> float:
    overlap = fitz.Rect(left)
    overlap &= right
    if overlap.x1 <= overlap.x0 or overlap.y1 <= overlap.y0:
        return 0.0
    return overlap.get_area()

def _line_starts_with_caption_hint(text: str, hints: Tuple[str, ...]) -> bool:
    normalized = _s(text).strip().lower()
    if not normalized:
        return False
    for hint in hints:
        if hint in {"chart", "graph"}:
            if re.match(
                rf"^{re.escape(hint)}\s*(?:\d|[ivxlcdm]+\b|[a-z]\b|[:.\-])", normalized
            ):
                return True
            continue
        if normalized.startswith(hint):
            return True
    return False

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


def _pad_rect(rect: fitz.Rect, page_rect: fitz.Rect) -> fitz.Rect:
    pad_x = max(page_rect.width * CHART_PAD_X_FRAC, 2.0)
    pad_y = max(page_rect.height * CHART_PAD_Y_FRAC, 2.0)
    x0 = max(page_rect.x0, rect.x0 - pad_x)
    y0 = max(page_rect.y0, rect.y0 - pad_y)
    x1 = min(page_rect.x1, rect.x1 + pad_x)
    y1 = min(page_rect.y1, rect.y1 + pad_y)
    return fitz.Rect(x0, y0, x1, y1)

def _save_thumb(
    pix: fitz.Pixmap, out_dir: str, report_name: str, index: int, max_w: int = 480
) -> str:
    safe_report_name = safe_path_segment(report_name, fallback="report")
    if pix.alpha:
        pix = fitz.Pixmap(fitz.csRGB, pix)
    elif pix.colorspace and pix.colorspace != fitz.csRGB:
        pix = fitz.Pixmap(fitz.csRGB, pix)

    png_bytes = pix.tobytes("png")
    img = Image.open(io.BytesIO(png_bytes)).convert("RGB")

    if img.width > max_w:
        new_h = int(img.height * max_w / img.width)
        img = img.resize((max_w, new_h), Image.LANCZOS)

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    if index == 0:
        filename = f"{safe_report_name}.png"
    else:
        filename = f"{safe_report_name}{index}.png"
    p = Path(out_dir) / filename
    img.save(p.as_posix(), format="PNG")
    return p.as_posix()


def _nearby_text(
    page: fitz.Page,
    rect: fitz.Rect,
    max_dist: float = 90,
    *,
    blocks: Optional[List[Tuple[float, float, float, float, str]]] = None,
) -> str:
    best = ("", 1e9)
    if blocks is None:
        try:
            blocks = page.get_text("blocks")
        except PDF_FIGURE_EXCEPTIONS:
            return ""
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if _is_page_number_text(text):
            continue
        r = fitz.Rect(x0, y0, x1, y1)
        dy = r.y0 - rect.y1
        dist = dy if dy >= 0 else abs(dy) + 24
        if dist <= max_dist and dist < best[1]:
            best = (text.strip(), dist)
    return best[0]


def _candidate_index_from_id(candidate_id: str) -> int:
    try:
        return int(str(candidate_id).rsplit("-", 1)[-1])
    except (TypeError, ValueError):
        return 0


def _merge_stats(
    base: Dict[str, object], extra: Dict[str, object]
) -> Dict[str, object]:
    merged = dict(base)
    for key, value in extra.items():
        if key == "reasons":
            reasons = value if isinstance(value, dict) else {}
            for reason, count in reasons.items():
                for _ in range(max(0, _int_count(count))):
                    _tally_reason(merged, str(reason))
            continue
        merged[key] = _int_count(merged.get(key, 0)) + _int_count(value)
    return merged


def _split_even_chunks(values: List[int], chunk_count: int) -> List[List[int]]:
    if not values:
        return []
    chunk_count = max(1, min(int(chunk_count), len(values)))
    chunks: List[List[int]] = [[] for _ in range(chunk_count)]
    for idx, value in enumerate(values):
        chunks[idx % chunk_count].append(value)
    return [chunk for chunk in chunks if chunk]


def _resolve_candidate_parallel_workers(requested_workers: int, unit_count: int) -> int:
    if unit_count <= 1:
        return 1
    workers = 0
    try:
        workers = int(requested_workers)
    except (TypeError, ValueError):
        workers = 0
    if workers <= 0:
        env_value = os.getenv("INGEST_REPORT_WORKER_LIMIT")
        if env_value:
            try:
                workers = int(env_value)
            except (TypeError, ValueError):
                workers = 0
    if workers <= 0:
        workers = max(2, min(6, (os.cpu_count() or 2)))
    return max(1, min(workers, unit_count, 8))


def _text_stats(text: str) -> Tuple[int, int]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    char_count = sum(len(line) for line in lines)
    return len(lines), char_count


def _text_line_lengths(text: str) -> List[int]:
    return [len(line.strip()) for line in text.splitlines() if line.strip()]


def _chart_text_heavy(lines: int, chars: int, ratio: float) -> bool:
    if lines <= CHART_TEXT_MAX_LINES:
        return False
    if chars < CHART_TEXT_MIN_CHARS:
        return False
    return ratio >= CHART_TEXT_RATIO_THRESHOLD


def _chart_is_label_dense_not_prose(text: str) -> bool:
    lengths = _text_line_lengths(text)
    if len(lengths) < CHART_LABEL_DENSE_MIN_LINES:
        return False
    avg_line_len = sum(lengths) / max(1, len(lengths))
    median_line_len = statistics.median(lengths)
    long_line_ratio = sum(
        1 for length in lengths if length >= CHART_LABEL_DENSE_LONG_LINE_LEN
    ) / max(1, len(lengths))
    short_line_ratio = sum(
        1 for length in lengths if length <= CHART_LABEL_DENSE_SHORT_LINE_LEN
    ) / max(1, len(lengths))
    return (
        avg_line_len <= CHART_LABEL_DENSE_MAX_AVG_LINE_LEN
        and median_line_len <= CHART_LABEL_DENSE_MAX_MEDIAN_LINE_LEN
        and long_line_ratio <= CHART_LABEL_DENSE_MAX_LONG_LINE_RATIO
        and short_line_ratio >= CHART_LABEL_DENSE_MIN_SHORT_LINE_RATIO
    )


def _infographic_is_label_dense_not_prose(text: str) -> bool:
    lengths = _text_line_lengths(text)
    if len(lengths) < CHART_LABEL_DENSE_MIN_LINES:
        return False
    avg_line_len = sum(lengths) / max(1, len(lengths))
    median_line_len = statistics.median(lengths)
    long_line_ratio = sum(
        1 for length in lengths if length >= CHART_LABEL_DENSE_LONG_LINE_LEN
    ) / max(1, len(lengths))
    short_line_ratio = sum(
        1 for length in lengths if length <= CHART_LABEL_DENSE_SHORT_LINE_LEN
    ) / max(1, len(lengths))
    return (
        avg_line_len <= INFOGRAPHIC_LABEL_DENSE_MAX_AVG_LINE_LEN
        and median_line_len <= INFOGRAPHIC_LABEL_DENSE_MAX_MEDIAN_LINE_LEN
        and long_line_ratio <= INFOGRAPHIC_LABEL_DENSE_MAX_LONG_LINE_RATIO
        and short_line_ratio >= INFOGRAPHIC_LABEL_DENSE_MIN_SHORT_LINE_RATIO
    )


def _trim_top_page_number(
    rect: fitz.Rect,
    page: fitz.Page,
    cap_rect: Optional[fitz.Rect],
) -> fitz.Rect:
    page_rect = page.rect
    top_band = page_rect.height * 0.15
    left_band = page_rect.x0 + page_rect.width * 0.25
    right_band = page_rect.x0 + page_rect.width * 0.55
    guard = max(page_rect.height * 0.008, 6.0)
    best_y1: Optional[float] = None
    try:
        blocks = page.get_text("blocks")
    except PDF_FIGURE_EXCEPTIONS:
        return rect
    for x0, y0, x1, y1, text, *_ in blocks:
        if not text:
            continue
        if not _is_page_number_text(text):
            continue
        block = fitz.Rect(x0, y0, x1, y1)
        if block.y0 > page_rect.y0 + top_band:
            continue
        in_left_corner = block.x1 <= left_band
        in_right_corner = block.x0 >= right_band
        if not in_left_corner and not in_right_corner:
            continue
        if not block.intersects(rect):
            continue
        if cap_rect is not None and block.y1 >= cap_rect.y0 - guard:
            continue
        if best_y1 is None or block.y1 > best_y1:
            best_y1 = block.y1
    if best_y1 is None:
        return rect
    new_top = max(rect.y0, best_y1 + guard)
    if new_top >= rect.y1:
        return rect
    return fitz.Rect(rect.x0, new_top, rect.x1, rect.y1)


def _rect_intersection_area(a: fitz.Rect, b: fitz.Rect) -> float:
    inter = a & b
    if inter.is_empty:
        return 0.0
    return max(0.0, inter.get_area())


def _tally_reason(stats: Dict[str, object], reason: str) -> None:
    reasons = stats.get("reasons")
    if not isinstance(reasons, dict):
        reasons = {}
        stats["reasons"] = reasons
    reasons[reason] = int(reasons.get(reason, 0)) + 1

__all__ = [name for name in globals() if not name.startswith("__")]
__all__ += ['_ChartRect', '_PageTextLine', '_s', '_int_count', '_rect_iou', '_table_normalize_text', '_starts_with_lower_alpha', '_table_page_text_lines', '_rect_containment_ratio', '_rect_seen', '_chart_candidate_score', '_find_overlapping_kept', '_rect_overlap_area', '_line_starts_with_caption_hint', '_alpha_ratio', '_is_page_number_text', '_horizontal_overlap_ratio', '_vertical_overlap_ratio', '_pad_rect', '_save_thumb', '_nearby_text', '_candidate_index_from_id', '_merge_stats', '_split_even_chunks', '_resolve_candidate_parallel_workers', '_text_stats', '_text_line_lengths', '_chart_text_heavy', '_chart_is_label_dense_not_prose', '_infographic_is_label_dense_not_prose', '_trim_top_page_number', '_rect_intersection_area', '_tally_reason']

from ._visual_heuristics.chart_layout import *
from ._visual_heuristics.chart_layout import __all__ as _chart_layout_all
from ._visual_heuristics.panel_detection import *
from ._visual_heuristics.panel_detection import __all__ as _panel_detection_all
from ._visual_heuristics.collectors import *
from ._visual_heuristics.collectors import __all__ as _collectors_all

__all__ += _chart_layout_all + _panel_detection_all + _collectors_all
