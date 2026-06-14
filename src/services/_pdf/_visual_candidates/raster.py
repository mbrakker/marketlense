"""Raster qualification primitives for PDF visual candidates.

This module owns deterministic image probes and raster-card classification while
candidate sequencing remains in the extraction coordinator.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional

import pymupdf as fitz
from PIL import Image, ImageFilter, ImageStat

from ..candidate_metrics import (
    bounded_quality as _bounded_quality,
    candidate_ocr_density as _candidate_ocr_density,
)
from ..visual_heuristics import (
    _chart_is_label_dense_not_prose,
    _is_page_number_text,
    _panel_chart_has_data_signal,
    _rect_containment_ratio,
    _rect_iou,
    _text_stats,
    _vertical_overlap_ratio,
    _VisualCandidateRelationships,
)

__all__ = [
    "CONTEXTUAL_RASTER_CARD_MIN_AREA_FRAC",
    "CONTEXTUAL_RASTER_CARD_MAX_AREA_FRAC",
    "CONTEXTUAL_RASTER_CARD_MIN_WIDTH_FRAC",
    "CONTEXTUAL_RASTER_CARD_MAX_WIDTH_FRAC",
    "CONTEXTUAL_RASTER_CARD_MIN_HEIGHT_FRAC",
    "CONTEXTUAL_RASTER_CARD_MAX_HEIGHT_FRAC",
    "CONTEXTUAL_RASTER_CARD_MIN_X0_FRAC",
    "CONTEXTUAL_RASTER_CARD_MIN_X1_FRAC",
    "CONTEXTUAL_RASTER_CARD_MAX_SAT_MEAN",
    "CONTEXTUAL_RASTER_CARD_MAX_DARK_FRAC",
    "CONTEXTUAL_RASTER_CARD_MIN_EDGE_DENSITY",
    "CONTEXTUAL_RASTER_CARD_MAX_EDGE_DENSITY",
    "CONTEXTUAL_RASTER_CARD_MIN_LEFT_CONTEXT_CHARS",
    "CONTEXTUAL_RASTER_CARD_MIN_LEFT_CONTEXT_BLOCKS",
    "PHOTO_LIKE_RASTER_MAX_WHITE_FRAC",
    "PHOTO_LIKE_RASTER_MIN_SAT_MEAN",
    "PHOTO_LIKE_RASTER_MIN_EDGE_DENSITY",
    "PHOTO_LIKE_RASTER_MIN_DARK_FRAC",
    "_RasterProbeCache",
    "_has_side_by_side_visual_sibling",
    "_render_visual_probe_image",
    "_visual_probe_profile",
    "_embedded_visual_looks_chart_like",
    "_bounded_quality",
    "_candidate_ocr_density",
    "_chart_confidence_score",
    "_embedded_visual_looks_decorative",
    "_embedded_visual_looks_photo_like",
    "_embedded_visual_is_oversized_wrapper",
    "_embedded_visual_qualifies_relaxed_geometry",
    "_left_side_context_signal",
    "_embedded_visual_qualifies_contextual_card",
]

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


def _has_side_by_side_visual_sibling(
    rect_item,
    candidates,
    page_rect: fitz.Rect,
    *,
    relationships: Optional[_VisualCandidateRelationships] = None,
) -> bool:
    related_candidates = (
        relationships.candidates_intersecting_y(
            ("xref", "block"),
            rect_item.rect,
        )
        if relationships is not None
        else candidates
    )
    for other in related_candidates:
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
    image = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
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
    *,
    relationships: Optional[_VisualCandidateRelationships] = None,
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
    related_candidates = (
        relationships.candidates_intersecting_y(
            ("xref", "block"),
            clipped_rect,
        )
        if relationships is not None
        else candidates
    )
    for other in related_candidates:
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
