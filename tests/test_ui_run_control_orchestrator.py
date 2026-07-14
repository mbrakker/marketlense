from __future__ import annotations

import logging
from pathlib import Path

from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import (
    ProcessLaunchResponse,
    ProcessOutputChunk,
    ProcessOutputReadResponse,
    ProcessPollResponse,
    ProcessTerminateResponse,
    UiRunCancelRequest,
    UiRunDeadLetterListRequest,
    UiRunDeadLetterReapRequest,
    UiRunLaunchRequest,
    UiRunLaunchResponse,
    UiRunPollRequest,
    UiRunRecord,
    UiRunRecordGetRequest,
    UiRunRecordWriteRequest,
)
from src.orchestrators import ui_run_control_orchestrator as orchestrator
from src.services.run_registry_service import (
    get_ui_run_record,
    write_ui_run_record,
)
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


def _queued_record(*, registry_path: str) -> UiRunRecord:
    return UiRunRecord(
        schema_version="1.0",
        run_id="run-queued",
        run_type="ingest",
        display_name="Queued ingest",
        status="queued",
        request_payload={"limit": 2},
        command=["python", "-m", "src.cli"],
        created_at_utc="2026-04-09T10:00:00+00:00",
        updated_at_utc="2026-04-09T10:00:00+00:00",
        output_path="out.log",
        request_path="request.json",
        pid=1234,
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
    assert isinstance(response.record.run_id, RunId)
    assert isinstance(stored.run_id, RunId)
    assert response.record.status == "running"
    assert response.record.started_at_utc == "2026-04-09T10:00:05+00:00"
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
    assert isinstance(first.record.run_id, RunId)
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
    assert isinstance(response.record.run_id, RunId)
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


def test_poll_ui_run_promotes_live_queued_worker_to_running(
    tmp_path: Path,
    monkeypatch,
) -> None:
    registry_path = _registry_path(tmp_path)
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=registry_path,
            record=_queued_record(registry_path=registry_path),
        ),
        _ctx(),
    )
    monkeypatch.setattr(
        orchestrator,
        "poll_process",
        lambda request, ctx: ProcessPollResponse(
            schema_version="1.0",
            pid=request.pid,
            running=True,
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
                text="[worker] running",
                truncated=False,
                size_bytes=16,
            ),
        ),
    )

    response = orchestrator.poll_ui_run(
        UiRunPollRequest(
            schema_version="1.0",
            registry_path=registry_path,
            run_id="run-queued",
            output_tail_bytes=2048,
        ),
        _ctx(),
    )

    persisted = get_ui_run_record(
        UiRunRecordGetRequest(
            schema_version="1.0",
            registry_path=registry_path,
            run_id="run-queued",
        ),
        _ctx(),
    ).record

    assert response.record.status == "running"
    assert response.record.started_at_utc
    assert persisted == response.record


def test_dead_letter_reaper_launches_one_recovery_then_suppresses_duplicates(
    tmp_path: Path,
) -> None:
    registry_path = _registry_path(tmp_path)
    failed = UiRunRecord(
        schema_version="1.0",
        run_id="retryable-run",
        run_type="report_download",
        display_name="Download report",
        status="failed",
        request_payload={"url": "https://example.com/report"},
        command=["python", "-m", "src.cli"],
        created_at_utc="2026-01-01T00:00:00+00:00",
        updated_at_utc="2026-01-01T00:01:00+00:00",
        finished_at_utc="2026-01-01T00:01:00+00:00",
        output_path="out.log",
        request_path="request.json",
        error_code="browser_download_request_failed",
        error_message="temporary request failure",
        error_retryable=True,
        error_severity="error",
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0", registry_path=registry_path, record=failed
        ),
        _ctx(),
    )
    launches: list[UiRunLaunchRequest] = []

    def launch(request: UiRunLaunchRequest, ctx) -> UiRunLaunchResponse:
        launches.append(request)
        return UiRunLaunchResponse(
            schema_version="1.0",
            record=UiRunRecord(
                schema_version="1.0",
                run_id="recovery-run",
                run_type=request.run_type,
                display_name=request.display_name,
                status="queued",
                request_payload=request.request_payload,
                command=[],
                created_at_utc="2026-01-01T00:02:00+00:00",
                updated_at_utc="2026-01-01T00:02:00+00:00",
            ),
        )

    request = UiRunDeadLetterReapRequest(
        schema_version="1.0",
        registry_path=registry_path,
        workspace_root=str(tmp_path),
        cooldown_seconds=0,
    )
    first = orchestrator.reap_dead_letter_runs(request, _ctx(), launch_run=launch)
    second = orchestrator.reap_dead_letter_runs(request, _ctx(), launch_run=launch)

    assert first.recovered_run_ids == ["retryable-run"]
    assert first.held_run_ids == []
    assert second.recovered_run_ids == []
    assert launches[0].request_payload == {
        "url": "https://example.com/report",
        "_workflow_control_recovery_attempt": 1,
    }
    assert len(launches) == 1


