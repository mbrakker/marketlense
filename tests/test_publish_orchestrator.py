from __future__ import annotations

import json
import logging
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
from tests.support.fakes import FakeHttpResponse


def _write_html(output_dir: str, name: str, body: str) -> Path:
    html_path = Path(output_dir) / name
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text(
        f"<html><head><title>Report</title></head><body>{body}</body></html>",
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
        == 3
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
