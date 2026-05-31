from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import List

from src.contracts.files import (
    DeleteFileRequest,
    DeleteFileResponse,
    DirectoryEntry,
    FileExistsRequest,
    FileExistsResponse,
    FileHashRequest,
    FileHashResponse,
    FileStatRequest,
    FileStatResponse,
    ListDirectoryRequest,
    ListDirectoryResponse,
    ListHtmlRequest,
    ListHtmlResponse,
    PipelineCheckpointReadRequest,
    PipelineCheckpointReadResponse,
    PipelineCheckpointWriteRequest,
    PipelineCheckpointWriteResponse,
    PipelineStageCheckpoint,
    PdfCacheTextReadRequest,
    PdfCacheTextReadResponse,
    ReadBytesRequest,
    ReadBytesResponse,
    ReadTextRequest,
    ReadTextResponse,
    WriteBytesRequest,
    WriteBytesResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.file_service")
_WINDOWS_ABSOLUTE_PATH_RX = re.compile(r"^[A-Za-z]:[\\/]")
_PDF_CACHE_MD5_RX = re.compile(r"^[0-9a-fA-F]{32}$")
_PIPELINE_CHECKPOINT_TOKEN_RX = re.compile(r"^[A-Za-z0-9_.=-]+$")
_PIPELINE_CHECKPOINT_SCHEMA_VERSION = "1.0"
_PIPELINE_CHECKPOINT_DIR = ".checkpoints"
_ATOMIC_WRITE_STALE_SECONDS = 3600.0
_ATOMIC_WRITE_TEMP_TAG = ".tmp-write-"


def _normalize_glob_pattern(raw_pattern: str) -> str:
    pattern = str(raw_pattern or "").strip() or "*"
    normalized = pattern.replace("\\", "/")
    if normalized.startswith("/") or _WINDOWS_ABSOLUTE_PATH_RX.match(pattern):
        raise AppError(
            code="directory_glob_invalid",
            message="Directory glob pattern must be relative to root_dir",
            retryable=False,
            context={"glob_pattern": pattern},
        )
    if any(part == ".." for part in normalized.split("/")):
        raise AppError(
            code="directory_glob_invalid",
            message="Directory glob pattern must not escape root_dir",
            retryable=False,
            context={"glob_pattern": pattern},
        )
    return pattern


def _require_pdf_cache_md5(raw_md5: str) -> str:
    token = str(raw_md5 or "").strip()
    if not _PDF_CACHE_MD5_RX.fullmatch(token):
        raise AppError(
            code="pdf_cache_md5_invalid",
            message="PDF cache md5 key must be a 32-character hexadecimal digest",
            retryable=False,
            context={"md5": token},
        )
    return token.lower()


def _require_checkpoint_token(raw_value: str, field_name: str) -> str:
    token = str(raw_value or "").strip()
    if not token or not _PIPELINE_CHECKPOINT_TOKEN_RX.fullmatch(token):
        raise AppError(
            code="pipeline_checkpoint_key_invalid",
            message=f"Pipeline checkpoint {field_name} is invalid",
            retryable=False,
            context={field_name: token},
        )
    return token


def _pipeline_checkpoint_path(
    checkpoint_root: str,
    pipeline_name: str,
    file_id: str,
    stage_name: str,
) -> Path:
    root = Path(checkpoint_root).expanduser().resolve()
    pipeline_token = _require_checkpoint_token(pipeline_name, "pipeline_name")
    file_token = _require_checkpoint_token(file_id, "file_id")
    stage_token = _require_checkpoint_token(stage_name, "stage_name")
    return (
        root
        / _PIPELINE_CHECKPOINT_DIR
        / pipeline_token
        / file_token
        / f"{stage_token}.json"
    )


def _checkpoint_to_payload(checkpoint: PipelineStageCheckpoint) -> dict:
    return {
        "schema_version": checkpoint.schema_version,
        "pipeline_name": checkpoint.pipeline_name,
        "file_id": checkpoint.file_id,
        "report_slug": checkpoint.report_slug,
        "stage_name": checkpoint.stage_name,
        "stage_status": checkpoint.stage_status,
        "artifact_refs": dict(checkpoint.artifact_refs),
        "payload": dict(checkpoint.payload),
        "completed_at_utc": checkpoint.completed_at_utc,
        "source_run_id": checkpoint.source_run_id,
        "source_task_id": checkpoint.source_task_id,
    }


def _checkpoint_from_payload(payload: object) -> PipelineStageCheckpoint:
    if not isinstance(payload, dict):
        raise AppError(
            code="pipeline_checkpoint_invalid",
            message="Pipeline checkpoint payload must be a JSON object",
            retryable=False,
        )
    schema_version = str(payload.get("schema_version") or "").strip()
    artifact_refs = payload.get("artifact_refs")
    checkpoint_payload = payload.get("payload")
    if schema_version != _PIPELINE_CHECKPOINT_SCHEMA_VERSION:
        raise AppError(
            code="pipeline_checkpoint_invalid",
            message="Pipeline checkpoint schema version is unsupported",
            retryable=False,
            context={"schema_version": schema_version},
        )
    if not isinstance(artifact_refs, dict) or not isinstance(checkpoint_payload, dict):
        raise AppError(
            code="pipeline_checkpoint_invalid",
            message="Pipeline checkpoint artifact_refs and payload must be objects",
            retryable=False,
        )
    return PipelineStageCheckpoint(
        schema_version=schema_version,
        pipeline_name=_require_checkpoint_token(
            str(payload.get("pipeline_name") or ""), "pipeline_name"
        ),
        file_id=_require_checkpoint_token(str(payload.get("file_id") or ""), "file_id"),
        report_slug=str(payload.get("report_slug") or "").strip(),
        stage_name=_require_checkpoint_token(
            str(payload.get("stage_name") or ""), "stage_name"
        ),
        stage_status=str(payload.get("stage_status") or "").strip(),
        artifact_refs={str(k): str(v) for k, v in artifact_refs.items()},
        payload=checkpoint_payload,
        completed_at_utc=str(payload.get("completed_at_utc") or "").strip(),
        source_run_id=str(payload.get("source_run_id") or "").strip(),
        source_task_id=str(payload.get("source_task_id") or "").strip(),
    )


def read_text(request: ReadTextRequest, ctx: RunContext) -> ReadTextResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="read_text_start",
            module=logger.name,
            fields={"path": request.path},
        )
    )
    try:
        content = Path(request.path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AppError(
            code="file_not_found",
            message=f"File not found: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    except (OSError, UnicodeDecodeError) as exc:
        raise AppError(
            code="file_read_failed",
            message=f"Failed to read text file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc

    logger.info(
        log_event(
            ctx,
            role="service",
            event="read_text_complete",
            module=logger.name,
            fields={"path": request.path, "length": len(content)},
        )
    )
    return ReadTextResponse(schema_version="1.0", path=request.path, content=content)


def read_bytes(request: ReadBytesRequest, ctx: RunContext) -> ReadBytesResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="read_bytes_start",
            module=logger.name,
            fields={"path": request.path},
        )
    )
    try:
        content = Path(request.path).read_bytes()
    except FileNotFoundError as exc:
        raise AppError(
            code="file_not_found",
            message=f"File not found: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    except OSError as exc:
        raise AppError(
            code="file_read_failed",
            message=f"Failed to read binary file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc

    logger.info(
        log_event(
            ctx,
            role="service",
            event="read_bytes_complete",
            module=logger.name,
            fields={"path": request.path, "length": len(content)},
        )
    )
    return ReadBytesResponse(schema_version="1.0", path=request.path, content=content)


def list_html(request: ListHtmlRequest, ctx: RunContext) -> ListHtmlResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="list_html_start",
            module=logger.name,
            fields={"root_dir": request.root_dir},
        )
    )
    root = Path(request.root_dir)
    if not root.exists():
        raise AppError(
            code="output_dir_missing",
            message=f"Output dir does not exist: {request.root_dir}",
            retryable=False,
        )
    html_paths: List[str] = [str(p) for p in sorted(root.glob("*.html"))]
    logger.info(
        log_event(
            ctx,
            role="service",
            event="list_html_complete",
            module=logger.name,
            fields={"count": len(html_paths)},
        )
    )
    return ListHtmlResponse(
        schema_version="1.0",
        root_dir=request.root_dir,
        html_paths=html_paths,
    )


def list_directory(
    request: ListDirectoryRequest, ctx: RunContext
) -> ListDirectoryResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="list_directory_start",
            module=logger.name,
            fields={
                "root_dir": request.root_dir,
                "glob_pattern": request.glob_pattern,
                "recursive": request.recursive,
                "include_files": request.include_files,
                "include_dirs": request.include_dirs,
                "limit": request.limit,
            },
        )
    )
    root = Path(request.root_dir).expanduser().resolve()
    if not root.exists():
        raise AppError(
            code="directory_not_found",
            message=f"Directory not found: {request.root_dir}",
            retryable=False,
        )
    pattern = _normalize_glob_pattern(request.glob_pattern)
    limit = request.limit if request.limit > 0 else 500
    iterator = root.rglob(pattern) if request.recursive else root.glob(pattern)
    entries: list[DirectoryEntry] = []
    for entry in iterator:
        is_dir = entry.is_dir()
        if is_dir and not request.include_dirs:
            continue
        if (not is_dir) and not request.include_files:
            continue
        stat = entry.stat()
        entries.append(
            DirectoryEntry(
                schema_version="1.0",
                path=str(entry),
                name=entry.name,
                is_dir=is_dir,
                size_bytes=None if is_dir else int(stat.st_size),
                mtime_utc=float(stat.st_mtime),
            )
        )
        if len(entries) >= limit:
            break
    entries.sort(key=lambda item: item.path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="list_directory_complete",
            module=logger.name,
            fields={"root_dir": request.root_dir, "count": len(entries)},
        )
    )
    return ListDirectoryResponse(
        schema_version="1.0",
        root_dir=request.root_dir,
        entries=entries,
    )


