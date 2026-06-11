from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from src.services import drive_service as boundary

from .shared import *  # noqa: F401,F403
from .client_cache import _get_drive_client


def _iter_list_files_paginated(
    drive, list_kwargs: dict, request: DriveListRequest, ctx: RunContext
) -> Iterator[dict]:
    page_token: Optional[str] = None
    page_index = 0
    while True:
        try:
            kwargs = dict(list_kwargs)
            kwargs["pageToken"] = page_token
            resp = drive.files().list(**kwargs).execute()
        except DRIVE_BOUNDARY_EXCEPTIONS as exc:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="drive_list_error",
                    module=logger.name,
                    fields={"folder_id": request.folder_id, "error": str(exc)},
                )
            )
            raise AppError(
                code="drive_list_failed",
                message="Drive list failed",
                cause=exc,
                retryable=True,
                context={"folder_id": request.folder_id},
            ) from exc
        page_index += 1
        page_files = resp.get("files", [])
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_list_page_loaded",
                module=logger.name,
                fields={
                    "folder_id": request.folder_id,
                    "page_index": page_index,
                    "page_token": page_token or "",
                    "page_file_count": len(page_files),
                    "has_next_page": bool(resp.get("nextPageToken")),
                },
            )
        )
        for item in page_files:
            yield item
        page_token = resp.get("nextPageToken")
        if not page_token:
            break


def _folder_scope_cache_key(
    request: DriveListRequest,
) -> tuple[str, str, str, bool, bool]:
    auth_mode = _request_auth_mode(request)
    principal = _principal_path(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
    )
    return (
        principal,
        str(request.folder_id or "").strip(),
        str(request.drive_id or "").strip(),
        bool(request.supports_all_drives),
        bool(request.include_items_from_all_drives),
    )


def _prune_folder_scope_cache(now: float) -> int:
    removed = 0
    for cache_key, entry in list(boundary._FOLDER_SCOPE_CACHE.items()):
        if entry.expires_at > now:
            continue
        boundary._FOLDER_SCOPE_CACHE.pop(cache_key, None)
        removed += 1
    return removed


def _evict_folder_scope_cache(limit: int) -> int:
    evicted = 0
    while len(boundary._FOLDER_SCOPE_CACHE) > max(0, int(limit)):
        oldest_key = min(
            boundary._FOLDER_SCOPE_CACHE.items(),
            key=lambda item: (item[1].last_access_at, item[0]),
        )[0]
        boundary._FOLDER_SCOPE_CACHE.pop(oldest_key, None)
        evicted += 1
    return evicted


def _invalidate_folder_scope_cache(*, folder_id: str | None = None) -> int:
    target = str(folder_id or "").strip()
    with boundary._FOLDER_SCOPE_CACHE_LOCK:
        removed = 0
        for cache_key in list(boundary._FOLDER_SCOPE_CACHE.keys()):
            if target and cache_key[1] != target:
                continue
            boundary._FOLDER_SCOPE_CACHE.pop(cache_key, None)
            removed += 1
        return removed


def _resolve_folder_scope(
    drive, request: DriveListRequest, ctx: RunContext
) -> list[str]:
    cache_key = _folder_scope_cache_key(request)
    with boundary._FOLDER_SCOPE_CACHE_LOCK:
        now = _now_monotonic_seconds()
        expired = _prune_folder_scope_cache(now)
        cached = boundary._FOLDER_SCOPE_CACHE.get(cache_key)
        if cached is not None and cached.expires_at > now:
            cached.last_access_at = now
            cached.expires_at = now + boundary.DRIVE_FOLDER_SCOPE_CACHE_TTL_SECONDS
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="drive_list_folder_scope_cache_hit",
                    module=logger.name,
                    fields={
                        "root_folder_id": request.folder_id,
                        "folder_count": len(cached.folder_ids),
                        "expired_evictions": expired,
                        "cache_size": len(boundary._FOLDER_SCOPE_CACHE),
                    },
                )
            )
            return list(cached.folder_ids)

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
        for subfolder in _iter_list_files_paginated(drive, list_kwargs, request, ctx):
            subfolder_id = subfolder.get("id", "")
            if not subfolder_id or subfolder_id in seen:
                continue
            seen.add(subfolder_id)
            folder_ids.append(subfolder_id)
            queue.append(subfolder_id)

    with boundary._FOLDER_SCOPE_CACHE_LOCK:
        now = _now_monotonic_seconds()
        expired = _prune_folder_scope_cache(now)
        boundary._FOLDER_SCOPE_CACHE[cache_key] = _DriveFolderScopeCacheEntry(
            folder_ids=tuple(folder_ids),
            expires_at=now + boundary.DRIVE_FOLDER_SCOPE_CACHE_TTL_SECONDS,
            last_access_at=now,
        )
        evicted = _evict_folder_scope_cache(
            boundary.DRIVE_FOLDER_SCOPE_CACHE_MAX_ENTRIES
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_list_folder_scope_resolved",
            module=logger.name,
            fields={
                "root_folder_id": request.folder_id,
                "folder_count": len(folder_ids),
                "expired_evictions": expired,
                "max_entry_evictions": evicted,
                "cache_size": len(boundary._FOLDER_SCOPE_CACHE),
            },
        )
    )
    return folder_ids


