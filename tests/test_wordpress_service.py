from __future__ import annotations

import json
import logging
from typing import Any
import warnings

import requests
import urllib3  # type: ignore[import-untyped]

from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressMediaUploadRequest,
    WordPressPostLookupBatchRequest,
    WordPressPostCreateRequest,
    WordPressPostLookupRequest,
    WordPressReportCardUpdateRequest,
    WordPressPostUpdateRequest,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyTerm,
)
from src.services import wordpress_service as svc
from tests.support.fakes import FakeHttpResponse, RecordedHttpRequest


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_create_post_success(wordpress_http) -> None:
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/posts",
        status_code=201,
        payload={"id": 10, "link": "https://site/p/10", "status": "publish"},
    )
    request = WordPressPostCreateRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        title="T",
        content_html="<p>x</p>",
        status="publish",
        slug="slug",
        featured_media=2,
        categories=[1, 2],
        tags=[3],
        taxonomy_terms={"ml_publisher": [4]},
    )

    response = svc.create_post(request, _ctx())

    call = wordpress_http.calls_for("POST", "https://site/wp-json/wp/v2/posts")[0]
    assert response.post_id == 10
    assert response.link == "https://site/p/10"
    assert call.json_data["slug"] == "slug"
    assert call.json_data["categories"] == [1, 2]
    assert call.json_data["tags"] == [3]
    assert call.json_data["ml_publisher"] == [4]
    assert call.verify is True


def test_update_report_card_sends_only_card_payload(wordpress_http) -> None:
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/ml_report/12",
        status_code=200,
        payload={"id": 12, "link": "https://site/reports/report/", "status": "publish"},
    )
    request = WordPressReportCardUpdateRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        post_id=12,
        featured_media=303,
        meta={"ml_card_schema_version": "1.0"},
        post_type="ml_report",
    )

    response = svc.update_report_card(request, _ctx())

    call = wordpress_http.calls_for(
        "POST", "https://site/wp-json/wp/v2/ml_report/12"
    )[0]
    assert response.post_id == 12
    assert response.link == "https://site/reports/report/"
    assert call.json_data == {
        "featured_media": 303,
        "meta": {"ml_card_schema_version": "1.0"},
    }


def test_create_post_custom_post_type_endpoint(wordpress_http) -> None:
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://site/r/10", "status": "publish"},
    )
    request = WordPressPostCreateRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        title="T",
        content_html="<p>x</p>",
        status="publish",
        post_type="ml_report",
    )

    response = svc.create_post(request, _ctx())

    call = wordpress_http.calls_for("POST", "https://site/wp-json/wp/v2/ml_report")[0]
    assert response.post_id == 10
    assert call.verify is True


def test_create_post_falls_back_to_query_rest_route_when_pretty_rest_returns_html(
    wordpress_http,
) -> None:
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/ml_signal",
        status_code=200,
        text="<!DOCTYPE html><html><body>Home</body></html>",
        headers={"content-type": "text/html; charset=UTF-8"},
    )
    wordpress_http.add_json(
        "POST",
        "https://site/index.php?rest_route=%2Fwp%2Fv2%2Fml_signal",
        status_code=201,
        payload={
            "id": 12,
            "link": "https://site/signals/signal-a/",
            "status": "publish",
        },
    )
    request = WordPressPostCreateRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        title="Signal A",
        content_html="<p>x</p>",
        status="publish",
        post_type="ml_signal",
        slug="signal-a",
    )

    response = svc.create_post(request, _ctx())

    fallback_call = wordpress_http.calls_for(
        "POST",
        "https://site/index.php?rest_route=%2Fwp%2Fv2%2Fml_signal",
    )[0]
    assert response.post_id == 12
    assert response.link == "https://site/signals/signal-a/"
    assert fallback_call.json_data["slug"] == "signal-a"


def test_create_post_client_error(wordpress_http, assert_app_error) -> None:
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/posts",
        status_code=400,
        payload={"message": "bad"},
    )
    request = WordPressPostCreateRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        title="T",
        content_html="<p>x</p>",
        status="publish",
    )

    try:
        svc.create_post(request, _ctx())
    except Exception as err:
        assert_app_error(err, code="wp_post_client_error", retryable=False)
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_find_post_by_file_id_found(wordpress_http) -> None:
    payload = [
        {
            "id": 11,
            "link": "https://site/p/11",
            "content": {"rendered": "Drive fileId: file-1"},
        },
    ]
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/posts",
        status_code=200,
        payload=payload,
    )
    request = WordPressPostLookupRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        file_id="file-1",
    )

    response = svc.find_post_by_file_id(request, _ctx())

    call = wordpress_http.calls_for("GET", "https://site/wp-json/wp/v2/posts")[0]
    assert response.found is True
    assert response.post_id == 11
    assert response.link == "https://site/p/11"
    assert call.allow_redirects is False


def test_find_post_by_file_id_ssl_verify_disabled(wordpress_http) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/posts",
        status_code=200,
        payload=[],
    )
    request = WordPressPostLookupRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        file_id="file-1",
        ssl_verify=False,
    )

    response = svc.find_post_by_file_id(request, _ctx())

    call = wordpress_http.calls_for("GET", "https://site/wp-json/wp/v2/posts")[0]
    assert response.found is False
    assert call.allow_redirects is False
    assert call.verify is False


