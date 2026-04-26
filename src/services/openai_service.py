from __future__ import annotations

import base64
import hashlib
import json
import logging
import mimetypes
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import openai as openai_legacy

from src.contracts.openai import (
    OpenAIAnalyzeRequest,
    OpenAIAnalyzeResponse,
    OpenAIJSONImagePromptRequest,
    OpenAIJSONPromptRequest,
    OpenAIPdfOcrRequest,
    OpenAIPdfOcrResponse,
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
    OpenAIUsageAccountingRequest,
)
from src.contracts.files import WriteBytesRequest
from src.contracts.pdf_ocr import PdfOcrPageText
from src.contracts.report_models import Figure, Quote, ReportPayload
from src.contracts.run_context import RunContext
from src.services import file_service, openai_accounting_service
from src.utils.errors import AppError
from src.utils.json_recovery import parse_json_from_text, strip_json_fence
from src.utils.logging import log_event

OpenAI: Any | None = None
try:
    from openai import OpenAI as _OpenAI

    OpenAI = _OpenAI
except ImportError:  # pragma: no cover - compatibility fallback
    OpenAI = None

logger = logging.getLogger("market_lense.openai_service")
SEMANTIC_RESPONSE_CACHE_SCHEMA_VERSION = "1.0"
SEMANTIC_RESPONSE_CACHE_SUBDIR = "semantic_responses"
OPENAI_ERROR_TYPES: tuple[type[Exception], ...] = tuple(
    error_type
    for error_type in (
        getattr(openai_legacy, "OpenAIError", None),
        getattr(openai_legacy, "APIError", None),
        getattr(openai_legacy, "APIConnectionError", None),
        getattr(openai_legacy, "APIStatusError", None),
        getattr(openai_legacy, "APITimeoutError", None),
        getattr(openai_legacy, "RateLimitError", None),
        getattr(openai_legacy, "InternalServerError", None),
        getattr(openai_legacy, "BadRequestError", None),
        getattr(openai_legacy, "AuthenticationError", None),
    )
    if isinstance(error_type, type) and issubclass(error_type, Exception)
)
OPENAI_REQUEST_EXCEPTIONS: tuple[type[Exception], ...] = OPENAI_ERROR_TYPES + (
    RuntimeError,
    OSError,
    ValueError,
    TypeError,
    AttributeError,
)
OPENAI_CLIENT_INIT_EXCEPTIONS: tuple[type[Exception], ...] = OPENAI_ERROR_TYPES + (
    OSError,
    ValueError,
)
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

_RESPONSES_IMAGE_UNSUPPORTED_PARAM_PREFIXES: dict[str, tuple[str, ...]] = {
    # GPT-5 image calls via Responses API reject temperature/seed.
    "gpt-5": ("temperature", "seed"),
}
OPENAI_OCR_RESPONSE_FORMAT = {
    "type": "json_schema",
    "name": "pdf_ocr_pages",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "pages": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "page_number": {"type": "integer"},
                        "text": {"type": "string"},
                    },
                    "required": ["page_number", "text"],
                },
            }
        },
        "required": ["pages"],
    },
}


@dataclass(frozen=True)
class _SemanticResponseCacheSpec:
    operation: str
    key: str
    path: Path
    prompt_hash: str
    context_hash: str
    params_hash: str
    ttl_seconds: float | None


@dataclass(frozen=True)
class _VectorStoreOperationSpec:
    operation: str
    start_event: str
    complete_event: str
    error_code: str
    error_message: str


_VECTOR_STORE_CREATE_OPERATION = _VectorStoreOperationSpec(
    operation="vector_store_create",
    start_event="openai_vector_store_create_start",
    complete_event="openai_vector_store_create_complete",
    error_code="openai_vector_store_create_failed",
    error_message="OpenAI vector store create request failed",
)
_VECTOR_STORE_UPLOAD_OPERATION = _VectorStoreOperationSpec(
    operation="vector_store_upload_file",
    start_event="openai_vector_store_upload_start",
    complete_event="openai_vector_store_upload_complete",
    error_code="openai_vector_store_upload_failed",
    error_message="OpenAI file upload request failed",
)
_VECTOR_STORE_ATTACH_OPERATION = _VectorStoreOperationSpec(
    operation="vector_store_attach_file",
    start_event="openai_vector_store_attach_start",
    complete_event="openai_vector_store_attach_complete",
    error_code="openai_vector_store_attach_failed",
    error_message="OpenAI vector store attach request failed",
)
_VECTOR_STORE_STATUS_OPERATION = _VectorStoreOperationSpec(
    operation="vector_store_status",
    start_event="openai_vector_store_status_start",
    complete_event="openai_vector_store_status_complete",
    error_code="openai_vector_store_status_failed",
    error_message="OpenAI vector store status request failed",
)
_VECTOR_STORE_UPDATE_METADATA_OPERATION = _VectorStoreOperationSpec(
    operation="vector_store_update_metadata",
    start_event="openai_vector_store_update_metadata_start",
    complete_event="openai_vector_store_update_metadata_complete",
    error_code="openai_vector_store_update_metadata_failed",
    error_message="OpenAI vector store metadata update request failed",
)


