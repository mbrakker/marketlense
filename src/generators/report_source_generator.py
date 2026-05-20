from __future__ import annotations

import hashlib
import random
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Optional, TypedDict, cast

from src.contracts.pdf_contents import (
    PdfContentsDetectionRequest,
    PdfContentsDetectionResponse,
)
from src.contracts.pdf_context import PdfContext, PdfContextBuildRequest
from src.contracts.pdf_ocr import PdfOcrFallbackResponse
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
from src.generators.report_generation_dependencies import ReportSourceDependencies
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
    native_sample_confidence_score: float
    native_density_confidence_score: float
    native_confidence_score: float
    native_confidence_threshold: float
    native_page_confidence_threshold: float
    low_confidence_pages: list[int]
    ocr_recommended: bool
    ocr_recommendation_reason: str
    ocr_policy: str
    native_text_density: float
    native_text_not_available: bool


@dataclass(frozen=True)
class _NativeTextValidationResult:
    schema_version: str
    status: str
    reason: str
    pages: list[int]
    sample_confidence_score: float
    density_confidence_score: float
    native_confidence_score: float
    low_confidence_pages: list[int]
    ocr_recommended: bool


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


def _text_response_from_ocr_pages(
    runtime: ReportRuntimeState,
    ocr_result: PdfOcrFallbackResponse,
) -> PdfTextExtractResponse:
    pages = sorted(
        ocr_result.ocr_response.pages,
        key=lambda page: page.page_number,
    )
    chunks = []
    for page in pages:
        text = str(page.text or "").strip()
        if text:
            chunks.append(f"Source page {page.page_number}\n{text}")
    raw_text = "\n\n".join(chunks)
    text_out = raw_text[: max(runtime.settings.pdf_text_max_chars, 0)]
    density = (len(raw_text) / float(len(pages))) if pages else 0.0
    return PdfTextExtractResponse(
        schema_version="1.0",
        text=text_out,
        pages_extracted=len(pages),
        char_count=len(text_out),
        text_density=density,
    )


def _select_ocr_text_response(
    runtime: ReportRuntimeState,
    *,
    ocr_result: PdfOcrFallbackResponse,
    rendered_text_resp: PdfTextExtractResponse,
    rendered_text_status: TextStatus,
) -> tuple[PdfTextExtractResponse, TextStatus]:
    structured_text_resp = _text_response_from_ocr_pages(runtime, ocr_result)
    if structured_text_resp.char_count > rendered_text_resp.char_count:
        selected_resp = structured_text_resp
        selected_status = _build_text_status(runtime, structured_text_resp)
        source = "structured_ocr_pages"
    else:
        selected_resp = rendered_text_resp
        selected_status = rendered_text_status
        source = "rendered_ocr_pdf"
    logger.info(
        log_event(
            runtime.ctx,
            role="generator",
            event="ocr_text_source_selected",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "source": source,
                "structured_char_count": structured_text_resp.char_count,
                "structured_text_density": structured_text_resp.text_density,
                "rendered_char_count": rendered_text_resp.char_count,
                "rendered_text_density": rendered_text_resp.text_density,
            },
        )
    )
    return selected_resp, selected_status


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
            **extra_fields,
        },
    )


