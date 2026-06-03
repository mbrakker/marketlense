from __future__ import annotations

import logging
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Sequence

from src.contracts.sqlite_migration import (
    SqliteMigrationAppliedStep,
    SqliteMigrationApplyRequest,
    SqliteMigrationApplyResponse,
)
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

_REPORTS_CORE_TABLE_SQL = """
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
"""

_REPORTS_REQUIRED_COLUMNS: tuple[tuple[str, str], ...] = (
    ("publisher", "TEXT"),
    ("taxonomy_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("file_name", "TEXT"),
    ("source_url", "TEXT"),
    ("html_path", "TEXT"),
    ("md5", "TEXT"),
    ("categories_json", "TEXT NOT NULL DEFAULT '[]'"),
    ("region", "TEXT"),
    ("time_period", "TEXT"),
    ("page_count", "INTEGER"),
    ("contents_page", "INTEGER"),
    ("pdf_metadata_json", "TEXT"),
    ("analysis_mode", "TEXT"),
    ("vector_store_id", "TEXT"),
    ("evidence_packs_json", "TEXT"),
    ("report_id", "TEXT"),
    ("publisher_id", "TEXT"),
    ("source_md5", "TEXT"),
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

_REPORT_SOURCES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS report_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_domain TEXT NOT NULL,
  report_name TEXT NOT NULL,
  landing_page_url TEXT NOT NULL,
  normalized_landing_page_url TEXT NOT NULL,
  source_status TEXT NOT NULL,
  source_page_url TEXT,
  publisher_name TEXT,
  discovered_at_utc TEXT,
  discovered_on_page_number INTEGER,
  downloaded_at_utc TEXT,
  md5 TEXT,
  report_value_score REAL,
  report_value_band TEXT,
  report_value_score_json TEXT,
  report_value_scored_at_utc TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_PUBLISHERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publishers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  homepage TEXT NOT NULL,
  self_presentation TEXT NOT NULL,
  insights_url TEXT NOT NULL,
  normalized_insights_url TEXT NOT NULL DEFAULT '',
  google_folder TEXT,
  discovery_test_status TEXT,
  download_route_kind TEXT,
  download_route_summary TEXT,
  download_route_outcome TEXT,
  download_route_last_downloaded_file_path TEXT,
  download_route_last_final_page_url TEXT,
  download_route_updated_at INTEGER,
  inventory_route_kind TEXT,
  inventory_route_summary TEXT,
  inventory_route_trace_json TEXT,
  inventory_scenario_summary_json TEXT,
  inventory_route_last_final_page_url TEXT,
  inventory_route_updated_at INTEGER,
  inventory_snapshot_drive_file_id TEXT,
  inventory_snapshot_drive_file_name TEXT,
  inventory_snapshot_sha256 TEXT,
  inventory_snapshot_updated_at INTEGER,
  inventory_run_quality_json TEXT,
  inventory_run_quality_updated_at INTEGER
);
"""

_DOWNLOAD_ROUTE_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publisher_download_route_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  normalized_url TEXT NOT NULL,
  source_url TEXT NOT NULL,
  route_kind TEXT NOT NULL,
  route_summary TEXT NOT NULL,
  outcome TEXT NOT NULL,
  route_family TEXT NOT NULL,
  route_status TEXT NOT NULL,
  resolved_target_url TEXT NOT NULL,
  route_steps_json TEXT NOT NULL,
  confirmation_evidence_json TEXT NOT NULL,
  terminal_evidence_json TEXT NOT NULL DEFAULT '{}',
  browser_had_structured_result INTEGER NOT NULL,
  used_candidate_pdf_url INTEGER NOT NULL,
  used_candidate_source_page INTEGER NOT NULL,
  candidate_pdf_url TEXT,
  candidate_source_page_urls_json TEXT NOT NULL,
  candidate_discovery_provenances_json TEXT NOT NULL,
  publisher_discovery_route_kind TEXT,
  publisher_recommended_discovery_route_kind TEXT,
  blocked_reason TEXT,
  blocked_reason_detail TEXT,
  last_downloaded_file_path TEXT,
  last_final_page_url TEXT,
  onsite_capture_path TEXT,
  onsite_capture_format TEXT,
  onsite_page_count INTEGER,
  onsite_completeness_status TEXT,
  attempts INTEGER NOT NULL DEFAULT 0,
  verified_successes INTEGER NOT NULL DEFAULT 0,
  last_n_outcomes_json TEXT NOT NULL DEFAULT '[]',
  confidence_score REAL NOT NULL DEFAULT 0.0,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_PRIVATE_API_CANDIDATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publisher_private_api_candidates (
  fingerprint TEXT PRIMARY KEY,
  publisher_host TEXT NOT NULL,
  endpoint_pattern TEXT NOT NULL,
  method TEXT NOT NULL,
  request_shape_summary TEXT NOT NULL,
  response_pdf_url_json_pointer TEXT NOT NULL,
  expected_status_codes_json TEXT NOT NULL,
  required_response_markers_json TEXT NOT NULL,
  fallback_route_family TEXT NOT NULL,
  route_family TEXT NOT NULL,
  route_kind TEXT NOT NULL,
  evidence_labels_json TEXT NOT NULL,
  source_urls_json TEXT NOT NULL,
  success_count INTEGER NOT NULL DEFAULT 0,
  promoted_playbook_id TEXT NOT NULL DEFAULT '',
  promoted_at_utc TEXT NOT NULL DEFAULT '',
  first_observed_at_utc TEXT NOT NULL,
  last_observed_at_utc TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_INVENTORY_RECOVERY_CACHE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publisher_inventory_candidate_recovery_cache (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  normalized_url TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  source_surface_class TEXT NOT NULL,
  verification_class TEXT NOT NULL,
  recovery_action TEXT NOT NULL,
  last_outcome TEXT NOT NULL,
  last_http_status INTEGER,
  last_error_marker TEXT,
  updated_at_utc TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_INVENTORY_ROUTE_HISTORY_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS publisher_inventory_route_history (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  normalized_url TEXT NOT NULL,
  source_host TEXT NOT NULL,
  route_kind TEXT NOT NULL,
  outcome TEXT NOT NULL,
  status TEXT NOT NULL,
  quality_band TEXT NOT NULL,
  recommended_route_kind TEXT NOT NULL,
  used_memory_route INTEGER NOT NULL,
  page_count INTEGER NOT NULL,
  raw_candidate_count INTEGER NOT NULL,
  current_report_count INTEGER NOT NULL,
  raw_new_report_count INTEGER NOT NULL,
  screened_new_report_count INTEGER NOT NULL,
  qualified_new_report_count INTEGER NOT NULL,
  snapshot_changed INTEGER NOT NULL,
  requires_review INTEGER NOT NULL,
  scenario_class TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_REPORT_SECTIONS_TABLE_SQL = """
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
"""

_REPORT_FINDINGS_TABLE_SQL = """
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
"""

_REPORT_METRICS_TABLE_SQL = """
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
"""

_REPORT_QUOTES_TABLE_SQL = """
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
"""

_REPORT_CLAIMS_TABLE_SQL = """
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
"""

_REPORT_TAGS_TABLE_SQL = """
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
"""

_REPORT_CATEGORIES_TABLE_SQL = """
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
"""

_REPORT_FIGURES_TABLE_SQL = """
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
"""

_VECTOR_PROJECTION_QUEUE_TABLE_SQL = """
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
"""

_SIGNAL_CANDIDATES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signal_candidates (
  candidate_id TEXT PRIMARY KEY,
  extraction_request_id TEXT NOT NULL,
  candidate_type TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  confidence REAL NOT NULL,
  strength REAL NOT NULL,
  support_level TEXT NOT NULL,
  caveats_json TEXT NOT NULL,
  source_report_ids_json TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL,
  source_refs_json TEXT NOT NULL,
  raw_source_context_json TEXT NOT NULL,
  validation_status TEXT NOT NULL,
  validation_notes_json TEXT NOT NULL,
  group_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  generated_at_utc TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

_SIGNAL_CANDIDATE_GROUPS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS signal_candidate_groups (
  group_id TEXT PRIMARY KEY,
  extraction_request_id TEXT NOT NULL,
  stable_key TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  support_level TEXT NOT NULL,
  candidate_ids_json TEXT NOT NULL,
  source_report_ids_json TEXT NOT NULL,
  evidence_ids_json TEXT NOT NULL,
  caveats_json TEXT NOT NULL,
  raw_group_context_json TEXT NOT NULL,
  validation_status TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  generated_at_utc TEXT NOT NULL,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);
"""

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


@dataclass(frozen=True)
class _MigrationSpec:
    migration_id: str
    version: int
    apply_fn: Callable[[sqlite3.Connection], None]


def apply_reports_db_migrations(
    request: SqliteMigrationApplyRequest,
    conn: sqlite3.Connection,
) -> SqliteMigrationApplyResponse:
    return _apply_migration_plan(request, conn, _REPORTS_DB_MIGRATIONS)


def apply_state_db_migrations(
    request: SqliteMigrationApplyRequest,
    conn: sqlite3.Connection,
) -> SqliteMigrationApplyResponse:
    return _apply_migration_plan(request, conn, _STATE_DB_MIGRATIONS)


def apply_ui_run_registry_migrations(
    request: SqliteMigrationApplyRequest,
    conn: sqlite3.Connection,
) -> SqliteMigrationApplyResponse:
    return _apply_migration_plan(request, conn, _UI_RUN_REGISTRY_MIGRATIONS)


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


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


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


def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        """
        SELECT 1
        FROM sqlite_master
        WHERE type='table' AND name=?
        """,
        (table_name,),
    ).fetchone()
    return row is not None


