from __future__ import annotations

# ruff: noqa: F401,F403,F405,F821

from src.services import drive_service as boundary

from .shared import *  # noqa: F401,F403
from .auth import (
    _build_authorized_drive_http,
    _resolve_authorized_user_credentials,
    _resolve_drive_credentials,
)
from .client_cache import _get_drive_client


def preflight_drive_write_access(
    request: DriveWritePreflightRequest, ctx: RunContext
) -> DriveWritePreflightResponse:
    auth_mode = _request_auth_mode(request)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_write_preflight_start",
            module=logger.name,
            fields={
                "folder_id": request.folder_id,
                "supports_all_drives": request.supports_all_drives,
                "include_items_from_all_drives": request.include_items_from_all_drives,
                "drive_id": request.drive_id or "",
                "auth_mode": auth_mode,
            },
        )
    )
    try:
        _require_drive_auth(
            auth_mode=auth_mode,
            service_account_path=request.service_account_path,
            oauth_token_path=request.oauth_token_path,
        )
        if not str(request.folder_id or "").strip():
            raise AppError(
                code="drive_preflight_folder_id_missing",
                message="Drive folder ID is required for write preflight",
                retryable=False,
            )
        resolution = _resolve_drive_credentials(
            auth_mode=auth_mode,
            service_account_path=request.service_account_path,
            oauth_token_path=request.oauth_token_path,
            ctx=ctx,
        )
        if not _credentials_include_required_drive_scopes(resolution.credentials):
            raise AppError(
                code="drive_preflight_scope_insufficient",
                message="Drive credentials do not include the required write scope",
                retryable=False,
                severity="error",
                context={
                    "folder_id": request.folder_id,
                    "auth_mode": auth_mode,
                    "required_scopes": list(DRIVE_SCOPES),
                },
            )
        drive = boundary.build(
            "drive",
            "v3",
            http=_build_authorized_drive_http(resolution.credentials),
            cache_discovery=False,
            static_discovery=True,
        )
        folder = _load_drive_folder_write_metadata(
            drive=drive,
            folder_id=request.folder_id,
            supports_all_drives=request.supports_all_drives,
            ctx=ctx,
        )
        mime_type = str(folder.get("mimeType") or "").strip()
        if mime_type != "application/vnd.google-apps.folder":
            raise AppError(
                code="drive_preflight_target_not_folder",
                message="Drive preflight target is not a folder",
                retryable=False,
                severity="error",
                context={"folder_id": request.folder_id, "mime_type": mime_type},
            )
        can_add_children = bool(
            (folder.get("capabilities") or {}).get("canAddChildren")
        )
        if not can_add_children:
            raise AppError(
                code="drive_preflight_no_write_access",
                message="Drive credentials cannot create files in the target folder",
                retryable=False,
                severity="error",
                context={"folder_id": request.folder_id, "auth_mode": auth_mode},
            )
        _probe_drive_folder_write_access(
            drive=drive,
            folder_id=request.folder_id,
            supports_all_drives=request.supports_all_drives,
            ctx=ctx,
        )
        response = DriveWritePreflightResponse(
            schema_version="1.0",
            folder_id=request.folder_id,
            auth_mode=auth_mode,
            credentials_refreshed=resolution.refreshed,
            scopes_verified=True,
            folder_access_verified=True,
            write_access_verified=True,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_write_preflight_complete",
                module=logger.name,
                fields={
                    "folder_id": response.folder_id,
                    "auth_mode": response.auth_mode,
                    "credentials_refreshed": response.credentials_refreshed,
                    "scopes_verified": response.scopes_verified,
                    "folder_access_verified": response.folder_access_verified,
                    "write_access_verified": response.write_access_verified,
                },
            )
        )
        return response
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_write_preflight_failed",
                module=logger.name,
                fields={
                    "folder_id": request.folder_id,
                    "auth_mode": auth_mode,
                    "error_code": exc.code,
                    "retryable": exc.retryable,
                },
            )
        )
        raise


def _credentials_include_required_drive_scopes(credentials) -> bool:
    has_scopes = getattr(credentials, "has_scopes", None)
    if callable(has_scopes):
        try:
            return bool(has_scopes(DRIVE_SCOPES))
        except (TypeError, ValueError):
            return False
    scopes = getattr(credentials, "scopes", None)
    if scopes is None:
        scopes = getattr(credentials, "granted_scopes", None)
    if scopes is None:
        return True
    return set(DRIVE_SCOPES).issubset({str(scope) for scope in scopes})


