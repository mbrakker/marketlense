from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

import pytest

from src.contracts.sqlite_migration import SqliteMigrationApplyRequest
from src.services.sqlite_migration_service import (
    _apply_migration_plan,
    _MigrationSpec,
    apply_state_db_migrations,
    apply_ui_run_registry_migrations,
)
from src.utils.errors import AppError
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="test_sqlite_migration_service")


def test_state_db_migrations_create_schema_version_and_ledger_on_fresh_db(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    db_path = tmp_path / "state.sqlite"
    caplog.set_level(logging.INFO)

    with sqlite3.connect(db_path) as conn:
        response = apply_state_db_migrations(
            SqliteMigrationApplyRequest(
                schema_version="1.0",
                database_key="state_db",
                db_path=str(db_path),
                target_version=10,
                ctx=_ctx(),
            ),
            conn,
        )
        ledger_rows = conn.execute(
            """
            SELECT migration_id, version
            FROM schema_migration_ledger
            WHERE database_key=?
            ORDER BY version ASC
            """,
            ("state_db",),
        ).fetchall()
        version_row = conn.execute(
            "SELECT current_version FROM schema_version WHERE database_key=?",
            ("state_db",),
        ).fetchone()
        workflow_table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='workflow_control_observations'
            """
        ).fetchone()
        mail_table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='mail_delivery_requests'
            """
        ).fetchone()
        rejection_table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='mailbox_candidate_rejections'
            """
        ).fetchone()
        artifact_cache_table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='artifact_acquisition_cache'
            """
        ).fetchone()
        remediation_table = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name='remediation_records'
            """
        ).fetchone()

    assert response.current_version == 10
    assert [step.migration_id for step in response.applied_steps] == [
        "state_db_001_create_base_tables",
        "state_db_002_add_processed_vector_columns",
        "state_db_003_add_processed_ocr_columns",
        "state_db_004_add_published_post_type",
        "state_db_005_add_report_download_final_page_url",
        "state_db_006_create_workflow_control_observations",
        "state_db_007_create_mail_delivery_requests",
        "state_db_008_create_mailbox_candidate_rejections",
        "state_db_009_create_artifact_acquisition_cache",
        "state_db_010_create_remediation_ledger",
    ]
    assert ledger_rows == [
        ("state_db_001_create_base_tables", 1),
        ("state_db_002_add_processed_vector_columns", 2),
        ("state_db_003_add_processed_ocr_columns", 3),
        ("state_db_004_add_published_post_type", 4),
        ("state_db_005_add_report_download_final_page_url", 5),
        ("state_db_006_create_workflow_control_observations", 6),
        ("state_db_007_create_mail_delivery_requests", 7),
        ("state_db_008_create_mailbox_candidate_rejections", 8),
        ("state_db_009_create_artifact_acquisition_cache", 9),
        ("state_db_010_create_remediation_ledger", 10),
    ]
    assert version_row == (10,)
    assert workflow_table == ("workflow_control_observations",)
    assert mail_table == ("mail_delivery_requests",)
    assert rejection_table == ("mailbox_candidate_rejections",)
    assert artifact_cache_table == ("artifact_acquisition_cache",)
    assert remediation_table == ("remediation_records",)
    assert_logs_have_required_fields(caplog.records)


def test_sqlite_migration_failure_rolls_back_schema_changes(
    tmp_path: Path,
    assert_app_error,
) -> None:
    db_path = tmp_path / "broken.sqlite"

    def _failing_migration(conn: sqlite3.Connection) -> None:
        conn.execute("CREATE TABLE broken_table(id INTEGER PRIMARY KEY)")
        conn.execute("INSERT INTO broken_table(id) VALUES(1)")
        raise RuntimeError("boom")

    with sqlite3.connect(db_path) as conn:
        with pytest.raises(AppError) as exc_info:
            _apply_migration_plan(
                SqliteMigrationApplyRequest(
                    schema_version="1.0",
                    database_key="broken_db",
                    db_path=str(db_path),
                    target_version=1,
                    ctx=_ctx(),
                ),
                conn,
                (
                    _MigrationSpec(
                        migration_id="broken_db_001_fail",
                        version=1,
                        apply_fn=_failing_migration,
                    ),
                ),
            )

    assert_app_error(
        exc_info.value,
        code="sqlite_migration_failed",
        retryable=False,
        severity="error",
    )
    with sqlite3.connect(db_path) as conn:
        version_row = conn.execute(
            "SELECT current_version FROM schema_version WHERE database_key=?",
            ("broken_db",),
        ).fetchone()
        ledger_count = conn.execute(
            "SELECT COUNT(*) FROM schema_migration_ledger WHERE database_key=?",
            ("broken_db",),
        ).fetchone()[0]
        broken_table = conn.execute(
            """
            SELECT 1
            FROM sqlite_master
            WHERE type='table' AND name='broken_table'
            """
        ).fetchone()

    assert version_row is None
    assert ledger_count == 0
    assert broken_table is None


def test_ui_run_registry_migrations_are_idempotent_on_rerun(tmp_path: Path) -> None:
    db_path = tmp_path / "ui_runs.sqlite"
    request = SqliteMigrationApplyRequest(
        schema_version="1.0",
        database_key="ui_run_registry",
        db_path=str(db_path),
        target_version=3,
        ctx=_ctx(),
    )

    with sqlite3.connect(db_path) as conn:
        first = apply_ui_run_registry_migrations(request, conn)
        second = apply_ui_run_registry_migrations(request, conn)
        ledger_count = conn.execute(
            "SELECT COUNT(*) FROM schema_migration_ledger WHERE database_key=?",
            ("ui_run_registry",),
        ).fetchone()[0]
        dead_letter_tables = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type='table' AND name IN ('ui_run_dead_letters', 'ui_run_dead_letter_actions')
            ORDER BY name ASC
            """
        ).fetchall()

    assert first.current_version == 3
    assert [step.migration_id for step in first.applied_steps] == [
        "ui_run_registry_001_create_ui_runs",
        "ui_run_registry_002_add_dead_letter_ledger",
        "ui_run_registry_003_add_remediation_context",
    ]
    assert second.current_version == 3
    assert second.applied_steps == ()
    assert ledger_count == 3
    assert dead_letter_tables == [
        ("ui_run_dead_letter_actions",),
        ("ui_run_dead_letters",),
    ]
