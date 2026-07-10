from __future__ import annotations

from ._shared import *  # noqa: F401,F403

# ruff: noqa: F401,F403,F405


def test_publish_html_uses_preloaded_snapshot_with_real_wordpress_side_effect(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    write_report_card_fixture(settings, "out/missing-report.html")
    add_card_media_responses(wordpress_http)
    html_text = (
        "<html><head><title>Report</title></head>"
        "<body>Drive fileId: file123</body></html>"
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
            html_path="out/missing-report.html",
            auth_header="Bearer token",
            file_id=None,
            html_snapshot=build_publish_html_snapshot(html_text),
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "published"
    assert outcome.file_id == "file123"
    assert outcome.post_id == 42
    assert outcome.post_url == "https://example.com/post/42"
    assert "Drive fileId: file123" in post_call.json_data["content"]


def test_publish_html_injects_hidden_file_id_marker_when_missing(
    publish_settings_factory,
    run_context,
    wordpress_http,
    assert_no_defaulted_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    write_report_card_fixture(settings, "out/report.html")
    add_card_media_responses(wordpress_http)
    html_text = (
        "<html><head><title>Report</title></head>"
        "<body><section><h1>Report</h1></section></body></html>"
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
            html_path="out/report.html",
            auth_header="Bearer token",
            file_id="file123",
            html_text=html_text,
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert_no_defaulted_required_fields(outcome)
    assert outcome.status == "published"
    assert outcome.file_id == "file123"
    assert "<p hidden>Drive fileId: file123</p>" in post_call.json_data["content"]


def test_publish_html_blocks_editorial_contract_failures_with_rule_ids(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="block")
    write_report_card_fixture(settings, "out/report.html")
    add_card_media_responses(wordpress_http)
    html_text = (
        "<html><head><title>Report</title>"
        '<meta name="editorial-contract-version" content="public-report-editorial-v1">'
        "</head><body>"
        "Drive fileId: file123"
        "<article>Overall, this report provides valuable insights from "
        "report:executive_advisory.recommendations:r1.</article>"
        "</body></html>"
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path="out/report.html",
            auth_header="Bearer token",
            file_id="file123",
            html_text=html_text,
        ),
        settings,
        run_context,
    )

    assert outcome.status == "skipped"
    assert outcome.error == "publish_editorial_contract_failed"
    assert outcome.validation_status == "fail"
    assert any(
        "editorial.generic_phrasing" in issue
        for issue in outcome.validation_issues
    )
    assert any(
        "editorial.internal_reference" in issue
        for issue in outcome.validation_issues
    )
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/ml_report")
        == []
    )


def test_publish_html_uses_filename_for_nonreport_when_document_title_is_missing(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    settings = replace(settings, wp=replace(settings.wp, post_type="ml_signal"))
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_signal",
        status_code=201,
        payload={"id": 42, "link": "https://example.com/post/42", "status": "publish"},
    )

    outcome = pg.publish_html(
        PublishRequest(
            schema_version="1.0",
            html_path="out/report.html",
            auth_header="Bearer token",
            file_id="file123",
            html_text="<html><body>Report body</body></html>",
        ),
        settings,
        run_context,
    )

    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_signal"
    )[0]
    assert outcome.status == "published"
    assert post_call.json_data["title"] == "report"
    assert post_call.json_data["slug"] == "report"
