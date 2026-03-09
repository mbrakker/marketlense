from __future__ import annotations

from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressMediaUploadRequest,
    WordPressPostCreateRequest,
    WordPressPostLookupRequest,
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

    assert response.found is True
    assert response.post_id == 11
    assert response.link == "https://site/p/11"


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
    assert call.verify is False


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
