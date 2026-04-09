from __future__ import annotations

import logging
from pathlib import Path

from src.contracts.ui_run_control import (
    ProcessLaunchResponse,
    ProcessOutputChunk,
    ProcessOutputReadResponse,
    ProcessPollResponse,
    ProcessTerminateResponse,
    UiRunCancelRequest,
    UiRunLaunchRequest,
    UiRunPollRequest,
    UiRunRecord,
    UiRunRecordWriteRequest,
)
from src.orchestrators import ui_run_control_orchestrator as orchestrator
from src.services.run_registry_service import (
    get_ui_run_record,
    write_ui_run_record,
)
from src.contracts.ui_run_control import UiRunRecordGetRequest
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="test_ui_run_control_orchestrator")


def _registry_path(tmp_path: Path) -> str:
    return str((tmp_path / "state" / "ui_runs.sqlite").resolve())


def _running_record(*, registry_path: str) -> UiRunRecord:
    return UiRunRecord(
        schema_version="1.0",
        run_id="run-1",
        run_type="ingest",
        display_name="Ingest",
        status="running",
        request_payload={"limit": 2},
        command=["python", "-m", "src.cli"],
        created_at_utc="2026-04-09T10:00:00+00:00",
        updated_at_utc="2026-04-09T10:01:00+00:00",
        started_at_utc="2026-04-09T10:01:00+00:00",
        output_path="out.log",
        request_path="request.json",
        pid=3210,
    )


def test_launch_ui_run_persists_record_and_request(
    tmp_path: Path,
    monkeypatch,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO)

    def _fake_launch_process(request, ctx):
        return ProcessLaunchResponse(
            schema_version="1.0",
            pid=4321,
            command=request.command,
            cwd=request.cwd,
            output_path=request.output_path,
            started_at_utc="2026-04-09T10:00:05+00:00",
        )

    monkeypatch.setattr(orchestrator, "launch_process", _fake_launch_process)

    response = orchestrator.launch_ui_run(
        UiRunLaunchRequest(
            schema_version="1.0",
            registry_path=_registry_path(tmp_path),
            workspace_root=str(tmp_path),
            run_type="publisher_discovery",
            display_name="Publisher discovery",
            request_payload={"insights_url": "https://example.com/insights"},
        ),
        _ctx(),
    )

    stored = get_ui_run_record(
        UiRunRecordGetRequest(
            schema_version="1.0",
            registry_path=_registry_path(tmp_path),
            run_id=response.record.run_id,
        ),
        _ctx(),
    ).record

    assert stored == response.record
    assert response.record.pid == 4321
    assert Path(response.record.request_path).exists()
    assert Path(response.record.output_path).parent.exists()
    assert_logs_have_required_fields(caplog.records)


def test_poll_ui_run_marks_unexpected_worker_exit_as_failed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = _registry_path(tmp_path)
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=registry_path,
            record=_running_record(registry_path=registry_path),
        ),
        _ctx(),
    )

    monkeypatch.setattr(
        orchestrator,
        "poll_process",
        lambda request, ctx: ProcessPollResponse(
            schema_version="1.0",
            pid=request.pid,
            running=False,
        ),
    )
    monkeypatch.setattr(
        orchestrator,
        "read_process_output",
        lambda request, ctx: ProcessOutputReadResponse(
            schema_version="1.0",
            chunk=ProcessOutputChunk(
                schema_version="1.0",
                path=request.path,
                text="[worker] failed",
                truncated=False,
                size_bytes=15,
            ),
        ),
    )

    first = orchestrator.poll_ui_run(
        UiRunPollRequest(
            schema_version="1.0",
            registry_path=registry_path,
            run_id="run-1",
            output_tail_bytes=2048,
        ),
        _ctx(),
    )
    second = orchestrator.poll_ui_run(
        UiRunPollRequest(
            schema_version="1.0",
            registry_path=registry_path,
            run_id="run-1",
            output_tail_bytes=2048,
        ),
        _ctx(),
    )

    assert first.record.status == "failed"
    assert first.record.error_code == "ui_run_worker_exited_unexpectedly"
    assert first.output_chunk is not None
    assert second.record.status == "failed"
    assert second.record.finished_at_utc == first.record.finished_at_utc


def test_cancel_ui_run_updates_state_and_terminates_process(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = _registry_path(tmp_path)
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=registry_path,
            record=_running_record(registry_path=registry_path),
        ),
        _ctx(),
    )
    calls: list[int] = []

    def _fake_terminate(request, ctx):
        calls.append(request.pid)
        return ProcessTerminateResponse(
            schema_version="1.0",
            pid=request.pid,
            terminated=True,
        )

    monkeypatch.setattr(orchestrator, "terminate_process", _fake_terminate)

    response = orchestrator.cancel_ui_run(
        UiRunCancelRequest(
            schema_version="1.0",
            registry_path=registry_path,
            run_id="run-1",
        ),
        _ctx(),
    )

    assert response.canceled is True
    assert response.record.status == "canceled"
    assert calls == [3210]


def test_launch_ui_run_same_request_creates_new_record_ids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    def _fake_launch_process(request, ctx):
        return ProcessLaunchResponse(
            schema_version="1.0",
            pid=5000,
            command=request.command,
            cwd=request.cwd,
            output_path=request.output_path,
            started_at_utc="2026-04-09T10:00:05+00:00",
        )

    monkeypatch.setattr(orchestrator, "launch_process", _fake_launch_process)
    request = UiRunLaunchRequest(
        schema_version="1.0",
        registry_path=_registry_path(tmp_path),
        workspace_root=str(tmp_path),
        run_type="report_download",
        display_name="Report download",
        request_payload={"url": "https://example.com/report"},
    )

    first = orchestrator.launch_ui_run(request, _ctx())
    second = orchestrator.launch_ui_run(request, _ctx())

    assert first.record.run_id != second.record.run_id
