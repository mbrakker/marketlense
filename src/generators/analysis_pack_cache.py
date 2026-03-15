from __future__ import annotations

"""Shared generator-layer loader for cached analysis packs.

This centralizes the repeated resolve-path, read, decode, and cache-key-match
flow while leaving pack-specific validation and typed response adaptation in the
calling generator.
"""

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generic, Optional, TypeVar

from src.contracts.files import ReadTextRequest
from src.contracts.run_context import RunContext
from src.utils.errors import AppError

T = TypeVar("T")


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
        metadata={"doc": "Resolved cached pack path when the cache path was evaluated."},
    )
    value: Optional[T] = field(
        default=None,
        metadata={"doc": "Typed cached value when the cache load is a hit."},
    )


def load_cached_pack(
    *,
    cache_key: str,
    ctx: RunContext,
    resolve_path: Callable[[], str],
    read_text: Callable[[ReadTextRequest, RunContext], Any],
    on_read_failed: Callable[[AppError, str], None],
    adapt_payload: Callable[[Dict[str, Any], str], CachedPackAdaptResult[T]],
) -> CachedPackLoadResult[T]:
    if not cache_key:
        return CachedPackLoadResult(
            schema_version="1.0",
            status="cache_disabled",
            path=None,
        )

    path = resolve_path()
    try:
        response = read_text(ReadTextRequest(schema_version="1.0", path=path), ctx)
    except AppError as exc:
        if exc.code == "file_not_found":
            return CachedPackLoadResult(
                schema_version="1.0",
                status="file_not_found",
                path=path,
            )
        on_read_failed(exc, path)
        return CachedPackLoadResult(
            schema_version="1.0",
            status="read_failed",
            path=path,
        )

    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError:
        return CachedPackLoadResult(
            schema_version="1.0",
            status="invalid_json",
            path=path,
        )
    if not isinstance(payload, dict):
        return CachedPackLoadResult(
            schema_version="1.0",
            status="invalid_payload",
            path=path,
        )

    cached_meta = payload.get("_cache") if isinstance(payload.get("_cache"), dict) else {}
    if cached_meta.get("key") != cache_key:
        return CachedPackLoadResult(
            schema_version="1.0",
            status="key_mismatch",
            path=path,
        )

    adapted = adapt_payload(payload, path)
    return CachedPackLoadResult(
        schema_version="1.0",
        status=adapted.status,
        path=path,
        value=adapted.value,
    )
