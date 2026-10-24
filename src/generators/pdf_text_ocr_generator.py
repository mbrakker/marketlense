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
    read_cache_json,
    write_cache_json,
)
from src.services import file_service
from src.utils.cache_utils import sha256_json
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event
from src.utils.model_client_contract import require_injected_model_client
from src.utils.model_resolver import resolve_settings_execution_policy
from src.utils.path_utils import (
    WINDOWS_COMPONENT_BUDGET,
    WINDOWS_PATH_BUDGET,
    bounded_artifact_filename,
    is_windows_reserved_component,
    safe_path_segment,
    windows_path_units,
)

_OCR_ATOMIC_TEMP_NAME = ".0000000000000000.0000000000000000"
_OCR_IDENTITY_LENGTH = 12


def _ocr_path_error(path: Path, *, role: str, reason: str) -> AppError:
    return AppError(
        code="pdf_text_ocr_path_invalid",
        message=f"{role} cannot fit the supported Windows path policy",
        retryable=False,
        context={
            "path": str(path),
            "path_role": role,
            "reason": reason,
            "windows_path_budget": WINDOWS_PATH_BUDGET,
            "windows_component_budget": WINDOWS_COMPONENT_BUDGET,
            "next_action": "Set a shorter writable OCR cache_dir",
        },
    )


def _validate_ocr_path_components(path: Path, *, role: str) -> None:
    for component in path.parts:
        if component in {path.anchor, "", "."}:
            continue
        if (
            windows_path_units(component) > WINDOWS_COMPONENT_BUDGET
            or component != component.rstrip(" .")
            or is_windows_reserved_component(component)
        ):
            raise _ocr_path_error(path, role=role, reason="path_component_invalid")


def _validate_ocr_redirect(
    path: Path,
    *,
    allowed_root: Path,
    role: str,
) -> None:
    redirect_reason = file_service.path_redirect_reason(
        path,
        allowed_root=allowed_root,
    )
    if redirect_reason is not None:
        raise _ocr_path_error(path, role=role, reason=redirect_reason)


def _resolve_ocr_path(path_value: str | Path, *, role: str) -> Path:
    try:
        path = Path(path_value).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise _ocr_path_error(
            Path(str(path_value)), role=role, reason="path_resolution_failed"
        ) from exc
    _validate_ocr_path_components(path, role=role)
    return path


def _ocr_parent_file_name_budget(parent: Path, *, role: str) -> int:
    parent_units = windows_path_units(parent)
    atomic_temp_units = windows_path_units(_OCR_ATOMIC_TEMP_NAME)
    if parent_units + 1 + atomic_temp_units > WINDOWS_PATH_BUDGET:
        raise _ocr_path_error(parent, role=role, reason="atomic_temp_path_too_long")
    available = min(
        WINDOWS_COMPONENT_BUDGET,
        WINDOWS_PATH_BUDGET - parent_units - 1,
    )
    if available <= 0:
        raise _ocr_path_error(parent, role=role, reason="no_filename_budget")
    return available


def _truncate_ocr_units(value: str, max_units: int) -> str:
    if max_units <= 0:
        return ""
    units = 0
    result: list[str] = []
    for character in value:
        character_units = windows_path_units(character)
        if units + character_units > max_units:
            break
        result.append(character)
        units += character_units
    return "".join(result)


def _bounded_ocr_component(
    raw_value: str,
    *,
    identity: str,
    max_units: int,
    fallback: str,
) -> str:
    safe_value = safe_path_segment(raw_value, fallback=fallback)
    if (
        safe_value == raw_value
        and windows_path_units(safe_value) <= max_units
        and not is_windows_reserved_component(safe_value)
    ):
        return safe_value

    digest = sha256(str(identity).encode("utf-8")).hexdigest()[:_OCR_IDENTITY_LENGTH]
    suffix = f"-{digest}"
    prefix = _truncate_ocr_units(
        safe_value,
        max_units - windows_path_units(suffix),
    ).rstrip(" ._-")
    candidate = f"{prefix}{suffix}" if prefix else digest
    if (
        not candidate
        or windows_path_units(candidate) > max_units
        or windows_path_units(candidate) > WINDOWS_COMPONENT_BUDGET
        or is_windows_reserved_component(candidate)
    ):
        raise _ocr_path_error(
            Path(raw_value),
            role="OCR artifact path",
            reason="component_budget_exhausted",
        )
    return candidate


