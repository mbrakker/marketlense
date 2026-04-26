from __future__ import annotations

import json
import logging
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyLookupResponse,
    OrchestratorIdempotencyRecord,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.idempotency_service")

DDL = """
CREATE TABLE IF NOT EXISTS orchestrator_idempotency (
  scope TEXT NOT NULL,
  idempotency_key TEXT NOT NULL,
  input_checksum TEXT NOT NULL,
  outcome_json TEXT NOT NULL,
  artifact_refs_json TEXT NOT NULL,
  recorded_at_utc TEXT NOT NULL,
  updated_at INTEGER NOT NULL,
  PRIMARY KEY(scope, idempotency_key)
);
"""


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


@contextmanager
def _conn(db_path: str):
    if not db_path:
        raise AppError(
            code="idempotency_db_missing",
            message="Idempotency DB path is required",
            retryable=False,
            severity="error",
        )
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        conn = sqlite3.connect(db_path, timeout=5.0)
    except sqlite3.Error as exc:
        raise AppError(
            code="idempotency_db_unavailable",
            message="Failed to open idempotency DB",
            cause=exc,
            retryable=True,
            context={"db_path": db_path},
        ) from exc
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        conn.executescript(DDL)
        conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _validate_request_fields(
    *,
    scope: str,
    idempotency_key: str,
    input_checksum: str,
) -> None:
    if not str(scope or "").strip():
        raise AppError(
            code="idempotency_scope_missing",
            message="Idempotency scope is required",
            retryable=False,
            severity="error",
        )
    if not str(idempotency_key or "").strip():
        raise AppError(
            code="idempotency_key_missing",
            message="Idempotency key is required",
            retryable=False,
            severity="error",
        )
    if not str(input_checksum or "").strip():
        raise AppError(
            code="idempotency_checksum_missing",
            message="Idempotency input checksum is required",
            retryable=False,
            severity="error",
        )


def _row_to_record(row: sqlite3.Row) -> OrchestratorIdempotencyRecord:
    outcome_payload = json.loads(str(row["outcome_json"] or "{}"))
    artifact_references = json.loads(str(row["artifact_refs_json"] or "{}"))
    if not isinstance(outcome_payload, dict):
        outcome_payload = {}
    if not isinstance(artifact_references, dict):
        artifact_references = {}
    return OrchestratorIdempotencyRecord(
        schema_version="1.0",
        scope=str(row["scope"] or ""),
        idempotency_key=str(row["idempotency_key"] or ""),
        input_checksum=str(row["input_checksum"] or ""),
        outcome_payload=outcome_payload,
        artifact_references=artifact_references,
        recorded_at_utc=str(row["recorded_at_utc"] or ""),
    )


