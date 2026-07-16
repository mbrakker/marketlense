from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Dict
from uuid import uuid4

from src.contracts.logging import (
    LOG_EVENT_ROLES,
    LOG_EVENT_SCHEMA_VERSION,
    MAX_LOG_ARTIFACT_REFERENCE_CHARACTERS,
    MAX_LOG_COLLECTION_ITEMS,
    MAX_LOG_EVENT_BYTES,
    MAX_LOG_FIELD_DEPTH,
    MAX_LOG_FIELD_KEY_CHARACTERS,
    MAX_LOG_FIELD_NODES,
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
    tokens = {token for token in re.split(r"[^a-z0-9]+", key.casefold()) if token}
    if "evidence" in tokens and {"pack", "packs"}.intersection(tokens):
        return False
    if "prompt" in tokens and not {
        "namespace",
        "namespaces",
        "hash",
        "id",
        "count",
        "token",
        "tokens",
    }.intersection(tokens):
        return True
    return bool(CONTENT_FIELD_TOKENS.intersection(tokens))


def _collection_reduction_metadata(
    *,
    original_item_count: int,
    retained_item_count: int,
    reason: str,
) -> Dict[str, Any]:
    return {
        "reason": reason,
        "original_item_count": original_item_count,
        "retained_item_count": retained_item_count,
    }


def _bounded_non_scalar_metadata(value: Any) -> Dict[str, Any]:
    """Describe a discarded non-scalar without serializing its contents."""

    return {
        "redaction": REDACTED,
        "type": f"{type(value).__module__}.{type(value).__qualname__}",
    }


def _bounded_field_key(key: Any) -> str:
    value = str(key)
    if len(value) <= MAX_LOG_FIELD_KEY_CHARACTERS:
        return value
    return "field_sha256_" + hashlib.sha256(value.encode("utf-8")).hexdigest()


def _artifact_reference_metadata(value: str) -> Dict[str, Any]:
    return {
        "redaction": REDACTED,
        "sha256": hashlib.sha256(value.encode("utf-8")).hexdigest(),
        "character_count": len(value),
        "reason": "artifact_reference_too_long",
    }


def _redact_field_value(
    key: str,
    value: Any,
    *,
    depth: int,
    node_budget: list[int],
) -> Any:
    if node_budget[0] <= 0:
        return _collection_reduction_metadata(
            original_item_count=1,
            retained_item_count=0,
            reason="node_budget_exceeded",
        )
    node_budget[0] -= 1
    if isinstance(value, str):
        safe_value = _redact_value(value)
        if _is_artifact_reference_field(key):
            if len(safe_value) > MAX_LOG_ARTIFACT_REFERENCE_CHARACTERS:
                return _artifact_reference_metadata(safe_value)
            return safe_value
        if _is_content_field(key) or len(safe_value) > MAX_LOG_TEXT_CHARACTERS:
            return _text_metadata(safe_value)
        return safe_value
    if isinstance(value, Mapping):
        if depth >= MAX_LOG_FIELD_DEPTH:
            return _collection_reduction_metadata(
                original_item_count=len(value),
                retained_item_count=0,
                reason="max_depth_exceeded",
            )
        return _redact_fields(value, depth=depth + 1, node_budget=node_budget)
    if isinstance(value, (list, tuple, set, frozenset)):
        if depth >= MAX_LOG_FIELD_DEPTH:
            return _collection_reduction_metadata(
                original_item_count=len(value),
                retained_item_count=0,
                reason="max_depth_exceeded",
            )
        items = list(value)
        if isinstance(value, (set, frozenset)):
            items.sort(key=lambda item: str(item))
        retained_items = items[:MAX_LOG_COLLECTION_ITEMS]
        redacted_items = [
            _redact_field_value(
                key,
                item,
                depth=depth + 1,
                node_budget=node_budget,
            )
            for item in retained_items
        ]
        if len(items) > len(retained_items):
            redacted_items.append(
                {
                    "log_collection_reduced": _collection_reduction_metadata(
                        original_item_count=len(items),
                        retained_item_count=len(retained_items),
                        reason="max_collection_items_exceeded",
                    )
                }
            )
        return redacted_items
    if isinstance(value, (int, float, bool)) or value is None:
        return _redact_value(value)
    return _bounded_non_scalar_metadata(value)


def _redact_fields(
    fields: Mapping[str, Any],
    *,
    depth: int = 0,
    node_budget: list[int] | None = None,
) -> Dict[str, Any]:
    budget = node_budget if node_budget is not None else [MAX_LOG_FIELD_NODES]
    redacted: Dict[str, Any] = {}
    items = sorted(fields.items(), key=lambda item: str(item[0]))
    artifact_items = [
        item for item in items if _is_artifact_reference_field(str(item[0]))
    ]
    non_artifact_items = [
        item for item in items if not _is_artifact_reference_field(str(item[0]))
    ]
    retained_items = (
        artifact_items[:MAX_LOG_COLLECTION_ITEMS]
        + non_artifact_items[: max(0, MAX_LOG_COLLECTION_ITEMS - len(artifact_items))]
    )
    for k, v in retained_items:
        key = _bounded_field_key(k)
        if key.lower() in SENSITIVE_KEYS:
            redacted[key] = REDACTED
            continue
        redacted[key] = _redact_field_value(
            key,
            v,
            depth=depth,
            node_budget=budget,
        )
    if len(items) > len(retained_items):
        redacted["log_collection_reduced"] = _collection_reduction_metadata(
            original_item_count=len(items),
            retained_item_count=len(retained_items),
            reason="max_collection_items_exceeded",
        )
    return redacted


def _serialized_payload(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=True)


def _is_artifact_reference_field(key: str) -> bool:
    key_tokens = {token for token in re.split(r"[^a-z0-9]+", key.casefold()) if token}
    return bool(
        key_tokens.intersection(
            {
                "artifact",
                "audit",
                "hash",
                "path",
                "reference",
                "ref",
                "retained",
                "snapshot",
            }
        )
    )


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _reduced_value_metadata(value: Any) -> Dict[str, Any]:
    try:
        serialized = json.dumps(value, ensure_ascii=True, sort_keys=True)
    except (TypeError, ValueError):
        return _bounded_non_scalar_metadata(value)
    return {
        "redaction": REDACTED,
        "sha256": hashlib.sha256(serialized.encode("utf-8")).hexdigest(),
        "type": type(value).__name__,
    }


def _reduce_oversized_fields(
    fields: Dict[str, Any],
    *,
    attempted_size_bytes: int,
) -> Dict[str, Any]:
    """Retain scalar operations data and artifact references when size limits trip."""

    reduction = {
        "attempted_size_bytes": attempted_size_bytes,
        "maximum_size_bytes": MAX_LOG_EVENT_BYTES,
        "original_field_count": len(fields),
    }
    reduced: Dict[str, Any] = {"log_payload_reduced": reduction}
    omitted_field_count = 0
    for key, value in fields.items():
        if _is_scalar(value) or _is_artifact_reference_field(key):
            reduced[key] = value
        else:
            reduced[key] = _reduced_value_metadata(value)
    reduction["omitted_field_count"] = omitted_field_count
    return reduced


def _final_reduced_fields(
    payload: Dict[str, Any],
    fields: Dict[str, Any],
    *,
    attempted_size_bytes: int,
    original_field_count: int,
) -> Dict[str, Any]:
    """Fit retained artifact references under the absolute event-size contract."""

    reduction: Dict[str, Any] = {
        "attempted_size_bytes": attempted_size_bytes,
        "maximum_size_bytes": MAX_LOG_EVENT_BYTES,
        "original_field_count": original_field_count,
        "hashed_artifact_reference_count": 0,
        "omitted_artifact_reference_count": 0,
    }
    reduced: Dict[str, Any] = {"log_payload_reduced": reduction}
    for key, value in sorted(fields.items()):
        if not _is_artifact_reference_field(key):
            continue
        candidate = {**reduced, key: value}
        payload["fields"] = candidate
        if len(_serialized_payload(payload).encode("utf-8")) <= MAX_LOG_EVENT_BYTES:
            reduced[key] = value
            continue
        metadata = _reduced_value_metadata(value)
        candidate = {**reduced, key: metadata}
        payload["fields"] = candidate
        if len(_serialized_payload(payload).encode("utf-8")) <= MAX_LOG_EVENT_BYTES:
            reduced[key] = metadata
            reduction["hashed_artifact_reference_count"] += 1
            continue
        reduction["omitted_artifact_reference_count"] += 1
    payload["fields"] = reduced
    return reduced


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
    payload: Dict[str, Any] = {
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
        serialized = _serialized_payload(payload)
        if len(serialized.encode("utf-8")) <= MAX_LOG_EVENT_BYTES:
            return serialized
        payload["fields"] = _reduce_oversized_fields(
            payload["fields"],
            attempted_size_bytes=len(serialized.encode("utf-8")),
        )
        reduced_serialized = _serialized_payload(payload)
        if len(reduced_serialized.encode("utf-8")) <= MAX_LOG_EVENT_BYTES:
            return reduced_serialized
        payload["fields"] = _final_reduced_fields(
            payload,
            payload["fields"],
            attempted_size_bytes=len(serialized.encode("utf-8")),
            original_field_count=len(fields or {}),
        )
        final_serialized = _serialized_payload(payload)
        if len(final_serialized.encode("utf-8")) <= MAX_LOG_EVENT_BYTES:
            return final_serialized
        payload["fields"] = {
            "log_payload_reduced": {
                "attempted_size_bytes": len(serialized.encode("utf-8")),
                "maximum_size_bytes": MAX_LOG_EVENT_BYTES,
                "original_field_count": len(fields or {}),
                "hashed_artifact_reference_count": 0,
                "omitted_artifact_reference_count": sum(
                    1 for key in (fields or {}) if _is_artifact_reference_field(key)
                ),
            }
        }
        return _serialized_payload(payload)
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
