from __future__ import annotations

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from src.contracts.llm import (
    OpenRouterModelPreflightRequest,
    OpenRouterModelPreflightResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.llm_service")
_MAX_MODEL_RESPONSE_BYTES = 2 * 1024 * 1024


def preflight_openrouter_model(
    request: OpenRouterModelPreflightRequest, ctx: RunContext
) -> OpenRouterModelPreflightResponse:
    """Check authenticated model metadata without making an inference request."""

    api_key = str(request.api_key or "").strip()
    if not api_key:
        raise AppError(
            code="openrouter_missing_api_key",
            message="OpenRouter API credential is not configured",
            retryable=False,
        )
    model = str(request.model or "").strip()
    parts = model.split("/", 1)
    if len(parts) != 2 or not all(parts) or any("/" in part for part in parts):
        raise AppError(
            code="openrouter_model_invalid",
            message="OpenRouter model must use author/model-slug form",
            retryable=False,
        )

    timeout = min(max(float(request.timeout_seconds), 0.1), 10.0)
    path = "/".join(quote(part, safe="-_.:") for part in parts)
    http_request = Request(
        f"https://openrouter.ai/api/v1/model/{path}",
        headers={"Authorization": f"Bearer {api_key}", "Accept": "application/json"},
        method="GET",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_model_preflight_start",
            module=logger.name,
            fields={
                "provider": "openrouter",
                "model": model,
                "timeout_seconds": timeout,
            },
        )
    )
    try:
        with urlopen(http_request, timeout=timeout) as response:
            raw_response = response.read(_MAX_MODEL_RESPONSE_BYTES + 1)
    except HTTPError as exc:
        status_code = int(exc.code)
        if status_code in {401, 403}:
            code, retryable = "openrouter_credentials_invalid", False
        elif status_code == 404:
            code, retryable = "openrouter_model_unavailable", False
        elif status_code == 429 or status_code >= 500:
            code, retryable = "openrouter_provider_unavailable", True
        else:
            code, retryable = "openrouter_model_preflight_rejected", False
        raise AppError(
            code=code,
            message="OpenRouter model metadata preflight failed",
            cause=exc,
            retryable=retryable,
            context={
                "provider": "openrouter",
                "model": model,
                "status_code": status_code,
            },
        ) from exc
    except (TimeoutError, URLError, OSError) as exc:
        raise AppError(
            code="openrouter_provider_unavailable",
            message="OpenRouter model metadata preflight could not reach the provider",
            cause=exc,
            retryable=True,
            context={"provider": "openrouter", "model": model},
        ) from exc

    if len(raw_response) > _MAX_MODEL_RESPONSE_BYTES:
        raise AppError(
            code="openrouter_model_response_too_large",
            message="OpenRouter model metadata response exceeded the preflight size limit",
            retryable=True,
            context={"provider": "openrouter", "model": model},
        )
    try:
        payload = json.loads(raw_response.decode("utf-8"))
        data = payload.get("data") if isinstance(payload, dict) else None
        observed_model = (
            str(data.get("id") or data.get("canonical_slug") or "").strip()
            if isinstance(data, dict)
            else ""
        )
    except (UnicodeDecodeError, json.JSONDecodeError, AttributeError, TypeError) as exc:
        raise AppError(
            code="openrouter_model_response_invalid",
            message="OpenRouter model metadata response was invalid",
            cause=exc,
            retryable=True,
            context={"provider": "openrouter", "model": model},
        ) from exc

    if observed_model != model:
        raise AppError(
            code="openrouter_model_mismatch",
            message="OpenRouter returned metadata for a different model",
            retryable=False,
            context={"provider": "openrouter", "model": model},
        )

    result = OpenRouterModelPreflightResponse(
        schema_version="1.0", model=model, accessible=True, provider_calls=1
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_model_preflight_complete",
            module=logger.name,
            fields={
                "provider": "openrouter",
                "model": result.model,
                "accessible": result.accessible,
                "provider_calls": result.provider_calls,
            },
        )
    )
    return result
