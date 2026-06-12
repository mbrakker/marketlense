from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

import hashlib
import random
from typing import Optional

from src.contracts.pdf_contents import PdfContentsDetectionRequest
from src.contracts.pdf_context import PdfContext, PdfContextBuildRequest
from src.contracts.pdf_text import PdfTextExtractRequest, PdfTextExtractResponse
from src.contracts.pdf_utils import PdfInfoRequest, PdfInfoResponse
from src.contracts.report_assets import PreviewRequest
from src.contracts.report_generation import ReportRuntimeState
from src.generators.report_generation_dependencies import ReportSourceDependencies
from src.generators.report_generation_shared import (
    contents_cache_key,
    logger,
    pdf_info_cache_key,
    text_cache_key,
)
from src.generators.report_source_cache import (
    bind_report_source_cache,
    load_report_source_cache,
    write_report_source_cache,
)
from src.utils.logging import child_context, log_event

from .shared import *  # noqa: F401,F403
from .shared import TextStatus
from .cache_io import _adapt_cached_contents, _adapt_cached_pdf_info, _adapt_cached_text


def _select_sample_pages(
    file_id: str, md5: Optional[str], page_count: int, sample_count: int
) -> list[int]:
    if page_count <= 0 or sample_count <= 0:
        return []
    count = min(sample_count, page_count)
    seed_input = f"{file_id}:{md5 or ''}:{page_count}"
    seed = int(hashlib.sha256(seed_input.encode("utf-8")).hexdigest(), 16) % (2**32)
    rng = random.Random(seed)
    return sorted(rng.sample(range(page_count), count))


def _report_worker_config(runtime: ReportRuntimeState) -> tuple[int, bool]:
    report_worker_limit = runtime.report_worker_limit
    if report_worker_limit < 1:
        report_worker_limit = 1
    parallel_within_file = runtime.parallel_within_file and report_worker_limit > 1
    return report_worker_limit, parallel_within_file


def _build_pdf_context(
    runtime: ReportRuntimeState,
    dependencies: ReportSourceDependencies,
) -> PdfContext | None:
    if runtime.parallel_within_file:
        return None
    try:
        ctx_pdf = child_context(
            runtime.ctx, task_id=f"{runtime.ctx.task_id}:pdf_context"
        )
        pdf_ctx_resp = dependencies.build_pdf_context(
            PdfContextBuildRequest(
                schema_version="1.0",
                path=runtime.local_pdf_path,
            ),
            ctx_pdf,
        )
        if pdf_ctx_resp.fitz_error or pdf_ctx_resp.pypdf_error:
            logger.info(
                log_event(
                    ctx_pdf,
                    role="generator",
                    event="pdf_context_partial",
                    module=logger.name,
                    fields={
                        "fitz_ready": pdf_ctx_resp.context.fitz_doc is not None,
                        "pypdf_ready": pdf_ctx_resp.context.pypdf_reader is not None,
                        "fitz_error": pdf_ctx_resp.fitz_error or "",
                        "pypdf_error": pdf_ctx_resp.pypdf_error or "",
                    },
                )
            )
        return pdf_ctx_resp.context
    except Exception as exc:
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="pdf_context_unavailable",
                module=logger.name,
                fields={"path": runtime.local_pdf_path, "error": str(exc)},
            )
        )
        return None


