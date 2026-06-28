from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

import io
import math
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pymupdf as fitz
from PIL import Image
from ..parallel_helpers import (
    resolve_candidate_parallel_workers as _resolve_candidate_parallel_workers,
    split_even_chunks as _split_even_chunks,
    tally_reason as _tally_reason,
)

from .. import visual_heuristics as _boundary
from ..visual_heuristics import (
    _PAGE_NUMBER_RX,
    CHART_DEDUP_IOU,
    CHART_LABEL_DENSE_LONG_LINE_LEN,
    CHART_LABEL_DENSE_MAX_AVG_LINE_LEN,
    CHART_LABEL_DENSE_MAX_LONG_LINE_RATIO,
    CHART_LABEL_DENSE_MAX_MEDIAN_LINE_LEN,
    CHART_LABEL_DENSE_MIN_LINES,
    CHART_LABEL_DENSE_MIN_SHORT_LINE_RATIO,
    CHART_LABEL_DENSE_SHORT_LINE_LEN,
    CHART_OVERLAP_CONTAINMENT,
    CHART_OVERLAP_IOU,
    CHART_PAD_X_FRAC,
    CHART_PAD_Y_FRAC,
    CHART_TEXT_MAX_LINES,
    CHART_TEXT_MIN_CHARS,
    CHART_TEXT_RATIO_THRESHOLD,
    INFOGRAPHIC_LABEL_DENSE_MAX_AVG_LINE_LEN,
    INFOGRAPHIC_LABEL_DENSE_MAX_LONG_LINE_RATIO,
    INFOGRAPHIC_LABEL_DENSE_MAX_MEDIAN_LINE_LEN,
    INFOGRAPHIC_LABEL_DENSE_MIN_SHORT_LINE_RATIO,
    PDF_FIGURE_EXCEPTIONS,
)
from src.utils.path_utils import bounded_artifact_filename, safe_path_segment

globals().update(
    {
        name: value
        for name, value in vars(_boundary).items()
        if not name.startswith("__")
    }
)


@dataclass(frozen=True)
class _ChartRect:
    rect: fitz.Rect
    kind: str
    xref: Optional[int] = None
    caption: Optional[str] = None
    caption_rect: Optional[fitz.Rect] = None


@dataclass(frozen=True)
class _VisualCandidateRelationships:
    """Per-page visual-candidate lookup for relationship helpers.

    The index deliberately returns ordered supersets. Existing helper predicates
    still decide the exact semantics, while callers avoid scanning every visual
    item for relationships that can only involve candidates near the same page
    band.
    """

    page_rect: fitz.Rect
    candidates: Tuple[Any, ...]
    bin_height: float
    by_kind: Dict[str, Tuple[Any, ...]]
    y_bins_by_kind: Dict[str, Dict[int, Tuple[Any, ...]]]
    order_by_identity: Dict[int, int]

    @classmethod
    def build(
        cls,
        candidates: Iterable[Any],
        *,
        page_rect: fitz.Rect,
        bin_height: float = 96.0,
    ) -> "_VisualCandidateRelationships":
        items = tuple(candidates)
        resolved_page_rect = fitz.Rect(page_rect)
        resolved_bin_height = max(1.0, float(bin_height))
        order_by_identity = {
            id(candidate): index for index, candidate in enumerate(items)
        }
        by_kind_rows: Dict[str, List[Any]] = {}
        y_bin_rows: Dict[str, Dict[int, List[Any]]] = {}
        for candidate in items:
            kind = str(getattr(candidate, "kind", "") or "")
            if not kind:
                continue
            try:
                rect = fitz.Rect(getattr(candidate, "rect"))
            except PDF_FIGURE_EXCEPTIONS:
                continue
            if rect.is_empty:
                continue
            by_kind_rows.setdefault(kind, []).append(candidate)
            kind_bins = y_bin_rows.setdefault(kind, {})
            for bin_index in cls._bin_indexes_for_range(
                rect.y0,
                rect.y1,
                page_rect=resolved_page_rect,
                bin_height=resolved_bin_height,
            ):
                kind_bins.setdefault(bin_index, []).append(candidate)
        return cls(
            page_rect=resolved_page_rect,
            candidates=items,
            bin_height=resolved_bin_height,
            by_kind={kind: tuple(rows) for kind, rows in by_kind_rows.items()},
            y_bins_by_kind={
                kind: {bin_index: tuple(rows) for bin_index, rows in bins.items()}
                for kind, bins in y_bin_rows.items()
            },
            order_by_identity=order_by_identity,
        )

    @staticmethod
    def _bin_indexes_for_range(
        y0: float,
        y1: float,
        *,
        page_rect: fitz.Rect,
        bin_height: float,
    ) -> range:
        top = min(float(y0), float(y1))
        bottom = max(float(y0), float(y1))
        start = math.floor((top - page_rect.y0) / bin_height)
        end = math.floor((bottom - page_rect.y0) / bin_height)
        return range(int(start), int(end) + 1)

    def candidates_by_kind(self, kinds: Iterable[str]) -> Tuple[Any, ...]:
        rows: List[Any] = []
        for kind in kinds:
            rows.extend(self.by_kind.get(str(kind), ()))
        return self._ordered_unique(rows)

    def candidates_in_y_range(
        self,
        kinds: Iterable[str],
        y0: float,
        y1: float,
        *,
        pad: float = 0.0,
    ) -> Tuple[Any, ...]:
        rows: List[Any] = []
        bins = tuple(
            self._bin_indexes_for_range(
                float(y0) - float(pad),
                float(y1) + float(pad),
                page_rect=self.page_rect,
                bin_height=self.bin_height,
            )
        )
        for kind in kinds:
            by_bin = self.y_bins_by_kind.get(str(kind), {})
            for bin_index in bins:
                rows.extend(by_bin.get(bin_index, ()))
        return self._ordered_unique(rows)

    def candidates_intersecting_y(
        self,
        kinds: Iterable[str],
        rect: fitz.Rect,
        *,
        pad: float = 0.0,
    ) -> Tuple[Any, ...]:
        resolved = fitz.Rect(rect)
        return self.candidates_in_y_range(
            kinds,
            resolved.y0,
            resolved.y1,
            pad=pad,
        )

    def _ordered_unique(self, rows: Iterable[Any]) -> Tuple[Any, ...]:
        seen: set[int] = set()
        out: List[Any] = []
        for row in rows:
            identity = id(row)
            if identity in seen:
                continue
            seen.add(identity)
            out.append(row)
        out.sort(key=lambda row: self.order_by_identity.get(id(row), 0))
        return tuple(out)


