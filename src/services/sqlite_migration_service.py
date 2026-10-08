from __future__ import annotations

# ruff: noqa: F401, I001
import logging
import sqlite3
from pathlib import Path

from src.contracts.sqlite_migration import (
    SqliteCapabilityInspectionRequest,
    SqliteCapabilityInspectionResponse,
    SqliteMigrationApplyRequest,
    SqliteMigrationApplyResponse,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

from ._sqlite_migration.runner import (
    _LEDGER_DDL,
    _LLM_USAGE_LEDGER_MIGRATIONS,
    _add_column_if_missing,
    _applied_migration_ids,
    _apply_migration_plan,
    _current_version,
    _fetch_columns,
    _MigrationSpec,
    _normalize_url_key,
    _table_exists,
    _utc_now,
)
from ._sqlite_migration.reports import (
    _ARTIFACT_EXECUTION_PLAN_RUNS_TABLE_SQL,
    _ACQUISITION_ATTEMPT_RESOURCES_TABLE_SQL,
    _ACQUISITION_ROUTE_SUPPRESSIONS_TABLE_SQL,
    _ARTIFACT_LINEAGE_DEPENDENCIES_TABLE_SQL,
    _ARTIFACT_LINEAGE_RECORDS_TABLE_SQL,
    _ARTIFACT_LINEAGE_STATES_TABLE_SQL,
    _CLAIM_EMBEDDINGS_TABLE_SQL,
    _CORPUS_REHABILITATION_CAMPAIGNS_TABLE_SQL,
    _CORPUS_REHABILITATION_CAMPAIGN_ITEMS_TABLE_SQL,
    _DOWNLOAD_ROUTE_HISTORY_TABLE_SQL,
    _INVENTORY_RECOVERY_CACHE_TABLE_SQL,
    _INVENTORY_ROUTE_HISTORY_TABLE_SQL,
    _PRIVATE_API_CANDIDATE_TABLE_SQL,
    _PUBLISHERS_TABLE_SQL,
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
    _REPORTS_DB_MIGRATIONS,
    _REPORTS_REQUIRED_COLUMNS,
    _REPORT_SOURCE_REUSE_TELEMETRY_TABLE_SQL,
    _SIGNAL_CANDIDATE_GROUPS_TABLE_SQL,
    _SIGNAL_CANDIDATES_TABLE_SQL,
    _SOURCE_PUBLICATION_METADATA_TABLE_SQL,
    _VECTOR_PROJECTION_QUEUE_TABLE_SQL,
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
    _reports_db_015_create_artifact_lineage_registry,
    _reports_db_016_add_claim_embedding_queue_controls,
    _reports_db_017_add_lineage_execution_planning,
    _reports_db_018_create_source_publication_metadata,
    _reports_db_019_create_source_identity_observations,
    _reports_db_020_expand_execution_plan_audit,
    _reports_db_021_create_acquisition_resource_telemetry,
    _reports_db_022_add_execution_plan_prompt_family_reconciliation,
    _reports_db_023_create_corpus_rehabilitation_campaigns,
    _reports_db_027_create_source_reuse_telemetry,
    _reports_db_028_add_source_reuse_attribution_statuses,
    _reports_db_029_add_source_provenance_roles,
    _reports_db_030_add_signal_publication_manifest,
)
from ._sqlite_migration.state import (
    _STATE_ARTIFACT_ACQUISITION_CACHE_TABLE_SQL,
    _STATE_DB_MIGRATIONS,
    _STATE_DOWNLOAD_ROUTES_TABLE_SQL,
    _STATE_INGEST_STATE_TABLE_SQL,
    _STATE_MAIL_DELIVERY_REQUESTS_TABLE_SQL,
    _STATE_PROCESSED_TABLE_SQL,
    _STATE_PUBLISHED_TABLE_SQL,
    _STATE_REMEDIATION_RECORDS_TABLE_SQL,
    _STATE_REMEDIATION_TRANSITIONS_TABLE_SQL,
    _STATE_WORKFLOW_CONTROL_OBSERVATIONS_TABLE_SQL,
    _state_db_001_create_base_tables,
    _state_db_002_add_processed_vector_columns,
    _state_db_003_add_processed_ocr_columns,
    _state_db_004_add_published_post_type,
    _state_db_005_add_report_download_final_page_url,
    _state_db_006_create_workflow_control_observations,
    _state_db_007_create_mail_delivery_requests,
    _state_db_008_create_mailbox_candidate_rejections,
    _state_db_009_create_artifact_acquisition_cache,
    _state_db_010_create_remediation_ledger,
    _state_db_011_create_workflow_queue,
    _state_db_012_create_queue_publication_and_briefing_state,
    _state_db_013_create_supervisor_lease,
    _state_db_014_create_source_quarantine,
)
from ._sqlite_migration.ui_runs import (
    _UI_RUN_DEAD_LETTER_ACTIONS_TABLE_SQL,
    _UI_RUN_DEAD_LETTERS_TABLE_SQL,
    _UI_RUN_REGISTRY_MIGRATIONS,
    _UI_RUNS_TABLE_SQL,
    _ui_run_registry_001_create_ui_runs,
    _ui_run_registry_002_add_dead_letter_ledger,
    _ui_run_registry_003_add_remediation_context,
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


def apply_llm_usage_ledger_migrations(
    request: SqliteMigrationApplyRequest,
    conn: sqlite3.Connection,
) -> SqliteMigrationApplyResponse:
    """Apply policy-state migrations owned by the canonical usage ledger."""
    return _apply_migration_plan(request, conn, _LLM_USAGE_LEDGER_MIGRATIONS)


_logger = logging.getLogger("market_lense.sqlite_migration_service")
_MIGRATION_REGISTRIES: dict[str, tuple[_MigrationSpec, ...]] = {
    "state_db": _STATE_DB_MIGRATIONS,
    "reports_db": _REPORTS_DB_MIGRATIONS,
    "ui_run_registry": _UI_RUN_REGISTRY_MIGRATIONS,
    "llm_usage_db": _LLM_USAGE_LEDGER_MIGRATIONS,
}


def inspect_sqlite_capability(
    request: SqliteCapabilityInspectionRequest, ctx: RunContext
) -> SqliteCapabilityInspectionResponse:
    """Inspect one existing SQLite store without migration or persistent writes."""

    migrations = _MIGRATION_REGISTRIES.get(request.database_key)
    expected_version = (
        max((step.version for step in migrations), default=0) if migrations else 0
    )
    result = _sqlite_inspection_result(
        request.database_key,
        status="blocked",
        reason_code="sqlite_database_key_unsupported"
        if migrations is None
        else "sqlite_database_missing",
        retryable=False,
        expected_version=expected_version,
    )
    path = Path(request.db_path).expanduser()
    if migrations is None:
        return _log_sqlite_inspection(result, ctx)
    if not path.is_file():
        return _log_sqlite_inspection(result, ctx)

    read_conn: sqlite3.Connection | None = None
    try:
        read_uri = f"{path.resolve().as_uri()}?mode=ro"
        read_conn = sqlite3.connect(read_uri, uri=True, timeout=0.1)
        integrity = str(read_conn.execute("PRAGMA quick_check(1)").fetchone()[0])
        integrity_ok = integrity.casefold() == "ok"
        foreign_key_violations = read_conn.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        foreign_keys_ok = not foreign_key_violations
        has_schema_version = _table_exists(read_conn, "schema_version")
        has_migration_ledger = _table_exists(read_conn, "schema_migration_ledger")
        current_version = (
            _current_version(read_conn, request.database_key)
            if has_schema_version
            else 0
        )
        applied_ids = (
            _applied_migration_ids(read_conn, request.database_key)
            if has_migration_ledger
            else set()
        )
    except sqlite3.DatabaseError:
        result = _sqlite_inspection_result(
            request.database_key,
            status="blocked",
            reason_code="sqlite_integrity_failed",
            retryable=False,
            expected_version=expected_version,
            integrity_ok=False,
        )
        return _log_sqlite_inspection(result, ctx)
    except OSError:
        result = _sqlite_inspection_result(
            request.database_key,
            status="blocked",
            reason_code="sqlite_database_unavailable",
            retryable=True,
            expected_version=expected_version,
        )
        return _log_sqlite_inspection(result, ctx)
    finally:
        if read_conn is not None:
            read_conn.close()

    if not integrity_ok:
        result = _sqlite_inspection_result(
            request.database_key,
            status="blocked",
            reason_code="sqlite_integrity_failed",
            retryable=False,
            expected_version=expected_version,
            current_version=current_version,
            integrity_ok=False,
            foreign_keys_ok=foreign_keys_ok,
        )
        return _log_sqlite_inspection(result, ctx)
    if not foreign_keys_ok:
        result = _sqlite_inspection_result(
            request.database_key,
            status="blocked",
            reason_code="sqlite_foreign_key_violation",
            retryable=False,
            expected_version=expected_version,
            current_version=current_version,
            integrity_ok=True,
            foreign_keys_ok=False,
        )
        return _log_sqlite_inspection(result, ctx)
    expected_ids = {step.migration_id for step in migrations}
    if (
        current_version != expected_version
        or applied_ids != expected_ids
        or not has_schema_version
        or not has_migration_ledger
    ):
        result = _sqlite_inspection_result(
            request.database_key,
            status="blocked",
            reason_code="sqlite_schema_incompatible",
            retryable=False,
            expected_version=expected_version,
            current_version=current_version,
            integrity_ok=True,
            foreign_keys_ok=True,
        )
        return _log_sqlite_inspection(result, ctx)

    write_conn: sqlite3.Connection | None = None
    timeout = min(max(float(request.lock_timeout_seconds), 0.0), 1.0)
    try:
        write_conn = sqlite3.connect(path, timeout=timeout)
        write_conn.execute(f"PRAGMA busy_timeout={int(timeout * 1000)}")
        write_conn.execute("BEGIN IMMEDIATE")
        write_conn.rollback()
    except sqlite3.OperationalError as exc:
        locked = "locked" in str(exc).casefold() or "busy" in str(exc).casefold()
        result = _sqlite_inspection_result(
            request.database_key,
            status="degraded" if locked else "blocked",
            reason_code="sqlite_write_lock_busy"
            if locked
            else "sqlite_write_lock_unavailable",
            retryable=locked,
            expected_version=expected_version,
            current_version=current_version,
            integrity_ok=True,
            foreign_keys_ok=True,
            write_lock_available=False,
        )
        return _log_sqlite_inspection(result, ctx)
    except sqlite3.DatabaseError:
        result = _sqlite_inspection_result(
            request.database_key,
            status="blocked",
            reason_code="sqlite_write_lock_unavailable",
            retryable=False,
            expected_version=expected_version,
            current_version=current_version,
            integrity_ok=True,
            foreign_keys_ok=True,
            write_lock_available=False,
        )
        return _log_sqlite_inspection(result, ctx)
    finally:
        if write_conn is not None:
            write_conn.close()

    result = _sqlite_inspection_result(
        request.database_key,
        status="ready",
        reason_code="sqlite_capability_ready",
        retryable=False,
        expected_version=expected_version,
        current_version=current_version,
        integrity_ok=True,
        foreign_keys_ok=True,
        write_lock_available=True,
    )
    return _log_sqlite_inspection(result, ctx)


def _sqlite_inspection_result(
    database_key: str,
    *,
    status: str,
    reason_code: str,
    retryable: bool,
    expected_version: int,
    current_version: int = 0,
    integrity_ok: bool = False,
    foreign_keys_ok: bool = False,
    write_lock_available: bool = False,
) -> SqliteCapabilityInspectionResponse:
    return SqliteCapabilityInspectionResponse(
        schema_version="1.0",
        database_key=database_key,
        status=status,
        reason_code=reason_code,
        retryable=retryable,
        current_version=current_version,
        expected_version=expected_version,
        integrity_ok=integrity_ok,
        foreign_keys_ok=foreign_keys_ok,
        write_lock_available=write_lock_available,
    )


def _log_sqlite_inspection(
    result: SqliteCapabilityInspectionResponse, ctx: RunContext
) -> SqliteCapabilityInspectionResponse:
    _logger.info(
        log_event(
            ctx,
            role="service",
            event="sqlite_capability_inspection_complete",
            module=_logger.name,
            fields={
                "database_key": result.database_key,
                "status": result.status,
                "reason_code": result.reason_code,
                "retryable": result.retryable,
                "current_version": result.current_version,
                "expected_version": result.expected_version,
                "integrity_ok": result.integrity_ok,
                "foreign_keys_ok": result.foreign_keys_ok,
                "write_lock_available": result.write_lock_available,
            },
        )
    )
    return result