def _stable_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=True, separators=(",", ":"))


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_payload(payload: dict[str, Any]) -> str:
    return _sha256_text(_stable_json(payload))


def _file_fingerprint(path: str, *, content_hash: bool) -> dict[str, Any]:
    normalized = str(path or "").strip()
    payload: dict[str, Any] = {"path": normalized}
    if not normalized:
        return payload
    file_path = Path(normalized)
    try:
        stat = file_path.stat()
    except OSError as exc:
        payload["error"] = type(exc).__name__
        return payload
    payload["size_bytes"] = int(stat.st_size)
    if content_hash:
        try:
            payload["sha256"] = hashlib.sha256(file_path.read_bytes()).hexdigest()
        except OSError as exc:
            payload["error"] = type(exc).__name__
    else:
        payload["mtime_ns"] = int(stat.st_mtime_ns)
    return payload


def _semantic_response_cache_spec(
    request: Any,
    *,
    operation: str,
    params: dict[str, Any],
    context: dict[str, Any] | None = None,
) -> _SemanticResponseCacheSpec | None:
    if not bool(getattr(request, "response_cache_enabled", False)):
        return None
    cache_dir = str(getattr(request, "response_cache_dir", "") or "").strip()
    if not cache_dir:
        return None
    prompt_hash = _sha256_payload(
        {
            "schema_version": SEMANTIC_RESPONSE_CACHE_SCHEMA_VERSION,
            "system_prompt": str(getattr(request, "system_prompt", "") or ""),
        }
    )
    context_hash = _sha256_payload(
        {
            "schema_version": SEMANTIC_RESPONSE_CACHE_SCHEMA_VERSION,
            "user_prompt": str(getattr(request, "user_prompt", "") or ""),
            "context": context or {},
        }
    )
    params_payload = {
        "schema_version": SEMANTIC_RESPONSE_CACHE_SCHEMA_VERSION,
        "operation": operation,
        **params,
    }
    params_hash = _sha256_payload(params_payload)
    key = _sha256_payload(
        {
            "schema_version": SEMANTIC_RESPONSE_CACHE_SCHEMA_VERSION,
            "operation": operation,
            "prompt_hash": prompt_hash,
            "context_hash": context_hash,
            "params": params_payload,
        }
    )
    ttl_raw = getattr(request, "response_cache_ttl_seconds", 604800.0)
    ttl_seconds = None if ttl_raw is None else max(0.0, float(ttl_raw))
    cache_path = (
        Path(cache_dir) / SEMANTIC_RESPONSE_CACHE_SUBDIR / operation / f"{key}.json"
    )
    return _SemanticResponseCacheSpec(
        operation=operation,
        key=key,
        path=cache_path,
        prompt_hash=prompt_hash,
        context_hash=context_hash,
        params_hash=params_hash,
        ttl_seconds=ttl_seconds,
    )


def _log_semantic_cache_event(
    ctx: RunContext,
    *,
    event: str,
    spec: _SemanticResponseCacheSpec,
    fields: dict[str, Any] | None = None,
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields={
                "operation": spec.operation,
                "cache_key": spec.key,
                "cache_path": str(spec.path),
                "prompt_hash": spec.prompt_hash,
                "context_hash": spec.context_hash,
                "params_hash": spec.params_hash,
                **(fields or {}),
            },
        )
    )


def _read_semantic_response_cache(
    spec: _SemanticResponseCacheSpec,
    ctx: RunContext,
) -> dict[str, Any] | None:
    try:
        raw = spec.path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except FileNotFoundError:
        _log_semantic_cache_event(
            ctx,
            event="openai_semantic_cache_miss",
            spec=spec,
            fields={"reason": "missing"},
        )
        return None
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        _log_semantic_cache_event(
            ctx,
            event="openai_semantic_cache_miss",
            spec=spec,
            fields={"reason": "read_failed", "error_type": type(exc).__name__},
        )
        return None
    if not isinstance(payload, dict):
        _log_semantic_cache_event(
            ctx,
            event="openai_semantic_cache_miss",
            spec=spec,
            fields={"reason": "invalid_payload"},
        )
        return None
    metadata = payload.get("_cache")
    if not isinstance(metadata, dict) or metadata.get("key") != spec.key:
        _log_semantic_cache_event(
            ctx,
            event="openai_semantic_cache_miss",
            spec=spec,
            fields={"reason": "key_mismatch"},
        )
        return None
    cached_at = float(metadata.get("cached_at_epoch", 0.0) or 0.0)
    if spec.ttl_seconds is not None and spec.ttl_seconds >= 0.0:
        age_seconds = max(0.0, time.time() - cached_at)
        if age_seconds > spec.ttl_seconds:
            _log_semantic_cache_event(
                ctx,
                event="openai_semantic_cache_miss",
                spec=spec,
                fields={"reason": "expired", "age_seconds": round(age_seconds, 3)},
            )
            return None
    response_payload = payload.get("response")
    if not isinstance(response_payload, dict):
        _log_semantic_cache_event(
            ctx,
            event="openai_semantic_cache_miss",
            spec=spec,
            fields={"reason": "missing_response"},
        )
        return None
    _log_semantic_cache_event(ctx, event="openai_semantic_cache_hit", spec=spec)
    return response_payload


