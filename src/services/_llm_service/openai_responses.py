# ruff: noqa: F403,F405,I001
from __future__ import annotations

from src.services._llm_service.openai_shared import *
from src.services._llm_service.openai_shared import enforce_daily_spend_guardrail
from src.services._llm_service.openai_client import *


def openai_ocr_pdf(
    request: OpenAIPdfOcrRequest, ctx: RunContext
) -> OpenAIPdfOcrResponse:
    pdf_path_raw = str(request.pdf_path or "").strip()
    if not pdf_path_raw:
        raise AppError(
            code="openai_ocr_invalid_request",
            message="pdf_path is required for OpenAI OCR",
            retryable=False,
        )
    pdf_path = Path(pdf_path_raw)
    try:
        pdf_bytes = pdf_path.read_bytes()
    except FileNotFoundError as exc:
        raise AppError(
            code="openai_ocr_missing_pdf",
            message=f"PDF not found for OCR: {pdf_path}",
            cause=exc,
            retryable=False,
        ) from exc
    except OSError as exc:
        raise AppError(
            code="openai_ocr_pdf_read_failed",
            message=f"Failed to read PDF for OCR: {pdf_path}",
            cause=exc,
            retryable=False,
        ) from exc

    cache_spec = _semantic_response_cache_spec(
        request,
        operation="openai_ocr_pdf",
        params={
            "model": request.model,
            "response_format": "pdf_ocr_pages",
        },
        context={
            "pdf": {
                "path": str(pdf_path),
                "size_bytes": len(pdf_bytes),
                "sha256": hashlib.sha256(pdf_bytes).hexdigest(),
            },
        },
    )
    if cache_spec is not None:
        cached_payload = _read_semantic_response_cache(cache_spec, ctx)
        if cached_payload is not None:
            return _ocr_response_from_cache(cached_payload)
    enforce_daily_spend_guardrail(request, ctx, operation="openai_ocr_pdf")

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_ocr_pdf_start",
            module=logger.name,
            fields={
                "pdf_path": str(pdf_path),
                "pdf_size_bytes": len(pdf_bytes),
                "model": request.model,
                "timeout_seconds": request.timeout_seconds,
                "structured_output": True,
                "input_content_types": ["input_text", "input_file"],
            },
        )
    )
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="ocr_pdf",
        )
        resp = client.responses.create(
            model=request.model,
            instructions=request.system_prompt,
            input=[
                {
                    "role": "user",
                    "content": [
                        {"type": "input_text", "text": request.user_prompt},
                        {
                            "type": "input_file",
                            "filename": pdf_path.name,
                            "file_data": _bytes_to_data_url(
                                pdf_bytes, mime="application/pdf"
                            ),
                        },
                    ],
                }
            ],
            text={"format": OPENAI_OCR_RESPONSE_FORMAT},
        )
    except AppError:
        raise
    except OPENAI_REQUEST_EXCEPTIONS as exc:
        code, message, retryable = _classify_openai_request_error(
            exc,
            default_code="openai_ocr_request_failed",
            default_message="OpenAI OCR request failed",
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="openai_ocr_pdf_error",
                module=logger.name,
                fields={
                    "model": request.model,
                    "pdf_path": str(pdf_path),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        )
        raise AppError(
            code=code,
            message=message,
            cause=exc,
            retryable=retryable,
            context={
                "model": request.model,
                "pdf_path": str(pdf_path),
                "provider_error_type": type(exc).__name__,
            },
        ) from exc

    resolved_model = str(getattr(resp, "model", None) or request.model)
    metadata = _adapt_responses_metadata(resp, recover_json_object=True)
    accounting = _record_usage_accounting(
        ctx=ctx,
        step_name="openai_ocr_pdf",
        model=resolved_model,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        total_tokens=metadata.total_tokens,
        tool_calls=metadata.tool_calls,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=metadata.request_id,
        source_request=request,
        parse_status="not_validated",
        schema_validation_status="not_validated",
    )
    pages = _coerce_pdf_ocr_pages(metadata.parsed_json)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_ocr_pdf_response_received",
            module=logger.name,
            fields={
                "model": resolved_model,
                "request_id": metadata.request_id or "",
                "input_tokens": metadata.input_tokens,
                "output_tokens": metadata.output_tokens,
                "tool_calls": metadata.tool_calls,
                "parse_strategy": metadata.parse_strategy,
                "page_count": len(pages),
            },
        )
    )
    if not pages:
        _finalize_usage_accounting(
            accounting=accounting,
            ctx=ctx,
            parse_status="invalid",
            schema_validation_status="invalid",
            error_stage="output_validation",
            error_code="openai_ocr_invalid_response",
        )
        raise AppError(
            code="openai_ocr_invalid_response",
            message="OpenAI OCR returned no structured pages",
            retryable=False,
            context={
                "model": resolved_model,
                "request_id": metadata.request_id or "",
                "parse_strategy": metadata.parse_strategy,
                "response_text_preview": metadata.text[:400],
            },
        )

    _finalize_usage_accounting(
        accounting=accounting,
        ctx=ctx,
        parse_status="valid",
        schema_validation_status="valid",
    )
    response = OpenAIPdfOcrResponse(
        schema_version="1.0",
        pages=pages,
        raw_text=metadata.text,
        model=resolved_model,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        tool_calls=metadata.tool_calls,
        request_id=metadata.request_id,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_ocr_pdf_complete",
            module=logger.name,
            fields={
                "request_id": response.request_id or "",
                "model": response.model,
                "page_count": len(response.pages),
                "first_page": response.pages[0].page_number if response.pages else 0,
            },
        )
    )
    _write_semantic_response_cache(
        cache_spec,
        ctx,
        response_payload=asdict(response),
    )
    return response


