from __future__ import annotations

from types import SimpleNamespace

import logging
import json

from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportPublishPackage,
)
from src.contracts.publish import PublishOutcome
from src.contracts.wordpress import WordPressPostLookupResponse
from src.orchestrators.publish_orchestrator import publish_cross_report_package


def _package(tmp_path) -> CrossReportPublishPackage:
    return CrossReportPublishPackage(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        package_id="cross-report:analysis-ai",
        file_id="cross-report:analysis-ai",
        target_route="wordpress:ml_report",
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
    assert result.target_route == "wordpress:ml_report"
    assert result.idempotency_reused is False
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
            post_url="https://example.com/cross-report",
        )

    first = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        sleep_fn=lambda seconds: None,
    )
    second = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        sleep_fn=lambda seconds: None,
    )

    assert first.status == "published"
    assert first.post_id == 123
    assert second.idempotency_reused is True
    assert second.post_url == "https://example.com/cross-report"
    assert len(publish_calls) == 1
    assert publish_calls[0].html_snapshot is not None


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
            post_url="https://example.com/cross-report",
        )

    caplog.set_level(logging.INFO, logger="market_lense.publish_orchestrator")
    publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
        sleep_fn=lambda seconds: None,
    )
    reused = publish_cross_report_package(
        _package(tmp_path),
        _settings(tmp_path),
        run_context,
        dry_run=False,
        publish_html_fn=_publish,
        find_post_by_file_id_fn=_lookup,
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
