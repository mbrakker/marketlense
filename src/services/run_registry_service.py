from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId
from src.contracts.sqlite_migration import SqliteMigrationApplyRequest
from src.contracts.ui_run_control import (
    UiRunDeadLetterActionListRequest,
    UiRunDeadLetterActionListResponse,
    UiRunDeadLetterActionRecord,
    UiRunDeadLetterActionRequest,
    UiRunDeadLetterActionResponse,
    UiRunDeadLetterArtifactLinks,
    UiRunDeadLetterErrorTaxonomy,
    UiRunDeadLetterIdentity,
    UiRunDeadLetterListRequest,
    UiRunDeadLetterListResponse,
    UiRunDeadLetterRecord,
    UiRunDeadLetterRemediation,
    UiRunRecord,
    UiRunRecordGetRequest,
    UiRunRecordGetResponse,
    UiRunRecordListRequest,
    UiRunRecordListResponse,
    UiRunRecordWriteRequest,
    UiRunRecordWriteResponse,
)
from src.services.sqlite_migration_service import apply_ui_run_registry_migrations
from src.utils.clock import utc_now_iso as _utc_now
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.ui_run_dead_letter import (
    DEAD_LETTER_ACTIONS,
    DEAD_LETTER_TRIAGE_STATUSES,
    build_dead_letter_record,
)

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
                    target_version=3,
                    ctx=ctx,
                ),
                conn,
            )
            _backfill_dead_letter_remediation_context(
                conn,
                registry_path=path,
                ctx=ctx,
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
        None
        if record.error_retryable is None
        else (1 if record.error_retryable else 0),
        record.error_severity,
    )


def _row_to_record(row: sqlite3.Row) -> UiRunRecord:
    return UiRunRecord(
        schema_version="1.0",
        run_id=RunId(str(row["run_id"])),
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
        error_retryable=(
            None
            if row["error_retryable"] is None
            else bool(int(row["error_retryable"]))
        ),
        error_severity=str(row["error_severity"] or ""),
    )


def _dead_letter_from_row(row: sqlite3.Row) -> UiRunDeadLetterRecord:
    result_summary = json.loads(str(row["result_summary_json"]) or "{}")
    remediation_fields = set(row.keys())
    workflow_id = (
        str(row["workflow_id"] or "") if "workflow_id" in remediation_fields else ""
    )
    step_id = str(row["step_id"] or "") if "step_id" in remediation_fields else ""
    checkpoint_stage = (
        str(row["checkpoint_stage"] or "")
        if "checkpoint_stage" in remediation_fields
        else ""
    )
    input_checksum = (
        str(row["input_checksum"] or "")
        if "input_checksum" in remediation_fields
        else ""
    )
    idempotency_key = (
        str(row["idempotency_key"] or "")
        if "idempotency_key" in remediation_fields
        else ""
    )
    remediation_code = (
        str(row["remediation_code"] or "")
        if "remediation_code" in remediation_fields
        else ""
    )
    runbook_link = (
        str(row["runbook_link"] or "") if "runbook_link" in remediation_fields else ""
    )
    budget_context = (
        json.loads(str(row["budget_context_json"]) or "{}")
        if "budget_context_json" in remediation_fields
        else {}
    )
    return UiRunDeadLetterRecord(
        schema_version="1.1",
        run_id=RunId(str(row["run_id"])),
        run_type=str(row["run_type"] or ""),
        display_name=str(row["display_name"] or ""),
        run_status=str(row["run_status"] or ""),
        triage_status=str(row["triage_status"] or ""),
        triage_category=str(row["triage_category"] or ""),
        triage_reason=str(row["triage_reason"] or ""),
        failed_at_utc=str(row["first_failed_at_utc"] or ""),
        updated_at_utc=str(row["updated_at_utc"] or ""),
        error_taxonomy=UiRunDeadLetterErrorTaxonomy(
            schema_version="1.0",
            error_code=str(row["error_code"] or ""),
            error_message=str(row["error_message"] or ""),
            retryable=bool(int(row["error_retryable"] or 0)),
            severity=str(row["error_severity"] or ""),
            stage=str(row["error_stage"] or ""),
        ),
        identity=UiRunDeadLetterIdentity(
            schema_version="1.0",
            publisher_name=str(row["publisher_name"] or ""),
            publisher_insights_url=str(row["publisher_insights_url"] or ""),
            report_url=str(row["report_url"] or ""),
        ),
        artifact_links=UiRunDeadLetterArtifactLinks(
            schema_version="1.0",
            output_path=str(row["output_path"] or ""),
            request_path=str(row["request_path"] or ""),
            manifest_path=str(row["manifest_path"] or ""),
            artifact_paths=json.loads(str(row["artifact_paths_json"]) or "[]"),
        ),
        remediation=UiRunDeadLetterRemediation(
            schema_version="1.0",
            workflow_id=workflow_id,
            step_id=step_id,
            checkpoint_stage=checkpoint_stage,
            input_checksum=input_checksum,
            idempotency_key=idempotency_key,
            remediation_code=remediation_code,
            runbook_link=runbook_link,
            budget_context=budget_context,
        ),
        result_summary=result_summary,
        recovery_run_id=str(row["recovery_run_id"] or ""),
        last_action=str(row["last_action"] or ""),
        last_action_note=str(row["last_action_note"] or ""),
        last_action_at_utc=str(row["last_action_at_utc"] or ""),
    )


