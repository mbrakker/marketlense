"""Image-level operations for PDF crop artifacts.

This module owns deterministic raster trimming and image composition helpers
shared by crop rendering, without PDF workflow coordination.
"""

from __future__ import annotations

from typing import List

import pymupdf as fitz
from PIL import Image

from src.services._pdf._crop.boundary_detectors import (
    detect_rendered_crop_boundaries,
)
from src.utils.errors import AppError

PDF_CROP_EXCEPTIONS = (RuntimeError, ValueError, TypeError, AttributeError, OSError)


PREVIEW_RENDER_EXCEPTIONS = (AppError,) + PDF_CROP_EXCEPTIONS


CROP_TRIM_MAX_FRAC = 0.08


CROP_TRIM_MIN_PX = 12


CROP_TRIM_KEEP_PX = 8


CROP_TRIM_TOLERANCE = 8


CROP_TRIM_MIN_BG_FRAC = 0.9995


CROP_TRIM_SAMPLES = 60


def _dominant_border_color(img: Image.Image, box: int = 4) -> tuple[int, int, int]:
    width, height = img.size
    corners = [
        (0, 0),
        (max(0, width - box), 0),
        (0, max(0, height - box)),
        (max(0, width - box), max(0, height - box)),
    ]
    colors: List[tuple[int, int, int]] = []
    for x0, y0 in corners:
        for y in range(y0, min(height, y0 + box)):
            for x in range(x0, min(width, x0 + box)):
                colors.append(img.getpixel((x, y)))
    if not colors:
        return img.getpixel((0, 0))
    counts: dict[tuple[int, int, int], int] = {}
    for color in colors:
        counts[color] = counts.get(color, 0) + 1
    return max(counts, key=lambda color: counts[color])


def _row_is_bg(img: Image.Image, y: int, bg: tuple[int, int, int], tol: int) -> bool:
    width, _ = img.size
    step = 1
    samples = 0
    match = 0
    for x in range(0, width, step):
        samples += 1
        px = img.getpixel((x, y))
        if all(abs(px[i] - bg[i]) <= tol for i in range(3)):
            match += 1
    return (match / max(1, samples)) >= CROP_TRIM_MIN_BG_FRAC


def _col_is_bg(img: Image.Image, x: int, bg: tuple[int, int, int], tol: int) -> bool:
    _, height = img.size
    step = 1
    samples = 0
    match = 0
    for y in range(0, height, step):
        samples += 1
        px = img.getpixel((x, y))
        if all(abs(px[i] - bg[i]) <= tol for i in range(3)):
            match += 1
    return (match / max(1, samples)) >= CROP_TRIM_MIN_BG_FRAC


def _trim_uniform_border(
    img: Image.Image,
    allow_top: bool = True,
    allow_bottom: bool = True,
    allow_left: bool = True,
    allow_right: bool = True,
) -> Image.Image:
    width, height = img.size
    if width == 0 or height == 0:
        return img
    bg = _dominant_border_color(img)
    max_trim_y = int(height * CROP_TRIM_MAX_FRAC)
    max_trim_x = int(width * CROP_TRIM_MAX_FRAC)

    top = 0
    while (
        allow_top and top < max_trim_y and _row_is_bg(img, top, bg, CROP_TRIM_TOLERANCE)
    ):
        top += 1
    bottom = 0
    while (
        allow_bottom
        and bottom < max_trim_y
        and _row_is_bg(img, height - 1 - bottom, bg, CROP_TRIM_TOLERANCE)
    ):
        bottom += 1
    left = 0
    while (
        allow_left
        and left < max_trim_x
        and _col_is_bg(img, left, bg, CROP_TRIM_TOLERANCE)
    ):
        left += 1
    right = 0
    while (
        allow_right
        and right < max_trim_x
        and _col_is_bg(img, width - 1 - right, bg, CROP_TRIM_TOLERANCE)
    ):
        right += 1

    if top < CROP_TRIM_MIN_PX:
        top = 0
    if bottom < CROP_TRIM_MIN_PX:
        bottom = 0
    if left < CROP_TRIM_MIN_PX:
        left = 0
    if right < CROP_TRIM_MIN_PX:
        right = 0

    if top == 0 and bottom == 0 and left == 0 and right == 0:
        return img

    top = max(0, top - CROP_TRIM_KEEP_PX)
    bottom = max(0, bottom - CROP_TRIM_KEEP_PX)
    left = max(0, left - CROP_TRIM_KEEP_PX)
    right = max(0, right - CROP_TRIM_KEEP_PX)

    new_left = left
    new_top = top
    new_right = max(new_left + 1, width - right)
    new_bottom = max(new_top + 1, height - bottom)
    return img.crop((new_left, new_top, new_right, new_bottom))


