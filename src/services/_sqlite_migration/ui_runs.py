from __future__ import annotations

import sqlite3

from .runner import _MigrationSpec, _add_column_if_missing

_UI_RUNS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ui_runs (
  run_id TEXT PRIMARY KEY,
  run_type TEXT NOT NULL,
  display_name TEXT NOT NULL,
  status TEXT NOT NULL,
  request_payload_json TEXT NOT NULL,
  command_json TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  started_at_utc TEXT NOT NULL DEFAULT '',
  finished_at_utc TEXT NOT NULL DEFAULT '',
  output_path TEXT NOT NULL DEFAULT '',
  request_path TEXT NOT NULL DEFAULT '',
  artifact_paths_json TEXT NOT NULL DEFAULT '[]',
  result_summary_json TEXT NOT NULL DEFAULT '{}',
  pid INTEGER,
  exit_code INTEGER,
  error_code TEXT NOT NULL DEFAULT '',
  error_message TEXT NOT NULL DEFAULT '',
  error_retryable INTEGER,
  error_severity TEXT NOT NULL DEFAULT ''
);
"""

_UI_RUN_DEAD_LETTERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ui_run_dead_letters (
  run_id TEXT PRIMARY KEY,
  run_type TEXT NOT NULL,
  display_name TEXT NOT NULL,
  run_status TEXT NOT NULL,
  triage_status TEXT NOT NULL,
  triage_category TEXT NOT NULL,
  triage_reason TEXT NOT NULL,
  error_code TEXT NOT NULL,
  error_message TEXT NOT NULL,
  error_retryable INTEGER NOT NULL,
  error_severity TEXT NOT NULL,
  error_stage TEXT NOT NULL,
  publisher_name TEXT NOT NULL DEFAULT '',
  publisher_insights_url TEXT NOT NULL DEFAULT '',
  report_url TEXT NOT NULL DEFAULT '',
  output_path TEXT NOT NULL DEFAULT '',
  request_path TEXT NOT NULL DEFAULT '',
  manifest_path TEXT NOT NULL DEFAULT '',
  artifact_paths_json TEXT NOT NULL DEFAULT '[]',
  result_summary_json TEXT NOT NULL DEFAULT '{}',
  first_failed_at_utc TEXT NOT NULL,
  last_failed_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  recovery_run_id TEXT NOT NULL DEFAULT '',
  last_action TEXT NOT NULL DEFAULT 'auto_triaged',
  last_action_note TEXT NOT NULL DEFAULT '',
  last_action_at_utc TEXT NOT NULL DEFAULT ''
);
"""

_UI_RUN_DEAD_LETTER_ACTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ui_run_dead_letter_actions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT NOT NULL,
  action TEXT NOT NULL,
  actor TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  related_run_id TEXT NOT NULL DEFAULT '',
  created_at_utc TEXT NOT NULL
);
"""


def _ui_run_registry_001_create_ui_runs(conn: sqlite3.Connection) -> None:
    conn.execute(_UI_RUNS_TABLE_SQL)


def _ui_run_registry_002_add_dead_letter_ledger(conn: sqlite3.Connection) -> None:
    conn.execute(_UI_RUNS_TABLE_SQL)
    _add_column_if_missing(
        conn,
        table_name="ui_runs",
        column_name="error_retryable",
        column_type="INTEGER",
    )
    _add_column_if_missing(
        conn,
        table_name="ui_runs",
        column_name="error_severity",
        column_type="TEXT NOT NULL DEFAULT ''",
    )
    conn.execute(_UI_RUN_DEAD_LETTERS_TABLE_SQL)
    conn.execute(_UI_RUN_DEAD_LETTER_ACTIONS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ui_run_dead_letters_triage_status ON ui_run_dead_letters(triage_status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ui_run_dead_letters_triage_category ON ui_run_dead_letters(triage_category)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ui_run_dead_letters_last_failed_at_utc ON ui_run_dead_letters(last_failed_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_ui_run_dead_letter_actions_run_id_created_at_utc ON ui_run_dead_letter_actions(run_id, created_at_utc DESC)"
    )


_UI_RUN_REGISTRY_MIGRATIONS: tuple[_MigrationSpec, ...] = (
    _MigrationSpec(
        migration_id="ui_run_registry_001_create_ui_runs",
        version=1,
        apply_fn=_ui_run_registry_001_create_ui_runs,
    ),
    _MigrationSpec(
        migration_id="ui_run_registry_002_add_dead_letter_ledger",
        version=2,
        apply_fn=_ui_run_registry_002_add_dead_letter_ledger,
    ),
)
