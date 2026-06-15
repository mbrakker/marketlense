from __future__ import annotations

from typing import Any, Callable

from src.contracts.run_context import RunContext
from src.services._llm_service.policy import logger
from src.utils.errors import AppError
from src.utils.logging import log_event


def build_openrouter_client(
    *,
    settings: Any,
    ctx: RunContext,
    client_factory: Callable[..., Any],
) -> Any:
    api_key = str(getattr(settings, "openrouter_api_key", "") or "").strip()
    model = str(getattr(settings, "model", "") or "").strip()
    if not api_key:
        raise AppError(
            code="openrouter_missing_api_key",
            message="OPENROUTER_API_KEY is required",
            retryable=False,
            context={"model": model},
        )
    fields = {
        "provider": "openrouter",
        "model": model,
        "http_referer_present": bool(
            str(getattr(settings, "openrouter_http_referer", "") or "").strip()
        ),
        "temperature": getattr(settings, "temperature", None),
        "timeout_seconds": getattr(settings, "timeout_seconds", None),
        "max_retries": 0,
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_openrouter_client_start",
            module=logger.name,
            fields=fields,
        )
    )
    try:
        client = client_factory(
            model=model,
            api_key=api_key,
            http_referer=getattr(settings, "openrouter_http_referer", None),
            temperature=getattr(settings, "temperature", None),
            timeout=getattr(settings, "timeout_seconds", None),
            max_retries=0,
        )
    except (RuntimeError, OSError, TypeError, ValueError) as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="llm_openrouter_client_failed",
                module=logger.name,
                fields={**fields, "error_type": type(exc).__name__},
            )
        )
        raise AppError(
            code="openrouter_client_init_failed",
            message="Failed to initialize OpenRouter client",
            cause=exc,
            retryable=True,
            context={"model": model, "provider_error_type": type(exc).__name__},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_openrouter_client_complete",
            module=logger.name,
            fields=fields,
        )
    )
    return client


__all__ = ["build_openrouter_client"]