def _content_aware_trim(
    img: Image.Image,
    *,
    crop_type: str = "figure",
    allow_top: bool = True,
    allow_bottom: bool = True,
    allow_left: bool = True,
    allow_right: bool = True,
) -> tuple[Image.Image, tuple[int, int, int, int]]:
    width, height = img.size
    if width == 0 or height == 0:
        return img, (0, 0, 0, 0)
    max_trim_y = int(height * _content_trim_max_fraction(crop_type))
    max_trim_x = int(width * _content_trim_max_fraction(crop_type))
    edge_threshold = _adaptive_edge_threshold(img)

    def _row_has_content(y: int) -> bool:
        return _edge_change_density(img, horizontal=True, index=y) >= edge_threshold

    def _col_has_content(x: int) -> bool:
        return _edge_change_density(img, horizontal=False, index=x) >= edge_threshold

    top = 0
    while allow_top and top < max_trim_y and not _row_has_content(top):
        top += 1
    bottom = 0
    while (
        allow_bottom
        and bottom < max_trim_y
        and not _row_has_content(height - 1 - bottom)
    ):
        bottom += 1
    left = 0
    while allow_left and left < max_trim_x and not _col_has_content(left):
        left += 1
    right = 0
    while (
        allow_right and right < max_trim_x and not _col_has_content(width - 1 - right)
    ):
        right += 1

    top = _trim_with_padding(
        top, min_px=CROP_TRIM_MIN_PX, keep_px=_adaptive_keep_px(crop_type)
    )
    bottom = _trim_with_padding(
        bottom, min_px=CROP_TRIM_MIN_PX, keep_px=_adaptive_keep_px(crop_type)
    )
    left = _trim_with_padding(
        left, min_px=CROP_TRIM_MIN_PX, keep_px=_adaptive_keep_px(crop_type)
    )
    right = _trim_with_padding(
        right, min_px=CROP_TRIM_MIN_PX, keep_px=_adaptive_keep_px(crop_type)
    )
    if top == 0 and bottom == 0 and left == 0 and right == 0:
        return img, (0, 0, 0, 0)
    new_left = left
    new_top = top
    new_right = max(new_left + 1, width - right)
    new_bottom = max(new_top + 1, height - bottom)
    return img.crop((new_left, new_top, new_right, new_bottom)), (
        top,
        bottom,
        left,
        right,
    )


def verify_crop_image(
    img: Image.Image, *, crop_type: str = "figure"
) -> dict[str, object]:
    width, height = img.size
    defect_labels: list[str] = []
    if width < 80 or height < 60:
        defect_labels.append("too_small")
    aspect_ratio = width / max(1, height)
    if aspect_ratio > 5.5 or aspect_ratio < 0.18:
        defect_labels.append("suspicious_aspect_ratio")
    edge_density = _edge_content_densities(img)
    edge_leakage = _edge_leakage_densities(img, edge_density)
    margin_balance = _margin_balance_score(edge_density)
    neighbor_contamination = max(edge_leakage.values(), default=0.0)
    if neighbor_contamination > 0.45:
        defect_labels.append("neighbor_contamination")
    if min(edge_density.values(), default=0.0) > 0.12:
        defect_labels.append("edge_clipped_content")
    readability = 1.0
    if width < 180 or height < 120:
        readability = 0.75
    if crop_type == "table" and (width < 240 or height < 140):
        readability = min(readability, 0.7)
    edge_integrity = 1.0 - min(1.0, neighbor_contamination * 1.8)
    visual_crispness = _visual_crispness_score(img)
    content_density = _image_content_density(img)
    completeness = min(1.0, content_density * 8.0)
    if width >= 160 and height >= 100 and not defect_labels:
        completeness = max(completeness, 0.55)
    if (
        content_density < 0.015
        and visual_crispness < 0.45
        and (width < 160 or height < 100)
    ):
        defect_labels.append("low_information")
    detector_defects, detector_results = detect_rendered_crop_boundaries(
        img,
        crop_type=crop_type,
    )
    for defect in detector_defects:
        if defect not in defect_labels:
            defect_labels.append(defect)
    total_score = round(
        (
            completeness * 0.25
            + edge_integrity * 0.25
            + margin_balance * 0.2
            + readability * 0.15
            + visual_crispness * 0.15
        ),
        4,
    )
    accepted = not defect_labels and total_score >= _qa_acceptance_threshold(
        crop_type, width=width, height=height
    )
    return {
        "schema_version": "1.0",
        "accepted": accepted,
        "crop_type": crop_type,
        "content_completeness": round(completeness, 4),
        "edge_integrity": round(edge_integrity, 4),
        "margin_balance": round(margin_balance, 4),
        "neighbor_contamination": round(neighbor_contamination, 4),
        "readability": round(readability, 4),
        "visual_crispness": round(visual_crispness, 4),
        "total_score": total_score,
        "defect_labels": defect_labels,
        "edge_density": {key: round(value, 4) for key, value in edge_density.items()},
        "edge_leakage": {key: round(value, 4) for key, value in edge_leakage.items()},
        "detectors": detector_results,
    }


