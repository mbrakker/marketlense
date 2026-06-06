from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import replace
from pathlib import Path

from src.contracts.report_store import ReportMetadataUpsertRequest
from src.contracts.state import (
    StatePublishCheckRequest,
    StatePublishRecordRequest,
    StateRecordRequest,
)
from src.orchestrators import publish_orchestrator as orch
from src.orchestrators import retry_orchestrator
from src.services.report_store_service import upsert_metadata
from src.services.state_service import get_publish, record, record_publish
from tests.support.fakes import FakeHttpResponse, RecordedHttpRequest


def _publish_entity_metadata_script(
    *,
    entity_type: str = "report",
    source_artifact_id: str = "file123",
    canonical_route_intent: str = "wordpress:ml_report",
    publish_eligible: bool = True,
) -> str:
    return (
        '<script type="application/json" '
        'data-market-lense-publish-entity="true">'
        + json.dumps(
            {
                "schema_version": "1.0",
                "entity_type": entity_type,
                "source_artifact_id": source_artifact_id,
                "canonical_route_intent": canonical_route_intent,
                "publish_eligible": publish_eligible,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        + "</script>"
    )


def _write_html(
    output_dir: str,
    name: str,
    body: str,
    *,
    entity_type: str = "report",
    canonical_route_intent: str = "wordpress:ml_report",
    source_artifact_id: str = "file123",
    include_entity_metadata: bool = True,
) -> Path:
    html_path = Path(output_dir) / name
    html_path.parent.mkdir(parents=True, exist_ok=True)
    metadata = (
        _publish_entity_metadata_script(
            entity_type=entity_type,
            source_artifact_id=source_artifact_id,
            canonical_route_intent=canonical_route_intent,
        )
        if include_entity_metadata
        else ""
    )
    html_path.write_text(
        f"<html><head><title>Report</title>{metadata}</head><body>{body}</body></html>",
        encoding="utf-8",
    )
    return html_path


def _record_processed(state_db: str, file_id: str, run_context) -> None:
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=state_db,
            file_id=file_id,
            md5="md5",
        ),
        run_context,
    )


def _seed_report_metadata(
    reports_db: str, html_path: str, file_id: str, run_context
) -> None:
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=reports_db,
            file_id=file_id,
            title="Report",
            file_name="report.pdf",
            publisher=None,
            taxonomy=[],
            categories=[],
            region=None,
            time_period=None,
            source_url=None,
            html_path=html_path,
            md5="md5",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )


def _json_events(caplog, logger_name: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for log_record in caplog.records:
        if log_record.name != logger_name:
            continue
        try:
            payload = json.loads(log_record.getMessage())
        except json.JSONDecodeError:
            continue
        if isinstance(payload, dict):
            events.append(payload)
    return events


def test_publish_runs_when_processed(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=1)

    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type=settings.wp.post_type,
        ),
        run_context,
    )
    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file123"
    assert "Drive fileId: file123" in post_call.json_data["content"]
    assert publish_row is not None
    assert publish_row.wp_post_id == 10
    assert publish_row.wp_post_url == "https://example.com/post/10"


def test_publish_routes_report_by_embedded_entity_metadata(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    settings = replace(settings, wp=replace(settings.wp, post_type="posts"))
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={
            "id": 10,
            "link": "https://example.com/reports/10",
            "status": "publish",
        },
    )

    results = orch.run_publish(settings, limit=1)

    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type="ml_report",
        ),
        run_context,
    )
    assert len(results) == 1
    assert results[0].status == "published"
    assert publish_row is not None
    assert publish_row.post_type == "ml_report"
    assert (
        wordpress_http.calls_for("POST", "https://example.com/wp-json/wp/v2/posts")
        == []
    )


def test_publish_routes_signal_by_embedded_entity_metadata(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(
        settings.output_dir,
        "signal.html",
        "Drive fileId: signal:checkout-trust",
        entity_type="signal",
        canonical_route_intent="wordpress:ml_signal",
        source_artifact_id="signal:checkout-trust",
    )
    _record_processed(settings.state_db, "signal:checkout-trust", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_signal",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_signal",
        status_code=201,
        payload={
            "id": 15,
            "link": "https://example.com/signals/checkout-trust/",
            "status": "publish",
        },
    )

    results = orch.run_publish(settings, limit=1)

    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="signal:checkout-trust",
            post_type="ml_signal",
        ),
        run_context,
    )
    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].post_url == "https://example.com/signals/checkout-trust/"
    assert publish_row is not None
    assert publish_row.post_type == "ml_signal"


