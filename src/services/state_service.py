from __future__ import annotations

import logging
import sqlite3
from contextlib import contextmanager
from typing import Optional

from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateCheckRequest,
    StateDbAccessRequest,
    StateDbAccessResponse,
    StateGetRequest,
    StateGetResponse,
    StatePublishCheckRequest,
    StatePublishGetResponse,
    StatePublishRecordRequest,
    StateRecordRequest,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.state_service")

ACCESS_TIMEOUT_SECONDS = 0.0
LOCK_ERROR_MARKERS = ("database is locked", "database is busy")

DDL = """
CREATE TABLE IF NOT EXISTS processed (
  file_id TEXT PRIMARY KEY,
  md5 TEXT NOT NULL,
  processed_at INTEGER NOT NULL,
  openai_file_id TEXT,
  vector_store_id TEXT,
  vector_store_status TEXT,
  indexed_at_utc TEXT,
  last_error TEXT
);

CREATE TABLE IF NOT EXISTS published (
  file_id TEXT PRIMARY KEY,
  md5 TEXT NOT NULL,
  published_at INTEGER NOT NULL,
  wp_post_id INTEGER NOT NULL,
  wp_post_url TEXT NOT NULL
);
"""


@contextmanager
def _state_conn(path: str):
    if not path:
        raise AppError(
            code="state_db_missing",
            message="State DB path is required",
            retryable=False,
        )
    conn = sqlite3.connect(path)
    try:
        conn.executescript(DDL)
        _migrate_schema(conn)
        conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _migrate_schema(conn: sqlite3.Connection) -> None:
    """Add missing columns for processed table without dropping data."""
    cur = conn.execute("PRAGMA table_info(processed)")
    cols = {row[1] for row in cur.fetchall()}
    required = {
        "openai_file_id": "TEXT",
        "vector_store_id": "TEXT",
        "vector_store_status": "TEXT",
        "indexed_at_utc": "TEXT",
        "last_error": "TEXT",
    }
    for col, col_type in required.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE processed ADD COLUMN {col} {col_type}")


def _is_lock_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in LOCK_ERROR_MARKERS)


def check_state_db_access(request: StateDbAccessRequest, ctx: RunContext) -> StateDbAccessResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="state_db_access_start",
        module=logger.name,
        fields={"state_db": request.state_db, "timeout_seconds": request.timeout_seconds},
    ))
    if not request.state_db or not request.state_db.strip():
        raise AppError(
            code="state_db_missing",
            message="State DB path is required",
            retryable=False,
            severity="error",
        )
    timeout = request.timeout_seconds if request.timeout_seconds >= 0 else ACCESS_TIMEOUT_SECONDS
    logger.info(log_event(
        ctx,
        role="service",
        event="state_db_access_config",
        module=logger.name,
        fields={"timeout_seconds": timeout},
    ))
    try:
        conn = sqlite3.connect(request.state_db, timeout=timeout)
    except Exception as exc:
        logger.info(log_event(
            ctx,
            role="service",
            event="state_db_access_connect_failed",
            module=logger.name,
            fields={"state_db": request.state_db, "error": str(exc)},
        ))
        raise AppError(
            code="state_db_unavailable",
            message="Failed to open state DB",
            cause=exc,
            retryable=True,
            context={"state_db": request.state_db},
        ) from exc
    try:
        logger.info(log_event(
            ctx,
            role="service",
            event="state_db_access_probe",
            module=logger.name,
            fields={"state_db": request.state_db},
        ))
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError as exc:
        if _is_lock_error(exc):
            message = str(exc)
            logger.info(log_event(
                ctx,
                role="service",
                event="state_db_access_locked",
                module=logger.name,
                fields={"state_db": request.state_db, "error": message},
            ))
            response = StateDbAccessResponse(
                schema_version="1.0",
                state_db=request.state_db,
                accessible=False,
                locked=True,
                message=message,
            )
            logger.info(log_event(
                ctx,
                role="service",
                event="state_db_access_complete",
                module=logger.name,
                fields={
                    "state_db": response.state_db,
                    "accessible": response.accessible,
                    "locked": response.locked,
                    "message": response.message,
                },
            ))
            return response
        logger.info(log_event(
            ctx,
            role="service",
            event="state_db_access_failed",
            module=logger.name,
            fields={"state_db": request.state_db, "error": str(exc)},
        ))
        raise AppError(
            code="state_db_unavailable",
            message="State DB is not accessible",
            cause=exc,
            retryable=True,
            context={"state_db": request.state_db},
        ) from exc
    finally:
        conn.close()
    response = StateDbAccessResponse(
        schema_version="1.0",
        state_db=request.state_db,
        accessible=True,
        locked=False,
        message="",
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="state_db_access_complete",
        module=logger.name,
        fields={
            "state_db": response.state_db,
            "accessible": response.accessible,
            "locked": response.locked,
            "message": response.message,
        },
    ))
    return response


