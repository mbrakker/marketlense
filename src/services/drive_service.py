from __future__ import annotations

import hashlib
import io
import logging
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials

from src.contracts.drive import (
    DriveDownloadRequest,
    DriveDownloadResponse,
    DriveDownloadToPathRequest,
    DriveDownloadToPathResponse,
    DriveFile,
    DriveFileMetadataRequest,
    DriveFileMetadataResponse,
    DriveListRequest,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.drive_service")
_DRIVE_CLIENTS: dict[tuple[str, int], object] = {}
_DRIVE_CLIENTS_LOCK = threading.Lock()


class _HashingWriter:
    def __init__(self, handle):
        self._handle = handle
        self._hash = hashlib.md5()
        self._bytes_written = 0

    def write(self, data: bytes) -> int:
        if not data:
            return 0
        self._hash.update(data)
        self._bytes_written += len(data)
        return self._handle.write(data)

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        return self._handle.seek(offset, whence)

    def tell(self) -> int:
        return self._handle.tell()

    def flush(self) -> None:
        self._handle.flush()

    def close(self) -> None:
        self._handle.close()

    @property
    def md5(self) -> Optional[str]:
        if self._bytes_written <= 0:
            return None
        return self._hash.hexdigest()

    @property
    def bytes_written(self) -> int:
        return self._bytes_written


def _build_drive_client(sa_path: str):
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds = Credentials.from_service_account_file(sa_path, scopes=scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _get_drive_client(sa_path: str, ctx: RunContext):
    thread_id = threading.get_ident()
    cache_key = (sa_path, thread_id)
    if cache_key in _DRIVE_CLIENTS:
        logger.info(log_event(
            ctx,
            role="service",
            event="drive_client_reuse",
            module=logger.name,
            fields={"service_account_path": sa_path, "thread_id": thread_id},
        ))
        return _DRIVE_CLIENTS[cache_key]
    with _DRIVE_CLIENTS_LOCK:
        cached = _DRIVE_CLIENTS.get(cache_key)
        if cached is not None:
            logger.info(log_event(
                ctx,
                role="service",
                event="drive_client_reuse",
                module=logger.name,
                fields={"service_account_path": sa_path, "thread_id": thread_id},
            ))
            return cached
        client = _build_drive_client(sa_path)
        _DRIVE_CLIENTS[cache_key] = client
    logger.info(log_event(
        ctx,
        role="service",
        event="drive_client_created",
        module=logger.name,
        fields={"service_account_path": sa_path, "thread_id": thread_id},
    ))
    return client


def _parse_rfc3339(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone(timezone.utc)
    except Exception:
        return None


def list_pdfs(request: DriveListRequest, ctx: RunContext) -> Iterable[DriveFile]:
    logger.info(log_event(
        ctx,
        role="service",
        event="drive_list_start",
        module=logger.name,
        fields={
            "folder_id": request.folder_id,
            "page_size": request.page_size,
            "order_by": request.order_by or "",
            "modified_after": request.modified_after or "",
            "list_mode": request.list_mode,
            "supports_all_drives": request.supports_all_drives,
            "include_items_from_all_drives": request.include_items_from_all_drives,
            "drive_id": request.drive_id or "",
        },
    ))
    if not request.service_account_path:
        raise AppError(
            code="drive_sa_path_missing",
            message="Service account path is required to list Drive files",
            retryable=False,
        )
    if not request.folder_id:
        raise AppError(
            code="drive_folder_id_missing",
            message="Drive folder ID is required to list PDFs",
            retryable=False,
        )
    drive = _get_drive_client(request.service_account_path, ctx)
    q = f"'{request.folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    if request.modified_after:
        q += f" and modifiedTime > '{request.modified_after}'"
    list_mode = (request.list_mode or "full").strip().lower()
    fields = "files(id,modifiedTime,md5Checksum),nextPageToken"
    if list_mode == "full":
        fields = "files(id,name,modifiedTime,md5Checksum),nextPageToken"
    modified_after_dt = _parse_rfc3339(request.modified_after)
    page_token: Optional[str] = None
    total = 0
    completed = False
    early_stop = False
    try:
        while True:
            try:
                list_kwargs = {
                    "q": q,
                    "fields": fields,
                    "pageToken": page_token,
                    "supportsAllDrives": request.supports_all_drives,
                    "includeItemsFromAllDrives": request.include_items_from_all_drives,
                }
                if request.page_size:
                    list_kwargs["pageSize"] = int(request.page_size)
                if request.order_by:
                    list_kwargs["orderBy"] = request.order_by
                if request.drive_id:
                    list_kwargs["driveId"] = request.drive_id
                    list_kwargs["corpora"] = "drive"
                resp = drive.files().list(**list_kwargs).execute()
            except Exception as exc:
                logger.info(log_event(
                    ctx,
                    role="service",
                    event="drive_list_error",
                    module=logger.name,
                    fields={"folder_id": request.folder_id, "error": str(exc)},
                ))
                raise AppError(
                    code="drive_list_failed",
                    message="Drive list failed",
                    cause=exc,
                    retryable=True,
                    context={"folder_id": request.folder_id},
                ) from exc
            files = resp.get("files", [])
            for f in files:
                modified_time = f.get("modifiedTime")
                if modified_after_dt and request.order_by and "modifiedtime desc" in request.order_by.lower():
                    file_dt = _parse_rfc3339(modified_time)
                    if file_dt and file_dt <= modified_after_dt:
                        early_stop = True
                        break
                total += 1
                yield DriveFile(
                    schema_version="1.0",
                    file_id=f.get("id", ""),
                    name=f.get("name"),
                    modified_time=modified_time,
                    md5_checksum=f.get("md5Checksum"),
                )
            if early_stop:
                logger.info(log_event(
                    ctx,
                    role="service",
                    event="drive_list_cutoff_reached",
                    module=logger.name,
                    fields={"modified_after": request.modified_after or ""},
                ))
                completed = True
                break
            page_token = resp.get("nextPageToken")
            if not page_token:
                completed = True
                break
    finally:
        logger.info(log_event(
            ctx,
            role="service",
            event="drive_list_complete",
            module=logger.name,
            fields={"count": total, "partial": not completed},
        ))


def get_file_metadata(request: DriveFileMetadataRequest, ctx: RunContext) -> DriveFileMetadataResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="drive_file_metadata_start",
        module=logger.name,
        fields={"file_id": request.file_id},
    ))
    if not request.service_account_path:
        raise AppError(
            code="drive_sa_path_missing",
            message="Service account path is required to fetch Drive metadata",
            retryable=False,
        )
    if not request.file_id:
        raise AppError(
            code="drive_file_id_missing",
            message="Drive file ID is required to fetch metadata",
            retryable=False,
        )
    drive = _get_drive_client(request.service_account_path, ctx)
    try:
        resp = drive.files().get(fileId=request.file_id, fields="id,name,modifiedTime,md5Checksum").execute()
    except Exception as exc:
        logger.info(log_event(
            ctx,
            role="service",
            event="drive_file_metadata_failed",
            module=logger.name,
            fields={"file_id": request.file_id, "error": str(exc)},
        ))
        raise AppError(
            code="drive_metadata_failed",
            message="Drive metadata fetch failed",
            cause=exc,
            retryable=True,
            context={"file_id": request.file_id},
        ) from exc
    file = DriveFile(
        schema_version="1.0",
        file_id=resp.get("id", request.file_id),
        name=resp.get("name"),
        modified_time=resp.get("modifiedTime"),
        md5_checksum=resp.get("md5Checksum"),
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="drive_file_metadata_complete",
        module=logger.name,
        fields={"file_id": file.file_id, "name": file.name or ""},
    ))
    return DriveFileMetadataResponse(schema_version="1.0", file=file)


