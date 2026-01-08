from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict

import openai as openai_legacy
try:
    from openai import OpenAI
except Exception:  # pragma: no cover - compatibility fallback
    OpenAI = None  # type: ignore[assignment]

from src.contracts.costs import CostLedgerAppendRequest, CostLedgerEntry, CostRollupRequest
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.openai import (
    OpenAIAnalyzeRequest,
    OpenAIAnalyzeResponse,
    OpenAIResponseRequest,
    OpenAIResponseResult,
)
from src.contracts.run_context import RunContext
from src.services.cost_ledger_service import append_entry as append_cost_entry, rollup_daily
from src.utils.costing import estimate_cost_usd
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.openai_service")

REQUIRED_KEYS = ("tldr", "title", "insights", "quote", "figure", "commentary", "source", "publisher", "taxonomy", "region", "time_period")


def _validate_payload(data: dict) -> None:
    for k in REQUIRED_KEYS:
        if k not in data:
            raise ValueError(f"Missing key in JSON: {k}")
    if not isinstance(data.get("title"), str) or not data.get("title", "").strip():
        raise ValueError("`title` is required")
    if not isinstance(data.get("insights"), list) or len(data["insights"]) != 5:
        raise ValueError("`insights` must be a list of exactly 5 items")
    if not isinstance(data.get("taxonomy"), list):
        raise ValueError("`taxonomy` must be a list")
    if "region" not in data:
        raise ValueError("`region` is required")
    if "time_period" not in data:
        raise ValueError("`time_period` is required")


def _legacy_chat_completion(request: OpenAIAnalyzeRequest) -> Dict[str, Any]:
    # Compatibility path for environments where OpenAI client instantiation
    # fails (e.g., unexpected kwargs like proxies in older dependencies).
    openai_legacy.api_key = request.api_key
    if request.timeout_seconds is not None:
        openai_legacy.timeout = request.timeout_seconds
    payload_args = {
        "model": request.model,
        "messages": [
            {"role": "system", "content": request.system_prompt},
            {"role": "user", "content": request.user_prompt},
        ],
        "temperature": request.temperature,
        "seed": request.seed,
    }
    try:
        payload_args["response_format"] = {"type": "json_object"}
        resp = openai_legacy.ChatCompletion.create(**payload_args)
    except TypeError:
        payload_args.pop("response_format", None)
        resp = openai_legacy.ChatCompletion.create(**payload_args)
    payload = resp["choices"][0]["message"]["content"]
    usage = resp.get("usage") or {}
    return {
        "payload": payload,
        "request_id": resp.get("id"),
        "prompt_tokens": usage.get("prompt_tokens"),
        "completion_tokens": usage.get("completion_tokens"),
        "total_tokens": usage.get("total_tokens"),
    }


