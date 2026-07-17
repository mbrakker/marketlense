"""Preview page rendering for PDF crop-related assets.

This module owns preview image generation and cache fingerprints; crop-region
rendering and crop-refine rendering live in their focused owners.
"""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Optional

import pymupdf as fitz

from src.contracts.report_assets import PreviewRequest, PreviewResponse
from src.contracts.run_context import RunContext
from src.services._pdf._crop.image_ops import PREVIEW_RENDER_EXCEPTIONS
from src.services._pdf.fingerprint_cache import (
    PREVIEW_ARTIFACT_VERSION,
    PdfArtifactFingerprintDescriptor,
    build_page_content_fingerprint,
    resolve_artifact_cache,
    write_artifact_sidecar,
)
from src.services._pdf.shared import preview_logger
from src.utils.logging import log_event
from src.utils.path_utils import bounded_artifact_filename, safe_path_segment
from src.utils.slugify import slugify

_WINDOWS_SAFE_ARTIFACT_PATH_LENGTH = 240
_FINGERPRINT_TEMP_SUFFIX_LENGTH = len(".fingerprint.json.tmp-write-") + 10
_COMPACT_PREVIEW_FILENAME_LENGTH = 33


def render_preview(request: PreviewRequest, ctx: RunContext) -> PreviewResponse:
    preview_logger.info(
        log_event(
            ctx,
            role="service",
            event="preview_render_start",
            module=preview_logger.name,
            fields={
                "pdf_path": request.pdf_path,
                "dpi": request.dpi,
                "page_number": request.page_number,
                "variant": request.variant,
                "using_context": bool(
                    request.pdf_context and request.pdf_context.fitz_doc
                ),
            },
        )
    )
    try:
        img_path = _page_png(
            request.pdf_path,
            request.out_dir,
            request.report_name,
            page_number=max(request.page_number, 0),
            dpi=request.dpi,
            variant=request.variant,
            doc=request.pdf_context.fitz_doc if request.pdf_context else None,
            ctx=ctx,
        )
    except PREVIEW_RENDER_EXCEPTIONS as exc:
        preview_logger.info(
            log_event(
                ctx,
                role="service",
                event="preview_render_failed",
                module=preview_logger.name,
                fields={
                    "pdf_path": request.pdf_path,
                    "page_number": request.page_number,
                    "error": str(exc),
                },
            )
        )
        img_path = None
    preview_logger.info(
        log_event(
            ctx,
            role="service",
            event="preview_render_complete",
            module=preview_logger.name,
            fields={"image_path": img_path or "", "page_number": request.page_number},
        )
    )
    return PreviewResponse(
        schema_version="1.1",
        image_path=img_path,
        page_number=max(request.page_number, 0),
    )


def _page_png(
    pdf_path: str,
    out_dir: str,
    report_name: str,
    page_number: int = 0,
    dpi: int = 144,
    variant: str | None = None,
    doc: Optional[fitz.Document] = None,
    ctx: RunContext | None = None,
) -> Optional[str]:
    out_root = Path(out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    variant_slug = slugify(variant) if variant else ""
    original_report_name = safe_path_segment(report_name, fallback="report")
    filename = _preview_filename(original_report_name, variant_slug)
    if _artifact_cache_temp_path_length(out_root, original_report_name, filename) > (
        _WINDOWS_SAFE_ARTIFACT_PATH_LENGTH
    ):
        filename = _preview_filename(
            original_report_name,
            variant_slug,
            max_length=_COMPACT_PREVIEW_FILENAME_LENGTH,
        )
    safe_report_name = _bounded_preview_report_name(
        out_root,
        original_report_name,
        filename,
    )
    img_dir = out_root / safe_report_name / "assets"
    img_dir.mkdir(parents=True, exist_ok=True)
    abs_png = img_dir / filename

    local_doc = doc or fitz.open(pdf_path)
    try:
        if local_doc.page_count == 0 or page_number >= local_doc.page_count:
            return None
        page = local_doc.load_page(page_number)
        rel_png = Path(safe_report_name) / "assets" / abs_png.name
        descriptor = PdfArtifactFingerprintDescriptor(
            artifact_kind="preview_render",
            source_pdf_path=pdf_path,
            output_rel_path=rel_png.as_posix(),
            page=int(page_number),
            artifact_identity=(
                f"preview:{int(page_number)}:{slugify(variant) if variant else ''}"
            ),
            content_fingerprint=build_page_content_fingerprint(page),
            settings_payload={
                "dpi": int(dpi),
                "variant": slugify(variant) if variant else "",
                "page": int(page_number),
            },
            artifact_version=PREVIEW_ARTIFACT_VERSION,
        )
        cache_status = resolve_artifact_cache(descriptor, abs_png)
        if cache_status.hit:
            if ctx is not None:
                preview_logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="preview_render_cache_hit",
                        module=preview_logger.name,
                        fields={
                            "cache_key": cache_status.cache_key,
                            "source_artifact": cache_status.output_rel_path,
                            "validity_reason": cache_status.reason,
                            "page_number": int(page_number),
                        },
                    )
                )
            return rel_png.as_posix()
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        pix.save(abs_png.as_posix())
        write_artifact_sidecar(descriptor, abs_png)
        if ctx is not None:
            preview_logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="preview_render_cache_store",
                    module=preview_logger.name,
                    fields={
                        "cache_key": cache_status.cache_key,
                        "source_artifact": rel_png.as_posix(),
                        "validity_reason": cache_status.reason,
                        "page_number": int(page_number),
                    },
                )
            )
    finally:
        if doc is None:
            local_doc.close()

    return rel_png.as_posix()


def _preview_filename(
    report_name: str, variant_slug: str, *, max_length: int = 96
) -> str:
    suffix = f"-{variant_slug}" if variant_slug else ""
    return bounded_artifact_filename(
        f"{report_name}{suffix}",
        compact_stem=f"preview{suffix}",
        extension=".png",
        max_length=max_length,
    )


def _bounded_preview_report_name(
    out_root: Path, report_name: str, filename: str
) -> str:
    """Keep preview artifacts below the Windows path limit in deep workspaces."""
    if _artifact_cache_temp_path_length(out_root, report_name, filename) <= (
        _WINDOWS_SAFE_ARTIFACT_PATH_LENGTH
    ):
        return report_name
    digest = sha256(report_name.encode("utf-8")).hexdigest()[:12]
    base_length = _artifact_cache_temp_path_length(out_root, digest, filename)
    prefix_budget = max(0, _WINDOWS_SAFE_ARTIFACT_PATH_LENGTH - base_length - 1)
    prefix = report_name[:prefix_budget].rstrip(" .-_")
    return f"{prefix}-{digest}" if prefix else digest


def _artifact_cache_temp_path_length(
    out_root: Path, report_name: str, filename: str
) -> int:
    return (
        len(str(out_root / report_name / "assets" / filename))
        + _FINGERPRINT_TEMP_SUFFIX_LENGTH
    )


__all__ = ["render_preview", "_page_png"]
