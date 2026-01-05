from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import pymupdf as fitz

from src.contracts.report_assets import PreviewRequest, PreviewResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

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
            "using_context": bool(request.pdf_context and request.pdf_context.fitz_doc),
        },
    ))
    img_path = _first_page_png(
        request.pdf_path,
        request.out_dir,
        request.report_name,
        dpi=request.dpi,
        doc=request.pdf_context.fitz_doc if request.pdf_context else None,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="preview_render_complete",
        module=logger.name,
        fields={"image_path": img_path or ""},
    ))
    return PreviewResponse(schema_version="1.0", image_path=img_path)


def _first_page_png(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    dpi: int = 144,
    doc: Optional[fitz.Document] = None,
) -> Optional[str]:
    try:
        out_root = Path(out_dir)
        out_root.mkdir(parents=True, exist_ok=True)

        img_dir = out_root / report_name / "assets"
        img_dir.mkdir(parents=True, exist_ok=True)

        abs_png = img_dir / f"{report_name}.png"

        local_doc = doc or fitz.open(pdf_path)
        try:
            if local_doc.page_count == 0:
                return None
            page = local_doc.load_page(0)
            zoom = dpi / 72.0
            pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            pix.save(abs_png.as_posix())
        finally:
            if doc is None:
                local_doc.close()

        rel_png = Path(report_name) / "assets" / abs_png.name
        return rel_png.as_posix()
    except Exception:
        return None