def _trim_with_padding(value: int, *, min_px: int, keep_px: int) -> int:
    if value < min_px:
        return 0
    return max(0, value - keep_px)


def _qa_acceptance_threshold(crop_type: str, *, width: int, height: int) -> float:
    if crop_type == "chart" and width >= 240 and height >= 140:
        return 0.65
    if crop_type == "table":
        return 0.7
    return 0.72


def _content_trim_max_fraction(crop_type: str) -> float:
    if crop_type == "table":
        return 0.06
    if crop_type == "chart":
        return 0.07
    return 0.1


def _adaptive_keep_px(crop_type: str) -> int:
    if crop_type == "table":
        return 12
    if crop_type == "chart":
        return 10
    return 8


def _adaptive_edge_threshold(img: Image.Image) -> float:
    width, height = img.size
    probes = []
    for y in (0, max(0, height - 1), height // 2):
        probes.append(_edge_change_density(img, horizontal=True, index=y))
    for x in (0, max(0, width - 1), width // 2):
        probes.append(_edge_change_density(img, horizontal=False, index=x))
    return max(0.018, min(0.08, (sum(probes) / max(1, len(probes))) * 2.5))


def _edge_change_density(img: Image.Image, *, horizontal: bool, index: int) -> float:
    width, height = img.size
    if width <= 1 or height <= 1:
        return 0.0
    samples = 0
    changed = 0
    if horizontal:
        previous = img.getpixel((0, index))
        for x in range(1, width):
            current = img.getpixel((x, index))
            samples += 1
            if _pixel_delta(previous, current) > 18:
                changed += 1
            previous = current
    else:
        previous = img.getpixel((index, 0))
        for y in range(1, height):
            current = img.getpixel((index, y))
            samples += 1
            if _pixel_delta(previous, current) > 18:
                changed += 1
            previous = current
    return changed / max(1, samples)


def _pixel_delta(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return max(abs(int(a[i]) - int(b[i])) for i in range(3))


def _edge_content_densities(img: Image.Image) -> dict[str, float]:
    width, height = img.size
    bg = _dominant_border_color(img)
    band = max(2, min(width, height) // 50)

    return {
        "top": _box_content_density(img, bg, (0, 0, width, min(height, band))),
        "bottom": _box_content_density(
            img, bg, (0, max(0, height - band), width, height)
        ),
        "left": _box_content_density(img, bg, (0, 0, min(width, band), height)),
        "right": _box_content_density(
            img, bg, (max(0, width - band), 0, width, height)
        ),
    }


def _edge_leakage_densities(
    img: Image.Image, edge_density: dict[str, float]
) -> dict[str, float]:
    width, height = img.size
    bg = _dominant_border_color(img)
    band = max(2, min(width, height) // 50)
    inner_band = band * 2

    adjacent_density = {
        "top": _box_content_density(
            img, bg, (0, min(height, band), width, min(height, band + inner_band))
        ),
        "bottom": _box_content_density(
            img,
            bg,
            (0, max(0, height - band - inner_band), width, max(0, height - band)),
        ),
        "left": _box_content_density(
            img, bg, (min(width, band), 0, min(width, band + inner_band), height)
        ),
        "right": _box_content_density(
            img,
            bg,
            (max(0, width - band - inner_band), 0, max(0, width - band), height),
        ),
    }
    return {
        edge: max(0.0, float(edge_density.get(edge, 0.0)) - adjacent_density[edge])
        for edge in ("top", "bottom", "left", "right")
    }


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
            if _pixel_delta(img.getpixel((x, y)), bg) > CROP_TRIM_TOLERANCE:
                content += 1
    return content / max(1, total)


def _image_content_density(img: Image.Image) -> float:
    width, height = img.size
    if width == 0 or height == 0:
        return 0.0
    bg = _dominant_border_color(img)
    step = max(1, min(width, height) // CROP_TRIM_SAMPLES)
    total = 0
    content = 0
    for y in range(0, height, step):
        for x in range(0, width, step):
            total += 1
            if _pixel_delta(img.getpixel((x, y)), bg) > CROP_TRIM_TOLERANCE:
                content += 1
    return content / max(1, total)


def _margin_balance_score(edge_density: dict[str, float]) -> float:
    horizontal = abs(edge_density.get("left", 0.0) - edge_density.get("right", 0.0))
    vertical = abs(edge_density.get("top", 0.0) - edge_density.get("bottom", 0.0))
    return max(0.0, 1.0 - min(1.0, horizontal + vertical))


def _visual_crispness_score(img: Image.Image) -> float:
    width, height = img.size
    if width <= 2 or height <= 2:
        return 0.0
    step = max(1, min(width, height) // 80)
    total = 0
    edges = 0
    for y in range(1, height - 1, step):
        for x in range(1, width - 1, step):
            total += 1
            horizontal = _pixel_delta(
                img.getpixel((x - 1, y)), img.getpixel((x + 1, y))
            )
            vertical = _pixel_delta(img.getpixel((x, y - 1)), img.getpixel((x, y + 1)))
            if max(horizontal, vertical) > 12:
                edges += 1
    return min(1.0, max(0.35, edges / max(1, total) * 4.0))


def _uniform_border_trim_amounts(
    img: Image.Image,
    *,
    allow_top: bool = True,
    allow_bottom: bool = True,
    allow_left: bool = True,
    allow_right: bool = True,
) -> tuple[int, int, int, int]:
    width, height = img.size
    if width == 0 or height == 0:
        return (0, 0, 0, 0)
    bg = _dominant_border_color(img)
    max_trim_y = int(height * CROP_TRIM_MAX_FRAC)
    max_trim_x = int(width * CROP_TRIM_MAX_FRAC)

    top = 0
    while (
        allow_top and top < max_trim_y and _row_is_bg(img, top, bg, CROP_TRIM_TOLERANCE)
    ):
        top += 1
    bottom = 0
    while (
        allow_bottom
        and bottom < max_trim_y
        and _row_is_bg(img, height - 1 - bottom, bg, CROP_TRIM_TOLERANCE)
    ):
        bottom += 1
    left = 0
    while (
        allow_left
        and left < max_trim_x
        and _col_is_bg(img, left, bg, CROP_TRIM_TOLERANCE)
    ):
        left += 1
    right = 0
    while (
        allow_right
        and right < max_trim_x
        and _col_is_bg(img, width - 1 - right, bg, CROP_TRIM_TOLERANCE)
    ):
        right += 1
    return (top, bottom, left, right)


def _stack_crop_images(images: list[Image.Image]) -> Image.Image:
    width = max(img.width for img in images)
    height = sum(img.height for img in images)
    canvas = Image.new("RGB", (width, height), (255, 255, 255))
    y = 0
    for img in images:
        x = max(0, (width - img.width) // 2)
        canvas.paste(img, (x, y))
        y += img.height
    return canvas


def _render_clip_image(
    page: fitz.Page, rect: fitz.Rect, *, render_scale: float = 2.0
) -> Image.Image:
    pix = page.get_pixmap(
        matrix=fitz.Matrix(render_scale, render_scale),
        clip=rect,
        alpha=False,
    )
    return Image.frombytes("RGB", (pix.width, pix.height), pix.samples)


__all__ = [
    "PDF_CROP_EXCEPTIONS",
    "PREVIEW_RENDER_EXCEPTIONS",
    "CROP_TRIM_MAX_FRAC",
    "CROP_TRIM_MIN_PX",
    "CROP_TRIM_KEEP_PX",
    "CROP_TRIM_TOLERANCE",
    "CROP_TRIM_MIN_BG_FRAC",
    "CROP_TRIM_SAMPLES",
    "_dominant_border_color",
    "_row_is_bg",
    "_col_is_bg",
    "_trim_uniform_border",
    "_content_aware_trim",
    "verify_crop_image",
    "_uniform_border_trim_amounts",
    "_stack_crop_images",
    "_render_clip_image",
]