def _write_semantic_response_cache(
    spec: _SemanticResponseCacheSpec | None,
    ctx: RunContext,
    *,
    response_payload: dict[str, Any],
) -> None:
    if spec is None:
        return
    payload = {
        "schema_version": SEMANTIC_RESPONSE_CACHE_SCHEMA_VERSION,
        "_cache": {
            "schema_version": SEMANTIC_RESPONSE_CACHE_SCHEMA_VERSION,
            "key": spec.key,
            "operation": spec.operation,
            "prompt_hash": spec.prompt_hash,
            "context_hash": spec.context_hash,
            "params_hash": spec.params_hash,
            "ttl_seconds": spec.ttl_seconds,
            "cached_at_utc": datetime.now(timezone.utc).isoformat(),
            "cached_at_epoch": time.time(),
        },
        "response": response_payload,
    }
    try:
        file_service.write_bytes(
            WriteBytesRequest(
                schema_version="1.0",
                path=str(spec.path),
                content=json.dumps(
                    payload, sort_keys=True, ensure_ascii=True, indent=2
                ).encode("utf-8"),
            ),
            ctx,
        )
    except (AppError, TypeError, ValueError) as exc:
        _log_semantic_cache_event(
            ctx,
            event="openai_semantic_cache_write_failed",
            spec=spec,
            fields={"error_type": type(exc).__name__, "error": str(exc)},
        )
        return
    _log_semantic_cache_event(ctx, event="openai_semantic_cache_write", spec=spec)


def _openai_response_result_from_cache(payload: dict[str, Any]) -> OpenAIResponseResult:
    return OpenAIResponseResult(
        schema_version=str(payload.get("schema_version") or "1.0"),
        text=str(payload.get("text") or ""),
        parsed_json=payload.get("parsed_json")
        if isinstance(payload.get("parsed_json"), dict)
        else None,
        input_tokens=int(payload["input_tokens"])
        if payload.get("input_tokens") is not None
        else None,
        output_tokens=int(payload["output_tokens"])
        if payload.get("output_tokens") is not None
        else None,
        tool_calls=int(payload["tool_calls"])
        if payload.get("tool_calls") is not None
        else None,
        model=str(payload.get("model") or ""),
        total_tokens=int(payload["total_tokens"])
        if payload.get("total_tokens") is not None
        else None,
        request_id=str(payload.get("request_id"))
        if payload.get("request_id")
        else None,
    )


def _ocr_response_from_cache(payload: dict[str, Any]) -> OpenAIPdfOcrResponse:
    raw_pages_value = payload.get("pages")
    raw_pages: list[Any] = raw_pages_value if isinstance(raw_pages_value, list) else []
    pages = [
        PdfOcrPageText(
            schema_version=str(item.get("schema_version") or "1.0"),
            page_number=int(item.get("page_number") or 0),
            text=str(item.get("text") or ""),
        )
        for item in raw_pages
        if isinstance(item, dict)
    ]
    return OpenAIPdfOcrResponse(
        schema_version=str(payload.get("schema_version") or "1.0"),
        pages=pages,
        raw_text=str(payload.get("raw_text") or ""),
        model=str(payload.get("model") or ""),
        input_tokens=int(payload["input_tokens"])
        if payload.get("input_tokens") is not None
        else None,
        output_tokens=int(payload["output_tokens"])
        if payload.get("output_tokens") is not None
        else None,
        tool_calls=int(payload["tool_calls"])
        if payload.get("tool_calls") is not None
        else None,
        request_id=str(payload.get("request_id"))
        if payload.get("request_id")
        else None,
    )


