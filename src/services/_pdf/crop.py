from __future__ import annotations

from pathlib import Path
from typing import Iterable, List, Optional

import pymupdf as fitz
from PIL import Image

from src.contracts.report_assets import (
    CropRefineBBoxApplyRequest,
    CropRefineBBoxApplyResponse,
    CropRefinePageRenderRequest,
    CropRefinePageRenderResponse,
    CropRequest,
    CropResponse,
    PreviewRequest,
    PreviewResponse,
)
from src.contracts.report_models import CropItem
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.slugify import slugify

from .figures import (
    CROP_REFINE_BBOX_PAD_MAX,
    CROP_REFINE_BBOX_PAD_MIN,
    CROP_REFINE_BBOX_PAD_X_FRAC,
    CROP_REFINE_BBOX_PAD_Y_FRAC,
    CROP_REFINE_EDGE_INCLUDE_OVERLAP_RATIO,
    CROP_REFINE_EDGE_MIN_OVERLAP,
    CROP_REFINE_EDGE_TOUCH_TOL,
    CROP_REFINE_EDGE_TRIM_OVERLAP_RATIO,
    _clamp_bottom_to_note,
    _horizontal_overlap_ratio,
    _is_page_number_text,
    _note_block_bottom,
    _vertical_overlap_ratio,
)
from .shared import crop_logger, preview_logger

# BEGIN PDF CROPPING
CROP_TRIM_MAX_FRAC = 0.08
CROP_TRIM_MIN_PX = 12
CROP_TRIM_KEEP_PX = 8
CROP_TRIM_TOLERANCE = 8
CROP_TRIM_MIN_BG_FRAC = 0.9995
CROP_TRIM_SAMPLES = 60
CROP_STRICT_EDGE_TOUCH_TOL = 1.0
CROP_STRICT_EDGE_MIN_OVERLAP = 0.2
CROP_STRICT_EDGE_TRIM_OVERLAP_RATIO = 0.25
CROP_STRICT_EDGE_TRIM_MARGIN = 1.0
CROP_FILENAME_ID_MAX_LEN = 96


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


def _tighten_crop_rect_for_strict_mode(page: fitz.Page, rect: fitz.Rect, *, mode: str) -> fitz.Rect:
    adjusted = fitz.Rect(rect)
    page_rect = page.rect
    blocks = _crop_refine_text_blocks(page)

    if blocks:
        for _ in range(2):
            changed = False
            for block in blocks:
                inter = adjusted & block
                if inter.is_empty:
                    continue
                overlap_ratio = inter.get_area() / max(block.get_area(), 1.0)
                if overlap_ratio > CROP_STRICT_EDGE_TRIM_OVERLAP_RATIO:
                    continue
                h_overlap = _horizontal_overlap_ratio(block, adjusted)
                crosses_bottom = (
                    block.y0 < adjusted.y1 - CROP_STRICT_EDGE_TOUCH_TOL
                    and block.y1 > adjusted.y1 + CROP_STRICT_EDGE_TOUCH_TOL
                    and h_overlap >= CROP_STRICT_EDGE_MIN_OVERLAP
                )
                if not crosses_bottom:
                    continue
                new_bottom = min(adjusted.y1, block.y0 - CROP_STRICT_EDGE_TRIM_MARGIN)
                if new_bottom > adjusted.y0 + 1:
                    adjusted.y1 = new_bottom
                    changed = True
            adjusted &= page_rect
            if not changed:
                break

    # For strict table/chart crops keep note/source/statlink lines but
    # clamp away the next prose section that often follows immediately.
    if mode in {"table_strict", "chart_strict"}:
        note_min_y0_frac = 0.25 if mode == "table_strict" else 0.35
        note_bottom = _note_block_bottom(page, adjusted, min_y0_frac=note_min_y0_frac)
        if note_bottom is not None:
            adjusted = _clamp_bottom_to_note(page, adjusted, note_bottom, page_rect) & page_rect

    if adjusted.width < 1 or adjusted.height < 1:
        return rect & page_rect
    return adjusted


