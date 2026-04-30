from __future__ import annotations

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from src.contracts.config import (
    AppConfigReadRequest,
    AppConfigReadResponse,
    AppConfigWriteRequest,
    AppConfigWriteResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.config_service.app_document")
_ATOMIC_WRITE_TEMP_TAG = ".tmp-write-"


def read_app_config_document(
    request: AppConfigReadRequest,
    ctx: RunContext,
    *,
    resolve_config_path: Callable[[str], Path],
    parse_yaml_mapping,
) -> AppConfigReadResponse:
    cfg_path = resolve_config_path(request.path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="app_config_read_start",
            module=logger.name,
            fields={"path": str(cfg_path)},
        )
    )
    if not cfg_path.exists():
        raise AppError(
            code="config_file_not_found",
            message=f"Config file not found: {cfg_path}",
            retryable=False,
            context={"path": str(cfg_path)},
        )
    try:
        content = cfg_path.read_text(encoding="utf-8")
    except Exception as exc:
        raise AppError(
            code="config_read_failed",
            message=f"Failed to read config file: {cfg_path}",
            cause=exc,
            retryable=False,
            context={"path": str(cfg_path)},
        ) from exc
    payload = _parse_config_payload(
        content=content,
        cfg_path=cfg_path,
        parse_yaml_mapping=parse_yaml_mapping,
    )
    stat = cfg_path.stat()
    response = AppConfigReadResponse(
        schema_version="1.0",
        path=str(cfg_path),
        content=content,
        payload=payload,
        size_bytes=int(stat.st_size),
        modified_utc=float(stat.st_mtime),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="app_config_read_complete",
            module=logger.name,
            fields={
                "path": response.path,
                "size_bytes": response.size_bytes,
                "modified_utc": response.modified_utc,
                "top_level_keys": list(payload.keys()),
            },
        )
    )
    return response


def write_app_config_document(
    request: AppConfigWriteRequest,
    ctx: RunContext,
    *,
    resolve_config_path: Callable[[str], Path],
    parse_yaml_mapping,
) -> AppConfigWriteResponse:
    cfg_path = resolve_config_path(request.path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="app_config_write_start",
            module=logger.name,
            fields={
                "path": str(cfg_path),
                "make_backup": request.make_backup,
                "content_length": len(request.content),
            },
        )
    )
    normalized_content = request.content.replace("\r\n", "\n")
    if normalized_content and not normalized_content.endswith("\n"):
        normalized_content = f"{normalized_content}\n"
    payload = _parse_config_payload(
        content=normalized_content,
        cfg_path=cfg_path,
        parse_yaml_mapping=parse_yaml_mapping,
    )

    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    backup_path = _write_backup_if_requested(
        cfg_path=cfg_path,
        make_backup=request.make_backup,
    )
    try:
        _atomic_write_text(cfg_path, normalized_content)
    except Exception as exc:
        raise AppError(
            code="config_write_failed",
            message=f"Failed to write config file: {cfg_path}",
            cause=exc,
            retryable=False,
            context={"path": str(cfg_path)},
        ) from exc

    stat = cfg_path.stat()
    response = AppConfigWriteResponse(
        schema_version="1.0",
        path=str(cfg_path),
        bytes_written=len(normalized_content.encode("utf-8")),
        modified_utc=float(stat.st_mtime),
        top_level_keys=[str(key) for key in payload.keys()],
        backup_path=backup_path,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="app_config_write_complete",
            module=logger.name,
            fields={
                "path": response.path,
                "bytes_written": response.bytes_written,
                "modified_utc": response.modified_utc,
                "backup_path": response.backup_path or "",
                "top_level_keys": response.top_level_keys,
            },
        )
    )
    return response


def _parse_config_payload(*, content: str, cfg_path: Path, parse_yaml_mapping) -> dict:
    try:
        return parse_yaml_mapping(content, label="Config", path=cfg_path)
    except Exception as exc:
        kind = str(getattr(exc, "kind", "") or "")
        if kind == "invalid":
            raise AppError(
                code="config_yaml_invalid",
                message=f"Config YAML invalid: {cfg_path}",
                cause=getattr(exc, "cause", None) or exc,
                retryable=False,
                context={"path": str(cfg_path)},
            ) from exc
        raise AppError(
            code="config_yaml_root_invalid",
            message=f"Config YAML root must be a mapping: {cfg_path}",
            retryable=False,
            context={
                "path": str(cfg_path),
                "root_type": str(getattr(exc, "root_type", "") or ""),
            },
        ) from exc


def _write_backup_if_requested(*, cfg_path: Path, make_backup: bool) -> str | None:
    if not make_backup or not cfg_path.exists():
        return None
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = cfg_path.with_name(f"{cfg_path.name}.{stamp}.bak")
    backup.write_text(cfg_path.read_text(encoding="utf-8"), encoding="utf-8")
    return str(backup)


def _atomic_write_text(path: Path, content: str) -> None:
    temp_path = path.with_name(
        f"{path.name}{_ATOMIC_WRITE_TEMP_TAG}{os.getpid()}-{time.time_ns()}"
    )
    try:
        with temp_path.open("w", encoding="utf-8", newline="") as file_obj:
            file_obj.write(content)
            file_obj.flush()
            os.fsync(file_obj.fileno())
        os.replace(temp_path, path)
    except Exception:
        try:
            temp_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
