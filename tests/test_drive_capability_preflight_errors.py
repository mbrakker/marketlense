from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httplib2
import pytest
from googleapiclient.errors import HttpError

from src.contracts.drive import DriveFolderCapabilityPreflightRequest
from src.contracts.run_context import RunContext
from src.services import drive_service
from src.utils.errors import AppError


class _FailingListCall:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def execute(self, *, num_retries: int = 0) -> dict[str, object]:
        assert num_retries == 0
        raise self.error


class _FailingFiles:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def list(self, **_kwargs: object) -> _FailingListCall:
        return _FailingListCall(self.error)

    def get(self, **_kwargs: object) -> _FailingListCall:
        return _FailingListCall(self.error)


class _FailingDriveClient:
    def __init__(self, error: Exception) -> None:
        self._files = _FailingFiles(error)

    def files(self) -> _FailingFiles:
        return self._files


class _MetadataCall:
    def execute(self, *, num_retries: int = 0) -> dict[str, object]:
        assert num_retries == 0
        return {
            "id": "configured-folder",
            "mimeType": "application/vnd.google-apps.folder",
            "capabilities": {"canAddChildren": True},
        }


class _MetadataFiles:
    def __init__(self) -> None:
        self.get_kwargs: dict[str, object] | None = None

    def get(self, **kwargs: object) -> _MetadataCall:
        self.get_kwargs = kwargs
        return _MetadataCall()

    def list(self, **_kwargs: object) -> _MetadataCall:
        raise AssertionError(
            "preflight should inspect folder metadata, not list children"
        )


class _MetadataDriveClient:
    def __init__(self) -> None:
        self._files = _MetadataFiles()

    def files(self) -> _MetadataFiles:
        return self._files


def _write_authorized_user_token(
    token_path: Path, *, granted_scopes: list[str] | None
) -> None:
    payload: dict[str, object] = {
        "token": "test-access-token",
        "refresh_token": "test-refresh-token",
        "client_id": "test-client-id",
        "client_secret": "test-client-secret",
        "scopes": ["https://www.googleapis.com/auth/drive"],
        "expiry": (datetime.now(timezone.utc) + timedelta(hours=1))
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
    }
    if granted_scopes is not None:
        payload["granted_scopes"] = granted_scopes
    token_path.write_text(json.dumps(payload), encoding="utf-8")


@pytest.mark.parametrize(
    ("status_code", "expected_retryable"),
    [(400, False), (404, False), (429, True), (500, True)],
)
def test_drive_folder_preflight_classifies_http_errors_by_recoverability(
    tmp_path: Path,
    external_boundary_mocks_only,
    status_code: int,
    expected_retryable: bool,
) -> None:
    credential_file = tmp_path / "service-account.json"
    credential_file.write_text("{}", encoding="utf-8")
    error = HttpError(
        httplib2.Response({"status": str(status_code)}),
        b"provider error payload",
    )
    fake_drive = _FailingDriveClient(error)
    external_boundary_mocks_only.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda *_args, **_kwargs: object()),
    )
    external_boundary_mocks_only.setattr(
        drive_service, "build", lambda *_args, **_kwargs: fake_drive
    )

    request = DriveFolderCapabilityPreflightRequest(
        schema_version="1.0",
        folder_id="configured-folder",
        service_account_path=str(credential_file),
        auth_mode="service_account",
        timeout_seconds=5.0,
    )
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    with pytest.raises(AppError) as exc_info:
        drive_service.preflight_drive_folder_access(request, ctx)

    assert exc_info.value.retryable is expected_retryable
    assert exc_info.value.context["status_code"] == status_code
    assert exc_info.value.code == "drive_folder_unavailable"


def test_drive_folder_preflight_reads_folder_and_child_write_capability(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    credential_file = tmp_path / "service-account.json"
    credential_file.write_text("{}", encoding="utf-8")
    fake_drive = _MetadataDriveClient()
    external_boundary_mocks_only.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda *_args, **_kwargs: object()),
    )
    external_boundary_mocks_only.setattr(
        drive_service, "build", lambda *_args, **_kwargs: fake_drive
    )
    request = DriveFolderCapabilityPreflightRequest(
        schema_version="1.0",
        folder_id="configured-folder",
        service_account_path=str(credential_file),
        auth_mode="service_account",
        timeout_seconds=5.0,
    )
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    response = drive_service.preflight_drive_folder_access(request, ctx)

    assert fake_drive._files.get_kwargs == {
        "fileId": "configured-folder",
        "fields": "id,mimeType,capabilities(canAddChildren)",
        "supportsAllDrives": True,
    }
    assert response.accessible is True
    assert response.is_folder is True
    assert response.can_add_children is True


