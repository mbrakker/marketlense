from __future__ import annotations

import pytest

from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import (
    WordPressAuthSettings,
    WordPressPublishCapabilityRequirements,
    WordPressPublishTargetPreflightRequest,
    WordPressPublishTargetPreflightResponse,
)
from src.services import wordpress_service
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _settings() -> PublishSettings:
    return PublishSettings(
        schema_version="1.0",
        output_dir="out",
        state_db="state.sqlite",
        reports_db="reports.sqlite",
        category_mapping_path="categories.yaml",
        wp=WordPressAuthSettings(
            schema_version="1.0",
            site_url="https://site",
            username="user",
            app_password="app-password",
            bearer_token=None,
            post_status="draft",
            post_type="ml_report",
        ),
    )


def _meta_schema() -> dict[str, object]:
    keys = (
        "ml_file_id",
        "ml_content_sha256",
        "ml_source_title",
        "ml_source_url",
        "ml_source_note",
        "ml_source_publication_date",
    )
    return {
        "schema": {
            "properties": {
                "meta": {"properties": {key: {"type": "string"} for key in keys}}
            }
        }
    }


def test_publish_capability_verifies_auth_and_create_permission(
    wordpress_http,
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/users/me",
        status_code=200,
        payload={"id": 7, "capabilities": {"edit_ml_reports": True}},
    )
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/types/ml_report",
        status_code=200,
        payload={
            "rest_base": "ml_report",
            "capabilities": {"create_posts": "edit_ml_reports"},
        },
    )
    wordpress_http.add_json(
        "OPTIONS",
        "https://site/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=_meta_schema(),
    )

    response = wordpress_service.preflight_publish_capability(_settings(), _ctx())

    assert response.authenticated is True
    assert response.verified_capabilities == ("create_posts",)
    assert response.provider_calls == 3
    user_call = wordpress_http.calls_for("GET", "https://site/wp-json/wp/v2/users/me")[
        0
    ]
    assert user_call.params == {"context": "edit"}
    assert user_call.timeout <= 5.0


def test_publish_capability_counts_rest_route_fallback_requests(wordpress_http) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/users/me",
        status_code=200,
        payload={"id": 7, "capabilities": {"edit_ml_reports": True}},
    )
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/types/ml_report",
        status_code=404,
        payload={"code": "rest_no_route"},
    )
    wordpress_http.add_json(
        "GET",
        "https://site/index.php?rest_route=%2Fwp%2Fv2%2Ftypes%2Fml_report",
        status_code=200,
        payload={
            "rest_base": "ml_report",
            "capabilities": {"create_posts": "edit_ml_reports"},
        },
    )
    wordpress_http.add_json(
        "OPTIONS",
        "https://site/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=_meta_schema(),
    )

    response = wordpress_service.preflight_publish_capability(_settings(), _ctx())

    assert response.authenticated is True
    assert response.provider_calls == 4
    assert len(wordpress_http.calls) == 4


def test_publish_capability_counts_prior_calls_when_later_request_fails(
    wordpress_http,
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/users/me",
        status_code=200,
        payload={"id": 7, "capabilities": {"edit_ml_reports": True}},
    )
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/types/ml_report",
        status_code=503,
        payload={"code": "service_unavailable"},
    )

    with pytest.raises(AppError) as exc_info:
        wordpress_service.preflight_publish_capability(_settings(), _ctx())

    assert getattr(exc_info.value, "retryable", False) is True
    assert getattr(exc_info.value, "context", {}).get("provider_calls") == 2


def test_publish_capability_blocks_invalid_auth_without_writes(
    wordpress_http, assert_app_error
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/users/me",
        status_code=401,
        payload={"code": "rest_not_logged_in"},
    )

    try:
        wordpress_service.preflight_publish_capability(_settings(), _ctx())
    except Exception as err:
        assert_app_error(
            err,
            code="wordpress_authentication_invalid",
            retryable=False,
        )
    else:  # pragma: no cover
        raise AssertionError("expected AppError")
    assert (
        len(wordpress_http.calls_for("GET", "https://site/wp-json/wp/v2/users/me")) == 1
    )
    assert not [
        call for call in wordpress_http.calls if call.method in {"POST", "DELETE"}
    ]


