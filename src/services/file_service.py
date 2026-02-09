from __future__ import annotations

import hashlib
import logging
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


def read_text(request: ReadTextRequest, ctx: RunContext) -> ReadTextResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="read_text_start",
        module=logger.name,
        fields={"path": request.path},
    ))
    try:
        content = Path(request.path).read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise AppError(
            code="file_not_found",
            message=f"File not found: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    except Exception as exc:
        raise AppError(
            code="file_read_failed",
            message=f"Failed to read text file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc

    logger.info(log_event(
        ctx,
        role="service",
        event="read_text_complete",
        module=logger.name,
        fields={"path": request.path, "length": len(content)},
    ))
    return ReadTextResponse(schema_version="1.0", path=request.path, content=content)


def read_bytes(request: ReadBytesRequest, ctx: RunContext) -> ReadBytesResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="read_bytes_start",
        module=logger.name,
        fields={"path": request.path},
    ))
    try:
        content = Path(request.path).read_bytes()
    except FileNotFoundError as exc:
        raise AppError(
            code="file_not_found",
            message=f"File not found: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    except Exception as exc:
        raise AppError(
            code="file_read_failed",
            message=f"Failed to read binary file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc

    logger.info(log_event(
        ctx,
        role="service",
        event="read_bytes_complete",
        module=logger.name,
        fields={"path": request.path, "length": len(content)},
    ))
    return ReadBytesResponse(schema_version="1.0", path=request.path, content=content)


def list_html(request: ListHtmlRequest, ctx: RunContext) -> ListHtmlResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="list_html_start",
        module=logger.name,
        fields={"root_dir": request.root_dir},
    ))
    root = Path(request.root_dir)
    if not root.exists():
        raise AppError(
            code="output_dir_missing",
            message=f"Output dir does not exist: {request.root_dir}",
            retryable=False,
        )
    html_paths: List[str] = [str(p) for p in sorted(root.glob("*.html"))]
    logger.info(log_event(
        ctx,
        role="service",
        event="list_html_complete",
        module=logger.name,
        fields={"count": len(html_paths)},
    ))
    return ListHtmlResponse(
        schema_version="1.0",
        root_dir=request.root_dir,
        html_paths=html_paths,
    )


def list_directory(request: ListDirectoryRequest, ctx: RunContext) -> ListDirectoryResponse:
    logger.info(log_event(
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
    ))
    root = Path(request.root_dir)
    if not root.exists():
        raise AppError(
            code="directory_not_found",
            message=f"Directory not found: {request.root_dir}",
            retryable=False,
        )
    pattern = request.glob_pattern.strip() if request.glob_pattern else "*"
    if not pattern:
        pattern = "*"
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
        entries.append(DirectoryEntry(
            schema_version="1.0",
            path=str(entry),
            name=entry.name,
            is_dir=is_dir,
            size_bytes=None if is_dir else int(stat.st_size),
            mtime_utc=float(stat.st_mtime),
        ))
        if len(entries) >= limit:
            break
    entries.sort(key=lambda item: item.path)
    logger.info(log_event(
        ctx,
        role="service",
        event="list_directory_complete",
        module=logger.name,
        fields={"root_dir": request.root_dir, "count": len(entries)},
    ))
    return ListDirectoryResponse(
        schema_version="1.0",
        root_dir=request.root_dir,
        entries=entries,
    )


def file_exists(request: FileExistsRequest, ctx: RunContext) -> FileExistsResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="file_exists_start",
        module=logger.name,
        fields={"path": request.path},
    ))
    exists = Path(request.path).exists()
    logger.info(log_event(
        ctx,
        role="service",
        event="file_exists_complete",
        module=logger.name,
        fields={"path": request.path, "exists": exists},
    ))
    return FileExistsResponse(schema_version="1.0", path=request.path, exists=exists)


def write_bytes(request: WriteBytesRequest, ctx: RunContext) -> WriteBytesResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="write_bytes_start",
        module=logger.name,
        fields={"path": request.path, "size": len(request.content)},
    ))
    path = Path(request.path)
    if request.make_parents:
        path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_bytes(request.content)
    except Exception as exc:
        raise AppError(
            code="file_write_failed",
            message=f"Failed to write binary file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    md5 = _md5_bytes(request.content)
    logger.info(log_event(
        ctx,
        role="service",
        event="write_bytes_complete",
        module=logger.name,
        fields={"path": request.path, "md5": md5},
    ))
    return WriteBytesResponse(
        schema_version="1.0",
        path=request.path,
        bytes_written=len(request.content),
        md5=md5,
    )


def file_md5(request: FileHashRequest, ctx: RunContext) -> FileHashResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="file_md5_start",
        module=logger.name,
        fields={"path": request.path},
    ))
    path = Path(request.path)
    if not path.exists():
        raise AppError(
            code="file_not_found",
            message=f"File not found: {request.path}",
            retryable=False,
        )
    try:
        md5 = _md5_file(path)
    except Exception as exc:
        raise AppError(
            code="file_hash_failed",
            message=f"Failed to hash file: {request.path}",
            cause=exc,
            retryable=False,
        ) from exc
    logger.info(log_event(
        ctx,
        role="service",
        event="file_md5_complete",
        module=logger.name,
        fields={"path": request.path, "md5": md5},
    ))
    return FileHashResponse(schema_version="1.0", path=request.path, md5=md5)


def file_stat(request: FileStatRequest, ctx: RunContext) -> FileStatResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="file_stat_start",
        module=logger.name,
        fields={"path": request.path, "compute_md5": request.compute_md5},
    ))
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
        logger.info(log_event(
            ctx,
            role="service",
            event="file_stat_complete",
            module=logger.name,
            fields={"path": request.path, "exists": False},
        ))
        return response
    try:
        stat = path.stat()
    except Exception as exc:
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
        except Exception as exc:
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
    logger.info(log_event(
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
    ))
    return response


def delete_file(request: DeleteFileRequest, ctx: RunContext) -> DeleteFileResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="delete_file_start",
        module=logger.name,
        fields={"path": request.path},
    ))
    path = Path(request.path)
    deleted = False
    if path.exists():
        try:
            path.unlink()
            deleted = True
        except Exception as exc:
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
    logger.info(log_event(
        ctx,
        role="service",
        event="delete_file_complete",
        module=logger.name,
        fields={"path": request.path, "deleted": deleted},
    ))
    return DeleteFileResponse(schema_version="1.0", path=request.path, deleted=deleted)


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