def test_publish_uses_explicit_html_paths_over_output_listing(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "aaa-first.html", "Drive fileId: first")
    target = _write_html(settings.output_dir, "zzz-target.html", "Drive fileId: target")
    _record_processed(settings.state_db, "target", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=1, html_paths=[str(target)])

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "target"


def test_publish_auto_discovery_skips_unowned_html_before_limit(
    publish_settings_factory, run_context, wordpress_http, caplog
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(
        settings.output_dir,
        "aaa-enterprise-prototype.html",
        "<p>Design prototype only</p>",
        include_entity_metadata=False,
    )
    _write_html(settings.output_dir, "zzz-report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    with caplog.at_level(logging.INFO, logger="market_lense.publish_orchestrator"):
        results = orch.run_publish(settings, limit=1)

    events = _json_events(caplog, "market_lense.publish_orchestrator")
    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file123"
    assert any(
        event.get("event") == "publish_non_entity_html_skipped" for event in events
    )


def test_publish_auto_discovery_orders_reports_by_metadata_updated_at_before_limit(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    old_html = _write_html(
        settings.output_dir,
        "aaa-old-report.html",
        "Drive fileId: old-file",
        source_artifact_id="old-file",
    )
    new_html = _write_html(
        settings.output_dir,
        "zzz-new-report.html",
        "Drive fileId: new-file",
        source_artifact_id="new-file",
    )
    _record_processed(settings.state_db, "old-file", run_context)
    _record_processed(settings.state_db, "new-file", run_context)
    _seed_report_metadata(settings.reports_db, str(old_html), "old-file", run_context)
    _seed_report_metadata(settings.reports_db, str(new_html), "new-file", run_context)
    with sqlite3.connect(settings.reports_db) as conn:
        conn.execute("UPDATE reports SET updated_at = 100 WHERE file_id = ?", ("old-file",))
        conn.execute("UPDATE reports SET updated_at = 200 WHERE file_id = ?", ("new-file",))
        conn.commit()
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "new-file"


def test_publish_reuses_idempotent_outcome_without_second_post(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    first = orch.run_publish(settings, limit=1)
    second = orch.run_publish(settings, limit=1)

    assert first[0].status == "published"
    assert second[0].status == "published"
    assert second[0].post_id == 10
    assert second[0].post_url == "https://example.com/post/10"
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )


def test_publish_limit_applies_to_attempted_items_when_first_item_errors(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "first.html", "Drive fileId: first123")
    _write_html(settings.output_dir, "second.html", "Drive fileId: second123")
    _record_processed(settings.state_db, "first123", run_context)
    _record_processed(settings.state_db, "second123", run_context)
    wordpress_http.add(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        RuntimeError("ssl certificate verify failed"),
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].file_id == "first123"
    assert results[0].status == "error"
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 2
    )


def test_publish_blocks_when_validation_fails(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="block")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    validation_path = (
        Path(settings.output_dir) / "report" / "report_analysis" / "validation.json"
    )
    validation_path.parent.mkdir(parents=True, exist_ok=True)
    validation_path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "status": "fail",
                "severity": "error",
                "issues": [
                    {
                        "schema_version": "1.0",
                        "message": "bad data",
                        "severity": "error",
                        "affected_section": "insights",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _record_processed(settings.state_db, "file123", run_context)

    results = orch.run_publish(settings, limit=1)

    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type=settings.wp.post_type,
        ),
        run_context,
    )
    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].error == "validation_failed"
    assert results[0].validation_status == "fail"
    assert results[0].validation_issues == ["bad data"]
    assert wordpress_http.calls == []
    assert publish_row is None


def test_publish_missing_entity_metadata_fails_before_wordpress(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(
        settings.output_dir,
        "report.html",
        "Drive fileId: file123",
        include_entity_metadata=False,
    )
    _record_processed(settings.state_db, "file123", run_context)

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].error == "publish_entity_metadata_missing"
    assert wordpress_http.calls == []


def test_publish_unknown_entity_metadata_fails_before_wordpress(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(
        settings.output_dir,
        "unknown.html",
        "Drive fileId: entity123",
        entity_type="unknown",
        canonical_route_intent="wordpress:ml_unknown",
        source_artifact_id="entity123",
    )
    _record_processed(settings.state_db, "entity123", run_context)

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].error == "publish_entity_metadata_unsupported"
    assert wordpress_http.calls == []


def test_publish_mismatched_entity_metadata_fails_before_wordpress(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(
        settings.output_dir,
        "mismatch.html",
        "Drive fileId: file123",
        entity_type="report",
        canonical_route_intent="wordpress:ml_signal",
        source_artifact_id="file123",
    )
    _record_processed(settings.state_db, "file123", run_context)

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].error == "publish_entity_metadata_mismatch"
    assert wordpress_http.calls == []


def test_publish_prefers_reports_db_file_id_mapping(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = _write_html(
        settings.output_dir, "report.html", "No explicit file marker"
    )
    _record_processed(settings.state_db, "file_from_db", run_context)
    _seed_report_metadata(
        settings.reports_db, str(html_path), "file_from_db", run_context
    )
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 77, "link": "https://example.com/post/77", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=1)
    post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file_from_db"
    assert "Drive fileId: file_from_db" in post_call.json_data["content"]


def test_publish_reuses_preloaded_html_snapshot_after_preflight_read(
    publish_settings_factory,
    run_context,
    wordpress_http,
    external_boundary_mocks_only,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 44, "link": "https://example.com/post/44", "status": "publish"},
    )

    real_get_outcome = orch.idempotency_service.get_outcome

    def _delete_html_then_lookup(request, ctx):
        html_path.unlink(missing_ok=True)
        return real_get_outcome(request, ctx)

    external_boundary_mocks_only.setattr(
        orch.idempotency_service,
        "get_outcome",
        _delete_html_then_lookup,
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file123"
    assert not html_path.exists()


def test_publish_uses_canonical_validation_json_over_regen_snapshots(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="block")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    report_analysis_dir = Path(settings.output_dir) / "report" / "report_analysis"
    report_analysis_dir.mkdir(parents=True, exist_ok=True)
    (report_analysis_dir / "validation.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "status": "pass",
                "severity": "pass",
                "issues": [],
            }
        ),
        encoding="utf-8",
    )
    (report_analysis_dir / "validation_regen_attempt_1.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "status": "fail",
                "severity": "error",
                "issues": [
                    {
                        "schema_version": "1.0",
                        "message": "stale attempt failure",
                        "severity": "error",
                        "affected_section": "summary",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 88, "link": "https://example.com/post/88", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].validation_status == "pass"
    assert results[0].validation_issues == []
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )


def test_publish_batches_preflight_and_term_resolution(
    publish_settings_factory,
    run_context,
    wordpress_http,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn", ssl_verify=False)
    first_html = _write_html(settings.output_dir, "first.html", "Drive fileId: file123")
    second_html = _write_html(
        settings.output_dir, "second.html", "Drive fileId: file456"
    )
    _record_processed(settings.state_db, "file123", run_context)
    _record_processed(settings.state_db, "file456", run_context)
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=settings.reports_db,
            file_id="file123",
            title="First",
            file_name="first.pdf",
            publisher="WARC",
            taxonomy=["shared-tag", "new-tag"],
            categories=["digital_payments", "retail_media"],
            region=None,
            time_period=None,
            source_url=None,
            html_path=str(first_html),
            md5="md5",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=settings.reports_db,
            file_id="file456",
            title="Second",
            file_name="second.pdf",
            publisher="WARC",
            taxonomy=["shared-tag", "new-tag"],
            categories=["digital_payments", "retail_media"],
            region=None,
            time_period=None,
            source_url=None,
            html_path=str(second_html),
            md5="md5",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )

    def _lookup_posts(call: RecordedHttpRequest) -> FakeHttpResponse:
        params = call.params or {}
        search = str(params.get("search") or "")
        if "file123" in search:
            return FakeHttpResponse.from_payload(
                status_code=200,
                payload=[
                    {
                        "id": 501,
                        "link": "https://example.com/post/501",
                        "content": {"rendered": "Drive fileId: file123"},
                    }
                ],
            )
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _lookup_categories(call: RecordedHttpRequest) -> FakeHttpResponse:
        slug = str((call.params or {}).get("slug") or "")
        if slug == "digital_payments":
            return FakeHttpResponse.from_payload(status_code=200, payload=[{"id": 11}])
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _create_categories(call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = call.json_data or {}
        if payload.get("slug") == "retail_media":
            return FakeHttpResponse.from_payload(status_code=201, payload={"id": 12})
        raise AssertionError(f"unexpected category payload: {payload}")

    def _lookup_publishers(call: RecordedHttpRequest) -> FakeHttpResponse:
        _ = call
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _create_publishers(call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = call.json_data or {}
        if payload.get("slug") == "warc":
            return FakeHttpResponse.from_payload(status_code=201, payload={"id": 22})
        raise AssertionError(f"unexpected publisher payload: {payload}")

    def _lookup_tags(call: RecordedHttpRequest) -> FakeHttpResponse:
        slug = str((call.params or {}).get("slug") or "")
        if slug == "shared-tag":
            return FakeHttpResponse.from_payload(status_code=200, payload=[{"id": 31}])
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _create_tags(call: RecordedHttpRequest) -> FakeHttpResponse:
        payload = call.json_data or {}
        if payload.get("slug") == "new-tag":
            return FakeHttpResponse.from_payload(status_code=201, payload={"id": 32})
        raise AssertionError(f"unexpected tag payload: {payload}")

    caplog.set_level(logging.INFO)
    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_report", _lookup_posts
    )
    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/categories", _lookup_categories
    )
    wordpress_http.add(
        "POST", "https://example.com/wp-json/wp/v2/categories", _create_categories
    )
    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_publisher", _lookup_publishers
    )
    wordpress_http.add(
        "POST", "https://example.com/wp-json/wp/v2/ml_publisher", _create_publishers
    )
    wordpress_http.add("GET", "https://example.com/wp-json/wp/v2/tags", _lookup_tags)
    wordpress_http.add("POST", "https://example.com/wp-json/wp/v2/tags", _create_tags)
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 77, "link": "https://example.com/post/77", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=2, ctx=run_context)

    first_publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type=settings.wp.post_type,
        ),
        run_context,
    )
    second_post_call = wordpress_http.calls_for(
        "POST", "https://example.com/wp-json/wp/v2/ml_report"
    )[0]
    events = _json_events(caplog, orch.logger.name)
    assert [result.status for result in results] == ["skipped", "published"]
    assert results[0].error == "already_exists"
    assert results[0].post_id == 501
    assert results[1].file_id == "file456"
    assert second_post_call.json_data["categories"] == [11, 12]
    assert second_post_call.json_data["tags"] == [31, 32]
    assert second_post_call.json_data["ml_publisher"] == [22]
    assert first_publish_row is not None
    assert first_publish_row.wp_post_id == 501
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/categories"
            )
        )
        == 2
    )
    assert (
        len(wordpress_http.calls_for("GET", "https://example.com/wp-json/wp/v2/tags"))
        == 2
    )
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_publisher"
            )
        )
        == 1
    )
    assert any(event.get("event") == "publish_preflight_complete" for event in events)
    assert_logs_have_required_fields(events)


