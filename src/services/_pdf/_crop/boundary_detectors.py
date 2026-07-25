"""Deterministic boundary detectors for final PDF visual crops.

This module owns crop-completeness detectors that combine PDF drawing geometry
with rendered-image edge signals. It stays inside the PDF crop capability and
does not coordinate service calls or artifact writes.
"""

from __future__ import annotations

from typing import Any

import pymupdf as fitz
from PIL import Image

from src.utils.errors import AppError

TABLE_RULE_SNAP_MAX_DISTANCE = 32.0
TABLE_RULE_MIN_OVERLAP_RATIO = 0.62
TABLE_RULE_THINNESS_MAX = 3.0
CARD_EDGE_DENSITY_THRESHOLD = 0.42
CHART_EDGE_DENSITY_THRESHOLD = 0.32


def rgb_pixel(img: Image.Image, coordinate: tuple[int, int]) -> tuple[int, int, int]:
    """Normalize Pillow's supported pixel forms to the RGB data crop checks use."""

    pixel = img.getpixel(coordinate)
    if isinstance(pixel, tuple):
        if len(pixel) >= 3:
            return int(pixel[0]), int(pixel[1]), int(pixel[2])
        if len(pixel) >= 1:
            value = int(pixel[0])
            return value, value, value
    if isinstance(pixel, (int, float)):
        value = int(pixel)
        return value, value, value
    raise AppError(
        code="pdf_crop_pixel_invalid",
        message="Rendered crop image contains an unsupported pixel value",
        retryable=False,
        context={"coordinate": list(coordinate), "mode": str(img.mode or "")},
    )


