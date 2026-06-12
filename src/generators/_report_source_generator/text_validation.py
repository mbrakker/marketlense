from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from src.contracts.pdf_context import PdfContext
from src.contracts.pdf_ocr import PdfOcrFallbackResponse
from src.contracts.pdf_text import (
    PdfTextExtractResponse,
    PdfTextSampleRequest,
)
from src.contracts.report_generation import ReportRuntimeState
from src.generators.report_generation_dependencies import ReportSourceDependencies
from src.generators.report_generation_shared import logger
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

from .shared import *  # noqa: F401,F403
from .shared import TextStatus, _NativeTextValidationResult
from .source_loading import _build_text_status, _load_text, _select_sample_pages


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


def _density_confidence_score(
    *, text_density: float, density_threshold: float
) -> float:
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


def _resolve_document_sample_confidence(
    samples: list[object], declared_score: float
) -> float:
    if declared_score > 0.0:
        return round(max(0.0, min(declared_score, 1.0)), 3)
    if not samples:
        return 0.0
    return round(
        sum(_resolve_sample_confidence(sample) for sample in samples)
        / float(len(samples)),
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
                    _resolve_sample_confidence(sample) for sample in sample_resp.samples
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
    elif bool(text_status["not_available"]) and native_confidence_score < max(
        native_confidence_threshold, 0.7
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


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
