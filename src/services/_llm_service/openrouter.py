from __future__ import annotations

import json
import os
from typing import Any, Callable
from urllib import error as urllib_error
from urllib import request as urllib_request

from src.contracts.openai import (
    OpenAIResponseResult,
    OpenAIUsageAccountingRequest,
    OpenAIUsageAccountingResponse,
    OpenAIUsageOutcomeUpdateRequest,
)
from src.contracts.run_context import RunContext
from src.services import openai_accounting_service
from src.services._llm_service.context_compaction import (
    compact_prompt_request_if_needed,
)
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
    request, _compaction_result = compact_prompt_request_if_needed(
        request=request,
        ctx=ctx,
        operation="openrouter_chat_json",
        logger=logger,
    )
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
    except json.JSONDecodeError as exc:
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
    try:
        text = str(response_payload["choices"][0]["message"]["content"] or "")
    except (KeyError, IndexError, TypeError) as exc:
        result = OpenAIResponseResult(
            schema_version="1.0",
            text="",
            parsed_json=None,
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
            tool_calls=0,
            model=model,
            total_tokens=_optional_int(usage.get("total_tokens")),
            request_id=(
                str(response_payload.get("id") or "")
                if isinstance(response_payload, dict)
                else ""
            )
            or None,
        )
        accounting = _record_openrouter_usage_accounting(
            request=request,
            result=result,
            ctx=ctx,
            parse_status="not_validated",
            schema_validation_status="not_validated",
        )
        _finalize_openrouter_usage_accounting(
            accounting=accounting,
            ctx=ctx,
            parse_status="invalid",
            schema_validation_status="not_validated",
            error_code="openrouter_response_invalid_json",
        )
        raise AppError(
            code="openrouter_response_invalid_json",
            message="OpenRouter response did not contain valid JSON content",
            cause=exc,
            retryable=False,
            context={"model": model},
        ) from exc
    try:
        parsed_json = json.loads(text)
    except json.JSONDecodeError as exc:
        result = OpenAIResponseResult(
            schema_version="1.0",
            text=text,
            parsed_json=None,
            input_tokens=_optional_int(usage.get("prompt_tokens")),
            output_tokens=_optional_int(usage.get("completion_tokens")),
            tool_calls=0,
            model=model,
            total_tokens=_optional_int(usage.get("total_tokens")),
            request_id=str(response_payload.get("id") or "") or None,
        )
        accounting = _record_openrouter_usage_accounting(
            request=request,
            result=result,
            ctx=ctx,
            parse_status="not_validated",
            schema_validation_status="not_validated",
        )
        _finalize_openrouter_usage_accounting(
            accounting=accounting,
            ctx=ctx,
            parse_status="invalid",
            schema_validation_status="not_validated",
            error_code="openrouter_response_invalid_json",
        )
        raise AppError(
            code="openrouter_response_invalid_json",
            message="OpenRouter response did not contain valid JSON content",
            cause=exc,
            retryable=False,
            context={"model": model},
        ) from exc
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
    accounting = _record_openrouter_usage_accounting(
        request=request,
        result=result,
        ctx=ctx,
        parse_status="valid",
        schema_validation_status="not_validated",
    )
    _finalize_openrouter_usage_accounting(
        accounting=accounting,
        ctx=ctx,
        parse_status="valid",
        schema_validation_status="valid",
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


def _record_openrouter_usage_accounting(
    *,
    request: Any,
    result: OpenAIResponseResult,
    ctx: RunContext,
    parse_status: str,
    schema_validation_status: str,
) -> OpenAIUsageAccountingResponse:
    cache_decision = ""
    if hasattr(request, "response_cache_enabled"):
        cache_decision = (
            "enabled"
            if bool(getattr(request, "response_cache_enabled", False))
            else "disabled"
        )
    return openai_accounting_service.record_usage(
        OpenAIUsageAccountingRequest(
            schema_version="1.0",
            step_name="openrouter_chat_json",
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            total_tokens=result.total_tokens,
            cached_input_tokens=None,
            tool_calls=int(result.tool_calls or 0),
            cost_ledger_path=str(
                getattr(request, "cost_ledger_path", "") or "./out/cost-ledger.jsonl"
            ),
            cost_daily_path=str(
                getattr(request, "cost_daily_path", "") or "./out/cost-daily.json"
            ),
            model_pricing=getattr(request, "model_pricing", None) or {},
            request_id=result.request_id,
            provider="openrouter",
            action="openrouter_chat_json",
            usage_db_path=str(
                getattr(request, "usage_db_path", "") or "./state/llm_usage.sqlite"
            ),
            publisher_name=str(
                getattr(request, "publisher_name", "")
                or getattr(request, "publisher", "")
                or ""
            ),
            report_name=str(
                getattr(request, "report_name", "")
                or getattr(request, "report_title", "")
                or getattr(request, "title", "")
                or ""
            ),
            source_url=str(
                getattr(request, "source_url", "")
                or getattr(request, "landing_page_url", "")
                or getattr(request, "url", "")
                or ""
            ),
            prompt_namespace=str(getattr(request, "prompt_namespace", "") or ""),
            prompt_hash=str(
                getattr(request, "prompt_hash", "")
                or getattr(request, "prompt_sha256", "")
                or getattr(request, "prompt_user_sha256", "")
                or ""
            ),
            provider_decision=str(
                getattr(request, "provider_decision", "") or "openrouter_direct"
            ),
            cache_decision=cache_decision,
            temperature=getattr(request, "temperature", None),
            seed=getattr(request, "seed", None),
            timeout_seconds=getattr(request, "timeout_seconds", None),
            parse_status=parse_status,
            schema_validation_status=schema_validation_status,
            extra={
                "http_referer_present": bool(
                    str(getattr(request, "openrouter_http_referer", "") or "").strip()
                    or os.getenv("OPENROUTER_HTTP_REFERER", "").strip()
                ),
                "schema_name": str(getattr(request, "schema_name", "") or ""),
            },
        ),
        ctx,
    )


def _finalize_openrouter_usage_accounting(
    *,
    accounting: OpenAIUsageAccountingResponse,
    ctx: RunContext,
    parse_status: str,
    schema_validation_status: str,
    error_code: str = "",
) -> None:
    if not accounting.usage_db_recorded or not accounting.event_key:
        return
    openai_accounting_service.update_usage_outcome(
        OpenAIUsageOutcomeUpdateRequest(
            schema_version="1.0",
            usage_db_path=accounting.usage_db_path,
            event_key=accounting.event_key,
            parse_status=parse_status,
            schema_validation_status=schema_validation_status,
            error_stage="output_validation" if error_code else "",
            error_code=error_code,
        ),
        ctx,
    )


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
