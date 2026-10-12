"""Crop-refine page rendering and bbox application.

This module owns the local service helpers used by crop-refine workflows while
reusing shared crop geometry guards.
"""

from __future__ import annotations

from pathlib import Path

import pymupdf as fitz
from PIL import Image

from src.contracts.report_assets import (
    CROP_REFINE_COORDINATE_TRANSFORM_VERSION,
    CropRefineBBoxApplyRequest,
    CropRefineBBoxApplyResponse,
    CropRefinePageRenderRequest,
    CropRefinePageRenderResponse,
)
from src.contracts.run_context import RunContext
from src.services._pdf._crop.geometry import _crop_refine_edge_guard_rect
from src.services._pdf._crop.image_ops import _png_safe_pixmap
from src.services._pdf.fingerprint_cache import (
    CROP_REFINE_PAGE_ARTIFACT_VERSION,
    PdfArtifactFingerprintDescriptor,
    build_page_content_fingerprint,
    resolve_artifact_cache,
    write_artifact_sidecar,
)
from src.services._pdf.page_artifacts import create_page_artifact_cache
from src.services._pdf.shared import crop_logger
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.path_utils import safe_path_segment


def _matrix_coefficients(
    matrix: fitz.Matrix,
) -> tuple[float, float, float, float, float, float]:
    return tuple(float(value) for value in matrix)  # type: ignore[return-value]


def _page_render_response(
    *,
    page: fitz.Page,
    image_path: str,
    page_number: int,
    image_width: int,
    image_height: int,
) -> CropRefinePageRenderResponse:
    page_width = float(page.rect.width)
    page_height = float(page.rect.height)
    scale_x = (float(image_width) / page_width) if page_width > 0 else 0.0
    scale_y = (float(image_height) / page_height) if page_height > 0 else 0.0
    display_to_pdf = _matrix_coefficients(page.derotation_matrix)
    pdf_to_display = _matrix_coefficients(page.rotation_matrix)
    image_to_pdf = (
        display_to_pdf[0] / scale_x,
        display_to_pdf[1] / scale_x,
        display_to_pdf[2] / scale_y,
        display_to_pdf[3] / scale_y,
        display_to_pdf[4],
        display_to_pdf[5],
    )
    crop_box = page.cropbox
    media_box = page.mediabox
    return CropRefinePageRenderResponse(
        schema_version="1.1",
        image_path=image_path,
        page=page_number,
        image_width=image_width,
        image_height=image_height,
        page_width=page_width,
        page_height=page_height,
        scale_x=scale_x,
        scale_y=scale_y,
        coordinate_transform_version=CROP_REFINE_COORDINATE_TRANSFORM_VERSION,
        display_to_pdf_transform=display_to_pdf,
        pdf_to_display_transform=pdf_to_display,
        image_to_pdf_transform=image_to_pdf,
        rotation=int(page.rotation),
        crop_box=(
            float(crop_box.x0),
            float(crop_box.y0),
            float(crop_box.x1),
            float(crop_box.y1),
        ),
        media_box=(
            float(media_box.x0),
            float(media_box.y0),
            float(media_box.x1),
            float(media_box.y1),
        ),
        pdf_page_width=float(crop_box.width),
        pdf_page_height=float(crop_box.height),
    )


def render_page_for_crop_refine(
    request: CropRefinePageRenderRequest, ctx: RunContext
) -> CropRefinePageRenderResponse:
    crop_logger.info(
        log_event(
            ctx,
            role="service",
            event="crop_refine_page_render_start",
            module=crop_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "report_name": request.report_name,
                "page": request.page,
                "dpi": request.dpi,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.fitz_doc
                ),
            },
        )
    )
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
        safe_report_name = safe_path_segment(request.report_name, fallback="report")
        out_dir = Path(request.out_dir) / safe_report_name / "crop_refine_pages"
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = f"page-{request.page}.png"
        abs_path = out_dir / filename
        rel = (Path(safe_report_name) / "crop_refine_pages" / filename).as_posix()
        descriptor = PdfArtifactFingerprintDescriptor(
            artifact_kind="crop_refine_page_render",
            source_pdf_path=request.pdf_path,
            output_rel_path=rel,
            page=int(request.page),
            artifact_identity=f"crop_refine_page:{int(request.page)}",
            content_fingerprint=build_page_content_fingerprint(page),
            settings_payload={
                "dpi": int(request.dpi),
                "page": int(request.page),
            },
            artifact_version=CROP_REFINE_PAGE_ARTIFACT_VERSION,
        )
        cache_status = resolve_artifact_cache(descriptor, abs_path)
        if cache_status.hit:
            with Image.open(abs_path) as cached_img:
                image_width = int(cached_img.width)
                image_height = int(cached_img.height)
            crop_logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="crop_refine_page_render_cache_hit",
                    module=crop_logger.name,
                    fields={
                        "cache_key": cache_status.cache_key,
                        "source_artifact": cache_status.output_rel_path,
                        "validity_reason": cache_status.reason,
                        "page": int(request.page),
                    },
                )
            )
            response = _page_render_response(
                page=page,
                image_path=rel,
                page_number=request.page,
                image_width=image_width,
                image_height=image_height,
            )
        else:
            zoom = max(float(request.dpi), 72.0) / 72.0
            pix = _png_safe_pixmap(
                page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
            )
            pix.save(abs_path.as_posix())
            write_artifact_sidecar(descriptor, abs_path)
            crop_logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="crop_refine_page_render_cache_store",
                    module=crop_logger.name,
                    fields={
                        "cache_key": cache_status.cache_key,
                        "source_artifact": rel,
                        "validity_reason": cache_status.reason,
                        "page": int(request.page),
                    },
                )
            )
            response = _page_render_response(
                page=page,
                image_path=rel,
                page_number=request.page,
                image_width=int(pix.width),
                image_height=int(pix.height),
            )
    finally:
        if owns_doc and local_doc is not None:
            local_doc.close()
    crop_logger.info(
        log_event(
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
        )
    )
    return response