def _dead_letter_action_from_row(row: sqlite3.Row) -> UiRunDeadLetterActionRecord:
    return UiRunDeadLetterActionRecord(
        schema_version="1.0",
        run_id=RunId(str(row["run_id"])),
        action=str(row["action"] or ""),
        actor=str(row["actor"] or ""),
        note=str(row["note"] or ""),
        related_run_id=str(row["related_run_id"] or ""),
        created_at_utc=str(row["created_at_utc"] or ""),
    )


def _backfill_dead_letter_remediation_context(
    conn: sqlite3.Connection,
    *,
    registry_path: str,
    ctx: RunContext,
) -> None:
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """
        SELECT ui_runs.*, ui_run_dead_letters.first_failed_at_utc
        FROM ui_run_dead_letters
        INNER JOIN ui_runs ON ui_runs.run_id = ui_run_dead_letters.run_id
        WHERE ui_run_dead_letters.input_checksum = ''
           OR ui_run_dead_letters.idempotency_key = ''
           OR ui_run_dead_letters.remediation_code = ''
           OR ui_run_dead_letters.runbook_link = ''
        """
    ).fetchall()
    for row in rows:
        record = _row_to_record(row)
        dead_letter = build_dead_letter_record(
            registry_path=registry_path,
            record=record,
            failed_at_utc=str(row["first_failed_at_utc"] or record.updated_at_utc),
            updated_at_utc=record.updated_at_utc,
        )
        remediation = dead_letter.remediation
        conn.execute(
            """
            UPDATE ui_run_dead_letters
            SET workflow_id=?, step_id=?, checkpoint_stage=?, input_checksum=?,
                idempotency_key=?, remediation_code=?, runbook_link=?,
                budget_context_json=?
            WHERE run_id=?
            """,
            (
                remediation.workflow_id,
                remediation.step_id,
                remediation.checkpoint_stage,
                remediation.input_checksum,
                remediation.idempotency_key,
                remediation.remediation_code,
                remediation.runbook_link,
                json.dumps(remediation.budget_context, ensure_ascii=True),
                str(record.run_id),
            ),
        )
    if rows:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="ui_run_dead_letter_remediation_backfill_complete",
                module=logger.name,
                fields={"registry_path": registry_path, "backfilled_count": len(rows)},
            )
        )


