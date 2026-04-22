from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.contracts.drive import (
    DriveOAuthAuthorizeRequest,
    DriveDownloadToPathRequest,
    DriveFolderFileListRequest,
    DriveListRequest,
    DriveUploadBytesRequest,
    DriveUploadLocalFileRequest,
    DriveFile,
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
        return _FakeListCall(
            self._responses.get(query, {"files": [], "nextPageToken": None})
        )

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

    def get_media(self, *, fileId):
        return {"fileId": fileId}


class _FakeDriveClient:
    def __init__(self, responses: dict[str, dict], raise_on_query: str | None = None):
        self._files_resource = _FakeFilesResource(
            responses, raise_on_query=raise_on_query
        )

    def files(self):
        return self._files_resource


class _FakeAuthorizedUserCredentials:
    def __init__(
        self,
        *,
        valid: bool = True,
        expired: bool = False,
        refresh_token: str | None = "refresh-token",
    ):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.scopes = ["https://www.googleapis.com/auth/drive"]

    def refresh(self, _request):
        self.valid = True
        self.expired = False

    def to_json(self) -> str:
        return '{"refresh_token":"refresh-token","client_id":"client","client_secret":"secret","scopes":["https://www.googleapis.com/auth/drive"]}'


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
            "files": [
                {
                    "id": "root-pdf",
                    "name": "Root.pdf",
                    "modifiedTime": "2025-01-01T00:00:00Z",
                    "md5Checksum": "aaa",
                }
            ],
            "nextPageToken": None,
        },
        "'child-folder' in parents and mimeType='application/pdf' and trashed=false": {
            "files": [
                {
                    "id": "child-pdf",
                    "name": "Child.pdf",
                    "modifiedTime": "2025-01-02T00:00:00Z",
                    "md5Checksum": "bbb",
                }
            ],
            "nextPageToken": None,
        },
        "'grandchild-folder' in parents and mimeType='application/pdf' and trashed=false": {
            "files": [
                {
                    "id": "grandchild-pdf",
                    "name": "Grandchild.pdf",
                    "modifiedTime": "2025-01-03T00:00:00Z",
                    "md5Checksum": "ccc",
                }
            ],
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


def test_upload_local_file_reads_and_uploads_artifact(monkeypatch, tmp_path):
    fake_drive = _FakeDriveClient({})
    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    drive_service._DRIVE_CLIENTS = {}
    source_path = tmp_path / "report.html"
    source_path.write_text("<html>report</html>", encoding="utf-8")

    response = drive_service.upload_local_file(
        DriveUploadLocalFileRequest(
            schema_version="1.0",
            folder_id="root-folder",
            service_account_path="/tmp/fake-sa.json",
            source_path=str(source_path),
            file_name=None,
            mime_type="text/html",
        ),
        _ctx(),
    )

    assert response.source_path == str(source_path)
    assert response.size == len(source_path.read_bytes())
    assert response.md5 is not None
    assert response.file.file_id == "uploaded-file"
    created = fake_drive.files().created_payloads[0]
    assert created["body"]["name"] == "report.html"
    assert created["body"]["parents"] == ["root-folder"]


def test_upload_local_file_requires_existing_file(tmp_path):
    missing_path = tmp_path / "missing.pdf"

    with pytest.raises(AppError) as excinfo:
        drive_service.upload_local_file(
            DriveUploadLocalFileRequest(
                schema_version="1.0",
                folder_id="root-folder",
                service_account_path="/tmp/fake-sa.json",
                source_path=str(missing_path),
            ),
            _ctx(),
        )

    assert excinfo.value.code == "drive_upload_source_path_invalid"


def test_list_pdfs_uses_oauth_user_credentials(monkeypatch, tmp_path):
    responses = {
        "'root-folder' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false": {
            "files": [],
            "nextPageToken": None,
        },
        "'root-folder' in parents and mimeType='application/pdf' and trashed=false": {
            "files": [
                {
                    "id": "root-pdf",
                    "name": "Root.pdf",
                    "modifiedTime": "2025-01-01T00:00:00Z",
                    "md5Checksum": "aaa",
                }
            ],
            "nextPageToken": None,
        },
    }
    fake_drive = _FakeDriveClient(responses)
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        drive_service.AuthorizedUserCredentials,
        "from_authorized_user_file",
        staticmethod(lambda _path, scopes: _FakeAuthorizedUserCredentials()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    drive_service._DRIVE_CLIENTS = {}

    files = list(
        drive_service.list_pdfs(
            DriveListRequest(
                schema_version="1.0",
                folder_id="root-folder",
                service_account_path="",
                auth_mode="oauth_user",
                oauth_token_path=str(token_path),
                list_mode="full",
            ),
            _ctx(),
        )
    )

    assert [f.file_id for f in files] == ["root-pdf"]


def test_authorize_oauth_user_writes_token(monkeypatch, tmp_path):
    client_secret_path = tmp_path / "client.json"
    token_output_path = tmp_path / "token.json"
    client_secret_path.write_text("{}", encoding="utf-8")

    class _FakeFlow:
        @staticmethod
        def from_client_secrets_file(_path, _scopes):
            class _Runner:
                def run_local_server(self, port, open_browser):
                    assert port == 0
                    assert open_browser is True
                    return _FakeAuthorizedUserCredentials()

            return _Runner()

    monkeypatch.setattr(drive_service, "InstalledAppFlow", _FakeFlow)

    response = drive_service.authorize_oauth_user(
        DriveOAuthAuthorizeRequest(
            schema_version="1.0",
            client_secret_path=str(client_secret_path),
            token_output_path=str(token_output_path),
        ),
        _ctx(),
    )

    assert token_output_path.exists()
    assert response.token_output_path == str(token_output_path)
    assert response.refresh_token_present is True


def test_list_pdfs_wraps_missing_service_account_path_as_typed_error(
    monkeypatch, assert_app_error
):
    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(
            lambda _sa_path, scopes: (_ for _ in ()).throw(FileNotFoundError("missing"))
        ),
    )
    drive_service._DRIVE_CLIENTS = {}

    with pytest.raises(AppError) as err:
        list(drive_service.list_pdfs(_request(), _ctx()))

    assert_app_error(err.value, code="drive_service_account_invalid", retryable=False)


def test_download_pdf_to_path_removes_partial_file_on_failure(
    monkeypatch, tmp_path, assert_app_error
):
    fake_drive = _FakeDriveClient({})
    output_path = tmp_path / "downloaded.pdf"

    class _FailingDownloader:
        def __init__(self, writer, _request):
            self._writer = writer
            self._attempts = 0

        def next_chunk(self):
            self._attempts += 1
            self._writer.write(b"%PDF-partial")
            raise RuntimeError("chunk failed")

    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    monkeypatch.setattr(drive_service, "MediaIoBaseDownload", _FailingDownloader)
    drive_service._DRIVE_CLIENTS = {}

    with pytest.raises(AppError) as err:
        drive_service.download_pdf_to_path(
            DriveDownloadToPathRequest(
                schema_version="1.0",
                file=DriveFile(
                    schema_version="1.0",
                    file_id="file-1",
                    name="report.pdf",
                    modified_time=None,
                    md5_checksum=None,
                ),
                service_account_path="/tmp/fake-sa.json",
                output_path=str(output_path),
                make_parents=True,
            ),
            _ctx(),
        )

    assert_app_error(err.value, code="drive_download_failed", retryable=True)
    assert not output_path.exists()