def _bytes_to_data_url(raw: bytes, *, mime: str) -> str:
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{encoded}"


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
    except OSError as exc:
        raise AppError(
            code="image_read_failed",
            message=f"Failed to read image: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    mime, _ = mimetypes.guess_type(path)
    mime = mime or "image/png"
    return _bytes_to_data_url(raw, mime=mime)


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


def _openai_error_status_code(exc: Exception) -> int | None:
    status = getattr(exc, "status_code", None)
    if status is None:
        response = getattr(exc, "response", None)
        status = getattr(response, "status_code", None)
    try:
        return int(status) if status is not None else None
    except (TypeError, ValueError):
        return None


def _openai_error_body_code(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if isinstance(body, dict):
        error_obj = body.get("error")
        if isinstance(error_obj, dict):
            for key in ("code", "type"):
                value = error_obj.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip().lower()
    return ""


def _classify_openai_request_error(
    exc: Exception,
    *,
    default_code: str,
    default_message: str,
) -> tuple[str, str, bool]:
    error_type = type(exc).__name__.lower()
    message = str(exc).lower()
    body_code = _openai_error_body_code(exc)
    combined = " ".join(part for part in (error_type, message, body_code) if part)
    if any(
        token in combined
        for token in (
            "content_filter",
            "content policy",
            "policy_violation",
            "refusal",
            "safety",
            "blocked",
        )
    ):
        return (
            "openai_refusal",
            "OpenAI request was refused or blocked by policy",
            False,
        )
    if "authentication" in error_type or "invalid_api_key" in combined:
        return ("openai_authentication_failed", "OpenAI authentication failed", False)
    status_code = _openai_error_status_code(exc)
    if status_code in {400, 401, 403, 404} or "badrequest" in error_type:
        return ("openai_bad_request", "OpenAI request was rejected permanently", False)
    return (default_code, default_message, True)


def _parse_json_object_from_text(text: str) -> tuple[dict | None, str]:
    parsed, strategy = parse_json_from_text(text, accepted_types=(dict,))
    return parsed if isinstance(parsed, dict) else None, strategy


def _strip_json_fence(text: str) -> str:
    return strip_json_fence(text)


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
        except OPENAI_REQUEST_EXCEPTIONS as exc:
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


def _known_unsupported_image_params(model: str) -> set[str]:
    normalized = str(model or "").strip().lower()
    unsupported: set[str] = set()
    for prefix, params in _RESPONSES_IMAGE_UNSUPPORTED_PARAM_PREFIXES.items():
        if normalized.startswith(prefix):
            unsupported.update(params)
    return unsupported


def _extract_responses_output_text(resp: Any) -> str:
    text = getattr(resp, "output_text", None)
    if isinstance(text, str) and text:
        return text
    output = (
        getattr(resp, "output", None)
        or getattr(resp, "choices", None)
        or getattr(resp, "data", None)
    )
    if isinstance(output, list) and output:
        extracted_blocks: list[str] = []
        for item in output:
            content = getattr(item, "content", None) or (
                item.get("content") if isinstance(item, dict) else None
            )
            if not isinstance(content, list):
                continue
            for block in content:
                maybe_text = getattr(block, "text", None) or (
                    block.get("text") if isinstance(block, dict) else None
                )
                if isinstance(maybe_text, str) and maybe_text:
                    extracted_blocks.append(maybe_text)
        if extracted_blocks:
            return "\n".join(extracted_blocks)
    text = getattr(resp, "text", None)
    return text if isinstance(text, str) else ""


def _extract_responses_usage(
    resp: Any,
) -> tuple[int | None, int | None, int, int | None]:
    usage = getattr(resp, "usage", None) or {}
    input_tokens = getattr(usage, "input_tokens", None) if usage else None
    output_tokens = getattr(usage, "output_tokens", None) if usage else None
    total_tokens = getattr(usage, "total_tokens", None) if usage else None
    tool_calls = 0
    if isinstance(usage, dict):
        input_tokens = usage.get("input_tokens")
        output_tokens = usage.get("output_tokens")
        total_tokens = usage.get("total_tokens")
        tool_calls = usage.get("total_tool_calls") or usage.get("tool_calls") or 0
    return input_tokens, output_tokens, int(tool_calls or 0), total_tokens


@dataclass(frozen=True)
class _OpenAIResponseMetadata:
    text: str
    request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    tool_calls: int
    total_tokens: int | None
    parsed_json: dict | None
    parse_strategy: str


def _parse_response_json(
    text: str, *, recover_json_object: bool
) -> tuple[dict | None, str]:
    if recover_json_object:
        return _parse_json_object_from_text(text)
    if not text:
        return None, "empty"
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None, "invalid_json"
    if not isinstance(parsed, dict):
        return None, "json_non_object"
    return parsed, "json_object"


def _build_response_metadata(
    *,
    text: str,
    request_id: str | None,
    input_tokens: int | None,
    output_tokens: int | None,
    tool_calls: int,
    total_tokens: int | None,
    recover_json_object: bool,
) -> _OpenAIResponseMetadata:
    parsed_json, parse_strategy = _parse_response_json(
        text,
        recover_json_object=recover_json_object,
    )
    resolved_total_tokens = total_tokens
    if resolved_total_tokens is None and (
        input_tokens is not None or output_tokens is not None
    ):
        resolved_total_tokens = int(input_tokens or 0) + int(output_tokens or 0)
    return _OpenAIResponseMetadata(
        text=text,
        request_id=str(request_id) if request_id else None,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_calls=int(tool_calls or 0),
        total_tokens=resolved_total_tokens,
        parsed_json=parsed_json,
        parse_strategy=parse_strategy,
    )


def _adapt_chat_completion_metadata(
    run: _ChatCompletionRun,
) -> _OpenAIResponseMetadata:
    return _build_response_metadata(
        text=run.payload if isinstance(run.payload, str) else "",
        request_id=run.request_id,
        input_tokens=run.prompt_tokens,
        output_tokens=run.completion_tokens,
        tool_calls=0,
        total_tokens=run.total_tokens,
        recover_json_object=False,
    )


def _adapt_responses_metadata(
    resp: Any, *, recover_json_object: bool
) -> _OpenAIResponseMetadata:
    input_tokens, output_tokens, tool_calls, total_tokens = _extract_responses_usage(
        resp
    )
    return _build_response_metadata(
        text=_extract_responses_output_text(resp),
        request_id=getattr(resp, "id", None),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        tool_calls=tool_calls,
        total_tokens=total_tokens,
        recover_json_object=recover_json_object,
    )


def _record_usage_accounting(
    *,
    ctx: RunContext,
    step_name: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    tool_calls: int,
    cost_ledger_path: str,
    cost_daily_path: str,
    model_pricing: dict,
    request_id: str | None,
    cached_input_tokens: int | None = None,
) -> None:
    openai_accounting_service.record_usage(
        OpenAIUsageAccountingRequest(
            schema_version="1.0",
            step_name=step_name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_input_tokens=cached_input_tokens,
            tool_calls=int(tool_calls or 0),
            cost_ledger_path=cost_ledger_path,
            cost_daily_path=cost_daily_path,
            model_pricing=model_pricing or {},
            request_id=request_id,
        ),
        ctx,
    )


def _coerce_pdf_ocr_pages(payload: dict | None) -> list[PdfOcrPageText]:
    if not isinstance(payload, dict):
        return []
    raw_pages = payload.get("pages")
    if not isinstance(raw_pages, list):
        return []
    pages: list[PdfOcrPageText] = []
    seen_numbers: set[int] = set()
    for item in raw_pages:
        if not isinstance(item, dict):
            continue
        try:
            page_number = int(str(item.get("page_number") or "").strip())
        except (TypeError, ValueError):
            continue
        if page_number < 1 or page_number in seen_numbers:
            continue
        seen_numbers.add(page_number)
        pages.append(
            PdfOcrPageText(
                schema_version="1.0",
                page_number=page_number,
                text=str(item.get("text") or ""),
            )
        )
    pages.sort(key=lambda page: page.page_number)
    return pages


@dataclass(frozen=True)
class _ChatCompletionRun:
    payload: str
    request_id: str | None
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None


def _legacy_chat_completion_call(
    *,
    api_key: str,
    timeout_seconds: float | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    seed: int | None,
) -> _ChatCompletionRun:
    # Compatibility path for environments where OpenAI client instantiation
    # fails (e.g., unexpected kwargs like proxies in older dependencies).
    previous_timeout = getattr(openai_legacy, "timeout", None)
    had_timeout_attr = hasattr(openai_legacy, "timeout")
    openai_legacy.api_key = api_key
    try:
        if timeout_seconds is not None:
            openai_legacy.timeout = timeout_seconds
        elif had_timeout_attr:
            delattr(openai_legacy, "timeout")
        payload_args = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
            "seed": seed,
        }
        try:
            payload_args["response_format"] = {"type": "json_object"}
            resp = openai_legacy.ChatCompletion.create(**payload_args)
        except TypeError:
            payload_args.pop("response_format", None)
            resp = openai_legacy.ChatCompletion.create(**payload_args)
        payload = resp["choices"][0]["message"]["content"]
        usage = resp.get("usage") or {}
        return _ChatCompletionRun(
            payload=payload,
            request_id=resp.get("id"),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            total_tokens=usage.get("total_tokens"),
        )
    finally:
        if had_timeout_attr:
            openai_legacy.timeout = previous_timeout
        else:
            try:
                delattr(openai_legacy, "timeout")
            except AttributeError:
                had_timeout_attr = False


def _modern_chat_completion_call(
    *,
    api_key: str,
    timeout_seconds: float | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    seed: int | None,
) -> _ChatCompletionRun:
    if OpenAI is None:
        raise TypeError("OpenAI client not available")
    client_kwargs: dict = {"api_key": api_key}
    if timeout_seconds is not None:
        client_kwargs["timeout"] = timeout_seconds
    client = OpenAI(**client_kwargs)
    payload_args = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "response_format": {"type": "json_object"},
        "temperature": temperature,
    }
    if seed is not None:
        payload_args["seed"] = seed
    resp = client.chat.completions.create(**payload_args)
    usage = getattr(resp, "usage", None)
    return _ChatCompletionRun(
        payload=resp.choices[0].message.content or "",
        request_id=getattr(resp, "id", None),
        prompt_tokens=getattr(usage, "prompt_tokens", None)
        if usage is not None
        else None,
        completion_tokens=getattr(usage, "completion_tokens", None)
        if usage is not None
        else None,
        total_tokens=getattr(usage, "total_tokens", None)
        if usage is not None
        else None,
    )