def test_publish_preflight_term_batch_failure_does_not_block_other_files(
    publish_settings_factory,
    run_context,
    wordpress_http,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    ok_html = _write_html(settings.output_dir, "ok.html", "Drive fileId: file-ok")
    bad_html = _write_html(settings.output_dir, "bad.html", "Drive fileId: file-bad")
    _record_processed(settings.state_db, "file-ok", run_context)
    _record_processed(settings.state_db, "file-bad", run_context)
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=settings.reports_db,
            file_id="file-ok",
            title="OK",
            file_name="ok.pdf",
            publisher=None,
            taxonomy=[],
            categories=[],
            region=None,
            time_period=None,
            source_url=None,
            html_path=str(ok_html),
            md5="md5",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=settings.reports_db,
            file_id="file-bad",
            title="BAD",
            file_name="bad.pdf",
            publisher=None,
            taxonomy=["broken-tag"],
            categories=[],
            region=None,
            time_period=None,
            source_url=None,
            html_path=str(bad_html),
            md5="md5",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        run_context,
    )

    def _lookup_posts(_call: RecordedHttpRequest) -> FakeHttpResponse:
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    def _lookup_tags(call: RecordedHttpRequest) -> FakeHttpResponse:
        slug = str((call.params or {}).get("slug") or "")
        if slug == "broken-tag":
            return FakeHttpResponse.from_payload(
                status_code=503,
                payload={"message": "retry"},
            )
        return FakeHttpResponse.from_payload(status_code=200, payload=[])

    wordpress_http.add(
        "GET", "https://example.com/wp-json/wp/v2/ml_report", _lookup_posts
    )
    wordpress_http.add("GET", "https://example.com/wp-json/wp/v2/tags", _lookup_tags)
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 88, "link": "https://example.com/post/88", "status": "publish"},
    )

    results = orch.run_publish(settings, limit=2, ctx=run_context)

    assert [result.status for result in results] == ["error", "published"]
    assert results[0].file_id == "file-bad"
    assert results[1].file_id == "file-ok"
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )


def test_publish_retries_retryable_app_error(
    publish_settings_factory,
    run_context,
    wordpress_http,
    caplog,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        FakeHttpResponse.from_payload(status_code=503, payload={"message": "retry"}),
        FakeHttpResponse.from_payload(status_code=503, payload={"message": "retry"}),
        FakeHttpResponse.from_payload(
            status_code=201,
            payload={
                "id": 33,
                "link": "https://example.com/post/33",
                "status": "publish",
            },
        ),
    )
    sleep_calls: list[int] = []
    caplog.set_level(logging.INFO)
    external_boundary_mocks_only.setattr(
        retry_orchestrator.random, "uniform", lambda _a, _b: 0.0
    )
    external_boundary_mocks_only.setattr(
        orch.time, "sleep", lambda seconds: sleep_calls.append(int(seconds))
    )

    results = orch.run_publish(settings, limit=1)

    retry_logs = [
        record
        for record in caplog.records
        if '"event": "publish_retry"' in record.message
    ]
    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file123"
    assert (
        len(
            wordpress_http.calls_for(
                "GET", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 1
    )
    assert (
        len(
            wordpress_http.calls_for(
                "POST", "https://example.com/wp-json/wp/v2/ml_report"
            )
        )
        == 3
    )
    assert sleep_calls == [1, 2]
    assert len(retry_logs) == 2
    assert_logs_have_required_fields(caplog.records)


def test_publish_ignores_publish_state_for_different_post_type(
    publish_settings_factory, run_context, wordpress_http
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    record_publish(
        StatePublishRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            md5="md5",
            wp_post_id=99,
            wp_post_url="https://example.com/post/99",
            post_type="posts",
        ),
        run_context,
    )
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={
            "id": 101,
            "link": "https://example.com/reports/101",
            "status": "publish",
        },
    )

    results = orch.run_publish(settings, limit=1)

    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type=settings.wp.post_type,
        ),
        run_context,
    )
    assert len(results) == 1
    assert results[0].status == "published"
    assert publish_row is not None
    assert publish_row.wp_post_id == 101
    assert publish_row.post_type == settings.wp.post_type


def test_publish_uses_provided_run_context_for_logs(
    publish_settings_factory,
    run_context,
    wordpress_http,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    _write_html(settings.output_dir, "report.html", "Drive fileId: file123")
    _record_processed(settings.state_db, "file123", run_context)
    wordpress_http.add_json(
        "GET",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=200,
        payload=[],
    )
    wordpress_http.add_json(
        "POST",
        "https://example.com/wp-json/wp/v2/ml_report",
        status_code=201,
        payload={"id": 10, "link": "https://example.com/post/10", "status": "publish"},
    )

    caplog.set_level(logging.INFO, logger=orch.logger.name)
    results = orch.run_publish(settings, limit=1, ctx=run_context)

    events = _json_events(caplog, orch.logger.name)
    assert len(results) == 1
    assert results[0].status == "published"
    assert_logs_have_required_fields(events)
    assert any(event.get("event") == "publish_start" for event in events)
    assert any(event.get("event") == "publish_complete" for event in events)
    assert all(event.get("run_id") == run_context.run_id for event in events)