def _validate_ocr_text_pages(
    runtime: ReportRuntimeState,
    *,
    ocr_result: PdfOcrFallbackResponse,
    text_status: TextStatus,
) -> _NativeTextValidationResult:
    pages = sorted(
        ocr_result.ocr_response.pages,
        key=lambda page: page.page_number,
    )
    if not pages:
        _raise_text_unextractable(
            runtime,
            reason="no_ocr_pages",
            pages=[],
            extra_fields={"ocr_pdf_path": ocr_result.render_response.output_path},
        )
    text_pages = [page for page in pages if str(page.text or "").strip()]
    text_page_numbers = [page.page_number for page in text_pages]
    total_chars = sum(len(str(page.text or "").strip()) for page in pages)
    blank_page_numbers = [
        page.page_number for page in pages if not str(page.text or "").strip()
    ]
    sample_count = min(runtime.settings.pdf_text_sample_pages, len(pages))
    validation_pages = text_page_numbers[:sample_count] or [
        page.page_number for page in pages[:sample_count]
    ]
    logger.info(
        log_event(
            child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:text_sample"),
            role="generator",
            event="ocr_text_extractability_checked",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "validation_pages": validation_pages,
                "text_page_count": len(text_pages),
                "blank_page_count": len(blank_page_numbers),
                "total_page_count": len(pages),
                "char_count": total_chars,
                "text_density": text_status["text_density"],
                "density_threshold": text_status["density_threshold"],
                "ocr_pdf_path": ocr_result.render_response.output_path,
            },
        )
    )
    if not text_pages:
        _raise_text_unextractable(
            runtime,
            reason="no_text_in_ocr_pages",
            pages=validation_pages,
            extra_fields={
                "ocr_pdf_path": ocr_result.render_response.output_path,
                "char_count": total_chars,
            },
        )
    sample_confidence_score = (
        round(min(len(text_pages) / float(sample_count), 1.0), 3)
        if sample_count
        else 0.0
    )
    density_confidence_score = _density_confidence_score(
        text_density=float(text_status["text_density"]),
        density_threshold=float(text_status["density_threshold"]),
    )
    native_confidence_score = round(
        (sample_confidence_score * 0.75) + (density_confidence_score * 0.25),
        3,
    )
    reason = ""
    if bool(text_status["not_available"]):
        reason = "ocr_text_density_below_threshold"
    return _NativeTextValidationResult(
        schema_version="1.0",
        status="fail" if reason else "pass",
        reason=reason,
        pages=validation_pages,
        sample_confidence_score=sample_confidence_score,
        density_confidence_score=density_confidence_score,
        native_confidence_score=native_confidence_score,
        low_confidence_pages=blank_page_numbers,
        ocr_recommended=False,
    )


def _load_validated_ocr_text(
    runtime: ReportRuntimeState,
    *,
    analysis_pdf_path: str,
    ocr_result: PdfOcrFallbackResponse,
    dependencies: ReportSourceDependencies,
) -> tuple[PdfTextExtractResponse, TextStatus, _NativeTextValidationResult]:
    rendered_text_resp, rendered_text_status = _load_text(
        runtime,
        analysis_pdf_path=analysis_pdf_path,
        pdf_context_for_tasks=None,
        cache_prefix="ocr_text",
        dependencies=dependencies,
    )
    text_resp, text_status = _select_ocr_text_response(
        runtime,
        ocr_result=ocr_result,
        rendered_text_resp=rendered_text_resp,
        rendered_text_status=rendered_text_status,
    )
    ocr_validation = _validate_ocr_text_pages(
        runtime,
        ocr_result=ocr_result,
        text_status=text_status,
    )
    return text_resp, text_status, ocr_validation


def _density_confidence_score(*, text_density: float, density_threshold: float) -> float:
    if density_threshold <= 0:
        return 1.0
    return round(max(0.0, min(text_density / density_threshold, 1.0)), 3)


def _resolve_sample_confidence(sample: object) -> float:
    confidence_score = float(getattr(sample, "confidence_score", 0.0) or 0.0)
    word_count = int(getattr(sample, "word_count", 0) or 0)
    char_count = int(getattr(sample, "char_count", 0) or 0)
    has_text = bool(getattr(sample, "has_text", False))
    if confidence_score > 0.0 or word_count > 0:
        return round(max(0.0, min(confidence_score, 1.0)), 3)
    if not has_text or char_count <= 0:
        return 0.0
    return round(min(char_count / 20.0, 1.0), 3)


