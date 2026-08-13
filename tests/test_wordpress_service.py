from __future__ import annotations

import hashlib
import json
import logging
import warnings

import urllib3  # type: ignore[import-untyped]

from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressAuthSettings,
    WordPressCardUpdateRequest,
    WordPressMediaUploadRequest,
    WordPressPostCreateRequest,
    WordPressPostLookupBatchRequest,
    WordPressPostLookupRequest,
    WordPressPostReadExpectation,
    WordPressPostReadRequest,
    WordPressTaxonomyEnsureRequest,
    WordPressTaxonomyTerm,
)
from src.services import wordpress_service as svc
from src.utils.errors import AppError
from src.utils.wordpress_readback import wordpress_readback_value_sha256
from tests.support.fakes import FakeHttpResponse, RecordedHttpRequest


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _wp_auth_settings(*, post_type: str = "ml_report") -> WordPressAuthSettings:
    return WordPressAuthSettings(
        schema_version="1.0",
        site_url="https://site",
        username="user",
        app_password="app-password",
        bearer_token=None,
        post_status="draft",
        post_type=post_type,
    )


def _preflight_meta_schema(*meta_keys: str) -> dict[str, object]:
    return {
        "schema": {
            "properties": {
                "meta": {"properties": {key: {"type": "string"} for key in meta_keys}}
            }
        }
    }


def test_preflight_publish_target_verifies_authenticated_proof_meta_schema(
    wordpress_http,
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/types/ml_report",
        status_code=200,
        payload={"rest_base": "ml_report"},
    )
    wordpress_http.add_json(
        "OPTIONS",
        "https://site/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=_preflight_meta_schema(
            "ml_file_id",
            "ml_content_sha256",
            "ml_source_title",
            "ml_source_url",
            "ml_source_note",
            "ml_source_publication_date",
        ),
    )

    response = svc.preflight_publish_target(_wp_auth_settings(), _ctx())

    assert response.reachable is True
    assert response.verified_meta_keys == (
        "ml_file_id",
        "ml_content_sha256",
        "ml_source_title",
        "ml_source_url",
        "ml_source_note",
        "ml_source_publication_date",
    )
    assert (
        wordpress_http.calls_for("OPTIONS", "https://site/wp-json/wp/v2/ml_report")[0]
        .headers["Authorization"]
        .startswith("Basic ")
    )


def test_preflight_publish_target_blocks_missing_proof_meta_schema(
    wordpress_http, assert_app_error
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/types/ml_report",
        status_code=200,
        payload={"rest_base": "ml_report"},
    )
    wordpress_http.add_json(
        "OPTIONS",
        "https://site/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=_preflight_meta_schema("ml_file_id"),
    )

    try:
        svc.preflight_publish_target(_wp_auth_settings(), _ctx())
    except Exception as err:
        assert_app_error(
            err,
            code="wordpress_publish_target_metadata_missing",
            retryable=False,
        )
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


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
    request = WordPressCardUpdateRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        post_id=12,
        featured_media=303,
        meta={"ml_card_schema_version": "1.0"},
        post_type="ml_report",
    )

    response = svc.update_card(request, _ctx())

    call = wordpress_http.calls_for("POST", "https://site/wp-json/wp/v2/ml_report/12")[
        0
    ]
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
    assert call.params["status"] == "any"


def test_find_post_by_file_id_fails_closed_for_multiple_matches(
    wordpress_http, assert_app_error
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/posts",
        status_code=200,
        payload=[
            {"id": 11, "link": "https://site/p/11", "meta": {"ml_file_id": "file-1"}},
            {"id": 12, "link": "https://site/p/12", "meta": {"ml_file_id": "file-1"}},
        ],
    )

    try:
        svc.find_post_by_file_id(
            WordPressPostLookupRequest(
                schema_version="1.0",
                base_url="https://site",
                auth_header="Bearer token",
                file_id="file-1",
            ),
            _ctx(),
        )
    except Exception as err:
        assert_app_error(err, code="wp_post_lookup_ambiguous", retryable=False)
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


def test_read_post_by_id_verifies_expected_source_identity(wordpress_http) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/posts/11",
        status_code=200,
        payload={
            "id": 11,
            "link": "https://site/p/11",
            "meta": {"ml_file_id": "file-1"},
        },
    )

    response = svc.read_post_by_id(
        WordPressPostReadRequest(
            schema_version="1.0",
            base_url="https://site",
            auth_header="Bearer token",
            post_id=11,
            file_id="file-1",
        ),
        _ctx(),
    )

    assert response.found is True
    assert response.post_id == 11
    assert response.link == "https://site/p/11"
    call = wordpress_http.calls_for("GET", "https://site/wp-json/wp/v2/posts/11")[0]
    assert call.params == {"context": "edit"}


