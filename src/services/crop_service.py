from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List, Optional

import pymupdf as fitz

from src.contracts.report_models import CropItem
from src.contracts.report_assets import CropRequest, CropResponse
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.crop_service")


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
            if idx == 0:
                filename = f"{report_name}.png"
            else:
                filename = f"{report_name}{idx}.png"
            op = output_dir / filename
            pix.save(op.as_posix())
            rel = Path(report_name) / safe_subdir / filename
            paths.append(rel.as_posix())
    finally:
        if doc is None:
            local_doc.close()
    return paths
