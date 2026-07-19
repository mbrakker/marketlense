"""Shared generator-layer loader for cached analysis packs.

This centralizes the repeated resolve-path, read, decode, and cache-key-match
flow while leaving pack-specific validation and typed response adaptation in the
calling generator.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

from src.contracts.files import ReadTextRequest
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

T = TypeVar("T")
logger = logging.getLogger("market_lense.analysis_pack_cache")


@dataclass(frozen=True)
class CachedPackAdaptResult(Generic[T]):
    schema_version: str = field(
        metadata={"doc": "Cached analysis-pack adaptation schema version."}
    )
    status: str = field(
        metadata={"doc": "Typed adaptation status, such as 'hit' or 'schema_invalid'."}
    )
    value: Optional[T] = field(
        default=None,
        metadata={"doc": "Typed cached value produced by the caller adapter."},
    )


@dataclass(frozen=True)
class CachedPackLoadResult(Generic[T]):
    schema_version: str = field(
        metadata={"doc": "Cached analysis-pack load schema version."}
    )
    status: str = field(
        metadata={
            "doc": "Cache load status, such as 'file_not_found', 'invalid_json', or 'hit'."
        }
    )
    path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Resolved cached pack path when the cache path was evaluated."
        },
    )
    value: Optional[T] = field(
        default=None,
        metadata={"doc": "Typed cached value when the cache load is a hit."},
    )
    status_code: str = field(
        default="",
        metadata={"doc": "Stable artifact status code for corruption recovery."},
    )


def _log_cache_status(
    *,
    ctx: RunContext,
    artifact_kind: str,
    path: str | None,
    status_code: str,
    recovery_policy: str,
    detail: str = "",
) -> None:
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="analysis_pack_cache_status",
            module=logger.name,
            fields={
                "artifact_kind": artifact_kind,
                "path": path or "",
                "status_code": status_code,
                "recovery_policy": recovery_policy,
                "detail": detail,
            },
        )
    )


def _cache_meta_expired(cached_meta: dict[str, Any]) -> bool:
    raw_expires_at = str(
        cached_meta.get("expires_at_utc") or cached_meta.get("expires_at") or ""
    ).strip()
    if not raw_expires_at:
        return False
    try:
        expires_at = datetime.fromisoformat(raw_expires_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    return expires_at <= datetime.now(timezone.utc)


def load_cached_pack(
    *,
    cache_key: str,
    ctx: RunContext,
    resolve_path: Callable[[], str],
    read_text: Callable[[ReadTextRequest, RunContext], Any],
    on_read_failed: Callable[[AppError, str], None],
    adapt_payload: Callable[[Dict[str, Any], str], CachedPackAdaptResult[T]],
    cache_meta_matcher: Callable[[dict[str, Any]], tuple[bool, str]] | None = None,
    artifact_kind: str = "analysis_pack",
) -> CachedPackLoadResult[T]:
    if not cache_key:
        _log_cache_status(
            ctx=ctx,
            artifact_kind=artifact_kind,
            path=None,
            status_code="cache_disabled",
            recovery_policy="regenerate",
        )
        return CachedPackLoadResult(
            schema_version="1.0",
            status="cache_disabled",
            path=None,
            status_code="cache_disabled",
        )

    path = resolve_path()
    try:
        response = read_text(ReadTextRequest(schema_version="1.0", path=path), ctx)
    except AppError as exc:
        if exc.code == "file_not_found":
            _log_cache_status(
                ctx=ctx,
                artifact_kind=artifact_kind,
                path=path,
                status_code="missing",
                recovery_policy="regenerate",
            )
            return CachedPackLoadResult(
                schema_version="1.0",
                status="file_not_found",
                path=path,
                status_code="missing",
            )
        on_read_failed(exc, path)
        if exc.retryable:
            raise
        _log_cache_status(
            ctx=ctx,
            artifact_kind=artifact_kind,
            path=path,
            status_code="read_failed",
            recovery_policy="regenerate",
            detail=exc.code,
        )
        return CachedPackLoadResult(
            schema_version="1.0",
            status="read_failed",
            path=path,
            status_code="read_failed",
        )

    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        _log_cache_status(
            ctx=ctx,
            artifact_kind=artifact_kind,
            path=path,
            status_code="invalid_json",
            recovery_policy="regenerate",
            detail=str(exc),
        )
        return CachedPackLoadResult(
            schema_version="1.0",
            status="invalid_json",
            path=path,
            status_code="invalid_json",
        )
    if not isinstance(payload, dict):
        _log_cache_status(
            ctx=ctx,
            artifact_kind=artifact_kind,
            path=path,
            status_code="invalid_schema",
            recovery_policy="regenerate",
            detail=type(payload).__name__,
        )
        return CachedPackLoadResult(
            schema_version="1.0",
            status="invalid_payload",
            path=path,
            status_code="invalid_schema",
        )

    raw_cache_meta = payload.get("_cache")
    cached_meta: dict[str, Any] = (
        raw_cache_meta if isinstance(raw_cache_meta, dict) else {}
    )
    cache_matches = cached_meta.get("key") == cache_key
    mismatch_reason = "key_mismatch"
    if cache_meta_matcher is not None:
        cache_matches, mismatch_reason = cache_meta_matcher(cached_meta)
    if not cache_matches:
        _log_cache_status(
            ctx=ctx,
            artifact_kind=artifact_kind,
            path=path,
            status_code=mismatch_reason or "key_mismatch",
            recovery_policy="regenerate",
        )
        return CachedPackLoadResult(
            schema_version="1.0",
            status=mismatch_reason or "key_mismatch",
            path=path,
            status_code=mismatch_reason or "key_mismatch",
        )
    if _cache_meta_expired(cached_meta):
        _log_cache_status(
            ctx=ctx,
            artifact_kind=artifact_kind,
            path=path,
            status_code="expired",
            recovery_policy="regenerate",
        )
        return CachedPackLoadResult(
            schema_version="1.0",
            status="expired",
            path=path,
            status_code="expired",
        )

    adapted = adapt_payload(payload, path)
    if adapted.status != "hit":
        _log_cache_status(
            ctx=ctx,
            artifact_kind=artifact_kind,
            path=path,
            status_code=adapted.status,
            recovery_policy="regenerate",
        )
    return CachedPackLoadResult(
        schema_version="1.0",
        status=adapted.status,
        path=path,
        value=adapted.value,
        status_code=adapted.status,
    )