def test_read_post_by_id_proves_complete_authenticated_transaction(
    wordpress_http,
) -> None:
    raw_content = "<p>Verified report content.</p>"
    rendered_content = "<p>Verified report content.</p>"
    content_sha256 = hashlib.sha256(raw_content.encode("utf-8")).hexdigest()
    rendered_sha256 = hashlib.sha256(rendered_content.encode("utf-8")).hexdigest()
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/ml_report/11",
        status_code=200,
        payload={
            "id": 11,
            "type": "ml_report",
            "status": "publish",
            "link": "https://site/reports/verified-report/",
            "featured_media": 91,
            "categories": [2, 4],
            "tags": [7],
            "ml_publisher": [19],
            "content": {"raw": raw_content, "rendered": rendered_content},
            "yoast_head_json": {"og_url": "https://site/reports/verified-report/"},
            "meta": {
                "ml_file_id": "file-1",
                "ml_content_sha256": content_sha256,
                "ml_source_title": "Verified report",
                "ml_source_url": "https://publisher.example/report",
                "ml_card_cover_large_id": 91,
            },
        },
    )

    response = svc.read_post_by_id(
        WordPressPostReadRequest(
            schema_version="1.0",
            base_url="https://site",
            auth_header="Bearer token",
            post_id=11,
            file_id="file-1",
            post_type="ml_report",
            expectation=WordPressPostReadExpectation(
                schema_version="1.0",
                post_type="ml_report",
                status="publish",
                file_id="file-1",
                content_sha256=content_sha256,
                canonical_url="https://site/reports/verified-report/",
                metadata={
                    key: _field_sha256(value)
                    for key, value in {
                        "ml_file_id": "file-1",
                        "ml_content_sha256": content_sha256,
                        "ml_source_title": "Verified report",
                        "ml_source_url": "https://publisher.example/report",
                        "ml_card_cover_large_id": 91,
                    }.items()
                },
                source_attribution={
                    "ml_source_title": _field_sha256("Verified report"),
                    "ml_source_url": _field_sha256("https://publisher.example/report"),
                },
                taxonomy_assignments={
                    "categories": [2, 4],
                    "tags": [7],
                    "ml_publisher": [19],
                },
                media_associations={
                    "featured_media": 91,
                    "ml_card_cover_large_id": 91,
                },
                rendered_content_sha256=rendered_sha256,
            ),
        ),
        _ctx(),
    )

    assert response.found is True
    assert response.content_verified is True
    assert response.metadata_verified is True
    assert {check.name: check.status for check in response.checks} == {
        "post_id": "verified",
        "report_file_identity": "verified",
        "canonical_url": "verified",
        "post_type": "verified",
        "status": "verified",
        "content_checksum": "verified",
        "source_attribution": "verified",
        "metadata": "verified",
        "taxonomy_assignments": "verified",
        "media_associations": "verified",
        "open_graph_url": "verified",
        "final_rendered_content_hash": "verified",
    }


def _field_sha256(value: object) -> str:
    return wordpress_readback_value_sha256(value)


def test_read_post_by_id_fails_closed_when_content_checksum_differs(
    wordpress_http,
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/ml_report/11",
        status_code=200,
        payload={
            "id": 11,
            "type": "ml_report",
            "status": "publish",
            "link": "https://site/reports/verified-report/",
            "content": {"raw": "unexpected"},
            "meta": {"ml_file_id": "file-1"},
        },
    )

    response = svc.read_post_by_id(
        WordPressPostReadRequest(
            schema_version="1.0",
            base_url="https://site",
            auth_header="Bearer token",
            post_id=11,
            file_id="file-1",
            post_type="ml_report",
            expectation=WordPressPostReadExpectation(
                schema_version="1.0",
                post_type="ml_report",
                status="publish",
                file_id="file-1",
                content_sha256="different",
                canonical_url="https://site/reports/verified-report/",
            ),
        ),
        _ctx(),
    )

    assert response.found is False
    assert {check.name: check.status for check in response.checks}[
        "content_checksum"
    ] == ("mismatch")


