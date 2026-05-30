from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

import logging
import json

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportPublishPackage,
)
from src.contracts.publish import PublishOutcome
from src.contracts.wordpress import (
    WordPressPostLookupResponse,
    WordPressTagEnsureResponse,
    WordPressTaxonomyEnsureResponse,
)
from src.orchestrators.publish_orchestrator import publish_cross_report_package


def _package(tmp_path) -> CrossReportPublishPackage:
    return CrossReportPublishPackage(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        package_id="cross-report:analysis-ai",
        file_id="cross-report:analysis-ai",
        target_route="wordpress:ml_briefing",
        title="AI Commerce Across Reports",
        slug="ai-commerce-across-reports",
        excerpt="AI commerce is visible across selected reports.",
        body_html="<article><h1>AI Commerce Across Reports</h1></article>",
        html_text="<html><body><article><h1>AI Commerce Across Reports</h1></article></body></html>",
        html_path=str(tmp_path / "publish.html"),
        canonical_artifact_path=str(tmp_path / "analysis.json"),
        artifact_sha256="artifact-sha",
        validation_sha256="validation-sha",
        selected_theme_id="theme-ai",
        selected_report_ids=["report-a", "report-b"],
        source_metadata=[
            {"report_id": "report-a", "publisher": "Publisher A"},
            {"report_id": "report-b", "publisher": "Publisher B"},
        ],
        category_labels=["Retail"],
        tag_labels=["AI"],
        evidence_reference_ids=["ev-a", "ev-b"],
        raw_metric_ids=["metric-a"],
        prompt_hashes={"system": "system-hash", "user": "user-hash"},
        machine_metadata={"analysis_id": "analysis-ai"},
    )


def _settings(tmp_path):
    return SimpleNamespace(
        state_db=str(tmp_path / "state.sqlite"),
        output_dir=str(tmp_path),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path="src/config/category-mappings.yaml",
        media_upload_workers=1,
        validation_policy="block",
        wp=SimpleNamespace(
            site_url="https://example.com",
            username="user",
            app_password="pass",
            bearer_token=None,
            post_status="draft",
            post_type="posts",
            ssl_verify=True,
            ca_bundle_path=None,
        ),
    )


def _ensure_cross_report_taxonomy(request, ctx):
    if request.taxonomy_rest_base == "categories":
        return WordPressTaxonomyEnsureResponse(
            schema_version="1.0",
            slug_to_id={"retail": 11},
        )
    if request.taxonomy_rest_base == "ml_publisher":
        return WordPressTaxonomyEnsureResponse(
            schema_version="1.0",
            slug_to_id={"publisher-a": 21, "publisher-b": 22},
        )
    raise AssertionError(request.taxonomy_rest_base)


def _ensure_cross_report_tags(request, ctx):
    return WordPressTagEnsureResponse(
        schema_version="1.0",
        slug_to_id={"ai": 31},
    )


def test_publish_cross_report_package_dry_run_skips_wordpress(
    tmp_path,
    run_context,
) -> None:
    calls = []

    result = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=True,
        publish_html_fn=lambda request, settings, ctx: calls.append("publish"),
        find_post_by_file_id_fn=lambda request, ctx: calls.append("lookup"),
    )

    assert result.status == "dry_run"
    assert result.target_route == "wordpress:ml_briefing"
    assert result.idempotency_reused is False
    assert calls == []


def test_publish_cross_report_package_dry_run_reports_briefing_payload_classification(
    tmp_path,
    run_context,
) -> None:
    calls = []

    result = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=True,
        publish_html_fn=lambda request, settings, ctx: calls.append("publish"),
        find_post_by_file_id_fn=lambda request, ctx: calls.append("lookup"),
    )

    assert result.status == "dry_run"
    assert result.target_route == "wordpress:ml_briefing"
    assert result.target_post_type == "ml_briefing"
    assert result.target_slug == "ai-commerce-across-reports"
    assert result.category_slugs == ["retail"]
    assert result.tag_slugs == ["ai"]
    assert result.taxonomy_term_slugs == {
        "ml_publisher": ["publisher-a", "publisher-b"]
    }
    assert calls == []


