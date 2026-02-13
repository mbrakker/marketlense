from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional

from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateBatchCheckItem,
    StateBatchCheckRequest,
    StateBatchCheckResponse,
    StateCheckRequest,
    StateDbAccessRequest,
    StateDbAccessResponse,
    StateGetRequest,
    StateGetResponse,
    StateIngestCursorGetRequest,
    StateIngestCursorGetResponse,
    StateIngestCursorSetRequest,
    StateProcessedListRequest,
    StateProcessedListResponse,
    StateProcessedRow,
    StatePublishCheckRequest,
    StatePublishGetResponse,
    StatePublishedListRequest,
    StatePublishedListResponse,
    StatePublishedRow,
    StatePublishRecordRequest,
    StateRecordRequest,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.state_service")

ACCESS_TIMEOUT_SECONDS = 0.0
LOCK_ERROR_MARKERS = ("database is locked", "database is busy")
_STATE_CONN_LOCK = threading.Lock()
BATCH_STATE_CHECK_MAX_PAIRS = 200

DDL = """
CREATE TABLE IF NOT EXISTS processed (
  file_id TEXT PRIMARY KEY,
  md5 TEXT NOT NULL,
  processed_at INTEGER NOT NULL,
  openai_file_id TEXT,
  vector_store_id TEXT,
  vector_store_status TEXT,
  indexed_at_utc TEXT,
  last_error TEXT,
  text_validation_status TEXT,
  text_validation_reason TEXT,
  text_validation_pages_json TEXT,
  doc_map_summary_json TEXT
);

CREATE TABLE IF NOT EXISTS ingest_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at INTEGER NOT NULL
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
    with _STATE_CONN_LOCK:
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
        "text_validation_status": "TEXT",
        "text_validation_reason": "TEXT",
        "text_validation_pages_json": "TEXT",
        "doc_map_summary_json": "TEXT",
    }
    for col, col_type in required.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE processed ADD COLUMN {col} {col_type}")


def _is_lock_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in LOCK_ERROR_MARKERS)


def _parse_int_list(raw: Optional[str]) -> Optional[list[int]]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, list) and all(isinstance(item, int) for item in parsed):
        return parsed
    return None


def _parse_dict(raw: Optional[str]) -> Optional[dict]:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _normalize_batch_items(items: list[StateBatchCheckItem]) -> list[StateBatchCheckItem]:
    normalized: list[StateBatchCheckItem] = []
    seen: set[tuple[str, str]] = set()
    for item in items:
        file_id = item.file_id.strip() if isinstance(item.file_id, str) else ""
        md5 = item.md5.strip() if isinstance(item.md5, str) else ""
        if not file_id or not md5:
            continue
        key = (file_id, md5)
        if key in seen:
            continue
        seen.add(key)
        normalized.append(StateBatchCheckItem(schema_version="1.0", file_id=file_id, md5=md5))
    return normalized


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


def get_ingest_cursor(request: StateIngestCursorGetRequest, ctx: RunContext) -> StateIngestCursorGetResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="ingest_cursor_get_start",
        module=logger.name,
        fields={"state_db": request.state_db},
    ))
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT value FROM ingest_state WHERE key=?",
            ("last_successful_ingest_utc",),
        )
        row = cur.fetchone()
    value = row[0] if row else None
    response = StateIngestCursorGetResponse(
        schema_version="1.0",
        state_db=request.state_db,
        last_successful_ingest_utc=value,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="ingest_cursor_get_complete",
        module=logger.name,
        fields={"state_db": request.state_db, "last_successful_ingest_utc": value or ""},
    ))
    return response


def set_ingest_cursor(request: StateIngestCursorSetRequest, ctx: RunContext) -> None:
    logger.info(log_event(
        ctx,
        role="service",
        event="ingest_cursor_set_start",
        module=logger.name,
        fields={"state_db": request.state_db, "last_successful_ingest_utc": request.last_successful_ingest_utc},
    ))
    with _state_conn(request.state_db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO ingest_state(key, value, updated_at) VALUES(?, ?, strftime('%s','now'))",
            ("last_successful_ingest_utc", request.last_successful_ingest_utc),
        )
    logger.info(log_event(
        ctx,
        role="service",
        event="ingest_cursor_set_complete",
        module=logger.name,
        fields={"state_db": request.state_db},
    ))


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


def already_processed_batch(request: StateBatchCheckRequest, ctx: RunContext) -> StateBatchCheckResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="state_check_batch_start",
        module=logger.name,
        fields={"state_db": request.state_db, "requested": len(request.items)},
    ))
    items = _normalize_batch_items(request.items)
    if not items:
        response = StateBatchCheckResponse(
            schema_version="1.0",
            state_db=request.state_db,
            processed_items=[],
        )
        logger.info(log_event(
            ctx,
            role="service",
            event="state_check_batch_complete",
            module=logger.name,
            fields={"state_db": request.state_db, "checked": 0, "matched": 0},
        ))
        return response

    matched: list[StateBatchCheckItem] = []
    with _state_conn(request.state_db) as conn:
        for idx in range(0, len(items), BATCH_STATE_CHECK_MAX_PAIRS):
            chunk = items[idx: idx + BATCH_STATE_CHECK_MAX_PAIRS]
            where = " OR ".join("(file_id=? AND md5=?)" for _ in chunk)
            params: list[str] = []
            for item in chunk:
                params.extend((item.file_id, item.md5))
            cur = conn.execute(
                f"SELECT file_id, md5 FROM processed WHERE {where}",
                params,
            )
            for file_id, md5 in cur.fetchall():
                matched.append(
                    StateBatchCheckItem(schema_version="1.0", file_id=file_id, md5=md5)
                )

    response = StateBatchCheckResponse(
        schema_version="1.0",
        state_db=request.state_db,
        processed_items=matched,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="state_check_batch_complete",
        module=logger.name,
        fields={"state_db": request.state_db, "checked": len(items), "matched": len(matched)},
    ))
    return response


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
            "file_id, md5, processed_at, openai_file_id, vector_store_id, vector_store_status, indexed_at_utc, "
            "last_error, text_validation_status, text_validation_reason, text_validation_pages_json, doc_map_summary_json"
            ") VALUES(?, ?, strftime('%s','now'), ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                request.file_id,
                request.md5,
                request.openai_file_id,
                request.vector_store_id,
                request.vector_store_status,
                request.indexed_at_utc,
                request.last_error,
                request.text_validation_status,
                request.text_validation_reason,
                json.dumps(request.text_validation_pages) if request.text_validation_pages is not None else None,
                json.dumps(request.doc_map_summary) if request.doc_map_summary is not None else None,
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
            "SELECT file_id, md5, processed_at, openai_file_id, vector_store_id, vector_store_status, indexed_at_utc, "
            "last_error, text_validation_status, text_validation_reason, text_validation_pages_json, doc_map_summary_json "
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
    (
        file_id,
        md5,
        processed_at,
        openai_file_id,
        vector_store_id,
        vector_store_status,
        indexed_at_utc,
        last_error,
        text_validation_status,
        text_validation_reason,
        text_validation_pages_json,
        doc_map_summary_json,
    ) = row
    text_validation_pages = _parse_int_list(text_validation_pages_json)
    doc_map_summary = _parse_dict(doc_map_summary_json)
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
        text_validation_status=text_validation_status,
        text_validation_reason=text_validation_reason,
        text_validation_pages=text_validation_pages,
        doc_map_summary=doc_map_summary,
    )


def list_processed(request: StateProcessedListRequest, ctx: RunContext) -> StateProcessedListResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="state_processed_list_start",
        module=logger.name,
        fields={"state_db": request.state_db, "limit": request.limit},
    ))
    limit = int(request.limit) if isinstance(request.limit, int) else 200
    if limit <= 0:
        limit = 200
    rows: list[StateProcessedRow] = []
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT file_id, md5, processed_at, openai_file_id, vector_store_id, vector_store_status, indexed_at_utc, "
            "last_error, text_validation_status, text_validation_reason, text_validation_pages_json, doc_map_summary_json "
            "FROM processed ORDER BY processed_at DESC LIMIT ?",
            (limit,),
        )
        for (
            file_id,
            md5,
            processed_at,
            openai_file_id,
            vector_store_id,
            vector_store_status,
            indexed_at_utc,
            last_error,
            text_validation_status,
            text_validation_reason,
            text_validation_pages_json,
            doc_map_summary_json,
        ) in cur.fetchall():
            rows.append(StateProcessedRow(
                schema_version="1.0",
                file_id=file_id,
                md5=md5,
                processed_at=int(processed_at),
                openai_file_id=openai_file_id,
                vector_store_id=vector_store_id,
                vector_store_status=vector_store_status,
                indexed_at_utc=indexed_at_utc,
                last_error=last_error,
                text_validation_status=text_validation_status,
                text_validation_reason=text_validation_reason,
                text_validation_pages=_parse_int_list(text_validation_pages_json),
                doc_map_summary=_parse_dict(doc_map_summary_json),
            ))
    response = StateProcessedListResponse(schema_version="1.0", rows=rows)
    logger.info(log_event(
        ctx,
        role="service",
        event="state_processed_list_complete",
        module=logger.name,
        fields={"state_db": request.state_db, "count": len(rows)},
    ))
    return response


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


def list_published(request: StatePublishedListRequest, ctx: RunContext) -> StatePublishedListResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="state_published_list_start",
        module=logger.name,
        fields={"state_db": request.state_db, "limit": request.limit},
    ))
    limit = int(request.limit) if isinstance(request.limit, int) else 200
    if limit <= 0:
        limit = 200
    rows: list[StatePublishedRow] = []
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT file_id, md5, published_at, wp_post_id, wp_post_url "
            "FROM published ORDER BY published_at DESC LIMIT ?",
            (limit,),
        )
        for file_id, md5, published_at, wp_post_id, wp_post_url in cur.fetchall():
            rows.append(StatePublishedRow(
                schema_version="1.0",
                file_id=file_id,
                md5=md5,
                published_at=int(published_at),
                wp_post_id=int(wp_post_id),
                wp_post_url=wp_post_url,
            ))
    response = StatePublishedListResponse(schema_version="1.0", rows=rows)
    logger.info(log_event(
        ctx,
        role="service",
        event="state_published_list_complete",
        module=logger.name,
        fields={"state_db": request.state_db, "count": len(rows)},
    ))
    return response