class _VisualOverlapIndex:
    """Page-local y-band index for visual candidate overlap checks."""

    def __init__(
        self,
        *,
        page_rect: fitz.Rect,
        bin_height: float = 96.0,
    ) -> None:
        self._page_rect = fitz.Rect(page_rect)
        self._bin_height = max(1.0, float(bin_height))
        self._bins: Dict[int, List[int]] = {}
        self._bins_by_index: Dict[int, Tuple[int, ...]] = {}
        self._rects: Dict[int, fitz.Rect] = {}

    def add(self, index: int, rect: fitz.Rect) -> None:
        self.remove(index)
        resolved = fitz.Rect(rect)
        if resolved.is_empty or resolved.get_area() <= 0.0:
            return
        buckets = tuple(self._bin_indexes_for_rect(resolved))
        for bucket in buckets:
            self._bins.setdefault(bucket, []).append(index)
        self._bins_by_index[index] = buckets
        self._rects[index] = resolved

    def remove(self, index: int) -> None:
        previous = self._bins_by_index.pop(index, ())
        for bucket in previous:
            values = self._bins.get(bucket)
            if values is None:
                continue
            self._bins[bucket] = [value for value in values if value != index]
        self._rects.pop(index, None)

    def lookup(self, rect: fitz.Rect) -> List[int]:
        resolved = fitz.Rect(rect)
        if resolved.is_empty or resolved.get_area() <= 0.0:
            return []
        matches: Dict[int, None] = {}
        for bucket in self._bin_indexes_for_rect(resolved):
            for index in self._bins.get(bucket, []):
                existing = self._rects.get(index)
                if existing is None:
                    continue
                if self._intersects_y(resolved, existing):
                    matches[index] = None
        return sorted(matches)

    def _bin_indexes_for_rect(self, rect: fitz.Rect) -> range:
        return _VisualCandidateRelationships._bin_indexes_for_range(
            rect.y0,
            rect.y1,
            page_rect=self._page_rect,
            bin_height=self._bin_height,
        )

    @staticmethod
    def _intersects_y(left: fitz.Rect, right: fitz.Rect) -> bool:
        return min(left.y1, right.y1) > max(left.y0, right.y0)


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
    *,
    overlap_index: Optional[_VisualOverlapIndex] = None,
) -> Optional[int]:
    indexes = (
        overlap_index.lookup(rect) if overlap_index is not None else range(len(kept))
    )
    for idx in indexes:
        existing, _score, _out_idx = kept[idx]
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
        img = img.resize((max_w, new_h), Image.Resampling.LANCZOS)

    Path(out_dir).mkdir(parents=True, exist_ok=True)
    suffix = "" if index == 0 else str(index)
    filename = bounded_artifact_filename(
        f"{safe_report_name}{suffix}",
        compact_stem=f"thumb-{index}",
        extension=".png",
    )
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


__all__ = [
    "_ChartRect",
    "_VisualCandidateRelationships",
    "_VisualOverlapIndex",
    "_PageTextLine",
    "_s",
    "_int_count",
    "_rect_iou",
    "_table_normalize_text",
    "_starts_with_lower_alpha",
    "_table_page_text_lines",
    "_rect_containment_ratio",
    "_rect_seen",
    "_chart_candidate_score",
    "_find_overlapping_kept",
    "_rect_overlap_area",
    "_line_starts_with_caption_hint",
    "_alpha_ratio",
    "_is_page_number_text",
    "_horizontal_overlap_ratio",
    "_vertical_overlap_ratio",
    "_pad_rect",
    "_save_thumb",
    "_nearby_text",
    "_candidate_index_from_id",
    "_merge_stats",
    "_split_even_chunks",
    "_resolve_candidate_parallel_workers",
    "_text_stats",
    "_text_line_lengths",
    "_chart_text_heavy",
    "_chart_is_label_dense_not_prose",
    "_infographic_is_label_dense_not_prose",
    "_trim_top_page_number",
    "_rect_intersection_area",
    "_tally_reason",
]
