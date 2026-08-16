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
from src.services._sqlite_common import table_exists as _table_exists
from src.utils.clock import utc_now_seconds_iso as _utc_now
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

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


def _llm_usage_001_create_budget_authority_tables(conn: sqlite3.Connection) -> None:
    """Add policy state to the canonical LLM ledger without a second cost ledger."""
    conn.execute(
        """
        create table if not exists budget_authority_reservations (
            reservation_key text primary key,
            schema_version text not null,
            run_id text not null,
            workflow_id text not null,
            publisher_name text not null,
            report_id text not null,
            resource_type text not null,
            operation text not null,
            day_utc text not null,
            estimated_cost_usd real not null,
            estimated_tokens integer not null,
            estimated_calls integer not null,
            estimated_steps integer not null,
            estimated_writes integer not null,
            estimated_pdfs integer not null,
            estimated_duration_seconds integer not null,
            status text not null,
            expires_at_utc text not null,
            created_at_utc text not null,
            released_at_utc text not null default '',
            reconciled_at_utc text not null default ''
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_budget_authority_reservations_scope
        on budget_authority_reservations(
            day_utc, run_id, publisher_name, status, expires_at_utc
        )
        """
    )
    conn.execute(
        """
        create table if not exists budget_authority_events (
            id integer primary key autoincrement,
            schema_version text not null,
            timestamp_utc text not null,
            run_id text not null,
            workflow_id text not null,
            publisher_name text not null,
            report_id text not null,
            resource_type text not null,
            operation text not null,
            decision text not null,
            reason_code text not null,
            policy_version text not null,
            reservation_key text not null default '',
            override_actor text not null default '',
            override_scope text not null default '',
            override_reason text not null default '',
            override_expires_at_utc text not null default '',
            details_json text not null default '{}'
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_budget_authority_events_scope
        on budget_authority_events(run_id, workflow_id, publisher_name, timestamp_utc)
        """
    )


def _llm_usage_002_add_side_effect_actuals_and_deferred_work(
    conn: sqlite3.Connection,
) -> None:
    """Retain final non-provider usage and actionable deferrals in the same DB.

    Provider monetary actuals intentionally remain only in ``llm_usage_events``;
    this table records the non-monetary side effects that that ledger cannot
    describe without manufacturing a provider-cost record.
    """
    _add_column_if_missing(
        conn,
        table_name="budget_authority_reservations",
        column_name="estimated_drive_reads",
        column_type="INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        conn,
        table_name="budget_authority_reservations",
        column_name="estimated_mailbox_reads",
        column_type="INTEGER NOT NULL DEFAULT 0",
    )
    conn.execute(
        """
        create table if not exists budget_authority_actuals (
            reservation_key text primary key,
            schema_version text not null,
            finalized_at_utc text not null,
            run_id text not null,
            workflow_id text not null,
            publisher_name text not null,
            report_id text not null,
            resource_type text not null,
            operation text not null,
            day_utc text not null,
            outcome text not null,
            error_code text not null default '',
            actual_tokens integer not null default 0,
            actual_calls integer not null default 0,
            actual_steps integer not null default 0,
            actual_duration_seconds integer not null default 0,
            actual_retries integer not null default 0,
            actual_browser_launches integer not null default 0,
            actual_drive_writes integer not null default 0,
            actual_drive_reads integer not null default 0,
            actual_wordpress_writes integer not null default 0,
            actual_pdfs integer not null default 0,
            actual_mailbox_reads integer not null default 0
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_budget_authority_actuals_scope
        on budget_authority_actuals(
            day_utc, run_id, publisher_name, resource_type, finalized_at_utc
        )
        """
    )
    conn.execute(
        """
        create table if not exists budget_authority_deferred_work (
            work_key text primary key,
            schema_version text not null,
            deferred_at_utc text not null,
            run_id text not null,
            workflow_id text not null,
            publisher_name text not null,
            report_id text not null,
            resource_type text not null,
            operation text not null,
            idempotency_key text not null,
            next_action text not null,
            affected_limit text not null,
            policy_version text not null,
            status text not null default 'pending'
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_budget_authority_deferred_work_pending
        on budget_authority_deferred_work(status, run_id, workflow_id, deferred_at_utc)
        """
    )


