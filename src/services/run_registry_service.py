from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from src.contracts.run_context import RunContext
from src.contracts.sqlite_migration import SqliteMigrationApplyRequest
from src.contracts.ui_run_control import (
    UiRunRecord,
    UiRunRecordGetRequest,
    UiRunRecordGetResponse,
    UiRunRecordListRequest,
    UiRunRecordListResponse,
    UiRunRecordWriteRequest,
    UiRunRecordWriteResponse,
)
from src.services.sqlite_migration_service import apply_ui_run_registry_migrations
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.run_registry_service")

DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0
_RUN_REGISTRY_LOCK = threading.Lock()

def default_ui_run_registry_path(state_db: str) -> str:
    state_path = Path(state_db).expanduser().resolve()
    return str(state_path.with_name("ui_runs.sqlite"))


@contextmanager
def _registry_conn(path: str, ctx: RunContext):
    if not path:
        raise AppError(
            code="ui_run_registry_missing",
            message="UI run registry path is required",
            retryable=False,
        )
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        conn = sqlite3.connect(path, timeout=DEFAULT_BUSY_TIMEOUT_SECONDS)
    except sqlite3.Error as exc:
        raise AppError(
            code="ui_run_registry_unavailable",
            message="Failed to open UI run registry DB",
            cause=exc,
            retryable=True,
            context={"registry_path": path},
        ) from exc
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute(
            f"PRAGMA busy_timeout={max(0, int(DEFAULT_BUSY_TIMEOUT_SECONDS * 1000))}"
        )
        conn.execute("PRAGMA synchronous=NORMAL")
        with _RUN_REGISTRY_LOCK:
            apply_ui_run_registry_migrations(
                SqliteMigrationApplyRequest(
                    schema_version="1.0",
                    database_key="ui_run_registry",
                    db_path=path,
                    target_version=1,
                    ctx=ctx,
                ),
                conn,
            )
            conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _record_to_row(record: UiRunRecord) -> tuple[object, ...]:
    return (
        record.run_id,
        record.run_type,
        record.display_name,
        record.status,
        json.dumps(record.request_payload, ensure_ascii=True),
        json.dumps(record.command, ensure_ascii=True),
        record.created_at_utc,
        record.updated_at_utc,
        record.started_at_utc,
        record.finished_at_utc,
        record.output_path,
        record.request_path,
        json.dumps(record.artifact_paths, ensure_ascii=True),
        json.dumps(record.result_summary, ensure_ascii=True),
        record.pid,
        record.exit_code,
        record.error_code,
        record.error_message,
    )


def _row_to_record(row: sqlite3.Row) -> UiRunRecord:
    return UiRunRecord(
        schema_version="1.0",
        run_id=str(row["run_id"]),
        run_type=str(row["run_type"]),
        display_name=str(row["display_name"]),
        status=str(row["status"]),
        request_payload=json.loads(str(row["request_payload_json"]) or "{}"),
        command=json.loads(str(row["command_json"]) or "[]"),
        created_at_utc=str(row["created_at_utc"] or ""),
        updated_at_utc=str(row["updated_at_utc"] or ""),
        started_at_utc=str(row["started_at_utc"] or ""),
        finished_at_utc=str(row["finished_at_utc"] or ""),
        output_path=str(row["output_path"] or ""),
        request_path=str(row["request_path"] or ""),
        artifact_paths=json.loads(str(row["artifact_paths_json"]) or "[]"),
        result_summary=json.loads(str(row["result_summary_json"]) or "{}"),
        pid=int(row["pid"]) if row["pid"] is not None else None,
        exit_code=int(row["exit_code"]) if row["exit_code"] is not None else None,
        error_code=str(row["error_code"] or ""),
        error_message=str(row["error_message"] or ""),
    )


def write_ui_run_record(
    request: UiRunRecordWriteRequest, ctx: RunContext
) -> UiRunRecordWriteResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_registry_write_start",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.record.run_id,
                "run_type": request.record.run_type,
                "status": request.record.status,
            },
        )
    )
    with _registry_conn(request.registry_path, ctx) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute(
            """
            INSERT INTO ui_runs (
              run_id, run_type, display_name, status, request_payload_json, command_json,
              created_at_utc, updated_at_utc, started_at_utc, finished_at_utc, output_path,
              request_path, artifact_paths_json, result_summary_json, pid, exit_code,
              error_code, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(run_id) DO UPDATE SET
              run_type=excluded.run_type,
              display_name=excluded.display_name,
              status=excluded.status,
              request_payload_json=excluded.request_payload_json,
              command_json=excluded.command_json,
              created_at_utc=excluded.created_at_utc,
              updated_at_utc=excluded.updated_at_utc,
              started_at_utc=excluded.started_at_utc,
              finished_at_utc=excluded.finished_at_utc,
              output_path=excluded.output_path,
              request_path=excluded.request_path,
              artifact_paths_json=excluded.artifact_paths_json,
              result_summary_json=excluded.result_summary_json,
              pid=excluded.pid,
              exit_code=excluded.exit_code,
              error_code=excluded.error_code,
              error_message=excluded.error_message
            """,
            _record_to_row(request.record),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_registry_write_complete",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.record.run_id,
                "status": request.record.status,
            },
        )
    )
    return UiRunRecordWriteResponse(schema_version="1.0", record=request.record)


def get_ui_run_record(
    request: UiRunRecordGetRequest, ctx: RunContext
) -> UiRunRecordGetResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_registry_get_start",
            module=logger.name,
            fields={"registry_path": request.registry_path, "run_id": request.run_id},
        )
    )
    with _registry_conn(request.registry_path, ctx) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM ui_runs WHERE run_id = ?",
            (request.run_id,),
        ).fetchone()
    record = _row_to_record(row) if row is not None else None
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_registry_get_complete",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "found": bool(record),
            },
        )
    )
    return UiRunRecordGetResponse(schema_version="1.0", record=record)


def list_ui_run_records(
    request: UiRunRecordListRequest, ctx: RunContext
) -> UiRunRecordListResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_registry_list_start",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "statuses": request.statuses,
                "limit": request.limit,
            },
        )
    )
    query = "SELECT * FROM ui_runs"
    params: list[object] = []
    normalized_statuses = [str(status).strip() for status in request.statuses if str(status).strip()]
    if normalized_statuses:
        placeholders = ", ".join("?" for _ in normalized_statuses)
        query += f" WHERE status IN ({placeholders})"
        params.extend(normalized_statuses)
    query += " ORDER BY created_at_utc DESC, run_id DESC LIMIT ?"
    params.append(int(request.limit))
    with _registry_conn(request.registry_path, ctx) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    records = [_row_to_record(row) for row in rows]
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_registry_list_complete",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "count": len(records),
            },
        )
    )
    return UiRunRecordListResponse(schema_version="1.0", records=records)
