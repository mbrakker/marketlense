from __future__ import annotations

import json
import logging
from typing import Any

import requests

from src.contracts.wordpress import (
    WordPressMediaUploadRequest,
    WordPressPostCreateRequest,
    WordPressPostLookupBatchRequest,
    WordPressPostUpdateRequest,
)
from src.services import wordpress_service as svc
from tests.support.fakes import FakeHttpResponse
from tests.test_wordpress_service import _ctx


def test_upload_media_server_error_logs_response_diagnostics(
    wordpress_http, caplog, assert_app_error, assert_logs_have_required_fields
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.wordpress_service")
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/media",
        status_code=503,
        payload={"code": "server_error", "message": "temporary outage"},
        headers={
            "Content-Type": "application/json",
            "Retry-After": "120",
            "Set-Cookie": "secret=1",
        },
        reason="Service Unavailable",
    )
    request = WordPressMediaUploadRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        filename="x.png",
        mime_type="image/png",
        data=b"abc",
    )
    try:
        svc.upload_media(request, _ctx())
    except Exception as err:
        assert_app_error(err, code="wp_media_server_error", retryable=True)
        assert err.context["status_code"] == 503
        assert err.context["reason"] == "Service Unavailable"
        assert err.context["response_headers"]["Content-Type"] == "application/json"
        assert err.context["response_headers"]["Retry-After"] == "120"
        assert "Set-Cookie" not in err.context["response_headers"]
        assert "temporary outage" in err.context["response_body_excerpt"]
    else:
        raise AssertionError("expected AppError")
    events = [
        json.loads(record.message)
        for record in caplog.records
        if "wp_media_upload_http_error" in record.message
    ]
    assert len(events) == 1
    assert events[0]["fields"]["status_code"] == 503
    assert events[0]["fields"]["reason"] == "Service Unavailable"
    logged_body = events[0]["fields"]["response_body_excerpt"]
    assert (
        logged_body["redaction"] == "***REDACTED***"
        and logged_body["sha256"]
        and logged_body["character_count"] > 0
    )
    assert "Set-Cookie" not in events[0]["fields"]["response_headers"]
    assert_logs_have_required_fields(events)


def test_upload_media_rate_limit_is_retryable(wordpress_http, assert_app_error) -> None:
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/media",
        status_code=429,
        payload={"code": "too_many_requests", "message": "slow down"},
        headers={"Retry-After": "60"},
        reason="Too Many Requests",
    )
    request = WordPressMediaUploadRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        filename="x.png",
        mime_type="image/png",
        data=b"abc",
    )
    try:
        svc.upload_media(request, _ctx())
    except Exception as err:
        assert_app_error(err, code="wp_media_rate_limited", retryable=True)
        assert (
            err.context["status_code"] == 429
            and err.context["response_headers"]["Retry-After"] == "60"
        )
    else:
        raise AssertionError("expected AppError")


def test_update_post_categories_server_error(wordpress_http, assert_app_error) -> None:
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/posts/12",
        status_code=503,
        payload={"message": "retry"},
    )
    request = WordPressPostUpdateRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        post_id=12,
        categories=[1],
    )
    try:
        svc.update_post_categories(request, _ctx())
    except Exception as err:
        assert_app_error(err, code="wp_post_update_server_error", retryable=True)
    else:
        raise AssertionError("expected AppError")


def test_batch_lookup_reuses_pooled_session(
    external_boundary_mocks_only, assert_logs_have_required_fields, caplog
) -> None:
    class _FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def mount(self, _prefix: str, _adapter: Any) -> None:
            return

        def request(self, method: str, url: str, **kwargs: Any) -> FakeHttpResponse:
            self.calls.append({"method": method, "url": url, **kwargs})
            file_id = str((kwargs.get("params") or {}).get("ml_file_id") or "")
            payload = (
                [
                    {
                        "id": 11,
                        "link": "https://pooled.test/p/11",
                        "content": {"rendered": "Public report content"},
                        "meta": {"ml_file_id": "file-1"},
                    }
                ]
                if file_id == "file-1"
                else []
            )
            return FakeHttpResponse.from_payload(status_code=200, payload=payload)

    created_sessions: list[_FakeSession] = []

    def _session_factory() -> _FakeSession:
        session = _FakeSession()
        created_sessions.append(session)
        return session

    caplog.set_level(logging.INFO, logger="market_lense.wordpress_service")
    external_boundary_mocks_only.setattr(svc.requests, "Session", _session_factory)
    response = svc.find_posts_by_file_id_batch(
        WordPressPostLookupBatchRequest(
            schema_version="1.0",
            base_url="https://pooled.test",
            auth_header="Bearer token",
            file_ids=["file-1", "file-2"],
            post_type="posts",
        ),
        _ctx(),
    )
    assert [item.found for item in response.items] == [True, False]
    assert len(created_sessions) == 1 and len(created_sessions[0].calls) == 2
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.wordpress_service"
    ]
    assert_logs_have_required_fields(events)
    lookup_complete = [
        event for event in events if event.get("event") == "wp_post_lookup_complete"
    ]
    assert len(lookup_complete) == 2
    assert (
        lookup_complete[0]["fields"]["used_pooled_session"] is True
        and lookup_complete[0]["fields"]["pool_reused"] is False
    )
    assert (
        lookup_complete[1]["fields"]["used_pooled_session"] is True
        and lookup_complete[1]["fields"]["pool_reused"] is True
    )


def test_create_post_session_request_exception_adapts_to_app_error(
    external_boundary_mocks_only, assert_app_error
) -> None:
    class _FakeSession:
        def mount(self, _prefix: str, _adapter: Any) -> None:
            return

        def request(self, method: str, url: str, **kwargs: Any) -> FakeHttpResponse:
            raise requests.RequestException(
                f"boom {method} {url} {kwargs.get('timeout')}"
            )

    external_boundary_mocks_only.setattr(
        svc.requests, "Session", lambda: _FakeSession()
    )
    request = WordPressPostCreateRequest(
        schema_version="1.0",
        base_url="https://create-error.test",
        auth_header="Bearer token",
        title="T",
        content_html="<p>x</p>",
        status="publish",
    )
    try:
        svc.create_post(request, _ctx())
    except Exception as err:
        assert_app_error(err, code="wp_post_create_failed", retryable=True)
        assert (
            err.context["method"] == "POST"
            and err.context["url"] == "https://create-error.test/wp-json/wp/v2/posts"
            and err.context["pool_key"] == "https://create-error.test"
        )
    else:
        raise AssertionError("expected AppError")