def _llm_usage_003_expand_deferred_work_recovery_state(
    conn: sqlite3.Connection,
) -> None:
    """Upgrade budget-deferral audit rows into leaseable recovery work.

    The table deliberately stays in the canonical usage ledger: a budget decision
    and its durable recovery record must commit together, without a second queue
    or cross-database best-effort handoff.
    """
    required = {
        "stage": "TEXT NOT NULL DEFAULT ''",
        "source_id": "TEXT NOT NULL DEFAULT ''",
        "plan_hash": "TEXT NOT NULL DEFAULT ''",
        "reason_code": "TEXT NOT NULL DEFAULT 'budget_limit_reached'",
        "earliest_run_at_utc": "TEXT NOT NULL DEFAULT ''",
        "deadline_at_utc": "TEXT NOT NULL DEFAULT ''",
        "attempt_count": "INTEGER NOT NULL DEFAULT 0",
        "max_attempts": "INTEGER NOT NULL DEFAULT 3",
        "reusable_artifacts_json": "TEXT NOT NULL DEFAULT '[]'",
        "lease_owner": "TEXT NOT NULL DEFAULT ''",
        "lease_expires_at_utc": "TEXT NOT NULL DEFAULT ''",
        "terminal_status": "TEXT NOT NULL DEFAULT ''",
        "remediation_id": "TEXT NOT NULL DEFAULT ''",
        "updated_at_utc": "TEXT NOT NULL DEFAULT ''",
        "completed_at_utc": "TEXT NOT NULL DEFAULT ''",
        "defer_count": "INTEGER NOT NULL DEFAULT 1",
        "budget_request_json": "TEXT NOT NULL DEFAULT '{}'",
    }
    for column_name, column_type in required.items():
        _add_column_if_missing(
            conn,
            table_name="budget_authority_deferred_work",
            column_name=column_name,
            column_type=column_type,
        )
    conn.execute(
        """
        UPDATE budget_authority_deferred_work
        SET earliest_run_at_utc=deferred_at_utc
        WHERE earliest_run_at_utc=''
        """
    )
    conn.execute(
        """
        UPDATE budget_authority_deferred_work
        SET updated_at_utc=deferred_at_utc
        WHERE updated_at_utc=''
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_budget_authority_deferred_work_due
        ON budget_authority_deferred_work(
            status, earliest_run_at_utc, lease_expires_at_utc, deferred_at_utc
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_budget_authority_deferred_work_workflow
        ON budget_authority_deferred_work(workflow_id, status, updated_at_utc DESC)
        """
    )


def _llm_usage_004_add_task_attribution_to_actuals(
    conn: sqlite3.Connection,
) -> None:
    """Attribute durable non-provider measurements to the creating task.

    Provider usage has always carried ``RunContext`` task identifiers in
    ``llm_usage_events``.  Reservations, final actuals, and direct side-effect
    events need the same scope so acquisition telemetry can be read without
    subtracting concurrent run totals.
    """
    for table_name in (
        "budget_authority_reservations",
        "budget_authority_actuals",
    ):
        _add_column_if_missing(
            conn,
            table_name=table_name,
            column_name="task_id",
            column_type="TEXT NOT NULL DEFAULT ''",
        )
        _add_column_if_missing(
            conn,
            table_name=table_name,
            column_name="span_id",
            column_type="TEXT NOT NULL DEFAULT ''",
        )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_budget_authority_actuals_run_task
        ON budget_authority_actuals(run_id, task_id)
        """
    )


_LLM_USAGE_LEDGER_MIGRATIONS: tuple[_MigrationSpec, ...] = (
    _MigrationSpec(
        migration_id="llm_usage_ledger_001_create_budget_authority_tables",
        version=1,
        apply_fn=_llm_usage_001_create_budget_authority_tables,
    ),
    _MigrationSpec(
        migration_id="llm_usage_ledger_002_add_side_effect_actuals_and_deferred_work",
        version=2,
        apply_fn=_llm_usage_002_add_side_effect_actuals_and_deferred_work,
    ),
    _MigrationSpec(
        migration_id="llm_usage_ledger_003_expand_deferred_work_recovery_state",
        version=3,
        apply_fn=_llm_usage_003_expand_deferred_work_recovery_state,
    ),
    _MigrationSpec(
        migration_id="llm_usage_ledger_004_add_task_attribution_to_actuals",
        version=4,
        apply_fn=_llm_usage_004_add_task_attribution_to_actuals,
    ),
)