def _resolve_document_sample_confidence(samples: list[object], declared_score: float) -> float:
    if declared_score > 0.0:
        return round(max(0.0, min(declared_score, 1.0)), 3)
    if not samples:
        return 0.0
    return round(
        sum(_resolve_sample_confidence(sample) for sample in samples) / float(len(samples)),
        3,
    )


def _validate_extractable_text(
    runtime: ReportRuntimeState,
    *,
    pdf_path: str,
    page_count: int,
    pdf_context: PdfContext | None,
    text_status: TextStatus,
    dependencies: ReportSourceDependencies,
) -> _NativeTextValidationResult:
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
                "page_confidence_scores": [
                    _resolve_sample_confidence(sample)
                    for sample in sample_resp.samples
                ],
                "document_confidence_score": round(
                    _resolve_document_sample_confidence(
                        sample_resp.samples,
                        float(sample_resp.document_confidence_score or 0.0),
                    ),
                    3,
                ),
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
    sample_confidence_score = round(
        _resolve_document_sample_confidence(
            sample_resp.samples,
            float(sample_resp.document_confidence_score or 0.0),
        ),
        3,
    )
    density_confidence_score = _density_confidence_score(
        text_density=float(text_status["text_density"]),
        density_threshold=float(text_status["density_threshold"]),
    )
    native_confidence_score = round(
        (sample_confidence_score * 0.75) + (density_confidence_score * 0.25),
        3,
    )
    native_confidence_threshold = float(
        getattr(runtime.settings, "pdf_text_native_confidence_threshold", 0.55)
    )
    native_page_confidence_threshold = float(
        getattr(runtime.settings, "pdf_text_native_page_confidence_threshold", 0.35)
    )
    low_confidence_pages = [
        sample.page_number
        for sample in sample_resp.samples
        if _resolve_sample_confidence(sample) < native_page_confidence_threshold
    ]
    ocr_recommended = False
    recommendation_reason = ""
    if low_confidence_pages and len(low_confidence_pages) == len(sample_resp.samples):
        ocr_recommended = True
        recommendation_reason = "native_page_confidence_below_threshold"
    elif (
        bool(text_status["not_available"])
        and native_confidence_score < max(native_confidence_threshold, 0.7)
    ):
        ocr_recommended = True
        recommendation_reason = "text_density_below_threshold"
    elif native_confidence_score < native_confidence_threshold:
        ocr_recommended = True
        recommendation_reason = "native_text_confidence_below_threshold"
    logger.info(
        log_event(
            sample_ctx,
            role="generator",
            event="native_text_confidence_evaluated",
            module=logger.name,
            fields={
                "file_id": runtime.file.file_id,
                "sample_pages": text_validation_pages,
                "sample_confidence_score": sample_confidence_score,
                "density_confidence_score": density_confidence_score,
                "native_confidence_score": native_confidence_score,
                "native_confidence_threshold": native_confidence_threshold,
                "native_page_confidence_threshold": native_page_confidence_threshold,
                "text_density": text_status["text_density"],
                "density_threshold": text_status["density_threshold"],
                "low_confidence_pages": low_confidence_pages,
                "ocr_recommended": ocr_recommended,
                "ocr_recommendation_reason": recommendation_reason,
                "pdf_path": pdf_path,
            },
        )
    )
    return _NativeTextValidationResult(
        schema_version="1.0",
        status="fail" if ocr_recommended else "pass",
        reason=recommendation_reason if ocr_recommended else "",
        pages=text_validation_pages,
        sample_confidence_score=sample_confidence_score,
        density_confidence_score=density_confidence_score,
        native_confidence_score=native_confidence_score,
        low_confidence_pages=low_confidence_pages,
        ocr_recommended=ocr_recommended,
    )


