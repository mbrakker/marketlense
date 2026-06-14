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
    OpenAIVectorStoreDeleteRequest,
    OpenAIVectorStoreDeleteResponse,
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

logger = logging.getLogger("market_lense.llm_service.openai")
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


def _openai_client_factory() -> Any | None:
    return getattr(openai_legacy, "OpenAI", None)


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
_VECTOR_STORE_DELETE_OPERATION = _VectorStoreOperationSpec(
    operation="vector_store_delete",
    start_event="openai_vector_store_delete_start",
    complete_event="openai_vector_store_delete_complete",
    error_code="openai_vector_store_delete_failed",
    error_message="OpenAI vector store delete request failed",
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


def _adapt_chat_completion_metadata(run: Any) -> _OpenAIResponseMetadata:
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


__all__ = [
    "Any",
    "AppError",
    "Callable",
    "Figure",
    "OPENAI_CLIENT_INIT_EXCEPTIONS",
    "OPENAI_ERROR_TYPES",
    "OPENAI_OCR_RESPONSE_FORMAT",
    "OPENAI_REQUEST_EXCEPTIONS",
    "_openai_client_factory",
    "OpenAIAnalyzeRequest",
    "OpenAIAnalyzeResponse",
    "OpenAIJSONImagePromptRequest",
    "OpenAIJSONPromptRequest",
    "OpenAIPdfOcrRequest",
    "OpenAIPdfOcrResponse",
    "OpenAIResponseRequest",
    "OpenAIResponseResult",
    "OpenAIUsageAccountingRequest",
    "OpenAIVectorStoreAttachFileRequest",
    "OpenAIVectorStoreAttachFileResponse",
    "OpenAIVectorStoreCreateRequest",
    "OpenAIVectorStoreCreateResponse",
    "OpenAIVectorStoreDeleteRequest",
    "OpenAIVectorStoreDeleteResponse",
    "OpenAIVectorStoreFileUploadRequest",
    "OpenAIVectorStoreFileUploadResponse",
    "OpenAIVectorStoreStatusRequest",
    "OpenAIVectorStoreStatusResponse",
    "OpenAIVectorStoreUpdateMetadataRequest",
    "OpenAIVectorStoreUpdateMetadataResponse",
    "Path",
    "PdfOcrPageText",
    "Quote",
    "REQUIRED_KEYS",
    "ReportPayload",
    "RunContext",
    "SEMANTIC_RESPONSE_CACHE_SCHEMA_VERSION",
    "SEMANTIC_RESPONSE_CACHE_SUBDIR",
    "WriteBytesRequest",
    "_OpenAIResponseMetadata",
    "_RESPONSES_IMAGE_UNSUPPORTED_PARAM_PREFIXES",
    "_SemanticResponseCacheSpec",
    "_VECTOR_STORE_ATTACH_OPERATION",
    "_VECTOR_STORE_CREATE_OPERATION",
    "_VECTOR_STORE_DELETE_OPERATION",
    "_VECTOR_STORE_STATUS_OPERATION",
    "_VECTOR_STORE_UPDATE_METADATA_OPERATION",
    "_VECTOR_STORE_UPLOAD_OPERATION",
    "_VectorStoreOperationSpec",
    "_adapt_chat_completion_metadata",
    "_adapt_responses_metadata",
    "_build_response_metadata",
    "_bytes_to_data_url",
    "_classify_openai_request_error",
    "_coerce_pdf_ocr_pages",
    "_extract_responses_output_text",
    "_extract_responses_usage",
    "_extract_unsupported_parameter",
    "_file_fingerprint",
    "_image_path_to_data_url",
    "_known_unsupported_image_params",
    "_ocr_response_from_cache",
    "_openai_error_body_code",
    "_openai_error_status_code",
    "_openai_response_result_from_cache",
    "_parse_json_object_from_text",
    "_parse_response_json",
    "_read_semantic_response_cache",
    "_record_usage_accounting",
    "_responses_create_with_unsupported_param_retry",
    "_semantic_response_cache_spec",
    "_sha256_payload",
    "_sha256_text",
    "_stable_json",
    "_strip_json_fence",
    "_validate_payload",
    "_write_semantic_response_cache",
    "asdict",
    "dataclass",
    "file_service",
    "hashlib",
    "json",
    "log_event",
    "logger",
    "openai_accounting_service",
    "openai_legacy",
]
