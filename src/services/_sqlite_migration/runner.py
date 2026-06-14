from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from typing import Callable, Sequence

from src.contracts.sqlite_migration import (
    SqliteMigrationAppliedStep,
    SqliteMigrationApplyRequest,
    SqliteMigrationApplyResponse,
)
from src.utils.clock import utc_now_seconds_iso as _utc_now
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url
from src.services._sqlite_common import table_exists as _table_exists

logger = logging.getLogger("market_lense.sqlite_migration_service")

_LEDGER_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
  database_key TEXT PRIMARY KEY,
  current_version INTEGER NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS schema_migration_ledger (
  database_key TEXT NOT NULL,
  migration_id TEXT NOT NULL,
  version INTEGER NOT NULL,
  applied_at_utc TEXT NOT NULL,
  duration_ms INTEGER NOT NULL,
  PRIMARY KEY(database_key, migration_id)
);

CREATE INDEX IF NOT EXISTS idx_schema_migration_ledger_database_version
  ON schema_migration_ledger(database_key, version);
"""


@dataclass(frozen=True)
class _MigrationSpec:
    migration_id: str
    version: int
    apply_fn: Callable[[sqlite3.Connection], None]


def _apply_migration_plan(
    request: SqliteMigrationApplyRequest,
    conn: sqlite3.Connection,
    migrations: Sequence[_MigrationSpec],
) -> SqliteMigrationApplyResponse:
    if request.target_version != len(migrations):
        raise AppError(
            code="sqlite_migration_target_version_invalid",
            message="Configured SQLite migration target version does not match the migration plan",
            retryable=False,
            severity="error",
            context={
                "database_key": request.database_key,
                "target_version": request.target_version,
                "plan_length": len(migrations),
            },
        )
    conn.executescript(_LEDGER_DDL)
    conn.commit()
    current_version = _current_version(conn, request.database_key)
    applied_ids = _applied_migration_ids(conn, request.database_key)
    pending = [
        migration
        for migration in migrations
        if migration.migration_id not in applied_ids
    ]
    logger.info(
        log_event(
            request.ctx,
            role="service",
            event="sqlite_migration_ledger_start",
            module=logger.name,
            fields={
                "database_key": request.database_key,
                "db_path": request.db_path,
                "current_version": current_version,
                "target_version": request.target_version,
                "pending_migration_ids": [
                    migration.migration_id for migration in pending
                ],
            },
        )
    )
    applied_steps: list[SqliteMigrationAppliedStep] = []
    for migration in pending:
        started = time.perf_counter()
        try:
            conn.execute("BEGIN IMMEDIATE")
            migration.apply_fn(conn)
            applied_at_utc = _utc_now()
            duration_ms = max(0, int((time.perf_counter() - started) * 1000))
            conn.execute(
                """
                INSERT INTO schema_migration_ledger(
                    database_key,
                    migration_id,
                    version,
                    applied_at_utc,
                    duration_ms
                )
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    request.database_key,
                    migration.migration_id,
                    migration.version,
                    applied_at_utc,
                    duration_ms,
                ),
            )
            conn.execute(
                """
                INSERT INTO schema_version(database_key, current_version, updated_at_utc)
                VALUES(?, ?, ?)
                ON CONFLICT(database_key) DO UPDATE SET
                    current_version=excluded.current_version,
                    updated_at_utc=excluded.updated_at_utc
                """,
                (request.database_key, migration.version, applied_at_utc),
            )
            conn.commit()
        except Exception as exc:
            conn.rollback()
            logger.info(
                log_event(
                    request.ctx,
                    role="service",
                    event="sqlite_migration_failed",
                    module=logger.name,
                    fields={
                        "database_key": request.database_key,
                        "db_path": request.db_path,
                        "migration_id": migration.migration_id,
                        "target_version": migration.version,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                )
            )
            raise AppError(
                code="sqlite_migration_failed",
                message="SQLite schema migration failed",
                cause=exc,
                retryable=False,
                severity="error",
                context={
                    "database_key": request.database_key,
                    "db_path": request.db_path,
                    "migration_id": migration.migration_id,
                    "target_version": migration.version,
                },
            ) from exc
        applied_step = SqliteMigrationAppliedStep(
            schema_version="1.0",
            migration_id=migration.migration_id,
            version=migration.version,
            duration_ms=duration_ms,
        )
        applied_steps.append(applied_step)
        logger.info(
            log_event(
                request.ctx,
                role="service",
                event="sqlite_migration_applied",
                module=logger.name,
                fields={
                    "database_key": request.database_key,
                    "db_path": request.db_path,
                    "migration_id": migration.migration_id,
                    "version": migration.version,
                    "duration_ms": duration_ms,
                },
            )
        )
    final_version = _current_version(conn, request.database_key)
    response = SqliteMigrationApplyResponse(
        schema_version="1.0",
        database_key=request.database_key,
        current_version=final_version,
        applied_steps=tuple(applied_steps),
    )
    logger.info(
        log_event(
            request.ctx,
            role="service",
            event="sqlite_migration_ledger_complete",
            module=logger.name,
            fields={
                "database_key": request.database_key,
                "db_path": request.db_path,
                "current_version": response.current_version,
                "applied_migration_ids": [
                    step.migration_id for step in response.applied_steps
                ],
            },
        )
    )
    return response


def _current_version(conn: sqlite3.Connection, database_key: str) -> int:
    row = conn.execute(
        "SELECT current_version FROM schema_version WHERE database_key=?",
        (database_key,),
    ).fetchone()
    return int(row[0]) if row is not None else 0


def _applied_migration_ids(conn: sqlite3.Connection, database_key: str) -> set[str]:
    rows = conn.execute(
        """
        SELECT migration_id
        FROM schema_migration_ledger
        WHERE database_key=?
        ORDER BY version ASC, migration_id ASC
        """,
        (database_key,),
    ).fetchall()
    return {str(row[0]) for row in rows}


def _normalize_url_key(url: object) -> str:
    token = str(url or "").strip()
    if not token:
        return ""
    return normalize_url(token)


def _fetch_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
    if not _table_exists(conn, table_name):
        return set()
    return {
        str(row[1])
        for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()
    }


def _add_column_if_missing(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    if column_name not in _fetch_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")
