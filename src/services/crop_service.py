from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List, Optional

import pymupdf as fitz
from PIL import Image

from src.contracts.report_models import CropItem
from src.contracts.report_assets import CropRequest, CropResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.crop_service")

CROP_TRIM_MAX_FRAC = 0.08
CROP_TRIM_MIN_PX = 12
CROP_TRIM_KEEP_PX = 2
CROP_TRIM_TOLERANCE = 8
CROP_TRIM_MIN_BG_FRAC = 0.98
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
    return max(counts, key=counts.get)


def _row_is_bg(img: Image.Image, y: int, bg: tuple[int, int, int], tol: int) -> bool:
    width, _ = img.size
    step = max(1, width // CROP_TRIM_SAMPLES)
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
    step = max(1, height // CROP_TRIM_SAMPLES)
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
    while allow_top and top < max_trim_y and _row_is_bg(img, top, bg, CROP_TRIM_TOLERANCE):
        top += 1
    bottom = 0
    while allow_bottom and bottom < max_trim_y and _row_is_bg(img, height - 1 - bottom, bg, CROP_TRIM_TOLERANCE):
        bottom += 1
    left = 0
    while allow_left and left < max_trim_x and _col_is_bg(img, left, bg, CROP_TRIM_TOLERANCE):
        left += 1
    right = 0
    while allow_right and right < max_trim_x and _col_is_bg(img, width - 1 - right, bg, CROP_TRIM_TOLERANCE):
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


def crop_regions(request: CropRequest, ctx: RunContext) -> CropResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="crop_regions_start",
        module=logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "count": len(request.items),
            "subdir": request.subdir,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    paths = _crop_regions(
        request.pdf_path,
        request.out_dir,
        request.report_name,
        request.subdir,
        request.items,
        pad=request.pad,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="crop_regions_complete",
        module=logger.name,
        fields={"count": len(paths)},
    ))
    return CropResponse(schema_version="1.0", paths=paths)


def _crop_regions(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    subdir: str,
    items: Iterable[CropItem],
    pad: int = 8,
    doc: Optional[fitz.Document] = None,
) -> List[str]:
    safe_subdir = subdir or "slices"
    output_dir = Path(out_dir) / report_name / safe_subdir
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    local_doc = doc or fitz.open(pdf_path)
    try:
        for idx, it in enumerate(items):
            pno = it.page
            x0, y0, x1, y1 = it.bbox
            page = local_doc[pno]
            r = fitz.Rect(x0 - pad, y0 - pad, x1 + pad, y1 + pad)
            r = r & page.rect
            if r.is_empty:
                continue
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=r, alpha=False)
            img = None
            if it.type == "chart":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    img = _trim_uniform_border(img, allow_bottom=False)
                except Exception:
                    img = None
            if idx == 0:
                filename = f"{report_name}.png"
            else:
                filename = f"{report_name}{idx}.png"
            op = output_dir / filename
            if img is not None:
                img.save(op.as_posix())
            else:
                pix.save(op.as_posix())
            rel = Path(report_name) / safe_subdir / filename
            paths.append(rel.as_posix())
    finally:
        if doc is None:
            local_doc.close()
    return paths
