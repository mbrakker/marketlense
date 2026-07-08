from __future__ import annotations

import sqlite3

from .runner import _MigrationSpec, _add_column_if_missing

_STATE_PROCESSED_TABLE_SQL = """
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
"""

_STATE_INGEST_STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS ingest_state (
  key TEXT PRIMARY KEY,
  value TEXT,
  updated_at INTEGER NOT NULL
);
"""

_STATE_PUBLISHED_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS published (
  file_id TEXT PRIMARY KEY,
  md5 TEXT NOT NULL,
  published_at INTEGER NOT NULL,
  wp_post_id INTEGER NOT NULL,
  wp_post_url TEXT NOT NULL,
  post_type TEXT NOT NULL DEFAULT ''
);
"""

_STATE_DOWNLOAD_ROUTES_TABLE_SQL = """
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

_STATE_WORKFLOW_CONTROL_OBSERVATIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS workflow_control_observations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  observed_at_utc TEXT NOT NULL,
  run_id TEXT NOT NULL,
  workflow TEXT NOT NULL,
  step_name TEXT NOT NULL,
  route TEXT NOT NULL,
  publisher TEXT NOT NULL DEFAULT '',
  report_key TEXT NOT NULL DEFAULT '',
  outcome TEXT NOT NULL,
  error_code TEXT NOT NULL DEFAULT '',
  error_retryable INTEGER NOT NULL DEFAULT 0,
  error_severity TEXT NOT NULL DEFAULT '',
  latency_ms INTEGER NOT NULL DEFAULT 0,
  cost_usd REAL NOT NULL DEFAULT 0.0,
  retry_count INTEGER NOT NULL DEFAULT 0,
  resource_pressure_json TEXT NOT NULL DEFAULT '{}'
);
"""

_STATE_MAIL_DELIVERY_REQUESTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS mail_delivery_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  idempotency_key TEXT NOT NULL UNIQUE,
  source_url TEXT NOT NULL,
  report_title TEXT NOT NULL DEFAULT '',
  publisher_name TEXT NOT NULL DEFAULT '',
  delivery_email TEXT NOT NULL DEFAULT '',
  requested_after_utc TEXT NOT NULL,
  route_family TEXT NOT NULL DEFAULT '',
  route_history_id TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  next_attempt_after_utc TEXT NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  provider_cursor TEXT NOT NULL DEFAULT '',
  seen_provider_message_ids_json TEXT NOT NULL DEFAULT '[]',
  outcome TEXT NOT NULL DEFAULT '',
  selected_message_id TEXT NOT NULL DEFAULT '',
  downloaded_file_path TEXT NOT NULL DEFAULT '',
  error_code TEXT NOT NULL DEFAULT '',
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);
"""

_STATE_MAILBOX_CANDIDATE_REJECTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS mailbox_candidate_rejections (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  request_id INTEGER NOT NULL,
  provider_message_id TEXT NOT NULL,
  sender TEXT NOT NULL DEFAULT '',
  source_host TEXT NOT NULL DEFAULT '',
  link_host TEXT NOT NULL DEFAULT '',
  publisher_affinity TEXT NOT NULL DEFAULT '',
  title_token_overlap REAL NOT NULL DEFAULT 0.0,
  reason_code TEXT NOT NULL,
  expires_at_utc TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  UNIQUE(request_id, provider_message_id, link_host, reason_code)
);
"""


def _state_db_001_create_base_tables(conn: sqlite3.Connection) -> None:
    conn.execute(_STATE_PROCESSED_TABLE_SQL)
    conn.execute(_STATE_INGEST_STATE_TABLE_SQL)
    conn.execute(_STATE_PUBLISHED_TABLE_SQL)
    conn.execute(_STATE_DOWNLOAD_ROUTES_TABLE_SQL)


def _state_db_002_add_processed_vector_columns(conn: sqlite3.Connection) -> None:
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
    for column_name, column_type in required.items():
        _add_column_if_missing(
            conn,
            table_name="processed",
            column_name=column_name,
            column_type=column_type,
        )


def _state_db_003_add_processed_ocr_columns(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn,
        table_name="processed",
        column_name="ocr_fallback_used",
        column_type="INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        conn,
        table_name="processed",
        column_name="ocr_pdf_path",
        column_type="TEXT",
    )


def _state_db_004_add_published_post_type(conn: sqlite3.Connection) -> None:
    _add_column_if_missing(
        conn,
        table_name="published",
        column_name="post_type",
        column_type="TEXT NOT NULL DEFAULT ''",
    )


def _state_db_005_add_report_download_final_page_url(
    conn: sqlite3.Connection,
) -> None:
    _add_column_if_missing(
        conn,
        table_name="report_download_routes",
        column_name="last_final_page_url",
        column_type="TEXT",
    )


def _state_db_006_create_workflow_control_observations(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_STATE_WORKFLOW_CONTROL_OBSERVATIONS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_control_observations_workflow_time "
        "ON workflow_control_observations(workflow, observed_at_utc DESC)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_workflow_control_observations_publisher "
        "ON workflow_control_observations(publisher, observed_at_utc DESC)"
    )


def _state_db_007_create_mail_delivery_requests(conn: sqlite3.Connection) -> None:
    conn.execute(_STATE_MAIL_DELIVERY_REQUESTS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mail_delivery_requests_due "
        "ON mail_delivery_requests(status, next_attempt_after_utc, id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mail_delivery_requests_source "
        "ON mail_delivery_requests(source_url, delivery_email)"
    )


def _state_db_008_create_mailbox_candidate_rejections(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_STATE_MAILBOX_CANDIDATE_REJECTIONS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_mailbox_candidate_rejections_request "
        "ON mailbox_candidate_rejections(request_id, expires_at_utc)"
    )


_STATE_DB_MIGRATIONS: tuple[_MigrationSpec, ...] = (
    _MigrationSpec(
        migration_id="state_db_001_create_base_tables",
        version=1,
        apply_fn=_state_db_001_create_base_tables,
    ),
    _MigrationSpec(
        migration_id="state_db_002_add_processed_vector_columns",
        version=2,
        apply_fn=_state_db_002_add_processed_vector_columns,
    ),
    _MigrationSpec(
        migration_id="state_db_003_add_processed_ocr_columns",
        version=3,
        apply_fn=_state_db_003_add_processed_ocr_columns,
    ),
    _MigrationSpec(
        migration_id="state_db_004_add_published_post_type",
        version=4,
        apply_fn=_state_db_004_add_published_post_type,
    ),
    _MigrationSpec(
        migration_id="state_db_005_add_report_download_final_page_url",
        version=5,
        apply_fn=_state_db_005_add_report_download_final_page_url,
    ),
    _MigrationSpec(
        migration_id="state_db_006_create_workflow_control_observations",
        version=6,
        apply_fn=_state_db_006_create_workflow_control_observations,
    ),
    _MigrationSpec(
        migration_id="state_db_007_create_mail_delivery_requests",
        version=7,
        apply_fn=_state_db_007_create_mail_delivery_requests,
    ),
    _MigrationSpec(
        migration_id="state_db_008_create_mailbox_candidate_rejections",
        version=8,
        apply_fn=_state_db_008_create_mailbox_candidate_rejections,
    ),
)