def test_dead_letter_reaper_holds_recovery_chain_at_attempt_budget(tmp_path) -> None:
    registry_path = str(tmp_path / "ui_runs.sqlite")
    failed = UiRunRecord(
        schema_version="1.0",
        run_id="exhausted-run",
        run_type="browser_download",
        display_name="Exhausted retry",
        status="failed",
        request_payload={
            "url": "https://example.com/report",
            "_workflow_control_recovery_attempt": 2,
        },
        command=["python", "-m", "src.cli"],
        created_at_utc="2026-01-01T00:00:00+00:00",
        updated_at_utc="2026-01-01T00:01:00+00:00",
        finished_at_utc="2026-01-01T00:01:00+00:00",
        output_path="out.log",
        request_path="request.json",
        error_code="browser_download_request_failed",
        error_message="temporary request failure",
        error_retryable=True,
        error_severity="error",
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0", registry_path=registry_path, record=failed
        ),
        _ctx(),
    )
    launches: list[UiRunLaunchRequest] = []

    def launch(request: UiRunLaunchRequest, ctx) -> UiRunLaunchResponse:
        launches.append(request)
        raise AssertionError("attempt-exhausted recovery must not launch")

    response = orchestrator.reap_dead_letter_runs(
        UiRunDeadLetterReapRequest(
            schema_version="1.0",
            registry_path=registry_path,
            workspace_root=str(tmp_path),
            cooldown_seconds=0,
            max_recovery_attempts=2,
        ),
        _ctx(),
        launch_run=launch,
    )

    assert response.recovered_run_ids == []
    assert response.held_run_ids == ["exhausted-run"]
    assert launches == []
    escalated = orchestrator.list_dead_letter_runs(
        UiRunDeadLetterListRequest(
            schema_version="1.0",
            registry_path=registry_path,
            triage_statuses=["escalated"],
            limit=10,
        ),
        _ctx(),
    ).records
    assert [item.run_id for item in escalated] == ["exhausted-run"]
    assert escalated[0].last_action == "escalated"
    assert escalated[0].last_action_note == (
        "automatic_escalation:recovery_attempt_budget_exhausted"
    )


def test_dead_letter_reaper_escalates_non_retryable_terminal_failure(tmp_path) -> None:
    registry_path = str(tmp_path / "ui_runs.sqlite")
    failed = UiRunRecord(
        schema_version="1.0",
        run_id="terminal-run",
        run_type="report_download",
        display_name="Terminal report download",
        status="failed",
        request_payload={"url": "https://example.com/report"},
        command=["python", "-m", "src.cli"],
        created_at_utc="2026-01-01T00:00:00+00:00",
        updated_at_utc="2026-01-01T00:01:00+00:00",
        finished_at_utc="2026-01-01T00:01:00+00:00",
        error_code="validation_failed",
        error_message="Source validation failed",
        error_retryable=False,
        error_severity="error",
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0", registry_path=registry_path, record=failed
        ),
        _ctx(),
    )

    response = orchestrator.reap_dead_letter_runs(
        UiRunDeadLetterReapRequest(
            schema_version="1.0",
            registry_path=registry_path,
            workspace_root=str(tmp_path),
            cooldown_seconds=0,
        ),
        _ctx(),
    )
    escalated = orchestrator.list_dead_letter_runs(
        UiRunDeadLetterListRequest(
            schema_version="1.0",
            registry_path=registry_path,
            triage_statuses=["escalated"],
            limit=10,
        ),
        _ctx(),
    ).records

    assert response.recovered_run_ids == []
    assert response.held_run_ids == ["terminal-run"]
    assert [item.run_id for item in escalated] == ["terminal-run"]
    assert escalated[0].last_action_note == "automatic_escalation:non_retryable_failure"
