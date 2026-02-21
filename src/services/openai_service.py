from __future__ import annotations

import base64
import json
import logging
import mimetypes
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

import openai as openai_legacy

OpenAI: Any | None = None
try:
    from openai import OpenAI as _OpenAI

    OpenAI = _OpenAI
except Exception:  # pragma: no cover - compatibility fallback
    OpenAI = None

from src.contracts.costs import (
    CostLedgerAppendRequest,
    CostLedgerEntry,
    CostRollupRequest,
)
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.openai import (
    OpenAIAnalyzeRequest,
    OpenAIAnalyzeResponse,
    OpenAIJSONImagePromptRequest,
    OpenAIJSONPromptRequest,
    OpenAIResponseRequest,
    OpenAIResponseResult,
    OpenAIVectorStoreAttachFileRequest,
    OpenAIVectorStoreAttachFileResponse,
    OpenAIVectorStoreCreateRequest,
    OpenAIVectorStoreCreateResponse,
    OpenAIVectorStoreFileUploadRequest,
    OpenAIVectorStoreFileUploadResponse,
    OpenAIVectorStoreStatusRequest,
    OpenAIVectorStoreStatusResponse,
    OpenAIVectorStoreUpdateMetadataRequest,
    OpenAIVectorStoreUpdateMetadataResponse,
)
from src.contracts.run_context import RunContext
from src.services.cost_ledger_service import (
    append_entry as append_cost_entry,
    rollup_daily,
)
from src.utils.costing import estimate_cost_usd
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.openai_service")

REQUIRED_KEYS = (
    "tldr",
    "title",
    "insights",
    "quote",
    "figure",
    "commentary",
    "source",
    "publisher",
    "taxonomy",
    "region",
    "time_period",
)


