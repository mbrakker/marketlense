from __future__ import annotations

import sqlite3

import pytest

from src.contracts.run_context import RunContext
from src.orchestrators import ingest_orchestrator
from src.orchestrators._ingest_orchestrator import db_preflight, lock_lifecycle
from src.utils.errors import AppError


def test_ingest_orchestrator_keeps_run_ingest_facade_and_private_owners() -> None:
    assert callable(ingest_orchestrator.run_ingest)
    assert callable(lock_lifecycle.acquire_ingest_lock)
    assert callable(lock_lifecycle.finalize_ingest_run)
    assert callable(db_preflight.verify_ingest_db_access)


def test_ingest_facade_delegates_lock_and_db_lifecycle() -> None:
    source = ingest_orchestrator.__loader__.get_source(ingest_orchestrator.__name__)

    assert "acquire_ingest_lock(settings, lock_ctx)" in source
    assert "verify_ingest_db_access(settings, root_ctx)" in source
    assert "finalize_ingest_run(" in source
    assert "def _acquire_ingest_lock" not in source
    assert "def _verify_ingest_db_access" not in source


def test_ingest_db_preflight_accepts_writable_databases(ingest_settings) -> None:
    db_preflight.verify_ingest_db_access(
        ingest_settings,
        RunContext("1.0", "run", "ingest", "span"),
    )


@pytest.mark.parametrize("locked_database", ["state_db", "reports_db"])
def test_ingest_db_preflight_reports_the_locked_database(
    ingest_settings, locked_database
) -> None:
    path = getattr(ingest_settings, locked_database)
    connection = sqlite3.connect(path)
    connection.execute("BEGIN EXCLUSIVE")
    try:
        with pytest.raises(AppError) as error:
            db_preflight.verify_ingest_db_access(
                ingest_settings,
                RunContext("1.0", "run", "ingest", "span"),
            )
    finally:
        connection.rollback()
        connection.close()

    assert error.value.code == "db_locked"
    assert error.value.retryable is False
    assert error.value.context[f"{locked_database}_locked"] is True


def test_ingest_lock_lifecycle_acquires_and_releases_real_lock(ingest_settings) -> None:
    ctx = RunContext("1.0", "run", "ingest-lock", "span")

    lock_info = lock_lifecycle.acquire_ingest_lock(ingest_settings, ctx)

    assert lock_info is not None
    assert lock_info.owner_id == "ingest:run"
    lock_lifecycle.finalize_ingest_run(lock_ctx=ctx, lock_info=lock_info)
    reacquired = lock_lifecycle.acquire_ingest_lock(ingest_settings, ctx)
    assert reacquired is not None
    lock_lifecycle.finalize_ingest_run(lock_ctx=ctx, lock_info=reacquired)
