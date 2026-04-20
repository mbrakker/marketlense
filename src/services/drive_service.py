from __future__ import annotations

import hashlib
import io
import logging
import json
import threading
from pathlib import Path
from typing import Iterable, Optional

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request as GoogleAuthRequest
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
from google.oauth2.credentials import Credentials as AuthorizedUserCredentials
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
try:
    from google_auth_oauthlib.flow import InstalledAppFlow
except ImportError:  # pragma: no cover - dependency guard
    InstalledAppFlow = None

from src.contracts.drive import (
    DriveDownloadRequest,
    DriveDownloadResponse,
    DriveDownloadToPathRequest,
    DriveDownloadToPathResponse,
    DriveFile,
    DriveFileMetadataRequest,
    DriveFileMetadataResponse,
    DriveFolderFileListRequest,
    DriveFolderFileListResponse,
    DriveListRequest,
    DriveOAuthAuthorizeRequest,
    DriveOAuthAuthorizeResponse,
    DriveUploadBytesRequest,
    DriveUploadBytesResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.drive_service")
Credentials = ServiceAccountCredentials
_DRIVE_CLIENTS: dict[tuple[str, str, int], object] = {}
_DRIVE_CLIENTS_LOCK = threading.Lock()
DRIVE_BOUNDARY_EXCEPTIONS = (HttpError, OSError, RuntimeError, ValueError, TypeError)
DRIVE_SCOPES = ["https://www.googleapis.com/auth/drive"]


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


def _normalize_drive_auth_mode(raw_mode: str | None) -> str:
    token = str(raw_mode or "service_account").strip().lower()
    if token in {"service_account", "oauth_user"}:
        return token
    raise AppError(
        code="drive_auth_mode_invalid",
        message="Drive auth mode must be service_account or oauth_user",
        retryable=False,
        context={"auth_mode": raw_mode or ""},
    )


def _persist_authorized_user_credentials(credentials, token_path: str) -> None:
    path = Path(token_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(credentials.to_json(), encoding="utf-8")


def _load_authorized_user_credentials(
    *, token_path: str, ctx: RunContext
):
    if not token_path:
        raise AppError(
            code="drive_oauth_token_path_missing",
            message="OAuth token path is required when Drive auth mode is oauth_user",
            retryable=False,
        )
    token_file = Path(token_path)
    if not token_file.exists():
        raise AppError(
            code="drive_oauth_token_missing",
            message="OAuth token JSON was not found; run drive-oauth-login first",
            retryable=False,
            context={"oauth_token_path": token_path},
        )
    try:
        credentials = AuthorizedUserCredentials.from_authorized_user_file(
            str(token_file), DRIVE_SCOPES
        )
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise AppError(
            code="drive_oauth_token_invalid",
            message="OAuth token JSON is invalid",
            cause=exc,
            retryable=False,
            context={"oauth_token_path": token_path},
        ) from exc
    if credentials.valid:
        return credentials
    if credentials.expired and credentials.refresh_token:
        try:
            credentials.refresh(GoogleAuthRequest())
        except RefreshError as exc:
            raise AppError(
                code="drive_oauth_refresh_failed",
                message="OAuth token refresh failed",
                cause=exc,
                retryable=False,
                context={"oauth_token_path": token_path},
            ) from exc
        _persist_authorized_user_credentials(credentials, token_path)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_oauth_token_refreshed",
                module=logger.name,
                fields={"oauth_token_path": token_path},
            )
        )
        return credentials
    raise AppError(
        code="drive_oauth_refresh_token_missing",
        message="OAuth token is not valid and cannot be refreshed; run drive-oauth-login again",
        retryable=False,
        context={"oauth_token_path": token_path},
    )