def _load_drive_folder_write_metadata(
    *,
    drive,
    folder_id: str,
    supports_all_drives: bool,
    ctx: RunContext,
) -> dict:
    try:
        folder = (
            drive.files()
            .get(
                fileId=folder_id,
                fields="id,mimeType,capabilities/canAddChildren",
                supportsAllDrives=supports_all_drives,
            )
            .execute()
        )
    except HttpError as exc:
        status = int(getattr(getattr(exc, "resp", None), "status", 0) or 0)
        retryable = status not in {400, 401, 403, 404}
        code = (
            "drive_preflight_folder_access_denied"
            if status in {401, 403, 404}
            else "drive_preflight_folder_metadata_failed"
        )
        raise AppError(
            code=code,
            message="Drive folder metadata could not be loaded during preflight",
            cause=exc,
            retryable=retryable,
            severity="error",
            context={"folder_id": folder_id, "status": status},
        ) from exc
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
        raise AppError(
            code="drive_preflight_folder_metadata_failed",
            message="Drive folder metadata could not be loaded during preflight",
            cause=exc,
            retryable=True,
            severity="error",
            context={"folder_id": folder_id},
        ) from exc
    if not isinstance(folder, dict):
        raise AppError(
            code="drive_preflight_folder_metadata_invalid",
            message="Drive folder metadata response was not an object",
            retryable=True,
            severity="error",
            context={"folder_id": folder_id},
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_write_preflight_folder_loaded",
            module=logger.name,
            fields={
                "folder_id": folder_id,
                "mime_type": str(folder.get("mimeType") or ""),
                "can_add_children": bool(
                    (folder.get("capabilities") or {}).get("canAddChildren")
                ),
            },
        )
    )
    return folder


def _probe_drive_folder_write_access(
    *,
    drive,
    folder_id: str,
    supports_all_drives: bool,
    ctx: RunContext,
) -> None:
    probe_name = _drive_write_preflight_probe_name(ctx)
    media = boundary.MediaIoBaseUpload(
        io.BytesIO(b"market-lense-drive-write-preflight\n"),
        mimetype="text/plain",
        resumable=False,
    )
    try:
        created = (
            drive.files()
            .create(
                body={"name": probe_name, "parents": [folder_id]},
                media_body=media,
                fields="id",
                supportsAllDrives=supports_all_drives,
            )
            .execute()
        )
    except HttpError as exc:
        status = int(getattr(getattr(exc, "resp", None), "status", 0) or 0)
        raise AppError(
            code="drive_preflight_write_probe_failed",
            message="Drive write preflight could not create a probe file",
            cause=exc,
            retryable=status not in {400, 401, 403, 404},
            severity="error",
            context={"folder_id": folder_id, "status": status},
        ) from exc
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
        raise AppError(
            code="drive_preflight_write_probe_failed",
            message="Drive write preflight could not create a probe file",
            cause=exc,
            retryable=True,
            severity="error",
            context={"folder_id": folder_id},
        ) from exc
    probe_file_id = str((created or {}).get("id") or "").strip()
    if not probe_file_id:
        raise AppError(
            code="drive_preflight_write_probe_invalid",
            message="Drive write preflight create response did not include a file ID",
            retryable=True,
            severity="error",
            context={"folder_id": folder_id},
        )
    try:
        (
            drive.files()
            .delete(fileId=probe_file_id, supportsAllDrives=supports_all_drives)
            .execute()
        )
    except HttpError as exc:
        status = int(getattr(getattr(exc, "resp", None), "status", 0) or 0)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_write_preflight_probe_cleanup_failed",
                module=logger.name,
                fields={
                    "folder_id": folder_id,
                    "probe_file_id": probe_file_id,
                    "status": status,
                    "retryable": status not in {400, 401, 403, 404},
                },
            )
        )
        return
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_write_preflight_probe_cleanup_failed",
                module=logger.name,
                fields={
                    "folder_id": folder_id,
                    "probe_file_id": probe_file_id,
                    "status": 0,
                    "retryable": True,
                },
            )
        )
        return
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_write_preflight_probe_complete",
            module=logger.name,
            fields={"folder_id": folder_id},
        )
    )


