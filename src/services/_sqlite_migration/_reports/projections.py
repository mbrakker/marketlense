"""Projections ownership for reports database migrations."""

from __future__ import annotations

# ruff: noqa: E501
import sqlite3

from src.services._sqlite_migration._reports.schema import (
    _ARTIFACT_EXECUTION_PLAN_RUNS_TABLE_SQL,
    _ARTIFACT_LINEAGE_DEPENDENCIES_TABLE_SQL,
    _ARTIFACT_LINEAGE_RECORDS_TABLE_SQL,
    _ARTIFACT_LINEAGE_STATES_TABLE_SQL,
    _CLAIM_EMBEDDING_QUEUE_TRANSITIONS_TABLE_SQL,
    _CLAIM_EMBEDDINGS_TABLE_SQL,
    _REPORT_CATEGORIES_TABLE_SQL,
    _REPORT_CLAIMS_TABLE_SQL,
    _REPORT_FIGURES_TABLE_SQL,
    _REPORT_FINDINGS_TABLE_SQL,
    _REPORT_METRICS_TABLE_SQL,
    _REPORT_QUOTES_TABLE_SQL,
    _REPORT_SECTIONS_TABLE_SQL,
    _REPORT_SOURCES_TABLE_SQL,
    _REPORT_TAGS_TABLE_SQL,
    _REPORTS_CORE_TABLE_SQL,
    _REPORTS_REQUIRED_COLUMNS,
    _SIGNAL_CANDIDATE_GROUPS_TABLE_SQL,
    _SIGNAL_CANDIDATES_TABLE_SQL,
    _SOURCE_IDENTITY_OBSERVATIONS_TABLE_SQL,
    _SOURCE_IDENTITY_RESOLUTIONS_TABLE_SQL,
    _SOURCE_PUBLICATION_METADATA_TABLE_SQL,
    _VECTOR_PROJECTION_QUEUE_TABLE_SQL,
)

