from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
from contextlib import contextmanager
from typing import Optional

from src.contracts.run_context import RunContext
from src.contracts.sqlite_migration import SqliteMigrationApplyRequest
from src.contracts.state import StateBatchCheckItem
from src.services.sqlite_migration_service import apply_state_db_migrations
from src.utils.errors import AppError

logger = logging.getLogger("market_lense.state_service")

ACCESS_TIMEOUT_SECONDS = 0.0
LOCK_ERROR_MARKERS = ("database is locked", "database is busy")
DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0
_STATE_CONN_LOCK = threading.Lock()
BATCH_STATE_CHECK_MAX_PAIRS = 200


@contextmanager
def _state_conn(path: str, ctx: RunContext):
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
            apply_state_db_migrations(
                SqliteMigrationApplyRequest(
                    schema_version="1.0",
                    database_key="state_db",
                    db_path=path,
                    target_version=5,
                    ctx=ctx,
                ),
                conn,
            )
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
    conn.execute(f"PRAGMA busy_timeout={max(0, int(busy_timeout_seconds * 1000))}")
    conn.execute("PRAGMA synchronous=NORMAL")


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
