from __future__ import annotations

import hashlib
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, TypedDict, cast

from src.contracts.pdf_contents import (
    PdfContentsDetectionRequest,
    PdfContentsDetectionResponse,
)
from src.contracts.pdf_context import PdfContextBuildRequest
from src.contracts.pdf_text import (
    PdfTextExtractRequest,
    PdfTextExtractResponse,
    PdfTextSampleRequest,
)
from src.contracts.pdf_utils import PdfInfoRequest, PdfInfoResponse
from src.contracts.report_assets import PreviewRequest
from src.contracts.report_generation import ReportRuntimeState, ReportSourceState
from src.contracts.report_models import ReportPayload
from src.generators.pdf_text_ocr_generator import recover_pdf_text_with_ocr
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import (
    base_payload,
    contents_cache_key,
    logger,
    pdf_info_cache_key,
    resolve_publisher,
    text_cache_key,
)
from src.generators.report_source_cache import (
    bind_report_source_cache,
    load_report_source_cache,
    write_report_source_cache,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event


class TextStatus(TypedDict):
    schema_version: str
    text_density: float
    density_threshold: float
    pages_sampled: int
    char_count: int
    not_available: bool
    reason: str


def _cached_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return None


def _cached_float(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _cached_bool(value: object) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _cached_str(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _cached_metadata(value: object) -> dict[str, str] | None:
    if not isinstance(value, dict):
        return None
    metadata: dict[str, str] = {}
    for key, item in value.items():
        if not isinstance(key, str) or not isinstance(item, str):
            return None
        metadata[key] = item
    return metadata


def _adapt_cached_pdf_info(
    payload: dict[str, object],
    *,
    pdf_path: str,
) -> PdfInfoResponse | None:
    page_count = _cached_int(payload.get("page_count"))
    metadata = _cached_metadata(payload.get("metadata"))
    if page_count is None or metadata is None:
        return None
    return PdfInfoResponse(
        schema_version="1.0",
        path=pdf_path,
        page_count=page_count,
        metadata=metadata,
    )


def _adapt_cached_contents(
    payload: dict[str, object],
    *,
    analysis_pdf_path: str,
) -> PdfContentsDetectionResponse | None:
    has_contents = _cached_bool(payload.get("has_contents"))
    page_index = _cached_int(payload.get("page_index"))
    page_number = _cached_int(payload.get("page_number"))
    heading = _cached_str(payload.get("heading"))
    confidence = _cached_float(payload.get("confidence"))
    if (
        has_contents is None
        or page_index is None
        or page_number is None
        or heading is None
        or confidence is None
    ):
        return None
    return PdfContentsDetectionResponse(
        schema_version="1.0",
        path=analysis_pdf_path,
        has_contents=has_contents,
        page_index=page_index,
        page_number=page_number,
        heading=heading,
        confidence=confidence,
    )


def _adapt_cached_text(payload: dict[str, object]) -> PdfTextExtractResponse | None:
    text = _cached_str(payload.get("text"))
    pages_extracted = _cached_int(payload.get("pages_extracted"))
    char_count = _cached_int(payload.get("char_count"))
    text_density = _cached_float(payload.get("text_density"))
    if (
        text is None
        or pages_extracted is None
        or char_count is None
        or text_density is None
    ):
        return None
    return PdfTextExtractResponse(
        schema_version="1.0",
        text=text,
        pages_extracted=pages_extracted,
        char_count=char_count,
        text_density=text_density,
    )


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
    dependencies: ReportGeneratorDependencies,
) -> object | None:
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
    pdf_context_for_tasks: object | None,
    dependencies: ReportGeneratorDependencies,
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
    detection_pdf_context: object | None,
    preview_pdf_context: object | None,
    cache_prefix: str,
    dependencies: ReportGeneratorDependencies,
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


def _load_text(
    runtime: ReportRuntimeState,
    *,
    analysis_pdf_path: str,
    pdf_context_for_tasks: object | None,
    cache_prefix: str,
    dependencies: ReportGeneratorDependencies,
) -> tuple[PdfTextExtractResponse, TextStatus]:
    text_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:text")
    text_binding = bind_report_source_cache(
        settings=runtime.settings,
        md5=runtime.md5,
        file_id=runtime.file.file_id,
        phase="text",
        prefix=cache_prefix,
        cache_key=text_cache_key(runtime.md5, runtime.settings)
        if runtime.md5
        else "",
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
    }
    if (
        text_status["density_threshold"]
        and text_status["text_density"] < text_status["density_threshold"]
    ):
        text_status["not_available"] = True
        text_status["reason"] = "text_density_below_threshold"
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


def _raise_text_unextractable(
    runtime: ReportRuntimeState,
    *,
    reason: str,
    pages: list[int],
    extra_fields: dict[str, object],
) -> None:
    logger.info(
        log_event(
            child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:text_sample"),
            role="generator",
            event="text_extractability_failed",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "reason": reason,
                "sample_pages": pages,
                **extra_fields,
            },
        )
    )
    raise AppError(
        code="pdf_text_unextractable",
        message="pdf_text_unextractable",
        retryable=False,
        context={
            "text_validation_status": "fail",
            "text_validation_reason": reason,
            "text_validation_pages": pages,
        },
    )


def _validate_extractable_text(
    runtime: ReportRuntimeState,
    *,
    pdf_path: str,
    page_count: int,
    pdf_context: object | None,
    dependencies: ReportGeneratorDependencies,
) -> tuple[str, str, list[int]]:
    sample_ctx = child_context(
        runtime.ctx, task_id=f"{runtime.ctx.task_id}:text_sample"
    )
    sample_indices = _select_sample_pages(
        file_id=runtime.file.file_id,
        md5=runtime.md5,
        page_count=page_count,
        sample_count=runtime.settings.pdf_text_sample_pages,
    )
    text_validation_pages = [idx + 1 for idx in sample_indices]
    if not sample_indices:
        _raise_text_unextractable(
            runtime,
            reason="no_pages_to_sample",
            pages=text_validation_pages,
            extra_fields={"page_count": page_count},
        )
    sample_resp = dependencies.sample_pdf_text(
        PdfTextSampleRequest(
            schema_version="1.0",
            path=pdf_path,
            page_indices=sample_indices,
            pdf_context=pdf_context,
        ),
        sample_ctx,
    )
    sample_chars = {
        sample.page_number: sample.char_count for sample in sample_resp.samples
    }
    logger.info(
        log_event(
            sample_ctx,
            role="generator",
            event="text_extractability_checked",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "sample_pages": text_validation_pages,
                "any_text": sample_resp.any_text,
                "char_counts": sample_chars,
                "pdf_path": pdf_path,
            },
        )
    )
    if not sample_resp.any_text:
        _raise_text_unextractable(
            runtime,
            reason="no_text_in_sampled_pages",
            pages=text_validation_pages,
            extra_fields={"char_counts": sample_chars},
        )
    return "pass", "", text_validation_pages


