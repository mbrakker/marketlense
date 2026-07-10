from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from src.contracts.browser_download import (
    BrowserDownloadSessionReusePolicy,
    BrowserDownloadWarmWorkerPoolPolicy,
    BrowserReportDownloadRequest,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download import worker_pool
from src.services._browser_report_download.models import BrowserAgentRunResult
from src.services._browser_report_download.prompt import BrowserDownloadPromptBundle

from tests.test_browser_report_download_service.builders import _settings


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _prompt_bundle() -> BrowserDownloadPromptBundle:
    return BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/default",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user",
        task_prompt="download the report",
    )


def _batch_request(tmp_path: Path, *, publisher_scope: str = "example.com"):
    settings = replace(
        _settings(tmp_path),
        session_reuse_policy=BrowserDownloadSessionReusePolicy(
            schema_version="1.0",
            enabled=True,
            mode="same_publisher_batch",
            session_key="batch-key",
            publisher_scope=publisher_scope,
            ttl_seconds=180.0,
            base_dir=str(tmp_path / "session-reuse"),
            allow_cross_publisher=False,
        ),
        warm_worker_pool_policy=BrowserDownloadWarmWorkerPoolPolicy(
            schema_version="1.0",
            enabled=True,
            max_workers=1,
            max_runs_per_worker=2,
            max_memory_mb=256,
            idle_ttl_seconds=120.0,
            fallback_to_subprocess=True,
        ),
    )
    return BrowserReportDownloadRequest(
        schema_version="1.0",
        url=f"https://{publisher_scope}/reports/one",
        settings=settings,
        route_family_hint="browser_email_form",
    )


def test_warm_worker_pool_decision_requires_same_publisher_batch_session_reuse(
    tmp_path: Path,
) -> None:
    request = _batch_request(tmp_path)

    decision = worker_pool.resolve_warm_worker_pool_decision(
        request=request,
        normalized_url="https://example.com/reports/one",
    )

    assert decision.accepted is True
    assert decision.publisher_scope == "example.com"
    assert decision.pool_key_hash
    rejected = worker_pool.resolve_warm_worker_pool_decision(
        request=replace(
            request,
            settings=replace(
                request.settings,
                session_reuse_policy=replace(
                    request.settings.session_reuse_policy,
                    allow_cross_publisher=True,
                ),
            ),
        ),
        normalized_url="https://example.com/reports/one",
    )
    assert rejected.accepted is False
    assert rejected.rejection_reason == "cross_publisher_reuse_not_allowed"


class _FakeWorkerStdin:
    def __init__(self, process: "_FakeWorkerProcess") -> None:
        self._process = process
        self._buffer = ""

    def write(self, value: str) -> int:
        self._buffer += value
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._process.handle_command(json.loads(line))
        return len(value)

    def flush(self) -> None:
        return None


class _FakeWorkerProcess:
    _next_pid = 5000

    def __init__(self) -> None:
        type(self)._next_pid += 1
        self.pid = type(self)._next_pid
        self.stdin = _FakeWorkerStdin(self)
        self.terminated = False
        self.kill_count = 0

    def poll(self):
        return 0 if self.terminated else None

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.kill_count += 1
        self.terminated = True

    def wait(self, timeout: float | None = None) -> int:
        self.terminated = True
        return 0

    def handle_command(self, command: dict) -> None:
        response_path = Path(command["response_path"])
        response_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "ok",
                    "result": {
                        "schema_version": "1.0",
                        "raw_model_response": json.dumps(
                            {"route_kind": "pdf_download"}
                        ),
                        "final_page_url": "https://example.com/final",
                        "final_page_title": "Report",
                        "final_page_html": "",
                        "downloaded_files": [],
                        "attachment_paths": [],
                        "network_resource_urls": [],
                        "network_events": [],
                        "html_snapshot_path": "",
                        "screenshot_path": "",
                        "print_pdf_capture_path": "",
                        "print_pdf_capture_provenance": "",
                        "dialog_evidence": [],
                    },
                    "error": None,
                }
            ),
            encoding="utf-8",
        )


def test_warm_worker_pool_reuses_same_publisher_worker_and_restarts_after_run_limit(
    tmp_path: Path,
) -> None:
    created: list[_FakeWorkerProcess] = []
    now = {"value": 0.0}

    def _process_factory(*args, **kwargs):
        process = _FakeWorkerProcess()
        created.append(process)
        return process

    pool = worker_pool.BrowserWarmWorkerPool(
        process_factory=_process_factory,
        memory_reader=lambda pid: 128 * 1024 * 1024,
        monotonic_fn=lambda: now["value"],
    )
    request = _batch_request(tmp_path)

    first = pool.run(
        request=request,
        ctx=_ctx(),
        normalized_url="https://example.com/reports/one",
        execution_url="https://example.com/reports/one",
        download_dir=tmp_path / "downloads" / "one",
        prompt_bundle=_prompt_bundle(),
    )
    second = pool.run(
        request=request,
        ctx=_ctx(),
        normalized_url="https://example.com/reports/two",
        execution_url="https://example.com/reports/two",
        download_dir=tmp_path / "downloads" / "two",
        prompt_bundle=_prompt_bundle(),
    )
    third = pool.run(
        request=request,
        ctx=_ctx(),
        normalized_url="https://example.com/reports/three",
        execution_url="https://example.com/reports/three",
        download_dir=tmp_path / "downloads" / "three",
        prompt_bundle=_prompt_bundle(),
    )

    assert isinstance(first, BrowserAgentRunResult)
    assert second.final_page_url == "https://example.com/final"
    assert third.raw_model_response
    assert len(created) == 2
    assert created[0].terminated is True
    assert created[1].terminated is False
