from __future__ import annotations

from types import SimpleNamespace

from src.contracts.publish import PublishQueueRequest
from src.contracts.run_context import RunContext
from src.orchestrators import publish_queue_orchestrator as orch
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
        PublishQueueRequest(schema_version="1.0", output_dir="out", state_db="state.sqlite"),
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