def _add_column_if_missing(
    conn: sqlite3.Connection,
    *,
    table_name: str,
    column_name: str,
    column_type: str,
) -> None:
    if column_name not in _fetch_columns(conn, table_name):
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}")


def _reports_db_001_create_reports_core(conn: sqlite3.Connection) -> None:
    conn.execute(_REPORTS_CORE_TABLE_SQL)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_title ON reports(title)")


def _reports_db_002_create_report_sources_base(conn: sqlite3.Connection) -> None:
    conn.execute(_REPORT_SOURCES_TABLE_SQL)


def _reports_db_003_normalize_report_sources(conn: sqlite3.Connection) -> None:
    expected = {
        "id",
        "source_domain",
        "report_name",
        "landing_page_url",
        "normalized_landing_page_url",
        "source_status",
        "source_page_url",
        "publisher_name",
        "discovered_at_utc",
        "discovered_on_page_number",
        "downloaded_at_utc",
        "md5",
        "created_at",
        "updated_at",
    }
    current = _fetch_columns(conn, "report_sources")
    if current != expected:
        conn.execute("DROP TABLE IF EXISTS report_sources_new")
        conn.execute(
            """
            CREATE TABLE report_sources_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_domain TEXT NOT NULL,
              report_name TEXT NOT NULL,
              landing_page_url TEXT NOT NULL,
              normalized_landing_page_url TEXT NOT NULL,
              source_status TEXT NOT NULL,
              source_page_url TEXT,
              publisher_name TEXT,
              discovered_at_utc TEXT,
              discovered_on_page_number INTEGER,
              downloaded_at_utc TEXT,
              md5 TEXT,
              created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
              updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
            """
        )
        if current:
            rows = conn.execute(
                "SELECT * FROM report_sources ORDER BY id ASC"
            ).fetchall()
            column_order = [
                str(row[1])
                for row in conn.execute("PRAGMA table_info(report_sources)").fetchall()
            ]
            current_epoch = int(
                conn.execute("SELECT strftime('%s','now')").fetchone()[0]
            )
            for fetched in rows:
                source = dict(zip(column_order, fetched))
                landing_page_url = str(source.get("landing_page_url") or "").strip()
                normalized_landing_page_url = _normalize_url_key(landing_page_url)
                if not landing_page_url or not normalized_landing_page_url:
                    continue
                downloaded_at_utc = (
                    str(source.get("downloaded_at_utc") or "").strip() or None
                )
                source_status = (
                    str(source.get("source_status") or "").strip() or "downloaded"
                )
                source_page_url = (
                    str(source.get("source_page_url") or "").strip() or landing_page_url
                )
                discovered_at_utc = (
                    str(source.get("discovered_at_utc") or "").strip()
                    or downloaded_at_utc
                )
                discovered_on_page_number = source.get("discovered_on_page_number")
                created_at = int(source.get("created_at") or 0) or current_epoch
                updated_at = int(source.get("updated_at") or 0) or created_at
                conn.execute(
                    """
                    INSERT OR REPLACE INTO report_sources_new(
                        id,
                        source_domain,
                        report_name,
                        landing_page_url,
                        normalized_landing_page_url,
                        source_status,
                        source_page_url,
                        publisher_name,
                        discovered_at_utc,
                        discovered_on_page_number,
                        downloaded_at_utc,
                        md5,
                        created_at,
                        updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        int(source.get("id") or 0) or None,
                        str(source.get("source_domain") or "").strip(),
                        str(source.get("report_name") or "").strip(),
                        landing_page_url,
                        normalized_landing_page_url,
                        source_status,
                        source_page_url,
                        str(source.get("publisher_name") or "").strip() or None,
                        discovered_at_utc,
                        int(discovered_on_page_number)
                        if discovered_on_page_number is not None
                        else None,
                        downloaded_at_utc,
                        str(source.get("md5") or "").strip().lower() or None,
                        created_at,
                        updated_at,
                    ),
                )
        conn.execute("DROP TABLE IF EXISTS report_sources")
        conn.execute("ALTER TABLE report_sources_new RENAME TO report_sources")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_domain ON report_sources(source_domain)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_report_sources_normalized_url ON report_sources(normalized_landing_page_url)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_status ON report_sources(source_status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_md5 ON report_sources(md5)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_discovered_at ON report_sources(discovered_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_downloaded_at ON report_sources(downloaded_at_utc)"
    )


def _reports_db_004_create_publishers_base(conn: sqlite3.Connection) -> None:
    conn.execute(_PUBLISHERS_TABLE_SQL)


def _reports_db_005_normalize_publishers(conn: sqlite3.Connection) -> None:
    expected = {
        "id",
        "name",
        "homepage",
        "self_presentation",
        "insights_url",
        "normalized_insights_url",
        "google_folder",
        "discovery_test_status",
        "download_route_kind",
        "download_route_summary",
        "download_route_outcome",
        "download_route_last_downloaded_file_path",
        "download_route_last_final_page_url",
        "download_route_updated_at",
        "inventory_route_kind",
        "inventory_route_summary",
        "inventory_route_trace_json",
        "inventory_scenario_summary_json",
        "inventory_route_last_final_page_url",
        "inventory_route_updated_at",
        "inventory_snapshot_drive_file_id",
        "inventory_snapshot_drive_file_name",
        "inventory_snapshot_sha256",
        "inventory_snapshot_updated_at",
        "inventory_run_quality_json",
        "inventory_run_quality_updated_at",
    }
    current = _fetch_columns(conn, "publishers")
    if current != expected:
        conn.execute("DROP TABLE IF EXISTS publishers_new")
        conn.execute(
            """
            CREATE TABLE publishers_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              name TEXT NOT NULL,
              homepage TEXT NOT NULL,
              self_presentation TEXT NOT NULL,
              insights_url TEXT NOT NULL,
              normalized_insights_url TEXT NOT NULL DEFAULT '',
              google_folder TEXT,
              discovery_test_status TEXT,
              download_route_kind TEXT,
              download_route_summary TEXT,
              download_route_outcome TEXT,
              download_route_last_downloaded_file_path TEXT,
              download_route_last_final_page_url TEXT,
              download_route_updated_at INTEGER,
              inventory_route_kind TEXT,
              inventory_route_summary TEXT,
              inventory_route_trace_json TEXT,
              inventory_scenario_summary_json TEXT,
              inventory_route_last_final_page_url TEXT,
              inventory_route_updated_at INTEGER,
              inventory_snapshot_drive_file_id TEXT,
              inventory_snapshot_drive_file_name TEXT,
              inventory_snapshot_sha256 TEXT,
              inventory_snapshot_updated_at INTEGER,
              inventory_run_quality_json TEXT,
              inventory_run_quality_updated_at INTEGER
            )
            """
        )
        if current:
            order_column = "id" if "id" in current else "rowid"
            rows = conn.execute(
                f"SELECT * FROM publishers ORDER BY {order_column} ASC"
            ).fetchall()
            column_order = [
                str(row[1])
                for row in conn.execute("PRAGMA table_info(publishers)").fetchall()
            ]
            insert_columns = [
                "id",
                "name",
                "homepage",
                "self_presentation",
                "insights_url",
                "normalized_insights_url",
                "google_folder",
                "discovery_test_status",
                "download_route_kind",
                "download_route_summary",
                "download_route_outcome",
                "download_route_last_downloaded_file_path",
                "download_route_last_final_page_url",
                "download_route_updated_at",
                "inventory_route_kind",
                "inventory_route_summary",
                "inventory_route_trace_json",
                "inventory_scenario_summary_json",
                "inventory_route_last_final_page_url",
                "inventory_route_updated_at",
                "inventory_snapshot_drive_file_id",
                "inventory_snapshot_drive_file_name",
                "inventory_snapshot_sha256",
                "inventory_snapshot_updated_at",
                "inventory_run_quality_json",
                "inventory_run_quality_updated_at",
            ]
            available_insert_columns = [
                column
                for column in insert_columns
                if column != "id" or column in current
            ]
            placeholders = ", ".join("?" for _ in available_insert_columns)
            for fetched in rows:
                source = dict(zip(column_order, fetched))
                insights_url = str(source.get("insights_url") or "").strip()
                normalized_insights_url = str(
                    source.get("normalized_insights_url") or ""
                ).strip() or _normalize_url_key(insights_url)
                values: list[object] = []
                for column in available_insert_columns:
                    if column == "normalized_insights_url":
                        values.append(normalized_insights_url)
                    else:
                        values.append(source.get(column))
                conn.execute(
                    f"""
                    INSERT INTO publishers_new({", ".join(available_insert_columns)})
                    VALUES({placeholders})
                    """,
                    values,
                )
        conn.execute("DROP TABLE IF EXISTS publishers")
        conn.execute("ALTER TABLE publishers_new RENAME TO publishers")
    rows = conn.execute(
        """
        SELECT id, insights_url
        FROM publishers
        WHERE trim(insights_url) <> ''
          AND (
            normalized_insights_url IS NULL
            OR trim(normalized_insights_url) = ''
          )
        ORDER BY id ASC
        """
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            UPDATE publishers
            SET normalized_insights_url=?
            WHERE id=?
            """,
            (_normalize_url_key(row[1]), int(row[0])),
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_publishers_name ON publishers(name)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publishers_homepage ON publishers(homepage)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publishers_insights_url ON publishers(insights_url)"
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_publishers_normalized_insights_url
        ON publishers(normalized_insights_url)
        """
    )


def _reports_db_006_create_or_upgrade_download_route_history(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_DOWNLOAD_ROUTE_HISTORY_TABLE_SQL)
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="terminal_evidence_json",
        column_type="TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="blocked_reason",
        column_type="TEXT",
    )
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="blocked_reason_detail",
        column_type="TEXT",
    )
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="onsite_capture_path",
        column_type="TEXT",
    )
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="onsite_capture_format",
        column_type="TEXT",
    )
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="onsite_page_count",
        column_type="INTEGER",
    )
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="onsite_completeness_status",
        column_type="TEXT",
    )
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="attempts",
        column_type="INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="verified_successes",
        column_type="INTEGER NOT NULL DEFAULT 0",
    )
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="last_n_outcomes_json",
        column_type="TEXT NOT NULL DEFAULT '[]'",
    )
    _add_column_if_missing(
        conn,
        table_name="publisher_download_route_history",
        column_name="confidence_score",
        column_type="REAL NOT NULL DEFAULT 0.0",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_download_route_history_normalized_url ON publisher_download_route_history(normalized_url)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_download_route_history_updated_at ON publisher_download_route_history(updated_at)"
    )


def _reports_db_007_normalize_inventory_recovery_cache(
    conn: sqlite3.Connection,
) -> None:
    expected = {
        "id",
        "normalized_url",
        "canonical_url",
        "source_surface_class",
        "verification_class",
        "recovery_action",
        "last_outcome",
        "last_http_status",
        "last_error_marker",
        "updated_at_utc",
        "created_at",
        "updated_at",
    }
    conn.execute(_INVENTORY_RECOVERY_CACHE_TABLE_SQL)
    current = _fetch_columns(conn, "publisher_inventory_candidate_recovery_cache")
    if current != expected:
        conn.execute(
            "DROP TABLE IF EXISTS publisher_inventory_candidate_recovery_cache_new"
        )
        conn.execute(
            """
            CREATE TABLE publisher_inventory_candidate_recovery_cache_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              normalized_url TEXT NOT NULL,
              canonical_url TEXT NOT NULL,
              source_surface_class TEXT NOT NULL,
              verification_class TEXT NOT NULL,
              recovery_action TEXT NOT NULL,
              last_outcome TEXT NOT NULL,
              last_http_status INTEGER,
              last_error_marker TEXT,
              updated_at_utc TEXT NOT NULL,
              created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
              updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
            )
            """
        )
        selectable = [
            column
            for column in (
                "normalized_url",
                "canonical_url",
                "source_surface_class",
                "verification_class",
                "recovery_action",
                "last_outcome",
                "last_http_status",
                "last_error_marker",
                "updated_at_utc",
                "created_at",
                "updated_at",
            )
            if column in current
        ]
        if selectable:
            quoted = ", ".join(selectable)
            conn.execute(
                f"""
                INSERT INTO publisher_inventory_candidate_recovery_cache_new({quoted})
                SELECT {quoted}
                FROM publisher_inventory_candidate_recovery_cache
                """
            )
        conn.execute(
            "DROP TABLE IF EXISTS publisher_inventory_candidate_recovery_cache"
        )
        conn.execute(
            "ALTER TABLE publisher_inventory_candidate_recovery_cache_new RENAME TO publisher_inventory_candidate_recovery_cache"
        )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_publisher_inventory_candidate_recovery_cache_key ON publisher_inventory_candidate_recovery_cache(normalized_url, canonical_url)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publisher_inventory_candidate_recovery_cache_updated_at ON publisher_inventory_candidate_recovery_cache(updated_at)"
    )


def _reports_db_008_create_inventory_route_history(conn: sqlite3.Connection) -> None:
    conn.execute(_INVENTORY_ROUTE_HISTORY_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publisher_inventory_route_history_normalized_url ON publisher_inventory_route_history(normalized_url)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publisher_inventory_route_history_source_host ON publisher_inventory_route_history(source_host)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publisher_inventory_route_history_updated_at ON publisher_inventory_route_history(updated_at)"
    )


def _reports_db_009_add_reports_projection_columns(conn: sqlite3.Connection) -> None:
    conn.execute(_REPORTS_CORE_TABLE_SQL)
    for column_name, column_type in _REPORTS_REQUIRED_COLUMNS:
        _add_column_if_missing(
            conn,
            table_name="reports",
            column_name=column_name,
            column_type=column_type,
        )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_publisher ON reports(publisher)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_file_name ON reports(file_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_projection_status ON reports(projection_status)"
    )


def _reports_db_010_create_analytics_projection_tables(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_REPORT_SECTIONS_TABLE_SQL)
    conn.execute(_REPORT_FINDINGS_TABLE_SQL)
    conn.execute(_REPORT_METRICS_TABLE_SQL)
    conn.execute(_REPORT_QUOTES_TABLE_SQL)
    conn.execute(_REPORT_CLAIMS_TABLE_SQL)
    conn.execute(_REPORT_TAGS_TABLE_SQL)
    conn.execute(_REPORT_CATEGORIES_TABLE_SQL)
    conn.execute(_REPORT_FIGURES_TABLE_SQL)
    conn.execute(_VECTOR_PROJECTION_QUEUE_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sections_report_id ON report_sections(report_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_findings_report_id ON report_findings(report_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_metrics_report_id ON report_metrics(report_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_quotes_report_id ON report_quotes(report_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_claims_report_id ON report_claims(report_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_tags_report_id ON report_tags(report_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_categories_report_id ON report_categories(report_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_figures_report_id ON report_figures(report_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_report_id ON vector_projection_queue(report_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_status ON vector_projection_queue(embedding_status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_content_hash ON vector_projection_queue(content_hash)"
    )


def _reports_db_011_add_report_source_value_scores(conn: sqlite3.Connection) -> None:
    conn.execute(_REPORT_SOURCES_TABLE_SQL)
    _add_column_if_missing(
        conn,
        table_name="report_sources",
        column_name="report_value_score",
        column_type="REAL",
    )
    _add_column_if_missing(
        conn,
        table_name="report_sources",
        column_name="report_value_band",
        column_type="TEXT",
    )
    _add_column_if_missing(
        conn,
        table_name="report_sources",
        column_name="report_value_score_json",
        column_type="TEXT",
    )
    _add_column_if_missing(
        conn,
        table_name="report_sources",
        column_name="report_value_scored_at_utc",
        column_type="TEXT",
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_publisher_score ON report_sources(publisher_name, report_value_score)"
    )


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


def _reports_db_012_create_private_api_candidate_ledger(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_PRIVATE_API_CANDIDATE_TABLE_SQL)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_private_api_candidates_publisher_host
        ON publisher_private_api_candidates(publisher_host)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_private_api_candidates_promoted_at
        ON publisher_private_api_candidates(promoted_at_utc)
        """
    )


