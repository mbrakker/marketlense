from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pymupdf as fitz

from src.contracts.report_assets import PreviewRequest, PreviewResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.preview_service")


def render_preview(request: PreviewRequest, ctx: RunContext) -> PreviewResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="preview_render_start",
        module=logger.name,
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
        logger.info(log_event(
            ctx,
            role="service",
            event="preview_render_failed",
            module=logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "page_number": request.page_number,
                "error": str(exc),
            },
        ))
        img_path = None
    logger.info(log_event(
        ctx,
        role="service",
        event="preview_render_complete",
        module=logger.name,
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
