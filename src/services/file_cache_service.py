from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict
from pathlib import Path

from src.contracts.file_cache import (
    FileCacheMd5SidecarRecord,
    FileCacheMd5SidecarResolveRequest,
    FileCacheMd5SidecarResolveResponse,
    FileCacheMd5SidecarWriteRequest,
    FileCacheMd5SidecarWriteResponse,
)
from src.contracts.run_context import RunContext
from src.utils.coercion import coerce_float
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.file_cache_service")
MD5_SIDECAR_SCHEMA_VERSION = "1.0"
MD5_SIDECAR_SUFFIX = ".md5.json"
_MD5_RX = re.compile(r"^[0-9a-fA-F]{32}$")


def resolve_md5_sidecar(
    request: FileCacheMd5SidecarResolveRequest,
    ctx: RunContext,
) -> FileCacheMd5SidecarResolveResponse:
    sidecar_path = _sidecar_path(request.cache_path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="md5_sidecar_resolve_start",
            module=logger.name,
            fields={
                "file_id": request.file_id,
                "cache_path": request.cache_path,
                "sidecar_path": sidecar_path,
                "size_bytes": request.size_bytes,
                "mtime_utc": request.mtime_utc,
            },
        )
    )
    path = Path(sidecar_path)
    if not path.exists():
        return _resolve_response(
            request=request,
            sidecar_path=sidecar_path,
            sidecar_exists=False,
            record=None,
            resolved_md5=None,
            hit=False,
            reason="missing",
            ctx=ctx,
        )
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return _resolve_response(
            request=request,
            sidecar_path=sidecar_path,
            sidecar_exists=True,
            record=None,
            resolved_md5=None,
            hit=False,
            reason="read_failed",
            ctx=ctx,
            extra_fields={"error": str(exc)},
        )
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as exc:
        return _resolve_response(
            request=request,
            sidecar_path=sidecar_path,
            sidecar_exists=True,
            record=None,
            resolved_md5=None,
            hit=False,
            reason="invalid_json",
            ctx=ctx,
            extra_fields={"error": str(exc)},
        )
    if not isinstance(payload, dict):
        return _resolve_response(
            request=request,
            sidecar_path=sidecar_path,
            sidecar_exists=True,
            record=None,
            resolved_md5=None,
            hit=False,
            reason="invalid_payload",
            ctx=ctx,
        )
    record = _record_from_payload(payload, request.file_id)
    if record is None:
        return _resolve_response(
            request=request,
            sidecar_path=sidecar_path,
            sidecar_exists=True,
            record=None,
            resolved_md5=None,
            hit=False,
            reason="invalid_payload",
            ctx=ctx,
        )
    observed_mtime = _normalize_mtime(request.mtime_utc)
    if request.size_bytes is None:
        return _resolve_response(
            request=request,
            sidecar_path=sidecar_path,
            sidecar_exists=True,
            record=record,
            resolved_md5=None,
            hit=False,
            reason="size_missing",
            ctx=ctx,
        )
    if record.size_bytes != int(request.size_bytes):
        return _resolve_response(
            request=request,
            sidecar_path=sidecar_path,
            sidecar_exists=True,
            record=record,
            resolved_md5=None,
            hit=False,
            reason="size_mismatch",
            ctx=ctx,
        )
    if observed_mtime is None:
        return _resolve_response(
            request=request,
            sidecar_path=sidecar_path,
            sidecar_exists=True,
            record=record,
            resolved_md5=None,
            hit=False,
            reason="mtime_missing",
            ctx=ctx,
        )
    if record.mtime_utc != observed_mtime:
        return _resolve_response(
            request=request,
            sidecar_path=sidecar_path,
            sidecar_exists=True,
            record=record,
            resolved_md5=None,
            hit=False,
            reason="mtime_mismatch",
            ctx=ctx,
        )
    return _resolve_response(
        request=request,
        sidecar_path=sidecar_path,
        sidecar_exists=True,
        record=record,
        resolved_md5=record.md5,
        hit=True,
        reason="matched",
        ctx=ctx,
    )