def _build_drive_client(
    *,
    auth_mode: str,
    service_account_path: str,
    oauth_token_path: str | None,
    ctx: RunContext,
):
    if auth_mode == "service_account":
        try:
            creds = Credentials.from_service_account_file(
                service_account_path, scopes=DRIVE_SCOPES
            )
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            raise AppError(
                code="drive_service_account_invalid",
                message="Service account credentials could not be loaded",
                cause=exc,
                retryable=False,
                context={"service_account_path": service_account_path},
            ) from exc
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    creds = _load_authorized_user_credentials(
        token_path=str(oauth_token_path or ""),
        ctx=ctx,
    )
    return build("drive", "v3", credentials=creds, cache_discovery=False)


def _get_drive_client(
    *,
    auth_mode: str,
    service_account_path: str,
    oauth_token_path: str | None,
    ctx: RunContext,
):
    thread_id = threading.get_ident()
    principal_path = (
        service_account_path if auth_mode == "service_account" else str(oauth_token_path or "")
    )
    cache_key = (auth_mode, principal_path, thread_id)
    if cache_key in _DRIVE_CLIENTS:
        logger.info(log_event(
            ctx,
            role="service",
            event="drive_client_reuse",
            module=logger.name,
            fields={"auth_mode": auth_mode, "credential_path": principal_path, "thread_id": thread_id},
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
                fields={"auth_mode": auth_mode, "credential_path": principal_path, "thread_id": thread_id},
            ))
            return cached
        client = _build_drive_client(
            auth_mode=auth_mode,
            service_account_path=service_account_path,
            oauth_token_path=oauth_token_path,
            ctx=ctx,
        )
        _DRIVE_CLIENTS[cache_key] = client
    logger.info(log_event(
        ctx,
        role="service",
        event="drive_client_created",
        module=logger.name,
        fields={"auth_mode": auth_mode, "credential_path": principal_path, "thread_id": thread_id},
    ))
    return client


def _require_drive_auth(
    *,
    auth_mode: str,
    service_account_path: str,
    oauth_token_path: str | None,
) -> None:
    if auth_mode == "service_account":
        if not service_account_path:
            raise AppError(
                code="drive_sa_path_missing",
                message="Service account path is required when Drive auth mode is service_account",
                retryable=False,
            )
        return
    if not str(oauth_token_path or "").strip():
        raise AppError(
            code="drive_oauth_token_path_missing",
            message="OAuth token path is required when Drive auth mode is oauth_user",
            retryable=False,
        )


def _request_auth_mode(request) -> str:
    return _normalize_drive_auth_mode(getattr(request, "auth_mode", "service_account"))



def _list_files_paginated(drive, list_kwargs: dict, request: DriveListRequest, ctx: RunContext) -> list[dict]:
    page_token: Optional[str] = None
    items: list[dict] = []
    while True:
        try:
            kwargs = dict(list_kwargs)
            kwargs["pageToken"] = page_token
            resp = drive.files().list(**kwargs).execute()
        except DRIVE_BOUNDARY_EXCEPTIONS as exc:
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
        items.extend(resp.get("files", []))
        page_token = resp.get("nextPageToken")
        if not page_token:
            break
    return items


def _resolve_folder_scope(drive, request: DriveListRequest, ctx: RunContext) -> list[str]:
    folder_ids = [request.folder_id]
    seen = {request.folder_id}
    queue = [request.folder_id]
    while queue:
        current_folder_id = queue.pop(0)
        list_kwargs = {
            "q": f"'{current_folder_id}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            "fields": "files(id),nextPageToken",
            "supportsAllDrives": request.supports_all_drives,
            "includeItemsFromAllDrives": request.include_items_from_all_drives,
        }
        if request.page_size:
            list_kwargs["pageSize"] = int(request.page_size)
        if request.drive_id:
            list_kwargs["driveId"] = request.drive_id
            list_kwargs["corpora"] = "drive"
        subfolders = _list_files_paginated(drive, list_kwargs, request, ctx)
        for subfolder in subfolders:
            subfolder_id = subfolder.get("id", "")
            if not subfolder_id or subfolder_id in seen:
                continue
            seen.add(subfolder_id)
            folder_ids.append(subfolder_id)
            queue.append(subfolder_id)

    logger.info(log_event(
        ctx,
        role="service",
        event="drive_list_folder_scope_resolved",
        module=logger.name,
        fields={"root_folder_id": request.folder_id, "folder_count": len(folder_ids)},
    ))
    return folder_ids


