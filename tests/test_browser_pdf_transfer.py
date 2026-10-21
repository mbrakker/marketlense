from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace

import pytest
import requests

from src.services import _http_acquisition
from src.services._browser_report_download._http import pdf_transfer
from src.utils.errors import AppError


class _FakePdfResponse:
    def __init__(self, *, url: str, content: bytes) -> None:
        self.url = url
        self.status_code = 200
        self.headers = {"Content-Type": "application/pdf"}
        self._content = content

    def iter_content(self, chunk_size: int = 65536):
        for start in range(0, len(self._content), chunk_size):
            yield self._content[start : start + chunk_size]

    def close(self) -> None:
        return None


def test_download_pdf_from_url_retries_without_browser_user_agent(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    _http_acquisition._SESSION_POOL._sessions.clear()
    seen_headers: list[dict[str, str]] = []
    payload = b"%PDF-1.7 fallback headers worked"

    class FakeSession:
        def mount(self, *_args, **_kwargs) -> None:
            return None

        def request(self, _method: str, url: str, **kwargs):
            headers = dict(kwargs.get("headers", {}))
            seen_headers.append(headers)
            if "User-Agent" in headers:
                raise requests.ReadTimeout("browser user agent stalled")
            return _FakePdfResponse(url=url, content=payload)

    external_boundary_mocks_only.setattr(
        _http_acquisition.requests,
        "Session",
        FakeSession,
    )
    destination_path = tmp_path / "report.pdf"
    caplog.set_level(logging.INFO, logger=pdf_transfer.logger.name)

    pdf_transfer.download_pdf_from_url(
        pdf_url="https://example.com/report.pdf",
        destination_path=destination_path,
        timeout_seconds=5.0,
        ctx=run_context,
        normalized_url="https://example.com/report.pdf",
    )

    assert destination_path.read_bytes() == payload
    assert len(seen_headers) == 2
    assert "User-Agent" in seen_headers[0]
    assert seen_headers[1] == {"Accept": seen_headers[0]["Accept"]}
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == pdf_transfer.logger.name
    ]
    assert any(
        event["event"] == "browser_report_download_pdf_fetch_header_fallback"
        for event in events
    )
    assert any(
        event["event"] == "browser_report_download_pdf_fetch_response"
        and event["fields"]["used_header_fallback"] is True
        for event in events
    )
    assert_logs_have_required_fields(events)
    _http_acquisition._SESSION_POOL._sessions.clear()