def file_exists(request: FileExistsRequest, ctx: RunContext) -> FileExistsResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="file_exists_start",
            module=logger.name,
            fields={"path": request.path},
        )
    )
    exists = Path(request.path).exists()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="file_exists_complete",
            module=logger.name,
            fields={"path": request.path, "exists": exists},
        )
    )
    return FileExistsResponse(schema_version="1.0", path=request.path, exists=exists)


def write_bytes(request: WriteBytesRequest, ctx: RunContext) -> WriteBytesResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="write_bytes_start",
            module=logger.name,
            fields={"path": request.path, "size": len(request.content)},
        )
    )
    path = Path(request.path)
    if request.make_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _atomic_write_bytes(path, request.content)
    except OSError as exc:
        raise AppError(
            code="file_write_failed",
            message=f"Failed to write binary file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    md5 = _md5_bytes(request.content)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="write_bytes_complete",
            module=logger.name,
            fields={"path": request.path, "md5": md5},
        )
    )
    return WriteBytesResponse(
        schema_version="1.0",
        path=request.path,
        bytes_written=len(request.content),
        md5=md5,
    )


def write_pipeline_checkpoint(
    request: PipelineCheckpointWriteRequest,
    ctx: RunContext,
) -> PipelineCheckpointWriteResponse:
    checkpoint = request.checkpoint
    path = _pipeline_checkpoint_path(
        request.checkpoint_root,
        checkpoint.pipeline_name,
        checkpoint.file_id,
        checkpoint.stage_name,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pipeline_checkpoint_write_start",
            module=logger.name,
            fields={
                "checkpoint_root": request.checkpoint_root,
                "pipeline_name": checkpoint.pipeline_name,
                "file_id": checkpoint.file_id,
                "stage_name": checkpoint.stage_name,
                "stage_status": checkpoint.stage_status,
                "artifact_ref_count": len(checkpoint.artifact_refs),
            },
        )
    )
    if checkpoint.schema_version != _PIPELINE_CHECKPOINT_SCHEMA_VERSION:
        raise AppError(
            code="pipeline_checkpoint_invalid",
            message="Pipeline checkpoint schema version is unsupported",
            retryable=False,
            context={"schema_version": checkpoint.schema_version},
        )
    if checkpoint.stage_status not in {"completed", "failed"}:
        raise AppError(
            code="pipeline_checkpoint_invalid",
            message="Pipeline checkpoint stage_status must be completed or failed",
            retryable=False,
            context={"stage_status": checkpoint.stage_status},
        )
    payload = _checkpoint_to_payload(checkpoint)
    content = (
        json.dumps(payload, ensure_ascii=True, sort_keys=True, indent=2) + "\n"
    ).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        _atomic_write_bytes(path, content)
    except OSError as exc:
        raise AppError(
            code="pipeline_checkpoint_write_failed",
            message=f"Failed to write pipeline checkpoint: {path}",
            cause=exc,
            retryable=False,
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pipeline_checkpoint_write_complete",
            module=logger.name,
            fields={
                "checkpoint_path": str(path),
                "pipeline_name": checkpoint.pipeline_name,
                "file_id": checkpoint.file_id,
                "stage_name": checkpoint.stage_name,
                "bytes_written": len(content),
            },
        )
    )
    return PipelineCheckpointWriteResponse(
        schema_version="1.0",
        checkpoint_path=str(path),
        bytes_written=len(content),
    )