def list_pdfs(request: DriveListRequest, ctx: RunContext) -> Iterable[DriveFile]:
    auth_mode = _request_auth_mode(request)
    logger.info(
        log_event(
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
            for f in _iter_list_files_paginated(drive, list_kwargs, request, ctx):
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
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_list_complete",
                module=logger.name,
                fields={"count": total, "partial": not completed},
            )
        )


def get_file_metadata(
    request: DriveFileMetadataRequest, ctx: RunContext
) -> DriveFileMetadataResponse:
    auth_mode = _request_auth_mode(request)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_file_metadata_start",
            module=logger.name,
            fields={"file_id": request.file_id, "auth_mode": auth_mode},
        )
    )
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
        resp = (
            drive.files()
            .get(
                fileId=request.file_id,
                fields="id,name,modifiedTime,md5Checksum,mimeType",
            )
            .execute()
        )
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_file_metadata_failed",
                module=logger.name,
                fields={"file_id": request.file_id, "error": str(exc)},
            )
        )
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
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_file_metadata_complete",
            module=logger.name,
            fields={"file_id": file.file_id, "name": file.name or ""},
        )
    )
    return DriveFileMetadataResponse(schema_version="1.0", file=file)


def download_pdf(
    request: DriveDownloadRequest, ctx: RunContext
) -> DriveDownloadResponse:
    file_meta = request.file
    auth_mode = _request_auth_mode(request)

    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_download_start",
            module=logger.name,
            fields={
                "file_id": file_meta.file_id,
                "name": file_meta.name,
                "auth_mode": auth_mode,
            },
        )
    )

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
        downloader = boundary.MediaIoBaseDownload(buffer, req)
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
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_download_complete",
            module=logger.name,
            fields={"md5": md5, "size": len(content)},
        )
    )

    return DriveDownloadResponse(
        schema_version="1.0",
        file=file_meta,
        content=content,
        md5=md5,
        size=len(content),
    )


def download_pdf_to_path(
    request: DriveDownloadToPathRequest, ctx: RunContext
) -> DriveDownloadToPathResponse:
    file_meta = request.file
    auth_mode = _request_auth_mode(request)

    logger.info(
        log_event(
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
        )
    )

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
            downloader = boundary.MediaIoBaseDownload(writer, req)
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
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="drive_download_partial_cleanup_failed",
                    module=logger.name,
                    fields={
                        "file_id": file_meta.file_id,
                        "output_path": request.output_path,
                    },
                )
            )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_download_to_path_failed",
                module=logger.name,
                fields={
                    "file_id": file_meta.file_id,
                    "output_path": request.output_path,
                    "error": str(exc),
                },
            )
        )
        raise AppError(
            code="drive_download_failed",
            message="Drive download failed",
            cause=exc,
            retryable=True,
            context={"file_id": file_meta.file_id, "output_path": request.output_path},
        ) from exc

    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_download_to_path_complete",
            module=logger.name,
            fields={"md5": md5, "size": size, "output_path": request.output_path},
        )
    )

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
    list_request = DriveListRequest(
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
    )
    limit = request.limit if request.limit > 0 else 50
    files: list[DriveFile] = []
    for row in _iter_list_files_paginated(
        drive,
        list_kwargs,
        list_request,
        ctx,
    ):
        file_id = str(row.get("id", "")).strip()
        if not file_id:
            continue
        files.append(
            DriveFile(
                schema_version="1.0",
                file_id=file_id,
                name=row.get("name"),
                modified_time=row.get("modifiedTime"),
                md5_checksum=row.get("md5Checksum"),
                mime_type=row.get("mimeType"),
            )
        )
        if len(files) >= limit:
            break
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
            fields={
                "folder_id": request.folder_id,
                "count": len(files),
                "truncated": len(files) >= limit,
            },
        )
    )
    return response


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
