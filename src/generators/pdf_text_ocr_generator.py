from __future__ import annotations

import json
import logging
from dataclasses import asdict, replace
from hashlib import sha256
from pathlib import Path

from src.contracts.files import FileStatRequest
from src.contracts.openai import OpenAIPdfOcrRequest, OpenAIPdfOcrResponse
from src.contracts.pdf_ocr import (
    PdfOcrAggregateResponse,
    PdfOcrChunk,
    PdfOcrFallbackResponse,
    PdfOcrPageText,
    PdfOcrSplitRequest,
    PdfTextRenderRequest,
    PdfTextRenderResponse,
)
from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest
from src.contracts.report_generation import ReportRuntimeState
from src.generators.report_generation_dependencies import ReportSourceDependencies
from src.generators.report_generation_shared import (
    cache_dir,
    read_cache_json,
    write_cache_json,
)
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event
from src.utils.model_client_contract import require_injected_model_client


def recover_pdf_text_with_ocr(
    runtime: ReportRuntimeState,
    *,
    page_count: int,
    dependencies: ReportSourceDependencies,
    llm_client=None,
) -> PdfOcrFallbackResponse:
    logger = logging.getLogger("market_lense.pdf_text_ocr_generator")
    ocr_ctx = replace(
        child_context(runtime.ctx, task_id=f"{runtime.ctx.task_id}:ocr_fallback"),
        report_id=runtime.file.file_id,
        source_identity_id=runtime.md5 or runtime.file.file_id,
        publisher_id=runtime.publisher_name or "unattributed",
        workflow="report_generation",
        stage="source_preparation",
        artifact_family="source_ocr",
    )
    prompt_namespace = runtime.settings.pdf_text_ocr_prompt_namespace
    prompt_set = dependencies.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace=prompt_namespace,
            reload_if_changed=True,
        ),
        ocr_ctx,
    )
    logger.info(
        log_event(
            ocr_ctx,
            role="generator",
            event="ocr_prompt_selected",
            module=logger.name,
            fields={
                "namespace": prompt_namespace,
                "system_path": prompt_set.system.path,
                "system_sha256": prompt_set.system.sha256,
                "user_path": prompt_set.user.path,
                "user_sha256": prompt_set.user.sha256,
            },
        )
    )
    system_render = dependencies.render_prompt(
        PromptRenderRequest(
            schema_version="1.0",
            template=prompt_set.system,
            variables={},
        ),
        ocr_ctx,
    )

    cache_key = ""
    cache_json_path: Path | None = None
    cache_pdf_path: Path | None = None
    cache_root = _ocr_cache_root(runtime)
    if runtime.md5 and runtime.settings.pdf_text_ocr_cache_enabled:
        cache_key = sha256_json(
            {
                "schema_version": "1.0",
                "md5": runtime.md5,
                "model": runtime.settings.pdf_text_ocr_model,
                "prompt_system_sha256": prompt_set.system.sha256,
                "prompt_user_sha256": prompt_set.user.sha256,
                "chunk_page_count": runtime.settings.pdf_text_ocr_chunk_page_count,
            }
        )
        cache_json_path = cache_root / f"ocr_response_{cache_key}.json"
        cache_pdf_path = cache_root / f"ocr_text_{cache_key}.pdf"
        cached_payload = read_cache_json(cache_json_path, ocr_ctx, dependencies)
        cached_pdf_exists = False
        if cache_pdf_path is not None:
            cached_pdf_stat = dependencies.file_stat(
                FileStatRequest(schema_version="1.0", path=str(cache_pdf_path)),
                ocr_ctx,
            )
            cached_pdf_exists = bool(cached_pdf_stat.exists)
        if (
            isinstance(cached_payload, dict)
            and cached_payload.get("key") == cache_key
            and cached_pdf_exists
        ):
            cached_response = _cached_response_from_payload(cached_payload)
            logger.info(
                log_event(
                    ocr_ctx,
                    role="generator",
                    event="ocr_cache_hit",
                    module=logger.name,
                    fields={
                        "cache_key": cache_key,
                        "cache_json_path": str(cache_json_path),
                        "cache_pdf_path": str(cache_pdf_path),
                    },
                )
            )
            return PdfOcrFallbackResponse(
                schema_version="1.0",
                ocr_response=cached_response,
                render_response=PdfTextRenderResponse(
                    schema_version="1.0",
                    output_path=str(cache_pdf_path),
                    rendered_page_count=len(cached_response.pages),
                ),
                cache_hit=True,
            )
        logger.info(
            log_event(
                ocr_ctx,
                role="generator",
                event="ocr_cache_miss",
                module=logger.name,
                fields={
                    "cache_key": cache_key,
                    "cache_json_path": str(cache_json_path) if cache_json_path else "",
                    "cache_pdf_path": str(cache_pdf_path) if cache_pdf_path else "",
                },
            )
        )

    attempted_models = _ocr_candidate_models(runtime)
    if not attempted_models:
        raise AppError(
            code="pdf_text_ocr_failed",
            message="OCR fallback failed",
            retryable=False,
            context={
                "ocr_error_code": "ocr_model_candidates_empty",
                "ocr_error_message": "No OCR model candidates were configured",
                "attempted_models": attempted_models,
            },
        )

    chunk_dir_name = cache_key or f"run-{runtime.ctx.run_id}"
    split_response = dependencies.split_pdf_for_ocr(
        PdfOcrSplitRequest(
            schema_version="1.0",
            source_pdf_path=runtime.local_pdf_path,
            output_dir=str(cache_root / f"ocr_chunks_{chunk_dir_name}"),
            chunk_page_count=runtime.settings.pdf_text_ocr_chunk_page_count,
        ),
        ocr_ctx,
    )
    logger.info(
        log_event(
            ocr_ctx,
            role="generator",
            event="ocr_chunk_plan_ready",
            module=logger.name,
            fields={
                "chunk_count": len(split_response.chunks),
                "chunk_page_count": runtime.settings.pdf_text_ocr_chunk_page_count,
                "source_page_count": page_count,
            },
        )
    )

    aggregated_pages: list[PdfOcrPageText] = []
    models_used: list[str] = []
    request_ids: list[str] = []
    raw_chunks: list[dict[str, object]] = []
    llm_client = require_injected_model_client(llm_client, scope="pdf_text_ocr")
    for chunk in split_response.chunks:
        chunk_ctx = child_context(
            ocr_ctx,
            task_id=f"{ocr_ctx.task_id}:ocr_chunk:{chunk.chunk_index}",
        )
        user_render = dependencies.render_prompt(
            PromptRenderRequest(
                schema_version="1.0",
                template=prompt_set.user,
                variables={
                    "page_count": chunk.page_count,
                    "source_page_start": chunk.start_page_number,
                    "source_page_end": chunk.end_page_number,
                },
            ),
            chunk_ctx,
        )
        logger.info(
            log_event(
                chunk_ctx,
                role="generator",
                event="ocr_chunk_prompt_rendered",
                module=logger.name,
                fields={
                    "chunk_index": chunk.chunk_index,
                    "chunk_pdf_path": chunk.chunk_pdf_path,
                    "source_page_start": chunk.start_page_number,
                    "source_page_end": chunk.end_page_number,
                    "prompt_content_hash": prompt_set.prompt_content_hash,
                    "system_prompt_chars": len(system_render.text),
                    "user_prompt_chars": len(user_render.text),
                },
            )
        )
        chunk_response = _run_ocr_chunk(
            runtime=runtime,
            llm_client=llm_client,
            chunk=chunk,
            system_prompt=system_render.text,
            user_prompt=user_render.text,
            attempted_models=attempted_models,
            logger=logger,
            chunk_ctx=chunk_ctx,
            prompt_namespace=prompt_namespace,
            prompt_hash=prompt_set.user.sha256,
        )
        chunk_pages = _map_chunk_pages(chunk, chunk_response.pages)
        aggregated_pages.extend(chunk_pages)
        if chunk_response.model and chunk_response.model not in models_used:
            models_used.append(chunk_response.model)
        if chunk_response.request_id and chunk_response.request_id not in request_ids:
            request_ids.append(chunk_response.request_id)
        raw_chunks.append(
            {
                "chunk_index": chunk.chunk_index,
                "chunk_pdf_path": chunk.chunk_pdf_path,
                "source_page_start": chunk.start_page_number,
                "source_page_end": chunk.end_page_number,
                "resolved_model": chunk_response.model,
                "request_id": chunk_response.request_id,
                "response_chars": len(chunk_response.raw_text or ""),
                "response_sha256": sha256(
                    (chunk_response.raw_text or "").encode("utf-8")
                ).hexdigest(),
            }
        )

    ocr_response = PdfOcrAggregateResponse(
        schema_version="1.0",
        pages=sorted(aggregated_pages, key=lambda page: page.page_number),
        raw_text=json.dumps({"chunks": raw_chunks}, ensure_ascii=True),
        models=models_used,
        request_ids=request_ids,
        chunk_count=len(split_response.chunks),
    )
    output_path = (
        str(cache_pdf_path)
        if cache_pdf_path is not None
        else str(Path(runtime.settings.cache_dir) / f"{runtime.report_name}.ocr.pdf")
    )
    try:
        render_response = dependencies.render_text_pdf(
            PdfTextRenderRequest(
                schema_version="1.0",
                output_path=output_path,
                pages=list(ocr_response.pages),
            ),
            ocr_ctx,
        )
    except AppError as exc:
        raise AppError(
            code="pdf_text_ocr_failed",
            message="OCR PDF render failed",
            cause=exc,
            retryable=exc.retryable,
            severity=exc.severity,
            context={"ocr_error_code": exc.code, "ocr_error_message": exc.message},
        ) from exc

    if cache_key and cache_json_path is not None:
        write_cache_json(
            cache_json_path,
            {
                "schema_version": "1.0",
                "key": cache_key,
                "ocr_response": asdict(ocr_response),
                "render_response": asdict(render_response),
            },
            ocr_ctx,
            dependencies,
        )
        logger.info(
            log_event(
                ocr_ctx,
                role="generator",
                event="ocr_cache_written",
                module=logger.name,
                fields={
                    "cache_key": cache_key,
                    "cache_json_path": str(cache_json_path),
                    "cache_pdf_path": render_response.output_path,
                },
            )
        )
    logger.info(
        log_event(
            ocr_ctx,
            role="generator",
            event="ocr_validation_complete",
            module=logger.name,
            fields={
                "page_count": len(ocr_response.pages),
                "rendered_page_count": render_response.rendered_page_count,
                "chunk_count": ocr_response.chunk_count,
                "models": list(ocr_response.models),
            },
        )
    )
    return PdfOcrFallbackResponse(
        schema_version="1.0",
        ocr_response=ocr_response,
        render_response=render_response,
        cache_hit=False,
    )