def _image_path_to_data_url(path: str) -> str:
    img_path = Path(path)
    try:
        raw = img_path.read_bytes()
    except FileNotFoundError as exc:
        raise AppError(
            code="image_not_found",
            message=f"Image not found: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    except Exception as exc:
        raise AppError(
            code="image_read_failed",
            message=f"Failed to read image: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/png"
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


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


def _extract_unsupported_parameter(exc: Exception) -> str | None:
    message = str(exc)
    match = re.search(r"Unsupported parameter:\s*'([^']+)'", message)
    if match:
        return str(match.group(1))
    param = getattr(exc, "param", None)
    if isinstance(param, str) and param.strip():
        return param.strip()
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error_obj = body.get("error")
        if isinstance(error_obj, dict):
            body_param = error_obj.get("param")
            if isinstance(body_param, str) and body_param.strip():
                return body_param.strip()
    return None


def _strip_json_fence(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()
    if len(lines) < 2 or lines[-1].strip() != "```":
        return stripped
    first_line = lines[0].strip().lower()
    if first_line not in {"```", "```json", "```jsonc", "```javascript", "```js"}:
        return stripped
    return "\n".join(lines[1:-1]).strip()


def _extract_json_value(text: str) -> str:
    source = (text or "").strip()
    start = -1
    for idx, ch in enumerate(source):
        if ch in {"{", "["}:
            start = idx
            break
    if start < 0:
        return ""
    stack: list[str] = []
    in_string = False
    escaped = False
    for idx in range(start, len(source)):
        ch = source[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            stack.append("}")
            continue
        if ch == "[":
            stack.append("]")
            continue
        if ch in {"}", "]"}:
            if not stack or ch != stack[-1]:
                return ""
            stack.pop()
            if not stack:
                return source[start : idx + 1]
    return ""


def _parse_json_object_from_text(text: str) -> tuple[dict | None, str]:
    raw = (text or "").strip()
    if not raw:
        return None, "empty"
    candidates: list[tuple[str, str]] = [("direct", raw)]
    stripped = _strip_json_fence(raw)
    if stripped and stripped != raw:
        candidates.append(("fence", stripped))
    for strategy, candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed, strategy
        if parsed is not None:
            return None, "json_non_object"
        extracted = _extract_json_value(candidate)
        if not extracted:
            continue
        try:
            parsed_extracted = json.loads(extracted)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed_extracted, dict):
            return parsed_extracted, f"{strategy}_extracted"
        return None, "json_non_object"
    return None, "invalid_json"


def _responses_create_with_unsupported_param_retry(
    *,
    client: Any,
    payload_args: dict,
    fallback_params: tuple[str, ...],
    ctx: RunContext,
    event_name: str,
    model: str,
) -> Any:
    attempt_args = dict(payload_args)
    while True:
        try:
            return client.responses.create(**attempt_args)
        except Exception as exc:
            unsupported_param = _extract_unsupported_parameter(exc)
            if (
                unsupported_param not in fallback_params
                or unsupported_param not in attempt_args
            ):
                raise
            attempt_args.pop(unsupported_param, None)
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event=event_name,
                    module=logger.name,
                    fields={
                        "model": model,
                        "dropped_param": unsupported_param,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            )


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


def _legacy_chat_json(request: OpenAIJSONPromptRequest) -> Dict[str, Any]:
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


def analyze_report(
    request: OpenAIAnalyzeRequest, ctx: RunContext
) -> OpenAIAnalyzeResponse:
    logger.info(
        log_event(
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
        )
    )

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
        prompt_tokens = (
            getattr(usage, "prompt_tokens", None) if usage is not None else None
        )
        completion_tokens = (
            getattr(usage, "completion_tokens", None) if usage is not None else None
        )
        total_tokens = (
            getattr(usage, "total_tokens", None) if usage is not None else None
        )

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

    payload_text = payload if isinstance(payload, str) else ""
    if not payload_text:
        raise AppError(
            code="openai_response_empty",
            message="OpenAI response payload is empty",
            retryable=False,
            context={"model": request.model},
        )

    try:
        data = json.loads(payload_text)
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
            cached_input_tokens=int(cached_tokens)
            if cached_tokens is not None
            else None,
            tool_calls=int(tool_calls or 0),
            estimated_cost_usd=estimated_cost,
            extra={"request_id": str(request_id) if request_id else None},
        )
        append_cost_entry(
            CostLedgerAppendRequest(
                schema_version="1.0", path=request.cost_ledger_path, entry=entry
            ),
            ctx,
        )
        rollup_daily(
            CostRollupRequest(
                schema_version="1.0",
                ledger_path=request.cost_ledger_path,
                out_path=request.cost_daily_path,
            ),
            ctx,
        )
    except (
        Exception
    ) as exc:  # pragma: no cover - ledger failures must not break main flow
        logger.info(
            log_event(
                ctx,
                role="service",
                event="cost_ledger_write_failed",
                module=logger.name,
                fields={"error": str(exc)},
            )
        )

    logger.info(
        log_event(
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
        )
    )

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
    )

    return OpenAIAnalyzeResponse(
        schema_version="1.0",
        payload=result,
        prompt_system_sha256=request.prompt_system_sha256,
        prompt_user_sha256=request.prompt_user_sha256,
        model=request.model,
        temperature=request.temperature,
        raw_content=payload_text,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        request_id=str(request_id) if request_id else None,
    )


def openai_chat_json(
    request: OpenAIJSONPromptRequest, ctx: RunContext
) -> OpenAIResponseResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_chat_json_start",
            module=logger.name,
            fields={
                "model": request.model,
                "temperature": request.temperature,
                "seed": request.seed,
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    client_kwargs: dict = {"api_key": request.api_key}
    if request.timeout_seconds is not None:
        client_kwargs["timeout"] = request.timeout_seconds
    text = ""
    request_id = None
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None
    tool_calls = 0

    def _do_modern_call() -> None:
        nonlocal text, request_id, prompt_tokens, completion_tokens, total_tokens
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
        text = resp.choices[0].message.content or ""
        request_id = getattr(resp, "id", None)
        usage = getattr(resp, "usage", None)
        prompt_tokens = (
            getattr(usage, "prompt_tokens", None) if usage is not None else None
        )
        completion_tokens = (
            getattr(usage, "completion_tokens", None) if usage is not None else None
        )
        total_tokens = (
            getattr(usage, "total_tokens", None) if usage is not None else None
        )

    try:
        try:
            _do_modern_call()
        except TypeError:
            legacy = _legacy_chat_json(request)
            text = legacy.get("payload") or ""
            request_id = legacy.get("request_id")
            prompt_tokens = legacy.get("prompt_tokens")
            completion_tokens = legacy.get("completion_tokens")
            total_tokens = legacy.get("total_tokens")
    except Exception as exc:
        raise AppError(
            code="openai_chat_failed",
            message="OpenAI chat request failed",
            cause=exc,
            retryable=True,
            context={"model": request.model},
        ) from exc

    parsed_json = None
    if text:
        try:
            parsed_json = json.loads(text)
        except json.JSONDecodeError:
            parsed_json = None

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
            step_name="openai_chat_json",
            model=request.model,
            input_tokens=int(prompt_tokens or 0),
            output_tokens=int(completion_tokens or 0),
            cached_input_tokens=None,
            tool_calls=int(tool_calls or 0),
            estimated_cost_usd=estimated_cost,
            extra={"request_id": str(request_id) if request_id else None},
        )
        append_cost_entry(
            CostLedgerAppendRequest(
                schema_version="1.0", path=request.cost_ledger_path, entry=entry
            ),
            ctx,
        )
        rollup_daily(
            CostRollupRequest(
                schema_version="1.0",
                ledger_path=request.cost_ledger_path,
                out_path=request.cost_daily_path,
            ),
            ctx,
        )
    except Exception as exc:  # pragma: no cover
        logger.info(
            log_event(
                ctx,
                role="service",
                event="cost_ledger_write_failed",
                module=logger.name,
                fields={"error": str(exc)},
            )
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_chat_json_complete",
            module=logger.name,
            fields={
                "model": request.model,
                "request_id": request_id or "",
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
                "total_tokens": total_tokens,
                "parsed_json": isinstance(parsed_json, dict),
            },
        )
    )

    return OpenAIResponseResult(
        schema_version="1.0",
        text=text or "",
        parsed_json=parsed_json if isinstance(parsed_json, dict) else None,
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        tool_calls=tool_calls,
        model=request.model,
        total_tokens=total_tokens,
        request_id=str(request_id) if request_id else None,
    )