def _upsert_dead_letter_for_failed_record(
    conn: sqlite3.Connection,
    *,
    registry_path: str,
    record: UiRunRecord,
) -> None:
    failed_at_utc = str(record.finished_at_utc or record.updated_at_utc or "")
    action_at_utc = _utc_now()
    existing = conn.execute(
        "SELECT * FROM ui_run_dead_letters WHERE run_id = ?",
        (str(record.run_id),),
    ).fetchone()
    existing_record = _dead_letter_from_row(existing) if existing is not None else None
    dead_letter = build_dead_letter_record(
        registry_path=registry_path,
        record=record,
        failed_at_utc=(
            existing_record.failed_at_utc
            if existing_record is not None
            else failed_at_utc
        ),
        updated_at_utc=action_at_utc,
        triage_status=(
            existing_record.triage_status if existing_record is not None else "open"
        ),
        recovery_run_id=(
            existing_record.recovery_run_id if existing_record is not None else ""
        ),
        last_action=(
            existing_record.last_action
            if existing_record is not None
            else "auto_triaged"
        ),
        last_action_note=(
            existing_record.last_action_note if existing_record is not None else ""
        ),
        last_action_at_utc=(
            existing_record.last_action_at_utc
            if existing_record is not None
            else action_at_utc
        ),
    )
    conn.execute(
        """
        INSERT INTO ui_run_dead_letters (
          run_id, run_type, display_name, run_status, triage_status, triage_category,
          triage_reason, error_code, error_message, error_retryable, error_severity,
          error_stage, publisher_name, publisher_insights_url, report_url, output_path,
          request_path, manifest_path, artifact_paths_json, result_summary_json,
          workflow_id, step_id, checkpoint_stage, input_checksum, idempotency_key,
          remediation_code, runbook_link, budget_context_json,
          first_failed_at_utc, last_failed_at_utc, updated_at_utc, recovery_run_id,
          last_action, last_action_note, last_action_at_utc
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
          run_type=excluded.run_type,
          display_name=excluded.display_name,
          run_status=excluded.run_status,
          triage_category=excluded.triage_category,
          triage_reason=excluded.triage_reason,
          error_code=excluded.error_code,
          error_message=excluded.error_message,
          error_retryable=excluded.error_retryable,
          error_severity=excluded.error_severity,
          error_stage=excluded.error_stage,
          publisher_name=excluded.publisher_name,
          publisher_insights_url=excluded.publisher_insights_url,
          report_url=excluded.report_url,
          output_path=excluded.output_path,
          request_path=excluded.request_path,
          manifest_path=excluded.manifest_path,
          artifact_paths_json=excluded.artifact_paths_json,
          result_summary_json=excluded.result_summary_json,
          workflow_id=excluded.workflow_id,
          step_id=excluded.step_id,
          checkpoint_stage=excluded.checkpoint_stage,
          input_checksum=excluded.input_checksum,
          idempotency_key=excluded.idempotency_key,
          remediation_code=excluded.remediation_code,
          runbook_link=excluded.runbook_link,
          budget_context_json=excluded.budget_context_json,
          last_failed_at_utc=excluded.last_failed_at_utc,
          updated_at_utc=excluded.updated_at_utc
        """,
        (
            dead_letter.run_id,
            dead_letter.run_type,
            dead_letter.display_name,
            dead_letter.run_status,
            dead_letter.triage_status,
            dead_letter.triage_category,
            dead_letter.triage_reason,
            dead_letter.error_taxonomy.error_code,
            dead_letter.error_taxonomy.error_message,
            1 if dead_letter.error_taxonomy.retryable else 0,
            dead_letter.error_taxonomy.severity,
            dead_letter.error_taxonomy.stage,
            dead_letter.identity.publisher_name,
            dead_letter.identity.publisher_insights_url,
            dead_letter.identity.report_url,
            dead_letter.artifact_links.output_path,
            dead_letter.artifact_links.request_path,
            dead_letter.artifact_links.manifest_path,
            json.dumps(dead_letter.artifact_links.artifact_paths, ensure_ascii=True),
            json.dumps(dead_letter.result_summary, ensure_ascii=True),
            dead_letter.remediation.workflow_id,
            dead_letter.remediation.step_id,
            dead_letter.remediation.checkpoint_stage,
            dead_letter.remediation.input_checksum,
            dead_letter.remediation.idempotency_key,
            dead_letter.remediation.remediation_code,
            dead_letter.remediation.runbook_link,
            json.dumps(dead_letter.remediation.budget_context, ensure_ascii=True),
            dead_letter.failed_at_utc,
            dead_letter.updated_at_utc,
            dead_letter.updated_at_utc,
            dead_letter.recovery_run_id,
            dead_letter.last_action,
            dead_letter.last_action_note,
            dead_letter.last_action_at_utc,
        ),
    )
    if existing is None:
        conn.execute(
            """
            INSERT INTO ui_run_dead_letter_actions(
              run_id, action, actor, note, related_run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(dead_letter.run_id),
                "auto_triaged",
                "system",
                dead_letter.last_action_note or dead_letter.triage_reason,
                "",
                dead_letter.updated_at_utc,
            ),
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
              error_code, error_message, error_retryable, error_severity
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
              error_message=excluded.error_message,
              error_retryable=excluded.error_retryable,
              error_severity=excluded.error_severity
            """,
            _record_to_row(request.record),
        )
        if request.record.status == "failed":
            _upsert_dead_letter_for_failed_record(
                conn,
                registry_path=request.registry_path,
                record=request.record,
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
    normalized_statuses = [
        str(status).strip() for status in request.statuses if str(status).strip()
    ]
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


def list_ui_run_dead_letters(
    request: UiRunDeadLetterListRequest, ctx: RunContext
) -> UiRunDeadLetterListResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_dead_letter_list_start",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "triage_statuses": request.triage_statuses,
                "limit": request.limit,
            },
        )
    )
    query = "SELECT * FROM ui_run_dead_letters"
    params: list[object] = []
    normalized_statuses = [
        str(status).strip() for status in request.triage_statuses if str(status).strip()
    ]
    if normalized_statuses:
        placeholders = ", ".join("?" for _ in normalized_statuses)
        query += f" WHERE triage_status IN ({placeholders})"
        params.extend(normalized_statuses)
    query += " ORDER BY last_failed_at_utc DESC, run_id DESC LIMIT ?"
    params.append(int(request.limit))
    with _registry_conn(request.registry_path, ctx) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(query, tuple(params)).fetchall()
    records = [_dead_letter_from_row(row) for row in rows]
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_dead_letter_list_complete",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "count": len(records),
            },
        )
    )
    return UiRunDeadLetterListResponse(schema_version="1.0", records=records)