def _load_pdf_info(
    runtime: ReportRuntimeState,
    pdf_context_for_tasks: PdfContext | None,
    dependencies: ReportSourceDependencies,
) -> PdfInfoResponse:
    info_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:pdf_info")
    info_binding = bind_report_source_cache(
        settings=runtime.settings,
        md5=runtime.md5,
        file_id=runtime.file.file_id,
        phase="pdf_info",
        prefix="pdf_info",
        cache_key=pdf_info_cache_key(runtime.md5) if runtime.md5 else "",
    )
    info_cached = load_report_source_cache(
        info_binding,
        ctx=info_ctx,
        dependencies=dependencies,
        adapt_payload=lambda payload: _adapt_cached_pdf_info(
            payload,
            pdf_path=runtime.local_pdf_path,
        ),
    )
    info_resp = info_cached.value
    info_cache_hit = info_cached.cache_hit
    if info_resp is None:
        info_resp = dependencies.extract_pdf_info(
            PdfInfoRequest(
                schema_version="1.0",
                path=runtime.local_pdf_path,
                pdf_context=pdf_context_for_tasks,
            ),
            info_ctx,
        )
        write_report_source_cache(
            info_binding,
            payload={
                "schema_version": "1.0",
                "key": info_binding.cache_key,
                "page_count": info_resp.page_count,
                "metadata": info_resp.metadata,
            },
            ctx=info_ctx,
            dependencies=dependencies,
        )
    logger.info(
        log_event(
            info_ctx,
            role="generator",
            event="pdf_info_loaded",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "page_count": info_resp.page_count,
                "metadata_keys": list(info_resp.metadata.keys()),
                "cache_hit": info_cache_hit,
            },
        )
    )
    return info_resp


def _load_contents(
    runtime: ReportRuntimeState,
    *,
    analysis_pdf_path: str,
    preview_pdf_path: str,
    detection_pdf_context: PdfContext | None,
    preview_pdf_context: PdfContext | None,
    cache_prefix: str,
    dependencies: ReportSourceDependencies,
) -> tuple[int, str, str]:
    contents_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:contents")
    local_contents_page = 0
    local_contents_heading = ""
    local_contents_image = ""
    try:
        contents_binding = bind_report_source_cache(
            settings=runtime.settings,
            md5=runtime.md5,
            file_id=runtime.file.file_id,
            phase="contents",
            prefix=cache_prefix,
            cache_key=contents_cache_key(runtime.md5, runtime.settings)
            if runtime.md5
            else "",
        )
        contents_cached = load_report_source_cache(
            contents_binding,
            ctx=contents_ctx,
            dependencies=dependencies,
            adapt_payload=lambda payload: _adapt_cached_contents(
                payload,
                analysis_pdf_path=analysis_pdf_path,
            ),
        )
        contents_resp = contents_cached.value
        contents_cache_hit = contents_cached.cache_hit
        if contents_resp is None:
            contents_resp = dependencies.detect_contents_page(
                PdfContentsDetectionRequest(
                    schema_version="1.0",
                    path=analysis_pdf_path,
                    max_pages=runtime.settings.contents_max_pages,
                    min_headings=runtime.settings.contents_min_headings,
                    keywords=runtime.settings.contents_keywords,
                    pdf_context=detection_pdf_context,
                ),
                contents_ctx,
            )
            write_report_source_cache(
                contents_binding,
                payload={
                    "schema_version": "1.0",
                    "key": contents_binding.cache_key,
                    "has_contents": contents_resp.has_contents,
                    "page_index": contents_resp.page_index,
                    "page_number": contents_resp.page_number,
                    "heading": contents_resp.heading,
                    "confidence": contents_resp.confidence,
                },
                ctx=contents_ctx,
                dependencies=dependencies,
            )
        if contents_resp.has_contents:
            local_contents_page = contents_resp.page_number
            local_contents_heading = contents_resp.heading or ""
            if runtime.settings.contents_preview_enabled:
                contents_preview = dependencies.render_preview(
                    PreviewRequest(
                        schema_version="1.1",
                        pdf_path=preview_pdf_path,
                        out_dir=runtime.settings.output_dir,
                        report_name=runtime.report_name,
                        page_number=max(contents_resp.page_index, 0),
                        variant="contents",
                        dpi=runtime.settings.contents_preview_dpi,
                        pdf_context=preview_pdf_context,
                    ),
                    runtime.ctx,
                )
                if contents_preview.image_path:
                    local_contents_image = contents_preview.image_path
            else:
                logger.info(
                    log_event(
                        contents_ctx,
                        role="generator",
                        event="contents_preview_skipped",
                        module=logger.name,
                        fields={
                            "file_id": runtime.file.file_id,
                            "reason": "preview_disabled",
                        },
                    )
                )
        logger.info(
            log_event(
                contents_ctx,
                role="generator",
                event="contents_detection_result",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "has_contents": contents_resp.has_contents,
                    "page_number": local_contents_page,
                    "image_path": local_contents_image or "",
                    "cache_hit": contents_cache_hit,
                },
            )
        )
        return local_contents_page, local_contents_heading, local_contents_image
    except Exception as exc:
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="contents_detection_failed",
                module=logger.name,
                fields={"file_id": runtime.file.file_id, "error": str(exc)},
            )
        )
        return local_contents_page, local_contents_heading, local_contents_image