def write_md5_sidecar(
    request: FileCacheMd5SidecarWriteRequest,
    ctx: RunContext,
) -> FileCacheMd5SidecarWriteResponse:
    sidecar_path = _sidecar_path(request.cache_path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="md5_sidecar_write_start",
            module=logger.name,
            fields={
                "file_id": request.file_id,
                "cache_path": request.cache_path,
                "sidecar_path": sidecar_path,
                "md5": request.md5 or "",
                "size_bytes": request.size_bytes,
                "mtime_utc": request.mtime_utc,
            },
        )
    )
    normalized_mtime = _normalize_mtime(request.mtime_utc)
    normalized_md5 = _normalize_md5(request.md5)
    if normalized_md5 is None or request.size_bytes is None or normalized_mtime is None:
        response = FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=sidecar_path,
            record=None,
            written=False,
            reason="incomplete_metadata",
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="md5_sidecar_write_complete",
                module=logger.name,
                fields={
                    "file_id": request.file_id,
                    "sidecar_path": sidecar_path,
                    "written": False,
                    "reason": response.reason,
                },
            )
        )
        return response
    file_id = str(request.file_id or "").strip()
    if not file_id:
        raise AppError(
            code="md5_sidecar_file_id_missing",
            message="file_id is required for md5 sidecar writes",
            retryable=False,
            context={"cache_path": request.cache_path},
        )
    record = FileCacheMd5SidecarRecord(
        schema_version=MD5_SIDECAR_SCHEMA_VERSION,
        file_id=file_id,
        name=str(request.file_name or "").strip(),
        md5=normalized_md5,
        size_bytes=int(request.size_bytes),
        mtime_utc=normalized_mtime,
    )
    path = Path(sidecar_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(json.dumps(asdict(record), ensure_ascii=True), encoding="utf-8")
    except OSError as exc:
        raise AppError(
            code="md5_sidecar_write_failed",
            message=f"Failed to write md5 sidecar: {sidecar_path}",
            cause=exc,
            retryable=False,
            context={"cache_path": request.cache_path, "sidecar_path": sidecar_path},
        ) from exc
    response = FileCacheMd5SidecarWriteResponse(
        schema_version="1.0",
        cache_path=request.cache_path,
        sidecar_path=sidecar_path,
        record=record,
        written=True,
        reason="written",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="md5_sidecar_write_complete",
            module=logger.name,
            fields={
                "file_id": request.file_id,
                "sidecar_path": sidecar_path,
                "written": True,
                "md5": record.md5,
                "size_bytes": record.size_bytes,
            },
        )
    )
    return response


def _record_from_payload(
    payload: dict,
    request_file_id: str,
) -> FileCacheMd5SidecarRecord | None:
    normalized_md5 = _normalize_md5(payload.get("md5"))
    if normalized_md5 is None:
        return None
    try:
        size_bytes = int(str(payload.get("size_bytes")))
    except (TypeError, ValueError):
        return None
    normalized_mtime = _normalize_mtime(payload.get("mtime_utc"))
    if normalized_mtime is None:
        return None
    return FileCacheMd5SidecarRecord(
        schema_version=str(payload.get("schema_version") or MD5_SIDECAR_SCHEMA_VERSION),
        file_id=str(payload.get("file_id") or request_file_id).strip(),
        name=str(payload.get("name") or "").strip(),
        md5=normalized_md5,
        size_bytes=size_bytes,
        mtime_utc=normalized_mtime,
    )


def _resolve_response(
    *,
    request: FileCacheMd5SidecarResolveRequest,
    sidecar_path: str,
    sidecar_exists: bool,
    record: FileCacheMd5SidecarRecord | None,
    resolved_md5: str | None,
    hit: bool,
    reason: str,
    ctx: RunContext,
    extra_fields: dict | None = None,
) -> FileCacheMd5SidecarResolveResponse:
    response = FileCacheMd5SidecarResolveResponse(
        schema_version="1.0",
        cache_path=request.cache_path,
        sidecar_path=sidecar_path,
        sidecar_exists=sidecar_exists,
        record=record,
        resolved_md5=resolved_md5,
        hit=hit,
        reason=reason,
    )
    fields = {
        "file_id": request.file_id,
        "cache_path": request.cache_path,
        "sidecar_path": sidecar_path,
        "sidecar_exists": sidecar_exists,
        "hit": hit,
        "reason": reason,
        "resolved_md5": resolved_md5 or "",
    }
    if record is not None:
        fields["record_md5"] = record.md5
        fields["record_size_bytes"] = record.size_bytes
        fields["record_mtime_utc"] = record.mtime_utc
    if extra_fields:
        fields.update(extra_fields)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="md5_sidecar_resolve_complete",
            module=logger.name,
            fields=fields,
        )
    )
    return response


def _sidecar_path(cache_path: str) -> str:
    token = str(cache_path or "").strip()
    if not token:
        raise AppError(
            code="md5_sidecar_cache_path_invalid",
            message="cache_path is required for md5 sidecar operations",
            retryable=False,
        )
    return f"{token}{MD5_SIDECAR_SUFFIX}"


def _normalize_md5(value: object) -> str | None:
    token = str(value or "").strip()
    if not token:
        return None
    if not _MD5_RX.fullmatch(token):
        return None
    return token.lower()


def _normalize_mtime(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(coerce_float(value))
    except (TypeError, ValueError):
        return None