def _run_chat_completion(
    *,
    api_key: str,
    timeout_seconds: float | None,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float,
    seed: int | None,
) -> _ChatCompletionRun:
    try:
        return _modern_chat_completion_call(
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            seed=seed,
        )
    except TypeError:
        return _legacy_chat_completion_call(
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            seed=seed,
        )


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

    payload = None
    request_id = None
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None
    tool_calls = request.tool_calls or 0
    cached_tokens = request.cached_input_tokens

    try:
        run = _run_chat_completion(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            model=request.model,
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            temperature=request.temperature,
            seed=request.seed,
        )
        payload = run.payload
        request_id = run.request_id
        prompt_tokens = run.prompt_tokens
        completion_tokens = run.completion_tokens
        total_tokens = run.total_tokens
    except OPENAI_REQUEST_EXCEPTIONS as exc:
        code, message, retryable = _classify_openai_request_error(
            exc,
            default_code="openai_request_failed",
            default_message="OpenAI request failed",
        )
        raise AppError(
            code=code,
            message=message,
            cause=exc,
            retryable=retryable,
            context={
                "model": request.model,
                "provider_error_type": type(exc).__name__,
            },
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

    _record_usage_accounting(
        ctx=ctx,
        step_name="openai_analyze",
        model=request.model,
        input_tokens=prompt_tokens,
        output_tokens=completion_tokens,
        cached_input_tokens=int(cached_tokens) if cached_tokens is not None else None,
        tool_calls=tool_calls,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=request_id,
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
    cache_spec = _semantic_response_cache_spec(
        request,
        operation="openai_chat_json",
        params={
            "model": request.model,
            "temperature": request.temperature,
            "seed": request.seed,
            "response_format": "json_object",
        },
    )
    if cache_spec is not None:
        cached_payload = _read_semantic_response_cache(cache_spec, ctx)
        if cached_payload is not None:
            return _openai_response_result_from_cache(cached_payload)
    metadata = _OpenAIResponseMetadata(
        text="",
        request_id=None,
        input_tokens=None,
        output_tokens=None,
        tool_calls=0,
        total_tokens=None,
        parsed_json=None,
        parse_strategy="empty",
    )

    try:
        run = _run_chat_completion(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            model=request.model,
            system_prompt=request.system_prompt,
            user_prompt=request.user_prompt,
            temperature=request.temperature,
            seed=request.seed,
        )
        metadata = _adapt_chat_completion_metadata(run)
    except OPENAI_REQUEST_EXCEPTIONS as exc:
        code, message, retryable = _classify_openai_request_error(
            exc,
            default_code="openai_chat_failed",
            default_message="OpenAI chat request failed",
        )
        raise AppError(
            code=code,
            message=message,
            cause=exc,
            retryable=retryable,
            context={
                "model": request.model,
                "provider_error_type": type(exc).__name__,
            },
        ) from exc

    _record_usage_accounting(
        ctx=ctx,
        step_name="openai_chat_json",
        model=request.model,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        tool_calls=metadata.tool_calls,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=metadata.request_id,
    )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_chat_json_complete",
            module=logger.name,
            fields={
                "model": request.model,
                "request_id": metadata.request_id or "",
                "prompt_tokens": metadata.input_tokens,
                "completion_tokens": metadata.output_tokens,
                "total_tokens": metadata.total_tokens,
                "parsed_json": metadata.parsed_json is not None,
            },
        )
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
    cache_spec = _semantic_response_cache_spec(
        request,
        operation="openai_chat_json_with_images",
        params={
            "model": request.model,
            "temperature": request.temperature,
            "seed": request.seed,
            "response_format": "json_object",
        },
        context={
            "image_fingerprints": [
                _file_fingerprint(path, content_hash=True)
                for path in (request.image_paths or [])
            ],
        },
    )
    if cache_spec is not None:
        cached_payload = _read_semantic_response_cache(cache_spec, ctx)
        if cached_payload is not None:
            return _openai_response_result_from_cache(cached_payload)
    image_urls = [_image_path_to_data_url(path) for path in request.image_paths]
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="chat_json_with_images",
        )
        user_content = [{"type": "input_text", "text": request.user_prompt}]
        user_content.extend(
            {"type": "input_image", "image_url": image_url} for image_url in image_urls
        )
        payload_args: dict[str, Any] = {
            "model": request.model,
            "input": [
                {
                    "role": "system",
                    "content": [{"type": "input_text", "text": request.system_prompt}],
                },
                {"role": "user", "content": user_content},
            ],
        }
        known_unsupported = _known_unsupported_image_params(request.model)
        if request.temperature is not None and "temperature" not in known_unsupported:
            payload_args["temperature"] = request.temperature
        if request.seed is not None and "seed" not in known_unsupported:
            payload_args["seed"] = request.seed
        if known_unsupported:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="openai_chat_json_with_images_skip_known_unsupported_params",
                    module=logger.name,
                    fields={
                        "model": request.model,
                        "skipped_params": sorted(known_unsupported),
                    },
                )
            )
        resp = _responses_create_with_unsupported_param_retry(
            client=client,
            payload_args=payload_args,
            fallback_params=("temperature", "seed"),
            ctx=ctx,
            event_name="openai_chat_json_with_images_retry_without_param",
            model=request.model,
        )
    except AppError:
        raise
    except OPENAI_REQUEST_EXCEPTIONS as exc:
        code, message, retryable = _classify_openai_request_error(
            exc,
            default_code="openai_chat_images_failed",
            default_message="OpenAI JSON+images request failed",
        )
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
            code=code,
            message=message,
            cause=exc,
            retryable=retryable,
            context={
                "model": request.model,
                "provider_error_type": type(exc).__name__,
            },
        ) from exc

    metadata = _adapt_responses_metadata(resp, recover_json_object=False)
    _record_usage_accounting(
        ctx=ctx,
        step_name="openai_chat_json_with_images",
        model=request.model,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        tool_calls=metadata.tool_calls,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=metadata.request_id,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_chat_json_with_images_complete",
            module=logger.name,
            fields={
                "model": request.model,
                "request_id": metadata.request_id or "",
                "image_count": len(request.image_paths or []),
                "input_tokens": metadata.input_tokens,
                "output_tokens": metadata.output_tokens,
                "tool_calls": metadata.tool_calls,
                "parsed_json": metadata.parsed_json is not None,
            },
        )
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
    if not pages or not any(page.text.strip() for page in pages):
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

    _record_usage_accounting(
        ctx=ctx,
        step_name="openai_ocr_pdf",
        model=resolved_model,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        tool_calls=metadata.tool_calls,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=metadata.request_id,
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
            "tools": ["file_search"],
        },
        context={"vector_store_id": request.vector_store_id},
    )
    if cache_spec is not None:
        cached_payload = _read_semantic_response_cache(cache_spec, ctx)
        if cached_payload is not None:
            return _openai_response_result_from_cache(cached_payload)
    payload_args = {
        "model": request.model,
        "instructions": request.system_prompt,
        "input": [{"role": "user", "content": request.user_prompt}],
        "temperature": request.temperature,
        "tools": [
            {"type": "file_search", "vector_store_ids": [request.vector_store_id]}
        ],
    }
    if request.seed is not None:
        payload_args["seed"] = request.seed
    try:
        client = _build_openai_client(
            api_key=request.api_key,
            timeout_seconds=request.timeout_seconds,
            operation="response_vector_store",
        )
        resp = _responses_create_with_unsupported_param_retry(
            client=client,
            payload_args=payload_args,
            fallback_params=("temperature", "seed"),
            ctx=ctx,
            event_name="openai_response_retry_without_param",
            model=request.model,
        )
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

    _record_usage_accounting(
        ctx=ctx,
        step_name="openai_response_vector_store",
        model=request.model,
        input_tokens=metadata.input_tokens,
        output_tokens=metadata.output_tokens,
        tool_calls=metadata.tool_calls,
        cost_ledger_path=request.cost_ledger_path,
        cost_daily_path=request.cost_daily_path,
        model_pricing=request.model_pricing,
        request_id=metadata.request_id,
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


def openai_vector_store_create(
    request: OpenAIVectorStoreCreateRequest, ctx: RunContext
) -> OpenAIVectorStoreCreateResponse:
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_CREATE_OPERATION.start_event,
        fields={
            "name": request.name,
            "metadata_keys": list((request.metadata or {}).keys()),
            "timeout_seconds": request.timeout_seconds,
        },
    )
    resp = _run_vector_store_request(
        api_key=request.api_key,
        timeout_seconds=request.timeout_seconds,
        spec=_VECTOR_STORE_CREATE_OPERATION,
        ctx=ctx,
        request_fn=lambda client: client.vector_stores.create(
            name=request.name, metadata=request.metadata or {}
        ),
    )
    vector_store_id = _require_openai_id(
        resp,
        code="openai_vector_store_create_failed",
        message="OpenAI vector store create did not return an id",
    )
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_CREATE_OPERATION.complete_event,
        fields={"name": request.name, "vector_store_id": vector_store_id},
    )
    return OpenAIVectorStoreCreateResponse(
        schema_version="1.0", vector_store_id=vector_store_id
    )