def test_publish_cross_report_package_live_reuses_persisted_publish_outcome(
    tmp_path,
    run_context,
) -> None:
    publish_calls = []

    def _lookup(request, ctx):
        return WordPressPostLookupResponse(
            schema_version="1.0",
            found=False,
            post_id=None,
            link=None,
        )

    def _publish(request, settings, ctx):
        publish_calls.append(request)
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=request.file_id,
            status="published",
            post_id=123,
            post_url="https://example.com/briefings/ai-commerce-across-reports/",
        )

    first = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        ensure_taxonomy_terms_fn=_ensure_cross_report_taxonomy,
        ensure_tags_fn=_ensure_cross_report_tags,
        sleep_fn=lambda seconds: None,
    )
    second = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        ensure_taxonomy_terms_fn=_ensure_cross_report_taxonomy,
        ensure_tags_fn=_ensure_cross_report_tags,
        sleep_fn=lambda seconds: None,
    )

    assert first.status == "published"
    assert first.post_id == 123
    assert second.idempotency_reused is True
    assert (
        second.post_url == "https://example.com/briefings/ai-commerce-across-reports/"
    )
    assert len(publish_calls) == 1
    assert publish_calls[0].html_snapshot is not None


def test_publish_cross_report_package_routes_briefing_packages_to_briefing_post_type(
    tmp_path,
    run_context,
) -> None:
    observed_lookup_post_types = []
    observed_publish_post_types = []
    package = replace(_package(tmp_path), target_route="wordpress:ml_briefing")
    settings = _settings(tmp_path)
    settings.wp.post_type = "ml_report"

    def _lookup(request, ctx):
        observed_lookup_post_types.append(request.post_type)
        return WordPressPostLookupResponse(
            schema_version="1.0",
            found=False,
            post_id=None,
            link=None,
        )

    def _publish(request, settings, ctx):
        observed_publish_post_types.append(settings.wp.post_type)
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=request.file_id,
            status="published",
            post_id=321,
            post_url="https://example.com/briefings/ai-commerce-across-reports/",
        )

    result = publish_cross_report_package(
        package,
        settings,
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        ensure_taxonomy_terms_fn=_ensure_cross_report_taxonomy,
        ensure_tags_fn=_ensure_cross_report_tags,
        sleep_fn=lambda seconds: None,
    )

    assert result.status == "published"
    assert result.target_route == "wordpress:ml_briefing"
    assert result.post_url == "https://example.com/briefings/ai-commerce-across-reports/"
    assert observed_lookup_post_types == ["ml_briefing"]
    assert observed_publish_post_types == ["ml_briefing"]
    assert settings.wp.post_type == "ml_report"


def test_publish_cross_report_package_builds_briefing_terms_and_slug_payload(
    tmp_path,
    run_context,
) -> None:
    taxonomy_calls = []
    tag_calls = []
    publish_calls = []

    def _lookup(request, ctx):
        return WordPressPostLookupResponse(
            schema_version="1.0",
            found=False,
            post_id=None,
            link=None,
        )

    def _ensure_taxonomy(request, ctx):
        taxonomy_calls.append(request)
        if request.taxonomy_rest_base == "categories":
            return WordPressTaxonomyEnsureResponse(
                schema_version="1.0",
                slug_to_id={"retail": 11},
            )
        if request.taxonomy_rest_base == "ml_publisher":
            return WordPressTaxonomyEnsureResponse(
                schema_version="1.0",
                slug_to_id={"publisher-a": 21, "publisher-b": 22},
            )
        raise AssertionError(request.taxonomy_rest_base)

    def _ensure_tags(request, ctx):
        tag_calls.append(request)
        return WordPressTagEnsureResponse(
            schema_version="1.0",
            slug_to_id={"ai": 31},
        )

    def _publish(request, settings, ctx):
        publish_calls.append((request, settings))
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=request.file_id,
            status="published",
            post_id=321,
            post_url="https://example.com/briefings/ai-commerce-across-reports/",
        )

    result = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        ensure_taxonomy_terms_fn=_ensure_taxonomy,
        ensure_tags_fn=_ensure_tags,
        sleep_fn=lambda seconds: None,
    )

    publish_request, publish_settings = publish_calls[0]
    assert result.status == "published"
    assert result.target_post_type == "ml_briefing"
    assert result.target_slug == "ai-commerce-across-reports"
    assert result.category_slugs == ["retail"]
    assert result.tag_slugs == ["ai"]
    assert result.taxonomy_term_slugs == {
        "ml_publisher": ["publisher-a", "publisher-b"]
    }
    assert publish_settings.wp.post_type == "ml_briefing"
    assert publish_request.slug == "ai-commerce-across-reports"
    assert publish_request.resolved_terms.category_ids == [11]
    assert publish_request.resolved_terms.tag_ids == [31]
    assert publish_request.resolved_terms.taxonomy_terms == {"ml_publisher": [21, 22]}
    assert [call.taxonomy_rest_base for call in taxonomy_calls] == [
        "categories",
        "ml_publisher",
    ]
    assert tag_calls[0].tags == ["ai"]


