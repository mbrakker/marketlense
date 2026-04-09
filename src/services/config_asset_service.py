from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

from src.contracts.config_assets import (
    ConfigAssetReadRequest,
    ConfigAssetReadResponse,
    ConfigAssetWriteRequest,
    ConfigAssetWriteResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.config_asset_service")


def _normalize_format(format_name: str) -> str:
    token = str(format_name or "").strip().lower()
    if token in {"yaml", "json", "text"}:
        return token
    raise AppError(
        code="config_asset_format_invalid",
        message=f"Unsupported config asset format: {format_name}",
        retryable=False,
        context={"format": format_name},
    )


def _normalize_root_type(root_type: str) -> str:
    token = str(root_type or "any").strip().lower()
    if token in {"any", "mapping", "list"}:
        return token
    raise AppError(
        code="config_asset_root_type_invalid",
        message=f"Unsupported config asset root type: {root_type}",
        retryable=False,
        context={"expected_root_type": root_type},
    )


def _payload_root_type(payload: Any) -> str:
    if payload is None:
        return "none"
    if isinstance(payload, dict):
        return "mapping"
    if isinstance(payload, list):
        return "list"
    return "scalar"


def _decode_content(content: str, *, format_name: str) -> Any:
    if format_name == "text":
        return None
    if format_name == "yaml":
        try:
            return yaml.safe_load(content) if content.strip() else None
        except yaml.YAMLError as exc:
            raise AppError(
                code="config_asset_yaml_invalid",
                message="Config asset YAML is invalid",
                cause=exc,
                retryable=False,
            ) from exc
    try:
        return json.loads(content) if content.strip() else None
    except json.JSONDecodeError as exc:
        raise AppError(
            code="config_asset_json_invalid",
            message="Config asset JSON is invalid",
            cause=exc,
            retryable=False,
        ) from exc


def _validate_root_type(payload: Any, *, expected_root_type: str, path: Path) -> str:
    root_type = _payload_root_type(payload)
    if expected_root_type == "any":
        return root_type
    if expected_root_type == "mapping" and root_type != "mapping":
        raise AppError(
            code="config_asset_root_type_mismatch",
            message=f"Expected mapping payload for config asset: {path}",
            retryable=False,
            context={"path": str(path), "root_type": root_type},
        )
    if expected_root_type == "list" and root_type != "list":
        raise AppError(
            code="config_asset_root_type_mismatch",
            message=f"Expected list payload for config asset: {path}",
            retryable=False,
            context={"path": str(path), "root_type": root_type},
        )
    return root_type


def _sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def read_config_asset(
    request: ConfigAssetReadRequest, ctx: RunContext
) -> ConfigAssetReadResponse:
    format_name = _normalize_format(request.format)
    expected_root_type = _normalize_root_type(request.expected_root_type)
    path = Path(request.path).expanduser().resolve()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="config_asset_read_start",
            module=logger.name,
            fields={
                "path": str(path),
                "format": format_name,
                "expected_root_type": expected_root_type,
            },
        )
    )
    if not path.exists():
        raise AppError(
            code="config_asset_not_found",
            message=f"Config asset not found: {path}",
            retryable=False,
            context={"path": str(path)},
        )
    try:
        content = path.read_text(encoding="utf-8")
    except Exception as exc:
        raise AppError(
            code="config_asset_read_failed",
            message=f"Failed to read config asset: {path}",
            cause=exc,
            retryable=False,
            context={"path": str(path)},
        ) from exc
    payload = _decode_content(content, format_name=format_name)
    root_type = _validate_root_type(
        payload, expected_root_type=expected_root_type, path=path
    )
    stat = path.stat()
    response = ConfigAssetReadResponse(
        schema_version="1.0",
        path=str(path),
        format=format_name,
        content=content,
        payload=payload,
        root_type=root_type,
        sha256=_sha256(content),
        size_bytes=int(stat.st_size),
        modified_utc=float(stat.st_mtime),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="config_asset_read_complete",
            module=logger.name,
            fields={
                "path": response.path,
                "format": response.format,
                "root_type": response.root_type,
                "sha256": response.sha256,
                "size_bytes": response.size_bytes,
                "modified_utc": response.modified_utc,
            },
        )
    )
    return response


def write_config_asset(
    request: ConfigAssetWriteRequest, ctx: RunContext
) -> ConfigAssetWriteResponse:
    format_name = _normalize_format(request.format)
    expected_root_type = _normalize_root_type(request.expected_root_type)
    path = Path(request.path).expanduser().resolve()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="config_asset_write_start",
            module=logger.name,
            fields={
                "path": str(path),
                "format": format_name,
                "expected_root_type": expected_root_type,
                "make_backup": request.make_backup,
                "content_length": len(request.content),
            },
        )
    )
    normalized_content = request.content.replace("\r\n", "\n")
    if normalized_content and not normalized_content.endswith("\n"):
        normalized_content = f"{normalized_content}\n"
    payload = _decode_content(normalized_content, format_name=format_name)
    root_type = _validate_root_type(
        payload, expected_root_type=expected_root_type, path=path
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    backup_path: str | None = None
    if request.make_backup and path.exists():
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = path.with_name(f"{path.name}.{stamp}.bak")
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
        backup_path = str(backup)
    try:
        path.write_text(normalized_content, encoding="utf-8")
    except Exception as exc:
        raise AppError(
            code="config_asset_write_failed",
            message=f"Failed to write config asset: {path}",
            cause=exc,
            retryable=False,
            context={"path": str(path)},
        ) from exc
    stat = path.stat()
    response = ConfigAssetWriteResponse(
        schema_version="1.0",
        path=str(path),
        format=format_name,
        root_type=root_type,
        sha256=_sha256(normalized_content),
        bytes_written=len(normalized_content.encode("utf-8")),
        modified_utc=float(stat.st_mtime),
        backup_path=backup_path,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="config_asset_write_complete",
            module=logger.name,
            fields={
                "path": response.path,
                "format": response.format,
                "root_type": response.root_type,
                "sha256": response.sha256,
                "bytes_written": response.bytes_written,
                "modified_utc": response.modified_utc,
                "backup_path": response.backup_path or "",
            },
        )
    )
    return response