def _drive_write_preflight_probe_name(ctx: RunContext) -> str:
    tokens = [ctx.run_id, ctx.task_id, ctx.span_id]
    suffix = "-".join(_safe_drive_probe_token(token) for token in tokens if token)
    if not suffix:
        suffix = "run"
    return f".market-lense-write-preflight-{suffix}.txt"


def _safe_drive_probe_token(value: str) -> str:
    chars = []
    for char in str(value):
        if char.isalnum() or char in {"-", "_"}:
            chars.append(char)
            continue
        chars.append("-")
    token = "".join(chars).strip("-_")
    return token[:48] or "id"


def _escape_drive_query_value(value: str) -> str:
    return str(value).replace("\\", "\\\\").replace("'", "\\'")


def ensure_folder(
    request: DriveFolderEnsureRequest, ctx: RunContext
) -> DriveFolderEnsureResponse:
    auth_mode = _request_auth_mode(request)
    parent_folder_id = str(request.parent_folder_id or "").strip()
    folder_name = str(request.folder_name or "").strip()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_folder_ensure_start",
            module=logger.name,
            fields={
                "parent_folder_id": parent_folder_id,
                "folder_name": folder_name,
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
    if not parent_folder_id:
        raise AppError(
            code="drive_folder_parent_missing",
            message="Drive parent folder ID is required to ensure a child folder",
            retryable=False,
            severity="error",
        )
    if not folder_name:
        raise AppError(
            code="drive_folder_name_missing",
            message="Drive folder name is required to ensure a child folder",
            retryable=False,
            severity="error",
        )
    drive = _get_drive_client(
        auth_mode=auth_mode,
        service_account_path=request.service_account_path,
        oauth_token_path=request.oauth_token_path,
        ctx=ctx,
    )
    escaped_name = _escape_drive_query_value(folder_name)
    query = (
        f"'{parent_folder_id}' in parents "
        "and mimeType='application/vnd.google-apps.folder' "
        f"and name='{escaped_name}' and trashed=false"
    )
    list_kwargs = {
        "q": query,
        "fields": "files(id,name,modifiedTime,mimeType),nextPageToken",
        "pageSize": 10,
        "supportsAllDrives": request.supports_all_drives,
        "includeItemsFromAllDrives": request.include_items_from_all_drives,
    }
    if request.drive_id:
        list_kwargs["driveId"] = request.drive_id
        list_kwargs["corpora"] = "drive"
    try:
        existing = drive.files().list(**list_kwargs).execute()
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_folder_lookup_failed",
                module=logger.name,
                fields={
                    "parent_folder_id": parent_folder_id,
                    "folder_name": folder_name,
                    "error": str(exc),
                },
            )
        )
        raise AppError(
            code="drive_folder_lookup_failed",
            message="Drive folder lookup failed",
            cause=exc,
            retryable=True,
            severity="error",
            context={"parent_folder_id": parent_folder_id, "folder_name": folder_name},
        ) from exc
    for row in existing.get("files", []) if isinstance(existing, dict) else []:
        file_id = str((row or {}).get("id") or "").strip()
        name = str((row or {}).get("name") or "").strip()
        if file_id and name == folder_name:
            response = DriveFolderEnsureResponse(
                schema_version="1.0",
                folder=DriveFile(
                    schema_version="1.0",
                    file_id=file_id,
                    name=name,
                    modified_time=(row or {}).get("modifiedTime"),
                    md5_checksum=None,
                    mime_type=(row or {}).get("mimeType")
                    or "application/vnd.google-apps.folder",
                ),
                parent_folder_id=parent_folder_id,
                created=False,
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="drive_folder_ensure_complete",
                    module=logger.name,
                    fields={
                        "parent_folder_id": parent_folder_id,
                        "folder_id": response.folder.file_id,
                        "folder_name": folder_name,
                        "created": response.created,
                    },
                )
            )
            return response
    try:
        created = (
            drive.files()
            .create(
                body={
                    "name": folder_name,
                    "parents": [parent_folder_id],
                    "mimeType": "application/vnd.google-apps.folder",
                },
                fields="id,name,modifiedTime,mimeType",
                supportsAllDrives=request.supports_all_drives,
            )
            .execute()
        )
    except DRIVE_BOUNDARY_EXCEPTIONS as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_folder_create_failed",
                module=logger.name,
                fields={
                    "parent_folder_id": parent_folder_id,
                    "folder_name": folder_name,
                    "error": str(exc),
                },
            )
        )
        raise AppError(
            code="drive_folder_create_failed",
            message="Drive folder creation failed",
            cause=exc,
            retryable=True,
            severity="error",
            context={"parent_folder_id": parent_folder_id, "folder_name": folder_name},
        ) from exc
    folder_id = str((created or {}).get("id") or "").strip()
    if not folder_id:
        raise AppError(
            code="drive_folder_create_invalid_response",
            message="Drive folder creation did not return a folder ID",
            retryable=True,
            severity="error",
            context={"parent_folder_id": parent_folder_id, "folder_name": folder_name},
        )
    response = DriveFolderEnsureResponse(
        schema_version="1.0",
        folder=DriveFile(
            schema_version="1.0",
            file_id=folder_id,
            name=(created or {}).get("name") or folder_name,
            modified_time=(created or {}).get("modifiedTime"),
            md5_checksum=None,
            mime_type=(created or {}).get("mimeType")
            or "application/vnd.google-apps.folder",
        ),
        parent_folder_id=parent_folder_id,
        created=True,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_folder_ensure_complete",
            module=logger.name,
            fields={
                "parent_folder_id": parent_folder_id,
                "folder_id": response.folder.file_id,
                "folder_name": folder_name,
                "created": response.created,
            },
        )
    )
    return response


