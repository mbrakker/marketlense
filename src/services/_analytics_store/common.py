from __future__ import annotations

"""Common operations for the analytics store service."""

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterable
from src.contracts.cross_report_analysis import (
    CrossReportReadContentClass,
)
from src.contracts.run_context import RunContext
from src.contracts.sqlite_migration import SqliteMigrationApplyRequest
from src.services.sqlite_migration_service import apply_reports_db_migrations
from src.services._sqlite_common import (
    configure_sqlite_connection,
)
from src.utils.errors import AppError

DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0

_CONN_LOCK = threading.Lock()

_EMBEDDING_STATUSES = {"pending", "embedded", "failed"}

_CROSS_REPORT_READ_CONTENT_CLASSES: set[CrossReportReadContentClass] = {
    "claim",
    "finding",
    "quote",
    "metric",
}

DDL = """
CREATE TABLE IF NOT EXISTS reports (
  file_id TEXT PRIMARY KEY,
  file_name TEXT,
  title TEXT NOT NULL,
  publisher TEXT,
  taxonomy_json TEXT NOT NULL DEFAULT '[]',
  categories_json TEXT NOT NULL DEFAULT '[]',
  region TEXT,
  time_period TEXT,
  source_url TEXT,
  html_path TEXT,
  md5 TEXT,
  page_count INTEGER,
  contents_page INTEGER,
  pdf_metadata_json TEXT,
  analysis_mode TEXT,
  vector_store_id TEXT,
  evidence_packs_json TEXT,
  report_id TEXT,
  publisher_id TEXT,
  source_md5 TEXT,
  ingest_run_id TEXT,
  analysis_run_id TEXT,
  validation_status TEXT,
  validation_severity TEXT,
  text_density REAL,
  text_not_available INTEGER,
  projection_schema_version TEXT,
  projection_version TEXT,
  projection_status TEXT NOT NULL DEFAULT 'not_projected' CHECK(projection_status IN ('not_projected','projected','failed')),
  projection_attempt_count INTEGER NOT NULL DEFAULT 0,
  projection_error_code TEXT,
  projection_error_message TEXT,
  projection_error_retryable INTEGER,
  projection_generated_at_utc TEXT,
  projection_updated_at_utc TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS report_sections (
  section_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  key_points_json TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_findings (
  finding_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  finding_id TEXT NOT NULL,
  text TEXT NOT NULL,
  evidence TEXT NOT NULL,
  confidence TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_metrics (
  metric_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  metric_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  value TEXT NOT NULL,
  unit TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_quotes (
  quote_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  quote_id TEXT NOT NULL,
  text TEXT NOT NULL,
  speaker TEXT NOT NULL,
  citation TEXT NOT NULL,
  page INTEGER,
  evidence_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_claims (
  claim_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  claim TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  evidence TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_tags (
  tag_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  tag_type TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_categories (
  category_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  category_id TEXT NOT NULL,
  label TEXT NOT NULL,
  fit_score REAL NOT NULL,
  decision TEXT NOT NULL,
  selected INTEGER NOT NULL,
  evidence_sections_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_figures (
  figure_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  image_path TEXT NOT NULL,
  kind TEXT NOT NULL,
  page INTEGER NOT NULL,
  is_primary INTEGER NOT NULL,
  detected_caption TEXT NOT NULL,
  generated_caption TEXT NOT NULL,
  display_caption TEXT NOT NULL,
  caption_source TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vector_projection_queue (
  entity_uid TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  report_id TEXT NOT NULL,
  text_payload TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  content_class TEXT NOT NULL,
  embedding_status TEXT NOT NULL CHECK(embedding_status IN ('pending','embedded','failed')),
  embedding_version TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS claim_embeddings (
  embedding_uid TEXT PRIMARY KEY,
  claim_uid TEXT NOT NULL,
  entity_uid TEXT NOT NULL,
  report_id TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  embedding_version TEXT NOT NULL,
  provider TEXT NOT NULL,
  model TEXT NOT NULL,
  dimensions INTEGER,
  vector_json TEXT,
  external_vector_id TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  status TEXT NOT NULL CHECK(status IN ('embedded','failed')),
  generated_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL,
  attempt_count INTEGER NOT NULL,
  error_code TEXT NOT NULL,
  error_message TEXT NOT NULL,
  error_retryable INTEGER NOT NULL,
  error_severity TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_report_sections_report_id ON report_sections(report_id);
CREATE INDEX IF NOT EXISTS idx_report_findings_report_id ON report_findings(report_id);
CREATE INDEX IF NOT EXISTS idx_report_metrics_report_id ON report_metrics(report_id);
CREATE INDEX IF NOT EXISTS idx_report_quotes_report_id ON report_quotes(report_id);
CREATE INDEX IF NOT EXISTS idx_report_claims_report_id ON report_claims(report_id);
CREATE INDEX IF NOT EXISTS idx_report_tags_report_id ON report_tags(report_id);
CREATE INDEX IF NOT EXISTS idx_report_categories_report_id ON report_categories(report_id);
CREATE INDEX IF NOT EXISTS idx_report_figures_report_id ON report_figures(report_id);
CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_report_id ON vector_projection_queue(report_id);
CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_status ON vector_projection_queue(embedding_status);
CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_content_hash ON vector_projection_queue(content_hash);
CREATE INDEX IF NOT EXISTS idx_claim_embeddings_claim_uid ON claim_embeddings(claim_uid);
CREATE INDEX IF NOT EXISTS idx_claim_embeddings_report_id ON claim_embeddings(report_id);
CREATE INDEX IF NOT EXISTS idx_claim_embeddings_status ON claim_embeddings(status);
CREATE INDEX IF NOT EXISTS idx_claim_embeddings_content_hash ON claim_embeddings(content_hash);
CREATE INDEX IF NOT EXISTS idx_reports_projection_status ON reports(projection_status);
"""

