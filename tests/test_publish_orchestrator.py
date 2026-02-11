from __future__ import annotations

import json
from pathlib import Path

from src.contracts.publish import PublishOutcome
from src.contracts.state import StatePublishCheckRequest, StateRecordRequest
from src.contracts.wordpress import WordPressPostLookupResponse
from src.orchestrators import publish_orchestrator as orch
from src.services.state_service import get_publish, record


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

    publish_calls: list[str] = []

    def _publish(req, current_settings, ctx):
        publish_calls.append(req.file_id or "")
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
    assert publish_calls == ["file123"]
    publish_row = get_publish(
        StatePublishCheckRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id="file123",
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
        ),
        run_context,
    )
    assert publish_row is None