def _crop_output_filename(report_name: str, item: CropItem, idx: int) -> str:
    item_slug = slugify(str(item.id or ""))
    if not item_slug:
        item_slug = f"item-{idx}"
    if len(item_slug) > CROP_FILENAME_ID_MAX_LEN:
        item_slug = item_slug[:CROP_FILENAME_ID_MAX_LEN]
    return f"{report_name}-{item_slug}.png"


def crop_regions(request: CropRequest, ctx: RunContext) -> CropResponse:
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_regions_start",
        module=crop_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "count": len(request.items),
            "subdir": request.subdir,
            "mode": request.mode,
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
        mode=request.mode,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
    )
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_regions_complete",
        module=crop_logger.name,
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
    mode: str = "legacy",
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
            if mode in {"table_strict", "chart_strict", "figure_strict"}:
                r = _tighten_crop_rect_for_strict_mode(
                    page,
                    r,
                    mode=mode,
                )
            if r.is_empty:
                continue
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), clip=r, alpha=False)
            img = None
            if mode == "figure_strict":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    img = _trim_uniform_border(
                        img,
                        allow_top=True,
                        allow_bottom=True,
                        allow_left=True,
                        allow_right=True,
                    )
                except Exception:
                    img = None
            elif mode == "table_strict":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    img = _trim_uniform_border(img, allow_top=False, allow_bottom=True, allow_left=True, allow_right=True)
                except Exception:
                    img = None
            elif mode == "chart_strict" or it.type == "chart":
                try:
                    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
                    if mode == "chart_strict":
                        img = _trim_uniform_border(
                            img,
                            allow_top=True,
                            allow_bottom=True,
                            allow_left=True,
                            allow_right=True,
                        )
                    else:
                        img = _trim_uniform_border(img, allow_bottom=False, allow_right=False)
                except Exception:
                    img = None
            filename = _crop_output_filename(report_name, it, idx)
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


def render_page_for_crop_refine(request: CropRefinePageRenderRequest, ctx: RunContext) -> CropRefinePageRenderResponse:
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_refine_page_render_start",
        module=crop_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "report_name": request.report_name,
            "page": request.page,
            "dpi": request.dpi,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    local_doc = request.pdf_context.fitz_doc if request.pdf_context else None
    owns_doc = local_doc is None
    if local_doc is None:
        local_doc = fitz.open(request.pdf_path)
    try:
        if request.page < 0 or request.page >= local_doc.page_count:
            raise AppError(
                code="crop_refine_page_out_of_range",
                message=f"Crop refine page out of range: {request.page}",
                retryable=False,
                context={"page_count": local_doc.page_count},
            )
        page = local_doc[request.page]
        zoom = max(float(request.dpi), 72.0) / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        out_dir = Path(request.out_dir) / request.report_name / "crop_refine_pages"
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"page-{request.page}.png"
        abs_path = out_dir / filename
        pix.save(abs_path.as_posix())
        rel = (Path(request.report_name) / "crop_refine_pages" / filename).as_posix()
        page_width = float(page.rect.width)
        page_height = float(page.rect.height)
        scale_x = (float(pix.width) / page_width) if page_width > 0 else 0.0
        scale_y = (float(pix.height) / page_height) if page_height > 0 else 0.0
        response = CropRefinePageRenderResponse(
            schema_version="1.0",
            image_path=rel,
            page=request.page,
            image_width=int(pix.width),
            image_height=int(pix.height),
            page_width=page_width,
            page_height=page_height,
            scale_x=scale_x,
            scale_y=scale_y,
        )
    finally:
        if owns_doc and local_doc is not None:
            local_doc.close()
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_refine_page_render_complete",
        module=crop_logger.name,
        fields={
            "page": response.page,
            "image_path": response.image_path,
            "image_width": response.image_width,
            "image_height": response.image_height,
        },
    ))
    return response