def list_ui_run_dead_letter_actions(
    request: UiRunDeadLetterActionListRequest, ctx: RunContext
) -> UiRunDeadLetterActionListResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_dead_letter_action_list_start",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "limit": request.limit,
            },
        )
    )
    with _registry_conn(request.registry_path, ctx) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT run_id, action, actor, note, related_run_id, created_at_utc
            FROM ui_run_dead_letter_actions
            WHERE run_id = ?
            ORDER BY created_at_utc DESC, id DESC
            LIMIT ?
            """,
            (str(request.run_id), int(request.limit)),
        ).fetchall()
    actions = [_dead_letter_action_from_row(row) for row in rows]
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_dead_letter_action_list_complete",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "count": len(actions),
            },
        )
    )
    return UiRunDeadLetterActionListResponse(
        schema_version="1.0",
        actions=actions,
    )


def record_ui_run_dead_letter_action(
    request: UiRunDeadLetterActionRequest, ctx: RunContext
) -> UiRunDeadLetterActionResponse:
    action = str(request.action or "").strip()
    if action not in DEAD_LETTER_ACTIONS - {"auto_triaged"}:
        raise AppError(
            code="ui_run_dead_letter_action_invalid",
            message="Dead-letter action must be retry_requested, discarded, or escalated",
            retryable=False,
            context={"action": request.action},
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_dead_letter_action_start",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "action": action,
                "actor": request.actor,
            },
        )
    )
    with _registry_conn(request.registry_path, ctx) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM ui_run_dead_letters WHERE run_id = ?",
            (str(request.run_id),),
        ).fetchone()
        if row is None:
            raise AppError(
                code="ui_run_dead_letter_not_found",
                message=f"Dead-letter record not found for run: {request.run_id}",
                retryable=False,
                context={
                    "registry_path": request.registry_path,
                    "run_id": request.run_id,
                },
            )
        existing = _dead_letter_from_row(row)
        triage_status = (
            "discarded"
            if action == "discarded"
            else "escalated"
            if action == "escalated"
            else "recovery_requested"
        )
        if triage_status not in DEAD_LETTER_TRIAGE_STATUSES:
            raise AppError(
                code="ui_run_dead_letter_status_invalid",
                message="Dead-letter triage status is invalid",
                retryable=False,
                context={"triage_status": triage_status},
            )
        action_at_utc = _utc_now()
        conn.execute(
            """
            UPDATE ui_run_dead_letters
            SET triage_status=?,
                updated_at_utc=?,
                recovery_run_id=?,
                last_action=?,
                last_action_note=?,
                last_action_at_utc=?
            WHERE run_id=?
            """,
            (
                triage_status,
                action_at_utc,
                str(request.related_run_id or "").strip(),
                action,
                str(request.note or "").strip(),
                action_at_utc,
                str(request.run_id),
            ),
        )
        conn.execute(
            """
            INSERT INTO ui_run_dead_letter_actions(
              run_id, action, actor, note, related_run_id, created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(request.run_id),
                action,
                str(request.actor or "ui").strip() or "ui",
                str(request.note or "").strip(),
                str(request.related_run_id or "").strip(),
                action_at_utc,
            ),
        )
        updated_row = conn.execute(
            "SELECT * FROM ui_run_dead_letters WHERE run_id = ?",
            (str(request.run_id),),
        ).fetchone()
        action_row = conn.execute(
            """
            SELECT run_id, action, actor, note, related_run_id, created_at_utc
            FROM ui_run_dead_letter_actions
            WHERE run_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (str(request.run_id),),
        ).fetchone()
    record = _dead_letter_from_row(updated_row)
    action_record = _dead_letter_action_from_row(action_row)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="ui_run_dead_letter_action_complete",
            module=logger.name,
            fields={
                "registry_path": request.registry_path,
                "run_id": request.run_id,
                "action": action,
                "triage_status": record.triage_status,
                "related_run_id": request.related_run_id,
            },
        )
    )
    return UiRunDeadLetterActionResponse(
        schema_version="1.0",
        record=record,
        action_record=action_record,
    )