def test_find_post_by_file_id_suppresses_insecure_request_warning_when_ssl_verify_disabled(
    wordpress_http,
) -> None:
    def _lookup(_call: RecordedHttpRequest) -> FakeHttpResponse:
        warnings.warn(
            "unverified https request",
            urllib3.exceptions.InsecureRequestWarning,
            stacklevel=1,
        )
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    wordpress_http.add("GET", "https://site/wp-json/wp/v2/posts", _lookup)
    request = WordPressPostLookupRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        file_id="file-1",
        ssl_verify=False,
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = svc.find_post_by_file_id(request, _ctx())

    assert response.found is False
    insecure = [
        warning
        for warning in caught
        if issubclass(warning.category, urllib3.exceptions.InsecureRequestWarning)
    ]
    assert insecure == []


def test_find_post_by_file_id_keeps_insecure_request_warning_when_ssl_verify_enabled(
    wordpress_http,
) -> None:
    def _lookup(_call: RecordedHttpRequest) -> FakeHttpResponse:
        warnings.warn(
            "unverified https request",
            urllib3.exceptions.InsecureRequestWarning,
            stacklevel=1,
        )
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    wordpress_http.add("GET", "https://site/wp-json/wp/v2/posts", _lookup)
    request = WordPressPostLookupRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        file_id="file-1",
    )

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response = svc.find_post_by_file_id(request, _ctx())

    assert response.found is False
    insecure = [
        warning
        for warning in caught
        if issubclass(warning.category, urllib3.exceptions.InsecureRequestWarning)
    ]
    assert len(insecure) == 1


def test_find_posts_by_file_id_batch_collects_found_and_missing(wordpress_http) -> None:
    def _lookup(call: RecordedHttpRequest) -> FakeHttpResponse:
        search = str(call.params.get("search") or "")
        if "file-1" in search:
            return FakeHttpResponse.from_payload(
                status_code=200,
                payload=[
                    {
                        "id": 11,
                        "link": "https://site/p/11",
                        "content": {"rendered": "Drive fileId: file-1"},
                    }
                ],
            )
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    wordpress_http.add("GET", "https://site/wp-json/wp/v2/posts", _lookup)
    request = WordPressPostLookupBatchRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        file_ids=["file-1", "file-2", "file-1"],
    )

    response = svc.find_posts_by_file_id_batch(request, _ctx())

    assert len(response.items) == 2
    assert response.items[0].file_id == "file-1"
    assert response.items[0].found is True
    assert response.items[0].post_id == 11
    assert response.items[1].file_id == "file-2"
    assert response.items[1].found is False
    assert response.items[1].post_id is None
    assert (
        len(wordpress_http.calls_for("GET", "https://site/wp-json/wp/v2/posts")) == 2
    )


def test_find_posts_by_file_id_batch_captures_item_errors(
    wordpress_http, assert_app_error
) -> None:
    def _lookup(call: RecordedHttpRequest) -> FakeHttpResponse:
        search = str(call.params.get("search") or "")
        if "file-bad" in search:
            return FakeHttpResponse.from_payload(
                status_code=503,
                payload={"message": "retry"},
            )
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    wordpress_http.add("GET", "https://site/wp-json/wp/v2/posts", _lookup)
    request = WordPressPostLookupBatchRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        file_ids=["file-bad", "file-ok"],
    )

    response = svc.find_posts_by_file_id_batch(request, _ctx())

    assert len(response.items) == 2
    assert response.items[0].file_id == "file-bad"
    assert response.items[0].found is False
    assert response.items[0].error_code == "wp_post_lookup_server_error"
    assert response.items[0].retryable is True
    assert response.items[1].file_id == "file-ok"
    assert response.items[1].found is False


def test_find_post_by_file_id_redirect_logs_response_diagnostics(
    wordpress_http,
    caplog,
    assert_app_error,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.wordpress_service")
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/posts",
        status_code=302,
        text="",
        headers={
            "Location": "wp-admin/install.php",
            "Set-Cookie": "secret=1",
        },
        reason="Found",
    )
    request = WordPressPostLookupRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        file_id="file-redirect",
    )

    try:
        svc.find_post_by_file_id(request, _ctx())
    except Exception as err:
        assert_app_error(err, code="wp_post_lookup_redirected", retryable=True)
        assert err.context["status_code"] == 302
        assert err.context["reason"] == "Found"
        assert err.context["response_headers"]["Location"] == "wp-admin/install.php"
        assert "Set-Cookie" not in err.context["response_headers"]
        assert err.context["response_body_excerpt"] == ""
    else:  # pragma: no cover
        raise AssertionError("expected AppError")

    call = wordpress_http.calls_for("GET", "https://site/wp-json/wp/v2/posts")[0]
    assert call.allow_redirects is False

    events = [
        json.loads(record.message)
        for record in caplog.records
        if "wp_post_lookup_http_redirect" in record.message
    ]
    assert len(events) == 1
    assert events[0]["fields"]["status_code"] == 302
    assert events[0]["fields"]["reason"] == "Found"
    assert events[0]["fields"]["response_headers"]["Location"] == "wp-admin/install.php"
    assert "Set-Cookie" not in events[0]["fields"]["response_headers"]
    assert_logs_have_required_fields(events)


