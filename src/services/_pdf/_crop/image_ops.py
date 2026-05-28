"""Image-level operations for PDF crop artifacts.

This module owns deterministic raster trimming and image composition helpers
shared by crop rendering, without PDF workflow coordination.
"""

from __future__ import annotations

from typing import List

import pymupdf as fitz
from PIL import Image

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


def _render_clip_image(page: fitz.Page, rect: fitz.Rect) -> Image.Image:
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=rect, alpha=False)
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
    "_uniform_border_trim_amounts",
    "_stack_crop_images",
    "_render_clip_image",
]