def openai_respond_with_vector_store(
    request: OpenAIResponseRequest, ctx: RunContext
) -> OpenAIResponseResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_response_start",
            module=logger.name,
            fields={
                "model": request.model,
                "temperature": request.temperature,
                "vector_store_id": request.vector_store_id,
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    if not request.vector_store_id:
        raise AppError(
            code="vector_store_missing",
            message="vector_store_id is required for file search responses",
            retryable=False,
        )
    cache_spec = _semantic_response_cache_spec(
        request,
        operation="openai_response_vector_store",
        params={
            "model": request.model,
            "temperature": request.temperature,
            "seed": request.seed,
            "max_output_tokens": request.max_output_tokens,
            "tools": ["file_search"],
        },
        context={"vector_store_id": request.vector_store_id},
    )
    if cache_spec is not None:
        cached_payload = _read_semantic_response_cache(cache_spec, ctx)
        if cached_payload is not None:
            return _openai_response_result_from_cache(cached_payload)
    enforce_daily_spend_guardrail(
        request, ctx, operation="openai_respond_with_vector_store"
    )
    payload_args: dict[str, Any] = {
        "model": request.model,
        "instructions": request.system_prompt,
        "input": [{"role": "user", "content": request.user_prompt}],
        "tools": [
            {"type": "file_search", "vector_store_ids": [request.vector_store_id]}
        ],
    }
    if request.max_output_tokens is not None:
        payload_args["max_output_tokens"] = request.max_output_tokens
    known_unsupported = _known_unsupported_responses_params(request.model)
    skipped_params: set[str] = set()
    if request.temperature is not None:
        if "temperature" in known_unsupported:
            skipped_params.add("temperature")
        else:
            payload_args["temperature"] = request.temperature
    if request.seed is not None:
        if "seed" in known_unsupported:
            skipped_params.add("seed")
        else:
            payload_args["seed"] = request.seed
    if skipped_params:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="openai_response_skip_known_unsupported_params",
                module=logger.name,
                fields={
                    "model": request.model,
                    "skipped_params": sorted(skipped_params),
                },
            )
        )
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="response_vector_store",
        )
        resp = client.responses.create(**payload_args)
    except AppError:
        raise
    except OPENAI_REQUEST_EXCEPTIONS as exc:
        code, message, retryable = _classify_openai_request_error(
            exc,
            default_code="openai_response_failed",
            default_message="OpenAI responses request failed",
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="openai_response_error",
                module=logger.name,
                fields={
                    "model": request.model,
                    "vector_store_id": request.vector_store_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                },
            )
        )
        raise AppError(
            code=code,
            message=message,
            cause=exc,
            retryable=retryable,
            context={
                "model": request.model,
                "vector_store_id": request.vector_store_id,
                "error": str(exc),
                "provider_error_type": type(exc).__name__,
            },
        ) from exc

    metadata = _adapt_responses_metadata(resp, recover_json_object=True)
    parse_error_code = ""
    parse_error_message = ""
    if metadata.parsed_json is None:
        if metadata.parse_strategy == "empty":
            parse_error_code = "openai_response_empty"
            parse_error_message = "OpenAI response from vector store is empty"
        elif metadata.parse_strategy == "json_non_object":
            parse_error_code = "openai_response_json_type_invalid"
            parse_error_message = "OpenAI response JSON must be an object"
        else:
            parse_error_code = "openai_response_invalid_json"
            parse_error_message = "OpenAI response is not valid JSON"

    accounting = _record_usage_accounting(
        ctx=ctx,
        step_name="openai_response_vector_store",
        model=request.model,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        total_tokens=metadata.total_tokens,
        tool_calls=metadata.tool_calls,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=metadata.request_id,
        source_request=request,
        parse_status=("valid" if metadata.parsed_json is not None else "invalid"),
        schema_validation_status="not_validated",
    )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_response_complete",
            module=logger.name,
            fields={
                "model": request.model,
                "request_id": metadata.request_id or "",
                "input_tokens": metadata.input_tokens,
                "output_tokens": metadata.output_tokens,
                "tool_calls": metadata.tool_calls,
                "parsed_json": metadata.parsed_json is not None,
                "parse_strategy": metadata.parse_strategy,
                "parse_error_code": parse_error_code,
            },
        )
    )
    if parse_error_code:
        _finalize_usage_accounting(
            accounting=accounting,
            ctx=ctx,
            parse_status="invalid",
            schema_validation_status="not_validated",
            error_stage="output_validation",
            error_code=parse_error_code,
        )
        raise AppError(
            code=parse_error_code,
            message=parse_error_message,
            retryable=False,
            context={
                "model": request.model,
                "vector_store_id": request.vector_store_id,
                "parse_strategy": metadata.parse_strategy,
                "response_text_preview": metadata.text[:240],
            },
        )
    _finalize_usage_accounting(
        accounting=accounting,
        ctx=ctx,
        parse_status="valid",
        schema_validation_status="valid",
    )
    result = OpenAIResponseResult(
        schema_version="1.0",
        text=metadata.text,
        parsed_json=metadata.parsed_json,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        tool_calls=metadata.tool_calls,
        model=request.model,
        total_tokens=metadata.total_tokens,
        request_id=metadata.request_id,
    )
    _write_semantic_response_cache(
        cache_spec,
        ctx,
        response_payload=asdict(result),
    )
    return result


__all__ = [name for name in globals() if not name.startswith("__")]
