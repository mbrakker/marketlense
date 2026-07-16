from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from src.contracts.logging import (
    LOG_EVENT_ROLES,
    LOG_EVENT_SCHEMA_VERSION,
    REQUIRED_LOG_EVENT_FIELDS,
    LogEventValidationResult,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId, TaskId


def _coerce_task_id(task_id: TaskId | str | None) -> TaskId:
    return task_id if isinstance(task_id, TaskId) else TaskId(task_id or str(uuid4()))


def new_run_context(
    task_id: TaskId | str | None = None,
    span_id: str | None = None,
) -> RunContext:
    resolved_task_id = _coerce_task_id(task_id)
    resolved_span_id = span_id or str(uuid4())
    return RunContext(
        schema_version="1.1",
        run_id=RunId(str(uuid4())),
        task_id=resolved_task_id,
        span_id=resolved_span_id,
        trace_id=str(uuid4()),
        parent_span_id="",
        span_name=str(resolved_task_id),
        span_depth=0,
    )


def child_context(
    parent: RunContext,
    *,
    task_id: TaskId | str | None = None,
) -> RunContext:
    resolved_task_id = (
        _coerce_task_id(task_id) if task_id is not None else parent.task_id
    )
    return RunContext(
        schema_version=parent.schema_version,
        run_id=parent.run_id,
        task_id=resolved_task_id,
        span_id=str(uuid4()),
        trace_id=str(parent.trace_id or parent.run_id),
        parent_span_id=str(parent.span_id or ""),
        span_name=str(resolved_task_id),
        span_depth=max(0, int(getattr(parent, "span_depth", 0))) + 1,
    )


REDACTED = "***REDACTED***"
MAX_LOG_TEXT_CHARACTERS = 120
SENSITIVE_KEYS = {
    "api_key",
    "app_password",
    "auth_header",
    "authorization",
    "bearer_token",
    "password",
    "secret",
    "token",
}
CONTENT_FIELD_TOKENS = frozenset(
    {
        "body",
        "commentary",
        "content",
        "evidence",
        "excerpt",
        "paragraph",
        "prompt",
        "response",
        "text",
    }
)
_OPENAI_KEY_RX = re.compile(r"sk-[A-Za-z0-9]{20,}")
_BEARER_RX = re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]+")
_EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_URL_ENCODED_EMAIL_RX = re.compile(
    r"(?i)[A-Za-z0-9._%+-]+%40[A-Za-z0-9.-]+\.[A-Za-z]{2,}"
)
_URL_SENSITIVE_QUERY_RX = re.compile(
    r"(?i)([?&;](?:auth|authorization|email|e-mail|key|mkt_tok|password|secret|sig|signature|token)=)([^&#\s]+)"
)
_URL_ENCODED_SENSITIVE_QUERY_RX = re.compile(
    r"(?i)((?:%3F|%26|%3B)(?:auth|authorization|email|e-mail|key|mkt_tok|password|secret|sig|signature|token)(?:=|%3D))([^%&#\s]+)"
)
_PHONE_RX = re.compile(
    r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(\d{2,4}\)|\d{2,4})[-.\s]?\d{3}[-.\s]?\d{4}\b"
)
_SSN_RX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        v = _OPENAI_KEY_RX.sub(REDACTED, value)
        v = _BEARER_RX.sub(f"Bearer {REDACTED}", v)
        v = _URL_SENSITIVE_QUERY_RX.sub(lambda match: f"{match.group(1)}{REDACTED}", v)
        v = _URL_ENCODED_SENSITIVE_QUERY_RX.sub(
            lambda match: f"{match.group(1)}{REDACTED}",
            v,
        )
        v = _EMAIL_RX.sub(REDACTED, v)
        v = _URL_ENCODED_EMAIL_RX.sub(REDACTED, v)
        v = _PHONE_RX.sub(REDACTED, v)
        v = _SSN_RX.sub(REDACTED, v)
        return v
    return value


def _text_metadata(value: str) -> Dict[str, Any]:
    """Retain diagnostic identity without emitting retained report content."""

    return {
        "redaction": REDACTED,
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        "character_count": len(value),
    }


