from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from src.contracts.drive import (
    DriveOAuthAuthorizeRequest,
    DriveDownloadToPathRequest,
    DriveFolderFileListRequest,
    DriveListRequest,
    DriveWritePreflightRequest,
    DriveUploadBytesRequest,
    DriveUploadLocalFileRequest,
    DriveFile,
    DriveFolderEnsureRequest,
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
    def __init__(
        self,
        responses: dict[Any, dict],
        raise_on_query: str | None = None,
        get_response: dict | None = None,
        get_error: Exception | None = None,
        create_error: Exception | None = None,
        delete_error: Exception | None = None,
    ):
        self._responses = responses
        self._raise_on_query = raise_on_query
        self._get_response = get_response or {}
        self._get_error = get_error
        self._create_error = create_error
        self._delete_error = delete_error
        self.created_payloads: list[dict] = []
        self.delete_calls: list[dict] = []
        self.list_calls: list[dict] = []
        self.get_calls: list[dict] = []

    def list(self, **kwargs):
        query = kwargs.get("q", "")
        if self._raise_on_query and self._raise_on_query == query:
            raise RuntimeError("boom")
        self.list_calls.append(dict(kwargs))
        page_token = kwargs.get("pageToken")
        payload = self._responses.get((query, page_token))
        if payload is None:
            payload = self._responses.get(query, {"files": [], "nextPageToken": None})
        return _FakeListCall(payload)

    def create(self, **kwargs):
        if self._create_error is not None:
            raise self._create_error
        payload = {
            "id": "uploaded-file",
            "name": kwargs["body"]["name"],
            "modifiedTime": "2026-03-29T00:00:00Z",
            "md5Checksum": "abc123",
            "mimeType": "application/json",
        }
        self.created_payloads.append(kwargs)
        return _FakeListCall(payload)

    def delete(self, **kwargs):
        self.delete_calls.append(dict(kwargs))
        if self._delete_error is not None:
            raise self._delete_error
        return _FakeListCall({})

    def get(self, **kwargs):
        self.get_calls.append(dict(kwargs))
        if self._get_error is not None:
            raise self._get_error
        return _FakeListCall(self._get_response)

    def get_media(self, *, fileId):
        return {"fileId": fileId}


class _FakeDriveClient:
    def __init__(
        self,
        responses: dict[str, dict],
        raise_on_query: str | None = None,
        get_response: dict | None = None,
        get_error: Exception | None = None,
        create_error: Exception | None = None,
        delete_error: Exception | None = None,
    ):
        self._files_resource = _FakeFilesResource(
            responses,
            raise_on_query=raise_on_query,
            get_response=get_response,
            get_error=get_error,
            create_error=create_error,
            delete_error=delete_error,
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
        scopes: list[str] | None = None,
        refresh_error: Exception | None = None,
    ):
        self.valid = valid
        self.expired = expired
        self.refresh_token = refresh_token
        self.scopes = scopes or ["https://www.googleapis.com/auth/drive"]
        self.refresh_error = refresh_error
        self.refresh_count = 0

    def refresh(self, _request):
        self.refresh_count += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        self.valid = True
        self.expired = False

    def to_json(self) -> str:
        return '{"refresh_token":"refresh-token","client_id":"client","client_secret":"secret","scopes":["https://www.googleapis.com/auth/drive"]}'


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r1", task_id="t1", span_id="s1")


def _reset_drive_caches() -> None:
    drive_service._DRIVE_CLIENTS = {}
    drive_service._FOLDER_SCOPE_CACHE = {}


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
    _reset_drive_caches()

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
    _reset_drive_caches()

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
    _reset_drive_caches()

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
    _reset_drive_caches()

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


def test_ensure_folder_reuses_existing_child_folder(monkeypatch):
    fake_drive = _FakeDriveClient(
        {
            "'root-folder' in parents and mimeType='application/vnd.google-apps.folder' and name='Publisher A' and trashed=false": {
                "files": [
                    {
                        "id": "publisher-folder",
                        "name": "Publisher A",
                        "modifiedTime": "2026-06-03T00:00:00Z",
                        "mimeType": "application/vnd.google-apps.folder",
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
    _reset_drive_caches()

    response = drive_service.ensure_folder(
        DriveFolderEnsureRequest(
            schema_version="1.0",
            parent_folder_id="root-folder",
            folder_name="Publisher A",
            service_account_path="/tmp/fake-sa.json",
        ),
        _ctx(),
    )

    assert response.folder.file_id == "publisher-folder"
    assert response.created is False
    assert fake_drive.files().created_payloads == []


def test_ensure_folder_creates_missing_child_folder(monkeypatch):
    fake_drive = _FakeDriveClient({})
    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    _reset_drive_caches()

    response = drive_service.ensure_folder(
        DriveFolderEnsureRequest(
            schema_version="1.0",
            parent_folder_id="root-folder",
            folder_name="Publisher A",
            service_account_path="/tmp/fake-sa.json",
        ),
        _ctx(),
    )

    assert response.folder.file_id == "uploaded-file"
    assert response.created is True
    created = fake_drive.files().created_payloads[0]
    assert created["body"] == {
        "name": "Publisher A",
        "parents": ["root-folder"],
        "mimeType": "application/vnd.google-apps.folder",
    }


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


def test_preflight_drive_write_access_validates_folder_write_readiness(
    monkeypatch, assert_no_defaulted_required_fields
):
    fake_drive = _FakeDriveClient(
        {},
        get_response={
            "id": "root-folder",
            "mimeType": "application/vnd.google-apps.folder",
            "capabilities": {"canAddChildren": True},
        },
    )
    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: _FakeAuthorizedUserCredentials()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    _reset_drive_caches()

    response = drive_service.preflight_drive_write_access(
        DriveWritePreflightRequest(
            schema_version="1.0",
            folder_id="root-folder",
            service_account_path="/tmp/fake-sa.json",
        ),
        _ctx(),
    )

    assert response.folder_id == "root-folder"
    assert response.scopes_verified is True
    assert response.folder_access_verified is True
    assert response.write_access_verified is True
    assert response.credentials_refreshed is False
    assert fake_drive.files().get_calls[0]["fileId"] == "root-folder"
    assert fake_drive.files().get_calls[0]["supportsAllDrives"] is True
    assert fake_drive.files().created_payloads[0]["body"]["parents"] == ["root-folder"]
    assert fake_drive.files().delete_calls[0]["fileId"] == "uploaded-file"
    assert_no_defaulted_required_fields(response)


def test_preflight_drive_write_access_refreshes_expired_oauth_token(
    monkeypatch, tmp_path
):
    fake_drive = _FakeDriveClient(
        {},
        get_response={
            "id": "root-folder",
            "mimeType": "application/vnd.google-apps.folder",
            "capabilities": {"canAddChildren": True},
        },
    )
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    credentials = _FakeAuthorizedUserCredentials(valid=False, expired=True)

    monkeypatch.setattr(
        drive_service.AuthorizedUserCredentials,
        "from_authorized_user_file",
        staticmethod(lambda _path, scopes: credentials),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    _reset_drive_caches()

    response = drive_service.preflight_drive_write_access(
        DriveWritePreflightRequest(
            schema_version="1.0",
            folder_id="root-folder",
            service_account_path="",
            auth_mode="oauth_user",
            oauth_token_path=str(token_path),
        ),
        _ctx(),
    )

    assert response.credentials_refreshed is True
    assert credentials.refresh_count == 1
    assert token_path.read_text(encoding="utf-8").startswith('{"refresh_token"')


def test_preflight_drive_write_access_reports_oauth_refresh_failure(
    monkeypatch, tmp_path, assert_app_error
):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    credentials = _FakeAuthorizedUserCredentials(
        valid=False,
        expired=True,
        refresh_error=drive_service.RefreshError("refresh denied"),
    )

    monkeypatch.setattr(
        drive_service.AuthorizedUserCredentials,
        "from_authorized_user_file",
        staticmethod(lambda _path, scopes: credentials),
    )
    _reset_drive_caches()

    with pytest.raises(AppError) as err:
        drive_service.preflight_drive_write_access(
            DriveWritePreflightRequest(
                schema_version="1.0",
                folder_id="root-folder",
                service_account_path="",
                auth_mode="oauth_user",
                oauth_token_path=str(token_path),
            ),
            _ctx(),
        )

    assert_app_error(err.value, code="drive_oauth_refresh_failed", retryable=False)


def test_preflight_drive_write_access_rejects_insufficient_oauth_scope(
    monkeypatch, tmp_path, assert_app_error
):
    token_path = tmp_path / "token.json"
    token_path.write_text("{}", encoding="utf-8")
    credentials = _FakeAuthorizedUserCredentials(
        scopes=["https://www.googleapis.com/auth/drive.metadata.readonly"]
    )

    monkeypatch.setattr(
        drive_service.AuthorizedUserCredentials,
        "from_authorized_user_file",
        staticmethod(lambda _path, scopes: credentials),
    )
    _reset_drive_caches()

    with pytest.raises(AppError) as err:
        drive_service.preflight_drive_write_access(
            DriveWritePreflightRequest(
                schema_version="1.0",
                folder_id="root-folder",
                service_account_path="",
                auth_mode="oauth_user",
                oauth_token_path=str(token_path),
            ),
            _ctx(),
        )

    assert_app_error(
        err.value, code="drive_preflight_scope_insufficient", retryable=False
    )


def test_preflight_drive_write_access_reports_missing_oauth_token(
    tmp_path, assert_app_error
):
    with pytest.raises(AppError) as err:
        drive_service.preflight_drive_write_access(
            DriveWritePreflightRequest(
                schema_version="1.0",
                folder_id="root-folder",
                service_account_path="",
                auth_mode="oauth_user",
                oauth_token_path=str(tmp_path / "missing-token.json"),
            ),
            _ctx(),
        )

    assert_app_error(err.value, code="drive_oauth_token_missing", retryable=False)


def test_preflight_drive_write_access_rejects_folder_without_write_capability(
    monkeypatch, assert_app_error
):
    fake_drive = _FakeDriveClient(
        {},
        get_response={
            "id": "root-folder",
            "mimeType": "application/vnd.google-apps.folder",
            "capabilities": {"canAddChildren": False},
        },
    )
    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: _FakeAuthorizedUserCredentials()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    _reset_drive_caches()

    with pytest.raises(AppError) as err:
        drive_service.preflight_drive_write_access(
            DriveWritePreflightRequest(
                schema_version="1.0",
                folder_id="root-folder",
                service_account_path="/tmp/fake-sa.json",
            ),
            _ctx(),
        )

    assert_app_error(err.value, code="drive_preflight_no_write_access", retryable=False)


def test_preflight_drive_write_access_rejects_failed_write_probe(
    monkeypatch, assert_app_error
):
    fake_drive = _FakeDriveClient(
        {},
        get_response={
            "id": "root-folder",
            "mimeType": "application/vnd.google-apps.folder",
            "capabilities": {"canAddChildren": True},
        },
        create_error=RuntimeError("storage quota exceeded"),
    )
    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: _FakeAuthorizedUserCredentials()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    _reset_drive_caches()

    with pytest.raises(AppError) as err:
        drive_service.preflight_drive_write_access(
            DriveWritePreflightRequest(
                schema_version="1.0",
                folder_id="root-folder",
                service_account_path="/tmp/fake-sa.json",
            ),
            _ctx(),
        )

    assert_app_error(
        err.value, code="drive_preflight_write_probe_failed", retryable=True
    )


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
    _reset_drive_caches()

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
    _reset_drive_caches()

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
    _reset_drive_caches()

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


def test_list_pdfs_streams_pages_incrementally(monkeypatch):
    folder_query = (
        "'root-folder' in parents and mimeType='application/vnd.google-apps.folder' "
        "and trashed=false"
    )
    pdf_query = "'root-folder' in parents and mimeType='application/pdf' and trashed=false"
    fake_drive = _FakeDriveClient(
        {
            folder_query: {"files": [], "nextPageToken": None},
            (pdf_query, None): {
                "files": [
                    {
                        "id": "page-1",
                        "name": "Page1.pdf",
                        "modifiedTime": "2025-01-01T00:00:00Z",
                        "md5Checksum": "aaa",
                    }
                ],
                "nextPageToken": "token-2",
            },
            (pdf_query, "token-2"): {
                "files": [
                    {
                        "id": "page-2",
                        "name": "Page2.pdf",
                        "modifiedTime": "2025-01-02T00:00:00Z",
                        "md5Checksum": "bbb",
                    }
                ],
                "nextPageToken": None,
            },
        }
    )
    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    _reset_drive_caches()

    iterator = drive_service.list_pdfs(_request(), _ctx())
    first = next(iterator)
    pdf_calls_after_first = [
        call for call in fake_drive.files().list_calls if call.get("q") == pdf_query
    ]

    assert first.file_id == "page-1"
    assert len(pdf_calls_after_first) == 1
    assert pdf_calls_after_first[0].get("pageToken") is None

    second = next(iterator)
    pdf_calls_after_second = [
        call for call in fake_drive.files().list_calls if call.get("q") == pdf_query
    ]

    assert second.file_id == "page-2"
    assert len(pdf_calls_after_second) == 2
    assert pdf_calls_after_second[1].get("pageToken") == "token-2"
    assert list(iterator) == []


def test_list_pdfs_reuses_cached_folder_scope_until_invalidated(monkeypatch):
    folder_query_root = (
        "'root-folder' in parents and mimeType='application/vnd.google-apps.folder' "
        "and trashed=false"
    )
    folder_query_child_a = (
        "'child-a' in parents and mimeType='application/vnd.google-apps.folder' "
        "and trashed=false"
    )
    folder_query_child_b = (
        "'child-b' in parents and mimeType='application/vnd.google-apps.folder' "
        "and trashed=false"
    )
    pdf_query_root = "'root-folder' in parents and mimeType='application/pdf' and trashed=false"
    pdf_query_child_a = "'child-a' in parents and mimeType='application/pdf' and trashed=false"
    pdf_query_child_b = "'child-b' in parents and mimeType='application/pdf' and trashed=false"
    responses: dict[Any, dict] = {
        folder_query_root: {"files": [{"id": "child-a"}], "nextPageToken": None},
        folder_query_child_a: {"files": [], "nextPageToken": None},
        pdf_query_root: {"files": [{"id": "root-pdf"}], "nextPageToken": None},
        pdf_query_child_a: {"files": [{"id": "child-a-pdf"}], "nextPageToken": None},
    }
    fake_drive = _FakeDriveClient(responses)
    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    monkeypatch.setattr(drive_service, "build", lambda *_args, **_kwargs: fake_drive)
    _reset_drive_caches()

    first = list(drive_service.list_pdfs(_request(), _ctx()))
    assert [file.file_id for file in first] == ["root-pdf", "child-a-pdf"]

    responses[folder_query_root] = {
        "files": [{"id": "child-a"}, {"id": "child-b"}],
        "nextPageToken": None,
    }
    responses[folder_query_child_b] = {"files": [], "nextPageToken": None}
    responses[pdf_query_child_b] = {
        "files": [{"id": "child-b-pdf"}],
        "nextPageToken": None,
    }

    second = list(drive_service.list_pdfs(_request(), _ctx()))
    assert [file.file_id for file in second] == ["root-pdf", "child-a-pdf"]

    removed = drive_service._invalidate_folder_scope_cache(folder_id="root-folder")
    third = list(drive_service.list_pdfs(_request(), _ctx()))

    assert removed == 1
    assert [file.file_id for file in third] == [
        "root-pdf",
        "child-a-pdf",
        "child-b-pdf",
    ]


def test_drive_client_cache_expires_and_evicts_oldest(monkeypatch):
    created: list[object] = []
    timestamps = iter([0.0, 1.0, 2.0, 3.0, 4.0, 11.0])

    def _fake_build(service_name: str, version: str, http, cache_discovery: bool):
        assert service_name == "drive"
        assert version == "v3"
        assert http is not None
        assert cache_discovery is False
        client = object()
        created.append(client)
        return client

    monkeypatch.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda _sa_path, scopes: object()),
    )
    monkeypatch.setattr(drive_service, "build", _fake_build)
    monkeypatch.setattr(drive_service.time, "monotonic", lambda: next(timestamps))
    monkeypatch.setattr(drive_service, "DRIVE_CLIENT_CACHE_TTL_SECONDS", 5.0)
    monkeypatch.setattr(drive_service, "DRIVE_CLIENT_CACHE_MAX_ENTRIES", 2)
    _reset_drive_caches()

    ctx = _ctx()
    client_a_1 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-a.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    client_a_2 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-a.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    client_b_1 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-b.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    client_c_1 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-c.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    client_a_3 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-a.json",
        oauth_token_path=None,
        ctx=ctx,
    )
    client_b_2 = drive_service._get_drive_client(
        auth_mode="service_account",
        service_account_path="sa-b.json",
        oauth_token_path=None,
        ctx=ctx,
    )

    assert client_a_1 is client_a_2
    assert client_a_3 is not client_a_1
    assert client_b_2 is not client_b_1
    assert client_c_1 is not client_b_1
    assert len(created) == 5
