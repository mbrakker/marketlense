"""Capability module for chart and infographic candidate extraction.

This split keeps `figures.collect_candidates()` as the single service boundary
while isolating visual-candidate orchestration into its own upgrade surface.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
import math
from pathlib import Path
import re
from typing import Dict, List, Optional

import pymupdf as fitz
from PIL import Image, ImageFilter, ImageStat

from src.contracts.candidates import Candidate, CandidateFeatures

from .visual_heuristics import (
    CHART_CAPTION_HINTS,
    CHART_CAPTIONED_DRAW_MAX_ASPECT,
    CHART_DENSE_RECOVERY_MIN_CHARS,
    CHART_DENSE_RECOVERY_MIN_LINES,
    CHART_EDGE_TEXT_HEADING_GAP_SCALE,
    CHART_EDGE_TEXT_HEADING_GAP_X_SCALE,
    CHART_MARGIN_FRAC,
    CHART_MARGIN_RELAX_FRAC,
    INFO_CHART_MAX_ASPECT,
    PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD,
    _adjust_rect_for_text_margins,
    _candidate_index_from_id,
    _caption_near_top,
    _caption_blocks,
    _ChartRect,
    _chart_candidate_score,
    _infographic_is_label_dense_not_prose,
    _chart_is_label_dense_not_prose,
    _panel_chart_is_label_dense_not_prose,
    _chart_text_heavy,
    _clamp_bottom_to_next_chart_blocker,
    _clamp_bottom_to_note,
    _clamp_top_to_caption,
    _clamp_top_to_heading,
    _collect_chart_rects,
    _extend_chart_rect_with_adjacent_drawings,
    _expand_rect_into_whitespace,
    _extend_panel_with_adjacent_text_blocks,
    _extend_with_adjacent_text_blocks,
    _extend_with_heading_above,
    _extend_with_note_blocks,
    _find_overlapping_kept,
    _int_count,
    _is_page_number_text,
    _line_starts_with_caption_hint,
    _merge_caption_above,
    _merge_stats,
    _nearest_caption_block,
    _nearest_heading_above,
    _nearby_text,
    _note_block_bottom,
    _pad_rect,
    _panel_caption_looks_top_band,
    _panel_chart_has_data_signal,
    _panel_chart_has_compact_stat_card_signal,
    _panel_candidate_shadowed_by_heading_candidate,
    _panel_candidate_shadowed_by_larger_panel,
    _panel_chart_has_structured_card_signal,
    _panel_caption_looks_metric_stub,
    _panel_component_looks_like_guidance_card,
    _panel_component_looks_like_independent_data_panel,
    _panel_neighbor_x_bounds,
    _panel_stacked_bottom_clip_y,
    _panel_should_clamp_to_internal_caption,
    _panel_title_slice_bounds,
    _rect_iou,
    _rect_containment_ratio,
    _resolve_candidate_parallel_workers,
    _save_thumb,
    _split_even_chunks,
    _tally_reason,
    _text_stats,
    _trim_top_page_number,
    _vertical_overlap_ratio,
)
from .page_artifacts import (
    PdfPageArtifactCache,
    PdfPageArtifacts,
    get_page_artifacts,
)

PANEL_CHART_CONTEXT_TEXT_RATIO_MAX = 0.85
CONTEXTUAL_RASTER_CARD_MIN_AREA_FRAC = 0.18
CONTEXTUAL_RASTER_CARD_MAX_AREA_FRAC = 0.45
CONTEXTUAL_RASTER_CARD_MIN_WIDTH_FRAC = 0.35
CONTEXTUAL_RASTER_CARD_MAX_WIDTH_FRAC = 0.55
CONTEXTUAL_RASTER_CARD_MIN_HEIGHT_FRAC = 0.5
CONTEXTUAL_RASTER_CARD_MAX_HEIGHT_FRAC = 0.82
CONTEXTUAL_RASTER_CARD_MIN_X0_FRAC = 0.48
CONTEXTUAL_RASTER_CARD_MIN_X1_FRAC = 0.88
CONTEXTUAL_RASTER_CARD_MAX_SAT_MEAN = 95.0
CONTEXTUAL_RASTER_CARD_MAX_DARK_FRAC = 0.12
CONTEXTUAL_RASTER_CARD_MIN_EDGE_DENSITY = 0.07
CONTEXTUAL_RASTER_CARD_MAX_EDGE_DENSITY = 0.095
CONTEXTUAL_RASTER_CARD_MIN_LEFT_CONTEXT_CHARS = 140
CONTEXTUAL_RASTER_CARD_MIN_LEFT_CONTEXT_BLOCKS = 1
PHOTO_LIKE_RASTER_MAX_WHITE_FRAC = 0.30
PHOTO_LIKE_RASTER_MIN_SAT_MEAN = 60.0
PHOTO_LIKE_RASTER_MIN_EDGE_DENSITY = 0.08
PHOTO_LIKE_RASTER_MIN_DARK_FRAC = 0.03
SMALL_DECORATIVE_RASTER_MAX_AREA_FRAC = 0.12
SMALL_DECORATIVE_RASTER_MAX_TEXT_CHARS = 180
_VISUAL_CONTEXT_LINE_RX = re.compile(
    r"^\s*(?:figure|fig\.|exhibit|chart|graph|source|infographic)\b",
    re.IGNORECASE,
)
_FIGURE_HINT_RX = re.compile(
    r"^\s*(?:figure|fig\.|exhibit|chart|graph|infographic)\b",
    re.IGNORECASE,
)
_BOX_HINT_RX = re.compile(r"^\s*box\b", re.IGNORECASE)
_URL_REF_RX = re.compile(r"https?://|doi\.org|www\.", re.IGNORECASE)
_SOURCE_OR_STATLINK_RX = re.compile(r"(?im)(?:^|\n)\s*(?:source:|statlink\b)")
_EXPLANATORY_FIGURE_REF_RX = re.compile(
    r"^\s*(?:figure|fig\.|chart|exhibit|infographic)\s+\d+(?:\.\d+)?(?:\s*[,:\-]\s*|\s+)"
    r"(?:[\w’'/-]+\s+){0,8}"
    r"(?:is|was|are|were|shows?|showing|illustrates?|describes?|presents?|"
    r"reflects?|compares?|compared|highlights?|based\s+on)\b",
    re.IGNORECASE,
)
_YEAR_RX = re.compile(r"\b(?:19|20)\d{2}[a-z]?\b")
_NUMBER_RX = re.compile(r"\b\d+(?:\.\d+)?\b")
_TERMINAL_INTEGER_RX = re.compile(r"\b\d{1,4}\s*$")
_BARE_TITLE_HEADING_RX = re.compile(
    r"^[A-Z][A-Za-z'’.-]*(?:\s+[A-Z][A-Za-z'’.-]*){0,2}$"
)
_MID_SENTENCE_START_WORDS = {
    "after",
    "although",
    "amid",
    "because",
    "but",
    "continue",
    "despite",
    "following",
    "growth",
    "however",
    "mainly",
    "monthly",
    "quarterly",
    "strong",
    "the",
    "top-up",
    "while",
}


@dataclass(frozen=True)
class _VisualPageContext:
    page_number: int
    page: fitz.Page
    page_rect: fitz.Rect
    page_chars: int
    top_cut: float
    bot_cut: float
    relaxed_top: float
    relaxed_bot: float
    page_has_chart_captions: bool
    artifacts: PdfPageArtifacts
    rect_items: List[_ChartRect]
    probe_cache: _RasterProbeCache


@dataclass
class _VisualPageCandidateEntry:
    candidate: Candidate
    rect: fitz.Rect
    score: float
    sequence: int
    recovered_only: bool


@dataclass
class _RasterProbeCache:
    images: dict[tuple[object, ...], Optional[Image.Image]]
    profiles: dict[tuple[object, ...], Optional[dict[str, float]]]
    hits: int = 0
    misses: int = 0

    @staticmethod
    def _rect_key(rect: fitz.Rect) -> tuple[float, float, float, float]:
        return (
            round(float(rect.x0), 3),
            round(float(rect.y0), 3),
            round(float(rect.x1), 3),
            round(float(rect.y1), 3),
        )

    def image_key(
        self,
        page: fitz.Page,
        rect: fitz.Rect,
        *,
        max_dim_px: int,
    ) -> tuple[object, ...]:
        return (
            "raster_image",
            int(getattr(page, "number", 0) or 0),
            self._rect_key(rect),
            int(max_dim_px),
            "rgb",
        )

    def profile_key(
        self,
        page: fitz.Page,
        rect: fitz.Rect,
        *,
        max_dim_px: int,
    ) -> tuple[object, ...]:
        return (
            "raster_profile",
            int(getattr(page, "number", 0) or 0),
            self._rect_key(rect),
            int(max_dim_px),
            "white_dark_saturation_edges",
        )

    def record_image(
        self,
        key: tuple[object, ...],
        image: Optional[Image.Image],
    ) -> Optional[Image.Image]:
        self.images[key] = image
        return image

    def image_or_none(self, key: tuple[object, ...]) -> Optional[Image.Image]:
        if key in self.images:
            self.hits += 1
            return self.images[key]
        self.misses += 1
        return None

    def record_profile(
        self,
        key: tuple[object, ...],
        profile: Optional[dict[str, float]],
    ) -> Optional[dict[str, float]]:
        self.profiles[key] = profile
        return profile

    def profile_or_none(
        self,
        key: tuple[object, ...],
    ) -> Optional[dict[str, float]]:
        if key in self.profiles:
            self.hits += 1
            return self.profiles[key]
        self.misses += 1
        return None

    def stats(self) -> dict[str, int]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "image_entries": len(self.images),
            "profile_entries": len(self.profiles),
        }


def _iter_visual_context_lines(text: str, *, max_lines: int = 4, max_chars: int = 200):
    seen_lines = 0
    seen_chars = 0
    for raw_line in str(text or "").splitlines():
        normalized = raw_line.strip()
        if not normalized:
            continue
        yield normalized
        seen_lines += 1
        seen_chars += len(normalized)
        if seen_lines >= max_lines or seen_chars >= max_chars:
            break


def _has_side_by_side_visual_sibling(
    rect_item,
    candidates,
    page_rect: fitz.Rect,
) -> bool:
    for other in candidates:
        if other is rect_item:
            continue
        if other.kind not in ("xref", "block"):
            continue
        other_rect = other.rect
        if _rect_iou(other_rect, rect_item.rect) >= 0.95:
            continue
        if _vertical_overlap_ratio(other_rect, rect_item.rect) < 0.6:
            continue
        horizontal_gap = max(
            0.0,
            max(rect_item.rect.x0, other_rect.x0)
            - min(rect_item.rect.x1, other_rect.x1),
        )
        if horizontal_gap > page_rect.width * 0.12:
            continue
        if other_rect.get_area() <= 0.0:
            continue
        area_ratio = rect_item.rect.get_area() / other_rect.get_area()
        if area_ratio < 0.45 or area_ratio > 2.2:
            continue
        return True
    return False


def _render_visual_probe_image(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    max_dim_px: int = 320,
    probe_cache: Optional[_RasterProbeCache] = None,
) -> Optional[Image.Image]:
    cache_key = (
        probe_cache.image_key(page, rect, max_dim_px=max_dim_px)
        if probe_cache is not None
        else None
    )
    if (
        probe_cache is not None
        and cache_key is not None
        and cache_key in probe_cache.images
    ):
        probe_cache.hits += 1
        return probe_cache.images[cache_key]
    if probe_cache is not None:
        probe_cache.misses += 1
    clip = fitz.Rect(rect) & page.rect
    if clip.is_empty or clip.width <= 1.0 or clip.height <= 1.0:
        return (
            probe_cache.record_image(cache_key, None)
            if probe_cache is not None and cache_key is not None
            else None
        )
    max_dim = max(float(clip.width), float(clip.height))
    scale = min(1.0, max_dim_px / max(1.0, max_dim))
    scale = max(0.35, scale)
    try:
        pix = page.get_pixmap(
            clip=clip,
            matrix=fitz.Matrix(scale, scale),
            alpha=False,
        )
    except Exception:
        return (
            probe_cache.record_image(cache_key, None)
            if probe_cache is not None and cache_key is not None
            else None
        )
    image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return (
        probe_cache.record_image(cache_key, image)
        if probe_cache is not None and cache_key is not None
        else image
    )


def _visual_probe_profile(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    probe_cache: Optional[_RasterProbeCache] = None,
) -> Optional[dict[str, float]]:
    cache_key = (
        probe_cache.profile_key(page, rect, max_dim_px=320)
        if probe_cache is not None
        else None
    )
    if (
        probe_cache is not None
        and cache_key is not None
        and cache_key in probe_cache.profiles
    ):
        probe_cache.hits += 1
        return probe_cache.profiles[cache_key]
    if probe_cache is not None:
        probe_cache.misses += 1
    image = _render_visual_probe_image(page, rect, probe_cache=probe_cache)
    if image is None:
        return (
            probe_cache.record_profile(cache_key, None)
            if probe_cache is not None and cache_key is not None
            else None
        )
    rgb = image.convert("RGB")
    gray = rgb.convert("L")
    hsv = rgb.convert("HSV")
    total_pixels = max(1, rgb.width * rgb.height)

    gray_hist = gray.histogram()
    white_frac = sum(gray_hist[241:]) / total_pixels
    dark_frac = sum(gray_hist[:40]) / total_pixels
    visual_entropy = 0.0
    for count in gray_hist:
        if count <= 0:
            continue
        probability = count / total_pixels
        visual_entropy -= probability * math.log2(probability)
    visual_entropy = min(1.0, max(0.0, visual_entropy / 8.0))

    saturation = hsv.split()[1]
    sat_mean = ImageStat.Stat(saturation).mean[0]

    edges = gray.filter(ImageFilter.FIND_EDGES)
    edge_hist = edges.histogram()
    edge_density = sum(edge_hist[36:]) / total_pixels

    profile = {
        "white_frac": float(white_frac),
        "dark_frac": float(dark_frac),
        "sat_mean": float(sat_mean),
        "edge_density": float(edge_density),
        "visual_entropy": float(visual_entropy),
    }
    return (
        probe_cache.record_profile(cache_key, profile)
        if probe_cache is not None and cache_key is not None
        else profile
    )


def _embedded_visual_looks_chart_like(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    probe_cache: Optional[_RasterProbeCache] = None,
) -> bool:
    profile = _visual_probe_profile(page, rect, probe_cache=probe_cache)
    if profile is None:
        return False
    white_frac = profile["white_frac"]
    sat_mean = profile["sat_mean"]
    edge_density = profile["edge_density"]
    return (white_frac >= 0.28 and sat_mean <= 95.0 and edge_density >= 0.008) or (
        white_frac >= 0.62 and sat_mean <= 70.0
    )


def _bounded_quality(value: float) -> float:
    if not math.isfinite(value):
        return 0.0
    return min(1.0, max(0.0, value))


def _candidate_ocr_density(text_chars: int, area_frac: float) -> float:
    if text_chars <= 0 or area_frac <= 0.0:
        return 0.0
    return round(float(text_chars) / max(1.0, float(area_frac) * 100.0), 2)


def _chart_confidence_score(
    *,
    area_frac: float,
    has_context_hint: bool,
    caption: str,
    bbox_text: str,
    text_lines: int,
    text_chars: int,
    note_included: bool,
    profile: Optional[dict[str, float]],
) -> float:
    area_score = _bounded_quality(area_frac / 0.18) * 0.22
    caption_score = 0.16 if caption.strip() else 0.0
    context_score = 0.16 if has_context_hint else 0.0
    note_score = 0.06 if note_included else 0.0
    text_score = 0.0
    if _chart_is_label_dense_not_prose(bbox_text) or _panel_chart_has_data_signal(
        bbox_text
    ):
        text_score = 0.22
    elif text_lines >= 3 and text_chars >= 40:
        text_score = 0.12

    visual_score = 0.0
    if profile is not None:
        entropy = float(profile.get("visual_entropy", 0.0) or 0.0)
        edge_density = float(profile.get("edge_density", 0.0) or 0.0)
        white_frac = float(profile.get("white_frac", 0.0) or 0.0)
        entropy_score = _bounded_quality(entropy / 0.55)
        edge_score = _bounded_quality(edge_density / 0.08)
        background_score = 1.0 if white_frac >= 0.18 else 0.65
        visual_score = min(entropy_score, edge_score, background_score) * 0.18

    return round(
        _bounded_quality(
            area_score
            + caption_score
            + context_score
            + note_score
            + text_score
            + visual_score
        ),
        3,
    )


def _embedded_visual_looks_decorative(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    probe_cache: Optional[_RasterProbeCache] = None,
) -> bool:
    profile = _visual_probe_profile(page, rect, probe_cache=probe_cache)
    if profile is None:
        return False
    return (
        profile["white_frac"] <= 0.22
        and profile["sat_mean"] >= 90.0
        and profile["edge_density"] <= 0.10
    )


def _embedded_visual_looks_photo_like(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    probe_cache: Optional[_RasterProbeCache] = None,
) -> bool:
    profile = _visual_probe_profile(page, rect, probe_cache=probe_cache)
    if profile is None:
        return False
    if profile["white_frac"] > PHOTO_LIKE_RASTER_MAX_WHITE_FRAC:
        return False
    if profile["edge_density"] < PHOTO_LIKE_RASTER_MIN_EDGE_DENSITY:
        return False
    return (
        profile["sat_mean"] >= PHOTO_LIKE_RASTER_MIN_SAT_MEAN
        or profile["dark_frac"] >= PHOTO_LIKE_RASTER_MIN_DARK_FRAC
    )


def _embedded_visual_is_oversized_wrapper(
    rect_item,
    candidates,
    page_rect: fitz.Rect,
) -> bool:
    if rect_item.kind != "xref":
        return False
    rect = fitz.Rect(rect_item.rect)
    overflow_x = max(0.0, page_rect.x0 - rect.x0) + max(0.0, rect.x1 - page_rect.x1)
    overflow_y = max(0.0, page_rect.y0 - rect.y0) + max(0.0, rect.y1 - page_rect.y1)
    if overflow_x <= page_rect.width * 0.04 and overflow_y <= page_rect.height * 0.04:
        return False
    clipped_rect = rect & page_rect
    clipped_area = clipped_rect.get_area()
    if clipped_area <= 0.0:
        return False
    for other in candidates:
        if other is rect_item or other.kind not in ("xref", "block"):
            continue
        other_rect = fitz.Rect(other.rect) & page_rect
        if other_rect.is_empty or other_rect.get_area() <= 0.0:
            continue
        if _rect_containment_ratio(other_rect, clipped_rect) < 0.95:
            continue
        if other_rect.get_area() < clipped_area * 0.12:
            continue
        if other_rect.get_area() > clipped_area * 0.75:
            continue
        if (
            other_rect.x0 < page_rect.x0 - 1.0
            or other_rect.x1 > page_rect.x1 + 1.0
            or other_rect.y0 < page_rect.y0 - 1.0
            or other_rect.y1 > page_rect.y1 + 1.0
        ):
            continue
        return True
    return False


def _embedded_visual_qualifies_relaxed_geometry(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    area_frac: float,
    probe_cache: Optional[_RasterProbeCache] = None,
) -> bool:
    if area_frac < 0.12:
        return False
    profile = _visual_probe_profile(page, rect, probe_cache=probe_cache)
    if profile is None:
        return False
    return (
        profile["white_frac"] >= 0.40
        and profile["sat_mean"] <= 60.0
        and profile["edge_density"] >= 0.05
    )


def _left_side_context_signal(
    blocks: List[tuple[float, float, float, float, str]],
    rect: fitz.Rect,
    page_rect: fitz.Rect,
) -> tuple[int, int]:
    left_boundary = rect.x0 - page_rect.width * 0.02
    top = max(page_rect.y0, rect.y0 - page_rect.height * 0.08)
    bottom = min(page_rect.y1, rect.y1 + page_rect.height * 0.08)
    chars = 0
    matched_blocks = 0
    for x0, y0, x1, y1, text in blocks:
        if x1 > left_boundary or x0 >= rect.x0:
            continue
        if y1 < top or y0 > bottom:
            continue
        compact = " ".join(str(text or "").split())
        if not compact or _is_page_number_text(compact):
            continue
        _, block_chars = _text_stats(compact)
        if block_chars < 40:
            continue
        chars += block_chars
        matched_blocks += 1
    return chars, matched_blocks


def _embedded_visual_qualifies_contextual_card(
    page: fitz.Page,
    rect: fitz.Rect,
    *,
    area_frac: float,
    blocks: List[tuple[float, float, float, float, str]],
    probe_cache: Optional[_RasterProbeCache] = None,
) -> bool:
    if (
        area_frac < CONTEXTUAL_RASTER_CARD_MIN_AREA_FRAC
        or area_frac > CONTEXTUAL_RASTER_CARD_MAX_AREA_FRAC
    ):
        return False
    page_rect = page.rect
    width_frac = rect.width / max(1.0, page_rect.width)
    height_frac = rect.height / max(1.0, page_rect.height)
    x0_frac = rect.x0 / max(1.0, page_rect.width)
    x1_frac = rect.x1 / max(1.0, page_rect.width)
    if not (
        CONTEXTUAL_RASTER_CARD_MIN_WIDTH_FRAC
        <= width_frac
        <= CONTEXTUAL_RASTER_CARD_MAX_WIDTH_FRAC
    ):
        return False
    if not (
        CONTEXTUAL_RASTER_CARD_MIN_HEIGHT_FRAC
        <= height_frac
        <= CONTEXTUAL_RASTER_CARD_MAX_HEIGHT_FRAC
    ):
        return False
    if (
        x0_frac < CONTEXTUAL_RASTER_CARD_MIN_X0_FRAC
        or x1_frac < CONTEXTUAL_RASTER_CARD_MIN_X1_FRAC
    ):
        return False
    left_chars, left_blocks = _left_side_context_signal(blocks, rect, page_rect)
    if (
        left_blocks < CONTEXTUAL_RASTER_CARD_MIN_LEFT_CONTEXT_BLOCKS
        or left_chars < CONTEXTUAL_RASTER_CARD_MIN_LEFT_CONTEXT_CHARS
    ):
        return False
    profile = _visual_probe_profile(page, rect, probe_cache=probe_cache)
    if profile is None:
        return False
    return (
        profile["sat_mean"] <= CONTEXTUAL_RASTER_CARD_MAX_SAT_MEAN
        and profile["dark_frac"] <= CONTEXTUAL_RASTER_CARD_MAX_DARK_FRAC
        and profile["edge_density"] >= CONTEXTUAL_RASTER_CARD_MIN_EDGE_DENSITY
        and profile["edge_density"] <= CONTEXTUAL_RASTER_CARD_MAX_EDGE_DENSITY
    )


def _page_has_chart_caption_blocks(
    blocks: List[tuple[float, float, float, float, str]],
) -> bool:
    for _x0, _y0, _x1, _y1, text in blocks:
        for normalized in _iter_visual_context_lines(text):
            normalized = normalized.lower()
            if _line_starts_with_caption_hint(normalized, CHART_CAPTION_HINTS):
                return True
    return False


def _text_has_visual_context_hint(text: str) -> bool:
    for normalized in _iter_visual_context_lines(text):
        if _VISUAL_CONTEXT_LINE_RX.match(normalized):
            return True
    return False


def _visual_nonempty_lines(text: str) -> List[str]:
    return [line.strip() for line in str(text or "").splitlines() if line.strip()]


def _caption_has_figure_hint(text: str) -> bool:
    return bool(_FIGURE_HINT_RX.match(str(text or "").strip()))


def _caption_looks_explanatory_figure_reference(text: str) -> bool:
    return bool(_EXPLANATORY_FIGURE_REF_RX.match(str(text or "").strip()))


def _caption_looks_bare_title_heading(text: str) -> bool:
    caption = str(text or "").strip()
    if not caption or _caption_has_figure_hint(caption):
        return False
    if any(ch.isdigit() for ch in caption):
        return False
    return bool(_BARE_TITLE_HEADING_RX.fullmatch(caption))


def _caption_looks_mid_sentence_fragment(text: str) -> bool:
    caption = str(text or "").strip()
    if not caption or _caption_has_figure_hint(caption):
        return False
    if caption.lower().startswith(("source:", "statlink")):
        return False
    if caption[0].islower() or caption[0] in "(+%":
        return True
    words = [word for word in re.split(r"\s+", caption) if word]
    if len(words) < 5:
        return False
    first = words[0].strip("“\"'([{").lower()
    return first in _MID_SENTENCE_START_WORDS


def _visual_candidate_looks_table_like(
    caption: str,
    text: str,
    *,
    kind: str = "",
    panel_data_signal: bool = False,
) -> bool:
    if _caption_has_figure_hint(caption):
        return False
    lines = _visual_nonempty_lines(text)
    if len(lines) < 6:
        return False
    total_chars = sum(len(line) for line in lines)
    avg_line_len = total_chars / max(1, len(lines))
    short_line_ratio = sum(1 for line in lines if len(line) <= 28) / max(1, len(lines))
    numeric_row_hits = sum(1 for line in lines if len(_NUMBER_RX.findall(line)) >= 3)
    terminal_numeric_hits = sum(
        1
        for line in lines
        if _TERMINAL_INTEGER_RX.search(line) and len(_NUMBER_RX.findall(line)) >= 1
    )
    single_token_numeric_hits = sum(
        1
        for line in lines
        if len(line.split()) == 1 and bool(_NUMBER_RX.fullmatch(line))
    )
    alpha_line_ratio = sum(
        1 for line in lines if any(ch.isalpha() for ch in line)
    ) / max(1, len(lines))
    mixed_alpha_numeric_hits = sum(
        1
        for line in lines
        if any(ch.isalpha() for ch in line) and bool(_NUMBER_RX.search(line))
    )
    dense_year_header = any(
        len(_YEAR_RX.findall(line)) >= 3 for line in lines[: min(4, len(lines))]
    )
    lower_text = text.lower()
    lower_lines = [line.lower() for line in lines]
    if (
        numeric_row_hits >= 4
        and avg_line_len <= 44.0
        and (short_line_ratio >= 0.15 or dense_year_header or len(lines) <= 8)
    ):
        return True
    if (
        dense_year_header
        and any("current prices" in line for line in lower_lines)
        and (
            any("percentage changes" in line for line in lower_lines)
            or any("volume" in line for line in lower_lines)
        )
        and (
            numeric_row_hits >= 1
            or "memorandum items" in lower_text
            or len(lines) >= 10
        )
    ):
        return True
    if (
        kind == "panel"
        and panel_data_signal
        and numeric_row_hits < 3
        and dense_year_header is False
        and alpha_line_ratio < 0.45
        and single_token_numeric_hits >= max(6, len(lines) // 3)
    ):
        return False
    if (
        kind == "panel"
        and panel_data_signal
        and len(lines) <= 12
        and numeric_row_hits == 0
        and terminal_numeric_hits >= 4
        and single_token_numeric_hits >= 4
        and alpha_line_ratio >= 0.2
        and mixed_alpha_numeric_hits >= 1
    ):
        return False
    if (
        terminal_numeric_hits >= max(6, math.ceil(len(lines) * 0.25))
        and short_line_ratio >= 0.55
        and avg_line_len <= 24.0
    ):
        return True
    if dense_year_header and numeric_row_hits >= 2 and avg_line_len <= 30.0:
        return True
    return (
        len(lines) >= 18
        and short_line_ratio >= 0.7
        and avg_line_len <= 18.0
        and numeric_row_hits >= 3
    )


def _visual_candidate_looks_note_fragment(
    caption: str,
    text: str,
    *,
    kind: str,
) -> bool:
    if kind != "panel":
        return False
    if _caption_has_figure_hint(caption):
        return False
    caption_text = str(caption or "").strip()
    lower_caption = caption_text.lower()
    if not caption_text:
        return False
    if not _SOURCE_OR_STATLINK_RX.search(text):
        return False
    if (
        _panel_chart_has_data_signal(text)
        or _panel_chart_has_structured_card_signal(text)
        or _panel_component_looks_like_guidance_card(text)
        or _chart_is_label_dense_not_prose(text)
        or (kind == "panel" and _panel_chart_is_label_dense_not_prose(text))
    ):
        return False
    lines = _visual_nonempty_lines(text)
    if not lines:
        return False
    total_chars = sum(len(line) for line in lines)
    avg_line_len = total_chars / max(1, len(lines))
    numeric_hits = len(_NUMBER_RX.findall(text))
    numbered_hits = len(re.findall(r"(?m)^\s*\d+\.\s+", text))
    if lower_caption.startswith(("source:", "statlink")):
        return True
    if (
        _caption_looks_mid_sentence_fragment(caption_text)
        and len(lines) <= 10
        and avg_line_len <= 56.0
        and numeric_hits <= 10
    ):
        return True
    return (
        numbered_hits >= 1
        and len(lines) <= 8
        and avg_line_len <= 52.0
        and numeric_hits <= 12
    )


def _visual_candidate_looks_bare_heading_fragment(
    caption: str,
    text: str,
    *,
    kind: str,
    area_frac: float,
    aspect: float,
) -> bool:
    if kind != "panel":
        return False
    if not _caption_looks_bare_title_heading(caption):
        return False
    if _SOURCE_OR_STATLINK_RX.search(text):
        return False
    if (
        _panel_chart_has_data_signal(text)
        or _panel_chart_has_structured_card_signal(text)
        or _panel_component_looks_like_guidance_card(text)
        or _chart_is_label_dense_not_prose(text)
        or (kind == "panel" and _panel_chart_is_label_dense_not_prose(text))
    ):
        return False
    lines = _visual_nonempty_lines(text)
    total_chars = sum(len(line) for line in lines)
    return total_chars <= 24 and area_frac <= 0.18 and aspect >= 1.4


def _visual_candidate_looks_reference_or_prose(
    caption: str,
    text: str,
    *,
    text_ratio: float,
) -> bool:
    explanatory_figure_reference = _caption_looks_explanatory_figure_reference(caption)
    if _caption_has_figure_hint(caption) and not explanatory_figure_reference:
        return False
    lines = _visual_nonempty_lines(text)
    total_chars = sum(len(line) for line in lines)
    avg_line_len = total_chars / max(1, len(lines))
    numeric_hits = len(_NUMBER_RX.findall(text))
    year_hits = len(_YEAR_RX.findall(text))
    url_hits = len(_URL_REF_RX.findall(text))
    numbered_hits = len(re.findall(r"(?m)^\s*\d+\.\s+", text))
    colon_hits = sum(1 for line in lines if ":" in line and len(line) <= 100)
    short_line_ratio = sum(1 for line in lines if len(line) <= 28) / max(1, len(lines))
    sentence_hits = len(re.findall(r"[.!?;](?:\s|$)", text))
    if (
        explanatory_figure_reference
        and len(lines) >= 4
        and avg_line_len >= 55.0
        and text_ratio >= 0.18
    ):
        return True
    if len(lines) < 6:
        return False
    if (
        len(lines) >= 10
        and avg_line_len >= 26.0
        and text_ratio >= 0.16
        and numeric_hits <= max(8, len(lines) // 2)
        and not _panel_chart_has_data_signal(text)
        and not _panel_component_looks_like_guidance_card(text)
    ):
        return True
    if (
        url_hits == 0
        and len(lines) <= 18
        and avg_line_len <= 60.0
        and colon_hits >= 3
        and short_line_ratio >= 0.15
    ):
        return False
    if (
        url_hits >= 1
        and year_hits >= 2
        and (numbered_hits >= 2 or avg_line_len >= 42.0)
    ):
        return True
    if (
        _BOX_HINT_RX.match(str(caption or "").strip())
        and len(lines) >= 6
        and avg_line_len >= 32.0
        and text_ratio >= 0.2
    ):
        return True
    if (
        numbered_hits >= 2
        and len(lines) >= 18
        and avg_line_len >= 34.0
        and text_ratio >= 0.28
    ):
        return True
    if (
        len(lines) >= 16
        and avg_line_len >= 60.0
        and text_ratio >= 0.22
        and sentence_hits >= 4
        and not _SOURCE_OR_STATLINK_RX.search(text)
    ):
        return True
    if (
        len(lines) >= 18
        and avg_line_len >= 48.0
        and text_ratio >= 0.22
        and sentence_hits >= 3
        and numbered_hits >= 1
    ):
        return True
    return (
        len(lines) >= 12
        and avg_line_len >= 40.0
        and text_ratio >= 0.25
        and numeric_hits <= max(6, len(lines) // 3)
    )


def _visual_candidate_looks_cover_art(
    rect_candidate: fitz.Rect,
    page_rect: fitz.Rect,
    caption: str,
    *,
    area_frac: float,
    text_chars: int,
) -> bool:
    if _caption_has_figure_hint(caption):
        return False
    caption_text = str(caption or "").strip()
    width_frac = rect_candidate.width / max(1.0, page_rect.width)
    height_frac = rect_candidate.height / max(1.0, page_rect.height)
    top_frac = (rect_candidate.y0 - page_rect.y0) / max(1.0, page_rect.height)
    if area_frac < 0.12:
        return False
    if (
        area_frac >= 0.25
        and width_frac >= 0.6
        and height_frac >= 0.42
        and text_chars <= 90
        and len(caption_text) <= 24
        and len(caption_text.split()) <= 3
    ):
        return True
    if top_frac > 0.1:
        return False
    if height_frac > 0.35:
        return False
    return text_chars <= 80 and len(caption_text) <= 20


def _visual_candidate_looks_section_opener_banner(
    rect_candidate: fitz.Rect,
    page_rect: fitz.Rect,
    caption: str,
    text: str,
    *,
    kind: str,
    area_frac: float,
) -> bool:
    if _caption_has_figure_hint(caption):
        return False
    if rect_candidate.y0 > page_rect.y0 + page_rect.height * 0.08:
        return False
    if rect_candidate.height > page_rect.height * 0.42:
        return False
    if area_frac < 0.12 or area_frac > 0.34:
        return False
    if rect_candidate.width / max(1.0, page_rect.width) < 0.65:
        return False
    caption_text = str(caption or "").strip()
    words = caption_text.split()
    if not caption_text or len(words) > 12:
        return False
    if _SOURCE_OR_STATLINK_RX.search(text):
        return False
    lines = _visual_nonempty_lines(text)
    if not lines:
        return False
    total_chars = sum(len(line) for line in lines)
    avg_line_len = total_chars / max(1, len(lines))
    numeric_hits = len(_NUMBER_RX.findall(text))
    short_line_ratio = sum(1 for line in lines if len(line) <= 20) / max(1, len(lines))
    fragmented_banner_text = (
        len(lines) >= 10
        and avg_line_len <= 14.0
        and short_line_ratio >= 0.7
        and numeric_hits <= 4
    )
    if (
        (_panel_chart_has_data_signal(text) and not fragmented_banner_text)
        or _panel_component_looks_like_guidance_card(text)
        or _panel_chart_has_structured_card_signal(text)
    ):
        return False
    return numeric_hits <= 2 and (
        (len(lines) <= 4 and total_chars <= 160 and avg_line_len <= 40.0)
        or (len(lines) <= 24 and total_chars <= 280 and avg_line_len <= 22.0)
    )


def _visual_candidate_looks_photo_narrative_card(
    page: fitz.Page,
    rect_candidate: fitz.Rect,
    caption: str,
    *,
    caption_rect: Optional[fitz.Rect],
    kind: str,
    area_frac: float,
    aspect: float,
    text_chars: int,
    panel_data_signal: bool,
    probe_cache: Optional[_RasterProbeCache] = None,
) -> bool:
    if kind != "panel":
        return False
    if _caption_has_figure_hint(caption):
        return False
    if panel_data_signal:
        return False
    if area_frac < 0.22 or area_frac > 0.5:
        return False
    if aspect < 0.72 or aspect > 1.25:
        return False
    if text_chars > 40:
        return False
    if caption_rect is None:
        return False
    inter = caption_rect & rect_candidate
    if inter.is_empty or inter.get_area() < caption_rect.get_area() * 0.9:
        return False
    words = [word for word in str(caption or "").split() if word]
    if len(words) < 5 or len(words) > 16:
        return False
    if ":" in str(caption or ""):
        return False
    return _embedded_visual_looks_photo_like(
        page,
        rect_candidate,
        probe_cache=probe_cache,
    )


def _visual_candidate_looks_narrative_panel_card(
    caption: str,
    text: str,
    *,
    kind: str,
    text_ratio: float,
    area_frac: float,
) -> bool:
    if kind != "panel":
        return False
    if _caption_has_figure_hint(caption):
        return False
    if area_frac < 0.12:
        return False
    lines = _visual_nonempty_lines(text)
    if len(lines) < 8:
        return False
    total_chars = sum(len(line) for line in lines)
    avg_line_len = total_chars / max(1, len(lines))
    numeric_hits = len(_NUMBER_RX.findall(text))
    numeric_row_hits = sum(1 for line in lines if len(_NUMBER_RX.findall(line)) >= 2)
    sentence_hits = len(re.findall(r"[.!?;](?:\s|$)", text))
    colon_hits = sum(1 for line in lines if ":" in line and len(line) <= 100)
    short_line_ratio = sum(1 for line in lines if len(line) <= 28) / max(1, len(lines))
    long_line_hits = sum(1 for line in lines if len(line) >= 30)
    has_data_signal = _panel_chart_has_data_signal(text)
    if _panel_component_looks_like_guidance_card(text):
        return False
    structured_card_signal = _panel_chart_has_structured_card_signal(text)
    if structured_card_signal and sentence_hits < 3:
        return False
    if _panel_chart_has_compact_stat_card_signal(text):
        return False
    fragmented_prose = text_ratio >= 0.3 and sentence_hits >= 3 and long_line_hits >= 8
    if _SOURCE_OR_STATLINK_RX.search(text):
        return False
    if colon_hits >= 3 and short_line_ratio >= 0.2:
        return False
    if has_data_signal and (
        numeric_row_hits >= 3 or (short_line_ratio >= 0.35 and not fragmented_prose)
    ):
        return False
    return (
        text_ratio >= 0.22
        and sentence_hits >= 2
        and numeric_hits <= max(12, len(lines))
        and (avg_line_len >= 28.0 or fragmented_prose)
    )


def _visual_candidate_looks_inline_numbered_panel(
    caption: str,
    text: str,
    *,
    note_included: bool,
    area_frac: float,
    aspect: float,
) -> bool:
    if _caption_has_figure_hint(caption):
        return False
    caption_text = str(caption or "").strip()
    if not re.search(r"\b\d\b\s*$", caption_text):
        return False
    if _YEAR_RX.search(caption_text):
        return False
    if not note_included:
        return False
    if area_frac > 0.24 or aspect < 1.8 or aspect > 2.8:
        return False
    if not _SOURCE_OR_STATLINK_RX.search(text):
        return False
    lines = _visual_nonempty_lines(text)
    if len(lines) > 10:
        return False
    numeric_row_hits = sum(1 for line in lines if len(_NUMBER_RX.findall(line)) >= 3)
    return numeric_row_hits <= 2


def _next_figure_caption_below(
    page: fitz.Page,
    cap_rect: fitz.Rect,
    *,
    blocks: Optional[List[tuple[float, float, float, float, str]]] = None,
) -> Optional[fitz.Rect]:
    for other_rect, other_text in _caption_blocks(
        page, CHART_CAPTION_HINTS, blocks=blocks
    ):
        if other_rect.y0 <= cap_rect.y0 + 8.0:
            continue
        if not _caption_has_figure_hint(other_text):
            continue
        return other_rect
    return None


def _visual_text_dense_recovery_allowed(
    kind: str,
    text: str,
    text_lines: int,
    text_chars: int,
    text_ratio: float,
) -> bool:
    lines = _visual_nonempty_lines(text)
    avg_line_len = text_chars / max(1, text_lines)
    numeric_hits = len(_NUMBER_RX.findall(text))
    return (
        _chart_is_label_dense_not_prose(text)
        or (kind == "panel" and _panel_chart_is_label_dense_not_prose(text))
        or (
            text_lines >= CHART_DENSE_RECOVERY_MIN_LINES
            and text_chars >= CHART_DENSE_RECOVERY_MIN_CHARS
            and not _chart_text_heavy(text_lines, text_chars, text_ratio)
        )
        or (
            kind == "draw"
            and bool(_SOURCE_OR_STATLINK_RX.search(text))
            and text_lines >= 12
            and numeric_hits >= 10
            and avg_line_len <= 42.0
            and text_ratio <= 0.68
            and not _caption_looks_explanatory_figure_reference(
                lines[0] if lines else ""
            )
        )
    )


def _initial_visual_stats() -> Dict[str, object]:
    return {"raw": 0, "kept": 0, "rejected": 0, "reasons": {}}


def _build_visual_page_context(
    page: fitz.Page,
    page_number: int,
    stats: Dict[str, object],
    *,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> Optional[_VisualPageContext]:
    artifacts = get_page_artifacts(page, cache=artifact_cache)
    if artifacts.full_page_scan_without_text:
        stats["skipped_pages"] = _int_count(stats.get("skipped_pages", 0)) + 1
        _tally_reason(stats, "page_full_scan_no_text")
        return None
    page_chars = artifacts.text_char_count
    page_rect = page.rect
    return _VisualPageContext(
        page_number=page_number,
        page=page,
        page_rect=page_rect,
        page_chars=page_chars,
        top_cut=page_rect.y0 + page_rect.height * CHART_MARGIN_FRAC,
        bot_cut=page_rect.y1 - page_rect.height * CHART_MARGIN_FRAC,
        relaxed_top=page_rect.y0 + page_rect.height * CHART_MARGIN_RELAX_FRAC,
        relaxed_bot=page_rect.y1 - page_rect.height * CHART_MARGIN_RELAX_FRAC,
        page_has_chart_captions=_page_has_chart_caption_blocks(artifacts.text_blocks),
        artifacts=artifacts,
        rect_items=_collect_chart_rects(
            page,
            text_dict=artifacts.text_dict,
            blocks=artifacts.text_blocks,
        ),
        probe_cache=_RasterProbeCache(images={}, profiles={}),
    )


def _append_visual_page_candidate(
    *,
    page_candidates: List[_VisualPageCandidateEntry],
    kept: list[tuple[fitz.Rect, float, int]],
    candidate: Candidate,
    final_rect: fitz.Rect,
    score: float,
    local_sequence: int,
    legacy_order_candidate: bool,
    stats: Dict[str, object],
) -> int:
    overlap_index = _find_overlapping_kept(final_rect, kept)
    if overlap_index is not None:
        existing_score = kept[overlap_index][1]
        if score <= existing_score:
            stats["rejected"] = _int_count(stats["rejected"]) + 1
            _tally_reason(stats, "overlap_dup")
            return local_sequence
        page_index = kept[overlap_index][2]
        existing_entry = page_candidates[page_index]
        page_candidates[page_index] = _VisualPageCandidateEntry(
            candidate=candidate,
            rect=final_rect,
            score=score,
            sequence=existing_entry.sequence,
            recovered_only=existing_entry.recovered_only and not legacy_order_candidate,
        )
        kept[overlap_index] = (final_rect, score, page_index)
        stats["replaced"] = _int_count(stats.get("replaced", 0)) + 1
        return local_sequence
    page_candidates.append(
        _VisualPageCandidateEntry(
            candidate=candidate,
            rect=final_rect,
            score=score,
            sequence=local_sequence,
            recovered_only=not legacy_order_candidate,
        )
    )
    kept.append((final_rect, score, len(page_candidates) - 1))
    stats["kept"] = _int_count(stats["kept"]) + 1
    return local_sequence + 1


def _emit_visual_page_candidates(
    out: List[Candidate],
    *,
    page_number: int,
    page_candidates: List[_VisualPageCandidateEntry],
) -> None:
    page_candidates.sort(key=lambda entry: (entry.recovered_only, entry.sequence))
    for local_index, entry in enumerate(page_candidates):
        out.append(replace(entry.candidate, id=f"chart-{page_number}-{local_index}"))


def _extract_visuals_sequential(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    pages: Optional[List[int]] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> tuple[List[Candidate], Dict[str, object]]:
    out: List[Candidate] = []
    stats = _initial_visual_stats()
    local_doc = doc or fitz.open(pdf_path)
    try:
        thumb_index = 0
        page_numbers = pages if pages is not None else list(range(len(local_doc)))
        for pno in page_numbers:
            if pno < 0 or pno >= len(local_doc):
                continue
            page = local_doc[pno]
            page_ctx = _build_visual_page_context(
                page,
                pno,
                stats,
                artifact_cache=artifact_cache,
            )
            if page_ctx is None:
                continue
            kept: List[tuple[fitz.Rect, float, int]] = []
            page_candidates: List[_VisualPageCandidateEntry] = []
            local_sequence = 0
            for rect_item in page_ctx.rect_items:
                stats["raw"] = _int_count(stats["raw"]) + 1
                rect_candidate = rect_item.rect
                base_rect = rect_candidate
                area_frac = rect_candidate.get_area() / page_ctx.page_rect.get_area()
                aspect = rect_candidate.width / max(1, rect_candidate.height)
                cap_rect = rect_item.caption_rect
                cap = rect_item.caption
                if cap_rect is None:
                    cap_rect, cap = _nearest_caption_block(
                        page_ctx.page,
                        rect_candidate,
                        CHART_CAPTION_HINTS,
                        blocks=page_ctx.artifacts.text_blocks,
                    )
                if not cap:
                    cap = _nearby_text(
                        page_ctx.page,
                        rect_candidate,
                        blocks=page_ctx.artifacts.text_blocks,
                    )
                if cap and _is_page_number_text(cap):
                    cap = ""
                cap_lower = (cap or "").lower()
                has_hint = _text_has_visual_context_hint(cap or "")
                has_context_hint = has_hint or rect_item.kind == "panel"
                aspect_max = (
                    INFO_CHART_MAX_ASPECT
                    if rect_item.kind
                    in (
                        "heading",
                        "panel",
                    )
                    else 2.5
                )
                if (
                    rect_item.kind == "draw"
                    and cap_rect is not None
                    and any(cap_lower.startswith(hint) for hint in CHART_CAPTION_HINTS)
                ):
                    aspect_max = max(aspect_max, CHART_CAPTIONED_DRAW_MAX_ASPECT)
                relaxed_image_geometry = False
                contextual_image_card = False
                if (
                    rect_item.kind in ("xref", "block")
                    and not has_hint
                    and not page_ctx.page_has_chart_captions
                ):
                    relaxed_image_geometry = (
                        _embedded_visual_qualifies_relaxed_geometry(
                            page_ctx.page,
                            rect_candidate,
                            area_frac=area_frac,
                            probe_cache=page_ctx.probe_cache,
                        )
                    )
                    contextual_image_card = _embedded_visual_qualifies_contextual_card(
                        page_ctx.page,
                        rect_candidate,
                        area_frac=area_frac,
                        blocks=page_ctx.artifacts.text_blocks,
                        probe_cache=page_ctx.probe_cache,
                    )
                min_aspect = (
                    0.45 if (relaxed_image_geometry or contextual_image_card) else 0.55
                )
                max_aspect = (
                    3.4
                    if (relaxed_image_geometry or contextual_image_card)
                    else aspect_max
                )
                if rect_item.kind == "panel" and aspect > max_aspect:
                    try:
                        pre_geom_panel_text = page_ctx.page.get_text(
                            "text", clip=rect_candidate
                        )
                    except Exception:
                        pre_geom_panel_text = ""
                    if _panel_chart_has_compact_stat_card_signal(pre_geom_panel_text):
                        max_aspect = max(max_aspect, 5.25)
                if area_frac < 0.05 or not (min_aspect <= aspect <= max_aspect):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "geometry")
                    continue
                is_infographic = bool(
                    re.match(r"^\s*infographic\b", cap or "", re.IGNORECASE)
                )
                if (
                    rect_candidate.y0 < page_ctx.top_cut
                    or rect_candidate.y1 > page_ctx.bot_cut
                ):
                    if has_context_hint or contextual_image_card:
                        if (
                            rect_candidate.y0 < page_ctx.page_rect.y0 - 2.0
                            or rect_candidate.y1 > page_ctx.page_rect.y1 + 2.0
                        ):
                            stats["rejected"] = _int_count(stats["rejected"]) + 1
                            _tally_reason(stats, "margin")
                            continue
                    elif (
                        rect_candidate.y0 < page_ctx.relaxed_top
                        or rect_candidate.y1 > page_ctx.relaxed_bot
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "margin")
                        continue
                if not has_hint and area_frac < 0.08:
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "caption_hint")
                    continue
                if (
                    rect_item.kind in ("block", "draw")
                    and not has_context_hint
                    and area_frac < 0.12
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "block_small_no_caption")
                    continue
                if (
                    rect_item.kind in ("block", "draw")
                    and not has_context_hint
                    and area_frac > 0.8
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "block_full_page_no_caption")
                    continue
                try:
                    raw_bbox_text = page_ctx.page.get_text("text", clip=rect_candidate)
                except Exception:
                    raw_bbox_text = ""
                raw_text_lines, raw_text_chars = _text_stats(raw_bbox_text)
                raw_text_ratio = (
                    (raw_text_chars / page_ctx.page_chars)
                    if page_ctx.page_chars
                    else 0.0
                )
                bbox_text = raw_bbox_text
                text_lines = raw_text_lines
                text_chars = raw_text_chars
                text_ratio = raw_text_ratio
                raw_text_heavy = _chart_text_heavy(
                    raw_text_lines, raw_text_chars, raw_text_ratio
                )
                image_chart_like = False
                image_decorative = False
                image_photo_like = False
                if rect_item.kind in ("xref", "block") and not has_hint:
                    if _embedded_visual_is_oversized_wrapper(
                        rect_item,
                        page_ctx.rect_items,
                        page_ctx.page_rect,
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "oversized_wrapper_image")
                        continue
                    image_chart_like = (
                        contextual_image_card
                        or _embedded_visual_looks_chart_like(
                            page_ctx.page,
                            rect_candidate,
                            probe_cache=page_ctx.probe_cache,
                        )
                    )
                    image_photo_like = _embedded_visual_looks_photo_like(
                        page_ctx.page,
                        rect_candidate,
                        probe_cache=page_ctx.probe_cache,
                    )
                    if not image_chart_like:
                        image_decorative = _embedded_visual_looks_decorative(
                            page_ctx.page,
                            rect_candidate,
                            probe_cache=page_ctx.probe_cache,
                        )
                text_dense_recovery_allowed = False
                infographic_dense_recovery_allowed = False
                panel_data_signal = False
                if (
                    rect_item.kind in ("draw", "panel")
                    and cap_rect is not None
                    and raw_text_heavy
                ):
                    try:
                        analysis_rect = _merge_caption_above(
                            rect_candidate,
                            cap_rect,
                            page_ctx.page_rect,
                        )
                        analysis_rect = _clamp_top_to_caption(
                            analysis_rect,
                            cap_rect,
                            page_ctx.page,
                            page_ctx.page_rect,
                        )
                        if rect_item.kind != "panel":
                            analysis_rect = _clamp_bottom_to_next_chart_blocker(
                                page_ctx.page,
                                analysis_rect,
                                cap_rect,
                            )
                        bbox_text = page_ctx.page.get_text("text", clip=analysis_rect)
                    except Exception:
                        bbox_text = raw_bbox_text
                    text_lines, text_chars = _text_stats(bbox_text)
                    text_ratio = (
                        (text_chars / page_ctx.page_chars)
                        if page_ctx.page_chars
                        else 0.0
                    )
                    text_dense_recovery_allowed = _visual_text_dense_recovery_allowed(
                        rect_item.kind,
                        bbox_text,
                        text_lines,
                        text_chars,
                        text_ratio,
                    )
                    if is_infographic:
                        infographic_dense_recovery_allowed = (
                            _infographic_is_label_dense_not_prose(bbox_text)
                            or _infographic_is_label_dense_not_prose(raw_bbox_text)
                        )
                if rect_item.kind == "panel":
                    panel_text = bbox_text if bbox_text else raw_bbox_text
                    panel_data_signal = _panel_chart_has_data_signal(panel_text) or (
                        _panel_component_looks_like_guidance_card(panel_text)
                    )
                    if _panel_candidate_shadowed_by_heading_candidate(
                        rect_item, page_ctx.rect_items
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "panel_shadowed_by_heading")
                        continue
                    if _panel_candidate_shadowed_by_larger_panel(
                        rect_item, page_ctx.rect_items, panel_text
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "panel_shadowed_by_larger_panel")
                        continue
                    if not panel_data_signal and (
                        raw_text_heavy
                        or (
                            raw_text_lines >= 5
                            and raw_text_chars >= 150
                            and raw_text_ratio >= 0.25
                        )
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "panel_no_data_signal")
                        continue
                if rect_item.kind in ("xref", "block") and not has_hint:
                    if (
                        image_photo_like
                        and not contextual_image_card
                        and not relaxed_image_geometry
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "photo_panel")
                        continue
                    if (
                        not image_chart_like
                        and (not cap or len(cap.strip()) < 8)
                        and text_chars <= 8
                        and area_frac < 0.5
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "decorative_image")
                        continue
                    if (
                        not image_chart_like
                        and text_chars <= 8
                        and area_frac <= 0.2
                        and _has_side_by_side_visual_sibling(
                            rect_item,
                            page_ctx.rect_items,
                            page_ctx.page_rect,
                        )
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "photo_panel")
                        continue
                    if (
                        rect_item.kind == "xref"
                        and not contextual_image_card
                        and not relaxed_image_geometry
                        and area_frac <= SMALL_DECORATIVE_RASTER_MAX_AREA_FRAC
                        and text_chars <= SMALL_DECORATIVE_RASTER_MAX_TEXT_CHARS
                    ):
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "small_decorative_image")
                        continue
                    if image_decorative and text_chars <= 24 and area_frac <= 0.5:
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "decorative_image")
                        continue
                if raw_text_heavy:
                    if (
                        rect_item.kind in ("draw", "panel")
                        and cap_rect is not None
                        and (
                            (has_context_hint and raw_text_ratio <= 0.55)
                            or (
                                rect_item.kind == "panel"
                                and (
                                    (
                                        panel_data_signal
                                        and raw_text_ratio
                                        <= PANEL_CHART_CONTEXT_TEXT_RATIO_MAX
                                    )
                                    or _panel_chart_is_label_dense_not_prose(
                                        bbox_text if bbox_text else raw_bbox_text
                                    )
                                    or _panel_component_looks_like_independent_data_panel(
                                        bbox_text if bbox_text else raw_bbox_text
                                    )
                                    or _panel_chart_has_structured_card_signal(
                                        bbox_text if bbox_text else raw_bbox_text
                                    )
                                )
                            )
                            or text_dense_recovery_allowed
                            or infographic_dense_recovery_allowed
                        )
                    ):
                        pass
                    else:
                        stats["rejected"] = _int_count(stats["rejected"]) + 1
                        _tally_reason(stats, "text_dense")
                        continue
                legacy_order_candidate = not raw_text_heavy or (
                    rect_item.kind in ("draw", "panel")
                    and has_context_hint
                    and raw_text_ratio <= 0.55
                )
                final_rect = rect_candidate
                expanded_with_heading = False
                if cap_rect is not None and has_context_hint:
                    final_rect = _merge_caption_above(
                        final_rect,
                        cap_rect,
                        page_ctx.page_rect,
                    )
                allow_adjacent = rect_item.kind in ("draw", "heading", "panel") or (
                    rect_item.kind == "xref" and has_context_hint
                )
                if allow_adjacent:
                    if rect_item.kind == "panel":
                        panel_min_x = None
                        panel_max_x = None
                        compact_stat_caption = _panel_caption_looks_metric_stub(
                            cap or ""
                        )
                        if (
                            cap_rect is not None
                            and not _caption_has_figure_hint(cap or "")
                            and not compact_stat_caption
                        ):
                            slice_bounds = _panel_title_slice_bounds(
                                page_ctx.page,
                                cap_rect,
                            )
                            if slice_bounds is not None:
                                panel_min_x, panel_max_x = slice_bounds
                                bound_pad = max(
                                    page_ctx.page_rect.width * 0.015,
                                    rect_candidate.width * 0.12,
                                )
                                panel_min_x = max(
                                    page_ctx.page.rect.x0,
                                    min(panel_min_x, rect_candidate.x0),
                                )
                                panel_min_x = max(
                                    panel_min_x,
                                    rect_candidate.x0 - bound_pad,
                                )
                                panel_max_x = min(
                                    page_ctx.page.rect.x1,
                                    max(panel_max_x, rect_candidate.x1),
                                )
                                panel_max_x = min(
                                    panel_max_x,
                                    rect_candidate.x1 + bound_pad,
                                )
                        neighbor_min_x, neighbor_max_x = _panel_neighbor_x_bounds(
                            rect_item,
                            page_ctx.rect_items,
                            page_ctx.page_rect,
                        )
                        if neighbor_min_x is not None:
                            panel_min_x = (
                                neighbor_min_x
                                if panel_min_x is None
                                else max(panel_min_x, neighbor_min_x)
                            )
                        if neighbor_max_x is not None:
                            panel_max_x = (
                                neighbor_max_x
                                if panel_max_x is None
                                else min(panel_max_x, neighbor_max_x)
                            )
                        final_rect = _extend_panel_with_adjacent_text_blocks(
                            page_ctx.page,
                            final_rect,
                            min_x=panel_min_x,
                            max_x=panel_max_x,
                        )
                    else:
                        final_rect = _extend_with_adjacent_text_blocks(
                            page_ctx.page,
                            final_rect,
                        )
                    if rect_item.kind == "draw":
                        final_rect = _extend_chart_rect_with_adjacent_drawings(
                            page_ctx.page,
                            final_rect,
                        )
                if not has_hint and rect_item.kind == "heading":
                    expanded = _extend_with_heading_above(page_ctx.page, final_rect)
                    expanded_with_heading = expanded.y0 < final_rect.y0 - 1
                    final_rect = expanded
                if not has_hint and rect_item.kind not in ("heading", "xref", "panel"):
                    head_rect = _nearest_heading_above(page_ctx.page, final_rect)
                    if head_rect is not None:
                        final_rect = final_rect | head_rect
                if rect_item.kind != "xref" or has_hint:
                    final_rect = _pad_rect(final_rect, page_ctx.page_rect)
                if not has_hint and rect_item.kind in ("draw", "heading", "panel"):
                    if rect_item.kind == "heading":
                        final_rect = _adjust_rect_for_text_margins(
                            page_ctx.page,
                            final_rect,
                            gap_scale=CHART_EDGE_TEXT_HEADING_GAP_SCALE,
                            gap_scale_x=CHART_EDGE_TEXT_HEADING_GAP_X_SCALE,
                        )
                        final_rect = _expand_rect_into_whitespace(
                            page_ctx.page,
                            final_rect,
                            allow_top=False,
                        )
                    elif rect_item.kind == "panel":
                        pass
                    else:
                        final_rect = _adjust_rect_for_text_margins(
                            page_ctx.page,
                            final_rect,
                        )
                        final_rect = _expand_rect_into_whitespace(
                            page_ctx.page,
                            final_rect,
                        )
                if (
                    rect_item.kind == "heading"
                    and cap_rect is not None
                    and not expanded_with_heading
                ):
                    final_rect = _clamp_top_to_heading(
                        final_rect,
                        cap_rect,
                        page_ctx.page,
                        page_ctx.page_rect,
                    )
                if not has_hint and rect_item.kind not in ("heading", "xref", "panel"):
                    head_rect = _nearest_heading_above(page_ctx.page, final_rect)
                    if head_rect is not None:
                        final_rect = _clamp_top_to_heading(
                            final_rect,
                            head_rect,
                            page_ctx.page,
                            page_ctx.page_rect,
                        )
                final_rect = _extend_with_note_blocks(page_ctx.page, final_rect)
                if (
                    cap_rect is not None
                    and has_context_hint
                    and cap_rect.y0 < base_rect.y0
                ):
                    final_rect = _clamp_top_to_caption(
                        final_rect,
                        cap_rect,
                        page_ctx.page,
                        page_ctx.page_rect,
                    )
                note_bottom = _note_block_bottom(page_ctx.page, final_rect)
                note_included = note_bottom is not None
                stacked_bottom_clip_y = (
                    _panel_stacked_bottom_clip_y(
                        page_ctx.page,
                        rect_item,
                        page_ctx.rect_items,
                    )
                    if rect_item.kind == "panel"
                    else None
                )
                panel_caption_is_top_band = (
                    rect_item.kind == "panel"
                    and cap_rect is not None
                    and _panel_caption_looks_top_band(
                        cap or "",
                        rect=rect_candidate,
                        cap_rect=cap_rect,
                    )
                )
                panel_caption_is_internal_label = (
                    rect_item.kind == "panel"
                    and cap_rect is not None
                    and cap_rect.y0 >= rect_candidate.y0 + 1.0
                    and not _caption_has_figure_hint(cap or "")
                    and not panel_caption_is_top_band
                )
                if note_bottom is not None:
                    final_rect = _clamp_bottom_to_note(
                        page_ctx.page,
                        final_rect,
                        note_bottom,
                        page_ctx.page_rect,
                    )
                if stacked_bottom_clip_y is not None:
                    final_rect.y1 = min(
                        final_rect.y1,
                        max(final_rect.y0 + 24.0, stacked_bottom_clip_y - 8.0),
                    )
                if (
                    rect_item.kind in ("draw", "panel")
                    and cap_rect is not None
                    and text_dense_recovery_allowed
                    and not panel_caption_is_internal_label
                ):
                    final_rect = _clamp_bottom_to_next_chart_blocker(
                        page_ctx.page,
                        final_rect,
                        cap_rect,
                    )
                if cap_rect is not None and _caption_near_top(final_rect, cap_rect):
                    if rect_item.kind == "panel" and panel_caption_is_internal_label:
                        pass
                    elif has_context_hint or rect_item.kind in ("panel", "draw"):
                        final_rect = _clamp_top_to_caption(
                            final_rect,
                            cap_rect,
                            page_ctx.page,
                            page_ctx.page_rect,
                            extra_pad=(
                                PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD
                                if panel_caption_is_top_band
                                else 0.0
                            ),
                        )
                if cap_rect is not None and _panel_should_clamp_to_internal_caption(
                    rect_item,
                    page_ctx.rect_items,
                ):
                    final_rect = _clamp_top_to_caption(
                        final_rect,
                        cap_rect,
                        page_ctx.page,
                        page_ctx.page_rect,
                        extra_pad=PANEL_CHART_INTERNAL_TITLE_EXTRA_TOP_PAD,
                    )
                final_rect = _trim_top_page_number(
                    final_rect,
                    page_ctx.page,
                    cap_rect if has_context_hint else None,
                )
                try:
                    bbox_text = page_ctx.page.get_text("text", clip=final_rect)
                except Exception:
                    bbox_text = ""
                text_lines, text_chars = _text_stats(bbox_text)
                text_ratio = (
                    (text_chars / page_ctx.page_chars) if page_ctx.page_chars else 0.0
                )
                if _visual_candidate_looks_table_like(
                    cap or "",
                    bbox_text,
                    kind=rect_item.kind,
                    panel_data_signal=panel_data_signal,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "table_like_visual")
                    continue
                if _visual_candidate_looks_reference_or_prose(
                    cap or "",
                    bbox_text,
                    text_ratio=text_ratio,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "reference_or_prose_visual")
                    continue
                if _visual_candidate_looks_note_fragment(
                    cap or "",
                    bbox_text,
                    kind=rect_item.kind,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "note_fragment_visual")
                    continue
                if _visual_candidate_looks_bare_heading_fragment(
                    cap or "",
                    bbox_text,
                    kind=rect_item.kind,
                    area_frac=area_frac,
                    aspect=aspect,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "bare_heading_fragment")
                    continue
                if _visual_candidate_looks_cover_art(
                    final_rect,
                    page_ctx.page_rect,
                    cap or "",
                    area_frac=area_frac,
                    text_chars=text_chars,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "front_matter_visual")
                    continue
                if _visual_candidate_looks_photo_narrative_card(
                    page_ctx.page,
                    final_rect,
                    cap or "",
                    caption_rect=cap_rect,
                    kind=rect_item.kind,
                    area_frac=area_frac,
                    aspect=aspect,
                    text_chars=text_chars,
                    panel_data_signal=panel_data_signal,
                    probe_cache=page_ctx.probe_cache,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "photo_panel")
                    continue
                if _visual_candidate_looks_narrative_panel_card(
                    cap or "",
                    bbox_text,
                    kind=rect_item.kind,
                    text_ratio=text_ratio,
                    area_frac=area_frac,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "narrative_panel")
                    continue
                if _visual_candidate_looks_section_opener_banner(
                    final_rect,
                    page_ctx.page_rect,
                    cap or "",
                    bbox_text,
                    kind=rect_item.kind,
                    area_frac=area_frac,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "section_opener_visual")
                    continue
                if _visual_candidate_looks_inline_numbered_panel(
                    cap or "",
                    bbox_text,
                    note_included=note_included,
                    area_frac=area_frac,
                    aspect=aspect,
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "inline_numbered_panel")
                    continue
                if (
                    rect_item.kind in ("draw", "heading")
                    and cap_rect is not None
                    and _caption_has_figure_hint(cap or "")
                    and cap_rect.y0
                    <= page_ctx.page_rect.y0 + page_ctx.page_rect.height * 0.1
                    and _SOURCE_OR_STATLINK_RX.search(bbox_text)
                ):
                    next_caption_rect = _next_figure_caption_below(
                        page_ctx.page,
                        cap_rect,
                        blocks=page_ctx.artifacts.text_blocks,
                    )
                else:
                    next_caption_rect = None
                weak_stacked_upper = (
                    next_caption_rect is not None
                    and _SOURCE_OR_STATLINK_RX.search(bbox_text)
                    and text_chars <= 260
                    and not _chart_is_label_dense_not_prose(bbox_text)
                    and not _panel_chart_has_data_signal(bbox_text)
                )
                if next_caption_rect is not None and (
                    final_rect.y1 >= next_caption_rect.y0 - 6.0 or weak_stacked_upper
                ):
                    stats["rejected"] = _int_count(stats["rejected"]) + 1
                    _tally_reason(stats, "stacked_top_figure")
                    continue
                pix = None
                if save_thumbs:
                    render_rect = final_rect
                    if (
                        rect_item.kind == "xref"
                        and rect_item.xref is not None
                        and _rect_iou(render_rect, rect_candidate) >= 0.98
                    ):
                        pix = fitz.Pixmap(local_doc, rect_item.xref)
                        if pix.alpha or (
                            pix.colorspace and pix.colorspace != fitz.csRGB
                        ):
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                    else:
                        try:
                            pix = page_ctx.page.get_pixmap(
                                clip=render_rect,
                                alpha=False,
                            )
                        except Exception:
                            pix = None
                cid = f"chart-{pno}-pending-{local_sequence}"
                thumb = (
                    _save_thumb(pix, thumbs_dir, report_name, thumb_index)
                    if save_thumbs and pix
                    else None
                )
                if save_thumbs and thumb:
                    thumb_path = Path(thumb)
                    rel_thumb = Path(report_name) / "thumbs" / thumb_path.name
                    thumb = rel_thumb.as_posix()
                profile = _visual_probe_profile(
                    page_ctx.page,
                    final_rect,
                    probe_cache=page_ctx.probe_cache,
                )
                visual_entropy = (
                    round(float(profile.get("visual_entropy", 0.0) or 0.0), 3)
                    if profile is not None
                    else 0.0
                )
                chart_confidence = _chart_confidence_score(
                    area_frac=area_frac,
                    has_context_hint=has_context_hint,
                    caption=cap or "",
                    bbox_text=bbox_text,
                    text_lines=text_lines,
                    text_chars=text_chars,
                    note_included=note_included,
                    profile=profile,
                )
                features = CandidateFeatures(
                    schema_version="1.0",
                    area_frac=round(area_frac, 3),
                    aspect=round(aspect, 2),
                    text_lines=text_lines,
                    text_chars=text_chars,
                    text_ratio=round(text_ratio, 3),
                    ocr_density=_candidate_ocr_density(text_chars, area_frac),
                    visual_entropy=visual_entropy,
                    chart_confidence=chart_confidence,
                )
                candidate = Candidate(
                    schema_version="1.0",
                    id=cid,
                    kind="chart",
                    page=pno,
                    bbox=(
                        final_rect.x0,
                        final_rect.y0,
                        final_rect.x1,
                        final_rect.y1,
                    ),
                    preview_text=cap or "",
                    caption=cap,
                    thumb_path=thumb,
                    meta={
                        "area_frac": features.area_frac,
                        "aspect": features.aspect,
                        "text_lines": features.text_lines,
                        "text_chars": features.text_chars,
                        "text_ratio": features.text_ratio,
                        "ocr_density": features.ocr_density,
                        "visual_entropy": features.visual_entropy,
                        "chart_confidence": features.chart_confidence,
                    },
                    features=features,
                )
                score = _chart_candidate_score(
                    area_frac, has_context_hint, cap or "", note_included
                )
                if rect_item.kind == "panel":
                    score += 0.35
                elif rect_item.kind == "draw":
                    score += 0.15
                elif rect_item.kind == "heading":
                    score -= 0.05
                local_sequence = _append_visual_page_candidate(
                    page_candidates=page_candidates,
                    kept=kept,
                    candidate=candidate,
                    final_rect=final_rect,
                    score=score,
                    local_sequence=local_sequence,
                    legacy_order_candidate=legacy_order_candidate,
                    stats=stats,
                )
                if save_thumbs:
                    thumb_index += 1
            _emit_visual_page_candidates(
                out,
                page_number=pno,
                page_candidates=page_candidates,
            )
            probe_stats = page_ctx.probe_cache.stats()
            stats["raster_probe_cache_hits"] = (
                _int_count(stats.get("raster_probe_cache_hits", 0))
                + probe_stats["hits"]
            )
            stats["raster_probe_cache_misses"] = (
                _int_count(stats.get("raster_probe_cache_misses", 0))
                + probe_stats["misses"]
            )
            stats["raster_probe_image_entries"] = (
                _int_count(stats.get("raster_probe_image_entries", 0))
                + probe_stats["image_entries"]
            )
            stats["raster_probe_profile_entries"] = (
                _int_count(stats.get("raster_probe_profile_entries", 0))
                + probe_stats["profile_entries"]
            )
    finally:
        if doc is None:
            local_doc.close()
    return out, stats


def extract_visual_candidates(
    pdf_path: str,
    thumbs_dir: str,
    report_name: str,
    *,
    save_thumbs: bool = False,
    doc: Optional[fitz.Document] = None,
    parallel_workers: int = 1,
    pages: Optional[List[int]] = None,
    artifact_cache: Optional[PdfPageArtifactCache] = None,
) -> tuple[List[Candidate], Dict[str, object]]:
    if save_thumbs:
        return _extract_visuals_sequential(
            pdf_path,
            thumbs_dir,
            report_name,
            save_thumbs=save_thumbs,
            doc=doc,
            pages=pages,
            artifact_cache=artifact_cache,
        )
    if doc is not None:
        all_pages = list(range(len(doc)))
    else:
        temp_doc = fitz.open(pdf_path)
        try:
            all_pages = list(range(len(temp_doc)))
        finally:
            temp_doc.close()
    page_numbers = pages if pages is not None else all_pages
    worker_count = _resolve_candidate_parallel_workers(
        parallel_workers, len(page_numbers)
    )
    if worker_count <= 1 or len(page_numbers) <= 1:
        return _extract_visuals_sequential(
            pdf_path,
            thumbs_dir,
            report_name,
            save_thumbs=save_thumbs,
            doc=doc,
            pages=page_numbers,
            artifact_cache=artifact_cache,
        )
    chunks = _split_even_chunks(page_numbers, worker_count)
    merged_stats: Dict[str, object] = {
        "raw": 0,
        "kept": 0,
        "rejected": 0,
        "reasons": {},
    }
    merged_candidates: List[Candidate] = []
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        futures = {
            executor.submit(
                _extract_visuals_sequential,
                pdf_path,
                thumbs_dir,
                report_name,
                False,
                None,
                chunk,
                artifact_cache,
            ): chunk
            for chunk in chunks
        }
        for future in as_completed(futures):
            chunk_candidates, chunk_stats = future.result()
            merged_candidates.extend(chunk_candidates)
            merged_stats = _merge_stats(merged_stats, chunk_stats)
    merged_candidates.sort(
        key=lambda candidate: (candidate.page, _candidate_index_from_id(candidate.id))
    )
    return merged_candidates, merged_stats
