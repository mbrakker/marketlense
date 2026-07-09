from __future__ import annotations

import json
import os
from urllib import error as urllib_error
from urllib import request as urllib_request
from typing import Any, Callable

from src.contracts.openai import OpenAIResponseResult
from src.contracts.run_context import RunContext
from src.services._llm_service.policy import logger
from src.utils.errors import AppError
from src.utils.logging import log_event


_BROWSER_USE_OPENROUTER_MAX_TOKENS_CAP = 12000
_OPENROUTER_CHAT_COMPLETIONS_URL = "https://openrouter.ai/api/v1/chat/completions"


def _resolve_effective_max_tokens(max_tokens: Any) -> int | None:
    if max_tokens is None:
        return None
    parsed = int(max_tokens)
    if parsed <= 0:
        return None
    return min(parsed, _BROWSER_USE_OPENROUTER_MAX_TOKENS_CAP)


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
    max_tokens = getattr(settings, "max_tokens", None)
    effective_max_tokens = _resolve_effective_max_tokens(max_tokens)
    fields = {
        "provider": "openrouter",
        "model": model,
        "http_referer_present": bool(
            str(getattr(settings, "openrouter_http_referer", "") or "").strip()
        ),
        "temperature": getattr(settings, "temperature", None),
        "timeout_seconds": getattr(settings, "timeout_seconds", None),
        "configured_max_tokens": max_tokens,
        "effective_max_tokens": effective_max_tokens,
        "max_tokens_cap": _BROWSER_USE_OPENROUTER_MAX_TOKENS_CAP,
        "max_retries": 0,
    }
    extra_body = (
        {"max_tokens": effective_max_tokens}
        if effective_max_tokens is not None
        else None
    )
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
            extra_body=extra_body,
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


def openrouter_chat_json(request: Any, ctx: RunContext) -> OpenAIResponseResult:
    api_key = (
        str(getattr(request, "openrouter_api_key", "") or "").strip()
        or os.getenv("OPENROUTER_API_KEY", "").strip()
    )
    if not api_key:
        raise AppError(
            code="openrouter_missing_api_key",
            message="OPENROUTER_API_KEY is required for LLM failover",
            retryable=False,
            context={"model": str(getattr(request, "model", "") or "")},
        )
    model = _openrouter_model(getattr(request, "model", ""))
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": str(getattr(request, "system_prompt", ""))},
            {"role": "user", "content": str(getattr(request, "user_prompt", ""))},
        ],
        "response_format": {"type": "json_object"},
        "temperature": getattr(request, "temperature", None),
    }
    seed = getattr(request, "seed", None)
    if seed is not None:
        payload["seed"] = seed
    wire_payload = json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": (
            str(getattr(request, "openrouter_http_referer", "") or "").strip()
            or os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
            or "https://marketlense.local"
        ),
        "X-Title": "Market Lense",
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openrouter_chat_json_start",
            module=logger.name,
            fields={
                "model": model,
                "timeout_seconds": getattr(request, "timeout_seconds", None),
                "http_referer_present": bool(headers["HTTP-Referer"]),
            },
        )
    )
    http_request = urllib_request.Request(
        _OPENROUTER_CHAT_COMPLETIONS_URL,
        data=wire_payload,
        headers=headers,
        method="POST",
    )
    try:
        with urllib_request.urlopen(
            http_request,
            timeout=float(getattr(request, "timeout_seconds", None) or 60.0),
        ) as response:
            raw_text = response.read().decode("utf-8")
    except (urllib_error.URLError, TimeoutError, OSError) as exc:
        raise AppError(
            code="openrouter_chat_failed",
            message="OpenRouter chat request failed",
            cause=exc,
            retryable=True,
            context={"model": model, "provider_error_type": type(exc).__name__},
        ) from exc
    try:
        response_payload = json.loads(raw_text)
        text = str(response_payload["choices"][0]["message"]["content"] or "")
        parsed_json = json.loads(text)
    except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(
            code="openrouter_response_invalid_json",
            message="OpenRouter response did not contain valid JSON content",
            cause=exc,
            retryable=False,
            context={"model": model},
        ) from exc
    usage_payload = (
        response_payload.get("usage") if isinstance(response_payload, dict) else {}
    )
    usage = usage_payload if isinstance(usage_payload, dict) else {}
    result = OpenAIResponseResult(
        schema_version="1.0",
        text=text,
        parsed_json=parsed_json,
        input_tokens=_optional_int(usage.get("prompt_tokens")),
        output_tokens=_optional_int(usage.get("completion_tokens")),
        tool_calls=0,
        model=model,
        total_tokens=_optional_int(usage.get("total_tokens")),
        request_id=str(response_payload.get("id") or "") or None,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openrouter_chat_json_complete",
            module=logger.name,
            fields={
                "model": model,
                "request_id": result.request_id or "",
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "total_tokens": result.total_tokens,
            },
        )
    )
    return result


def _openrouter_model(value: object) -> str:
    model = str(value or "").strip()
    if not model:
        return "openai/gpt-5-mini"
    if "/" in model:
        return model
    return f"openai/{model}"


def _optional_int(value: object) -> int | None:
    if not isinstance(value, (str, bytes, bytearray, int, float)):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = ["build_openrouter_client", "openrouter_chat_json"]