def _ocr_cache_root(runtime: ReportRuntimeState) -> Path:
    configured_root = Path(runtime.settings.cache_dir).expanduser()
    settings_root = _resolve_ocr_path(
        runtime.settings.cache_dir,
        role="OCR cache root",
    )
    raw_key = str(runtime.md5 or runtime.report_name or runtime.file.file_id or "ocr")
    base_candidates = (settings_root / "pdf_cache", settings_root / ".pdf-cache")
    for base in base_candidates:
        _validate_ocr_redirect(
            base,
            allowed_root=configured_root,
            role="OCR cache root",
        )
        _validate_ocr_path_components(base, role="OCR cache root")
        base_units = windows_path_units(base)
        key_budget = min(
            WINDOWS_COMPONENT_BUDGET,
            WINDOWS_PATH_BUDGET
            - base_units
            - 2
            - windows_path_units(_OCR_ATOMIC_TEMP_NAME),
        )
        if key_budget <= 0:
            continue
        key_component = _bounded_ocr_component(
            raw_key,
            identity=raw_key,
            max_units=key_budget,
            fallback="ocr",
        )
        cache_root = base / key_component
        _validate_ocr_redirect(
            cache_root,
            allowed_root=configured_root,
            role="OCR cache root",
        )
        _validate_ocr_path_components(cache_root, role="OCR cache root")
        try:
            _ocr_parent_file_name_budget(cache_root, role="OCR cache root")
        except AppError:
            continue
        return cache_root
    raise _ocr_path_error(
        settings_root,
        role="OCR cache root",
        reason="cache_root_budget_exhausted",
    )


def _ocr_cache_file_path(
    cache_root: Path,
    *,
    prefix: str,
    cache_key: str,
    extension: str,
) -> Path:
    available = _ocr_parent_file_name_budget(cache_root, role="OCR cache artifact")
    raw_stem = f"{prefix}_{cache_key}"
    normal_name = f"{raw_stem}{extension}"
    if (
        windows_path_units(normal_name) <= available
        and windows_path_units(normal_name) <= WINDOWS_COMPONENT_BUDGET
        and not is_windows_reserved_component(normal_name)
    ):
        return cache_root / normal_name

    bounded_name = bounded_artifact_filename(
        raw_stem,
        compact_stem=f"{prefix}_{cache_key[:_OCR_IDENTITY_LENGTH]}",
        extension=extension,
        max_length=available,
    )
    if (
        windows_path_units(bounded_name) > available
        or windows_path_units(bounded_name) > WINDOWS_COMPONENT_BUDGET
        or is_windows_reserved_component(bounded_name)
    ):
        raise _ocr_path_error(
            cache_root / bounded_name,
            role="OCR cache artifact",
            reason="cache_filename_budget_exhausted",
        )
    return cache_root / bounded_name


def _ocr_chunk_directory(
    runtime: ReportRuntimeState, cache_root: Path, cache_key: str
) -> Path:
    raw_name = f"ocr_chunks_{cache_key or f'run-{runtime.ctx.run_id}'}"
    parent_budget = min(
        WINDOWS_COMPONENT_BUDGET,
        WINDOWS_PATH_BUDGET
        - windows_path_units(cache_root)
        - 2
        - windows_path_units(_OCR_ATOMIC_TEMP_NAME),
    )
    if parent_budget <= 0:
        raise _ocr_path_error(
            cache_root,
            role="OCR chunk directory",
            reason="chunk_directory_budget_exhausted",
        )
    identity = f"{runtime.file.file_id}\x00{cache_key or runtime.ctx.run_id}"
    component = _bounded_ocr_component(
        raw_name,
        identity=identity,
        max_units=parent_budget,
        fallback="ocr_chunks",
    )
    chunk_dir = cache_root / component
    _validate_ocr_path_components(chunk_dir, role="OCR chunk directory")
    try:
        _ocr_parent_file_name_budget(chunk_dir, role="OCR chunk directory")
    except AppError as exc:
        raise _ocr_path_error(
            chunk_dir,
            role="OCR chunk directory",
            reason="chunk_directory_budget_exhausted",
        ) from exc
    return chunk_dir