def analyze_report(request: OpenAIAnalyzeRequest, ctx: RunContext) -> OpenAIAnalyzeResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="openai_analyze_start",
        module=logger.name,
        fields={
            "model": request.model,
            "temperature": request.temperature,
            "seed": request.seed,
            "timeout_seconds": request.timeout_seconds,
            "prompt_system_sha256": request.prompt_system_sha256,
            "prompt_user_sha256": request.prompt_user_sha256,
        },
    ))

    client_kwargs: dict = {"api_key": request.api_key}
    if request.timeout_seconds is not None:
        client_kwargs["timeout"] = request.timeout_seconds
    payload = None
    request_id = None
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None
    tool_calls = request.tool_calls or 0
    cached_tokens = request.cached_input_tokens

    def _do_modern_call() -> None:
        nonlocal payload, request_id, prompt_tokens, completion_tokens, total_tokens
        if OpenAI is None:
            raise TypeError("OpenAI client not available")
        client = OpenAI(**client_kwargs)
        payload_args = {
            "model": request.model,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_prompt},
            ],
            "response_format": {"type": "json_object"},
            "temperature": request.temperature,
        }
        if request.seed is not None:
            payload_args["seed"] = request.seed
        resp = client.chat.completions.create(**payload_args)
        payload = resp.choices[0].message.content
        request_id = getattr(resp, "id", None)
        usage = getattr(resp, "usage", None)
        prompt_tokens = getattr(usage, "prompt_tokens", None) if usage is not None else None
        completion_tokens = getattr(usage, "completion_tokens", None) if usage is not None else None
        total_tokens = getattr(usage, "total_tokens", None) if usage is not None else None

    try:
        _do_modern_call()
    except TypeError:
        legacy = _legacy_chat_completion(request)
        payload = legacy["payload"]
        request_id = legacy.get("request_id")
        prompt_tokens = legacy.get("prompt_tokens")
        completion_tokens = legacy.get("completion_tokens")
        total_tokens = legacy.get("total_tokens")
    except Exception as exc:
        raise AppError(
            code="openai_request_failed",
            message="OpenAI request failed",
            cause=exc,
            retryable=True,
            context={"model": request.model},
        ) from exc

    try:
        data = json.loads(payload)
        _validate_payload(data)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="openai_response_invalid_json",
            message="OpenAI response JSON parsing failed",
            cause=exc,
            retryable=False,
            context={"model": request.model},
        ) from exc
    except ValueError as exc:
        raise AppError(
            code="openai_response_validation_failed",
            message=str(exc),
            cause=exc,
            retryable=False,
            context={"model": request.model},
        ) from exc

    estimated_cost = estimate_cost_usd(
        request.model,
        int(prompt_tokens or 0),
        int(completion_tokens or 0),
        int(tool_calls or 0),
        pricing=request.model_pricing or {},
    )
    try:
        entry = CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            run_id=ctx.run_id,
            task_id=ctx.task_id,
            span_id=ctx.span_id,
            step_name="openai_analyze",
            model=request.model,
            input_tokens=int(prompt_tokens or 0),
            output_tokens=int(completion_tokens or 0),
            cached_input_tokens=int(cached_tokens) if cached_tokens is not None else None,
            tool_calls=int(tool_calls or 0),
            estimated_cost_usd=estimated_cost,
            extra={"request_id": str(request_id) if request_id else None},
        )
        append_cost_entry(
            CostLedgerAppendRequest(schema_version="1.0", path=request.cost_ledger_path, entry=entry),
            ctx,
        )
        rollup_daily(
            CostRollupRequest(schema_version="1.0", ledger_path=request.cost_ledger_path, out_path=request.cost_daily_path),
            ctx,
        )
    except Exception as exc:  # pragma: no cover - ledger failures must not break main flow
        logger.info(log_event(
            ctx,
            role="service",
            event="cost_ledger_write_failed",
            module=logger.name,
            fields={"error": str(exc)},
        ))

    logger.info(log_event(
        ctx,
        role="service",
        event="openai_analyze_complete",
        module=logger.name,
        fields={
            "request_id": request_id or "",
            "prompt_system_sha256": request.prompt_system_sha256,
            "prompt_user_sha256": request.prompt_user_sha256,
            "prompt_tokens": prompt_tokens,
            "completion_tokens": completion_tokens,
            "total_tokens": total_tokens,
        },
    ))

    quote = Quote(
        text=data.get("quote", {}).get("text", ""),
        author=data.get("quote", {}).get("author", "Unknown"),
    )
    figure = Figure(
        title=data.get("figure", {}).get("title", ""),
        evidence=data.get("figure", {}).get("evidence", ""),
    )
    title = (data.get("title") or "").strip()
    publisher = data.get("publisher", "") or ""
    region = data.get("region", "") or ""
    time_period = data.get("time_period", "") or ""
    raw_taxonomy = data.get("taxonomy") or []
    taxonomy = []
    if isinstance(raw_taxonomy, list):
        taxonomy = [str(item).strip() for item in raw_taxonomy if str(item).strip()]
    insights = data.get("insights", [])
    if len(insights) < 5:
        insights = insights + [""] * (5 - len(insights))
    insights = insights[:5]

    result = ReportPayload(
        tldr=data.get("tldr", ""),
        title=title,
        insights=insights,
        quote=quote,
        figure=figure,
        publisher=publisher,
        taxonomy=taxonomy,
        region=region,
        time_period=time_period,
        commentary=data.get("commentary", ""),
        source=data.get("source", ""),
        _openai_file_id="",
    )

    return OpenAIAnalyzeResponse(
        schema_version="1.0",
        payload=result,
        prompt_system_sha256=request.prompt_system_sha256,
        prompt_user_sha256=request.prompt_user_sha256,
        model=request.model,
        temperature=request.temperature,
        raw_content=payload,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        request_id=str(request_id) if request_id else None,
    )