def openai_chat_json_with_images(
    request: OpenAIJSONImagePromptRequest, ctx: RunContext
) -> OpenAIResponseResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_chat_json_with_images_start",
            module=logger.name,
            fields={
                "model": request.model,
                "temperature": request.temperature,
                "seed": request.seed,
                "timeout_seconds": request.timeout_seconds,
                "image_count": len(request.image_paths or []),
            },
        )
    )
    if not request.image_paths:
        raise AppError(
            code="openai_images_missing",
            message="openai_chat_json_with_images requires at least one image path",
            retryable=False,
        )
    image_urls = [_image_path_to_data_url(path) for path in request.image_paths]
    client_kwargs: dict = {"api_key": request.api_key}
    if request.timeout_seconds is not None:
        client_kwargs["timeout"] = request.timeout_seconds
    try:
        if OpenAI is None:
            raise TypeError("OpenAI client not available")
        client = OpenAI(**client_kwargs)
        user_content = [{"type": "input_text", "text": request.user_prompt}]
        user_content.extend(
            {"type": "input_image", "image_url": image_url} for image_url in image_urls
        )
        payload_args = {
            "model": request.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": request.system_prompt}],
                },
                {"role": "user", "content": user_content},
            ],
        }
        if request.temperature is not None:
            payload_args["temperature"] = request.temperature
        if request.seed is not None:
            payload_args["seed"] = request.seed
        resp = _responses_create_with_unsupported_param_retry(
            client=client,
            payload_args=payload_args,
            fallback_params=("temperature", "seed"),
            ctx=ctx,
            event_name="openai_chat_json_with_images_retry_without_param",
            model=request.model,
        )
    except TypeError as exc:
        raise AppError(
            code="openai_client_unavailable",
            message="OpenAI client not available",
            cause=exc,
            retryable=False,
            context={"model": request.model},
        ) from exc
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="openai_chat_json_with_images_error",
                module=logger.name,
                fields={
                    "model": request.model,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
            )
        )
        raise AppError(
            code="openai_chat_images_failed",
            message="OpenAI JSON+images request failed",
            cause=exc,
            retryable=True,
            context={"model": request.model},
        ) from exc

    text = getattr(resp, "output_text", "") or ""
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
    request_id = getattr(resp, "id", None)
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
            step_name="openai_chat_json_with_images",
            model=request.model,
            input_tokens=int(input_tokens or 0),
            output_tokens=int(output_tokens or 0),
            cached_input_tokens=None,
            tool_calls=int(tool_calls or 0),
            estimated_cost_usd=estimated_cost,
            extra={"request_id": str(request_id) if request_id else None},
        )
        append_cost_entry(
            CostLedgerAppendRequest(
                schema_version="1.0", path=request.cost_ledger_path, entry=entry
            ),
            ctx,
        )
        rollup_daily(
            CostRollupRequest(
                schema_version="1.0",
                ledger_path=request.cost_ledger_path,
                out_path=request.cost_daily_path,
            ),
            ctx,
        )
    except Exception as exc:  # pragma: no cover
        logger.info(
            log_event(
                ctx,
                role="service",
                event="cost_ledger_write_failed",
                module=logger.name,
                fields={"error": str(exc)},
            )
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_chat_json_with_images_complete",
            module=logger.name,
            fields={
                "model": request.model,
                "request_id": request_id or "",
                "image_count": len(request.image_paths or []),
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tool_calls": tool_calls,
                "parsed_json": isinstance(parsed_json, dict),
            },
        )
    )
    return OpenAIResponseResult(
        schema_version="1.0",
        text=text,
        parsed_json=parsed_json if isinstance(parsed_json, dict) else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_calls=tool_calls,
        model=request.model,
        total_tokens=(int(input_tokens or 0) + int(output_tokens or 0)),
        request_id=str(request_id) if request_id else None,
    )


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
    client_kwargs: dict = {"api_key": request.api_key}
    if request.timeout_seconds is not None:
        client_kwargs["timeout"] = request.timeout_seconds
    user_prompt = request.user_prompt
    if "json" not in user_prompt.lower():
        user_prompt = f"{user_prompt}\n\nReturn a JSON object."
    payload_args = {
        "model": request.model,
        "instructions": request.system_prompt,
        "input": [{"role": "user", "content": user_prompt}],
        "temperature": request.temperature,
        "tools": [
            {"type": "file_search", "vector_store_ids": [request.vector_store_id]}
        ],
    }
    if request.seed is not None:
        payload_args["seed"] = request.seed
    try:
        if OpenAI is None:
            raise TypeError("OpenAI client not available")
        client = OpenAI(**client_kwargs)
        resp = client.responses.create(**payload_args)
    except TypeError as exc:
        raise AppError(
            code="openai_client_unavailable",
            message="OpenAI client not available",
            cause=exc,
            retryable=False,
            context={"model": request.model},
        ) from exc
    except Exception as exc:
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
            code="openai_response_failed",
            message="OpenAI responses request failed",
            cause=exc,
            retryable=True,
            context={
                "model": request.model,
                "vector_store_id": request.vector_store_id,
                "error": str(exc),
            },
        ) from exc

    text = getattr(resp, "output_text", None)
    if text is None:
        output = (
            getattr(resp, "output", None)
            or getattr(resp, "choices", None)
            or getattr(resp, "data", None)
        )
        if output and isinstance(output, list):
            first = output[0]
            content = getattr(first, "content", None) or (
                first.get("content") if isinstance(first, dict) else None
            )
            if content and isinstance(content, list):
                maybe_text = getattr(content[0], "text", None) or (
                    content[0].get("text") if isinstance(content[0], dict) else None
                )
                if maybe_text:
                    text = maybe_text
    if text is None:
        text = getattr(resp, "text", "") or ""

    request_id = getattr(resp, "id", None)
    usage = getattr(resp, "usage", None) or {}
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
    tool_calls = 0
    if isinstance(usage, dict):
        tool_calls = usage.get("total_tool_calls") or usage.get("tool_calls") or 0
    parsed_json, parse_strategy = _parse_json_object_from_text(text)
    parse_error_code = ""
    parse_error_message = ""
    if parsed_json is None:
        if parse_strategy == "empty":
            parse_error_code = "openai_response_empty"
            parse_error_message = "OpenAI response from vector store is empty"
        elif parse_strategy == "json_non_object":
            parse_error_code = "openai_response_json_type_invalid"
            parse_error_message = "OpenAI response JSON must be an object"
        else:
            parse_error_code = "openai_response_invalid_json"
            parse_error_message = "OpenAI response is not valid JSON"

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
            extra={"request_id": str(request_id) if request_id else None},
        )
        append_cost_entry(
            CostLedgerAppendRequest(
                schema_version="1.0", path=request.cost_ledger_path, entry=entry
            ),
            ctx,
        )
        rollup_daily(
            CostRollupRequest(
                schema_version="1.0",
                ledger_path=request.cost_ledger_path,
                out_path=request.cost_daily_path,
            ),
            ctx,
        )
    except Exception as exc:  # pragma: no cover
        logger.info(
            log_event(
                ctx,
                role="service",
                event="cost_ledger_write_failed",
                module=logger.name,
                fields={"error": str(exc)},
            )
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_response_complete",
            module=logger.name,
            fields={
                "model": request.model,
                "request_id": request_id or "",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tool_calls": tool_calls,
                "parsed_json": parsed_json is not None,
                "parse_strategy": parse_strategy,
                "parse_error_code": parse_error_code,
            },
        )
    )
    if parse_error_code:
        raise AppError(
            code=parse_error_code,
            message=parse_error_message,
            retryable=False,
            context={
                "model": request.model,
                "vector_store_id": request.vector_store_id,
                "parse_strategy": parse_strategy,
                "response_text_preview": text[:240],
            },
        )
    return OpenAIResponseResult(
        schema_version="1.0",
        text=text,
        parsed_json=parsed_json if isinstance(parsed_json, dict) else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_calls=tool_calls,
        model=request.model,
        total_tokens=(int(input_tokens or 0) + int(output_tokens or 0)),
        request_id=str(request_id) if request_id else None,
    )


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
        if OpenAI is None:
            raise TypeError("OpenAI client not available")
        return OpenAI(**client_kwargs)
    except TypeError as exc:
        raise AppError(
            code="openai_client_unavailable",
            message="OpenAI client not available",
            cause=exc,
            retryable=False,
            context={"operation": operation},
        ) from exc
    except Exception as exc:
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