def apply_crop_refine_bbox(request: CropRefineBBoxApplyRequest, ctx: RunContext) -> CropRefineBBoxApplyResponse:
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_refine_bbox_apply_start",
        module=crop_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "page": request.page,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    local_doc = request.pdf_context.fitz_doc if request.pdf_context else None
    owns_doc = local_doc is None
    if local_doc is None:
        local_doc = fitz.open(request.pdf_path)
    try:
        if request.page < 0 or request.page >= local_doc.page_count:
            raise AppError(
                code="crop_refine_page_out_of_range",
                message=f"Crop refine page out of range: {request.page}",
                retryable=False,
                context={"page_count": local_doc.page_count},
            )
        page = local_doc[request.page]
        x0, y0, x1, y1 = request.bbox
        input_rect = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
        rect = input_rect & page.rect
        if rect.is_empty:
            rect = page.rect
        rect = _crop_refine_edge_guard_rect(page, rect)
        if rect.width < 1:
            rect = fitz.Rect(rect.x0, rect.y0, min(page.rect.x1, rect.x0 + 1), rect.y1)
        if rect.height < 1:
            rect = fitz.Rect(rect.x0, rect.y0, rect.x1, min(page.rect.y1, rect.y0 + 1))
        response = CropRefineBBoxApplyResponse(
            schema_version="1.0",
            page=request.page,
            bbox=(float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)),
        )
    finally:
        if owns_doc and local_doc is not None:
            local_doc.close()
    crop_logger.info(log_event(
        ctx,
        role="service",
        event="crop_refine_bbox_apply_complete",
        module=crop_logger.name,
        fields={
            "page": response.page,
            "bbox": response.bbox,
            "input_bbox": (float(input_rect.x0), float(input_rect.y0), float(input_rect.x1), float(input_rect.y1)),
        },
    ))
    return response


def _crop_refine_text_blocks(page: fitz.Page) -> list[fitz.Rect]:
    blocks: list[fitz.Rect] = []
    try:
        raw_blocks = page.get_text("blocks")
    except Exception:
        return blocks
    for x0, y0, x1, y1, text, *_ in raw_blocks:
        text_str = str(text or "").strip()
        if not text_str:
            continue
        if _is_page_number_text(text_str):
            continue
        blocks.append(fitz.Rect(float(x0), float(y0), float(x1), float(y1)))
    return blocks