def _md5_for_bytes(data: bytes) -> str:
    h = hashlib.md5()
    h.update(data)
    return h.hexdigest()


def download_pdf(request: DriveDownloadRequest, ctx: RunContext) -> DriveDownloadResponse:
    file_meta = request.file

    logger.info(log_event(
        ctx,
        role="service",
        event="drive_download_start",
        module=logger.name,
        fields={"file_id": file_meta.file_id, "name": file_meta.name},
    ))

    if not request.service_account_path:
        raise AppError(
            code="drive_sa_path_missing",
            message="Service account path is required to download Drive files",
            retryable=False,
        )
    if not file_meta.file_id:
        raise AppError(
            code="drive_file_id_missing",
            message="Drive file ID is required to download a PDF",
            retryable=False,
        )
    drive = _get_drive_client(request.service_account_path, ctx)
    try:
        req = drive.files().get_media(fileId=file_meta.file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    except Exception as exc:
        raise AppError(
            code="drive_download_failed",
            message="Drive download failed",
            cause=exc,
            retryable=True,
            context={"file_id": file_meta.file_id},
        ) from exc

    content = buffer.getvalue()
    md5 = _md5_for_bytes(content) if content else None
    logger.info(log_event(
        ctx,
        role="service",
        event="drive_download_complete",
        module=logger.name,
        fields={"md5": md5, "size": len(content)},
    ))

    return DriveDownloadResponse(
        schema_version="1.0",
        file=file_meta,
        content=content,
        md5=md5,
        size=len(content),
    )


def download_pdf_to_path(request: DriveDownloadToPathRequest, ctx: RunContext) -> DriveDownloadToPathResponse:
    file_meta = request.file

    logger.info(log_event(
        ctx,
        role="service",
        event="drive_download_to_path_start",
        module=logger.name,
        fields={
            "file_id": file_meta.file_id,
            "name": file_meta.name,
            "output_path": request.output_path,
            "make_parents": request.make_parents,
        },
    ))

    if not request.service_account_path:
        raise AppError(
            code="drive_sa_path_missing",
            message="Service account path is required to download Drive files",
            retryable=False,
        )
    if not file_meta.file_id:
        raise AppError(
            code="drive_file_id_missing",
            message="Drive file ID is required to download a PDF",
            retryable=False,
        )
    if not request.output_path:
        raise AppError(
            code="drive_output_path_missing",
            message="Output path is required to download a PDF",
            retryable=False,
        )

    path = Path(request.output_path)
    if request.make_parents:
        path.parent.mkdir(parents=True, exist_ok=True)

    drive = _get_drive_client(request.service_account_path, ctx)
    size = 0
    md5 = None
    try:
        req = drive.files().get_media(fileId=file_meta.file_id)
        with path.open("wb") as fh:
            writer = _HashingWriter(fh)
            downloader = MediaIoBaseDownload(writer, req)
            done = False
            while not done:
                _, done = downloader.next_chunk()
            writer.flush()
            size = writer.bytes_written
            md5 = writer.md5
    except Exception as exc:
        logger.info(log_event(
            ctx,
            role="service",
            event="drive_download_to_path_failed",
            module=logger.name,
            fields={"file_id": file_meta.file_id, "output_path": request.output_path, "error": str(exc)},
        ))
        raise AppError(
            code="drive_download_failed",
            message="Drive download failed",
            cause=exc,
            retryable=True,
            context={"file_id": file_meta.file_id, "output_path": request.output_path},
        ) from exc

    logger.info(log_event(
        ctx,
        role="service",
        event="drive_download_to_path_complete",
        module=logger.name,
        fields={"md5": md5, "size": size, "output_path": request.output_path},
    ))

    return DriveDownloadToPathResponse(
        schema_version="1.0",
        file=file_meta,
        output_path=request.output_path,
        md5=md5,
        size=size,
    )