def read_pipeline_checkpoint(
    request: PipelineCheckpointReadRequest,
    ctx: RunContext,
) -> PipelineCheckpointReadResponse:
    path = _pipeline_checkpoint_path(
        request.checkpoint_root,
        request.pipeline_name,
        request.file_id,
        request.stage_name,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pipeline_checkpoint_read_start",
            module=logger.name,
            fields={
                "checkpoint_root": request.checkpoint_root,
                "pipeline_name": request.pipeline_name,
                "file_id": request.file_id,
                "stage_name": request.stage_name,
            },
        )
    )
    if not path.exists():
        logger.info(
            log_event(
                ctx,
                role="service",
                event="pipeline_checkpoint_read_complete",
                module=logger.name,
                fields={"checkpoint_path": str(path), "found": False},
            )
        )
        return PipelineCheckpointReadResponse(
            schema_version="1.0",
            checkpoint_path=str(path),
            found=False,
            checkpoint=None,
        )
    try:
        raw_payload = json.loads(path.read_text(encoding="utf-8"))
        checkpoint = _checkpoint_from_payload(raw_payload)
    except AppError:
        raise
    except (OSError, json.JSONDecodeError) as exc:
        raise AppError(
            code="pipeline_checkpoint_read_failed",
            message=f"Failed to read pipeline checkpoint: {path}",
            cause=exc,
            retryable=False,
            context={"checkpoint_path": str(path)},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pipeline_checkpoint_read_complete",
            module=logger.name,
            fields={
                "checkpoint_path": str(path),
                "pipeline_name": checkpoint.pipeline_name,
                "file_id": checkpoint.file_id,
                "stage_name": checkpoint.stage_name,
                "found": True,
                "artifact_ref_count": len(checkpoint.artifact_refs),
            },
        )
    )
    return PipelineCheckpointReadResponse(
        schema_version="1.0",
        checkpoint_path=str(path),
        found=True,
        checkpoint=checkpoint,
    )


