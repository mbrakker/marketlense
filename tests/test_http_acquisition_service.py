from __future__ import annotations

import json
import logging
from pathlib import Path

import pytest

from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.services import _http_acquisition as service
from src.utils.errors import AppError


class _FakeResponse:
    def __init__(
        self,
        *,
        url: str,
        text: str = "",
        content: bytes | None = None,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.url = url
        self.status_code = status_code
        self.headers = headers or {"Content-Type": "text/html; charset=utf-8"}
        self._text = text
        self._content = content if content is not None else text.encode("utf-8")

    @property
    def text(self) -> str:
        return self._text

    def iter_content(self, chunk_size: int = 65536):
        for start in range(0, len(self._content), chunk_size):
            yield self._content[start : start + chunk_size]

    def close(self) -> None:
        return None


def _request(
    *,
    url: str,
    policy: HttpAcquisitionResponsePolicy | None = None,
    method: str = "GET",
    error_code: str = "http_acquisition_test_failed",
    error_message: str = "HTTP acquisition test request failed",
) -> HttpAcquisitionRequest:
    return HttpAcquisitionRequest(
        schema_version="1.0",
        purpose="http_acquisition_test",
        method=method,
        url=url,
        headers={"Accept": "text/html"},
        timeout_seconds=5.0,
        response_policy=policy
        or HttpAcquisitionResponsePolicy(
            schema_version="1.0",
            require_success_status=True,
            capture_text=True,
            capture_content_type_markers=("html", "xml"),
            max_body_bytes=1024,
        ),
        error_code=error_code,
        error_message=error_message,
    )


def _events(caplog) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != service.logger.name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def test_execute_http_acquisition_reuses_pooled_session_for_same_host(
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
) -> None:
    service._SESSION_POOL._sessions.clear()
    session_instances: list[object] = []

    class FakeSession:
        def __init__(self) -> None:
            session_instances.append(self)

        def mount(self, *_args, **_kwargs) -> None:
            return None

        def request(self, method: str, url: str, **kwargs):
            return _FakeResponse(
                url=url,
                text=f"{method}:{kwargs.get('headers', {}).get('Accept', '')}",
                headers={"Content-Type": "text/html; charset=utf-8"},
            )

    external_boundary_mocks_only.setattr(service.requests, "Session", FakeSession)
    caplog.set_level(logging.INFO, logger=service.logger.name)

    first = service.execute_http_acquisition(
        request=_request(url="https://example.com/a"),
        ctx=run_context,
    )
    second = service.execute_http_acquisition(
        request=_request(url="https://example.com/b"),
        ctx=run_context,
    )

    assert len(session_instances) == 1
    assert first.used_pooled_session is True
    assert second.used_pooled_session is True
    assert first.pool_key == "https://example.com"
    assert second.pool_key == "https://example.com"
    assert first.text_body == "GET:text/html"
    assert second.text_body == "GET:text/html"
    assert_logs_have_required_fields(_events(caplog))


def test_execute_http_acquisition_uses_patched_module_level_get(
    run_context,
    external_boundary_mocks_only,
) -> None:
    service._SESSION_POOL._sessions.clear()
    requested: list[str] = []

    def fake_get(url: str, **_kwargs):
        requested.append(url)
        return _FakeResponse(
            url=f"{url}/final",
            text="patched",
            headers={"content-type": "text/html; charset=utf-8"},
        )

    external_boundary_mocks_only.setattr(service.requests, "get", fake_get)

    response = service.execute_http_acquisition(
        request=_request(url="https://example.com/patched"),
        ctx=run_context,
        requests_module=service.requests,
    )

    assert requested == ["https://example.com/patched"]
    assert response.used_pooled_session is False
    assert response.final_url == "https://example.com/patched/final"
    assert response.text_body == "patched"


def test_execute_http_acquisition_streams_response_to_path(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    service._SESSION_POOL._sessions.clear()
    payload = b"%PDF-1.7 streamed bytes"

    class FakeSession:
        def mount(self, *_args, **_kwargs) -> None:
            return None

        def request(self, _method: str, url: str, **_kwargs):
            return _FakeResponse(
                url=url,
                content=payload,
                headers={"Content-Type": "application/pdf"},
            )

    external_boundary_mocks_only.setattr(service.requests, "Session", FakeSession)
    destination_path = tmp_path / "streamed.pdf"

    response = service.execute_http_acquisition(
        request=_request(
            url="https://example.com/report.pdf",
            policy=HttpAcquisitionResponsePolicy(
                schema_version="1.0",
                require_success_status=True,
                capture_text=False,
                stream_to_path=str(destination_path),
                max_stream_bytes=1024,
            ),
        ),
        ctx=run_context,
    )

    assert destination_path.read_bytes() == payload
    assert response.streamed_to_path == str(destination_path)
    assert response.streamed_bytes == len(payload)


def test_execute_http_acquisition_fails_when_stream_exceeds_cap(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    service._SESSION_POOL._sessions.clear()

    class FakeSession:
        def mount(self, *_args, **_kwargs) -> None:
            return None

        def request(self, _method: str, url: str, **_kwargs):
            return _FakeResponse(
                url=url,
                content=b"1234567890",
                headers={"Content-Type": "application/pdf"},
            )

    external_boundary_mocks_only.setattr(service.requests, "Session", FakeSession)
    destination_path = tmp_path / "too-large.pdf"

    with pytest.raises(AppError) as err:
        service.execute_http_acquisition(
            request=_request(
                url="https://example.com/report.pdf",
                policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=True,
                    capture_text=False,
                    stream_to_path=str(destination_path),
                    max_stream_bytes=4,
                ),
                error_code="http_acquisition_stream_failed",
                error_message="Streaming failed",
            ),
            ctx=run_context,
        )

    assert_app_error(
        err.value,
        code="http_acquisition_stream_failed",
        retryable=True,
    )
    assert destination_path.exists() is False