def prepare_report_source(
    runtime: ReportRuntimeState,
    dependencies: ReportGeneratorDependencies,
) -> ReportSourceState:
    pdf_context = _build_pdf_context(runtime, dependencies)
    _, parallel_within_file = _report_worker_config(runtime)
    pdf_context_for_tasks = None if parallel_within_file else pdf_context
    info_resp = _load_pdf_info(runtime, pdf_context_for_tasks, dependencies)
    analysis_pdf_path = runtime.local_pdf_path
    ocr_fallback_used = False
    ocr_pdf_path = ""

    try:
        text_validation_status, text_validation_reason, text_validation_pages = (
            _validate_extractable_text(
                runtime,
                pdf_path=runtime.local_pdf_path,
                page_count=info_resp.page_count,
                pdf_context=pdf_context,
                dependencies=dependencies,
            )
        )
    except AppError as exc:
        if (
            exc.code != "pdf_text_unextractable"
            or not runtime.settings.pdf_text_ocr_enabled
        ):
            raise
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="ocr_fallback_triggered",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "reason": str(
                        exc.context.get("text_validation_reason") or exc.code
                    ),
                    "sample_pages": list(
                        exc.context.get("text_validation_pages") or []
                    ),
                },
            )
        )
        ocr_result = recover_pdf_text_with_ocr(
            runtime,
            page_count=info_resp.page_count,
            dependencies=dependencies,
        )
        analysis_pdf_path = ocr_result.render_response.output_path
        ocr_fallback_used = True
        ocr_pdf_path = analysis_pdf_path
        try:
            text_validation_status, text_validation_reason, text_validation_pages = (
                _validate_extractable_text(
                    runtime,
                    pdf_path=analysis_pdf_path,
                    page_count=info_resp.page_count,
                    pdf_context=None,
                    dependencies=dependencies,
                )
            )
        except AppError as ocr_exc:
            if ocr_exc.code != "pdf_text_unextractable":
                raise
            raise AppError(
                code="pdf_text_ocr_failed",
                message="OCR fallback produced no extractable text",
                retryable=False,
                context={
                    "text_validation_status": "fail",
                    "text_validation_reason": "ocr_output_unextractable",
                    "text_validation_pages": list(
                        ocr_exc.context.get("text_validation_pages") or []
                    ),
                    "ocr_pdf_path": analysis_pdf_path,
                },
            ) from ocr_exc

    if parallel_within_file:
        with ThreadPoolExecutor(max_workers=runtime.report_worker_limit) as executor:
            contents_future = executor.submit(
                _load_contents,
                runtime,
                analysis_pdf_path=analysis_pdf_path,
                preview_pdf_path=runtime.local_pdf_path,
                detection_pdf_context=None
                if analysis_pdf_path != runtime.local_pdf_path
                else pdf_context_for_tasks,
                preview_pdf_context=pdf_context_for_tasks,
                cache_prefix="ocr_contents" if ocr_fallback_used else "contents",
                dependencies=dependencies,
            )
            text_future = executor.submit(
                _load_text,
                runtime,
                analysis_pdf_path=analysis_pdf_path,
                pdf_context_for_tasks=None
                if analysis_pdf_path != runtime.local_pdf_path
                else pdf_context_for_tasks,
                cache_prefix="ocr_text" if ocr_fallback_used else "text",
                dependencies=dependencies,
            )
            contents_page_number, contents_heading, contents_image = (
                contents_future.result()
            )
            text_resp, text_status = text_future.result()
    else:
        contents_page_number, contents_heading, contents_image = _load_contents(
            runtime,
            analysis_pdf_path=analysis_pdf_path,
            preview_pdf_path=runtime.local_pdf_path,
            detection_pdf_context=pdf_context
            if analysis_pdf_path == runtime.local_pdf_path
            else None,
            preview_pdf_context=pdf_context,
            cache_prefix="ocr_contents" if ocr_fallback_used else "contents",
            dependencies=dependencies,
        )
        text_resp, text_status = _load_text(
            runtime,
            analysis_pdf_path=analysis_pdf_path,
            pdf_context_for_tasks=pdf_context
            if analysis_pdf_path == runtime.local_pdf_path
            else None,
            cache_prefix="ocr_text" if ocr_fallback_used else "text",
            dependencies=dependencies,
        )
    payload: ReportPayload = base_payload(
        runtime.report_title,
        contents_page_number,
        contents_heading,
        contents_image,
    )
    payload._text_density = float(text_status["text_density"])
    payload._text_pages_sampled = int(text_status["pages_sampled"])
    payload._text_char_count = int(text_status["char_count"])
    payload._text_not_available = bool(text_status["not_available"])
    payload.publisher = resolve_publisher(payload, info_resp.metadata)
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="publisher_resolved",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "publisher": payload.publisher,
            },
        )
    )
    return ReportSourceState(
        schema_version="1.0",
        runtime=runtime,
        pdf_context=pdf_context,
        pdf_context_for_tasks=pdf_context_for_tasks,
        info_response=info_resp,
        contents_page_number=contents_page_number,
        contents_heading=contents_heading,
        contents_image=contents_image,
        text_response=text_resp,
        text_status=cast(dict[str, object], dict(text_status)),
        text_validation_status=text_validation_status,
        text_validation_reason=text_validation_reason,
        text_validation_pages=text_validation_pages,
        payload=payload,
        analysis_pdf_path=analysis_pdf_path,
        ocr_fallback_used=ocr_fallback_used,
        ocr_pdf_path=ocr_pdf_path,
    )