def _atomic_write_bytes(path: Path, content: bytes) -> None:
    _cleanup_stale_atomic_temp_files(path)
    temp_path = _atomic_temp_path(path)
    try:
        with temp_path.open("wb") as file_obj:
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


def _atomic_temp_path(path: Path) -> Path:
    token = f"{os.getpid()}-{time.time_ns()}"
    name_hash = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:16]
    return path.with_name(f".{name_hash}{_ATOMIC_WRITE_TEMP_TAG}{token}")


def _cleanup_stale_atomic_temp_files(path: Path) -> None:
    now = time.time()
    name_hash = hashlib.sha256(path.name.encode("utf-8")).hexdigest()[:16]
    patterns = (
        f".{name_hash}{_ATOMIC_WRITE_TEMP_TAG}*",
        f"{path.name}{_ATOMIC_WRITE_TEMP_TAG}*",
    )
    for pattern in patterns:
        for candidate in path.parent.glob(pattern):
            _cleanup_stale_atomic_temp_file(candidate, now)


def _cleanup_stale_atomic_temp_file(candidate: Path, now: float) -> None:
    try:
        if not candidate.is_file():
            return
        age_seconds = now - candidate.stat().st_mtime
        if age_seconds < _ATOMIC_WRITE_STALE_SECONDS:
            return
        candidate.unlink(missing_ok=True)
    except OSError:
        return


def file_md5(request: FileHashRequest, ctx: RunContext) -> FileHashResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="file_md5_start",
            module=logger.name,
            fields={"path": request.path},
        )
    )
    path = Path(request.path)
    if not path.exists():
        raise AppError(
            code="file_not_found",
            message=f"File not found: {request.path}",
            retryable=False,
        )
    try:
        md5 = _md5_file(path)
    except OSError as exc:
        raise AppError(
            code="file_hash_failed",
            message=f"Failed to hash file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="file_md5_complete",
            module=logger.name,
            fields={"path": request.path, "md5": md5},
        )
    )
    return FileHashResponse(schema_version="1.0", path=request.path, md5=md5)


