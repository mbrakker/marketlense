from __future__ import annotations

import hashlib
import random
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

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
from src.generators.report_generation_dependencies import ReportGeneratorDependencies
from src.generators.report_generation_shared import (
    base_payload,
    cache_dir,
    cache_path,
    contents_cache_key,
    logger,
    pdf_info_cache_key,
    read_cache_json,
    resolve_publisher,
    text_cache_key,
    write_cache_json,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event


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
        ctx_pdf = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:pdf_context")
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
    info_resp = None
    info_cache_hit = False
    cache_root = cache_dir(runtime.settings, runtime.md5) if runtime.md5 else None
    info_cache_key = ""
    info_cache_path = None
    if runtime.md5 and cache_root is not None:
        info_cache_key = pdf_info_cache_key(runtime.md5)
        info_cache_path = cache_path(cache_root, "pdf_info", info_cache_key)
        cached = read_cache_json(info_cache_path, info_ctx, dependencies)
        if cached and cached.get("key") == info_cache_key:
            info_resp = PdfInfoResponse(
                schema_version="1.0",
                path=runtime.local_pdf_path,
                page_count=int(cached.get("page_count") or 0),
                metadata=(
                    cached.get("metadata")
                    if isinstance(cached.get("metadata"), dict)
                    else {}
                ),
            )
            info_cache_hit = True
            logger.info(
                log_event(
                    info_ctx,
                    role="generator",
                    event="pdf_info_cache_hit",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "cache_path": str(info_cache_path),
                    },
                )
            )
        else:
            logger.info(
                log_event(
                    info_ctx,
                    role="generator",
                    event="pdf_info_cache_miss",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "cache_path": str(info_cache_path) if info_cache_path else "",
                    },
                )
            )
    if info_resp is None:
        info_resp = dependencies.extract_pdf_info(
            PdfInfoRequest(
                schema_version="1.0",
                path=runtime.local_pdf_path,
                pdf_context=pdf_context_for_tasks,
            ),
            info_ctx,
        )
        if runtime.md5 and cache_root is not None and info_cache_path is not None:
            write_cache_json(
                info_cache_path,
                {
                    "schema_version": "1.0",
                    "key": info_cache_key,
                    "page_count": info_resp.page_count,
                    "metadata": info_resp.metadata,
                },
                info_ctx,
                dependencies,
            )
            logger.info(
                log_event(
                    info_ctx,
                    role="generator",
                    event="pdf_info_cache_written",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "cache_path": str(info_cache_path),
                    },
                )
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
    pdf_context_for_tasks: object | None,
    dependencies: ReportGeneratorDependencies,
) -> tuple[int, str, str]:
    contents_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:contents")
    local_contents_page = 0
    local_contents_heading = ""
    local_contents_image = ""
    try:
        contents_resp = None
        contents_cache_hit = False
        cache_root = cache_dir(runtime.settings, runtime.md5) if runtime.md5 else None
        contents_key = ""
        contents_cache_path = None
        if runtime.md5 and cache_root is not None:
            contents_key = contents_cache_key(runtime.md5, runtime.settings)
            contents_cache_path = cache_path(cache_root, "contents", contents_key)
            cached = read_cache_json(contents_cache_path, contents_ctx, dependencies)
            if cached and cached.get("key") == contents_key:
                contents_resp = PdfContentsDetectionResponse(
                    schema_version="1.0",
                    path=runtime.local_pdf_path,
                    has_contents=bool(cached.get("has_contents")),
                    page_index=int(cached.get("page_index") or -1),
                    page_number=int(cached.get("page_number") or 0),
                    heading=str(cached.get("heading") or ""),
                    confidence=float(cached.get("confidence") or 0.0),
                )
                contents_cache_hit = True
                logger.info(
                    log_event(
                        contents_ctx,
                        role="generator",
                        event="contents_cache_hit",
                        module=logger.name,
                        fields={
                            "file_id": runtime.file.file_id,
                            "cache_path": str(contents_cache_path),
                        },
                    )
                )
            else:
                logger.info(
                    log_event(
                        contents_ctx,
                        role="generator",
                        event="contents_cache_miss",
                        module=logger.name,
                        fields={
                            "file_id": runtime.file.file_id,
                            "cache_path": str(contents_cache_path)
                            if contents_cache_path
                            else "",
                        },
                    )
                )
        if contents_resp is None:
            contents_resp = dependencies.detect_contents_page(
                PdfContentsDetectionRequest(
                    schema_version="1.0",
                    path=runtime.local_pdf_path,
                    max_pages=runtime.settings.contents_max_pages,
                    min_headings=runtime.settings.contents_min_headings,
                    keywords=runtime.settings.contents_keywords,
                    pdf_context=pdf_context_for_tasks,
                ),
                contents_ctx,
            )
            if runtime.md5 and cache_root is not None and contents_cache_path is not None:
                write_cache_json(
                    contents_cache_path,
                    {
                        "schema_version": "1.0",
                        "key": contents_key,
                        "has_contents": contents_resp.has_contents,
                        "page_index": contents_resp.page_index,
                        "page_number": contents_resp.page_number,
                        "heading": contents_resp.heading,
                        "confidence": contents_resp.confidence,
                    },
                    contents_ctx,
                    dependencies,
                )
                logger.info(
                    log_event(
                        contents_ctx,
                        role="generator",
                        event="contents_cache_written",
                        module=logger.name,
                        fields={
                            "file_id": runtime.file.file_id,
                            "cache_path": str(contents_cache_path),
                        },
                    )
                )
        if contents_resp.has_contents:
            local_contents_page = contents_resp.page_number
            local_contents_heading = contents_resp.heading or ""
            if runtime.settings.contents_preview_enabled:
                contents_preview = dependencies.render_preview(
                    PreviewRequest(
                        schema_version="1.1",
                        pdf_path=runtime.local_pdf_path,
                        out_dir=runtime.settings.output_dir,
                        report_name=runtime.report_name,
                        page_number=max(contents_resp.page_index, 0),
                        variant="contents",
                        dpi=runtime.settings.contents_preview_dpi,
                        pdf_context=pdf_context_for_tasks,
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
    pdf_context_for_tasks: object | None,
    dependencies: ReportGeneratorDependencies,
) -> tuple[PdfTextExtractResponse, dict[str, object]]:
    text_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:text")
    text_resp = None
    text_cache_hit = False
    cache_root = cache_dir(runtime.settings, runtime.md5) if runtime.md5 else None
    text_key = ""
    text_cache_path = None
    if runtime.md5 and cache_root is not None:
        text_key = text_cache_key(runtime.md5, runtime.settings)
        text_cache_path = cache_path(cache_root, "text", text_key)
        cached = read_cache_json(text_cache_path, text_ctx, dependencies)
        if cached and cached.get("key") == text_key:
            text_resp = PdfTextExtractResponse(
                schema_version="1.0",
                text=str(cached.get("text") or ""),
                pages_extracted=int(cached.get("pages_extracted") or 0),
                char_count=int(cached.get("char_count") or 0),
                text_density=float(cached.get("text_density") or 0.0),
            )
            text_cache_hit = True
            logger.info(
                log_event(
                    text_ctx,
                    role="generator",
                    event="text_cache_hit",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "cache_path": str(text_cache_path),
                    },
                )
            )
        else:
            logger.info(
                log_event(
                    text_ctx,
                    role="generator",
                    event="text_cache_miss",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "cache_path": str(text_cache_path) if text_cache_path else "",
                    },
                )
            )
    if text_resp is None:
        text_resp = dependencies.extract_pdf_text(
            PdfTextExtractRequest(
                schema_version="1.0",
                path=runtime.local_pdf_path,
                max_pages=runtime.settings.pdf_text_max_pages,
                max_chars=runtime.settings.pdf_text_max_chars,
                pdf_context=pdf_context_for_tasks,
            ),
            text_ctx,
        )
        if runtime.md5 and cache_root is not None and text_cache_path is not None:
            write_cache_json(
                text_cache_path,
                {
                    "schema_version": "1.0",
                    "key": text_key,
                    "text": text_resp.text,
                    "pages_extracted": text_resp.pages_extracted,
                    "char_count": text_resp.char_count,
                    "text_density": text_resp.text_density,
                },
                text_ctx,
                dependencies,
            )
            logger.info(
                log_event(
                    text_ctx,
                    role="generator",
                    event="text_cache_written",
                    module=logger.name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "cache_path": str(text_cache_path),
                    },
                )
            )
    text_status = {
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
    page_count: int,
    pdf_context: object | None,
    dependencies: ReportGeneratorDependencies,
) -> tuple[str, str, list[int]]:
    sample_ctx = child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:text_sample")
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
            path=runtime.local_pdf_path,
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

    if parallel_within_file:
        with ThreadPoolExecutor(max_workers=runtime.report_worker_limit) as executor:
            info_future = executor.submit(
                _load_pdf_info,
                runtime,
                pdf_context_for_tasks,
                dependencies,
            )
            contents_future = executor.submit(
                _load_contents,
                runtime,
                pdf_context_for_tasks,
                dependencies,
            )
            text_future = executor.submit(
                _load_text,
                runtime,
                pdf_context_for_tasks,
                dependencies,
            )
            info_resp = info_future.result()
            contents_page_number, contents_heading, contents_image = contents_future.result()
            text_resp, text_status = text_future.result()
    else:
        info_resp = _load_pdf_info(runtime, pdf_context_for_tasks, dependencies)
        contents_page_number, contents_heading, contents_image = _load_contents(
            runtime,
            pdf_context_for_tasks,
            dependencies,
        )
        text_resp, text_status = _load_text(runtime, pdf_context_for_tasks, dependencies)

    text_validation_status, text_validation_reason, text_validation_pages = (
        _validate_extractable_text(
            runtime,
            page_count=info_resp.page_count,
            pdf_context=pdf_context,
            dependencies=dependencies,
        )
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
        text_status=text_status,
        text_validation_status=text_validation_status,
        text_validation_reason=text_validation_reason,
        text_validation_pages=text_validation_pages,
        payload=payload,
    )
