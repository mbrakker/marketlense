# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

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

    def _fake_build(*_args, **kwargs):
        assert kwargs["cache_discovery"] is False
        assert kwargs["static_discovery"] is True
        return fake_drive

    monkeypatch.setattr(drive_service, "build", _fake_build)
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

__all__ = [
    "test_list_pdfs_includes_nested_subfolders",
    "test_list_pdfs_subfolder_discovery_error_is_retryable_app_error",
    "test_list_files_in_folder_filters_by_prefix",
    "test_upload_bytes_creates_drive_file",
    "test_ensure_folder_reuses_existing_child_folder",
    "test_ensure_folder_creates_missing_child_folder",
    "test_upload_local_file_reads_and_uploads_artifact",
    "test_upload_local_file_requires_existing_file",
    "test_preflight_drive_write_access_validates_folder_write_readiness",
    "test_preflight_drive_write_access_refreshes_expired_oauth_token",
    "test_preflight_drive_write_access_reports_oauth_refresh_failure",
    "test_preflight_drive_write_access_rejects_insufficient_oauth_scope",
    "test_preflight_drive_write_access_reports_missing_oauth_token",
    "test_preflight_drive_write_access_rejects_folder_without_write_capability",
    "test_preflight_drive_write_access_rejects_failed_write_probe",
    "test_list_pdfs_uses_oauth_user_credentials",
    "test_authorize_oauth_user_writes_token",
    "test_list_pdfs_wraps_missing_service_account_path_as_typed_error",
    "test_download_pdf_to_path_removes_partial_file_on_failure",
    "test_list_pdfs_streams_pages_incrementally",
]