def _crop_refine_edge_guard_rect(page: fitz.Page, rect: fitz.Rect) -> fitz.Rect:
    page_rect = page.rect
    pad_x = min(max(page_rect.width * CROP_REFINE_BBOX_PAD_X_FRAC, CROP_REFINE_BBOX_PAD_MIN), CROP_REFINE_BBOX_PAD_MAX)
    pad_y = min(max(page_rect.height * CROP_REFINE_BBOX_PAD_Y_FRAC, CROP_REFINE_BBOX_PAD_MIN), CROP_REFINE_BBOX_PAD_MAX)
    adjusted = fitz.Rect(rect.x0 - pad_x, rect.y0 - pad_y, rect.x1 + pad_x, rect.y1 + pad_y) & page_rect
    blocks = _crop_refine_text_blocks(page)
    if not blocks:
        return adjusted

    def _edge_cross(block: fitz.Rect, target: fitz.Rect) -> tuple[bool, bool, bool, bool]:
        tol = CROP_REFINE_EDGE_TOUCH_TOL
        v_overlap = _vertical_overlap_ratio(block, target)
        h_overlap = _horizontal_overlap_ratio(block, target)
        crosses_left = (
            block.x0 < target.x0 - tol
            and block.x1 > target.x0 + tol
            and v_overlap >= CROP_REFINE_EDGE_MIN_OVERLAP
        )
        crosses_right = (
            block.x0 < target.x1 - tol
            and block.x1 > target.x1 + tol
            and v_overlap >= CROP_REFINE_EDGE_MIN_OVERLAP
        )
        crosses_top = (
            block.y0 < target.y0 - tol
            and block.y1 > target.y0 + tol
            and h_overlap >= CROP_REFINE_EDGE_MIN_OVERLAP
        )
        crosses_bottom = (
            block.y0 < target.y1 - tol
            and block.y1 > target.y1 + tol
            and h_overlap >= CROP_REFINE_EDGE_MIN_OVERLAP
        )
        return crosses_left, crosses_right, crosses_top, crosses_bottom

    # Pass 1: if a text block is meaningfully intersected, expand to include full text.
    for block in blocks:
        inter = adjusted & block
        if inter.is_empty:
            continue
        overlap_ratio = inter.get_area() / max(block.get_area(), 1.0)
        if overlap_ratio < CROP_REFINE_EDGE_INCLUDE_OVERLAP_RATIO:
            continue
        crosses_left, crosses_right, crosses_top, crosses_bottom = _edge_cross(block, adjusted)
        if crosses_left:
            adjusted.x0 = min(adjusted.x0, block.x0)
        if crosses_right:
            adjusted.x1 = max(adjusted.x1, block.x1)
        if crosses_top:
            adjusted.y0 = min(adjusted.y0, block.y0)
        if crosses_bottom:
            adjusted.y1 = max(adjusted.y1, block.y1)
    adjusted &= page_rect

    # Pass 2: if only a tiny fraction of a text block is clipped at the edge, trim it away.
    for block in blocks:
        inter = adjusted & block
        if inter.is_empty:
            continue
        overlap_ratio = inter.get_area() / max(block.get_area(), 1.0)
        if overlap_ratio > CROP_REFINE_EDGE_TRIM_OVERLAP_RATIO:
            continue
        crosses_left, crosses_right, crosses_top, crosses_bottom = _edge_cross(block, adjusted)
        if crosses_left:
            adjusted.x0 = max(adjusted.x0, block.x1)
        if crosses_right:
            adjusted.x1 = min(adjusted.x1, block.x0)
        if crosses_top:
            adjusted.y0 = max(adjusted.y0, block.y1)
        if crosses_bottom:
            adjusted.y1 = min(adjusted.y1, block.y0)
    adjusted &= page_rect

    if adjusted.width < 1 or adjusted.height < 1:
        return rect & page_rect
    return adjusted


# BEGIN PDF PREVIEW
def render_preview(request: PreviewRequest, ctx: RunContext) -> PreviewResponse:
    preview_logger.info(log_event(
        ctx,
        role="service",
        event="preview_render_start",
        module=preview_logger.name,
        fields={
            "pdf_path": request.pdf_path,
            "dpi": request.dpi,
            "page_number": request.page_number,
            "variant": request.variant,
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    try:
        img_path = _page_png(
            request.pdf_path,
            request.out_dir,
            request.report_name,
            page_number=max(request.page_number, 0),
            dpi=request.dpi,
            variant=request.variant,
            doc=request.pdf_context.fitz_doc if request.pdf_context else None,
        )
    except Exception as exc:
        preview_logger.info(log_event(
            ctx,
            role="service",
            event="preview_render_failed",
            module=preview_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "page_number": request.page_number,
                "error": str(exc),
            },
        ))
        img_path = None
    preview_logger.info(log_event(
        ctx,
        role="service",
        event="preview_render_complete",
        module=preview_logger.name,
        fields={"image_path": img_path or "", "page_number": request.page_number},
    ))
    return PreviewResponse(schema_version="1.1", image_path=img_path, page_number=max(request.page_number, 0))


def _page_png(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    page_number: int = 0,
    dpi: int = 144,
    variant: str | None = None,
    doc: Optional[fitz.Document] = None,
) -> Optional[str]:
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    img_dir = out_root / report_name / "assets"
    img_dir.mkdir(parents=True, exist_ok=True)

    variant_slug = slugify(variant) if variant else ""
    suffix = f"-{variant_slug}" if variant_slug else ""
    abs_png = img_dir / f"{report_name}{suffix}.png"

    local_doc = doc or fitz.open(pdf_path)
    try:
        if local_doc.page_count == 0 or page_number >= local_doc.page_count:
            return None
        page = local_doc.load_page(page_number)
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(abs_png.as_posix())
    finally:
        if doc is None:
            local_doc.close()

    rel_png = Path(report_name) / "assets" / abs_png.name
    return rel_png.as_posix()
