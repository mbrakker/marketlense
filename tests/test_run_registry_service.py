from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import (
    UiRunDeadLetterActionListRequest,
    UiRunDeadLetterActionRequest,
    UiRunDeadLetterListRequest,
    UiRunRecord,
    UiRunRecordGetRequest,
    UiRunRecordListRequest,
    UiRunRecordWriteRequest,
)
from src.services import run_registry_service as registry_service
from src.services.run_registry_service import (
    default_ui_run_registry_path,
    get_ui_run_record,
    list_ui_run_dead_letter_actions,
    list_ui_run_dead_letters,
    list_ui_run_records,
    record_ui_run_dead_letter_action,
    write_ui_run_record,
)
from src.utils.errors import AppError
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="test_run_registry_service")


def _record(*, run_id: str, status: str, created_at_utc: str) -> UiRunRecord:
    return UiRunRecord(
        schema_version="1.0",
        run_id=run_id,
        run_type="ingest",
        display_name="Ingest",
        status=status,
        request_payload={"limit": 3},
        command=["python", "-m", "src.cli"],
        created_at_utc=created_at_utc,
        updated_at_utc=created_at_utc,
        output_path="out.log",
        request_path="request.json",
    )


def test_default_ui_run_registry_path_reuses_state_directory(tmp_path: Path) -> None:
    state_db = tmp_path / "state" / "index.sqlite"
    registry = default_ui_run_registry_path(str(state_db))

    assert Path(registry).name == "ui_runs.sqlite"
    assert Path(registry).parent == state_db.parent.resolve()


def test_run_registry_service_write_get_and_list(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    registry_path = tmp_path / "state" / "ui_runs.sqlite"
    caplog.set_level(logging.INFO)
    newer = _record(
        run_id="run-new",
        status="running",
        created_at_utc="2026-04-09T10:05:00+00:00",
    )
    older = _record(
        run_id="run-old",
        status="succeeded",
        created_at_utc="2026-04-09T10:00:00+00:00",
    )

    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            record=older,
        ),
        _ctx(),
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            record=newer,
        ),
        _ctx(),
    )

    loaded = get_ui_run_record(
        UiRunRecordGetRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            run_id="run-new",
        ),
        _ctx(),
    ).record
    listed = list_ui_run_records(
        UiRunRecordListRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            statuses=[],
            limit=10,
        ),
        _ctx(),
    ).records

    assert loaded == newer
    assert isinstance(loaded.run_id, RunId)
    assert all(isinstance(item.run_id, RunId) for item in listed)
    assert [item.run_id for item in listed] == ["run-new", "run-old"]
    with sqlite3.connect(registry_path) as conn:
        schema_version = conn.execute(
            "SELECT current_version FROM schema_version WHERE database_key='ui_run_registry'"
        ).fetchone()
        ledger_rows = conn.execute(
            """
            SELECT migration_id
            FROM schema_migration_ledger
            WHERE database_key='ui_run_registry'
            ORDER BY version ASC
            """
        ).fetchall()
    assert schema_version == (2,)
    assert ledger_rows == [
        ("ui_run_registry_001_create_ui_runs",),
        ("ui_run_registry_002_add_dead_letter_ledger",),
    ]
    assert_logs_have_required_fields(caplog.records)


def test_run_registry_service_upserts_existing_record(tmp_path: Path) -> None:
    registry_path = tmp_path / "state" / "ui_runs.sqlite"
    queued = _record(
        run_id="run-1",
        status="queued",
        created_at_utc="2026-04-09T10:00:00+00:00",
    )
    succeeded = UiRunRecord(
        schema_version="1.0",
        run_id="run-1",
        run_type="ingest",
        display_name="Ingest",
        status="succeeded",
        request_payload={"limit": 3},
        command=["python", "-m", "src.cli"],
        created_at_utc="2026-04-09T10:00:00+00:00",
        updated_at_utc="2026-04-09T10:10:00+00:00",
        started_at_utc="2026-04-09T10:01:00+00:00",
        finished_at_utc="2026-04-09T10:09:00+00:00",
        output_path="out.log",
        request_path="request.json",
        artifact_paths=["out/report.html"],
        result_summary={"processed_count": 1},
        pid=1234,
        exit_code=0,
    )

    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            record=queued,
        ),
        _ctx(),
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            record=succeeded,
        ),
        _ctx(),
    )

    loaded = get_ui_run_record(
        UiRunRecordGetRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            run_id="run-1",
        ),
        _ctx(),
    ).record

    assert loaded == succeeded
    assert isinstance(loaded.run_id, RunId)