def list_pdfs(request: DriveListRequest, ctx: RunContext) -> Iterable[DriveFile]:
    auth_mode = _request_auth_mode(request)
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
            "auth_mode": auth_mode,
        },
    ))
    _require_drive_auth(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
    )
    if not request.folder_id:
        raise AppError(
            code="drive_folder_id_missing",
            message="Drive folder ID is required to list PDFs",
            retryable=False,
        )
    drive = _get_drive_client(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
        ctx=ctx,
    )
    folder_ids = _resolve_folder_scope(drive, request, ctx)
    list_mode = (request.list_mode or "full").strip().lower()
    fields = "files(id,modifiedTime,md5Checksum),nextPageToken"
    if list_mode == "full":
        fields = "files(id,name,modifiedTime,md5Checksum),nextPageToken"
    total = 0
    completed = False
    try:
        for folder_id in folder_ids:
            q = f"'{folder_id}' in parents and mimeType='application/pdf' and trashed=false"
            if request.modified_after:
                q += f" and modifiedTime > '{request.modified_after}'"
            list_kwargs = {
                "q": q,
                "fields": fields,
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
            files = _list_files_paginated(drive, list_kwargs, request, ctx)
            for f in files:
                total += 1
                yield DriveFile(
                    schema_version="1.0",
                    file_id=f.get("id", ""),
                    name=f.get("name"),
                    modified_time=f.get("modifiedTime"),
                    md5_checksum=f.get("md5Checksum"),
                    mime_type=f.get("mimeType"),
                )
        completed = True
    finally:
        logger.info(log_event(
            ctx,
            role="service",
            event="drive_list_complete",
            module=logger.name,
            fields={"count": total, "partial": not completed},
        ))


def get_file_metadata(request: DriveFileMetadataRequest, ctx: RunContext) -> DriveFileMetadataResponse:
    auth_mode = _request_auth_mode(request)
    logger.info(log_event(
        ctx,
        role="service",
        event="drive_file_metadata_start",
        module=logger.name,
        fields={"file_id": request.file_id, "auth_mode": auth_mode},
    ))
    _require_drive_auth(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
    )
    if not request.file_id:
        raise AppError(
            code="drive_file_id_missing",
            message="Drive file ID is required to fetch metadata",
            retryable=False,
        )
    drive = _get_drive_client(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
        ctx=ctx,
    )
    try:
        resp = drive.files().get(fileId=request.file_id, fields="id,name,modifiedTime,md5Checksum,mimeType").execute()
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
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
        mime_type=resp.get("mimeType"),
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
    auth_mode = _request_auth_mode(request)

    logger.info(log_event(
        ctx,
        role="service",
        event="drive_download_start",
        module=logger.name,
        fields={"file_id": file_meta.file_id, "name": file_meta.name, "auth_mode": auth_mode},
    ))

    _require_drive_auth(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
    )
    if not file_meta.file_id:
        raise AppError(
            code="drive_file_id_missing",
            message="Drive file ID is required to download a PDF",
            retryable=False,
        )
    drive = _get_drive_client(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
        ctx=ctx,
    )
    try:
        req = drive.files().get_media(fileId=file_meta.file_id)
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(buffer, req)
        done = False
        while not done:
            _, done = downloader.next_chunk()
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
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
    auth_mode = _request_auth_mode(request)

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
            "auth_mode": auth_mode,
        },
    ))

    _require_drive_auth(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
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

    drive = _get_drive_client(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
        ctx=ctx,
    )
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
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.info(log_event(
                ctx,
                role="service",
                event="drive_download_partial_cleanup_failed",
                module=logger.name,
                fields={"file_id": file_meta.file_id, "output_path": request.output_path},
            ))
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


def list_files_in_folder(
    request: DriveFolderFileListRequest, ctx: RunContext
) -> DriveFolderFileListResponse:
    auth_mode = _request_auth_mode(request)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_folder_file_list_start",
            module=logger.name,
            fields={
                "folder_id": request.folder_id,
                "name_prefix": request.name_prefix or "",
                "page_size": request.page_size,
                "order_by": request.order_by or "",
                "limit": request.limit,
                "supports_all_drives": request.supports_all_drives,
                "include_items_from_all_drives": request.include_items_from_all_drives,
                "drive_id": request.drive_id or "",
                "auth_mode": auth_mode,
            },
        )
    )
    _require_drive_auth(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
    )
    if not request.folder_id:
        raise AppError(
            code="drive_folder_id_missing",
            message="Drive folder ID is required to list folder files",
            retryable=False,
        )
    drive = _get_drive_client(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
        ctx=ctx,
    )
    name_prefix = str(request.name_prefix or "").replace("'", "\\'")
    query = f"'{request.folder_id}' in parents and trashed=false"
    if name_prefix:
        query += f" and name contains '{name_prefix}'"
    list_kwargs = {
        "q": query,
        "fields": "files(id,name,modifiedTime,md5Checksum,mimeType),nextPageToken",
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
    rows = _list_files_paginated(drive, list_kwargs, DriveListRequest(
        schema_version="1.0",
        folder_id=request.folder_id,
        service_account_path=request.service_account_path,
        page_size=request.page_size,
        order_by=request.order_by,
        modified_after=None,
        list_mode="full",
        supports_all_drives=request.supports_all_drives,
        include_items_from_all_drives=request.include_items_from_all_drives,
        drive_id=request.drive_id,
        auth_mode=request.auth_mode,
        oauth_client_path=request.oauth_client_path,
        oauth_token_path=request.oauth_token_path,
    ), ctx)
    files = [
        DriveFile(
            schema_version="1.0",
            file_id=str(row.get("id", "")),
            name=row.get("name"),
            modified_time=row.get("modifiedTime"),
            md5_checksum=row.get("md5Checksum"),
            mime_type=row.get("mimeType"),
        )
        for row in rows
        if str(row.get("id", "")).strip()
    ]
    limit = request.limit if request.limit > 0 else 50
    files = files[:limit]
    response = DriveFolderFileListResponse(
        schema_version="1.0",
        folder_id=request.folder_id,
        files=files,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_folder_file_list_complete",
            module=logger.name,
            fields={"folder_id": request.folder_id, "count": len(files)},
        )
    )
    return response