def test_publish_cross_report_package_rejects_briefing_url_outside_briefings_section(
    tmp_path,
    run_context,
) -> None:
    def _lookup(request, ctx):
        return WordPressPostLookupResponse(
            schema_version="1.0",
            found=False,
            post_id=None,
            link=None,
        )

    def _publish(request, settings, ctx):
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=request.file_id,
            status="published",
            post_id=321,
            post_url="https://example.com/reports/ai-commerce-across-reports/",
        )

    result = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        ensure_taxonomy_terms_fn=lambda request, ctx: WordPressTaxonomyEnsureResponse(
            schema_version="1.0",
            slug_to_id={"retail": 11, "publisher-a": 21, "publisher-b": 22},
        ),
        ensure_tags_fn=lambda request, ctx: WordPressTagEnsureResponse(
            schema_version="1.0",
            slug_to_id={"ai": 31},
        ),
        sleep_fn=lambda seconds: None,
    )

    assert result.status == "error"
    assert result.error_code == "cross_report_briefing_url_mismatch"
    assert result.post_id is None


def test_publish_cross_report_package_existing_post_with_changed_checksum_errors(
    tmp_path,
    run_context,
) -> None:
    publish_calls = []

    def _lookup(request, ctx):
        return WordPressPostLookupResponse(
            schema_version="1.0",
            found=True,
            post_id=456,
            link="https://example.com/existing-cross-report",
        )

    def _publish(request, settings, ctx):
        publish_calls.append(request)
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=request.file_id,
            status="published",
            post_id=789,
            post_url="https://example.com/updated-cross-report",
        )

    result = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        sleep_fn=lambda seconds: None,
    )

    assert result.status == "error"
    assert result.error_code == "cross_report_publish_existing_post_checksum_mismatch"
    assert result.post_id is None
    assert publish_calls == []


def test_publish_cross_report_package_logs_idempotency_reuse(
    tmp_path,
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    def _lookup(request, ctx):
        return WordPressPostLookupResponse(
            schema_version="1.0",
            found=False,
            post_id=None,
            link=None,
        )

    def _publish(request, settings, ctx):
        return PublishOutcome(
            schema_version="1.0",
            html_path=request.html_path,
            file_id=request.file_id,
            status="published",
            post_id=123,
            post_url="https://example.com/briefings/ai-commerce-across-reports/",
        )

    caplog.set_level(logging.INFO, logger="market_lense.publish_orchestrator")
    publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        ensure_taxonomy_terms_fn=_ensure_cross_report_taxonomy,
        ensure_tags_fn=_ensure_cross_report_tags,
        sleep_fn=lambda seconds: None,
    )
    reused = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        ensure_taxonomy_terms_fn=_ensure_cross_report_taxonomy,
        ensure_tags_fn=_ensure_cross_report_tags,
        sleep_fn=lambda seconds: None,
    )

    assert reused.idempotency_reused is True
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.publish_orchestrator"
    ]
    assert_logs_have_required_fields(events)
    reuse_events = [
        event
        for event in events
        if event["event"] == "cross_report_publish_idempotency_reused"
    ]
    assert reuse_events[0]["fields"]["package_id"] == "cross-report:analysis-ai"