from ..runner import (
    _add_column_if_missing,
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


def _reports_db_014_create_claim_embedding_records(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_CLAIM_EMBEDDINGS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_claim_embeddings_claim_uid ON claim_embeddings(claim_uid)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_claim_embeddings_report_id ON claim_embeddings(report_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_claim_embeddings_status ON claim_embeddings(status)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_claim_embeddings_content_hash ON claim_embeddings(content_hash)"
    )


def _reports_db_015_create_artifact_lineage_registry(
    conn: sqlite3.Connection,
) -> None:
    conn.execute(_ARTIFACT_LINEAGE_RECORDS_TABLE_SQL)
    conn.execute(_ARTIFACT_LINEAGE_DEPENDENCIES_TABLE_SQL)
    conn.execute(_ARTIFACT_LINEAGE_STATES_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_lineage_records_scope ON artifact_lineage_records(report_id, source_id, artifact_kind)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_lineage_records_prompt ON artifact_lineage_records(prompt_hash)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_lineage_dependencies_dependency ON artifact_lineage_dependencies(dependency_artifact_id)"
    )


def _reports_db_016_add_claim_embedding_queue_controls(
    conn: sqlite3.Connection,
) -> None:
    """Add bounded-queue lifecycle metadata without rewriting retained rows."""
    for name, column_type in (
        ("queue_reason_code", "TEXT NOT NULL DEFAULT ''"),
        ("queue_error_retryable", "INTEGER NOT NULL DEFAULT 0"),
        ("queue_attempt_count", "INTEGER NOT NULL DEFAULT 0"),
        ("next_eligible_at_utc", "TEXT NOT NULL DEFAULT ''"),
        ("queue_actor", "TEXT NOT NULL DEFAULT ''"),
        ("execution_lease_id", "TEXT NOT NULL DEFAULT ''"),
        ("execution_lease_expires_at_utc", "TEXT NOT NULL DEFAULT ''"),
        ("projection_schema_version", "TEXT NOT NULL DEFAULT ''"),
    ):
        _add_column_if_missing(
            conn,
            table_name="vector_projection_queue",
            column_name=name,
            column_type=column_type,
        )
    conn.execute(_CLAIM_EMBEDDING_QUEUE_TRANSITIONS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_admission "
        "ON vector_projection_queue(embedding_status, next_eligible_at_utc, updated_at_utc, entity_uid)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_report_admission "
        "ON vector_projection_queue(report_id, embedding_status, updated_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_claim_embeddings_identity "
        "ON claim_embeddings(entity_uid, content_hash, embedding_version, provider, model, status)"
    )


def _reports_db_017_add_lineage_execution_planning(conn: sqlite3.Connection) -> None:
    """Add explicit planner provenance and durable planned-versus-actual audit rows."""
    _add_column_if_missing(
        conn,
        table_name="artifact_lineage_records",
        column_name="compatibility_json",
        column_type="TEXT NOT NULL DEFAULT '{}'",
    )
    _add_column_if_missing(
        conn,
        table_name="artifact_lineage_records",
        column_name="lineage_status",
        column_type="TEXT NOT NULL DEFAULT 'legacy_unverified'",
    )
    conn.execute(_ARTIFACT_EXECUTION_PLAN_RUNS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_artifact_execution_plan_runs_scope "
        "ON artifact_execution_plan_runs(report_id, execution_intent, created_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_claim_embedding_queue_transitions_entity "
        "ON claim_embedding_queue_transitions(entity_uid, timestamp_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_claim_embedding_queue_transitions_run "
        "ON claim_embedding_queue_transitions(run_id, timestamp_utc)"
    )


def _reports_db_018_create_source_publication_metadata(
    conn: sqlite3.Connection,
) -> None:
    """Persist source-backed publication provenance without rewriting legacy rows."""
    conn.execute(_SOURCE_PUBLICATION_METADATA_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_publication_metadata_status "
        "ON source_publication_metadata(evidence_status, updated_at_utc)"
    )


def _reports_db_019_create_source_identity_observations(
    conn: sqlite3.Connection,
) -> None:
    """Add immutable source identity evidence and deterministic resolutions."""
    conn.execute(_SOURCE_IDENTITY_OBSERVATIONS_TABLE_SQL)
    conn.execute(_SOURCE_IDENTITY_RESOLUTIONS_TABLE_SQL)
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_identity_observations_source "
        "ON source_identity_observations(source_record_id, created_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_identity_observations_content "
        "ON source_identity_observations(content_hash)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_identity_resolutions_identity "
        "ON source_identity_resolutions(source_identity_id)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_source_identity_resolutions_hash "
        "ON source_identity_resolutions(source_metadata_hash)"
    )
    for column_name, column_type in (
        ("source_identity_id", "TEXT"),
        ("source_metadata_hash", "TEXT"),
        ("source_identity_status", "TEXT"),
        ("source_publication_date_status", "TEXT"),
    ):
        _add_column_if_missing(
            conn,
            table_name="reports",
            column_name=column_name,
            column_type=column_type,
        )


def _reports_db_020_expand_execution_plan_audit(conn: sqlite3.Connection) -> None:
    """Retain plan/actual side effects, timing, cost, and reuse evidence."""
    conn.execute(_ARTIFACT_EXECUTION_PLAN_RUNS_TABLE_SQL)
    for column_name, column_type in (
        ("planned_side_effects_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("reusable_artifact_ids_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("actual_side_effects_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("duration_ms", "INTEGER NOT NULL DEFAULT 0"),
        ("actual_cost_usd", "REAL"),
        ("estimated_avoided_cost_usd", "REAL"),
    ):
        _add_column_if_missing(
            conn,
            table_name="artifact_execution_plan_runs",
            column_name=column_name,
            column_type=column_type,
        )


def _reports_db_022_add_execution_plan_prompt_family_reconciliation(
    conn: sqlite3.Connection,
) -> None:
    """Persist exact planned and observed prompt-family sets for enforced runs."""
    conn.execute(_ARTIFACT_EXECUTION_PLAN_RUNS_TABLE_SQL)
    for column_name, column_type in (
        ("planned_prompt_families_json", "TEXT NOT NULL DEFAULT '[]'"),
        ("actual_prompt_families_json", "TEXT NOT NULL DEFAULT '[]'"),
    ):
        _add_column_if_missing(
            conn,
            table_name="artifact_execution_plan_runs",
            column_name=column_name,
            column_type=column_type,
        )