def test_publish_capability_checks_all_entity_types_and_projection_route_read_only(
    wordpress_http,
) -> None:
    post_types = ("ml_report", "ml_briefing", "ml_signal")
    user_capabilities = {"manage_options": True}
    for post_type in post_types:
        capability = f"edit_{post_type}s"
        user_capabilities[capability] = True
        wordpress_http.add_json(
            "GET",
            f"https://site/wp-json/wp/v2/types/{post_type}",
            status_code=200,
            payload={
                "rest_base": post_type,
                "capabilities": {
                    "create_posts": capability,
                    "publish_posts": capability,
                },
            },
        )
        wordpress_http.add_json(
            "OPTIONS",
            f"https://site/wp-json/wp/v2/{post_type}",
            status_code=200,
            payload=_meta_schema()
            if post_type == "ml_report"
            else {
                "schema": {
                    "properties": {
                        "meta": {
                            "properties": {
                                "ml_file_id": {"type": "string"},
                                "ml_content_sha256": {"type": "string"},
                            }
                        }
                    }
                }
            },
        )
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/users/me",
        status_code=200,
        payload={"id": 7, "capabilities": user_capabilities},
    )
    wordpress_http.add_json(
        "OPTIONS",
        "https://site/wp-json/marketlense/v1/intelligence-projection",
        status_code=200,
        payload={"methods": ["POST"]},
    )
    requirements = WordPressPublishCapabilityRequirements(
        schema_version="1.0",
        post_types=post_types,
        post_type_capabilities=("create_posts", "publish_posts"),
        user_capabilities=("manage_options",),
        rest_routes=("marketlense/v1/intelligence-projection",),
    )

    response = wordpress_service.preflight_publish_capability(
        _settings(), _ctx(), requirements
    )

    assert response.verified_post_types == post_types
    assert response.verified_capabilities == ("create_posts", "publish_posts")
    assert response.verified_user_capabilities == ("manage_options",)
    assert response.verified_rest_routes == requirements.rest_routes
    assert response.provider_calls == 8
    assert not [
        call for call in wordpress_http.calls if call.method in {"POST", "DELETE"}
    ]


def test_publish_capability_blocks_projection_without_manage_options(
    wordpress_http, assert_app_error
) -> None:
    wordpress_http.add_json(
        "GET",
        "https://site/wp-json/wp/v2/users/me",
        status_code=200,
        payload={"id": 7, "capabilities": {"edit_posts": True}},
    )
    requirements = WordPressPublishCapabilityRequirements(
        schema_version="1.0",
        user_capabilities=("manage_options",),
        rest_routes=("marketlense/v1/intelligence-projection",),
    )

    try:
        wordpress_service.preflight_publish_capability(
            _settings(), _ctx(), requirements
        )
    except Exception as err:
        assert_app_error(
            err,
            code="wordpress_user_capability_missing",
            retryable=False,
        )
    else:  # pragma: no cover
        raise AssertionError("expected AppError")
    assert wordpress_http.calls == [
        call
        for call in wordpress_http.calls
        if call.method == "GET" and call.url.endswith("/users/me")
    ]


def test_publish_capability_requirements_reject_invalid_route() -> None:
    with pytest.raises(ValueError):
        WordPressPublishCapabilityRequirements(
            schema_version="1.0", rest_routes=("../users/me",)
        )


def test_publish_capability_requirements_reject_lowercase_methods() -> None:
    with pytest.raises(ValueError):
        WordPressPublishCapabilityRequirements(
            schema_version="1.0", rest_methods=("post",)
        )


def test_publish_capability_requirements_reject_non_tuple_post_types() -> None:
    with pytest.raises(ValueError):
        WordPressPublishCapabilityRequirements(
            schema_version="1.0", post_types=["ml_report"]
        )  # type: ignore[arg-type]


def test_wordpress_preflight_contracts_preserve_legacy_positional_fields() -> None:
    request = WordPressPublishTargetPreflightRequest(
        "1.0",
        "https://site",
        "Basic credentials",
        "ml_report",
        False,
        None,
        ("ml_file_id",),
        True,
        ("create_posts",),
        5.0,
    )
    response = WordPressPublishTargetPreflightResponse(
        "1.0",
        "https://site",
        "ml_report",
        "https://site/wp-json/wp/v2/ml_report",
        True,
        200,
        ("ml_file_id",),
        True,
        ("create_posts",),
        3,
    )

    assert request.timeout_seconds == 5.0
    assert request.additional_post_types == ()
    assert response.provider_calls == 3
    assert response.verified_post_types == ()