def test_ensure_taxonomy_terms_creates_missing_terms(wordpress_http) -> None:
    def _lookup(call: RecordedHttpRequest) -> FakeHttpResponse:
        if call.params.get("slug") == "existing":
            return FakeHttpResponse.from_payload(status_code=200, payload=[{"id": 5}])
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _create(call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = call.json_data
        if payload.get("slug") == "new":
            return FakeHttpResponse.from_payload(status_code=201, payload={"id": 7})
        return FakeHttpResponse.from_payload(
            status_code=400, payload={"message": "bad"}
        )

    wordpress_http.add("GET", "https://site/wp-json/wp/v2/categories", _lookup)
    wordpress_http.add("POST", "https://site/wp-json/wp/v2/categories", _create)
    request = WordPressTaxonomyEnsureRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        taxonomy_rest_base="categories",
        terms=[
            WordPressTaxonomyTerm(
                schema_version="1.0", slug="existing", name="Existing"
            ),
            WordPressTaxonomyTerm(schema_version="1.0", slug="new", name="New"),
        ],
    )

    response = svc.ensure_taxonomy_terms(request, _ctx())

    assert response.slug_to_id == {"existing": 5, "new": 7}
    assert (
        len(wordpress_http.calls_for("GET", "https://site/wp-json/wp/v2/categories"))
        == 2
    )
    assert (
        len(wordpress_http.calls_for("POST", "https://site/wp-json/wp/v2/categories"))
        == 1
    )


def test_ensure_taxonomy_terms_rejects_empty_rest_base(assert_app_error) -> None:
    request = WordPressTaxonomyEnsureRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        taxonomy_rest_base="",
        terms=[WordPressTaxonomyTerm(schema_version="1.0", slug="x", name="X")],
    )

    try:
        svc.ensure_taxonomy_terms(request, _ctx())
    except Exception as err:
        assert_app_error(err, code="wp_taxonomy_invalid_rest_base", retryable=False)
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_upload_media_invalid_response(wordpress_http, assert_app_error) -> None:
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/media",
        status_code=201,
        payload={"id": None},
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
        assert_app_error(err, code="wp_media_invalid_response", retryable=False)
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_upload_media_server_error_logs_response_diagnostics(
    wordpress_http,
    caplog,
    assert_app_error,
    assert_logs_have_required_fields,
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
    else:  # pragma: no cover
        raise AssertionError("expected AppError")

    events = [
        json.loads(record.message)
        for record in caplog.records
        if "wp_media_upload_http_error" in record.message
    ]
    assert len(events) == 1
    assert events[0]["fields"]["status_code"] == 503
    assert events[0]["fields"]["reason"] == "Service Unavailable"
    assert "temporary outage" in events[0]["fields"]["response_body_excerpt"]
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
        assert err.context["status_code"] == 429
        assert err.context["response_headers"]["Retry-After"] == "60"
    else:  # pragma: no cover
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
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_batch_lookup_reuses_pooled_session(
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    caplog,
) -> None:
    class _FakeSession:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        def mount(self, _prefix: str, _adapter: Any) -> None:
            return

        def request(self, method: str, url: str, **kwargs: Any) -> FakeHttpResponse:
            self.calls.append({"method": method, "url": url, **kwargs})
            search = str((kwargs.get("params") or {}).get("search") or "")
            if "file-1" in search:
                return FakeHttpResponse.from_payload(
                    status_code=200,
                    payload=[
                        {
                            "id": 11,
                            "link": "https://pooled.test/p/11",
                            "content": {"rendered": "Drive fileId: file-1"},
                        }
                    ],
                )
            return FakeHttpResponse.from_payload(status_code=200, payload=[])

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
    assert len(created_sessions) == 1
    assert len(created_sessions[0].calls) == 2
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
    assert lookup_complete[0]["fields"]["used_pooled_session"] is True
    assert lookup_complete[0]["fields"]["pool_reused"] is False
    assert lookup_complete[1]["fields"]["used_pooled_session"] is True
    assert lookup_complete[1]["fields"]["pool_reused"] is True


def test_create_post_session_request_exception_adapts_to_app_error(
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    class _FakeSession:
        def mount(self, _prefix: str, _adapter: Any) -> None:
            return

        def request(self, method: str, url: str, **kwargs: Any) -> FakeHttpResponse:
            raise requests.RequestException(
                f"boom {method} {url} {kwargs.get('timeout')}"
            )

    external_boundary_mocks_only.setattr(svc.requests, "Session", lambda: _FakeSession())

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
        assert err.context["method"] == "POST"
        assert err.context["url"] == "https://create-error.test/wp-json/wp/v2/posts"
        assert err.context["pool_key"] == "https://create-error.test"
    else:  # pragma: no cover
        raise AssertionError("expected AppError")