def _run_ocr_chunk(
    *,
    runtime: ReportRuntimeState,
    llm_client,
    chunk: PdfOcrChunk,
    system_prompt: str,
    user_prompt: str,
    attempted_models: list[str],
    logger: logging.Logger,
    chunk_ctx,
    prompt_namespace: str,
    prompt_hash: str,
) -> OpenAIPdfOcrResponse:
    if not attempted_models:
        raise AppError(
            code="pdf_text_ocr_failed",
            message="OCR fallback failed",
            retryable=False,
            context={
                "ocr_error_code": "ocr_model_candidates_empty",
                "ocr_error_message": "No OCR model candidates were configured",
                "attempted_models": attempted_models,
                "chunk_index": chunk.chunk_index,
            },
        )

    candidate_model = attempted_models[0]
    logger.info(
        log_event(
            chunk_ctx,
            role="generator",
            event="ocr_model_attempt_start",
            module=logger.name,
            fields={
                "chunk_index": chunk.chunk_index,
                "source_page_start": chunk.start_page_number,
                "source_page_end": chunk.end_page_number,
                "attempt": 1,
                "requested_model": candidate_model,
                "attempted_models": attempted_models,
            },
        )
    )
    try:
        response = llm_client.openai_ocr_pdf(
            OpenAIPdfOcrRequest(
                schema_version="1.0",
                api_key=runtime.settings.openai_api_key,
                pdf_path=chunk.chunk_pdf_path,
                model=candidate_model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                timeout_seconds=runtime.settings.pdf_text_ocr_timeout_seconds,
                cost_ledger_path=runtime.settings.cost_ledger_path,
                cost_daily_path=runtime.settings.cost_daily_path,
                usage_db_path=str(
                    getattr(
                        runtime.settings, "usage_db_path", "./state/llm_usage.sqlite"
                    )
                ),
                model_pricing=runtime.settings.model_pricing,
                publisher_name=runtime.publisher_name,
                report_name=runtime.source_report_name or runtime.report_title,
                source_url=runtime.source_url,
                prompt_namespace=prompt_namespace,
                prompt_hash=prompt_hash,
            ),
            chunk_ctx,
        )
    except AppError as exc:
        logger.warning(
            log_event(
                chunk_ctx,
                role="generator",
                event="ocr_model_attempt_failed",
                module=logger.name,
                fields={
                    "chunk_index": chunk.chunk_index,
                    "source_page_start": chunk.start_page_number,
                    "source_page_end": chunk.end_page_number,
                    "attempt": 1,
                    "requested_model": candidate_model,
                    "attempted_models": attempted_models,
                    "error_code": exc.code,
                    "error_message": exc.message,
                    "retryable": exc.retryable,
                },
            )
        )
        raise AppError(
            code="pdf_text_ocr_failed",
            message="OCR fallback failed",
            cause=exc,
            retryable=exc.retryable,
            severity=exc.severity,
            context={
                "ocr_error_code": exc.code,
                "ocr_error_message": exc.message,
                "attempted_models": attempted_models,
                "chunk_index": chunk.chunk_index,
                "source_page_start": chunk.start_page_number,
                "source_page_end": chunk.end_page_number,
            },
        ) from exc

    logger.info(
        log_event(
            chunk_ctx,
            role="generator",
            event="ocr_model_response",
            module=logger.name,
            fields={
                "chunk_index": chunk.chunk_index,
                "source_page_start": chunk.start_page_number,
                "source_page_end": chunk.end_page_number,
                "attempt": 1,
                "requested_model": candidate_model,
                "resolved_model": response.model,
                "request_id": response.request_id or "",
                "response_chars": len(response.raw_text or ""),
                "response_sha256": sha256(
                    (response.raw_text or "").encode("utf-8")
                ).hexdigest(),
                "page_count": len(response.pages),
            },
        )
    )
    return response


