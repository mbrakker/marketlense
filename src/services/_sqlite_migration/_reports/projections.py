from __future__ import annotations

"""Projections ownership for reports database migrations."""

import sqlite3
from ..runner import (
    _add_column_if_missing,
)

from src.services._sqlite_migration._reports.schema import (
    _REPORTS_CORE_TABLE_SQL,
    _REPORTS_REQUIRED_COLUMNS,
    _REPORT_CATEGORIES_TABLE_SQL,
    _REPORT_CLAIMS_TABLE_SQL,
    _REPORT_FIGURES_TABLE_SQL,
    _REPORT_FINDINGS_TABLE_SQL,
    _REPORT_METRICS_TABLE_SQL,
    _REPORT_QUOTES_TABLE_SQL,
    _REPORT_SECTIONS_TABLE_SQL,
    _REPORT_SOURCES_TABLE_SQL,
    _REPORT_TAGS_TABLE_SQL,
    _SIGNAL_CANDIDATES_TABLE_SQL,
    _SIGNAL_CANDIDATE_GROUPS_TABLE_SQL,
    _VECTOR_PROJECTION_QUEUE_TABLE_SQL,
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