def upload_bytes(request: DriveUploadBytesRequest, ctx: RunContext) -> DriveUploadBytesResponse:
    auth_mode = _request_auth_mode(request)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_upload_start",
            module=logger.name,
            fields={
                "folder_id": request.folder_id,
                "file_name": request.file_name,
                "mime_type": request.mime_type,
                "size": len(request.content),
                "supports_all_drives": request.supports_all_drives,
                "auth_mode": auth_mode,
            },
        )
    )
    _require_drive_auth(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
    )
    if not request.folder_id:
        raise AppError(
            code="drive_folder_id_missing",
            message="Drive folder ID is required to upload Drive files",
            retryable=False,
        )
    if not request.file_name.strip():
        raise AppError(
            code="drive_upload_file_name_missing",
            message="Drive upload file name is required",
            retryable=False,
        )
    drive = _get_drive_client(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
        ctx=ctx,
    )
    metadata = {"name": request.file_name.strip(), "parents": [request.folder_id]}
    media = MediaIoBaseUpload(
        io.BytesIO(request.content),
        mimetype=request.mime_type.strip() or "application/octet-stream",
        resumable=False,
    )
    try:
        resp = (
            drive.files()
            .create(
                body=metadata,
                media_body=media,
                fields="id,name,modifiedTime,md5Checksum,mimeType",
                supportsAllDrives=request.supports_all_drives,
            )
            .execute()
        )
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_upload_failed",
                module=logger.name,
                fields={
                    "folder_id": request.folder_id,
                    "file_name": request.file_name,
                    "error": str(exc),
                },
            )
        )
        raise AppError(
            code="drive_upload_failed",
            message="Drive upload failed",
            cause=exc,
            retryable=True,
            context={"folder_id": request.folder_id, "file_name": request.file_name},
        ) from exc
    response = DriveUploadBytesResponse(
        schema_version="1.0",
        file=DriveFile(
            schema_version="1.0",
            file_id=str(resp.get("id", "")),
            name=resp.get("name"),
            modified_time=resp.get("modifiedTime"),
            md5_checksum=resp.get("md5Checksum"),
            mime_type=resp.get("mimeType"),
        ),
        size=len(request.content),
        md5=_md5_for_bytes(request.content) if request.content else None,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_upload_complete",
            module=logger.name,
            fields={
                "folder_id": request.folder_id,
                "file_id": response.file.file_id,
                "file_name": response.file.name or "",
                "size": response.size,
                "md5": response.md5 or "",
            },
        )
    )
    return response