def _map_chunk_pages(
    chunk: PdfOcrChunk, raw_pages: list[PdfOcrPageText]
) -> list[PdfOcrPageText]:
    if not raw_pages:
        raise AppError(
            code="pdf_text_ocr_failed",
            message="OCR chunk returned no pages",
            retryable=False,
            context={
                "chunk_index": chunk.chunk_index,
                "source_page_start": chunk.start_page_number,
                "source_page_end": chunk.end_page_number,
            },
        )
    numbering_mode = _detect_chunk_numbering(chunk, raw_pages)
    if numbering_mode == "invalid":
        raise AppError(
            code="pdf_text_ocr_failed",
            message="OCR chunk returned unexpected page numbers",
            retryable=False,
            context={
                "chunk_index": chunk.chunk_index,
                "source_page_start": chunk.start_page_number,
                "source_page_end": chunk.end_page_number,
                "raw_page_numbers": [page.page_number for page in raw_pages],
            },
        )
    mapped_pages: list[PdfOcrPageText] = []
    pages_by_number = {page.page_number: page for page in raw_pages}
    for source_page_number in range(chunk.start_page_number, chunk.end_page_number + 1):
        lookup_page_number = (
            source_page_number - chunk.start_page_number + 1
            if numbering_mode == "relative"
            else source_page_number
        )
        page = pages_by_number.get(lookup_page_number)
        mapped_pages.append(
            PdfOcrPageText(
                schema_version=page.schema_version if page else "1.0",
                page_number=source_page_number,
                text=page.text if page else "",
            )
        )
    return mapped_pages


