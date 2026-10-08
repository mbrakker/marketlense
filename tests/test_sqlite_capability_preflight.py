from __future__ import annotations

import sqlite3
from pathlib import Path

from src.contracts.sqlite_migration import (
    SqliteCapabilityInspectionRequest,
    SqliteMigrationApplyRequest,
)
from src.services.sqlite_migration_service import (
    apply_state_db_migrations,
    inspect_sqlite_capability,
)
from src.services.config_service import new_runtime_context


def _migrate_state_db(path: Path) -> None:
    conn = sqlite3.connect(path)
    try:
        apply_state_db_migrations(
            SqliteMigrationApplyRequest(
                schema_version="1.0",
                database_key="state_db",
                db_path=str(path),
                target_version=16,
                ctx=new_runtime_context(task_id="test_sqlite_capability_migration"),
            ),
            conn,
        )
    finally:
        conn.close()


def test_inspect_sqlite_capability_accepts_current_database_without_migrating(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite"
    _migrate_state_db(path)
    before = path.read_bytes()

    result = inspect_sqlite_capability(
        SqliteCapabilityInspectionRequest(
            schema_version="1.0",
            database_key="state_db",
            db_path=str(path),
            lock_timeout_seconds=0.05,
        ),
        new_runtime_context(task_id="test_sqlite_capability_ready"),
    )

    assert result.status == "ready"
    assert result.current_version == result.expected_version == 16
    assert result.integrity_ok is True
    assert result.foreign_keys_ok is True
    assert result.write_lock_available is True
    assert path.read_bytes() == before


def test_inspect_sqlite_capability_rejects_schema_mismatch_without_migration(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite"
    _migrate_state_db(path)
    conn = sqlite3.connect(path)
    conn.execute(
        "UPDATE schema_version SET current_version=14 WHERE database_key='state_db'"
    )
    conn.commit()
    conn.close()

    result = inspect_sqlite_capability(
        SqliteCapabilityInspectionRequest(
            schema_version="1.0", database_key="state_db", db_path=str(path)
        ),
        new_runtime_context(task_id="test_sqlite_capability_schema"),
    )

    assert result.status == "blocked"
    assert result.reason_code == "sqlite_schema_incompatible"
    assert result.current_version == 14
    assert result.expected_version == 16


def test_inspect_sqlite_capability_does_not_create_missing_database(
    tmp_path: Path,
) -> None:
    path = tmp_path / "missing.sqlite"

    result = inspect_sqlite_capability(
        SqliteCapabilityInspectionRequest(
            schema_version="1.0", database_key="state_db", db_path=str(path)
        ),
        new_runtime_context(task_id="test_sqlite_capability_missing"),
    )

    assert result.status == "blocked"
    assert result.reason_code == "sqlite_database_missing"
    assert not path.exists()


def test_inspect_sqlite_capability_reports_corrupt_database(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.sqlite"
    path.write_bytes(b"not a sqlite database")

    result = inspect_sqlite_capability(
        SqliteCapabilityInspectionRequest(
            schema_version="1.0", database_key="state_db", db_path=str(path)
        ),
        new_runtime_context(task_id="test_sqlite_capability_corrupt"),
    )

    assert result.status == "blocked"
    assert result.reason_code == "sqlite_integrity_failed"


def test_inspect_sqlite_capability_reports_bounded_writer_lock_contention(
    tmp_path: Path,
) -> None:
    path = tmp_path / "state.sqlite"
    _migrate_state_db(path)
    blocker = sqlite3.connect(path, timeout=0.1)
    blocker.execute("BEGIN IMMEDIATE")
    try:
        result = inspect_sqlite_capability(
            SqliteCapabilityInspectionRequest(
                schema_version="1.0",
                database_key="state_db",
                db_path=str(path),
                lock_timeout_seconds=0.01,
            ),
            new_runtime_context(task_id="test_sqlite_capability_lock"),
        )
    finally:
        blocker.rollback()
        blocker.close()

    assert result.status == "degraded"
    assert result.reason_code == "sqlite_write_lock_busy"
    assert result.retryable is True
