from __future__ import annotations

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


class _FailingDriveClient:
    def __init__(self, error: Exception) -> None:
        self._files = _FailingFiles(error)

    def files(self) -> _FailingFiles:
        return self._files


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
