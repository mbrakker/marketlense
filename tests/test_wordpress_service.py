import json
from types import SimpleNamespace

import pytest

from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressCategoryEnsureRequest,
    WordPressCategoryTerm,
    WordPressMediaUploadRequest,
    WordPressPostCreateRequest,
    WordPressPostLookupRequest,
    WordPressPostUpdateRequest,
)
from src.services import wordpress_service as svc
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _response(status_code: int, payload: object) -> SimpleNamespace:
    return SimpleNamespace(status_code=status_code, text=json.dumps(payload))


def test_create_post_success(monkeypatch):
    captured = {}

    def _post(url, headers, data, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["payload"] = json.loads(data)
        captured["timeout"] = timeout
        return _response(
            201, {"id": 10, "link": "https://site/p/10", "status": "publish"}
        )

    monkeypatch.setattr(svc.requests, "post", _post)
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
    )
    response = svc.create_post(request, _ctx())
    assert response.post_id == 10
    assert response.link == "https://site/p/10"
    assert captured["url"].endswith("/wp-json/wp/v2/posts")
    assert captured["payload"]["slug"] == "slug"
    assert captured["payload"]["categories"] == [1, 2]
    assert captured["payload"]["tags"] == [3]


def test_create_post_custom_post_type_endpoint(monkeypatch):
    captured = {}

    def _post(url, headers, data, timeout):
        captured["url"] = url
        return _response(
            201, {"id": 10, "link": "https://site/r/10", "status": "publish"}
        )

    monkeypatch.setattr(svc.requests, "post", _post)
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
    assert response.post_id == 10
    assert captured["url"].endswith("/wp-json/wp/v2/ml_report")


def test_create_post_client_error(monkeypatch):
    monkeypatch.setattr(
        svc.requests, "post", lambda *args, **kwargs: _response(400, {"message": "bad"})
    )
    request = WordPressPostCreateRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        title="T",
        content_html="<p>x</p>",
        status="publish",
    )
    with pytest.raises(AppError) as exc:
        svc.create_post(request, _ctx())
    assert exc.value.code == "wp_post_client_error"
    assert exc.value.retryable is False


def test_find_post_by_file_id_found(monkeypatch):
    payload = [
        {
            "id": 11,
            "link": "https://site/p/11",
            "content": {"rendered": "Drive fileId: file-1"},
        },
    ]
    monkeypatch.setattr(
        svc.requests, "get", lambda *args, **kwargs: _response(200, payload)
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


def test_ensure_categories_creates_missing_terms(monkeypatch):
    calls = {"get": 0, "post": 0}

    def _get(url, headers, params, timeout):
        calls["get"] += 1
        if params.get("slug") == "existing":
            return _response(200, [{"id": 5}])
        return _response(200, [])

    def _post(url, headers, data, timeout):
        calls["post"] += 1
        payload = json.loads(data)
        if payload.get("slug") == "new":
            return _response(201, {"id": 7})
        return _response(400, {"message": "bad"})

    monkeypatch.setattr(svc.requests, "get", _get)
    monkeypatch.setattr(svc.requests, "post", _post)
    request = WordPressCategoryEnsureRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        categories=[
            WordPressCategoryTerm(
                schema_version="1.0", slug="existing", name="Existing"
            ),
            WordPressCategoryTerm(schema_version="1.0", slug="new", name="New"),
        ],
    )
    response = svc.ensure_categories(request, _ctx())
    assert response.slug_to_id == {"existing": 5, "new": 7}
    assert calls["get"] == 2
    assert calls["post"] == 1


def test_upload_media_invalid_response(monkeypatch):
    monkeypatch.setattr(
        svc.requests, "post", lambda *args, **kwargs: _response(201, {"id": None})
    )
    request = WordPressMediaUploadRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        filename="x.png",
        mime_type="image/png",
        data=b"abc",
    )
    with pytest.raises(AppError) as exc:
        svc.upload_media(request, _ctx())
    assert exc.value.code == "wp_media_invalid_response"


def test_update_post_categories_server_error(monkeypatch):
    monkeypatch.setattr(
        svc.requests,
        "post",
        lambda *args, **kwargs: _response(503, {"message": "retry"}),
    )
    request = WordPressPostUpdateRequest(
        schema_version="1.0",
        base_url="https://site",
        auth_header="Bearer token",
        post_id=12,
        categories=[1],
    )
    with pytest.raises(AppError) as exc:
        svc.update_post_categories(request, _ctx())
    assert exc.value.code == "wp_post_update_server_error"
    assert exc.value.retryable is True