def apply_crop_refine_bbox(
    request: CropRefineBBoxApplyRequest, ctx: RunContext
) -> CropRefineBBoxApplyResponse:
    crop_logger.info(
        log_event(
            ctx,
            role="service",
            event="crop_refine_bbox_apply_start",
            module=crop_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "page": request.page,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.fitz_doc
                ),
            },
        )
    )
    local_doc = request.pdf_context.fitz_doc if request.pdf_context else None
    artifact_cache = (
        getattr(request.pdf_context, "page_artifact_cache", None)
        if request.pdf_context is not None
        else None
    ) or create_page_artifact_cache()
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
        page_bounds = fitz.Rect(0, 0, page.cropbox.width, page.cropbox.height)
        input_rect = fitz.Rect(*(float(value) for value in request.bbox))
        original_rect = fitz.Rect(*(float(value) for value in request.original_bbox))
        degradation_reason = ""
        rect = input_rect & page_bounds
        outside_page = (
            rect.is_empty
            or input_rect.x0 < page_bounds.x0
            or input_rect.y0 < page_bounds.y0
            or input_rect.x1 > page_bounds.x1
            or input_rect.y1 > page_bounds.y1
        )
        original_clipped = original_rect & page_bounds
        original_outside_page = (
            original_clipped.is_empty
            or original_rect.x0 < page_bounds.x0
            or original_rect.y0 < page_bounds.y0
            or original_rect.x1 > page_bounds.x1
            or original_rect.y1 > page_bounds.y1
        )
        if original_outside_page:
            raise AppError(
                code="crop_refine_original_bbox_invalid",
                message="Crop refine source candidate geometry is outside the page",
                retryable=False,
                context={"page": request.page},
            )
        if outside_page:
            rect = fitz.Rect(original_clipped)
            degradation_reason = "proposal_outside_page_fallback"
        page_area = max(page_bounds.get_area(), 1.0)
        if (
            not request.full_page_target
            and rect.get_area() / page_area >= 0.9
            and original_clipped.get_area() / page_area < 0.85
        ):
            rect = fitz.Rect(original_clipped)
            degradation_reason = "near_page_expansion_fallback"
        rect = _crop_refine_edge_guard_rect(
            page,
            rect,
            artifact_cache=artifact_cache,
        )
        if rect.width < 1:
            rect = fitz.Rect(
                rect.x0, rect.y0, min(page_bounds.x1, rect.x0 + 1), rect.y1
            )
        if rect.height < 1:
            rect = fitz.Rect(
                rect.x0, rect.y0, rect.x1, min(page_bounds.y1, rect.y0 + 1)
            )
        response = CropRefineBBoxApplyResponse(
            schema_version="1.1",
            page=request.page,
            bbox=(float(rect.x0), float(rect.y0), float(rect.x1), float(rect.y1)),
            degradation_reason=degradation_reason,
        )
    finally:
        if owns_doc and local_doc is not None:
            local_doc.close()
    crop_logger.info(
        log_event(
            ctx,
            role="service",
            event="crop_refine_bbox_apply_complete",
            module=crop_logger.name,
            fields={
                "page": response.page,
                "bbox": response.bbox,
                "input_bbox": (
                    float(input_rect.x0),
                    float(input_rect.y0),
                    float(input_rect.x1),
                    float(input_rect.y1),
                ),
            },
        )
    )
    return response


__all__ = ["render_page_for_crop_refine", "apply_crop_refine_bbox"]
