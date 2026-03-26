from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from src.contracts.publish import PublishQueueRequest
from src.contracts.report_store import ReportMetadataUpsertRequest
from src.contracts.run_context import RunContext
from src.orchestrators import publish_queue_orchestrator as orch
from src.services.report_store_service import upsert_metadata
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_build_publish_queue_snapshot(monkeypatch) -> None:
    html_paths = ["out/a.html", "out/b.html", "out/c.html"]
    monkeypatch.setattr(orch, "list_html", lambda req, ctx: SimpleNamespace(html_paths=html_paths))

    def _read_text(req, ctx):
        if req.path.endswith("a.html"):
            return SimpleNamespace(content='<meta name="drive-file-id" content="file_a">')
        if req.path.endswith("b.html"):
            return SimpleNamespace(content="no file id marker")
        raise AppError(code="file_not_found", message="missing", retryable=False)

    monkeypatch.setattr(orch, "read_text", _read_text)
    monkeypatch.setattr(
        orch,
        "get_publish",
        lambda req, ctx: SimpleNamespace(wp_post_id=7, wp_post_url="https://example.com/post") if req.file_id == "file_a" else None,
    )

    response = orch.build_publish_queue_snapshot(
        PublishQueueRequest(
            schema_version="1.0",
            output_dir="out",
            state_db="state.sqlite",
            post_type="ml_report",
        ),
        _ctx(),
    )

    assert len(response.items) == 2
    first = response.items[0]
    assert first.file_id == "file_a"
    assert first.published is True
    assert first.wp_post_id == 7
    second = response.items[1]
    assert second.file_id == ""
    assert second.published is False


def test_build_publish_queue_snapshot_prefers_reports_db_mapping(
    monkeypatch, tmp_path: Path
) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    html_paths = [str(output_dir / "a.html"), str(output_dir / "b.html")]
    monkeypatch.setattr(
        orch, "list_html", lambda req, ctx: SimpleNamespace(html_paths=html_paths)
    )
    reports_db = str(tmp_path / "reports.sqlite")
    upsert_metadata(
        ReportMetadataUpsertRequest(
            schema_version="1.1",
            db_path=reports_db,
            file_id="file_a",
            title="Report A",
            file_name="a.pdf",
            publisher=None,
            taxonomy=[],
            categories=[],
            region=None,
            time_period=None,
            source_url=None,
            html_path=html_paths[0],
            md5="md5-a",
            page_count=None,
            contents_page_number=0,
            pdf_metadata={},
            analysis_mode="vector_store",
            vector_store_id=None,
            evidence_pack_paths={},
        ),
        _ctx(),
    )
    read_calls: list[str] = []

    def _read_text(req, ctx):
        read_calls.append(req.path)
        if req.path == html_paths[1]:
            return SimpleNamespace(content="Drive fileId: file_b")
        raise AppError(code="file_not_found", message="missing", retryable=False)

    monkeypatch.setattr(orch, "read_text", _read_text)
    monkeypatch.setattr(
        orch,
        "get_publish",
        lambda req, ctx: SimpleNamespace(wp_post_id=11, wp_post_url="https://example.com/a") if req.file_id == "file_a" else None,
    )

    response = orch.build_publish_queue_snapshot(
        PublishQueueRequest(
            schema_version="1.0",
            output_dir=str(output_dir),
            state_db="state.sqlite",
            reports_db=reports_db,
            post_type="ml_report",
        ),
        _ctx(),
    )

    assert len(response.items) == 2
    assert [item.file_id for item in response.items] == ["file_a", "file_b"]
    assert read_calls == [html_paths[1]]
