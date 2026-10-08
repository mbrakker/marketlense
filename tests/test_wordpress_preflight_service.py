from __future__ import annotations

from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.wordpress import WordPressAuthSettings
from src.services import wordpress_service


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
