from __future__ import annotations

import logging

from src.contracts.llm import (
    OpenAIModelPreflightRequest,
    OpenAIModelPreflightResponse,
)
from src.contracts.run_context import RunContext
from src.services._llm_service.openai_client import _build_openai_client
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.llm_service")


def preflight_openai_model(
    request: OpenAIModelPreflightRequest, ctx: RunContext
) -> OpenAIModelPreflightResponse:
    """Check model access with one bounded metadata request and no inference call."""

    model = str(request.model or "").strip()
    if not model:
        raise AppError(
            code="openai_model_missing",
            message="OpenAI model setting is missing",
            retryable=False,
        )
    if not str(request.api_key or "").strip():
        raise AppError(
            code="openai_missing_api_key",
            message="OpenAI API credential is not configured",
            retryable=False,
        )
    timeout = min(max(float(request.timeout_seconds), 0.1), 10.0)
    client = _build_openai_client(
        api_key=request.api_key,
        timeout_seconds=timeout,
        operation="capability_preflight_model_access",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_model_preflight_start",
            module=logger.name,
            fields={"provider": "openai", "model": model, "timeout_seconds": timeout},
        )
    )
    try:
        model_info = client.models.retrieve(model)
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        if status_code in {401, 403}:
            code, retryable = "openai_credentials_invalid", False
        elif status_code == 404:
            code, retryable = "openai_model_unavailable", False
        else:
            code, retryable = "openai_provider_unavailable", True
        raise AppError(
            code=code,
            message="OpenAI model metadata preflight failed",
            cause=exc,
            retryable=retryable,
            context={"provider": "openai", "model": model},
        ) from exc

    observed_model = str(getattr(model_info, "id", "") or "").strip()
    if not observed_model:
        raise AppError(
            code="openai_model_response_invalid",
            message="OpenAI model preflight returned no model identity",
            retryable=True,
            context={"provider": "openai", "model": model},
        )
    if observed_model != model:
        raise AppError(
            code="openai_model_mismatch",
            message="OpenAI returned a different model identity",
            retryable=False,
            context={"provider": "openai", "model": model},
        )
    response = OpenAIModelPreflightResponse(
        schema_version="1.0", model=model, accessible=True, provider_calls=1
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_model_preflight_complete",
            module=logger.name,
            fields={
                "provider": "openai",
                "model": response.model,
                "accessible": response.accessible,
                "provider_calls": response.provider_calls,
            },
        )
    )
    return response