def get_outcome(
    request: OrchestratorIdempotencyGetRequest,
    ctx: RunContext,
) -> OrchestratorIdempotencyLookupResponse:
    _validate_request_fields(
        scope=request.scope,
        idempotency_key=request.idempotency_key,
        input_checksum=request.input_checksum,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="idempotency_lookup_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "scope": request.scope,
                "idempotency_key": request.idempotency_key,
                "input_checksum": request.input_checksum,
            },
        )
    )
    try:
        with _conn(request.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT scope, idempotency_key, input_checksum, outcome_json,
                       artifact_refs_json, recorded_at_utc
                FROM orchestrator_idempotency
                WHERE scope=? AND idempotency_key=?
                """,
                (request.scope, request.idempotency_key),
            ).fetchone()
    except sqlite3.Error as exc:
        raise AppError(
            code="idempotency_lookup_failed",
            message="Failed to look up orchestrator idempotency outcome",
            cause=exc,
            retryable=True,
            context={"db_path": request.db_path, "scope": request.scope},
        ) from exc

    if row is None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="idempotency_lookup_complete",
                module=logger.name,
                fields={
                    "db_path": request.db_path,
                    "scope": request.scope,
                    "idempotency_key": request.idempotency_key,
                    "found": False,
                },
            )
        )
        return OrchestratorIdempotencyLookupResponse(
            schema_version="1.0", found=False, record=None
        )

    record = _row_to_record(row)
    if record.input_checksum != request.input_checksum:
        raise AppError(
            code="idempotency_checksum_mismatch",
            message="Idempotency key was reused with a different input checksum",
            retryable=False,
            severity="error",
            context={
                "db_path": request.db_path,
                "scope": request.scope,
                "idempotency_key": request.idempotency_key,
                "stored_input_checksum": record.input_checksum,
                "requested_input_checksum": request.input_checksum,
            },
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="idempotency_lookup_complete",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "scope": request.scope,
                "idempotency_key": request.idempotency_key,
                "found": True,
                "recorded_at_utc": record.recorded_at_utc,
            },
        )
    )
    return OrchestratorIdempotencyLookupResponse(
        schema_version="1.0",
        found=True,
        record=record,
    )


def record_outcome(
    request: OrchestratorIdempotencyRecordRequest,
    ctx: RunContext,
) -> OrchestratorIdempotencyRecord:
    _validate_request_fields(
        scope=request.scope,
        idempotency_key=request.idempotency_key,
        input_checksum=request.input_checksum,
    )
    recorded_at_utc = _utc_now_iso()
    outcome_json = json.dumps(
        request.outcome_payload or {},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    artifact_refs_json = json.dumps(
        request.artifact_references or {},
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="idempotency_record_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "scope": request.scope,
                "idempotency_key": request.idempotency_key,
                "input_checksum": request.input_checksum,
                "artifact_reference_keys": sorted(
                    str(key) for key in (request.artifact_references or {}).keys()
                ),
            },
        )
    )
    try:
        with _conn(request.db_path) as conn:
            conn.row_factory = sqlite3.Row
            existing_row = conn.execute(
                """
                SELECT scope, idempotency_key, input_checksum, outcome_json,
                       artifact_refs_json, recorded_at_utc
                FROM orchestrator_idempotency
                WHERE scope=? AND idempotency_key=?
                """,
                (request.scope, request.idempotency_key),
            ).fetchone()
            if existing_row is not None:
                existing = _row_to_record(existing_row)
                if existing.input_checksum != request.input_checksum:
                    raise AppError(
                        code="idempotency_checksum_mismatch",
                        message="Idempotency key was reused with a different input checksum",
                        retryable=False,
                        severity="error",
                        context={
                            "db_path": request.db_path,
                            "scope": request.scope,
                            "idempotency_key": request.idempotency_key,
                            "stored_input_checksum": existing.input_checksum,
                            "requested_input_checksum": request.input_checksum,
                        },
                    )
            conn.execute(
                """
                INSERT INTO orchestrator_idempotency(
                    scope,
                    idempotency_key,
                    input_checksum,
                    outcome_json,
                    artifact_refs_json,
                    recorded_at_utc,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, strftime('%s','now'))
                ON CONFLICT(scope, idempotency_key) DO UPDATE SET
                    input_checksum=excluded.input_checksum,
                    outcome_json=excluded.outcome_json,
                    artifact_refs_json=excluded.artifact_refs_json,
                    recorded_at_utc=excluded.recorded_at_utc,
                    updated_at=strftime('%s','now')
                """,
                (
                    request.scope,
                    request.idempotency_key,
                    request.input_checksum,
                    outcome_json,
                    artifact_refs_json,
                    recorded_at_utc,
                ),
            )
    except AppError:
        raise
    except sqlite3.Error as exc:
        raise AppError(
            code="idempotency_record_failed",
            message="Failed to record orchestrator idempotency outcome",
            cause=exc,
            retryable=True,
            context={"db_path": request.db_path, "scope": request.scope},
        ) from exc

    response = OrchestratorIdempotencyRecord(
        schema_version="1.0",
        scope=request.scope,
        idempotency_key=request.idempotency_key,
        input_checksum=request.input_checksum,
        outcome_payload=dict(request.outcome_payload or {}),
        artifact_references=dict(request.artifact_references or {}),
        recorded_at_utc=recorded_at_utc,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="idempotency_record_complete",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "scope": request.scope,
                "idempotency_key": request.idempotency_key,
                "recorded_at_utc": recorded_at_utc,
            },
        )
    )
    return response