def test_drive_folder_preflight_rejects_missing_write_scope_without_provider_call(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    class CredentialsWithoutWriteScope:
        def has_scopes(self, _scopes: list[str]) -> bool:
            return False

    credential_file = tmp_path / "service-account.json"
    credential_file.write_text("{}", encoding="utf-8")
    external_boundary_mocks_only.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda *_args, **_kwargs: CredentialsWithoutWriteScope()),
    )
    external_boundary_mocks_only.setattr(
        drive_service,
        "build",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("missing scope must fail before the provider call")
        ),
    )
    request = DriveFolderCapabilityPreflightRequest(
        schema_version="1.0",
        folder_id="configured-folder",
        service_account_path=str(credential_file),
        auth_mode="service_account",
        require_write_scope=True,
        timeout_seconds=5.0,
    )
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    with pytest.raises(AppError) as exc_info:
        drive_service.preflight_drive_folder_access(request, ctx)

    assert exc_info.value.code == "drive_preflight_scope_insufficient"
    assert exc_info.value.retryable is False


def test_drive_folder_preflight_does_not_refresh_after_unauthorized_response(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    class Credentials:
        def __init__(self) -> None:
            self.refresh_count = 0

        def has_scopes(self, _scopes: list[str]) -> bool:
            return True

        def before_request(
            self,
            _request: object,
            _method: str,
            _url: str,
            headers: dict[str, str],
        ) -> None:
            headers["Authorization"] = "Bearer test-token"

        def refresh(self, _request: object) -> None:
            self.refresh_count += 1

    credentials = Credentials()
    request_count = 0
    credential_file = tmp_path / "service-account.json"
    credential_file.write_text("{}", encoding="utf-8")
    real_build = drive_service.build

    def build_with_unauthorized_response(*args: object, **kwargs: object):
        authorized_http = kwargs["http"]

        def request_unauthorized(*_args: object, **_kwargs: object):
            nonlocal request_count
            request_count += 1
            return httplib2.Response({"status": "401"}), b"unauthorized"

        authorized_http.http.request = request_unauthorized
        return real_build(*args, **kwargs)

    external_boundary_mocks_only.setattr(
        drive_service.Credentials,
        "from_service_account_file",
        staticmethod(lambda *_args, **_kwargs: credentials),
    )
    external_boundary_mocks_only.setattr(
        drive_service, "build", build_with_unauthorized_response
    )
    request = DriveFolderCapabilityPreflightRequest(
        schema_version="1.0",
        folder_id="configured-folder",
        service_account_path=str(credential_file),
        auth_mode="service_account",
        timeout_seconds=5.0,
    )
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    with pytest.raises(AppError) as exc_info:
        drive_service.preflight_drive_folder_access(request, ctx)

    assert exc_info.value.context["provider_calls"] == 1
    assert request_count == 1
    assert credentials.refresh_count == 0


@pytest.mark.parametrize(
    ("granted_scopes", "expected_code"),
    [
        (["https://www.googleapis.com/auth/drive"], None),
        (
            ["https://www.googleapis.com/auth/drive.metadata.readonly"],
            "drive_preflight_scope_insufficient",
        ),
        (None, "drive_preflight_scope_unverified"),
    ],
)
def test_drive_folder_preflight_uses_actual_oauth_grant_scopes(
    tmp_path: Path,
    external_boundary_mocks_only,
    granted_scopes: list[str] | None,
    expected_code: str | None,
) -> None:
    token_path = tmp_path / "authorized-user.json"
    _write_authorized_user_token(token_path, granted_scopes=granted_scopes)
    fake_drive = _MetadataDriveClient()
    if expected_code is None:
        external_boundary_mocks_only.setattr(
            drive_service, "build", lambda *_args, **_kwargs: fake_drive
        )
    else:
        external_boundary_mocks_only.setattr(
            drive_service,
            "build",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                AssertionError("unverified write scope must fail before provider call")
            ),
        )

    request = DriveFolderCapabilityPreflightRequest(
        schema_version="1.0",
        folder_id="configured-folder",
        service_account_path="",
        auth_mode="oauth_user",
        oauth_token_path=str(token_path),
        require_write_scope=True,
        timeout_seconds=5.0,
    )
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    if expected_code is None:
        response = drive_service.preflight_drive_folder_access(request, ctx)
        assert response.accessible is True
        assert response.can_add_children is True
    else:
        with pytest.raises(AppError) as exc_info:
            drive_service.preflight_drive_folder_access(request, ctx)
        assert exc_info.value.code == expected_code
        assert exc_info.value.context["provider_calls"] == 0