def _detect_chunk_numbering(chunk: PdfOcrChunk, raw_pages: list[PdfOcrPageText]) -> str:
    page_numbers = [page.page_number for page in raw_pages]
    if all(1 <= page_number <= chunk.page_count for page_number in page_numbers):
        return "relative"
    if all(
        chunk.start_page_number <= page_number <= chunk.end_page_number
        for page_number in page_numbers
    ):
        return "absolute"
    return "invalid"


def _ocr_candidate_models(runtime: ReportRuntimeState) -> list[str]:
    model = str(runtime.settings.pdf_text_ocr_model or "").strip()
    return [model] if model else []


def _ocr_cache_root(runtime: ReportRuntimeState) -> Path:
    cache_key = runtime.md5 or runtime.report_name or runtime.file.file_id
    return cache_dir(runtime.settings, cache_key)


def _cached_response_from_payload(payload: dict) -> PdfOcrAggregateResponse:
    response_payload = payload.get("ocr_response")
    if not isinstance(response_payload, dict):
        raise AppError(
            code="pdf_text_ocr_failed",
            message="OCR cache payload missing response",
            retryable=False,
        )
    raw_pages = response_payload.get("pages")
    pages: list[PdfOcrPageText] = []
    if isinstance(raw_pages, list):
        for page_payload in raw_pages:
            if isinstance(page_payload, dict):
                pages.append(
                    PdfOcrPageText(
                        schema_version=str(page_payload.get("schema_version") or "1.0"),
                        page_number=int(page_payload.get("page_number") or 0),
                        text=str(page_payload.get("text") or ""),
                    )
                )
    raw_models = response_payload.get("models")
    models = [str(model).strip() for model in raw_models or [] if str(model).strip()]
    if not models:
        legacy_model = str(response_payload.get("model") or "").strip()
        if legacy_model:
            models = [legacy_model]
    raw_request_ids = response_payload.get("request_ids")
    request_ids = [
        str(request_id).strip()
        for request_id in raw_request_ids or []
        if str(request_id).strip()
    ]
    if not request_ids:
        legacy_request_id = str(response_payload.get("request_id") or "").strip()
        if legacy_request_id:
            request_ids = [legacy_request_id]
    chunk_count = int(response_payload.get("chunk_count") or max(len(models), 1))
    return PdfOcrAggregateResponse(
        schema_version=str(response_payload.get("schema_version") or "1.0"),
        pages=pages,
        raw_text=str(response_payload.get("raw_text") or ""),
        models=models,
        request_ids=request_ids,
        chunk_count=chunk_count,
    )
