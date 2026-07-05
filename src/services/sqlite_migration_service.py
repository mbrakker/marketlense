from __future__ import annotations

# ruff: noqa: F401

import sqlite3

from src.contracts.sqlite_migration import (
    SqliteMigrationApplyRequest,
    SqliteMigrationApplyResponse,
)

from ._sqlite_migration.runner import (
    _LEDGER_DDL,
    _MigrationSpec,
    _apply_migration_plan,
    _current_version,
    _applied_migration_ids,
    _utc_now,
    _normalize_url_key,
    _fetch_columns,
    _table_exists,
    _add_column_if_missing,
)
from ._sqlite_migration.reports import (
    _CLAIM_EMBEDDINGS_TABLE_SQL,
    _REPORTS_CORE_TABLE_SQL,
    _REPORTS_REQUIRED_COLUMNS,
    _REPORT_SOURCES_TABLE_SQL,
    _PUBLISHERS_TABLE_SQL,
    _DOWNLOAD_ROUTE_HISTORY_TABLE_SQL,
    _PRIVATE_API_CANDIDATE_TABLE_SQL,
    _INVENTORY_RECOVERY_CACHE_TABLE_SQL,
    _INVENTORY_ROUTE_HISTORY_TABLE_SQL,
    _REPORT_SECTIONS_TABLE_SQL,
    _REPORT_FINDINGS_TABLE_SQL,
    _REPORT_METRICS_TABLE_SQL,
    _REPORT_QUOTES_TABLE_SQL,
    _REPORT_CLAIMS_TABLE_SQL,
    _REPORT_TAGS_TABLE_SQL,
    _REPORT_CATEGORIES_TABLE_SQL,
    _REPORT_FIGURES_TABLE_SQL,
    _VECTOR_PROJECTION_QUEUE_TABLE_SQL,
    _SIGNAL_CANDIDATES_TABLE_SQL,
    _SIGNAL_CANDIDATE_GROUPS_TABLE_SQL,
    _reports_db_001_create_reports_core,
    _reports_db_002_create_report_sources_base,
    _reports_db_003_normalize_report_sources,
    _reports_db_004_create_publishers_base,
    _reports_db_005_normalize_publishers,
    _reports_db_006_create_or_upgrade_download_route_history,
    _reports_db_007_normalize_inventory_recovery_cache,
    _reports_db_008_create_inventory_route_history,
    _reports_db_009_add_reports_projection_columns,
    _reports_db_010_create_analytics_projection_tables,
    _reports_db_011_add_report_source_value_scores,
    _reports_db_012_create_private_api_candidate_ledger,
    _reports_db_013_create_signal_candidate_projection,
    _reports_db_014_create_claim_embedding_records,
    _REPORTS_DB_MIGRATIONS,
)
from ._sqlite_migration.state import (
    _STATE_PROCESSED_TABLE_SQL,
    _STATE_INGEST_STATE_TABLE_SQL,
    _STATE_PUBLISHED_TABLE_SQL,
    _STATE_DOWNLOAD_ROUTES_TABLE_SQL,
    _STATE_MAIL_DELIVERY_REQUESTS_TABLE_SQL,
    _STATE_WORKFLOW_CONTROL_OBSERVATIONS_TABLE_SQL,
    _state_db_001_create_base_tables,
    _state_db_002_add_processed_vector_columns,
    _state_db_003_add_processed_ocr_columns,
    _state_db_004_add_published_post_type,
    _state_db_005_add_report_download_final_page_url,
    _state_db_006_create_workflow_control_observations,
    _state_db_007_create_mail_delivery_requests,
    _STATE_DB_MIGRATIONS,
)
from ._sqlite_migration.ui_runs import (
    _UI_RUNS_TABLE_SQL,
    _UI_RUN_DEAD_LETTERS_TABLE_SQL,
    _UI_RUN_DEAD_LETTER_ACTIONS_TABLE_SQL,
    _ui_run_registry_001_create_ui_runs,
    _ui_run_registry_002_add_dead_letter_ledger,
    _UI_RUN_REGISTRY_MIGRATIONS,
)


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