def file_stat(request: FileStatRequest, ctx: RunContext) -> FileStatResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="file_stat_start",
            module=logger.name,
            fields={"path": request.path, "compute_md5": request.compute_md5},
        )
    )
    path = Path(request.path)
    if not path.exists():
        response = FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=False,
            size_bytes=None,
            mtime_utc=None,
            md5=None,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="file_stat_complete",
                module=logger.name,
                fields={"path": request.path, "exists": False},
            )
        )
        return response
    try:
        stat = path.stat()
    except OSError as exc:
        raise AppError(
            code="file_stat_failed",
            message=f"Failed to stat file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    md5 = None
    if request.compute_md5:
        try:
            md5 = _md5_file(path)
        except OSError as exc:
            raise AppError(
                code="file_hash_failed",
                message=f"Failed to hash file: {request.path}",
                cause=exc,
                retryable=False,
            ) from exc
    response = FileStatResponse(
        schema_version="1.0",
        path=request.path,
        exists=True,
        size_bytes=stat.st_size,
        mtime_utc=stat.st_mtime,
        md5=md5,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="file_stat_complete",
            module=logger.name,
            fields={
                "path": request.path,
                "exists": True,
                "size_bytes": response.size_bytes,
                "mtime_utc": response.mtime_utc,
                "md5": response.md5,
            },
        )
    )
    return response


def delete_file(request: DeleteFileRequest, ctx: RunContext) -> DeleteFileResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="delete_file_start",
            module=logger.name,
            fields={"path": request.path},
        )
    )
    path = Path(request.path)
    deleted = False
    if path.exists():
        try:
            path.unlink()
            deleted = True
        except OSError as exc:
            raise AppError(
                code="file_delete_failed",
                message=f"Failed to delete file: {request.path}",
                cause=exc,
                retryable=False,
            ) from exc
    elif not request.missing_ok:
        raise AppError(
            code="file_not_found",
            message=f"File not found: {request.path}",
            retryable=False,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="delete_file_complete",
            module=logger.name,
            fields={"path": request.path, "deleted": deleted},
        )
    )
    return DeleteFileResponse(schema_version="1.0", path=request.path, deleted=deleted)


def read_latest_pdf_cache_text(
    request: PdfCacheTextReadRequest, ctx: RunContext
) -> PdfCacheTextReadResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_cache_text_read_start",
            module=logger.name,
            fields={"cache_dir": request.cache_dir, "md5": request.md5},
        )
    )
    md5 = _require_pdf_cache_md5(request.md5)
    root = Path(request.cache_dir).expanduser().resolve() / "pdf_cache" / md5
    if not root.exists() or not root.is_dir():
        logger.info(
            log_event(
                ctx,
                role="service",
                event="pdf_cache_text_read_complete",
                module=logger.name,
                fields={
                    "md5": md5,
                    "hit": False,
                    "reason": "cache_dir_missing",
                },
            )
        )
        return PdfCacheTextReadResponse(schema_version="1.0", text="", source_path="")

    candidates = sorted(
        root.glob("text_*.json"), key=lambda path: path.stat().st_mtime, reverse=True
    )
    if not candidates:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="pdf_cache_text_read_complete",
                module=logger.name,
                fields={
                    "md5": md5,
                    "hit": False,
                    "reason": "no_text_cache_files",
                },
            )
        )
        return PdfCacheTextReadResponse(schema_version="1.0", text="", source_path="")

    source_path = candidates[0]
    try:
        payload = json.loads(source_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="pdf_cache_text_read_failed",
                module=logger.name,
                fields={"path": str(source_path), "error": str(exc)},
            )
        )
        return PdfCacheTextReadResponse(schema_version="1.0", text="", source_path="")
    text = payload.get("text") if isinstance(payload, dict) else ""
    if not isinstance(text, str):
        text = ""
    logger.info(
        log_event(
            ctx,
            role="service",
            event="pdf_cache_text_read_complete",
            module=logger.name,
            fields={
                "md5": md5,
                "hit": bool(text),
                "source_path": str(source_path),
                "length": len(text),
            },
        )
    )
    return PdfCacheTextReadResponse(
        schema_version="1.0", text=text, source_path=str(source_path)
    )


def _md5_bytes(data: bytes) -> str:
    h = hashlib.md5()
    h.update(data)
    return h.hexdigest()


def _md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()
