from __future__ import annotations

import sqlite3

from .common import _normalize_optional_url_key


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(reports)")
    cols = {row[1] for row in cur.fetchall()}
    if "file_name" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN file_name TEXT")
    if "region" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN region TEXT")
    if "time_period" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN time_period TEXT")
    if "categories_json" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN categories_json TEXT DEFAULT '[]'")
    if "page_count" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN page_count INTEGER")
    if "contents_page" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN contents_page INTEGER")
    if "pdf_metadata_json" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN pdf_metadata_json TEXT")
    if "analysis_mode" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN analysis_mode TEXT")
    if "vector_store_id" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN vector_store_id TEXT")
    if "evidence_packs_json" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN evidence_packs_json TEXT")
    if "report_id" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN report_id TEXT")
    if "publisher_id" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN publisher_id TEXT")
    if "source_md5" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN source_md5 TEXT")
    if "ingest_run_id" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN ingest_run_id TEXT")
    if "analysis_run_id" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN analysis_run_id TEXT")
    if "validation_status" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN validation_status TEXT")
    if "validation_severity" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN validation_severity TEXT")
    if "text_density" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN text_density REAL")
    if "text_not_available" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN text_not_available INTEGER")
    if "projection_schema_version" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN projection_schema_version TEXT")
    if "projection_version" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN projection_version TEXT")
    if "projection_status" not in cols:
        conn.execute(
            "ALTER TABLE reports ADD COLUMN projection_status TEXT NOT NULL DEFAULT 'not_projected' CHECK(projection_status IN ('not_projected','projected','failed'))"
        )
    if "projection_attempt_count" not in cols:
        conn.execute(
            "ALTER TABLE reports ADD COLUMN projection_attempt_count INTEGER NOT NULL DEFAULT 0"
        )
    if "projection_error_code" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN projection_error_code TEXT")
    if "projection_error_message" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN projection_error_message TEXT")
    if "projection_error_retryable" not in cols:
        conn.execute(
            "ALTER TABLE reports ADD COLUMN projection_error_retryable INTEGER"
        )
    if "projection_generated_at_utc" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN projection_generated_at_utc TEXT")
    if "projection_updated_at_utc" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN projection_updated_at_utc TEXT")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_file_name ON reports(file_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_reports_projection_status ON reports(projection_status)"
    )
    _ensure_report_sources_schema(conn)
    _ensure_publishers_schema(conn)
    _ensure_publisher_download_route_history_schema(conn)
    _ensure_publisher_inventory_candidate_recovery_cache_schema(conn)
    conn.commit()


def _ensure_report_sources_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(report_sources)")
    rows = cur.fetchall()
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
        "report_value_score",
        "report_value_band",
        "report_value_score_json",
        "report_value_scored_at_utc",
        "created_at",
        "updated_at",
    }
    current = {str(row[1]) for row in rows}
    if not rows:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_sources (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_domain TEXT NOT NULL,
              report_name TEXT NOT NULL,
              landing_page_url TEXT NOT NULL,
              normalized_landing_page_url TEXT NOT NULL DEFAULT '',
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
            )
            """
        )
        _ensure_report_sources_indexes(conn)
        return
    if "normalized_landing_page_url" not in current:
        conn.execute(
            """
            ALTER TABLE report_sources
            ADD COLUMN normalized_landing_page_url TEXT NOT NULL DEFAULT ''
            """
        )
    if "source_page_url" not in current:
        conn.execute("ALTER TABLE report_sources ADD COLUMN source_page_url TEXT")
    if "publisher_name" not in current:
        conn.execute("ALTER TABLE report_sources ADD COLUMN publisher_name TEXT")
    if "discovered_at_utc" not in current:
        conn.execute("ALTER TABLE report_sources ADD COLUMN discovered_at_utc TEXT")
    if "discovered_on_page_number" not in current:
        conn.execute(
            "ALTER TABLE report_sources ADD COLUMN discovered_on_page_number INTEGER"
        )
    if "report_value_score" not in current:
        conn.execute("ALTER TABLE report_sources ADD COLUMN report_value_score REAL")
    if "report_value_band" not in current:
        conn.execute("ALTER TABLE report_sources ADD COLUMN report_value_band TEXT")
    if "report_value_score_json" not in current:
        conn.execute(
            "ALTER TABLE report_sources ADD COLUMN report_value_score_json TEXT"
        )
    if "report_value_scored_at_utc" not in current:
        conn.execute(
            "ALTER TABLE report_sources ADD COLUMN report_value_scored_at_utc TEXT"
        )
    missing = expected - current
    unsupported = missing - {
        "normalized_landing_page_url",
        "source_page_url",
        "publisher_name",
        "discovered_at_utc",
        "discovered_on_page_number",
        "report_value_score",
        "report_value_band",
        "report_value_score_json",
        "report_value_scored_at_utc",
    }
    if unsupported:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS report_sources_new (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              source_domain TEXT NOT NULL,
              report_name TEXT NOT NULL,
              landing_page_url TEXT NOT NULL,
              normalized_landing_page_url TEXT NOT NULL DEFAULT '',
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
            INSERT INTO report_sources_new(
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
              report_value_score,
              report_value_band,
              report_value_score_json,
              report_value_scored_at_utc,
              created_at,
              updated_at
            )
            SELECT
              id,
              source_domain,
              report_name,
              landing_page_url,
              COALESCE(normalized_landing_page_url, ''),
              source_status,
              source_page_url,
              publisher_name,
              discovered_at_utc,
              discovered_on_page_number,
              downloaded_at_utc,
              md5,
              report_value_score,
              report_value_band,
              report_value_score_json,
              report_value_scored_at_utc,
              created_at,
              updated_at
            FROM report_sources;
            DROP TABLE report_sources;
            ALTER TABLE report_sources_new RENAME TO report_sources;
            """
        )
    rows = conn.execute(
        "SELECT id, landing_page_url FROM report_sources WHERE normalized_landing_page_url = ''"
    ).fetchall()
    for row in rows:
        normalized = _normalize_optional_url_key(str(row[1] or ""))
        conn.execute(
            "UPDATE report_sources SET normalized_landing_page_url=? WHERE id=?",
            (normalized, int(row[0])),
        )
    _ensure_report_sources_indexes(conn)