def authorize_oauth_user(
    request: DriveOAuthAuthorizeRequest, ctx: RunContext
) -> DriveOAuthAuthorizeResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_oauth_authorize_start",
            module=logger.name,
            fields={
                "client_secret_path": request.client_secret_path,
                "token_output_path": request.token_output_path,
                "open_browser": request.open_browser,
                "port": request.port,
            },
        )
    )
    client_secret_path = str(request.client_secret_path or "").strip()
    token_output_path = str(request.token_output_path or "").strip()
    if not client_secret_path:
        raise AppError(
            code="drive_oauth_client_path_missing",
            message="OAuth client JSON path is required",
            retryable=False,
        )
    if not token_output_path:
        raise AppError(
            code="drive_oauth_token_path_missing",
            message="OAuth token output path is required",
            retryable=False,
        )
    if not Path(client_secret_path).exists():
        raise AppError(
            code="drive_oauth_client_path_invalid",
            message="OAuth client JSON path does not exist",
            retryable=False,
            context={"client_secret_path": client_secret_path},
        )
    if InstalledAppFlow is None:
        raise AppError(
            code="drive_oauth_dependency_missing",
            message="google-auth-oauthlib is required for drive-oauth-login",
            retryable=False,
        )
    try:
        flow = InstalledAppFlow.from_client_secrets_file(
            client_secret_path, DRIVE_SCOPES
        )
        credentials = flow.run_local_server(
            port=int(request.port),
            open_browser=bool(request.open_browser),
        )
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
        raise AppError(
            code="drive_oauth_authorize_failed",
            message="Drive OAuth authorization failed",
            cause=exc,
            retryable=False,
            context={"client_secret_path": client_secret_path},
        ) from exc
    _persist_authorized_user_credentials(credentials, token_output_path)
    with _DRIVE_CLIENTS_LOCK:
        for cache_key in list(_DRIVE_CLIENTS.keys()):
            if cache_key[0] == "oauth_user" and cache_key[1] == token_output_path:
                _DRIVE_CLIENTS.pop(cache_key, None)
    response = DriveOAuthAuthorizeResponse(
        schema_version="1.0",
        token_output_path=token_output_path,
        scopes=list(getattr(credentials, "scopes", DRIVE_SCOPES) or DRIVE_SCOPES),
        refresh_token_present=bool(getattr(credentials, "refresh_token", None)),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_oauth_authorize_complete",
            module=logger.name,
            fields={
                "token_output_path": response.token_output_path,
                "scope_count": len(response.scopes),
                "refresh_token_present": response.refresh_token_present,
            },
        )
    )
    return response
