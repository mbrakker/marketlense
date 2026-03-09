from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from src.contracts.publish import PublishOutcome
from src.contracts.state import StatePublishCheckRequest, StateRecordRequest
from src.contracts.wordpress import WordPressPostLookupResponse
from src.orchestrators import publish_orchestrator as orch
from src.services.state_service import get_publish, record
from src.utils.errors import AppError


def test_publish_runs_when_processed(publish_settings_factory, run_context, monkeypatch) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text("<html><body>Drive fileId: file123</body></html>", encoding="utf-8")

    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            md5="md5",
        ),
        run_context,
    )

    publish_calls: list[tuple[str, str | None]] = []

    def _publish(req, current_settings, ctx):
        publish_calls.append((req.file_id or "", req.html_text))
        return PublishOutcome(
            schema_version="1.0",
            html_path=req.html_path,
            file_id=req.file_id,
            status="published",
            post_id=10,
            post_url="https://example.com/post/10",
        )

    monkeypatch.setattr(
        orch,
        "find_post_by_file_id",
        lambda req, ctx: WordPressPostLookupResponse(schema_version="1.0", found=False),
    )
    monkeypatch.setattr(orch, "publish_html", _publish)

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file123"
    assert len(publish_calls) == 1
    assert publish_calls[0][0] == "file123"
    assert publish_calls[0][1] is not None
    assert "Drive fileId: file123" in (publish_calls[0][1] or "")
    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type=settings.wp.post_type,
        ),
        run_context,
    )
    assert publish_row is not None
    assert publish_row.wp_post_id == 10
    assert publish_row.wp_post_url == "https://example.com/post/10"


def test_publish_blocks_when_validation_fails(publish_settings_factory, run_context, monkeypatch) -> None:
    settings = publish_settings_factory(validation_policy="block")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text("<html><body>Drive fileId: file123</body></html>", encoding="utf-8")

    validation_path = Path(settings.output_dir) / "report" / "report_analysis" / "validation.json"
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

    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            md5="md5",
        ),
        run_context,
    )

    find_calls: list[str] = []
    publish_calls: list[str] = []
    monkeypatch.setattr(
        orch,
        "find_post_by_file_id",
        lambda req, ctx: find_calls.append(req.file_id)
        or WordPressPostLookupResponse(schema_version="1.0", found=False),
    )
    monkeypatch.setattr(
        orch,
        "publish_html",
        lambda req, current_settings, ctx: publish_calls.append(req.file_id or ""),
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "error"
    assert results[0].error == "validation_failed"
    assert results[0].validation_status == "fail"
    assert results[0].validation_issues == ["bad data"]
    assert find_calls == []
    assert publish_calls == []
    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type=settings.wp.post_type,
        ),
        run_context,
    )
    assert publish_row is None


def test_publish_prefers_reports_db_file_id_mapping(publish_settings_factory, run_context, monkeypatch) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text("<html><body>No explicit file marker</body></html>", encoding="utf-8")

    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file_from_db",
            md5="md5",
        ),
        run_context,
    )

    monkeypatch.setattr(
        orch,
        "list_metadata",
        lambda req, ctx: SimpleNamespace(
            records=[SimpleNamespace(file_id="file_from_db", html_path=str(html_path), updated_at=100)]
        ),
    )
    monkeypatch.setattr(
        orch,
        "extract_file_id",
        lambda _html: (_ for _ in ()).throw(AssertionError("HTML parsing should not run when DB mapping is present")),
    )
    monkeypatch.setattr(
        orch,
        "find_post_by_file_id",
        lambda req, ctx: WordPressPostLookupResponse(schema_version="1.0", found=False),
    )
    monkeypatch.setattr(
        orch,
        "publish_html",
        lambda req, current_settings, ctx: (
            (_ for _ in ()).throw(AssertionError("html_text should stay empty for DB-mapped items"))
            if req.html_text is not None
            else PublishOutcome(
                schema_version="1.0",
                html_path=req.html_path,
                file_id=req.file_id,
                status="published",
                post_id=77,
                post_url="https://example.com/post/77",
            )
        ),
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file_from_db"


def test_publish_retries_retryable_app_error(publish_settings_factory, run_context, monkeypatch) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text("<html><body>Drive fileId: file123</body></html>", encoding="utf-8")

    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            md5="md5",
        ),
        run_context,
    )

    calls = {"count": 0}
    sleep_calls: list[int] = []
    monkeypatch.setattr(
        orch,
        "find_post_by_file_id",
        lambda req, ctx: WordPressPostLookupResponse(schema_version="1.0", found=False),
    )

    def _publish(req, current_settings, ctx):
        calls["count"] += 1
        if calls["count"] < 3:
            raise AppError(code="wordpress_http_error", message="retry", retryable=True)
        return PublishOutcome(
            schema_version="1.0",
            html_path=req.html_path,
            file_id=req.file_id,
            status="published",
            post_id=33,
            post_url="https://example.com/post/33",
        )

    monkeypatch.setattr(orch, "publish_html", _publish)
    monkeypatch.setattr(orch.time, "sleep", lambda seconds: sleep_calls.append(int(seconds)))

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "published"
    assert results[0].file_id == "file123"
    assert calls["count"] == 3
    assert sleep_calls == [1, 2]


def test_publish_ignores_publish_state_for_different_post_type(
    publish_settings_factory, run_context, monkeypatch
) -> None:
    settings = publish_settings_factory(validation_policy="warn")
    html_path = Path(settings.output_dir) / "report.html"
    html_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.write_text("<html><body>Drive fileId: file123</body></html>", encoding="utf-8")

    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            md5="md5",
        ),
        run_context,
    )

    from src.services.state_service import record_publish
    from src.contracts.state import StatePublishRecordRequest

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

    monkeypatch.setattr(
        orch,
        "find_post_by_file_id",
        lambda req, ctx: WordPressPostLookupResponse(schema_version="1.0", found=False),
    )
    monkeypatch.setattr(
        orch,
        "publish_html",
        lambda req, current_settings, ctx: PublishOutcome(
            schema_version="1.0",
            html_path=req.html_path,
            file_id=req.file_id,
            status="published",
            post_id=101,
            post_url="https://example.com/reports/101",
        ),
    )

    results = orch.run_publish(settings, limit=1)

    assert len(results) == 1
    assert results[0].status == "published"
    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
            post_type=settings.wp.post_type,
        ),
        run_context,
    )
    assert publish_row is not None
    assert publish_row.wp_post_id == 101
    assert publish_row.post_type == settings.wp.post_type
