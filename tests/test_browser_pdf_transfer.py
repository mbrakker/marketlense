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


def test_owned_wrapper_replacement_requires_a_pdf_and_preserves_wrapper_on_failure(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    _http_acquisition._SESSION_POOL._sessions.clear()
    destination_path = tmp_path / "wrapper.pdf"
    wrapper_bytes = b'<html><a href="https://example.com/real.pdf">PDF</a></html>'
    destination_path.write_bytes(wrapper_bytes)
    expected_signature = pdf_transfer.artifact_signature(destination_path)

    class FakeSession:
        def mount(self, *_args, **_kwargs) -> None:
            return None

        def request(self, _method: str, url: str, **_kwargs):
            return _FakePdfResponse(url=url, content=b"not a PDF")

    external_boundary_mocks_only.setattr(
        _http_acquisition.requests,
        "Session",
        FakeSession,
    )

    with pytest.raises(AppError) as error:
        pdf_transfer.download_pdf_from_url(
            pdf_url="https://example.com/real.pdf",
            destination_path=destination_path,
            timeout_seconds=5.0,
            ctx=run_context,
            normalized_url="https://example.com/wrapper",
            replace_existing=True,
            expected_existing_signature=expected_signature,
            require_pdf_signature=True,
        )

    assert error.value.code == "browser_download_invalid_pdf"
    assert destination_path.read_bytes() == wrapper_bytes
    assert not destination_path.with_suffix(".pdf.part").exists()
    _http_acquisition._SESSION_POOL._sessions.clear()


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
