from __future__ import annotations

import hashlib

from src.utils.wordpress_readback import wordpress_readback_value_sha256

from ._shared import *  # noqa: F401,F403

# ruff: noqa: F401,F403,F405


def test_publish_html_uploads_three_card_covers_and_sends_registered_meta(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        '<body><section id="report-intelligence" class="report-intelligence-panel">'
        "Topics covered</section>Drive fileId: file123</body></html>",
        encoding="utf-8",
    )
    write_report_card_fixture(settings, html_path)

    def _upload_card(call: RecordedHttpRequest) -> FakeHttpResponse:
        filename = call.files["file"][0]
        media_id = {
            "report-card-small.png": 301,
            "report-card-medium.png": 302,
            "report-card-large.png": 303,
        }[filename]
        return FakeHttpResponse.from_payload(
            status_code=201,
            payload={
                "id": media_id,
                "source_url": f"https://example.com/uploads/{media_id}.png",
            },
        )

    wordpress_http.add(
        "POST",
        "https://example.com/wp-json/wp/v2/media",
        _upload_card,
    )
    for media_id in (301, 302, 303):
        wordpress_http.add_json(
            "POST",
            f"https://example.com/wp-json/wp/v2/media/{media_id}",
            status_code=200,
            payload={"id": media_id},
        )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path=str(html_path),
            auth_header="Bearer token",
            file_id="file123",
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    upload_calls = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/media"
    )
    assert_no_defaulted_required_fields(outcome)
    assert sorted(call.files["file"][0] for call in upload_calls) == sorted(
        [
            "report-card-small.png",
            "report-card-medium.png",
            "report-card-large.png",
        ]
    )
    assert post_call.json_data["featured_media"] == 303
    assert post_call.json_data["title"] == (
        "Global Economic Conditions Quarterly Update"
    )
    assert post_call.json_data["meta"] == {
        "ml_file_id": "file123",
        "ml_content_sha256": hashlib.sha256(
            post_call.json_data["content"].encode("utf-8")
        ).hexdigest(),
        "ml_time_period": "Q2 2026",
        "ml_region": "Global",
        "ml_publisher_name": "McKinsey & Company",
        "ml_public_intelligence": "1",
        "ml_card_schema_version": "1.0",
        "ml_card_title_scale": "long",
        "ml_card_tldr_compact": "Complete compact TLDR.",
        "ml_card_tldr_standard": (
            "Complete standard TLDR with the required grounded context."
        ),
        "ml_card_key_insights": ["First insight.", "Second insight."],
        "ml_card_geography_scope": "global",
        "ml_card_cover_fingerprint": {
            "geometry_family": "ascending_trajectory",
            "seed": 184221,
        },
        "ml_card_cover_small_id": 301,
        "ml_card_cover_medium_id": 302,
        "ml_card_cover_large_id": 303,
        "ml_source_title": "Global Economic Conditions Quarterly Update",
        "ml_source_url": "https://publisher.example/reports/global-economic-conditions",
        "ml_source_note": (
            "Source: McKinsey & Company — Global Economic Conditions Quarterly Update"
        ),
        "ml_source_publication_date": "2026-06-09",
    }
    assert outcome.readback_expectation is not None
    assert (
        outcome.readback_expectation.content_sha256
        == post_call.json_data["meta"]["ml_content_sha256"]
    )
    assert "ml_content_sha256" not in outcome.readback_expectation.metadata
    assert outcome.readback_expectation.taxonomy_assignments == {
        "categories": [],
        "tags": [],
    }
    assert outcome.readback_expectation.metadata[
        "ml_source_note"
    ] == wordpress_readback_value_sha256(post_call.json_data["meta"]["ml_source_note"])
    assert (
        post_call.json_data["meta"]["ml_source_note"]
        not in outcome.readback_expectation.metadata.values()
    )