def _reports_db_013_create_signal_candidate_projection(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_SIGNAL_CANDIDATES_TABLE_SQL)
    conn.execute(_SIGNAL_CANDIDATE_GROUPS_TABLE_SQL)
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_signal_candidates_extraction_request
        ON signal_candidates(extraction_request_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_signal_candidates_validation_status
        ON signal_candidates(validation_status)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_signal_candidates_group_id
        ON signal_candidates(group_id)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_signal_candidate_groups_extraction_request
        ON signal_candidate_groups(extraction_request_id)
        """
    )


_REPORTS_DB_MIGRATIONS: tuple[_MigrationSpec, ...] = (
    _MigrationSpec(
        migration_id="reports_db_001_create_reports_core",
        version=1,
        apply_fn=_reports_db_001_create_reports_core,
    ),
    _MigrationSpec(
        migration_id="reports_db_002_create_report_sources_base",
        version=2,
        apply_fn=_reports_db_002_create_report_sources_base,
    ),
    _MigrationSpec(
        migration_id="reports_db_003_normalize_report_sources",
        version=3,
        apply_fn=_reports_db_003_normalize_report_sources,
    ),
    _MigrationSpec(
        migration_id="reports_db_004_create_publishers_base",
        version=4,
        apply_fn=_reports_db_004_create_publishers_base,
    ),
    _MigrationSpec(
        migration_id="reports_db_005_normalize_publishers",
        version=5,
        apply_fn=_reports_db_005_normalize_publishers,
    ),
    _MigrationSpec(
        migration_id="reports_db_006_create_or_upgrade_download_route_history",
        version=6,
        apply_fn=_reports_db_006_create_or_upgrade_download_route_history,
    ),
    _MigrationSpec(
        migration_id="reports_db_007_normalize_inventory_recovery_cache",
        version=7,
        apply_fn=_reports_db_007_normalize_inventory_recovery_cache,
    ),
    _MigrationSpec(
        migration_id="reports_db_008_create_inventory_route_history",
        version=8,
        apply_fn=_reports_db_008_create_inventory_route_history,
    ),
    _MigrationSpec(
        migration_id="reports_db_009_add_reports_projection_columns",
        version=9,
        apply_fn=_reports_db_009_add_reports_projection_columns,
    ),
    _MigrationSpec(
        migration_id="reports_db_010_create_analytics_projection_tables",
        version=10,
        apply_fn=_reports_db_010_create_analytics_projection_tables,
    ),
    _MigrationSpec(
        migration_id="reports_db_011_add_report_source_value_scores",
        version=11,
        apply_fn=_reports_db_011_add_report_source_value_scores,
    ),
    _MigrationSpec(
        migration_id="reports_db_012_create_private_api_candidate_ledger",
        version=12,
        apply_fn=_reports_db_012_create_private_api_candidate_ledger,
    ),
    _MigrationSpec(
        migration_id="reports_db_013_create_signal_candidate_projection",
        version=13,
        apply_fn=_reports_db_013_create_signal_candidate_projection,
    ),
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