def _is_content_field(key: str) -> bool:
    return bool(
        CONTENT_FIELD_TOKENS.intersection(
            token for token in re.split(r"[^a-z0-9]+", key.casefold()) if token
        )
    )


def _redact_field_value(key: str, value: Any) -> Any:
    if isinstance(value, str):
        safe_value = _redact_value(value)
        if _is_content_field(key) or len(safe_value) > MAX_LOG_TEXT_CHARACTERS:
            return _text_metadata(safe_value)
        return safe_value
    if isinstance(value, dict):
        return _redact_fields(value)
    if isinstance(value, (list, tuple)):
        return [_redact_field_value(key, item) for item in value]
    return _redact_value(value)


def _redact_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    redacted: Dict[str, Any] = {}
    for k, v in fields.items():
        key = str(k)
        if key.lower() in SENSITIVE_KEYS:
            redacted[key] = REDACTED
            continue
        redacted[key] = _redact_field_value(key, v)
    return redacted


def log_event(
    ctx: RunContext,
    *,
    role: str,
    event: str,
    module: str,
    fields: Dict[str, Any] | None = None,
) -> str:
    trace_id = str(getattr(ctx, "trace_id", "") or ctx.run_id)
    span_name = str(getattr(ctx, "span_name", "") or ctx.task_id)
    payload = {
        "run_id": ctx.run_id,
        "task_id": ctx.task_id,
        "span_id": ctx.span_id,
        "trace_id": trace_id,
        "parent_span_id": str(getattr(ctx, "parent_span_id", "") or ""),
        "span_name": span_name,
        "span_depth": int(getattr(ctx, "span_depth", 0) or 0),
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "module": module,
        "role": role,
        "event": event,
        "fields": _redact_fields(fields or {}),
    }
    try:
        return json.dumps(payload, ensure_ascii=True)
    except Exception:
        fallback = {
            "run_id": ctx.run_id,
            "task_id": ctx.task_id,
            "span_id": ctx.span_id,
            "trace_id": trace_id,
            "parent_span_id": str(getattr(ctx, "parent_span_id", "") or ""),
            "span_name": span_name,
            "span_depth": int(getattr(ctx, "span_depth", 0) or 0),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "module": module,
            "role": role,
            "event": event,
            "fields": {"error": "log serialization failed"},
        }
        return json.dumps(fallback, ensure_ascii=True)


def validate_log_event_payload(
    payload: str | dict[str, Any],
) -> LogEventValidationResult:
    try:
        data: Any = json.loads(payload) if isinstance(payload, str) else payload
    except json.JSONDecodeError:
        return LogEventValidationResult(
            schema_version=LOG_EVENT_SCHEMA_VERSION,
            valid=False,
            missing_fields=tuple(sorted(REQUIRED_LOG_EVENT_FIELDS)),
            invalid_fields=("json",),
        )
    if not isinstance(data, dict):
        return LogEventValidationResult(
            schema_version=LOG_EVENT_SCHEMA_VERSION,
            valid=False,
            missing_fields=tuple(sorted(REQUIRED_LOG_EVENT_FIELDS)),
            invalid_fields=("payload",),
        )

    missing = tuple(
        sorted(field for field in REQUIRED_LOG_EVENT_FIELDS if field not in data)
    )
    invalid: list[str] = []
    empty_allowed = {"parent_span_id"}
    for field in REQUIRED_LOG_EVENT_FIELDS:
        value = data.get(field)
        if field in data and field not in empty_allowed and not str(value).strip():
            invalid.append(field)
    role = str(data.get("role") or "").strip()
    if role and role not in LOG_EVENT_ROLES:
        invalid.append("role")
    fields_value = data.get("fields")
    if fields_value is not None and not isinstance(fields_value, dict):
        invalid.append("fields")

    return LogEventValidationResult(
        schema_version=LOG_EVENT_SCHEMA_VERSION,
        valid=not missing and not invalid,
        missing_fields=missing,
        invalid_fields=tuple(sorted(set(invalid))),
    )