def snap_table_rect_to_outer_rules(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    adjusted = fitz.Rect(rect) & page.rect
    if adjusted.is_empty:
        return adjusted

    container = _high_confidence_container_rect(page, adjusted)
    if container is not None:
        adjusted |= container

    top_rule, bottom_rule = _nearest_horizontal_outer_rules(page, adjusted)
    left_rule, right_rule = _nearest_vertical_outer_rules(page, adjusted)
    if top_rule is not None:
        adjusted.y0 = min(adjusted.y0, top_rule.y0)
    if bottom_rule is not None:
        adjusted.y1 = max(adjusted.y1, bottom_rule.y1)
    if left_rule is not None:
        adjusted.x0 = min(adjusted.x0, left_rule.x0)
    if right_rule is not None:
        adjusted.x1 = max(adjusted.x1, right_rule.x1)

    adjusted &= page.rect
    if adjusted.width < 1 or adjusted.height < 1:
        return rect & page.rect
    return adjusted


def detect_rendered_crop_boundaries(
    img: Image.Image, *, crop_type: str
) -> tuple[list[str], dict[str, Any]]:
    edge_density = _edge_content_densities(img)
    table_boundary = _table_boundary_detector(edge_density)
    chart_completeness = _chart_completeness_detector(edge_density, crop_type=crop_type)
    visual_card_boundary = _visual_card_boundary_detector(
        edge_density,
        crop_type=crop_type,
    )
    defects: list[str] = []
    if not chart_completeness["accepted"]:
        defects.append("chart_axis_or_label_clipped")
    if not visual_card_boundary["accepted"]:
        defects.append("visual_card_boundary_clipped")
    detectors = {
        "schema_version": "1.0",
        "table_boundary": table_boundary,
        "chart_completeness": chart_completeness,
        "visual_card_boundary": visual_card_boundary,
    }
    return defects, detectors


def _high_confidence_container_rect(
    page: fitz.Page,
    rect: fitz.Rect,
) -> fitz.Rect | None:
    best: fitz.Rect | None = None
    best_area = 0.0
    max_distance = _snap_distance(rect)
    for draw in page.get_drawings():
        draw_rect = fitz.Rect(draw.get("rect") or fitz.Rect())
        if draw_rect.is_empty:
            continue
        if draw_rect.width < rect.width * 0.95 or draw_rect.height < rect.height * 0.95:
            continue
        if _horizontal_overlap_ratio(draw_rect, rect) < 0.9:
            continue
        if _vertical_overlap_ratio(draw_rect, rect) < 0.9:
            continue
        if (
            min(
                abs(draw_rect.x0 - rect.x0),
                abs(draw_rect.x1 - rect.x1),
                abs(draw_rect.y0 - rect.y0),
                abs(draw_rect.y1 - rect.y1),
            )
            > max_distance
        ):
            continue
        area = draw_rect.get_area()
        if area > best_area:
            best = draw_rect
            best_area = area
    return best


def _nearest_horizontal_outer_rules(
    page: fitz.Page,
    rect: fitz.Rect,
) -> tuple[fitz.Rect | None, fitz.Rect | None]:
    top: fitz.Rect | None = None
    bottom: fitz.Rect | None = None
    max_distance = _snap_distance(rect)
    for rule in _horizontal_rule_rects(page):
        if _horizontal_overlap_ratio(rule, rect) < TABLE_RULE_MIN_OVERLAP_RATIO:
            continue
        top_distance = rect.y0 - rule.y0
        if 0.0 <= top_distance <= max_distance and (top is None or rule.y0 < top.y0):
            top = rule
        bottom_distance = rule.y1 - rect.y1
        if 0.0 <= bottom_distance <= max_distance and (
            bottom is None or rule.y1 > bottom.y1
        ):
            bottom = rule
    return top, bottom


def _nearest_vertical_outer_rules(
    page: fitz.Page,
    rect: fitz.Rect,
) -> tuple[fitz.Rect | None, fitz.Rect | None]:
    left: fitz.Rect | None = None
    right: fitz.Rect | None = None
    max_distance = _snap_distance(rect)
    for rule in _vertical_rule_rects(page):
        if _vertical_overlap_ratio(rule, rect) < TABLE_RULE_MIN_OVERLAP_RATIO:
            continue
        left_distance = rect.x0 - rule.x0
        if 0.0 <= left_distance <= max_distance and (left is None or rule.x0 < left.x0):
            left = rule
        right_distance = rule.x1 - rect.x1
        if 0.0 <= right_distance <= max_distance and (
            right is None or rule.x1 > right.x1
        ):
            right = rule
    return left, right


def _horizontal_rule_rects(page: fitz.Page) -> list[fitz.Rect]:
    rules: list[fitz.Rect] = []
    for draw in page.get_drawings():
        draw_rect = fitz.Rect(draw.get("rect") or fitz.Rect())
        if draw_rect.is_empty:
            continue
        if draw_rect.height <= TABLE_RULE_THINNESS_MAX and draw_rect.width >= 24.0:
            rules.append(draw_rect)
    return rules


def _vertical_rule_rects(page: fitz.Page) -> list[fitz.Rect]:
    rules: list[fitz.Rect] = []
    for draw in page.get_drawings():
        draw_rect = fitz.Rect(draw.get("rect") or fitz.Rect())
        if draw_rect.is_empty:
            continue
        if draw_rect.width <= TABLE_RULE_THINNESS_MAX and draw_rect.height >= 24.0:
            rules.append(draw_rect)
    return rules


def _snap_distance(rect: fitz.Rect) -> float:
    return min(TABLE_RULE_SNAP_MAX_DISTANCE, max(rect.width, rect.height) * 0.12)


def _horizontal_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    overlap = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
    return overlap / max(1.0, min(a.width, b.width))


def _vertical_overlap_ratio(a: fitz.Rect, b: fitz.Rect) -> float:
    overlap = max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))
    return overlap / max(1.0, min(a.height, b.height))


def _table_boundary_detector(edge_density: dict[str, float]) -> dict[str, Any]:
    strong_edges = [edge for edge, density in edge_density.items() if density >= 0.18]
    return {
        "accepted": True,
        "confidence": round(min(1.0, len(strong_edges) / 4.0), 4),
        "strong_edges": strong_edges,
        "edge_density": _rounded_edge_density(edge_density),
    }