def test_read_post_by_id_fails_closed_when_required_raw_content_is_not_exposed(
    wordpress_http,
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/ml_report/11",
        status_code=200,
        payload={
            "id": 11,
            "type": "ml_report",
            "status": "publish",
            "link": "https://site/reports/verified-report/",
            "content": {"rendered": "<p>Rendered only</p>"},
            "meta": {"ml_file_id": "file-1"},
        },
    )

    response = svc.read_post_by_id(
        WordPressPostReadRequest(
            schema_version="1.0",
            base_url="https://site",
            auth_header="Bearer token",
            post_id=11,
            file_id="file-1",
            post_type="ml_report",
            expectation=WordPressPostReadExpectation(
                schema_version="1.0",
                post_type="ml_report",
                status="publish",
                file_id="file-1",
                content_sha256="required-checksum",
                canonical_url="https://site/reports/verified-report/",
            ),
        ),
        _ctx(),
    )

    assert response.found is False
    assert {check.name: check.status for check in response.checks}[
        "content_checksum"
    ] == ("mismatch")


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
        file_id = str(call.params.get("ml_file_id") or "")
        if file_id == "file-1":
            return FakeHttpResponse.from_payload(
                status_code=200,
                payload=[
                    {
                        "id": 11,
                        "link": "https://site/p/11",
                        "content": {"rendered": "Public report content"},
                        "meta": {"ml_file_id": "file-1"},
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
    assert len(wordpress_http.calls_for("GET", "https://site/wp-json/wp/v2/posts")) == 2


def test_find_posts_by_file_id_batch_captures_item_errors(
    wordpress_http, assert_app_error
) -> None:
    def _lookup(call: RecordedHttpRequest) -> FakeHttpResponse:
        file_id = str(call.params.get("ml_file_id") or "")
        if file_id == "file-bad":
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
        assert_app_error(
            err,
            code="wordpress_target_installation_redirect",
            retryable=False,
        )
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
        if "wordpress_target_installation_redirect" in record.message
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


def test_ensure_taxonomy_terms_writes_topic_semantics_for_existing_terms(
    wordpress_http,
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/categories",
        status_code=200,
        payload=[{"id": 5}],
    )
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/categories/5",
        status_code=200,
        payload={"id": 5},
    )
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/categories",
        status_code=200,
        payload=[
            {
                "id": 5,
                "description": "Payments category",
                "meta": {
                    "ml_topic_definition": "Reports centered on digital payment behavior.",
                    "ml_topic_include_when": [
                        "Checkout, wallet, or fraud evidence is central."
                    ],
                    "ml_topic_exclude_when": [
                        "Payments are only a minor operational detail."
                    ],
                    "ml_topic_schema_version": "1.2",
                },
            }
        ],
    )
    request = WordPressTaxonomyEnsureRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        taxonomy_rest_base="categories",
        terms=[
            WordPressTaxonomyTerm(
                schema_version="1.1",
                slug="digital_payments",
                name="Digital Payments",
                description="Payments category",
                definition="Reports centered on digital payment behavior.",
                include_when=["Checkout, wallet, or fraud evidence is central."],
                exclude_when=["Payments are only a minor operational detail."],
                semantics_version="1.2",
            )
        ],
    )

    response = svc.ensure_taxonomy_terms(request, _ctx())

    update_call = wordpress_http.calls_for(
        "POST", "https://site/wp-json/wp/v2/categories/5"
    )[0]
    assert response.slug_to_id == {"digital_payments": 5}
    assert update_call.json_data == {
        "name": "Digital Payments",
        "slug": "digital_payments",
        "description": "Payments category",
        "meta": {
            "ml_topic_definition": "Reports centered on digital payment behavior.",
            "ml_topic_include_when": [
                "Checkout, wallet, or fraud evidence is central."
            ],
            "ml_topic_exclude_when": ["Payments are only a minor operational detail."],
            "ml_topic_schema_version": "1.2",
        },
    }
    readback_call = wordpress_http.calls_for(
        "GET", "https://site/wp-json/wp/v2/categories"
    )[1]
    assert readback_call.params == {"slug": "digital_payments", "context": "edit"}


def test_ensure_taxonomy_terms_rejects_missing_topic_semantics_readback(
    wordpress_http,
    assert_app_error,
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/categories",
        status_code=200,
        payload=[{"id": 5}],
    )
    wordpress_http.add_json(
        "POST",
        "https://site/wp-json/wp/v2/categories/5",
        status_code=200,
        payload={"id": 5},
    )
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/categories",
        status_code=200,
        payload=[
            {
                "id": 5,
                "description": "Payments category",
                "meta": {},
            }
        ],
    )
    request = WordPressTaxonomyEnsureRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        taxonomy_rest_base="categories",
        terms=[
            WordPressTaxonomyTerm(
                schema_version="1.1",
                slug="digital_payments",
                name="Digital Payments",
                description="Payments category",
                definition="Reports centered on digital payment behavior.",
                include_when=["Checkout, wallet, or fraud evidence is central."],
                exclude_when=["Payments are only a minor operational detail."],
                semantics_version="1.2",
            )
        ],
    )

    try:
        svc.ensure_taxonomy_terms(request, _ctx())
    except AppError as err:
        assert_app_error(
            err,
            code="wp_taxonomy_semantics_readback_mismatch",
            retryable=False,
            severity="error",
        )
        assert err.context["reason"] == "meta_mismatch:ml_topic_definition"
    else:  # pragma: no cover
        raise AssertionError("expected AppError")


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
