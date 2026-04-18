from __future__ import annotations

import json
import re
from typing import Any, Dict
from uuid import uuid4

from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId, TaskId


def new_run_context(
    task_id: TaskId | str | None = None,
    span_id: str | None = None,
) -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id=RunId(str(uuid4())),
        task_id=TaskId(task_id or str(uuid4())),
        span_id=span_id or str(uuid4()),
    )


def child_context(
    parent: RunContext,
    *,
    task_id: TaskId | str | None = None,
) -> RunContext:
    return RunContext(
        schema_version=parent.schema_version,
        run_id=parent.run_id,
        task_id=task_id or parent.task_id,
        span_id=str(uuid4()),
    )


REDACTED = "***REDACTED***"
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
_OPENAI_KEY_RX = re.compile(r"sk-[A-Za-z0-9]{20,}")
_BEARER_RX = re.compile(r"(?i)bearer\s+[A-Za-z0-9._-]+")
_EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RX = re.compile(r"\b(?:\+?\d{1,3}[-.\s]?)?(?:\(\d{2,4}\)|\d{2,4})[-.\s]?\d{3}[-.\s]?\d{4}\b")
_SSN_RX = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")


def _redact_value(value: Any) -> Any:
    if isinstance(value, str):
        v = _OPENAI_KEY_RX.sub(REDACTED, value)
        v = _BEARER_RX.sub(f"Bearer {REDACTED}", v)
        v = _EMAIL_RX.sub(REDACTED, v)
        v = _PHONE_RX.sub(REDACTED, v)
        v = _SSN_RX.sub(REDACTED, v)
        return v
    return value


def _redact_fields(fields: Dict[str, Any]) -> Dict[str, Any]:
    redacted: Dict[str, Any] = {}
    for k, v in fields.items():
        key = str(k)
        if key.lower() in SENSITIVE_KEYS:
            redacted[key] = REDACTED
            continue
        if isinstance(v, dict):
            redacted[key] = _redact_fields(v)
            continue
        if isinstance(v, list):
            redacted_items = []
            for item in v:
                if isinstance(item, dict):
                    redacted_items.append(_redact_fields(item))
                else:
                    redacted_items.append(_redact_value(item))
            redacted[key] = redacted_items
            continue
        redacted[key] = _redact_value(v)
    return redacted


def log_event(
    ctx: RunContext,
    *,
    role: str,
    event: str,
    module: str,
    fields: Dict[str, Any] | None = None,
) -> str:
    payload = {
        "run_id": ctx.run_id,
        "task_id": ctx.task_id,
        "span_id": ctx.span_id,
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
            "module": module,
            "role": role,
            "event": event,
            "fields": {"error": "log serialization failed"},
        }
        return json.dumps(fallback, ensure_ascii=True)