def _chart_completeness_detector(
    edge_density: dict[str, float], *, crop_type: str
) -> dict[str, Any]:
    clipped_edges: list[str] = []
    if crop_type == "chart":
        for edge in ("left", "bottom"):
            if edge_density.get(edge, 0.0) >= CHART_EDGE_DENSITY_THRESHOLD:
                clipped_edges.append(edge)
    return {
        "accepted": not clipped_edges,
        "confidence": round(
            min(1.0, max(edge_density.get(edge, 0.0) for edge in ("left", "bottom"))),
            4,
        ),
        "clipped_edges": clipped_edges,
        "edge_density": _rounded_edge_density(edge_density),
    }


def _visual_card_boundary_detector(
    edge_density: dict[str, float], *, crop_type: str
) -> dict[str, Any]:
    clipped_edges: list[str] = []
    if crop_type == "figure":
        for edge, opposite in (("left", "right"), ("right", "left")):
            if (
                edge_density.get(edge, 0.0) >= CARD_EDGE_DENSITY_THRESHOLD
                and edge_density.get(opposite, 0.0) < 0.12
            ):
                clipped_edges.append(edge)
        for edge, opposite in (("top", "bottom"), ("bottom", "top")):
            if (
                edge_density.get(edge, 0.0) >= CARD_EDGE_DENSITY_THRESHOLD
                and edge_density.get(opposite, 0.0) < 0.12
            ):
                clipped_edges.append(edge)
    return {
        "accepted": not clipped_edges,
        "confidence": round(
            min(1.0, max(edge_density.values(), default=0.0)),
            4,
        ),
        "clipped_edges": clipped_edges,
        "edge_density": _rounded_edge_density(edge_density),
    }


def _edge_content_densities(img: Image.Image) -> dict[str, float]:
    width, height = img.size
    bg = _dominant_border_color(img)
    band = max(2, min(width, height) // 50)
    return {
        "top": _box_content_density(img, bg, (0, 0, width, min(height, band))),
        "bottom": _box_content_density(
            img,
            bg,
            (0, max(0, height - band), width, height),
        ),
        "left": _box_content_density(img, bg, (0, 0, min(width, band), height)),
        "right": _box_content_density(
            img,
            bg,
            (max(0, width - band), 0, width, height),
        ),
    }


def _dominant_border_color(img: Image.Image, box: int = 4) -> tuple[int, int, int]:
    width, height = img.size
    corners = [
        (0, 0),
        (max(0, width - box), 0),
        (0, max(0, height - box)),
        (max(0, width - box), max(0, height - box)),
    ]
    colors: list[tuple[int, int, int]] = []
    for x0, y0 in corners:
        for y in range(y0, min(height, y0 + box)):
            for x in range(x0, min(width, x0 + box)):
                colors.append(rgb_pixel(img, (x, y)))
    if not colors:
        return rgb_pixel(img, (0, 0))
    counts: dict[tuple[int, int, int], int] = {}
    for color in colors:
        counts[color] = counts.get(color, 0) + 1
    return max(counts, key=lambda color: counts[color])


def _box_content_density(
    img: Image.Image, bg: tuple[int, int, int], box: tuple[int, int, int, int]
) -> float:
    x0, y0, x1, y1 = box
    if x1 <= x0 or y1 <= y0:
        return 0.0
    total = 0
    content = 0
    for y in range(y0, y1):
        for x in range(x0, x1):
            total += 1
            if _pixel_delta(rgb_pixel(img, (x, y)), bg) > 8:
                content += 1
    return content / max(1, total)


def _pixel_delta(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return max(abs(int(a[i]) - int(b[i])) for i in range(3))


def _rounded_edge_density(edge_density: dict[str, float]) -> dict[str, float]:
    return {key: round(float(value), 4) for key, value in edge_density.items()}


__all__ = [
    "TABLE_RULE_SNAP_MAX_DISTANCE",
    "TABLE_RULE_MIN_OVERLAP_RATIO",
    "TABLE_RULE_THINNESS_MAX",
    "CARD_EDGE_DENSITY_THRESHOLD",
    "CHART_EDGE_DENSITY_THRESHOLD",
    "rgb_pixel",
    "snap_table_rect_to_outer_rules",
    "detect_rendered_crop_boundaries",
]