def test_download_pdf_from_url_does_not_replace_existing_destination(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    _http_acquisition._SESSION_POOL._sessions.clear()
    destination_path = tmp_path / "report.pdf"
    previous_bytes = b"%PDF-1.7 previous"
    destination_path.write_bytes(previous_bytes)

    class FakeSession:
        def mount(self, *_args, **_kwargs) -> None:
            return None

        def request(self, _method: str, url: str, **_kwargs):
            return _FakePdfResponse(
                url=url,
                content=b"%PDF-1.7 competing replacement",
            )

    external_boundary_mocks_only.setattr(
        _http_acquisition.requests,
        "Session",
        FakeSession,
    )

    with pytest.raises(AppError) as error:
        pdf_transfer.download_pdf_from_url(
            pdf_url="https://example.com/report.pdf",
            destination_path=destination_path,
            timeout_seconds=5.0,
            ctx=run_context,
            normalized_url="https://example.com/report.pdf",
        )

    assert error.value.code == "browser_download_pdf_commit_conflict"
    assert error.value.retryable is True
    assert destination_path.read_bytes() == previous_bytes
    assert not destination_path.with_suffix(".pdf.part").exists()
    _http_acquisition._SESSION_POOL._sessions.clear()


def test_http_wrapper_is_recovered_before_final_publication(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    _http_acquisition._SESSION_POOL._sessions.clear()
    destination_path = tmp_path / "wrapper.pdf"
    wrapper_url = "https://example.com/wrapper.pdf"
    embedded_url = "https://example.com/real.pdf"
    wrapper_bytes = b'<html><a href="https://example.com/real.pdf">PDF</a></html>'
    embedded_bytes = b"%PDF-1.7 embedded before publication"
    embedded_request_destination_states: list[bool] = []

    class FakeSession:
        def mount(self, *_args, **_kwargs) -> None:
            return None

        def request(self, _method: str, url: str, **_kwargs):
            if url == wrapper_url:
                return _FakePdfResponse(url=url, content=wrapper_bytes)
            assert url == embedded_url
            embedded_request_destination_states.append(destination_path.exists())
            return _FakePdfResponse(url=url, content=embedded_bytes)

    external_boundary_mocks_only.setattr(
        _http_acquisition.requests,
        "Session",
        FakeSession,
    )

    pdf_transfer.download_pdf_from_url(
        pdf_url=wrapper_url,
        destination_path=destination_path,
        timeout_seconds=5.0,
        ctx=run_context,
        normalized_url=wrapper_url,
    )

    assert embedded_request_destination_states == [False]
    assert destination_path.read_bytes() == embedded_bytes
    assert list(tmp_path.glob("*.part")) == []
    _http_acquisition._SESSION_POOL._sessions.clear()


def test_http_wrapper_recovery_rejects_cycles_and_cleans_all_stages(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    _http_acquisition._SESSION_POOL._sessions.clear()
    destination_path = tmp_path / "cycle.pdf"
    first_url = "https://example.com/first.pdf"
    second_url = "https://example.com/second.pdf"
    calls: list[str] = []
    wrappers = {
        first_url: b'<html><a href="https://example.com/second.pdf">PDF</a></html>',
        second_url: b'<html><a href="https://example.com/first.pdf">PDF</a></html>',
    }

    class FakeSession:
        def mount(self, *_args, **_kwargs) -> None:
            return None

        def request(self, _method: str, url: str, **_kwargs):
            calls.append(url)
            return _FakePdfResponse(url=url, content=wrappers[url])

    external_boundary_mocks_only.setattr(
        _http_acquisition.requests,
        "Session",
        FakeSession,
    )

    with pytest.raises(AppError) as error:
        pdf_transfer.download_pdf_from_url(
            pdf_url=first_url,
            destination_path=destination_path,
            timeout_seconds=5.0,
            ctx=run_context,
            normalized_url=first_url,
        )

    assert error.value.code == "browser_download_invalid_pdf"
    assert calls == [first_url, second_url]
    assert not destination_path.exists()
    assert list(tmp_path.glob("*.part")) == []
    _http_acquisition._SESSION_POOL._sessions.clear()


def test_wrapper_recovery_uses_a_separate_destination_and_preserves_wrapper(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    destination_path = tmp_path / "wrapper.pdf"
    wrapper_bytes = b'<html><a href="https://example.com/real.pdf">PDF</a></html>'
    destination_path.write_bytes(wrapper_bytes)
    observed: dict[str, object] = {}

    def fake_download(**kwargs) -> None:
        recovery_path = Path(kwargs["destination_path"])
        observed.update(kwargs)
        recovery_path.write_bytes(b"%PDF-1.7 recovered")

    external_boundary_mocks_only.setattr(
        pdf_transfer,
        "download_pdf_from_url",
        fake_download,
    )

    recovered_path = pdf_transfer.ensure_downloaded_pdf(
        downloaded_path=destination_path,
        ctx=run_context,
        normalized_url="https://example.com/wrapper",
        document_url="https://example.com/wrapper",
        timeout_seconds=5.0,
    )

    assert recovered_path is not None
    assert recovered_path != destination_path
    assert recovered_path.read_bytes() == b"%PDF-1.7 recovered"
    assert destination_path.read_bytes() == wrapper_bytes
    assert observed["require_pdf_signature"] is True
    assert "replace_existing" not in observed
    assert "expected_existing_signature" not in observed


def test_direct_pdf_failure_does_not_delete_unowned_final_bytes(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    request = SimpleNamespace(
        url="https://example.com/report.pdf",
        settings=SimpleNamespace(timeout_seconds=5.0),
    )
    final_path = tmp_path / "report.pdf"
    final_bytes = b"%PDF-1.7 bytes written before an ambiguous failure"

    def failing_download(**kwargs) -> None:
        Path(kwargs["destination_path"]).write_bytes(final_bytes)
        raise AppError(
            code="browser_download_pdf_fetch_failed",
            message="ambiguous transfer failure",
            retryable=True,
        )

    external_boundary_mocks_only.setattr(
        pdf_transfer,
        "download_pdf_from_url",
        failing_download,
    )

    result = pdf_transfer.try_direct_pdf_download(
        request=request,
        ctx=run_context,
        normalized_url="https://example.com/report.pdf",
        download_dir=tmp_path,
    )

    assert result is None
    assert final_path.read_bytes() == final_bytes


def test_direct_pdf_validation_failure_preserves_committed_final_bytes(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    request = SimpleNamespace(
        url="https://example.com/report.pdf",
        settings=SimpleNamespace(timeout_seconds=5.0),
    )
    final_path = tmp_path / "report.pdf"
    final_bytes = b"%PDF-1.7 committed before validation failure"

    def fake_download(**kwargs) -> None:
        Path(kwargs["destination_path"]).write_bytes(final_bytes)

    def fail_validation(**_kwargs) -> None:
        raise AppError(
            code="browser_download_invalid_pdf_metadata",
            message="simulated downstream validation failure",
            retryable=True,
        )

    external_boundary_mocks_only.setattr(
        pdf_transfer,
        "download_pdf_from_url",
        fake_download,
    )
    external_boundary_mocks_only.setattr(
        pdf_transfer,
        "validate_downloaded_pdf_artifact",
        fail_validation,
    )

    result = pdf_transfer.try_direct_pdf_download(
        request=request,
        ctx=run_context,
        normalized_url="https://example.com/report.pdf",
        download_dir=tmp_path,
    )

    assert result is None
    assert final_path.read_bytes() == final_bytes
