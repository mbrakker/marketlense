from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

from src.contracts.run_context import RunContext
from src.contracts.sqlite_migration import SqliteMigrationApplyRequest
from src.services.sqlite_migration_service import apply_reports_db_migrations
from src.utils.errors import AppError

from .common import (
    DEFAULT_BUSY_TIMEOUT_SECONDS,
    _REPORT_CONN_LOCK,
    _configure_sqlite_connection,
)


@contextmanager
def _metadata_conn(path: str, ctx: RunContext):
    if not path:
        raise AppError(
            code="metadata_db_missing",
            message="Report metadata DB path is required",
            retryable=False,
            severity="error",
        )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(path, timeout=DEFAULT_BUSY_TIMEOUT_SECONDS)
    except sqlite3.Error as exc:
        raise AppError(
            code="metadata_db_unavailable",
            message="Failed to open report metadata DB",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": path},
        ) from exc
    try:
        _configure_sqlite_connection(
            conn,
            busy_timeout_seconds=DEFAULT_BUSY_TIMEOUT_SECONDS,
        )
        with _REPORT_CONN_LOCK:
            apply_reports_db_migrations(
                SqliteMigrationApplyRequest(
                    schema_version="1.0",
                    database_key="reports_db",
                    db_path=path,
                    target_version=12,
                    ctx=ctx,
                ),
                conn,
            )
            conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()
