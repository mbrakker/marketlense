from __future__ import annotations

from src.services._openai_service.base import *


def _require_api_key(api_key: str, *, operation: str) -> str:
    key = str(api_key or "").strip()
    if not key:
        raise AppError(
            code="openai_missing_api_key",
            message="OPENAI_API_KEY is required",
            retryable=False,
            context={"operation": operation},
        )
    return key


def _build_openai_client(
    *, api_key: str, timeout_seconds: float | None, operation: str
) -> Any:
    client_kwargs: dict[str, Any] = {
        "api_key": _require_api_key(api_key, operation=operation)
    }
    if timeout_seconds is not None:
        client_kwargs["timeout"] = timeout_seconds
    try:
        client_factory = _openai_client_factory()
        if client_factory is None:
            raise TypeError("OpenAI client not available")
        return client_factory(**client_kwargs)
    except TypeError as exc:
        raise AppError(
            code="openai_client_unavailable",
            message="OpenAI client not available",
            cause=exc,
            retryable=False,
            context={"operation": operation},
        ) from exc
    except OPENAI_CLIENT_INIT_EXCEPTIONS as exc:
        raise AppError(
            code="openai_client_init_failed",
            message="Failed to initialize OpenAI client",
            cause=exc,
            retryable=True,
            context={"operation": operation},
        ) from exc


def _value_from_response(response: Any, field: str) -> Any:
    value = getattr(response, field, None)
    if value is None and isinstance(response, dict):
        return response.get(field)
    return value


def _require_openai_id(response: Any, *, code: str, message: str) -> str:
    response_id = _value_from_response(response, "id")
    if not response_id:
        raise AppError(code=code, message=message, retryable=True)
    return str(response_id)


def _log_vector_store_event(
    ctx: RunContext, *, event: str, fields: dict[str, Any]
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields=fields,
        )
    )


def _run_vector_store_request(
    *,
    api_key: str,
    timeout_seconds: float | None,
    spec: _VectorStoreOperationSpec,
    ctx: RunContext,
    request_fn: Callable[[Any], Any],
    error_context: dict[str, Any] | None = None,
) -> Any:
    try:
        client = _build_openai_client(
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            operation=spec.operation,
        )
        return request_fn(client)
    except AppError:
        raise
    except OPENAI_REQUEST_EXCEPTIONS as exc:
        raise AppError(
            code=spec.error_code,
            message=spec.error_message,
            cause=exc,
            retryable=True,
            context=error_context,
        ) from exc


__all__ = [
    "_build_openai_client",
    "_log_vector_store_event",
    "_require_api_key",
    "_require_openai_id",
    "_run_vector_store_request",
    "_value_from_response",
]