def openai_respond_with_vector_store(request: OpenAIResponseRequest, ctx: RunContext) -> OpenAIResponseResult:
    logger.info(log_event(
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
    ))
    if not request.vector_store_id:
        raise AppError(
            code="vector_store_missing",
            message="vector_store_id is required for file search responses",
            retryable=False,
        )
    client_kwargs: dict = {"api_key": request.api_key}
    if request.timeout_seconds is not None:
        client_kwargs["timeout"] = request.timeout_seconds
    client = OpenAI(**client_kwargs)
    user_prompt = request.user_prompt
    if "json" not in user_prompt.lower():
        user_prompt = f"{user_prompt}\n\nReturn a JSON object."
    payload_args = {
        "model": request.model,
        "instructions": request.system_prompt,
        "input": [{"role": "user", "content": user_prompt}],
        "temperature": request.temperature,
        "text": {"format": {"type": "json_object"}},
        "tools": [{"type": "file_search", "vector_store_ids": [request.vector_store_id]}],
    }
    if request.seed is not None:
        payload_args["seed"] = request.seed
    try:
        resp = client.responses.create(**payload_args)
    except Exception as exc:
        raise AppError(
            code="openai_response_failed",
            message="OpenAI responses request failed",
            cause=exc,
            retryable=True,
            context={"model": request.model},
        ) from exc

    text = getattr(resp, "output_text", None)
    if text is None:
        output = getattr(resp, "output", None) or getattr(resp, "choices", None) or getattr(resp, "data", None)
        if output and isinstance(output, list):
            first = output[0]
            content = getattr(first, "content", None) or (first.get("content") if isinstance(first, dict) else None)
            if content and isinstance(content, list):
                maybe_text = getattr(content[0], "text", None) or (content[0].get("text") if isinstance(content[0], dict) else None)
                if maybe_text:
                    text = maybe_text
    if text is None:
        text = getattr(resp, "text", "") or ""

    usage = getattr(resp, "usage", None) or {}
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
    tool_calls = 0
    if isinstance(usage, dict):
        tool_calls = usage.get("total_tool_calls") or usage.get("tool_calls") or 0
    parsed_json = None
    if text:
        try:
            parsed_json = json.loads(text)
        except json.JSONDecodeError:
            parsed_json = None

    estimated_cost = estimate_cost_usd(
        request.model,
        int(input_tokens or 0),
        int(output_tokens or 0),
        int(tool_calls or 0),
        pricing=request.model_pricing or {},
    )
    try:
        entry = CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
            run_id=ctx.run_id,
            task_id=ctx.task_id,
            span_id=ctx.span_id,
            step_name="openai_response_vector_store",
            model=request.model,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            cached_input_tokens=None,
            tool_calls=int(tool_calls or 0),
            estimated_cost_usd=estimated_cost,
            extra={},
        )
        append_cost_entry(
            CostLedgerAppendRequest(schema_version="1.0", path=request.cost_ledger_path, entry=entry),
            ctx,
        )
        rollup_daily(
            CostRollupRequest(schema_version="1.0", ledger_path=request.cost_ledger_path, out_path=request.cost_daily_path),
            ctx,
        )
    except Exception as exc:  # pragma: no cover
        logger.info(log_event(
            ctx,
            role="service",
            event="cost_ledger_write_failed",
            module=logger.name,
            fields={"error": str(exc)},
        ))

    logger.info(log_event(
        ctx,
        role="service",
        event="openai_response_complete",
        module=logger.name,
        fields={
            "model": request.model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "tool_calls": tool_calls,
        },
    ))
    return OpenAIResponseResult(
        schema_version="1.0",
        text=text,
        parsed_json=parsed_json if isinstance(parsed_json, dict) else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_calls=tool_calls,
        model=request.model,
    )
