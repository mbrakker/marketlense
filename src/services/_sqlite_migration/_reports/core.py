from __future__ import annotations

"""Core ownership for reports database migrations."""

import sqlite3
from ..runner import (
    _fetch_columns,
    _normalize_url_key,
)

from src.services._sqlite_migration._reports.schema import (
    _PUBLISHERS_TABLE_SQL,
    _REPORTS_CORE_TABLE_SQL,
    _REPORT_SOURCES_TABLE_SQL,
)


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