def already_processed(request: StateCheckRequest, ctx: RunContext) -> bool:
    logger.info(log_event(
        ctx,
        role="service",
        event="state_check_start",
        module=logger.name,
        fields={"file_id": request.file_id},
    ))
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT 1 FROM processed WHERE file_id=? AND md5=?", (request.file_id, request.md5)
        )
        result = cur.fetchone() is not None
    logger.info(log_event(
        ctx,
        role="service",
        event="state_check_complete",
        module=logger.name,
        fields={"file_id": request.file_id, "already_processed": result},
    ))
    return result


def record(request: StateRecordRequest, ctx: RunContext) -> None:
    logger.info(log_event(
        ctx,
        role="service",
        event="state_record_start",
        module=logger.name,
        fields={"file_id": request.file_id},
    ))
    with _state_conn(request.state_db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO processed("
            "file_id, md5, processed_at, openai_file_id, vector_store_id, vector_store_status, indexed_at_utc, last_error"
            ") VALUES(?, ?, strftime('%s','now'), ?, ?, ?, ?, ?)",
            (
                request.file_id,
                request.md5,
                request.openai_file_id,
                request.vector_store_id,
                request.vector_store_status,
                request.indexed_at_utc,
                request.last_error,
            ),
        )
    logger.info(log_event(
        ctx,
        role="service",
        event="state_record_complete",
        module=logger.name,
        fields={"file_id": request.file_id},
    ))


def get(request: StateGetRequest, ctx: RunContext) -> Optional[StateGetResponse]:
    logger.info(log_event(
        ctx,
        role="service",
        event="state_get_start",
        module=logger.name,
        fields={"file_id": request.file_id},
    ))
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT file_id, md5, processed_at, openai_file_id, vector_store_id, vector_store_status, indexed_at_utc, last_error "
            "FROM processed WHERE file_id=?",
            (request.file_id,),
        )
        row = cur.fetchone()
    if not row:
        logger.info(log_event(
            ctx,
            role="service",
            event="state_get_complete",
            module=logger.name,
            fields={"file_id": request.file_id, "found": False},
        ))
        return None
    file_id, md5, processed_at, openai_file_id, vector_store_id, vector_store_status, indexed_at_utc, last_error = row
    logger.info(log_event(
        ctx,
        role="service",
        event="state_get_complete",
        module=logger.name,
        fields={"file_id": request.file_id, "found": True},
    ))
    return StateGetResponse(
        schema_version="1.0",
        file_id=file_id,
        md5=md5,
        processed_at=processed_at,
        openai_file_id=openai_file_id,
        vector_store_id=vector_store_id,
        vector_store_status=vector_store_status,
        indexed_at_utc=indexed_at_utc,
        last_error=last_error,
    )


def already_published(request: StatePublishCheckRequest, ctx: RunContext) -> bool:
    logger.info(log_event(
        ctx,
        role="service",
        event="state_publish_check_start",
        module=logger.name,
        fields={"file_id": request.file_id},
    ))
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT 1 FROM published WHERE file_id=?", (request.file_id,)
        )
        result = cur.fetchone() is not None
    logger.info(log_event(
        ctx,
        role="service",
        event="state_publish_check_complete",
        module=logger.name,
        fields={"file_id": request.file_id, "already_published": result},
    ))
    return result


def record_publish(request: StatePublishRecordRequest, ctx: RunContext) -> None:
    logger.info(log_event(
        ctx,
        role="service",
        event="state_publish_record_start",
        module=logger.name,
        fields={"file_id": request.file_id, "wp_post_id": request.wp_post_id},
    ))
    with _state_conn(request.state_db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO published(file_id, md5, published_at, wp_post_id, wp_post_url) "
            "VALUES(?, ?, strftime('%s','now'), ?, ?)",
            (request.file_id, request.md5, request.wp_post_id, request.wp_post_url),
        )
    logger.info(log_event(
        ctx,
        role="service",
        event="state_publish_record_complete",
        module=logger.name,
        fields={"file_id": request.file_id, "wp_post_id": request.wp_post_id},
    ))


def get_publish(request: StatePublishCheckRequest, ctx: RunContext) -> Optional[StatePublishGetResponse]:
    logger.info(log_event(
        ctx,
        role="service",
        event="state_publish_get_start",
        module=logger.name,
        fields={"file_id": request.file_id},
    ))
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT file_id, md5, published_at, wp_post_id, wp_post_url FROM published WHERE file_id=?",
            (request.file_id,),
        )
        row = cur.fetchone()
    if not row:
        logger.info(log_event(
            ctx,
            role="service",
            event="state_publish_get_complete",
            module=logger.name,
            fields={"file_id": request.file_id, "found": False},
        ))
        return None
    file_id, md5, published_at, wp_post_id, wp_post_url = row
    logger.info(log_event(
        ctx,
        role="service",
        event="state_publish_get_complete",
        module=logger.name,
        fields={"file_id": file_id, "found": True},
    ))
    return StatePublishGetResponse(
        schema_version="1.0",
        file_id=file_id,
        md5=md5,
        published_at=published_at,
        wp_post_id=wp_post_id,
        wp_post_url=wp_post_url,
    )