def openai_vector_store_upload_file(
    request: OpenAIVectorStoreFileUploadRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreFileUploadResponse:
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_UPLOAD_OPERATION.start_event,
        fields={
            "file_path": request.file_path,
            "purpose": request.purpose,
            "timeout_seconds": request.timeout_seconds,
        },
    )
    try:
        with open(request.file_path, "rb") as file_handle:
            resp = _run_vector_store_request(
                api_key=request.api_key,
                timeout_seconds=request.timeout_seconds,
                spec=_VECTOR_STORE_UPLOAD_OPERATION,
                ctx=ctx,
                request_fn=lambda client: client.files.create(
                    file=file_handle, purpose=request.purpose
                ),
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
    openai_file_id = _require_openai_id(
        resp,
        code="openai_vector_store_upload_failed",
        message="OpenAI file upload did not return an id",
    )
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_UPLOAD_OPERATION.complete_event,
        fields={"file_path": request.file_path, "openai_file_id": openai_file_id},
    )
    return OpenAIVectorStoreFileUploadResponse(
        schema_version="1.0", openai_file_id=openai_file_id
    )


def openai_vector_store_attach_file(
    request: OpenAIVectorStoreAttachFileRequest,
    ctx: RunContext,
) -> OpenAIVectorStoreAttachFileResponse:
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_ATTACH_OPERATION.start_event,
        fields={
            "vector_store_id": request.vector_store_id,
            "openai_file_id": request.openai_file_id,
            "timeout_seconds": request.timeout_seconds,
        },
    )
    resp = _run_vector_store_request(
        api_key=request.api_key,
        timeout_seconds=request.timeout_seconds,
        spec=_VECTOR_STORE_ATTACH_OPERATION,
        ctx=ctx,
        request_fn=lambda client: client.vector_stores.files.create(
            vector_store_id=request.vector_store_id,
            file_id=request.openai_file_id,
        ),
    )
    attached_id = _require_openai_id(
        resp,
        code="openai_vector_store_attach_failed",
        message="OpenAI vector store attach did not return an id",
    )
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_ATTACH_OPERATION.complete_event,
        fields={
            "vector_store_id": request.vector_store_id,
            "openai_file_id": attached_id,
        },
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
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_STATUS_OPERATION.start_event,
        fields={
            "vector_store_id": request.vector_store_id,
            "timeout_seconds": request.timeout_seconds,
        },
    )
    resp = _run_vector_store_request(
        api_key=request.api_key,
        timeout_seconds=request.timeout_seconds,
        spec=_VECTOR_STORE_STATUS_OPERATION,
        ctx=ctx,
        request_fn=lambda client: client.vector_stores.retrieve(
            request.vector_store_id
        ),
        error_context={"vector_store_id": request.vector_store_id},
    )
    status = _value_from_response(resp, "status")
    indexed_at = _value_from_response(resp, "created_at")
    last_error = _value_from_response(resp, "last_error")
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_STATUS_OPERATION.complete_event,
        fields={"vector_store_id": request.vector_store_id, "status": status},
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
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_UPDATE_METADATA_OPERATION.start_event,
        fields={
            "vector_store_id": request.vector_store_id,
            "metadata_keys": list((request.metadata or {}).keys()),
            "timeout_seconds": request.timeout_seconds,
        },
    )
    resp = _run_vector_store_request(
        api_key=request.api_key,
        timeout_seconds=request.timeout_seconds,
        spec=_VECTOR_STORE_UPDATE_METADATA_OPERATION,
        ctx=ctx,
        request_fn=lambda client: client.vector_stores.update(
            vector_store_id=request.vector_store_id,
            metadata=request.metadata or {},
        ),
        error_context={"vector_store_id": request.vector_store_id},
    )
    updated_id = _require_openai_id(
        resp,
        code="openai_vector_store_update_metadata_failed",
        message="OpenAI vector store metadata update did not return an id",
    )
    _log_vector_store_event(
        ctx,
        event=_VECTOR_STORE_UPDATE_METADATA_OPERATION.complete_event,
        fields={"vector_store_id": updated_id},
    )
    return OpenAIVectorStoreUpdateMetadataResponse(
        schema_version="1.0", vector_store_id=updated_id
    )
