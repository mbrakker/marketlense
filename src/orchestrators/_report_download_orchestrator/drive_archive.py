from __future__ import annotations

import logging
import mimetypes
from dataclasses import asdict
from pathlib import Path

from src.contracts.browser_download import (
    BrowserReportDownloadResult,
    ReportDownloadDriveUpload,
    ReportDownloadOrchestratorRequest,
)
from src.contracts.drive import DriveFolderFileListRequest, DriveUploadLocalFileRequest
from src.contracts.files import FileHashRequest
from src.contracts.report_store import ReportDownloadDriveFolderLookupRequest
from src.contracts.run_context import RunContext
from src.orchestrators._report_download_orchestrator.dependencies import (
    ReportDownloadDependencies,
)
from src.orchestrators._report_download_orchestrator.persistence import (
    _idempotency_key_with_checksum,
    _lookup_idempotency_record,
    _record_idempotency_outcome,
    _restore_drive_upload,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.utils.cache_utils import sha256_json
from src.utils.drive_utils import extract_drive_folder_id
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.report_download_orchestrator")

_REPORT_DOWNLOAD_DRIVE_UPLOAD_SCOPE = "report_download_orchestrator.drive_upload"


def archive_successful_report_artifacts(
    *,
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
    normalized_url: str,
    policy: RetryPolicy,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> list[ReportDownloadDriveUpload]:
    if not request.settings.drive_upload_enabled:
        return []
    if result.outcome not in {"downloaded", "captured"}:
        return []
    artifact_paths = _local_terminal_artifact_paths(result)
    if not artifact_paths:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_upload_no_artifacts",
                module=logger.name,
                fields={"normalized_url": normalized_url, "outcome": result.outcome},
            )
        )
        return []
    try:
        folder_id = _resolve_drive_upload_folder_id(
            request=request,
            normalized_url=normalized_url,
            ctx=ctx,
            dependencies=dependencies,
        )
        uploads = []
        for path in artifact_paths:
            uploads.append(
                archive_single_artifact(
                    request=request,
                    result=result,
                    normalized_url=normalized_url,
                    local_path=path,
                    folder_id=folder_id,
                    policy=policy,
                    ctx=ctx,
                    dependencies=dependencies,
                )
            )
        return uploads
    except AppError:
        if request.settings.drive_upload_required:
            raise
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_upload_best_effort_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url},
            )
        )
        return []


def _resolve_drive_upload_folder_id(
    *,
    request: ReportDownloadOrchestratorRequest,
    normalized_url: str,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> str:
    explicit_folder_id = extract_drive_folder_id(request.publisher_google_folder or "")
    if explicit_folder_id:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_folder_resolved",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "resolution_source": "request_publisher_google_folder",
                    "folder_id": explicit_folder_id,
                },
            )
        )
        return explicit_folder_id
    lookup = dependencies.get_report_download_drive_folder(
        ReportDownloadDriveFolderLookupRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            normalized_landing_page_url=normalized_url,
            publisher_insights_url=request.publisher_insights_url,
        ),
        ctx,
    )
    folder_id = extract_drive_folder_id(lookup.google_folder if lookup else "")
    if folder_id:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_folder_resolved",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "resolution_source": lookup.resolution_source if lookup else "",
                    "publisher_name": lookup.publisher_name if lookup else "",
                    "folder_id": folder_id,
                },
            )
        )
        return folder_id
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_drive_folder_missing",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "has_publisher_insights_url": bool(request.publisher_insights_url),
            },
        )
    )
    raise AppError(
        code="report_download_drive_folder_missing",
        message="Publisher Drive folder could not be resolved for acquired report archival",
        retryable=False,
        severity="error",
        context={
            "normalized_url": normalized_url,
            "publisher_insights_url": request.publisher_insights_url or "",
        },
    )


