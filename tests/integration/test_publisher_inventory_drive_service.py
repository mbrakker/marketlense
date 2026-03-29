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


@pytest.mark.integration
def test_drive_upload_list_and_download_snapshot_roundtrip() -> None:
    sa_path = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    folder_id = (
        os.getenv("PUBLISHER_DISCOVERY_TEST_FOLDER_ID", "").strip()
        or os.getenv("GDRIVE_FOLDER_ID", "").strip()
    )
    if not sa_path or not folder_id:
        pytest.skip("Drive integration credentials/folder not configured")

    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")
    file_name = (
        "publisher_inventory_snapshot__"
        + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        + ".json"
    )
    payload = b'{"schema_version":"1.0","publisher_name":"Integration Publisher"}'

    upload = drive_service.upload_bytes(
        DriveUploadBytesRequest(
            schema_version="1.0",
            folder_id=folder_id,
            service_account_path=sa_path,
            file_name=file_name,
            content=payload,
            mime_type="application/json",
        ),
        ctx,
    )
    assert upload.file.file_id

    listed = drive_service.list_files_in_folder(
        DriveFolderFileListRequest(
            schema_version="1.0",
            folder_id=folder_id,
            service_account_path=sa_path,
            name_prefix=file_name,
            limit=5,
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
            service_account_path=sa_path,
        ),
        ctx,
    )
    assert downloaded.content == payload