def upload_bytes(
    request: DriveUploadBytesRequest, ctx: RunContext
) -> DriveUploadBytesResponse:
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
    media = boundary.MediaIoBaseUpload(
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


def upload_local_file(
    request: DriveUploadLocalFileRequest,
    ctx: RunContext,
) -> DriveUploadLocalFileResponse:
    source_path = str(request.source_path or "").strip()
    file_name = str(request.file_name or "").strip()
    if not source_path:
        raise AppError(
            code="drive_upload_source_path_missing",
            message="Local source path is required to upload a Drive file",
            retryable=False,
        )
    path = Path(source_path)
    if not path.exists() or not path.is_file():
        raise AppError(
            code="drive_upload_source_path_invalid",
            message="Local source path does not exist or is not a file",
            retryable=False,
            context={"source_path": source_path},
        )
    if not file_name:
        file_name = path.name
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_upload_local_file_start",
            module=logger.name,
            fields={
                "folder_id": request.folder_id,
                "source_path": source_path,
                "file_name": file_name,
                "mime_type": request.mime_type,
                "supports_all_drives": request.supports_all_drives,
                "auth_mode": _request_auth_mode(request),
            },
        )
    )
    try:
        content = path.read_bytes()
    except OSError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="drive_upload_local_file_read_failed",
                module=logger.name,
                fields={"source_path": source_path, "error": str(exc)},
            )
        )
        raise AppError(
            code="drive_upload_source_read_failed",
            message="Local source file could not be read for Drive upload",
            cause=exc,
            retryable=True,
            context={"source_path": source_path},
        ) from exc
    upload_response = upload_bytes(
        DriveUploadBytesRequest(
            schema_version="1.0",
            folder_id=request.folder_id,
            service_account_path=request.service_account_path,
            file_name=file_name,
            content=content,
            mime_type=request.mime_type,
            supports_all_drives=request.supports_all_drives,
            auth_mode=request.auth_mode,
            oauth_client_path=request.oauth_client_path,
            oauth_token_path=request.oauth_token_path,
        ),
        ctx,
    )
    response = DriveUploadLocalFileResponse(
        schema_version="1.0",
        file=upload_response.file,
        source_path=source_path,
        size=upload_response.size,
        md5=upload_response.md5,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="drive_upload_local_file_complete",
            module=logger.name,
            fields={
                "folder_id": request.folder_id,
                "source_path": response.source_path,
                "file_id": response.file.file_id,
                "file_name": response.file.name or file_name,
                "size": response.size,
                "md5": response.md5 or "",
            },
        )
    )
    return response


__all__ = [
    name
    for name in globals()
    if not name.startswith("__") and name not in {"annotations"}
]