def _ocr_noncached_output_path(runtime: ReportRuntimeState) -> Path:
    parent = _resolve_ocr_path(runtime.settings.cache_dir, role="OCR output root")
    available = _ocr_parent_file_name_budget(parent, role="OCR output artifact")
    safe_report_name = safe_path_segment(
        runtime.report_name,
        fallback=safe_path_segment(runtime.file.file_id, fallback="report"),
    )
    identity = f"{runtime.file.file_id}\x00{runtime.ctx.run_id}"
    digest = sha256(identity.encode("utf-8")).hexdigest()[:_OCR_IDENTITY_LENGTH]
    identity_suffix = f"-{digest}"
    extension = ".ocr.pdf"
    normal_name = f"{safe_report_name}{identity_suffix}{extension}"
    if (
        windows_path_units(normal_name) <= available
        and windows_path_units(normal_name) <= WINDOWS_COMPONENT_BUDGET
        and not is_windows_reserved_component(normal_name)
    ):
        return parent / normal_name

    identity_budget = (
        available - windows_path_units(identity_suffix) - windows_path_units(extension)
    )
    readable_prefix = _truncate_ocr_units(safe_report_name, identity_budget).rstrip(
        " .-"
    )
    if not readable_prefix:
        raise _ocr_path_error(
            parent,
            role="OCR output artifact",
            reason="output_filename_budget_exhausted",
        )
    bounded_name = f"{readable_prefix}{identity_suffix}{extension}"
    if (
        windows_path_units(bounded_name) > available
        or windows_path_units(bounded_name) > WINDOWS_COMPONENT_BUDGET
        or is_windows_reserved_component(bounded_name)
    ):
        raise _ocr_path_error(
            parent / bounded_name,
            role="OCR output artifact",
            reason="output_filename_budget_exhausted",
        )
    return parent / bounded_name


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
        source_identity_id=str(runtime.ctx.source_identity_id or "").strip(),
        publisher_id=str(runtime.ctx.publisher_id or "").strip(),
        workflow="report_generation",
        stage="source_preparation",
        artifact_family="source_ocr",
    )
    prompt_namespace = runtime.settings.pdf_text_ocr_prompt_namespace
    reasoning_effort = resolve_settings_execution_policy(
        prompt_namespace, runtime.settings
    ).policy.reasoning_effort
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

    noncached_output_path: Path | None = None
    if not runtime.md5 or not runtime.settings.pdf_text_ocr_cache_enabled:
        noncached_output_path = _ocr_noncached_output_path(runtime)
    cache_key = ""
    cache_json_path: Path | None = None
    cache_pdf_path: Path | None = None
    cache_root = _ocr_cache_root(runtime)
    configured_cache_root = Path(runtime.settings.cache_dir).expanduser()
    if noncached_output_path is not None:
        _validate_ocr_redirect(
            noncached_output_path,
            allowed_root=configured_cache_root,
            role="OCR output artifact",
        )
    if runtime.md5 and runtime.settings.pdf_text_ocr_cache_enabled:
        cache_key = sha256_json(
            {
                "schema_version": "1.0",
                "md5": runtime.md5,
                "model": runtime.settings.pdf_text_ocr_model,
                "reasoning_effort": reasoning_effort,
                "prompt_system_sha256": prompt_set.system.sha256,
                "prompt_user_sha256": prompt_set.user.sha256,
                "chunk_page_count": runtime.settings.pdf_text_ocr_chunk_page_count,
            }
        )
        cache_json_path = _ocr_cache_file_path(
            cache_root,
            prefix="ocr_response",
            cache_key=cache_key,
            extension=".json",
        )
        cache_pdf_path = _ocr_cache_file_path(
            cache_root,
            prefix="ocr_text",
            cache_key=cache_key,
            extension=".pdf",
        )
        _validate_ocr_redirect(
            cache_json_path,
            allowed_root=configured_cache_root,
            role="OCR cache metadata",
        )
        _validate_ocr_redirect(
            cache_pdf_path,
            allowed_root=configured_cache_root,
            role="OCR cache PDF",
        )
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

    chunk_directory = _ocr_chunk_directory(runtime, cache_root, cache_key)
    _validate_ocr_redirect(
        chunk_directory,
        allowed_root=configured_cache_root,
        role="OCR chunk directory",
    )
    split_response = dependencies.split_pdf_for_ocr(
        # The split service repeats the check at its public boundary; this
        # generator-side check also prevents cache reads/writes from following
        # a redirected descendant before that service is called.
        PdfOcrSplitRequest(
            schema_version="1.0",
            source_pdf_path=runtime.local_pdf_path,
            output_dir=str(chunk_directory),
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
            reasoning_effort=reasoning_effort,
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
        else str(noncached_output_path)
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
    reasoning_effort: str,
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
                reasoning_effort=reasoning_effort,
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