def _build_text_status(
    runtime: ReportRuntimeState, text_resp: PdfTextExtractResponse
) -> TextStatus:
    text_status: TextStatus = {
        "schema_version": "1.0",
        "text_density": float(text_resp.text_density or 0.0),
        "density_threshold": float(
            getattr(runtime.settings, "pdf_text_min_density", 0.0)
        ),
        "pages_sampled": text_resp.pages_extracted,
        "char_count": text_resp.char_count,
        "not_available": False,
        "reason": "",
        "native_sample_confidence_score": 0.0,
        "native_density_confidence_score": 0.0,
        "native_confidence_score": 0.0,
        "native_confidence_threshold": float(
            getattr(runtime.settings, "pdf_text_native_confidence_threshold", 0.55)
        ),
        "native_page_confidence_threshold": float(
            getattr(
                runtime.settings,
                "pdf_text_native_page_confidence_threshold",
                0.35,
            )
        ),
        "low_confidence_pages": [],
        "ocr_recommended": False,
        "ocr_recommendation_reason": "",
        "ocr_policy": str(
            getattr(runtime.settings, "pdf_text_ocr_policy", "native_first_selective")
            or "native_first_selective"
        ),
        "native_text_density": float(text_resp.text_density or 0.0),
        "native_text_not_available": False,
    }
    if (
        text_status["density_threshold"]
        and text_status["text_density"] < text_status["density_threshold"]
    ):
        text_status["not_available"] = True
        text_status["reason"] = "text_density_below_threshold"
        text_status["native_text_not_available"] = True
    return text_status


def _load_text(
    runtime: ReportRuntimeState,
    *,
    analysis_pdf_path: str,
    pdf_context_for_tasks: PdfContext | None,
    cache_prefix: str,
    dependencies: ReportSourceDependencies,
) -> tuple[PdfTextExtractResponse, TextStatus]:
    text_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:text")
    text_binding = bind_report_source_cache(
        settings=runtime.settings,
        md5=runtime.md5,
        file_id=runtime.file.file_id,
        phase="text",
        prefix=cache_prefix,
        cache_key=text_cache_key(runtime.md5, runtime.settings) if runtime.md5 else "",
    )
    text_cached = load_report_source_cache(
        text_binding,
        ctx=text_ctx,
        dependencies=dependencies,
        adapt_payload=_adapt_cached_text,
    )
    text_resp = text_cached.value
    text_cache_hit = text_cached.cache_hit
    if text_resp is None:
        text_resp = dependencies.extract_pdf_text(
            PdfTextExtractRequest(
                schema_version="1.0",
                path=analysis_pdf_path,
                max_pages=runtime.settings.pdf_text_max_pages,
                max_chars=runtime.settings.pdf_text_max_chars,
                pdf_context=pdf_context_for_tasks,
            ),
            text_ctx,
        )
        write_report_source_cache(
            text_binding,
            payload={
                "schema_version": "1.0",
                "key": text_binding.cache_key,
                "text": text_resp.text,
                "pages_extracted": text_resp.pages_extracted,
                "char_count": text_resp.char_count,
                "text_density": text_resp.text_density,
            },
            ctx=text_ctx,
            dependencies=dependencies,
        )
    text_status = _build_text_status(runtime, text_resp)
    logger.info(
        log_event(
            text_ctx,
            role="generator",
            event="text_density_evaluated",
            module=logger.name,
            fields={
                "density": text_status["text_density"],
                "threshold": text_status["density_threshold"],
                "pages": text_status["pages_sampled"],
                "char_count": text_status["char_count"],
                "not_available": text_status["not_available"],
                "cache_hit": text_cache_hit,
            },
        )
    )
    return text_resp, text_status


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