def prepare_report_source(
    runtime: ReportRuntimeState,
    dependencies: ReportSourceDependencies,
) -> ReportSourceState:
    pdf_context = _build_pdf_context(runtime, dependencies)
    _, parallel_within_file = _report_worker_config(runtime)
    pdf_context_for_tasks = None if parallel_within_file else pdf_context
    info_resp = _load_pdf_info(runtime, pdf_context_for_tasks, dependencies)
    analysis_pdf_path = runtime.local_pdf_path
    ocr_fallback_used = False
    ocr_pdf_path = ""
    ocr_policy = str(
        getattr(runtime.settings, "pdf_text_ocr_policy", "native_first_selective")
        or "native_first_selective"
    )
    native_text_resp, native_text_status = _load_text(
        runtime,
        analysis_pdf_path=runtime.local_pdf_path,
        pdf_context_for_tasks=pdf_context_for_tasks,
        cache_prefix="text",
        dependencies=dependencies,
    )
    native_text_status["ocr_policy"] = ocr_policy
    text_resp = native_text_resp
    text_status = native_text_status
    should_force_ocr = runtime.settings.pdf_text_ocr_enabled and ocr_policy == "always"
    text_validation_status = "pass"
    text_validation_reason = ""
    text_validation_pages: list[int] = []
    native_validation: _NativeTextValidationResult | None = None
    try:
        native_validation = _validate_extractable_text(
            runtime,
            pdf_path=runtime.local_pdf_path,
            page_count=info_resp.page_count,
            pdf_context=pdf_context,
            text_status=native_text_status,
            dependencies=dependencies,
        )
        native_text_status["native_sample_confidence_score"] = (
            native_validation.sample_confidence_score
        )
        native_text_status["native_density_confidence_score"] = (
            native_validation.density_confidence_score
        )
        native_text_status["native_confidence_score"] = (
            native_validation.native_confidence_score
        )
        native_text_status["low_confidence_pages"] = (
            native_validation.low_confidence_pages
        )
        text_validation_status = native_validation.status
        text_validation_reason = native_validation.reason
        text_validation_pages = native_validation.pages
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
                    "reason": str(exc.context.get("text_validation_reason") or exc.code),
                    "sample_pages": list(exc.context.get("text_validation_pages") or []),
                    "ocr_policy": ocr_policy,
                    "native_confidence_score": float(
                        exc.context.get("native_confidence_score") or 0.0
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
            text_resp, text_status, ocr_validation = _load_validated_ocr_text(
                runtime,
                analysis_pdf_path=analysis_pdf_path,
                ocr_result=ocr_result,
                dependencies=dependencies,
            )
            text_validation_status = ocr_validation.status
            text_validation_reason = ocr_validation.reason
            text_validation_pages = ocr_validation.pages
            text_status["native_sample_confidence_score"] = (
                float(exc.context.get("sample_confidence_score") or 0.0)
            )
            text_status["native_density_confidence_score"] = (
                float(exc.context.get("density_confidence_score") or 0.0)
            )
            text_status["native_confidence_score"] = (
                float(exc.context.get("native_confidence_score") or 0.0)
            )
            text_status["low_confidence_pages"] = list(
                exc.context.get("low_confidence_pages") or []
            )
            text_status["ocr_recommended"] = True
            text_status["ocr_recommendation_reason"] = str(
                exc.context.get("text_validation_reason") or "policy_forced_ocr"
            )
            text_status["ocr_policy"] = ocr_policy
            text_status["native_text_density"] = native_text_status["text_density"]
            text_status["native_text_not_available"] = native_text_status[
                "not_available"
            ]
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
    if (
        native_validation is not None
        and native_validation.ocr_recommended
        and runtime.settings.pdf_text_ocr_enabled
        and not ocr_fallback_used
    ):
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="ocr_fallback_triggered",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "reason": native_validation.reason,
                    "sample_pages": list(native_validation.pages),
                    "ocr_policy": ocr_policy,
                    "native_confidence_score": native_validation.native_confidence_score,
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
            text_resp, text_status, ocr_validation = _load_validated_ocr_text(
                runtime,
                analysis_pdf_path=analysis_pdf_path,
                ocr_result=ocr_result,
                dependencies=dependencies,
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
        text_validation_status = ocr_validation.status
        text_validation_reason = ocr_validation.reason
        text_validation_pages = ocr_validation.pages
        text_status["native_sample_confidence_score"] = (
            native_validation.sample_confidence_score
        )
        text_status["native_density_confidence_score"] = (
            native_validation.density_confidence_score
        )
        text_status["native_confidence_score"] = (
            native_validation.native_confidence_score
        )
        text_status["low_confidence_pages"] = native_validation.low_confidence_pages
        text_status["ocr_recommended"] = True
        text_status["ocr_recommendation_reason"] = native_validation.reason
        text_status["ocr_policy"] = ocr_policy
        text_status["native_text_density"] = native_text_status["text_density"]
        text_status["native_text_not_available"] = native_text_status["not_available"]
    elif (
        native_validation is not None
        and native_validation.ocr_recommended
        and not ocr_fallback_used
    ):
        text_status["ocr_recommended"] = True
        text_status["ocr_recommendation_reason"] = native_validation.reason
    if should_force_ocr and not ocr_fallback_used:
        logger.info(
            log_event(
                runtime.ctx,
                role="generator",
                event="ocr_fallback_triggered",
                module=logger.name,
                fields={
                    "file_id": runtime.file.file_id,
                    "reason": "policy_forced_ocr",
                    "sample_pages": list(text_validation_pages),
                    "ocr_policy": ocr_policy,
                    "native_confidence_score": float(
                        text_status["native_confidence_score"]
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
            text_resp, text_status, ocr_validation = _load_validated_ocr_text(
                runtime,
                analysis_pdf_path=analysis_pdf_path,
                ocr_result=ocr_result,
                dependencies=dependencies,
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
        text_validation_status = ocr_validation.status
        text_validation_reason = ocr_validation.reason
        text_validation_pages = ocr_validation.pages
        text_status["ocr_recommended"] = True
        text_status["ocr_recommendation_reason"] = "policy_forced_ocr"
        text_status["ocr_policy"] = ocr_policy
        if native_validation is not None:
            text_status["native_sample_confidence_score"] = (
                native_validation.sample_confidence_score
            )
            text_status["native_density_confidence_score"] = (
                native_validation.density_confidence_score
            )
            text_status["native_confidence_score"] = (
                native_validation.native_confidence_score
            )
            text_status["low_confidence_pages"] = (
                native_validation.low_confidence_pages
            )
        text_status["native_text_density"] = native_text_status["text_density"]
        text_status["native_text_not_available"] = native_text_status["not_available"]

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
            _, refreshed_text_status = text_future.result()
            if not ocr_fallback_used:
                refreshed_text_status["native_sample_confidence_score"] = text_status[
                    "native_sample_confidence_score"
                ]
                refreshed_text_status["native_density_confidence_score"] = text_status[
                    "native_density_confidence_score"
                ]
                refreshed_text_status["native_confidence_score"] = text_status[
                    "native_confidence_score"
                ]
                refreshed_text_status["native_confidence_threshold"] = text_status[
                    "native_confidence_threshold"
                ]
                refreshed_text_status[
                    "native_page_confidence_threshold"
                ] = text_status["native_page_confidence_threshold"]
                refreshed_text_status["low_confidence_pages"] = text_status[
                    "low_confidence_pages"
                ]
                refreshed_text_status["ocr_recommended"] = text_status[
                    "ocr_recommended"
                ]
                refreshed_text_status["ocr_recommendation_reason"] = text_status[
                    "ocr_recommendation_reason"
                ]
                refreshed_text_status["ocr_policy"] = text_status["ocr_policy"]
                refreshed_text_status["native_text_density"] = text_status[
                    "native_text_density"
                ]
                refreshed_text_status["native_text_not_available"] = text_status[
                    "native_text_not_available"
                ]
                text_status = refreshed_text_status
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