def test_publish_html_updates_existing_report_card_post_in_place(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>",
        encoding="utf-8",
    )
    write_report_card_fixture(settings, html_path)
    add_card_media_responses(wordpress_http)
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report/42",
        status_code=200,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path=str(html_path),
            auth_header="Bearer token",
            file_id="file123",
            existing_post_id=42,
        ),
        settings,
        run_context,
    )

    update_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report/42"
    )[0]
    upload_calls = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/media"
    )
    assert outcome.status == "published"
    assert outcome.post_id == 42
    assert sorted(call.files["file"][0] for call in upload_calls) == [
        "report-card-large.png",
        "report-card-medium.png",
        "report-card-small.png",
    ]
    assert set(update_call.json_data) == {"featured_media", "meta"}
    assert update_call.json_data["featured_media"] == 303
    assert update_call.json_data["meta"]["ml_time_period"] == "Q2 2026"
    assert update_call.json_data["meta"]["ml_region"] == "Global"
    assert update_call.json_data["meta"]["ml_public_intelligence"] == "0"
    assert update_call.json_data["meta"]["ml_card_cover_small_id"] == 301
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/ml_report")
        == []
    )


def test_publish_html_preserves_public_intelligence_for_existing_report_card(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        '<body><section id="report-intelligence" class="report-intelligence-panel">'
        "Topics covered</section>Drive fileId: file123</body></html>",
        encoding="utf-8",
    )
    write_report_card_fixture(settings, html_path)
    add_card_media_responses(wordpress_http)
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report/42",
        status_code=200,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report/42",
        status_code=200,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    request = PublishRequest(
        schema_version="1.0",
        html_path=str(html_path),
        auth_header="Bearer token",
        file_id="file123",
        existing_post_id=42,
    )
    first = pg.publish_html(
        request,
        settings,
        run_context,
    )
    second = pg.publish_html(
        request,
        settings,
        run_context,
    )

    update_calls = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report/42"
    )
    assert first.status == second.status == "published"
    assert first.post_id == second.post_id == 42
    assert len(update_calls) == 2
    assert all(
        call.json_data["meta"]["ml_public_intelligence"] == "1" for call in update_calls
    )
    assert update_calls[0].json_data["meta"] == update_calls[1].json_data["meta"]


def test_publish_html_updates_legacy_post_with_the_report_card_contract(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    settings = replace(settings, wp=replace(settings.wp, post_type="post"))
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>",
        encoding="utf-8",
    )
    write_report_card_fixture(settings, html_path)
    add_card_media_responses(wordpress_http)
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/posts/42",
        status_code=200,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path=str(html_path),
            auth_header="Bearer token",
            file_id="file123",
            existing_post_id=42,
        ),
        settings,
        run_context,
    )

    update_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/posts/42"
    )[0]
    assert outcome.status == "published"
    assert update_call.json_data["meta"]["ml_publisher_name"] == "McKinsey & Company"
    assert update_call.json_data["meta"]["ml_card_schema_version"] == "1.0"
    assert update_call.json_data["meta"]["ml_card_cover_large_id"] == 303


def test_publish_html_resolves_output_root_relative_card_cover_paths(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>",
        encoding="utf-8",
    )
    write_report_card_fixture(settings, html_path)
    manifest_path = html_path.with_suffix("") / "report-card-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for size in ("small", "medium", "large"):
        manifest["covers"][size]["output_path"] = (
            f"out/report/assets/report-card-{size}.png"
        )
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    add_card_media_responses(wordpress_http)
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report/42",
        status_code=200,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path=str(html_path),
            auth_header="Bearer token",
            file_id="file123",
            existing_post_id=42,
        ),
        settings,
        run_context,
    )

    assert outcome.status == "published"
    assert outcome.post_id == 42


def test_publish_html_rejects_missing_report_card_manifest_before_post(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_app_error,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "missing-card.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>",
        encoding="utf-8",
    )

    with pytest.raises(AppError) as exc_info:
        pg.publish_html(
            PublishRequest(
                schema_version="1.0",
                html_path=str(html_path),
                auth_header="Bearer token",
                file_id="file123",
            ),
            settings,
            run_context,
        )

    assert_app_error(
        exc_info.value,
        code="cover_asset_set_incomplete",
        retryable=False,
    )
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/ml_report")
        == []
    )
