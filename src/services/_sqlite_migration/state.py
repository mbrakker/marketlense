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
)
