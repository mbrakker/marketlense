from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from src.contracts.semantic_ids import RunId
from src.contracts.ui_run_control import (
    UiRunRecord,
    UiRunRecordGetRequest,
    UiRunRecordListRequest,
    UiRunRecordWriteRequest,
)
from src.services import run_registry_service as registry_service
from src.services.run_registry_service import (
    default_ui_run_registry_path,
    get_ui_run_record,
    list_ui_run_records,
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