def test_run_registry_service_connect_failure_is_typed_app_error(
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    def _raise_connect(*args, **kwargs):
        raise sqlite3.OperationalError("connect boom")

    external_boundary_mocks_only.setattr(
        registry_service.sqlite3, "connect", _raise_connect
    )

    with pytest.raises(AppError) as exc_info:
        get_ui_run_record(
            UiRunRecordGetRequest(
                schema_version="1.0",
                registry_path="C:/tmp/ui_runs.sqlite",
                run_id="run-missing",
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="ui_run_registry_unavailable",
        retryable=True,
    )


def test_run_registry_service_auto_triages_failed_runs_and_logs_actions(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "state" / "ui_runs.sqlite"
    failed = UiRunRecord(
        schema_version="1.0",
        run_id="run-dead-letter",
        run_type="publisher_discovery",
        display_name="Publisher discovery",
        status="failed",
        request_payload={"insights_url": "https://example.com/insights"},
        command=["python", "-m", "src.cli"],
        created_at_utc="2026-04-29T09:00:00+00:00",
        updated_at_utc="2026-04-29T09:05:00+00:00",
        started_at_utc="2026-04-29T09:00:10+00:00",
        finished_at_utc="2026-04-29T09:05:00+00:00",
        output_path="out.log",
        request_path="request.json",
        artifact_paths=["out/report.json"],
        result_summary={"publisher_name": "Example Publisher"},
        error_code="publisher_inventory_browser_timeout",
        error_message="Discovery timed out",
        error_retryable=True,
        error_severity="error",
    )

    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            record=failed,
        ),
        _ctx(),
    )

    dead_letters = list_ui_run_dead_letters(
        UiRunDeadLetterListRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            triage_statuses=[],
            limit=10,
        ),
        _ctx(),
    ).records
    actions = list_ui_run_dead_letter_actions(
        UiRunDeadLetterActionListRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            run_id="run-dead-letter",
            limit=10,
        ),
        _ctx(),
    ).actions

    assert len(dead_letters) == 1
    assert dead_letters[0].triage_status == "open"
    assert dead_letters[0].triage_category == "external_dependency"
    assert dead_letters[0].error_taxonomy.stage == "publisher_discovery"
    assert dead_letters[0].identity.publisher_name == "Example Publisher"
    assert dead_letters[0].identity.publisher_insights_url == "https://example.com/insights"
    assert dead_letters[0].artifact_links.output_path == "out.log"
    assert dead_letters[0].artifact_links.request_path == "request.json"
    assert dead_letters[0].artifact_links.artifact_paths == ["out/report.json"]
    assert dead_letters[0].artifact_links.manifest_path.endswith(
        "ui_runs\\run-dead-letter\\replay_manifest.json"
    ) or dead_letters[0].artifact_links.manifest_path.endswith(
        "ui_runs/run-dead-letter/replay_manifest.json"
    )
    assert actions[0].action == "auto_triaged"
    assert actions[0].actor == "system"


def test_run_registry_service_records_recovery_and_discard_actions(
    tmp_path: Path,
) -> None:
    registry_path = tmp_path / "state" / "ui_runs.sqlite"
    failed = UiRunRecord(
        schema_version="1.0",
        run_id="run-action",
        run_type="report_download",
        display_name="Report download",
        status="failed",
        request_payload={"url": "https://example.com/report"},
        command=["python", "-m", "src.cli"],
        created_at_utc="2026-04-29T09:00:00+00:00",
        updated_at_utc="2026-04-29T09:05:00+00:00",
        finished_at_utc="2026-04-29T09:05:00+00:00",
        output_path="out.log",
        request_path="request.json",
        error_code="browser_download_agent_timeout",
        error_message="Timed out",
        error_retryable=False,
        error_severity="error",
    )
    write_ui_run_record(
        UiRunRecordWriteRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            record=failed,
        ),
        _ctx(),
    )

    recovery = record_ui_run_dead_letter_action(
        UiRunDeadLetterActionRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            run_id="run-action",
            action="retry_requested",
            actor="ui",
            note="Retry from tests",
            related_run_id="run-recovery",
        ),
        _ctx(),
    )
    discarded = record_ui_run_dead_letter_action(
        UiRunDeadLetterActionRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            run_id="run-action",
            action="discarded",
            actor="ui",
            note="No longer relevant",
        ),
        _ctx(),
    )
    actions = list_ui_run_dead_letter_actions(
        UiRunDeadLetterActionListRequest(
            schema_version="1.0",
            registry_path=str(registry_path),
            run_id="run-action",
            limit=10,
        ),
        _ctx(),
    ).actions

    assert recovery.record.triage_status == "recovery_requested"
    assert recovery.record.recovery_run_id == "run-recovery"
    assert recovery.action_record.action == "retry_requested"
    assert discarded.record.triage_status == "discarded"
    assert discarded.action_record.action == "discarded"
    assert [item.action for item in actions] == [
        "discarded",
        "retry_requested",
        "auto_triaged",
    ]