def _ensure_report_sources_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_domain_name ON report_sources(source_domain, report_name)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_downloaded ON report_sources(downloaded_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_normalized_url ON report_sources(normalized_landing_page_url)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_publisher_score ON report_sources(publisher_name, report_value_score)"
    )


def _ensure_publisher_download_route_history_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(publisher_download_route_history)")
    rows = cur.fetchall()
    current = {str(row[1]) for row in rows}
    if not rows:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS publisher_download_route_history (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              normalized_url TEXT NOT NULL,
              source_url TEXT NOT NULL,
              route_kind TEXT NOT NULL,
              route_summary TEXT NOT NULL,
              outcome TEXT NOT NULL,
              route_family TEXT NOT NULL DEFAULT 'browser_pdf_click',
              route_status TEXT NOT NULL DEFAULT 'inferred',
              resolved_target_url TEXT NOT NULL DEFAULT '',
              route_steps_json TEXT NOT NULL DEFAULT '[]',
              confirmation_evidence_json TEXT NOT NULL DEFAULT '{}',
              terminal_evidence_json TEXT NOT NULL DEFAULT '{}',
              browser_had_structured_result INTEGER NOT NULL DEFAULT 0,
              used_candidate_pdf_url INTEGER NOT NULL DEFAULT 0,
              used_candidate_source_page INTEGER NOT NULL DEFAULT 0,
              candidate_pdf_url TEXT,
              candidate_source_page_urls_json TEXT NOT NULL DEFAULT '[]',
              candidate_discovery_provenances_json TEXT NOT NULL DEFAULT '[]',
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
            )
            """
        )
        return
    required_defaults = {
        "route_family": "TEXT NOT NULL DEFAULT 'browser_pdf_click'",
        "route_status": "TEXT NOT NULL DEFAULT 'inferred'",
        "resolved_target_url": "TEXT NOT NULL DEFAULT ''",
        "route_steps_json": "TEXT NOT NULL DEFAULT '[]'",
        "confirmation_evidence_json": "TEXT NOT NULL DEFAULT '{}'",
        "terminal_evidence_json": "TEXT NOT NULL DEFAULT '{}'",
        "browser_had_structured_result": "INTEGER NOT NULL DEFAULT 0",
        "used_candidate_pdf_url": "INTEGER NOT NULL DEFAULT 0",
        "used_candidate_source_page": "INTEGER NOT NULL DEFAULT 0",
        "candidate_pdf_url": "TEXT",
        "candidate_source_page_urls_json": "TEXT NOT NULL DEFAULT '[]'",
        "candidate_discovery_provenances_json": "TEXT NOT NULL DEFAULT '[]'",
        "publisher_discovery_route_kind": "TEXT",
        "publisher_recommended_discovery_route_kind": "TEXT",
        "blocked_reason": "TEXT",
        "blocked_reason_detail": "TEXT",
        "last_downloaded_file_path": "TEXT",
        "last_final_page_url": "TEXT",
        "onsite_capture_path": "TEXT",
        "onsite_capture_format": "TEXT",
        "onsite_page_count": "INTEGER",
        "onsite_completeness_status": "TEXT",
        "attempts": "INTEGER NOT NULL DEFAULT 0",
        "verified_successes": "INTEGER NOT NULL DEFAULT 0",
        "last_n_outcomes_json": "TEXT NOT NULL DEFAULT '[]'",
        "confidence_score": "REAL NOT NULL DEFAULT 0.0",
    }
    for column, ddl in required_defaults.items():
        if column not in current:
            conn.execute(
                f"ALTER TABLE publisher_download_route_history ADD COLUMN {column} {ddl}"
            )


def _ensure_publisher_inventory_candidate_recovery_cache_schema(
    conn: sqlite3.Connection,
) -> None:
    cur = conn.execute(
        "PRAGMA table_info(publisher_inventory_candidate_recovery_cache)"
    )
    rows = cur.fetchall()
    current = {str(row[1]) for row in rows}
    if not rows:
        conn.execute(
            """
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
            )
            """
        )
        return
    for column, ddl in {
        "source_surface_class": "TEXT NOT NULL DEFAULT 'unknown'",
        "verification_class": "TEXT NOT NULL DEFAULT 'verified'",
        "recovery_action": "TEXT NOT NULL DEFAULT ''",
        "last_outcome": "TEXT NOT NULL DEFAULT ''",
        "last_http_status": "INTEGER",
        "last_error_marker": "TEXT",
        "updated_at_utc": "TEXT NOT NULL DEFAULT ''",
    }.items():
        if column not in current:
            conn.execute(
                f"ALTER TABLE publisher_inventory_candidate_recovery_cache ADD COLUMN {column} {ddl}"
            )


def _ensure_publishers_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(publishers)")
    cols = {row[1] for row in cur.fetchall()}
    if "normalized_insights_url" not in cols:
        conn.execute(
            """
            ALTER TABLE publishers
            ADD COLUMN normalized_insights_url TEXT NOT NULL DEFAULT ''
            """
        )
    if "google_folder" not in cols:
        conn.execute("ALTER TABLE publishers ADD COLUMN google_folder TEXT")
    if "discovery_test_status" not in cols:
        conn.execute("ALTER TABLE publishers ADD COLUMN discovery_test_status TEXT")
    if "download_route_kind" not in cols:
        conn.execute("ALTER TABLE publishers ADD COLUMN download_route_kind TEXT")
    if "download_route_summary" not in cols:
        conn.execute("ALTER TABLE publishers ADD COLUMN download_route_summary TEXT")
    if "download_route_outcome" not in cols:
        conn.execute("ALTER TABLE publishers ADD COLUMN download_route_outcome TEXT")
    if "download_route_last_downloaded_file_path" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN download_route_last_downloaded_file_path TEXT"
        )
    if "download_route_last_final_page_url" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN download_route_last_final_page_url TEXT"
        )
    if "download_route_updated_at" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN download_route_updated_at INTEGER"
        )
    if "inventory_route_kind" not in cols:
        conn.execute("ALTER TABLE publishers ADD COLUMN inventory_route_kind TEXT")
    if "inventory_route_summary" not in cols:
        conn.execute("ALTER TABLE publishers ADD COLUMN inventory_route_summary TEXT")
    if "inventory_route_trace_json" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN inventory_route_trace_json TEXT"
        )
    if "inventory_scenario_summary_json" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN inventory_scenario_summary_json TEXT"
        )
    if "inventory_route_last_final_page_url" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN inventory_route_last_final_page_url TEXT"
        )
    if "inventory_route_updated_at" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN inventory_route_updated_at INTEGER"
        )
    if "inventory_snapshot_drive_file_id" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN inventory_snapshot_drive_file_id TEXT"
        )
    if "inventory_snapshot_drive_file_name" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN inventory_snapshot_drive_file_name TEXT"
        )
    if "inventory_snapshot_sha256" not in cols:
        conn.execute("ALTER TABLE publishers ADD COLUMN inventory_snapshot_sha256 TEXT")
    if "inventory_snapshot_updated_at" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN inventory_snapshot_updated_at INTEGER"
        )
    if "inventory_run_quality_json" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN inventory_run_quality_json TEXT"
        )
    if "inventory_run_quality_updated_at" not in cols:
        conn.execute(
            "ALTER TABLE publishers ADD COLUMN inventory_run_quality_updated_at INTEGER"
        )
    _backfill_publisher_normalized_insights_urls(conn)
    _ensure_publishers_indexes(conn)


def _ensure_publishers_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_publishers_normalized_insights_url
        ON publishers(normalized_insights_url)
        """
    )


def _backfill_publisher_normalized_insights_urls(conn: sqlite3.Connection) -> None:
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
        normalized_insights_url = _normalize_optional_url_key(str(row[1] or ""))
        conn.execute(
            """
            UPDATE publishers
            SET normalized_insights_url=?
            WHERE id=?
            """,
            (normalized_insights_url, int(row[0])),
        )
