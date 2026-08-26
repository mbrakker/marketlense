# ruff: noqa: F403,F405
from __future__ import annotations

from src.services._llm_service.openai_client import (
    _build_openai_client,
    _value_from_response,
)
from src.services._llm_service.openai_shared import *
from src.services._llm_service.openai_shared import enforce_daily_spend_guardrail


def _embedding_vectors_from_response(resp: Any) -> list[list[float]]:
    data = getattr(resp, "data", None)
    if data is None and isinstance(resp, dict):
        data = resp.get("data")
    if not isinstance(data, list) or not data:
        raise AppError(
            code="openai_embedding_response_empty",
            message="OpenAI embedding response did not contain vectors",
            retryable=True,
            severity="error",
        )
    vectors: list[list[float]] = []
    for item in data:
        embedding = getattr(item, "embedding", None)
        if embedding is None and isinstance(item, dict):
            embedding = item.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise AppError(
                code="openai_embedding_vector_invalid",
                message="OpenAI embedding response contained an invalid vector",
                retryable=True,
                severity="error",
            )
        try:
            vectors.append([float(value) for value in embedding])
        except (TypeError, ValueError) as exc:
            raise AppError(
                code="openai_embedding_vector_invalid",
                message="OpenAI embedding vector values must be numeric",
                cause=exc,
                retryable=True,
                severity="error",
            ) from exc
    dimensions = len(vectors[0])
    if any(len(vector) != dimensions for vector in vectors):
        raise AppError(
            code="openai_embedding_dimensions_mismatch",
            message="OpenAI embedding vectors returned inconsistent dimensions",
            retryable=True,
            severity="error",
        )
    return vectors


def _embedding_usage(resp: Any) -> tuple[int | None, int | None]:
    usage = getattr(resp, "usage", None)
    if isinstance(usage, dict):
        input_tokens = usage.get("prompt_tokens") or usage.get("input_tokens")
        total_tokens = usage.get("total_tokens")
        return (
            int(input_tokens) if input_tokens is not None else None,
            int(total_tokens) if total_tokens is not None else None,
        )
    input_tokens = getattr(usage, "prompt_tokens", None) or getattr(
        usage, "input_tokens", None
    )
    total_tokens = getattr(usage, "total_tokens", None)
    return (
        int(input_tokens) if input_tokens is not None else None,
        int(total_tokens) if total_tokens is not None else None,
    )


def openai_create_embeddings(
    request: OpenAIEmbeddingRequest,
    ctx: RunContext,
) -> OpenAIEmbeddingResponse:
    inputs = [str(value or "").strip() for value in request.inputs]
    if not inputs or any(not value for value in inputs):
        raise AppError(
            code="openai_embedding_input_missing",
            message="Embedding inputs must be non-empty strings",
            retryable=False,
            severity="error",
        )
    if int(request.dimensions) <= 0:
        raise AppError(
            code="openai_embedding_dimensions_invalid",
            message="Embedding dimensions must be a positive integer",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_embedding_create_start",
            module=logger.name,
            fields={
                "model": request.model,
                "input_count": len(inputs),
                "dimensions": request.dimensions,
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    enforce_daily_spend_guardrail(request, ctx, operation="openai_embeddings")
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="embedding_create",
        )
        resp = client.embeddings.create(
            model=request.model,
            input=inputs,
            dimensions=request.dimensions,
        )
    except AppError:
        raise
    except OPENAI_REQUEST_EXCEPTIONS as exc:
        code, message, retryable = _classify_openai_request_error(
            exc,
            default_code="openai_embedding_request_failed",
            default_message="OpenAI embedding request failed",
        )
        raise AppError(
            code=code,
            message=message,
            cause=exc,
            retryable=retryable,
            severity="error",
        ) from exc

    vectors = _embedding_vectors_from_response(resp)
    if any(len(vector) != request.dimensions for vector in vectors):
        raise AppError(
            code="openai_embedding_dimensions_mismatch",
            message="OpenAI embedding vectors did not match requested dimensions",
            retryable=True,
            severity="error",
            context={"expected": request.dimensions, "actual": len(vectors[0])},
        )
    input_tokens, total_tokens = _embedding_usage(resp)
    request_id = _value_from_response(resp, "id")
    model = str(_value_from_response(resp, "model") or request.model)
    accounting = _record_usage_accounting(
        ctx=ctx,
        step_name="openai_embeddings",
        model=model,
        input_tokens=input_tokens,
        output_tokens=None,
        total_tokens=total_tokens,
        tool_calls=0,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=str(request_id) if request_id else None,
        source_request=request,
        parse_status="not_applicable",
        schema_validation_status="not_validated",
    )
    if len(vectors) != len(inputs):
        _finalize_usage_accounting(
            accounting=accounting,
            ctx=ctx,
            parse_status="not_applicable",
            schema_validation_status="invalid",
            error_stage="output_validation",
            error_code="openai_embedding_count_mismatch",
        )
        raise AppError(
            code="openai_embedding_count_mismatch",
            message="OpenAI embedding response count did not match request inputs",
            retryable=True,
            severity="error",
            context={"expected": len(inputs), "actual": len(vectors)},
        )
    _finalize_usage_accounting(
        accounting=accounting,
        ctx=ctx,
        parse_status="not_applicable",
        schema_validation_status="valid",
    )
    response = OpenAIEmbeddingResponse(
        schema_version="1.0",
        embeddings=vectors,
        model=model,
        dimensions=len(vectors[0]),
        request_id=str(request_id) if request_id else None,
        input_tokens=input_tokens,
        total_tokens=total_tokens,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_embedding_create_complete",
            module=logger.name,
            fields={
                "model": response.model,
                "input_count": len(inputs),
                "dimensions": response.dimensions,
                "request_id": response.request_id,
                "input_tokens": response.input_tokens,
                "total_tokens": response.total_tokens,
            },
        )
    )
    return response


__all__ = [name for name in globals() if not name.startswith("__")]
