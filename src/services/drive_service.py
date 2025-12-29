from __future__ import annotations

import hashlib
import io
import logging
import os
import re
import unicodedata
from pathlib import Path
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


def build_drive_client(sa_path: str):
    scopes = ["https://www.googleapis.com/auth/drive.readonly"]
    creds = Credentials.from_service_account_file(sa_path, scopes=scopes)
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def list_pdfs(drive, request: DriveListRequest, ctx: RunContext) -> Iterable[DriveFile]:
    log_event(
        logger,
        ctx,
        role="service",
        event="drive_list_start",
        fields={"folder_id": request.folder_id},
    )
    q = f"'{request.folder_id}' in parents and mimeType='application/pdf' and trashed=false"
    page_token: Optional[str] = None
    total = 0
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
            break
    log_event(
        logger,
        ctx,
        role="service",
        event="drive_list_complete",
        fields={"count": total},
    )


def _md5_for_file(path: str) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _safe_pdf_name(raw_name: str) -> str:
    name = os.path.basename(raw_name)
    name = unicodedata.normalize("NFKD", name)
    name = re.sub(r"[^A-Za-z0-9._ ()-]", "_", name).strip()
    if not name.lower().endswith(".pdf"):
        name = name + ".pdf"
    return name


def download_pdf(drive, request: DriveDownloadRequest, ctx: RunContext) -> DriveDownloadResponse:
    file_meta = request.file
    cache_path = Path(request.cache_dir)
    cache_path.mkdir(parents=True, exist_ok=True)

    raw_name = file_meta.name or f"{file_meta.file_id}.pdf"
    candidate = cache_path / _safe_pdf_name(raw_name)

    log_event(
        logger,
        ctx,
        role="service",
        event="drive_download_start",
        fields={"file_id": file_meta.file_id, "name": file_meta.name},
    )

    if candidate.exists():
        try:
            existing_md5 = _md5_for_file(str(candidate))
            if file_meta.md5_checksum and existing_md5 == file_meta.md5_checksum:
                log_event(
                    logger,
                    ctx,
                    role="service",
                    event="drive_download_cache_hit",
                    fields={"path": str(candidate)},
                )
                return DriveDownloadResponse(
                    schema_version="1.0",
                    file=file_meta,
                    local_path=str(candidate),
                    md5=existing_md5,
                )
        except Exception:
            pass

    if candidate.exists():
        base = candidate.stem
        suffix = 1
        while True:
            new_name = f"{base}-{suffix}.pdf"
            candidate = cache_path / new_name
            if not candidate.exists():
                break
            suffix += 1

    try:
        req = drive.files().get_media(fileId=file_meta.file_id)
        with open(candidate, "wb") as fh:
            downloader = MediaIoBaseDownload(fh, req)
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

    md5 = _md5_for_file(str(candidate))
    log_event(
        logger,
        ctx,
        role="service",
        event="drive_download_complete",
        fields={"path": str(candidate), "md5": md5},
    )

    return DriveDownloadResponse(
        schema_version="1.0",
        file=file_meta,
        local_path=str(candidate),
        md5=md5,
    )
