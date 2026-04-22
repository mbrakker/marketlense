from __future__ import annotations

import os
from datetime import datetime, timezone

import pytest

from src.contracts.drive import (
    DriveDownloadRequest,
    DriveFile,
    DriveFolderFileListRequest,
    DriveUploadBytesRequest,
)
from src.contracts.run_context import RunContext
from src.services import drive_service
from src.utils.errors import AppError


def _drive_auth_kwargs() -> dict[str, object]:
    auth_mode = os.getenv("GOOGLE_DRIVE_AUTH_MODE", "service_account").strip()
    if auth_mode == "oauth_user":
        oauth_token_path = os.getenv("GOOGLE_OAUTH_TOKEN_JSON", "").strip()
        oauth_client_path = os.getenv("GOOGLE_OAUTH_CLIENT_JSON", "").strip()
        if not oauth_token_path or not oauth_client_path:
            pytest.skip(
                "GOOGLE_OAUTH_CLIENT_JSON and GOOGLE_OAUTH_TOKEN_JSON are required for oauth_user Drive integration."
            )
        return {
            "service_account_path": "",
            "auth_mode": "oauth_user",
            "oauth_client_path": oauth_client_path,
            "oauth_token_path": oauth_token_path,
        }

    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if not sa_path:
        pytest.skip("GOOGLE_SERVICE_ACCOUNT_JSON is required for Drive integration.")
    return {"service_account_path": sa_path, "auth_mode": "service_account"}


@pytest.mark.integration
def test_drive_upload_list_and_download_snapshot_roundtrip() -> None:
    folder_id = (
        os.getenv("PUBLISHER_DISCOVERY_TEST_FOLDER_ID", "").strip()
        or os.getenv("GDRIVE_FOLDER_ID", "").strip()
    )
    if not folder_id:
        pytest.skip("Drive integration folder not configured")
    auth_kwargs = _drive_auth_kwargs()

    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    file_name = (
        "publisher_inventory_snapshot__"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + ".json"
    )
    payload = b'{"schema_version":"1.0","publisher_name":"Integration Publisher"}'

    try:
        upload = drive_service.upload_bytes(
            DriveUploadBytesRequest(
                schema_version="1.0",
                folder_id=folder_id,
                file_name=file_name,
                content=payload,
                mime_type="application/json",
                **auth_kwargs,
            ),
            ctx,
        )
    except AppError as exc:
        cause = str(exc.cause or "")
        if exc.code == "drive_upload_failed" and (
            "storageQuotaExceeded" in cause
            or "Service Accounts do not have storage quota" in cause
        ):
            pytest.skip(
                "Configured service-account Drive credentials cannot upload without shared-drive quota or OAuth delegation."
            )
        raise
    assert upload.file.file_id

    listed = drive_service.list_files_in_folder(
        DriveFolderFileListRequest(
            schema_version="1.0",
            folder_id=folder_id,
            name_prefix=file_name,
            limit=5,
            **auth_kwargs,
        ),
        ctx,
    )
    assert any(item.file_id == upload.file.file_id for item in listed.files)

    downloaded = drive_service.download_pdf(
        DriveDownloadRequest(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=upload.file.file_id,
                name=upload.file.name,
                modified_time=upload.file.modified_time,
                md5_checksum=upload.file.md5_checksum,
                mime_type=upload.file.mime_type,
            ),
            **auth_kwargs,
        ),
        ctx,
    )
    assert downloaded.content == payload
