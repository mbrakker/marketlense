from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest

from src.contracts.mailbox_acquisition import MailboxAcquisitionSettings
from src.contracts.run_context import RunContext
from src.services import mailbox_acquisition_service
from src.utils.errors import AppError


class _Credentials:
    expired = True
    refresh_token = "refresh-token"

    def __init__(self, *, refresh_error: Exception | None = None) -> None:
        self.refresh_error = refresh_error
        self.refresh_calls = 0

    def refresh(self, _request: Callable[..., object]) -> None:
        self.refresh_calls += 1
        _request("https://oauth.example.test/token", method="POST")
        if self.refresh_error is not None:
            raise self.refresh_error


class _ProfileRequest:
    def __init__(self, *, fail: bool) -> None:
        self.fail = fail
        self.calls = 0

    def execute(self, *, num_retries: int = 0) -> dict[str, object]:
        assert num_retries == 0
        self.calls += 1
        if self.fail:
            raise RuntimeError("profile request failed")
        return {"emailAddress": "redacted@example.test"}


class _Users:
    def __init__(self, request: _ProfileRequest) -> None:
        self.request = request

    def getProfile(self, *, userId: str) -> _ProfileRequest:
        assert userId == "me"
        return self.request


class _GmailClient:
    def __init__(self, request: _ProfileRequest) -> None:
        self._users = _Users(request)

    def users(self) -> _Users:
        return self._users


class _AuthRequestTransport:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def __call__(self, url: str, **kwargs: object) -> object:
        self.calls.append({"url": url, **kwargs})
        return object()


@pytest.mark.parametrize(("refresh_fails", "expected_calls"), [(False, 2), (True, 1)])
def test_gmail_preflight_counts_token_refresh_and_profile_requests(
    tmp_path: Path,
    external_boundary_mocks_only,
    refresh_fails: bool,
    expected_calls: int,
) -> None:
    token_file = tmp_path / "gmail-token.json"
    token_file.write_text("{}", encoding="utf-8")
    credentials = _Credentials(
        refresh_error=RuntimeError("refresh failed") if refresh_fails else None
    )
    auth_transport = _AuthRequestTransport()
    profile_request = _ProfileRequest(fail=False)
    authorized_http_options: list[dict[str, object]] = []
    external_boundary_mocks_only.setattr(
        mailbox_acquisition_service.Credentials,
        "from_authorized_user_file",
        staticmethod(lambda *_args, **_kwargs: credentials),
    )
    external_boundary_mocks_only.setattr(
        mailbox_acquisition_service, "GoogleAuthRequest", lambda: auth_transport
    )
    external_boundary_mocks_only.setattr(
        mailbox_acquisition_service,
        "AuthorizedHttp",
        lambda *_args, **kwargs: authorized_http_options.append(kwargs) or object(),
    )
    external_boundary_mocks_only.setattr(
        mailbox_acquisition_service,
        "build",
        lambda *_args, **_kwargs: _GmailClient(profile_request),
    )
    settings = MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="gmail",
        output_dir=str(tmp_path),
        search_window_minutes=60,
        max_results=1,
        poll_timeout_seconds=1.0,
        poll_interval_seconds=0.1,
        gmail_oauth_client_path="",
        gmail_oauth_token_path=str(token_file),
        gmail_user_id="me",
        imap_host="",
        imap_port=993,
        imap_user="",
        imap_password="",
        imap_mailbox="INBOX",
    )
    ctx = RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")

    if refresh_fails:
        with pytest.raises(AppError) as exc_info:
            mailbox_acquisition_service.preflight_mailbox_access(settings, ctx)
        assert exc_info.value.context["provider_calls"] == expected_calls
    else:
        response = mailbox_acquisition_service.preflight_mailbox_access(settings, ctx)
        assert response.provider_calls == expected_calls
        assert profile_request.calls == 1
    assert credentials.refresh_calls == 1
    assert len(auth_transport.calls) == 1
    assert auth_transport.calls[0]["timeout"] == 5.0
    assert len(authorized_http_options) == (0 if refresh_fails else 1)
    if not refresh_fails:
        assert authorized_http_options[0]["max_refresh_attempts"] == 0
