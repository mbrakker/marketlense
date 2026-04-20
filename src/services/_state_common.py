from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional

from src.contracts.state import StateBatchCheckItem
from src.utils.errors import AppError

logger = logging.getLogger("market_lense.state_service")

ACCESS_TIMEOUT_SECONDS = 0.0
LOCK_ERROR_MARKERS = ("database is locked", "database is busy")
DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0
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
  doc_map_summary_json TEXT,
  ocr_fallback_used INTEGER NOT NULL DEFAULT 0,
  ocr_pdf_path TEXT
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
  wp_post_url TEXT NOT NULL,
  post_type TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS report_download_routes (
  normalized_url TEXT PRIMARY KEY,
  source_url TEXT NOT NULL,
  route_kind TEXT NOT NULL,
  route_summary TEXT NOT NULL,
  outcome TEXT NOT NULL,
  last_downloaded_file_path TEXT,
  last_final_page_url TEXT,
  updated_at INTEGER NOT NULL
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
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    try:
        conn = sqlite3.connect(path, timeout=DEFAULT_BUSY_TIMEOUT_SECONDS)
    except sqlite3.Error as exc:
        raise AppError(
            code="state_db_unavailable",
            message="Failed to open state DB",
            cause=exc,
            retryable=True,
            context={"state_db": path},
        ) from exc
    try:
        _configure_sqlite_connection(
            conn,
            busy_timeout_seconds=DEFAULT_BUSY_TIMEOUT_SECONDS,
        )
        with _STATE_CONN_LOCK:
            conn.executescript(DDL)
            _migrate_schema(conn)
            conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _configure_sqlite_connection(
    conn: sqlite3.Connection,
    *,
    busy_timeout_seconds: float,
) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        f"PRAGMA busy_timeout={max(0, int(busy_timeout_seconds * 1000))}"
    )
    conn.execute("PRAGMA synchronous=NORMAL")


def _migrate_schema(conn: sqlite3.Connection) -> None:
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
        "ocr_fallback_used": "INTEGER NOT NULL DEFAULT 0",
        "ocr_pdf_path": "TEXT",
    }
    for col, col_type in required.items():
        if col not in cols:
            conn.execute(f"ALTER TABLE processed ADD COLUMN {col} {col_type}")

    published_cols = {row[1] for row in conn.execute("PRAGMA table_info(published)")}
    if "post_type" not in published_cols:
        conn.execute(
            "ALTER TABLE published ADD COLUMN post_type TEXT NOT NULL DEFAULT ''"
        )

    route_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(report_download_routes)")
    }
    if route_cols and "last_final_page_url" not in route_cols:
        conn.execute(
            "ALTER TABLE report_download_routes ADD COLUMN last_final_page_url TEXT"
        )


def _normalize_post_type(post_type: str) -> str:
    token = str(post_type).strip().strip("/")
    return token or "posts"


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


def _normalize_batch_items(
    items: list[StateBatchCheckItem],
) -> list[StateBatchCheckItem]:
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
        normalized.append(
            StateBatchCheckItem(schema_version="1.0", file_id=file_id, md5=md5)
        )
    return normalized