def openai_vector_store_create(
    request: OpenAIVectorStoreCreateRequest, ctx: RunContext
) -> OpenAIVectorStoreCreateResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_vector_store_create_start",
            module=logger.name,
            fields={
                "name": request.name,
                "metadata_keys": list((request.metadata or {}).keys()),
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="vector_store_create",
        )
        resp = client.vector_stores.create(
            name=request.name, metadata=request.metadata or {}
        )
        vector_store_id = _require_openai_id(
            resp,
            code="openai_vector_store_create_failed",
            message="OpenAI vector store create did not return an id",
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="openai_vector_store_create_failed",
            message="OpenAI vector store create request failed",
            cause=exc,
            retryable=True,
        ) from exc

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_vector_store_create_complete",
            module=logger.name,
            fields={"name": request.name, "vector_store_id": vector_store_id},
        )
    )
    return OpenAIVectorStoreCreateResponse(
        schema_version="1.0", vector_store_id=vector_store_id
    )


def openai_vector_store_upload_file(
    request: OpenAIVectorStoreFileUploadRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreFileUploadResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_vector_store_upload_start",
            module=logger.name,
            fields={
                "file_path": request.file_path,
                "purpose": request.purpose,
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="vector_store_upload_file",
        )
        with open(request.file_path, "rb") as file_handle:
            resp = client.files.create(file=file_handle, purpose=request.purpose)
        openai_file_id = _require_openai_id(
            resp,
            code="openai_vector_store_upload_failed",
            message="OpenAI file upload did not return an id",
        )
    except FileNotFoundError as exc:
        raise AppError(
            code="openai_file_missing",
            message=f"File not found: {request.file_path}",
            cause=exc,
            retryable=False,
        ) from exc
    except OSError as exc:
        raise AppError(
            code="openai_file_open_failed",
            message=f"Unable to read file: {request.file_path}",
            cause=exc,
            retryable=False,
        ) from exc
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="openai_vector_store_upload_failed",
            message="OpenAI file upload request failed",
            cause=exc,
            retryable=True,
        ) from exc

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_vector_store_upload_complete",
            module=logger.name,
            fields={"file_path": request.file_path, "openai_file_id": openai_file_id},
        )
    )
    return OpenAIVectorStoreFileUploadResponse(
        schema_version="1.0", openai_file_id=openai_file_id
    )


