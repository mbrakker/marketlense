from __future__ import annotations

import hashlib
import io
import logging
from typing import Iterable, Optional

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload
from google.oauth2.service_account import Credentials

from src.contracts.drive import (
    DriveDownloadRequest,
    DriveDownloadResponse,
    DriveFile,
    DriveListRequest,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.drive_service")


def _build_drive_client(sa_path: str):
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds = Credentials.from_service_account_file(sa_path, scopes=scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_pdfs(request: DriveListRequest, ctx: RunContext) -> Iterable[DriveFile]:
    logger.info(log_event(
        ctx,
        role="service",
        event="drive_list_start",
        module=logger.name,
        fields={"folder_id": request.folder_id},
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
    drive = _build_drive_client(request.service_account_path)
    q = f"'{request.folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    page_token: Optional[str] = None
    total = 0
    completed = False
    try:
        while True:
            try:
                resp = drive.files().list(
                    q=q,
                    fields="files(id,name,modifiedTime,md5Checksum,version),nextPageToken",
                    pageToken=page_token,
                    supportsAllDrives=True,
                    includeItemsFromAllDrives=True,
                ).execute()
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
                total += 1
                yield DriveFile(
                    schema_version="1.0",
                    file_id=f.get("id", ""),
                    name=f.get("name", ""),
                    modified_time=f.get("modifiedTime"),
                    md5_checksum=f.get("md5Checksum"),
                    version=str(f.get("version")) if f.get("version") is not None else None,
                )
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
    drive = _build_drive_client(request.service_account_path)
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
