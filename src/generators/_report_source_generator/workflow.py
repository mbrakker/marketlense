from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from .shared import *  # noqa: F401,F403
from .source_loading import (
    _build_pdf_context,
    _load_contents,
    _load_pdf_info,
    _load_text,
    _report_worker_config,
)
from .text_validation import _load_validated_ocr_text, _validate_extractable_text


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
                    "reason": str(
                        exc.context.get("text_validation_reason") or exc.code
                    ),
                    "sample_pages": list(
                        exc.context.get("text_validation_pages") or []
                    ),
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
            text_status["native_sample_confidence_score"] = float(
                exc.context.get("sample_confidence_score") or 0.0
            )
            text_status["native_density_confidence_score"] = float(
                exc.context.get("density_confidence_score") or 0.0
            )
            text_status["native_confidence_score"] = float(
                exc.context.get("native_confidence_score") or 0.0
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
            text_status["low_confidence_pages"] = native_validation.low_confidence_pages
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
                refreshed_text_status["native_page_confidence_threshold"] = text_status[
                    "native_page_confidence_threshold"
                ]
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


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
