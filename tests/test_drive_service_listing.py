from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.contracts.drive import (
    DriveFolderFileListRequest,
    DriveListRequest,
    DriveUploadBytesRequest,
)
from src.contracts.run_context import RunContext
from src.services import drive_service
from src.utils.errors import AppError


@dataclass
class _FakeListCall:
    payload: dict

    def execute(self):
        return self.payload


class _FakeFilesResource:
    def __init__(self, responses: dict[str, dict], raise_on_query: str | None = None):
        self._responses = responses
        self._raise_on_query = raise_on_query
        self.created_payloads: list[dict] = []

    def list(self, **kwargs):
        query = kwargs.get("q", "")
        if self._raise_on_query and self._raise_on_query == query:
            raise RuntimeError("boom")
        return _FakeListCall(self._responses.get(query, {"files": [], "nextPageToken": None}))

    def create(self, **kwargs):
        payload = {
            "id": "uploaded-file",
            "name": kwargs["body"]["name"],
            "modifiedTime": "2026-03-29T00:00:00Z",
            "md5Checksum": "abc123",
            "mimeType": "application/json",
        }
        self.created_payloads.append(kwargs)
        return _FakeListCall(payload)


class _FakeDriveClient:
    def __init__(self, responses: dict[str, dict], raise_on_query: str | None = None):
        self._files_resource = _FakeFilesResource(responses, raise_on_query=raise_on_query)

    def files(self):
        return self._files_resource


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r1", task_id="t1", span_id="s1")


def _request() -> DriveListRequest:
    return DriveListRequest(
        schema_version="1.0",
        folder_id="root-folder",
        service_account_path="/tmp/fake-sa.json",
        list_mode="full",
    )


def test_list_pdfs_includes_nested_subfolders(monkeypatch):
    responses = {
        "'root-folder' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false": {
            "files": [{"id": "child-folder"}],
            "nextPageToken": None,
        },
        "'child-folder' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false": {
            "files": [{"id": "grandchild-folder"}],
            "nextPageToken": None,
        },
        "'grandchild-folder' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false": {
            "files": [],
            "nextPageToken": None,
        },
        "'root-folder' in parents and mimeType='application/pdf' and trashed=false": {
            "files": [{"id": "root-pdf", "name": "Root.pdf", "modifiedTime": "2025-01-01T00:00:00Z", "md5Checksum": "aaa"}],
            "nextPageToken": None,
        },
        "'child-folder' in parents and mimeType='application/pdf' and trashed=false": {
            "files": [{"id": "child-pdf", "name": "Child.pdf", "modifiedTime": "2025-01-02T00:00:00Z", "md5Checksum": "bbb"}],
            "nextPageToken": None,
        },
        "'grandchild-folder' in parents and mimeType='application/pdf' and trashed=false": {
            "files": [{"id": "grandchild-pdf", "name": "Grandchild.pdf", "modifiedTime": "2025-01-03T00:00:00Z", "md5Checksum": "ccc"}],
            "nextPageToken": None,
        },
    }

    fake_drive = _FakeDriveClient(responses)

    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    drive_service._DRIVE_CLIENTS = {}

    files = list(drive_service.list_pdfs(_request(), _ctx()))

    assert [f.file_id for f in files] == ["root-pdf", "child-pdf", "grandchild-pdf"]


def test_list_pdfs_subfolder_discovery_error_is_retryable_app_error(
    monkeypatch, assert_app_error
):
    failing_query = "'root-folder' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false"
    fake_drive = _FakeDriveClient({}, raise_on_query=failing_query)

    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    drive_service._DRIVE_CLIENTS = {}

    with pytest.raises(AppError) as err:
        list(drive_service.list_pdfs(_request(), _ctx()))

    assert_app_error(err.value, code="drive_list_failed", retryable=True)


def test_list_files_in_folder_filters_by_prefix(monkeypatch):
    query = "'root-folder' in parents and trashed=false and name contains 'publisher_inventory_snapshot__'"
    fake_drive = _FakeDriveClient(
        {
            query: {
                "files": [
                    {
                        "id": "snapshot-1",
                        "name": "publisher_inventory_snapshot__20260329T000000Z.json",
                        "modifiedTime": "2026-03-29T00:00:00Z",
                        "md5Checksum": "aaa",
                        "mimeType": "application/json",
                    }
                ],
                "nextPageToken": None,
            }
        }
    )
    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    drive_service._DRIVE_CLIENTS = {}

    response = drive_service.list_files_in_folder(
        DriveFolderFileListRequest(
            schema_version="1.0",
            folder_id="root-folder",
            service_account_path="/tmp/fake-sa.json",
            name_prefix="publisher_inventory_snapshot__",
            limit=10,
        ),
        _ctx(),
    )

    assert [item.file_id for item in response.files] == ["snapshot-1"]
    assert response.files[0].mime_type == "application/json"


def test_upload_bytes_creates_drive_file(monkeypatch):
    fake_drive = _FakeDriveClient({})
    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    drive_service._DRIVE_CLIENTS = {}

    response = drive_service.upload_bytes(
        DriveUploadBytesRequest(
            schema_version="1.0",
            folder_id="root-folder",
            service_account_path="/tmp/fake-sa.json",
            file_name="publisher_inventory_snapshot__20260329T000000Z.json",
            content=b"{}",
            mime_type="application/json",
        ),
        _ctx(),
    )

    assert response.file.file_id == "uploaded-file"
    assert response.file.mime_type == "application/json"
    assert fake_drive.files().created_payloads[0]["body"]["parents"] == ["root-folder"]