def archive_single_artifact(
    *,
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
    normalized_url: str,
    local_path: str,
    folder_id: str,
    policy: RetryPolicy,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> ReportDownloadDriveUpload:
    path = Path(local_path)
    file_name = path.name
    mime_type = _mime_type_for_artifact(result=result, path=path)
    file_hash = dependencies.file_md5(
        FileHashRequest(schema_version="1.0", path=str(path)),
        ctx,
    )
    size = path.stat().st_size
    upload_checksum = sha256_json(
        {
            "schema_version": "1.0",
            "folder_id": folder_id,
            "normalized_url": normalized_url,
            "file_name": file_name,
            "mime_type": mime_type,
            "size": size,
            "md5": file_hash.md5,
        }
    )
    upload_key = _idempotency_key_with_checksum(
        folder_id,
        normalized_url,
        file_name,
        checksum=upload_checksum,
    )
    existing_upload = _lookup_idempotency_record(
        db_path=request.reports_db,
        scope=_REPORT_DOWNLOAD_DRIVE_UPLOAD_SCOPE,
        idempotency_key=upload_key,
        input_checksum=upload_checksum,
        ctx=ctx,
    )
    if existing_upload is not None:
        upload = _restore_drive_upload(dict(existing_upload.outcome_payload or {}))
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_upload_idempotency_reused",
                module=logger.name,
                fields={
                    "local_path": upload.local_path,
                    "folder_id": upload.folder_id,
                    "file_name": upload.file_name,
                    "status": upload.status,
                    "drive_file_id": upload.drive_file.file_id,
                    "md5": upload.md5 or "",
                },
            )
        )
        return upload
    duplicate = _find_duplicate_drive_file(
        request=request,
        folder_id=folder_id,
        file_name=file_name,
        md5=file_hash.md5,
        policy=policy,
        ctx=ctx,
        dependencies=dependencies,
    )
    if duplicate is not None:
        upload = ReportDownloadDriveUpload(
            schema_version="1.0",
            local_path=str(path),
            file_name=file_name,
            mime_type=mime_type,
            folder_id=folder_id,
            status="skipped_duplicate",
            size=size,
            md5=file_hash.md5,
            drive_file=duplicate,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_upload_skipped_duplicate",
                module=logger.name,
                fields={
                    "local_path": upload.local_path,
                    "folder_id": folder_id,
                    "file_name": file_name,
                    "drive_file_id": duplicate.file_id,
                    "md5": file_hash.md5,
                },
            )
        )
        _record_idempotency_outcome(
            db_path=request.reports_db,
            scope=_REPORT_DOWNLOAD_DRIVE_UPLOAD_SCOPE,
            idempotency_key=upload_key,
            input_checksum=upload_checksum,
            outcome_payload=asdict(upload),
            artifact_references={
                "folder_id": upload.folder_id,
                "file_name": upload.file_name,
                "drive_file_id": upload.drive_file.file_id,
                "md5": upload.md5,
                "status": upload.status,
            },
            ctx=ctx,
        )
        return upload
    upload_response = run_with_retry(
        step_name="report_download_drive_upload",
        operation=lambda: dependencies.upload_local_file(
            DriveUploadLocalFileRequest(
                schema_version="1.0",
                folder_id=folder_id,
                service_account_path=request.settings.drive_upload_google_sa_path,
                source_path=str(path),
                file_name=file_name,
                mime_type=mime_type,
                supports_all_drives=request.settings.drive_upload_supports_all_drives,
                auth_mode=request.settings.drive_upload_auth_mode,
                oauth_client_path=request.settings.drive_upload_oauth_client_path,
                oauth_token_path=request.settings.drive_upload_oauth_token_path,
            ),
            ctx,
        ),
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=policy,
        retry_event="report_download_drive_upload_retry",
        failure_event="report_download_drive_upload_failed",
        sleep_fn=dependencies.sleep_fn,
    )
    upload = ReportDownloadDriveUpload(
        schema_version="1.0",
        local_path=str(path),
        file_name=file_name,
        mime_type=mime_type,
        folder_id=folder_id,
        status="uploaded",
        size=upload_response.size,
        md5=upload_response.md5,
        drive_file=upload_response.file,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_drive_uploaded",
            module=logger.name,
            fields={
                "local_path": upload.local_path,
                "folder_id": folder_id,
                "file_name": file_name,
                "drive_file_id": upload.drive_file.file_id,
                "size": upload.size,
                "md5": upload.md5 or "",
            },
        )
    )
    _record_idempotency_outcome(
        db_path=request.reports_db,
        scope=_REPORT_DOWNLOAD_DRIVE_UPLOAD_SCOPE,
        idempotency_key=upload_key,
        input_checksum=upload_checksum,
        outcome_payload=asdict(upload),
        artifact_references={
            "folder_id": upload.folder_id,
            "file_name": upload.file_name,
            "drive_file_id": upload.drive_file.file_id,
            "md5": upload.md5,
            "status": upload.status,
        },
        ctx=ctx,
    )
    return upload


def _find_duplicate_drive_file(
    *,
    request: ReportDownloadOrchestratorRequest,
    folder_id: str,
    file_name: str,
    md5: str,
    policy: RetryPolicy,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
):
    response = run_with_retry(
        step_name="report_download_drive_duplicate_check",
        operation=lambda: dependencies.list_files_in_folder(
            DriveFolderFileListRequest(
                schema_version="1.0",
                folder_id=folder_id,
                service_account_path=request.settings.drive_upload_google_sa_path,
                name_prefix=file_name,
                supports_all_drives=request.settings.drive_upload_supports_all_drives,
                include_items_from_all_drives=(
                    request.settings.drive_upload_include_items_from_all_drives
                ),
                drive_id=request.settings.drive_upload_drive_id,
                auth_mode=request.settings.drive_upload_auth_mode,
                oauth_client_path=request.settings.drive_upload_oauth_client_path,
                oauth_token_path=request.settings.drive_upload_oauth_token_path,
            ),
            ctx,
        ),
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=policy,
        retry_event="report_download_drive_duplicate_check_retry",
        failure_event="report_download_drive_duplicate_check_failed",
        sleep_fn=dependencies.sleep_fn,
    )
    for file in response.files:
        if (file.name or "") == file_name and (file.md5_checksum or "") == md5:
            return file
    return None


def _local_terminal_artifact_paths(result: BrowserReportDownloadResult) -> list[str]:
    candidates = [
        result.downloaded_file_path,
        result.onsite_capture_path,
        result.terminal_evidence.html_snapshot_path,
        result.terminal_evidence.screenshot_path,
    ]
    seen: set[str] = set()
    paths: list[str] = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        if not value:
            continue
        key = _local_artifact_identity_key(value)
        if key in seen:
            continue
        seen.add(key)
        paths.append(value)
    return paths


def _local_artifact_identity_key(value: str) -> str:
    path = Path(value)
    try:
        return str(path.resolve(strict=False)).casefold()
    except OSError:
        return str(path).casefold()


def _mime_type_for_artifact(*, result: BrowserReportDownloadResult, path: Path) -> str:
    if result.downloaded_file_path and Path(result.downloaded_file_path) == path:
        return result.downloaded_mime_type or "application/octet-stream"
    if result.onsite_capture_path and Path(result.onsite_capture_path) == path:
        if result.onsite_capture_format in {"html", "html+markdown"}:
            return "text/html"
        if result.onsite_capture_format == "markdown":
            return "text/markdown"
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"