_REPORT_PROJECTION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("report_id", "TEXT"),
    ("publisher_id", "TEXT"),
    ("source_md5", "TEXT"),
    ("source_url", "TEXT"),
    ("ingest_run_id", "TEXT"),
    ("analysis_run_id", "TEXT"),
    ("validation_status", "TEXT"),
    ("validation_severity", "TEXT"),
    ("text_density", "REAL"),
    ("text_not_available", "INTEGER"),
    ("projection_schema_version", "TEXT"),
    ("projection_version", "TEXT"),
    (
        "projection_status",
        "TEXT NOT NULL DEFAULT 'not_projected' CHECK(projection_status IN ('not_projected','projected','failed'))",
    ),
    ("projection_attempt_count", "INTEGER NOT NULL DEFAULT 0"),
    ("projection_error_code", "TEXT"),
    ("projection_error_message", "TEXT"),
    ("projection_error_retryable", "INTEGER"),
    ("projection_generated_at_utc", "TEXT"),
    ("projection_updated_at_utc", "TEXT"),
)


@contextmanager
def _analytics_conn(path: str, ctx: RunContext):
    db_path = str(path or "").strip()
    if not db_path:
        raise AppError(
            code="analytics_store_db_missing",
            message="Analytics projection DB path is required",
            retryable=False,
            severity="error",
        )
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(db_path, timeout=DEFAULT_BUSY_TIMEOUT_SECONDS)
    except sqlite3.Error as exc:
        raise AppError(
            code="analytics_store_db_unavailable",
            message="Failed to open analytics projection DB",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": db_path},
        ) from exc
    try:
        _configure(conn)
        with _CONN_LOCK:
            apply_reports_db_migrations(
                SqliteMigrationApplyRequest(
                    schema_version="1.0",
                    database_key="reports_db",
                    db_path=db_path,
                    target_version=15,
                    ctx=ctx,
                ),
                conn,
            )
            conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _configure(conn: sqlite3.Connection) -> None:
    configure_sqlite_connection(
        conn,
        busy_timeout_seconds=DEFAULT_BUSY_TIMEOUT_SECONDS,
    )


def _ensure_reports_projection_columns(conn: sqlite3.Connection) -> None:
    cols = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()
    }
    for column_name, column_type in _REPORT_PROJECTION_COLUMNS:
        if column_name not in cols:
            conn.execute(f"ALTER TABLE reports ADD COLUMN {column_name} {column_type}")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _lineage_values(lineage) -> tuple[str, str, str, str, str, str]:
    return (
        lineage.projection_version,
        lineage.source_pack,
        lineage.source_ref,
        lineage.model,
        lineage.generated_at_utc,
        lineage.analysis_run_id,
    )


def _uid_set(rows: Iterable[Any], attr_name: str) -> set[str]:
    return {str(getattr(row, attr_name)) for row in rows}