def openai_vector_store_attach_file(
    request: OpenAIVectorStoreAttachFileRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreAttachFileResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_vector_store_attach_start",
            module=logger.name,
            fields={
                "vector_store_id": request.vector_store_id,
                "openai_file_id": request.openai_file_id,
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="vector_store_attach_file",
        )
        resp = client.vector_stores.files.create(
            vector_store_id=request.vector_store_id,
            file_id=request.openai_file_id,
        )
        attached_id = _require_openai_id(
            resp,
            code="openai_vector_store_attach_failed",
            message="OpenAI vector store attach did not return an id",
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="openai_vector_store_attach_failed",
            message="OpenAI vector store attach request failed",
            cause=exc,
            retryable=True,
        ) from exc

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_vector_store_attach_complete",
            module=logger.name,
            fields={
                "vector_store_id": request.vector_store_id,
                "openai_file_id": attached_id,
            },
        )
    )
    return OpenAIVectorStoreAttachFileResponse(
        schema_version="1.0",
        vector_store_id=request.vector_store_id,
        openai_file_id=attached_id,
    )


def openai_vector_store_status(
    request: OpenAIVectorStoreStatusRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreStatusResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_vector_store_status_start",
            module=logger.name,
            fields={
                "vector_store_id": request.vector_store_id,
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="vector_store_status",
        )
        resp = client.vector_stores.retrieve(request.vector_store_id)
        status = _value_from_response(resp, "status")
        indexed_at = _value_from_response(resp, "created_at")
        last_error = _value_from_response(resp, "last_error")
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="openai_vector_store_status_failed",
            message="OpenAI vector store status request failed",
            cause=exc,
            retryable=True,
            context={"vector_store_id": request.vector_store_id},
        ) from exc

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_vector_store_status_complete",
            module=logger.name,
            fields={"vector_store_id": request.vector_store_id, "status": status},
        )
    )
    return OpenAIVectorStoreStatusResponse(
        schema_version="1.0",
        vector_store_id=request.vector_store_id,
        status=str(status or ""),
        indexed_at_utc=str(indexed_at) if indexed_at is not None else None,
        last_error=str(last_error) if last_error else None,
    )


def openai_vector_store_update_metadata(
    request: OpenAIVectorStoreUpdateMetadataRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreUpdateMetadataResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_vector_store_update_metadata_start",
            module=logger.name,
            fields={
                "vector_store_id": request.vector_store_id,
                "metadata_keys": list((request.metadata or {}).keys()),
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="vector_store_update_metadata",
        )
        resp = client.vector_stores.update(
            vector_store_id=request.vector_store_id,
            metadata=request.metadata or {},
        )
        updated_id = _require_openai_id(
            resp,
            code="openai_vector_store_update_metadata_failed",
            message="OpenAI vector store metadata update did not return an id",
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="openai_vector_store_update_metadata_failed",
            message="OpenAI vector store metadata update request failed",
            cause=exc,
            retryable=True,
            context={"vector_store_id": request.vector_store_id},
        ) from exc

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_vector_store_update_metadata_complete",
            module=logger.name,
            fields={"vector_store_id": updated_id},
        )
    )
    return OpenAIVectorStoreUpdateMetadataResponse(
        schema_version="1.0", vector_store_id=updated_id
    )
