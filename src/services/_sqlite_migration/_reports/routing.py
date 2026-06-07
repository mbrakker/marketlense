from __future__ import annotations

"""Routing ownership for reports database migrations."""

import sqlite3
from ..runner import (
    _add_column_if_missing,
    _fetch_columns,
)

from src.services._sqlite_migration._reports.schema import (
    _DOWNLOAD_ROUTE_HISTORY_TABLE_SQL,
    _INVENTORY_RECOVERY_CACHE_TABLE_SQL,
    _INVENTORY_ROUTE_HISTORY_TABLE_SQL,
    _PRIVATE_API_CANDIDATE_TABLE_SQL,
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
