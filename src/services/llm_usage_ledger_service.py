from __future__ import annotations

import json
import logging
import sqlite3
import threading
import uuid
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, replace
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from statistics import median
from typing import Any, cast

from src.contracts.deferred_work import (
    DeferredWorkArtifactReference,
    DeferredWorkClaimRequest,
    DeferredWorkClaimResponse,
    DeferredWorkItem,
    DeferredWorkLeaseReleaseRequest,
    DeferredWorkLeaseReleaseResponse,
    DeferredWorkListRequest,
    DeferredWorkListResponse,
    DeferredWorkMetrics,
    DeferredWorkMetricsRequest,
    DeferredWorkStatus,
    DeferredWorkTransitionRequest,
    DeferredWorkTransitionResponse,
)
from src.contracts.files import AppendBytesRequest, WriteBytesRequest
from src.contracts.llm_usage import (
    LLMUsageExportRebuildRequest,
    LLMUsageExportRebuildResponse,
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerAppendResponse,
    LLMUsageLedgerEntry,
    LLMUsageLedgerOutcomeUpdateRequest,
    LLMUsageLedgerOutcomeUpdateResponse,
    LLMUsageLedgerReconciliationRequest,
    LLMUsageLedgerReconciliationResponse,
    LLMUsageMedianRebuildRequest,
    LLMUsageMedianRebuildResponse,
    LLMPolicyEffectivenessRequest,
    LLMPolicyEffectivenessResponse,
    LLMPolicyEffectivenessRow,
    LLMUsageProjectionStatusRequest,
    LLMUsageProjectionStatusResponse,
    LLMUsageRunSummaryRequest,
    LLMUsageRunSummaryResponse,
    LLMUsageSpendGuardrailRequest,
    LLMUsageSpendGuardrailResponse,
    LLMUsageSpendReservationReleaseRequest,
    LLMUsageSpendReservationReleaseResponse,
)
from src.contracts.run_budget import (
    BudgetAuthorityReport,
    BudgetDecision,
    BudgetOverrideContext,
    BudgetRequest,
    BudgetReservationReconcileRequest,
    BudgetReservationReconcileResponse,
    BudgetSideEffectFinalizeRequest,
    BudgetSideEffectFinalizeResponse,
    RunBudget,
    RunBudgetEventAppendRequest,
    RunBudgetEventAppendResponse,
    RunBudgetLimits,
    RunBudgetUsage,
    RunBudgetTaskUsageReadRequest,
    RunBudgetTaskUsageReadResponse,
    RunBudgetUsageReadRequest,
    RunBudgetUsageReadResponse,
)
from src.contracts.run_context import RunContext
from src.contracts.sqlite_migration import SqliteMigrationApplyRequest
from src.services import file_service
from src.services._llm_usage_ledger.projection_state import (
    allocate_projection_generation,
    ensure_projection_state_schema,
    event_count,
    increment_event_count,
    increment_semantic_task_count,
    semantic_task_count,
)
from src.services.sqlite_migration_service import apply_llm_usage_ledger_migrations
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.llm_usage_ledger_service")
_LOCK = threading.Lock()
_MEDIAN_REBUILD_EXECUTOR = ThreadPoolExecutor(
    max_workers=4, thread_name_prefix="llm_usage_median_rebuild"
)
_PENDING_MEDIAN_REBUILD_PATHS: set[str] = set()
_PENDING_MEDIAN_REBUILD_LOCK = threading.Lock()
_MEDIAN_REBUILD_EVENT_INTERVAL = 20
_USAGE_EXPORT_PROJECTION_INTERVAL = 20
_PROJECTION_LEASE_SECONDS = 120
_MAX_BUDGET_RESERVATION_TTL_SECONDS = 3600
_DEFERRED_WORK_RETRY_DELAY_SECONDS = 3600
_DEFERRED_WORK_DEADLINE_SECONDS = 72 * 3600
_DEFERRED_WORK_MAX_ATTEMPTS = 10
_DEFERRED_WORK_STATUSES = {"pending", "leased", "completed", "remediation", "terminal"}
_OUTCOME_STATUSES = {"valid", "invalid", "not_validated", "not_applicable"}
_PROVIDER_CALL_STATUSES = {"completed", "failed"}
_ERROR_CODE_STAGES = {
    "openai_embedding_count_mismatch": "output_validation",
    "openai_ocr_invalid_response": "output_validation",
    "openai_response_empty": "output_validation",
    "openai_response_json_type_invalid": "output_validation",
    "openai_response_invalid_json": "output_validation",
    "openai_response_validation_failed": "output_validation",
    "openrouter_response_invalid_json": "output_validation",
}
_ERROR_STAGES = {"", *set(_ERROR_CODE_STAGES.values())}
_RUN_BUDGET_EVENT_METRICS = {
    "runtime_seconds",
    "retries",
    "browser_launches",
    "drive_reads",
    "drive_writes",
    "wordpress_writes",
    "pdfs",
    "mailbox_reads",
}


def _validate_error_taxonomy(*, error_stage: str, error_code: str) -> None:
    if error_stage not in _ERROR_STAGES:
        raise AppError(
            code="llm_usage_ledger_error_stage_invalid",
            message="LLM usage error stage is unsupported",
            retryable=False,
            context={"error_stage": error_stage},
        )
    if not error_code:
        if error_stage:
            raise AppError(
                code="llm_usage_ledger_error_code_missing",
                message="LLM usage error stage requires a terminal error code",
                retryable=False,
                context={"error_stage": error_stage},
            )
        return
    expected_stage = _ERROR_CODE_STAGES.get(error_code)
    if expected_stage is None or expected_stage != error_stage:
        raise AppError(
            code="llm_usage_ledger_error_taxonomy_invalid",
            message="LLM usage terminal error code must map to its documented stage",
            retryable=False,
            context={"error_stage": error_stage, "error_code": error_code},
        )


def _validate_request(request: LLMUsageLedgerAppendRequest) -> None:
    if request.schema_version != "1.0":
        raise AppError(
            code="llm_usage_ledger_schema_version_invalid",
            message="LLM usage ledger append request schema version is unsupported",
            retryable=False,
            context={"schema_version": request.schema_version},
        )
    if request.entry.schema_version != "1.0":
        raise AppError(
            code="llm_usage_ledger_entry_schema_version_invalid",
            message="LLM usage ledger entry schema version is unsupported",
            retryable=False,
            context={"schema_version": request.entry.schema_version},
        )
    if not str(request.db_path or "").strip():
        raise AppError(
            code="llm_usage_ledger_path_missing",
            message="LLM usage ledger database path is required",
            retryable=False,
        )
    if not request.entry.provider.strip() or not request.entry.action.strip():
        raise AppError(
            code="llm_usage_ledger_identity_missing",
            message="LLM usage provider and action are required",
            retryable=False,
            context={
                "provider": request.entry.provider,
                "action": request.entry.action,
            },
        )
    if request.entry.provider_call_status not in _PROVIDER_CALL_STATUSES:
        raise AppError(
            code="llm_usage_ledger_provider_call_status_invalid",
            message="LLM usage provider call status is unsupported",
            retryable=False,
            context={"provider_call_status": request.entry.provider_call_status},
        )
    if request.entry.parse_status not in _OUTCOME_STATUSES:
        raise AppError(
            code="llm_usage_ledger_parse_status_invalid",
            message="LLM usage parse status is unsupported",
            retryable=False,
            context={"parse_status": request.entry.parse_status},
        )
    if request.entry.schema_validation_status not in _OUTCOME_STATUSES:
        raise AppError(
            code="llm_usage_ledger_schema_validation_status_invalid",
            message="LLM usage schema validation status is unsupported",
            retryable=False,
            context={
                "schema_validation_status": request.entry.schema_validation_status
            },
        )
    if request.entry.call_ordinal is not None and int(request.entry.call_ordinal) < 0:
        raise AppError(
            code="llm_usage_ledger_call_ordinal_invalid",
            message="LLM usage call ordinal must be non-negative",
            retryable=False,
            context={"call_ordinal": request.entry.call_ordinal},
        )
    _validate_error_taxonomy(
        error_stage=request.entry.error_stage,
        error_code=request.entry.error_code,
    )
    if request.entry.validation_run_id:
        required = {
            "cohort_id": request.entry.cohort_id,
            "workflow_run_id": request.entry.workflow_run_id,
            "workflow": request.entry.workflow,
            "stage": request.entry.stage,
            "report_id": request.entry.report_id,
            "artifact_family": request.entry.artifact_family,
            "publisher_id": request.entry.publisher_id,
            "action": request.entry.action,
            "semantic_task": request.entry.semantic_task,
            "prompt_namespace": request.entry.prompt_namespace,
            "policy_namespace": request.entry.policy_namespace,
            "cache_decision": request.entry.cache_decision,
            "model_policy_namespace": request.entry.model_policy_namespace,
            "configuration_hash": request.entry.configuration_hash,
            "policy_hash": request.entry.policy_hash,
            "producer_build_identity": request.entry.producer_build_identity,
        }
        missing = sorted(
            key for key, value in required.items() if not str(value).strip()
        )
        if missing:
            raise AppError(
                code="llm_usage_validation_attribution_missing",
                message="Validation-run LLM usage must retain complete runtime attribution",
                retryable=False,
                context={
                    "validation_run_id": request.entry.validation_run_id,
                    "missing": missing,
                },
            )


def _validate_median_rebuild_request(request: LLMUsageMedianRebuildRequest) -> None:
    if request.schema_version != "1.0":
        raise AppError(
            code="llm_usage_median_rebuild_schema_version_invalid",
            message="LLM usage median rebuild request schema version is unsupported",
            retryable=False,
            context={"schema_version": request.schema_version},
        )
    if not str(request.db_path or "").strip():
        raise AppError(
            code="llm_usage_median_rebuild_path_missing",
            message="LLM usage ledger database path is required",
            retryable=False,
        )


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        create table if not exists llm_usage_events (
            id integer primary key autoincrement,
            schema_version text not null,
            timestamp_utc text not null,
            provider text not null,
            action text not null,
            run_id text not null,
            task_id text not null,
            span_id text not null,
            trace_id text not null,
            model text not null,
            request_id text,
            publisher_name text not null,
            report_name text not null,
            source_url text not null,
            input_tokens integer not null,
            output_tokens integer not null,
            total_tokens integer not null,
            cached_input_tokens integer,
            tool_calls integer not null,
            estimated_cost_usd real not null,
            prompt_namespace text not null,
            prompt_hash text not null,
            provider_decision text not null,
            cache_decision text not null,
            temperature real,
            seed integer,
            timeout_seconds real,
            event_key text,
            call_ordinal integer not null default 0,
            provider_call_status text not null default 'completed',
            parse_status text not null default 'not_applicable',
            schema_validation_status text not null default 'not_applicable',
            error_stage text not null default '',
            error_code text not null default '',
            semantic_task text not null default '',
            report_id text not null default '',
            workflow text not null default '',
            stage text not null default '',
            plan_hash text not null default '',
            artifact_family text not null default '',
            validation_run_id text not null default '',
            cohort_id text not null default '',
            workflow_run_id text not null default '',
            publisher_id text not null default '',
            model_policy_namespace text not null default '',
            policy_namespace text not null default '',
            configuration_hash text not null default '',
            policy_hash text not null default '',
            producer_build_identity text not null default '',
            repair_attempt integer not null default 0,
            pricing_version text not null default '',
            pricing_status text not null default '',
            metadata_json text not null
        )
        """
    )
    existing_columns = {
        str(row[1]) for row in conn.execute("pragma table_info(llm_usage_events)")
    }
    migrations = {
        "event_key": "text",
        "call_ordinal": "integer not null default 0",
        "provider_call_status": "text not null default 'completed'",
        "parse_status": "text not null default 'not_applicable'",
        "schema_validation_status": "text not null default 'not_applicable'",
        "error_stage": "text not null default ''",
        "error_code": "text not null default ''",
        "semantic_task": "text not null default ''",
        "report_id": "text not null default ''",
        "workflow": "text not null default ''",
        "stage": "text not null default ''",
        "plan_hash": "text not null default ''",
        "artifact_family": "text not null default ''",
        "validation_run_id": "text not null default ''",
        "cohort_id": "text not null default ''",
        "workflow_run_id": "text not null default ''",
        "publisher_id": "text not null default ''",
        "model_policy_namespace": "text not null default ''",
        "policy_namespace": "text not null default ''",
        "configuration_hash": "text not null default ''",
        "policy_hash": "text not null default ''",
        "producer_build_identity": "text not null default ''",
        "repair_attempt": "integer not null default 0",
        "pricing_version": "text not null default ''",
        "pricing_status": "text not null default ''",
    }
    for column, definition in migrations.items():
        if column not in existing_columns:
            conn.execute(
                f"alter table llm_usage_events add column {column} {definition}"
            )
    conn.execute(
        """
        update llm_usage_events
        set semantic_task = case
            when instr(task_id, ':vector_store:') > 0
                then substr(task_id, instr(task_id, ':vector_store:') + 14)
            else action
        end
        where semantic_task = ''
        """
    )
    conn.execute(
        "update llm_usage_events set event_key = 'legacy:' || id where event_key is null or event_key = ''"
    )
    conn.execute(
        """
        create index if not exists idx_llm_usage_events_semantic_task
        on llm_usage_events(semantic_task)
        """
    )
    conn.execute(
        "create unique index if not exists idx_llm_usage_events_event_key on llm_usage_events(event_key)"
    )
    conn.execute(
        """
        create index if not exists idx_llm_usage_events_provider_time
        on llm_usage_events(provider, timestamp_utc)
        """
    )
    conn.execute(
        """
        create index if not exists idx_llm_usage_events_publisher_time
        on llm_usage_events(publisher_name, timestamp_utc)
        """
    )
    conn.execute(
        """
        create index if not exists idx_llm_usage_events_run
        on llm_usage_events(run_id, task_id)
        """
    )
    conn.execute(
        """
        create index if not exists idx_llm_usage_events_attribution
        on llm_usage_events(validation_run_id, cohort_id, workflow_run_id, report_id, workflow, stage, artifact_family)
        """
    )
    conn.execute(
        """
        create table if not exists run_budget_side_effect_events (
            event_key text primary key,
            schema_version text not null,
            timestamp_utc text not null,
            run_id text not null,
            task_id text not null default '',
            span_id text not null default '',
            publisher_name text not null,
            day_utc text not null,
            metric text not null,
            quantity integer not null,
            decision text not null,
            override_actor text not null default '',
            override_reason text not null default ''
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_run_budget_side_effect_events_scope
        on run_budget_side_effect_events(run_id, day_utc, publisher_name, metric)
        """
    )
    side_effect_columns = {
        str(row[1])
        for row in conn.execute(
            "pragma table_info(run_budget_side_effect_events)"
        ).fetchall()
    }
    for column_name in ("task_id", "span_id"):
        if column_name not in side_effect_columns:
            conn.execute(
                "alter table run_budget_side_effect_events "
                f"add column {column_name} text not null default ''"
            )
    conn.execute(
        """
        create index if not exists idx_run_budget_side_effect_events_run_task
        on run_budget_side_effect_events(run_id, task_id)
        """
    )
    conn.execute(
        """
        create table if not exists llm_usage_export_checkpoints (
            ledger_path text not null,
            daily_path text not null,
            event_count integer not null,
            source_sha256 text not null,
            ledger_sha256 text not null,
            daily_sha256 text not null,
            completed_at_utc text not null,
            primary key (ledger_path, daily_path)
        )
        """
    )
    checkpoint_columns = {
        str(row[1])
        for row in conn.execute(
            "pragma table_info(llm_usage_export_checkpoints)"
        ).fetchall()
    }
    if "last_projected_event_id" not in checkpoint_columns:
        conn.execute(
            """
            alter table llm_usage_export_checkpoints
            add column last_projected_event_id integer not null default 0
            """
        )
    if "generation_id" not in checkpoint_columns:
        conn.execute(
            """
            alter table llm_usage_export_checkpoints
            add column generation_id integer not null default 0
            """
        )
    conn.execute(
        """
        create table if not exists llm_usage_projection_leases (
            ledger_path text not null,
            daily_path text not null,
            holder_id text not null,
            expires_at_utc text not null,
            generation_id integer not null,
            primary key (ledger_path, daily_path)
        )
        """
    )
    conn.execute(
        """
        create table if not exists llm_usage_median_state (
            singleton integer primary key check (singleton = 1),
            dirty_through_event_id integer not null default 0,
            snapshot_through_event_id integer not null default 0,
            rebuild_in_progress integer not null default 0,
            updated_at_utc text not null default ''
        )
        """
    )
    conn.execute(
        """
        insert into llm_usage_median_state(singleton, updated_at_utc)
        values (1, '') on conflict(singleton) do nothing
        """
    )
    conn.execute(
        """
        create table if not exists llm_usage_spend_reservations (
            reservation_key text primary key,
            day_utc text not null,
            estimated_cost_usd real not null,
            status text not null,
            expires_at_utc text not null,
            created_at_utc text not null,
            released_at_utc text not null default ''
        )
        """
    )
    conn.execute(
        """
        create index if not exists idx_llm_usage_spend_reservations_active
        on llm_usage_spend_reservations(day_utc, status, expires_at_utc)
        """
    )
    ensure_projection_state_schema(conn)


def _validate_run_budget(budget: RunBudget) -> None:
    if budget.schema_version != "1.0":
        raise AppError(
            code="run_budget_schema_version_invalid",
            message="Run-budget schema version is unsupported",
            retryable=False,
            context={"schema_version": budget.schema_version},
        )
    if not str(budget.run_id or "").strip():
        raise AppError(
            code="run_budget_run_id_missing",
            message="Run-budget run_id is required for canonical accounting",
            retryable=False,
        )
    if not str(budget.usage_db_path or "").strip():
        raise AppError(
            code="run_budget_usage_db_path_missing",
            message="Run-budget usage_db_path is required for canonical accounting",
            retryable=False,
        )
    if not 0 < budget.reservation_ttl_seconds <= _MAX_BUDGET_RESERVATION_TTL_SECONDS:
        raise AppError(
            code="run_budget_reservation_ttl_invalid",
            message="Run-budget reservation TTL must be between one second and one hour",
            retryable=False,
        )


def _budget_day_utc(budget: RunBudget) -> str:
    value = str(budget.day_utc or "").strip()
    if value:
        try:
            return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
        except ValueError as exc:
            raise AppError(
                code="run_budget_day_utc_invalid",
                message="Run-budget day_utc must use YYYY-MM-DD",
                cause=exc,
                retryable=False,
                context={"day_utc": value},
            ) from exc
    return datetime.now(timezone.utc).date().isoformat()


def _read_budget_usage_for_scope(
    conn: sqlite3.Connection,
    *,
    llm_where: str,
    llm_params: tuple[object, ...],
    event_where: str,
    event_params: tuple[object, ...],
) -> RunBudgetUsage:
    llm = conn.execute(
        f"""
        select coalesce(sum(estimated_cost_usd), 0.0), coalesce(sum(total_tokens), 0), count(*)
        from llm_usage_events where {llm_where}
        """,
        llm_params,
    ).fetchone()
    events = conn.execute(
        f"""
        select
            coalesce(sum(case when metric = 'runtime_seconds' then quantity else 0 end), 0),
            coalesce(sum(case when metric = 'retries' then quantity else 0 end), 0),
            coalesce(sum(case when metric = 'browser_launches' then quantity else 0 end), 0),
            coalesce(sum(case when metric = 'drive_reads' then quantity else 0 end), 0),
            coalesce(sum(case when metric = 'drive_writes' then quantity else 0 end), 0),
            coalesce(sum(case when metric = 'wordpress_writes' then quantity else 0 end), 0),
            coalesce(sum(case when metric = 'pdfs' then quantity else 0 end), 0),
            coalesce(sum(case when metric = 'mailbox_reads' then quantity else 0 end), 0)
        from run_budget_side_effect_events where {event_where}
        """,
        event_params,
    ).fetchone()
    actuals = conn.execute(
        f"""
        select
            coalesce(sum(actual_tokens), 0),
            coalesce(sum(actual_calls), 0),
            coalesce(sum(actual_steps), 0),
            coalesce(sum(actual_duration_seconds), 0),
            coalesce(sum(actual_retries), 0),
            coalesce(sum(actual_browser_launches), 0),
            coalesce(sum(actual_drive_reads), 0),
            coalesce(sum(actual_drive_writes), 0),
            coalesce(sum(actual_wordpress_writes), 0),
            coalesce(sum(actual_pdfs), 0),
            coalesce(sum(actual_mailbox_reads), 0)
        from budget_authority_actuals where {event_where}
        """,
        event_params,
    ).fetchone()
    llm_values = llm or (0.0, 0, 0)
    event_values = events or (0, 0, 0, 0, 0, 0, 0, 0)
    actual_values = actuals or (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    return RunBudgetUsage(
        schema_version="1.0",
        spend_usd=float(cast(Any, llm_values[0]) or 0.0),
        tokens=int(llm_values[1] or 0) + int(actual_values[0] or 0),
        calls=int(llm_values[2] or 0) + int(actual_values[1] or 0),
        steps=int(actual_values[2] or 0),
        runtime_seconds=int(event_values[0] or 0) + int(actual_values[3] or 0),
        retries=int(event_values[1] or 0) + int(actual_values[4] or 0),
        browser_launches=int(event_values[2] or 0) + int(actual_values[5] or 0),
        drive_reads=int(event_values[3] or 0) + int(actual_values[6] or 0),
        drive_writes=int(event_values[4] or 0) + int(actual_values[7] or 0),
        wordpress_writes=int(event_values[5] or 0) + int(actual_values[8] or 0),
        pdfs=int(event_values[6] or 0) + int(actual_values[9] or 0),
        mailbox_reads=int(event_values[7] or 0) + int(actual_values[10] or 0),
    )


def _merge_budget_usage(*usages: RunBudgetUsage) -> RunBudgetUsage:
    fields = (
        "spend_usd",
        "tokens",
        "calls",
        "steps",
        "runtime_seconds",
        "retries",
        "browser_launches",
        "drive_writes",
        "drive_reads",
        "wordpress_writes",
        "pdfs",
        "mailbox_reads",
    )
    return RunBudgetUsage(
        schema_version="1.0",
        **{field: max(getattr(usage, field) for usage in usages) for field in fields},
    )


def _budget_projection_outcome(
    budget: RunBudget,
    status: LLMUsageProjectionStatusResponse | None,
) -> str:
    """Classify projection freshness without rebuilding derived compatibility files."""
    if status is None:
        return "not_configured"
    if not status.files_valid:
        return "derived_files_invalid"
    if status.latest_event_id and not status.projected_event_id:
        return "checkpoint_missing"
    if not status.pending_event_count:
        return "current"
    if status.pending_event_count <= max(0, budget.projection_pending_event_threshold):
        return "bounded_lag_accounted"
    return "fresh_projection_recommended"


def read_run_budget_usage(
    request: RunBudgetUsageReadRequest, ctx: RunContext
) -> RunBudgetUsageReadResponse:
    """Read one conservative usage snapshot from the canonical LLM ledger.

    A configured run budget applies to every configured scope. Taking the
    metric-wise maximum prevents a run/day/publisher overlap from being counted
    twice while ensuring no scope can be silently ignored.
    """
    if request.schema_version != "1.0":
        raise AppError(
            code="run_budget_usage_read_schema_version_invalid",
            message="Run-budget usage-read schema version is unsupported",
            retryable=False,
        )
    _validate_run_budget(request.budget)
    budget = request.budget
    day_utc = _budget_day_utc(budget)
    path = Path(budget.usage_db_path)
    _apply_budget_authority_migrations(path, ctx)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="run_budget_usage_read_start",
            module=logger.name,
            fields={
                "db_path": str(path),
                "run_id": budget.run_id,
                "day_utc": day_utc,
                "publisher_name": budget.publisher_name,
            },
        )
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, sqlite3.connect(path) as conn:
            _ensure_schema(conn)
            run_usage = _read_budget_usage_for_scope(
                conn,
                llm_where="run_id = ?",
                llm_params=(budget.run_id,),
                event_where="run_id = ?",
                event_params=(budget.run_id,),
            )
            day_usage = _read_budget_usage_for_scope(
                conn,
                llm_where="substr(timestamp_utc, 1, 10) = ?",
                llm_params=(day_utc,),
                event_where="day_utc = ?",
                event_params=(day_utc,),
            )
            publisher_usage = (
                _read_budget_usage_for_scope(
                    conn,
                    llm_where="publisher_name = ? and substr(timestamp_utc, 1, 10) = ?",
                    llm_params=(budget.publisher_name, day_utc),
                    event_where="publisher_name = ? and day_utc = ?",
                    event_params=(budget.publisher_name, day_utc),
                )
                if budget.publisher_name
                else RunBudgetUsage(schema_version="1.0")
            )
            event_count = int(
                conn.execute(
                    """
                    select count(*) from run_budget_side_effect_events
                    where run_id = ? or day_utc = ? or (publisher_name = ? and day_utc = ?)
                    """,
                    (budget.run_id, day_utc, budget.publisher_name, day_utc),
                ).fetchone()[0]
            ) + int(
                conn.execute(
                    """
                    select count(*) from budget_authority_actuals
                    where run_id = ? or day_utc = ? or (publisher_name = ? and day_utc = ?)
                    """,
                    (budget.run_id, day_utc, budget.publisher_name, day_utc),
                ).fetchone()[0]
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="run_budget_usage_read_failed",
            message=f"Could not read canonical budget usage from {path}",
            cause=exc,
            retryable=False,
            context={"db_path": str(path)},
        ) from exc
    projection_status = None
    if budget.projection_ledger_path and budget.projection_daily_path:
        projection_status = get_projection_status(
            LLMUsageProjectionStatusRequest(
                schema_version="1.0",
                db_path=budget.usage_db_path,
                ledger_path=budget.projection_ledger_path,
                daily_path=budget.projection_daily_path,
            ),
            ctx,
        )
    response = RunBudgetUsageReadResponse(
        schema_version="1.0",
        usage=_merge_budget_usage(run_usage, day_usage, publisher_usage),
        run_usage=run_usage,
        day_usage=day_usage,
        publisher_usage=publisher_usage,
        event_count=event_count,
        projection_outcome=_budget_projection_outcome(budget, projection_status),
        projection_pending_event_count=(
            projection_status.pending_event_count if projection_status else 0
        ),
        projection_pending_estimated_cost_usd=(
            projection_status.pending_estimated_cost_usd if projection_status else 0.0
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="run_budget_usage_read_complete",
            module=logger.name,
            fields={
                "run_id": budget.run_id,
                "day_utc": day_utc,
                "publisher_name": budget.publisher_name,
                "event_count": response.event_count,
                **_usage_log_fields("usage", response.usage),
                "projection_outcome": response.projection_outcome,
                "projection_pending_event_count": response.projection_pending_event_count,
                "projection_pending_estimated_cost_usd": response.projection_pending_estimated_cost_usd,
            },
        )
    )
    return response


def read_run_budget_task_usage(
    request: RunBudgetTaskUsageReadRequest, ctx: RunContext
) -> RunBudgetTaskUsageReadResponse:
    """Read actual canonical usage for exactly one task without budget merging.

    This read is deliberately observational: budget enforcement continues to use
    :func:`read_run_budget_usage` and its run/day/publisher scopes unchanged.
    """
    if request.schema_version != "1.0" or not str(request.task_id or "").strip():
        raise AppError(
            code="run_budget_task_usage_read_request_invalid",
            message="Task-scoped budget usage requires an exact task identifier",
            retryable=False,
        )
    _validate_run_budget(request.budget)
    budget = request.budget
    task_id = str(request.task_id).strip()
    path = Path(budget.usage_db_path)
    _apply_budget_authority_migrations(path, ctx)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, sqlite3.connect(path) as conn:
            _ensure_schema(conn)
            usage = _read_budget_usage_for_scope(
                conn,
                llm_where="run_id = ? and task_id = ?",
                llm_params=(budget.run_id, task_id),
                event_where="run_id = ? and task_id = ?",
                event_params=(budget.run_id, task_id),
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="run_budget_task_usage_read_failed",
            message=f"Could not read task-scoped canonical budget usage from {path}",
            cause=exc,
            retryable=False,
            context={"db_path": str(path), "run_id": budget.run_id, "task_id": task_id},
        ) from exc
    response = RunBudgetTaskUsageReadResponse(
        schema_version="1.0",
        run_id=budget.run_id,
        task_id=task_id,
        usage=usage,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="run_budget_task_usage_read_complete",
            module=logger.name,
            fields={
                "run_id": response.run_id,
                "task_id": response.task_id,
                **_usage_log_fields("usage", response.usage),
            },
        )
    )
    return response


def read_usage_run_summary(
    request: LLMUsageRunSummaryRequest,
    ctx: RunContext,
) -> LLMUsageRunSummaryResponse:
    """Read bounded canonical provider usage without creating another ledger."""
    if (
        request.schema_version != "1.0"
        or not str(request.db_path or "").strip()
        or not str(request.run_id or "").strip()
    ):
        raise AppError(
            code="llm_usage_run_summary_request_invalid",
            message="Usage-run summary requires a ledger path and run identifier",
            retryable=False,
        )
    path = Path(request.db_path)
    _apply_budget_authority_migrations(path, ctx)
    action = str(request.action or "").strip()
    task_id = str(request.task_id or "").strip()
    where = "run_id = ?"
    params: tuple[object, ...] = (str(request.run_id),)
    if task_id:
        where += " and task_id = ?"
        params = (*params, task_id)
    if action:
        where += " and action = ?"
        params = (*params, action)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, sqlite3.connect(path) as conn:
            _ensure_schema(conn)
            row = conn.execute(
                f"""
                select count(*), coalesce(sum(input_tokens), 0),
                       coalesce(sum(cached_input_tokens), 0),
                       coalesce(sum(output_tokens), 0),
                       coalesce(sum(estimated_cost_usd), 0.0)
                from llm_usage_events
                where {where}
                """,
                params,
            ).fetchone()
    except sqlite3.Error as exc:
        raise AppError(
            code="llm_usage_run_summary_read_failed",
            message="Canonical usage-run summary could not be read",
            cause=exc,
            retryable=False,
            context={"db_path": str(path), "run_id": str(request.run_id)},
        ) from exc
    response = LLMUsageRunSummaryResponse(
        schema_version="1.0",
        run_id=str(request.run_id),
        task_id=task_id,
        action=action,
        call_count=int(row[0] or 0) if row is not None else 0,
        input_tokens=int(row[1] or 0) if row is not None else 0,
        cached_input_tokens=int(row[2] or 0) if row is not None else 0,
        output_tokens=int(row[3] or 0) if row is not None else 0,
        estimated_cost_usd=round(float(row[4] or 0.0), 6) if row is not None else 0.0,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_run_summary_read",
            module=logger.name,
            fields={
                "run_id": response.run_id,
                "task_id": response.task_id,
                "action": response.action,
                "call_count": response.call_count,
                "input_tokens": response.input_tokens,
                "cached_input_tokens": response.cached_input_tokens,
                "output_tokens": response.output_tokens,
                "estimated_cost_usd": response.estimated_cost_usd,
            },
        )
    )
    return response


def read_policy_effectiveness(
    request: LLMPolicyEffectivenessRequest,
    ctx: RunContext,
) -> LLMPolicyEffectivenessResponse:
    """Return deterministic, read-only execution-identity effectiveness evidence."""

    if request.schema_version != "1.0" or not str(request.db_path or "").strip():
        raise AppError(
            code="llm_policy_effectiveness_request_invalid",
            message="Policy effectiveness requires a supported schema version and usage DB path",
            retryable=False,
        )
    path = Path(request.db_path)
    if not path.exists():
        return LLMPolicyEffectivenessResponse(schema_version="1.0")
    try:
        with sqlite3.connect(
            f"file:{path.resolve().as_posix()}?mode=ro", uri=True
        ) as conn:
            table = conn.execute(
                "select 1 from sqlite_master where type = 'table' and name = 'llm_usage_events'"
            ).fetchone()
            raw_rows = (
                list(
                    conn.execute(
                        """
                        select provider, model, prompt_namespace, input_tokens,
                               cached_input_tokens, output_tokens, estimated_cost_usd,
                               cache_decision, schema_validation_status, workflow,
                               plan_hash, metadata_json
                        from llm_usage_events
                        order by provider, model, prompt_namespace, id
                        """
                    )
                )
                if table is not None
                else []
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="llm_policy_effectiveness_read_failed",
            message="Policy effectiveness report could not read the canonical usage ledger",
            cause=exc,
            retryable=False,
            context={"db_path": str(path)},
        ) from exc

    aggregates: dict[tuple[str, str, str, str], dict[str, object]] = {}
    unattributed = 0
    for row in raw_rows:
        metadata = _safe_metadata(str(row[11] or ""))
        identity = str(metadata.get("execution_identity") or "").strip()
        if not identity:
            identity = "legacy_unattributed"
            unattributed += 1
        namespace = str(row[2] or "").strip() or "legacy_unattributed"
        key = (identity, namespace, str(row[0] or ""), str(row[1] or ""))
        aggregate = aggregates.setdefault(
            key,
            {
                "calls": 0,
                "validated": 0,
                "cache_reuse": 0,
                "latencies": [],
                "input_tokens": 0,
                "cached_input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": 0.0,
                "regeneration_plans": set(),
            },
        )
        aggregate["calls"] = _integer_value(aggregate["calls"]) + 1
        aggregate["validated"] = _integer_value(aggregate["validated"]) + int(
            str(row[8] or "") == "valid"
        )
        aggregate["cache_reuse"] = _integer_value(aggregate["cache_reuse"]) + int(
            str(row[7] or "") in {"provider_hit", "semantic_hit", "hit"}
        )
        latency_value = metadata.get("provider_latency_ms")
        if isinstance(latency_value, (int, float)) and latency_value >= 0:
            cast(list[float], aggregate["latencies"]).append(float(latency_value))
        aggregate["input_tokens"] = _integer_value(
            aggregate["input_tokens"]
        ) + _integer_value(row[3])
        aggregate["cached_input_tokens"] = _integer_value(
            aggregate["cached_input_tokens"]
        ) + _integer_value(row[4])
        aggregate["output_tokens"] = _integer_value(
            aggregate["output_tokens"]
        ) + _integer_value(row[5])
        aggregate["estimated_cost_usd"] = _float_value(
            aggregate["estimated_cost_usd"]
        ) + _float_value(row[6])
        if str(row[9] or "") == "report_generation" and str(row[10] or ""):
            cast(set[str], aggregate["regeneration_plans"]).add(str(row[10]))

    rows: list[LLMPolicyEffectivenessRow] = []
    for (identity, namespace, provider, model), aggregate in sorted(aggregates.items()):
        calls = _integer_value(aggregate["calls"])
        latencies = cast(list[float], aggregate["latencies"])
        rows.append(
            LLMPolicyEffectivenessRow(
                schema_version="1.0",
                execution_identity=identity,
                prompt_namespace=namespace,
                provider=provider,
                model=model,
                call_count=calls,
                validated_call_count=_integer_value(aggregate["validated"]),
                validation_rate=round(_integer_value(aggregate["validated"]) / calls, 6)
                if calls
                else 0.0,
                cache_reuse_count=_integer_value(aggregate["cache_reuse"]),
                cache_reuse_rate=round(
                    _integer_value(aggregate["cache_reuse"]) / calls, 6
                )
                if calls
                else 0.0,
                latency_record_count=len(latencies),
                average_latency_ms=(
                    round(sum(latencies) / len(latencies), 3) if latencies else None
                ),
                input_tokens=_integer_value(aggregate["input_tokens"]),
                cached_input_tokens=_integer_value(aggregate["cached_input_tokens"]),
                output_tokens=_integer_value(aggregate["output_tokens"]),
                estimated_cost_usd=round(
                    _float_value(aggregate["estimated_cost_usd"]), 6
                ),
                regeneration_count=len(cast(set[str], aggregate["regeneration_plans"])),
            )
        )
    response = LLMPolicyEffectivenessResponse(
        schema_version="1.0",
        rows=rows,
        unattributed_legacy_call_count=unattributed,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_policy_effectiveness_complete",
            module=logger.name,
            fields={
                "row_count": len(rows),
                "unattributed_legacy_call_count": unattributed,
                "provider_calls": len(raw_rows),
            },
        )
    )
    return response


def _integer_value(value: object) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return 0
    return 0


def _float_value(value: object) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return 0.0
    return 0.0


_BUDGET_DECISIONS = {"allow", "warn", "defer", "pause", "stop", "authorized_override"}
_BUDGET_LIMIT_FIELDS = (
    ("spend_usd", "max_spend_usd"),
    ("tokens", "max_tokens"),
    ("calls", "max_calls"),
    ("steps", "max_steps"),
    ("runtime_seconds", "max_runtime_seconds"),
    ("retries", "max_retries"),
    ("browser_launches", "max_browser_launches"),
    ("drive_writes", "max_drive_writes"),
    ("drive_reads", "max_drive_reads"),
    ("wordpress_writes", "max_wordpress_writes"),
    ("pdfs", "max_pdfs"),
    ("mailbox_reads", "max_mailbox_reads"),
)


def _apply_budget_authority_migrations(path: Path, ctx: RunContext) -> None:
    """Use the shared migration service for policy-state schema changes."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, sqlite3.connect(path) as conn:
        apply_llm_usage_ledger_migrations(
            SqliteMigrationApplyRequest(
                schema_version="1.0",
                database_key="llm_usage_ledger",
                db_path=str(path),
                target_version=4,
                ctx=ctx,
            ),
            conn,
        )


def _parse_deferred_work_time(value: str, *, field_name: str) -> datetime:
    normalized = str(value or "").strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise AppError(
            code="deferred_work_time_invalid",
            message="Deferred-work timestamps must be ISO-8601 UTC values",
            cause=exc,
            retryable=False,
            context={"field": field_name},
        ) from exc
    if parsed.tzinfo is None:
        raise AppError(
            code="deferred_work_time_invalid",
            message="Deferred-work timestamps must include a UTC offset",
            retryable=False,
            context={"field": field_name},
        )
    return parsed.astimezone(timezone.utc)


def _normalized_deferred_work_time(value: str, *, field_name: str) -> str:
    return _parse_deferred_work_time(value, field_name=field_name).isoformat()


def _deferred_work_times(request: BudgetRequest, *, now: datetime) -> tuple[str, str]:
    earliest = (
        _normalized_deferred_work_time(
            request.deferred_earliest_run_at_utc, field_name="earliest_run_at_utc"
        )
        if request.deferred_earliest_run_at_utc.strip()
        else (now + timedelta(seconds=_DEFERRED_WORK_RETRY_DELAY_SECONDS)).isoformat()
    )
    deadline = (
        _normalized_deferred_work_time(
            request.deferred_deadline_at_utc, field_name="deadline_at_utc"
        )
        if request.deferred_deadline_at_utc.strip()
        else (now + timedelta(seconds=_DEFERRED_WORK_DEADLINE_SECONDS)).isoformat()
    )
    if _parse_deferred_work_time(
        deadline, field_name="deadline_at_utc"
    ) <= _parse_deferred_work_time(earliest, field_name="earliest_run_at_utc"):
        raise AppError(
            code="deferred_work_deadline_invalid",
            message="Deferred-work deadline must be later than its earliest run time",
            retryable=False,
        )
    return earliest, deadline


def _deferred_work_key(request: BudgetRequest) -> str:
    material = request.idempotency_key or "|".join(
        (
            request.run_id,
            request.workflow_id,
            request.publisher_id,
            request.report_id,
            request.source_id,
            request.resource_type,
            request.operation,
        )
    )
    return sha256(material.encode("utf-8")).hexdigest()


def _deferred_artifacts_from_request(
    request: BudgetRequest,
) -> list[dict[str, str]]:
    artifacts: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for raw in request.reusable_artifact_references:
        if not isinstance(raw, (tuple, list)) or len(raw) != 3:
            continue
        kind, reference, checksum = (str(value or "").strip() for value in raw)
        if not kind or not reference or (kind, reference, checksum) in seen:
            continue
        seen.add((kind, reference, checksum))
        artifacts.append(
            {
                "schema_version": "1.0",
                "kind": kind,
                "reference": reference,
                "checksum": checksum,
            }
        )
    return artifacts


def _serialized_budget_request(request: BudgetRequest) -> str:
    return json.dumps(
        asdict(request), ensure_ascii=True, sort_keys=True, separators=(",", ":")
    )


def _upsert_deferred_work(
    conn: sqlite3.Connection,
    *,
    request: BudgetRequest,
    decision: BudgetDecision,
    now: datetime,
) -> None:
    max_attempts = int(request.deferred_max_attempts)
    if not 1 <= max_attempts <= _DEFERRED_WORK_MAX_ATTEMPTS:
        raise AppError(
            code="deferred_work_max_attempts_invalid",
            message="Deferred-work maximum attempts must be within the bounded policy range",
            retryable=False,
            context={"max_attempts": max_attempts},
        )
    earliest, deadline = _deferred_work_times(request, now=now)
    now_utc = now.isoformat()
    conn.execute(
        """
        INSERT INTO budget_authority_deferred_work(
            work_key, schema_version, deferred_at_utc, run_id, workflow_id,
            publisher_name, report_id, resource_type, operation, idempotency_key,
            next_action, affected_limit, policy_version, status, stage, source_id,
            plan_hash, reason_code, earliest_run_at_utc, deadline_at_utc,
            attempt_count, max_attempts, reusable_artifacts_json, lease_owner,
            lease_expires_at_utc, terminal_status, remediation_id, updated_at_utc,
            completed_at_utc, defer_count, budget_request_json
        ) VALUES (?, '2.0', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?, ?, 0, ?, ?, '', '', '', '', ?, '', 1, ?)
        ON CONFLICT(work_key) DO UPDATE SET
            schema_version=CASE WHEN status='pending' THEN excluded.schema_version ELSE schema_version END,
            stage=CASE WHEN status='pending' THEN excluded.stage ELSE stage END,
            source_id=CASE WHEN status='pending' THEN excluded.source_id ELSE source_id END,
            plan_hash=CASE WHEN status='pending' THEN excluded.plan_hash ELSE plan_hash END,
            reason_code=CASE WHEN status='pending' THEN excluded.reason_code ELSE reason_code END,
            earliest_run_at_utc=CASE WHEN status='pending' THEN excluded.earliest_run_at_utc ELSE earliest_run_at_utc END,
            deadline_at_utc=CASE WHEN status='pending' THEN excluded.deadline_at_utc ELSE deadline_at_utc END,
            max_attempts=CASE WHEN status='pending' THEN excluded.max_attempts ELSE max_attempts END,
            reusable_artifacts_json=CASE WHEN status='pending' THEN excluded.reusable_artifacts_json ELSE reusable_artifacts_json END,
            budget_request_json=CASE WHEN status='pending' THEN excluded.budget_request_json ELSE budget_request_json END,
            next_action=CASE WHEN status IN ('pending','leased') THEN excluded.next_action ELSE next_action END,
            affected_limit=CASE WHEN status IN ('pending','leased') THEN excluded.affected_limit ELSE affected_limit END,
            policy_version=CASE WHEN status IN ('pending','leased') THEN excluded.policy_version ELSE policy_version END,
            updated_at_utc=CASE WHEN status IN ('pending','leased') THEN excluded.updated_at_utc ELSE updated_at_utc END,
            defer_count=defer_count
        """,
        (
            _deferred_work_key(request),
            now_utc,
            request.run_id,
            request.workflow_id,
            request.publisher_id,
            request.report_id,
            request.resource_type,
            request.operation,
            request.idempotency_key,
            decision.next_action,
            decision.affected_limit,
            decision.policy_version,
            request.stage,
            request.source_id,
            request.plan_hash,
            decision.reason_code,
            earliest,
            deadline,
            max_attempts,
            json.dumps(_deferred_artifacts_from_request(request), sort_keys=True),
            now_utc,
            _serialized_budget_request(request),
        ),
    )


def _empty_budget_usage() -> RunBudgetUsage:
    return RunBudgetUsage(schema_version="1.0")


def _add_budget_usage(*usages: RunBudgetUsage) -> RunBudgetUsage:
    fields = (
        "spend_usd",
        "tokens",
        "calls",
        "steps",
        "runtime_seconds",
        "retries",
        "browser_launches",
        "drive_writes",
        "drive_reads",
        "wordpress_writes",
        "pdfs",
        "mailbox_reads",
    )
    return RunBudgetUsage(
        schema_version="1.0",
        **{field: sum(getattr(usage, field) for usage in usages) for field in fields},
    )


def _usage_log_fields(prefix: str, usage: RunBudgetUsage) -> dict[str, float | int]:
    """Return bounded scalar usage fields suitable for a structured event."""
    return {
        f"{prefix}_spend_usd": usage.spend_usd,
        f"{prefix}_tokens": usage.tokens,
        f"{prefix}_calls": usage.calls,
        f"{prefix}_steps": usage.steps,
        f"{prefix}_runtime_seconds": usage.runtime_seconds,
        f"{prefix}_retries": usage.retries,
        f"{prefix}_browser_launches": usage.browser_launches,
        f"{prefix}_drive_reads": usage.drive_reads,
        f"{prefix}_drive_writes": usage.drive_writes,
        f"{prefix}_wordpress_writes": usage.wordpress_writes,
        f"{prefix}_pdfs": usage.pdfs,
        f"{prefix}_mailbox_reads": usage.mailbox_reads,
    }


def _request_usage(request: BudgetRequest) -> RunBudgetUsage:
    resource = str(request.resource_type or "").strip().lower()
    writes = max(0, int(request.estimated_writes))
    return RunBudgetUsage(
        schema_version="1.0",
        spend_usd=max(0.0, float(request.estimated_cost_usd or 0.0)),
        tokens=max(0, int(request.estimated_tokens)),
        calls=max(0, int(request.estimated_calls))
        or (
            1
            if resource
            in {
                "llm_provider",
                "embedding",
                "ocr",
                "vision",
                "browser_use_model",
                "vector_store",
            }
            else 0
        ),
        steps=max(0, int(request.estimated_steps)),
        runtime_seconds=max(0, int(request.estimated_duration_seconds)),
        retries=1 if resource == "retry" else 0,
        browser_launches=1 if resource == "browser_launch" else 0,
        drive_writes=writes if resource == "drive_write" else 0,
        drive_reads=max(0, int(request.estimated_drive_reads))
        or (1 if resource == "drive_read" else 0),
        wordpress_writes=writes if resource == "wordpress_write" else 0,
        pdfs=max(0, int(request.estimated_pdfs))
        or (1 if resource == "pdf_process" else 0),
        mailbox_reads=max(0, int(request.estimated_mailbox_reads))
        or (1 if resource == "mailbox_read" else 0),
    )


def _legacy_limits(budget: RunBudget) -> RunBudgetLimits:
    return RunBudgetLimits(
        schema_version="1.0",
        max_spend_usd=budget.max_spend_usd,
        max_tokens=budget.max_tokens,
        max_calls=budget.max_calls,
        max_steps=budget.max_steps,
        max_runtime_seconds=budget.max_runtime_seconds,
        max_retries=budget.max_retries,
        max_browser_launches=budget.max_browser_launches,
        max_drive_writes=budget.max_drive_writes,
        max_drive_reads=budget.max_drive_reads,
        max_wordpress_writes=budget.max_wordpress_writes,
        max_pdfs=budget.max_pdfs,
        max_mailbox_reads=budget.max_mailbox_reads,
    )


def _scope_limits(budget: RunBudget, scope: str) -> RunBudgetLimits:
    configured = {
        "run": budget.run_limits,
        "day": budget.day_limits,
        "publisher": budget.publisher_limits,
    }[scope]
    if configured is not None:
        return configured
    if scope == "run":
        return _legacy_limits(budget)
    return RunBudgetLimits(schema_version="1.0")


def _reservation_usage_for_scope(
    conn: sqlite3.Connection,
    *,
    scope: str,
    request: BudgetRequest,
    day_utc: str,
    now_utc: str,
) -> RunBudgetUsage:
    clauses = ["status = 'reserved'", "expires_at_utc > ?"]
    params: list[object] = [now_utc]
    if request.idempotency_key:
        clauses.append("reservation_key <> ?")
        params.append(request.idempotency_key)
    if scope == "run":
        clauses.append("run_id = ?")
        params.append(request.run_id)
    elif scope == "day":
        clauses.append("day_utc = ?")
        params.append(day_utc)
    else:
        clauses.extend(("day_utc = ?", "publisher_name = ?"))
        params.extend((day_utc, request.publisher_id))
    where = " and ".join(clauses)
    row = conn.execute(
        f"""
        select coalesce(sum(estimated_cost_usd), 0.0),
               coalesce(sum(estimated_tokens), 0),
               coalesce(sum(estimated_calls), 0),
               coalesce(sum(estimated_steps), 0),
               coalesce(sum(estimated_duration_seconds), 0),
               coalesce(sum(case when resource_type = 'retry' then 1 else 0 end), 0),
               coalesce(sum(case when resource_type = 'browser_launch' then 1 else 0 end), 0),
               coalesce(sum(case when resource_type = 'drive_write' then estimated_writes else 0 end), 0),
               coalesce(sum(estimated_drive_reads), 0),
               coalesce(sum(case when resource_type = 'wordpress_write' then estimated_writes else 0 end), 0),
               coalesce(sum(estimated_pdfs), 0),
               coalesce(sum(estimated_mailbox_reads), 0)
        from budget_authority_reservations where {where}
        """,
        tuple(params),
    ).fetchone()
    values = row or (0.0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    return RunBudgetUsage(
        schema_version="1.0",
        spend_usd=float(values[0] or 0.0),
        tokens=int(values[1] or 0),
        calls=int(values[2] or 0),
        steps=int(values[3] or 0),
        runtime_seconds=int(values[4] or 0),
        retries=int(values[5] or 0),
        browser_launches=int(values[6] or 0),
        drive_writes=int(values[7] or 0),
        drive_reads=int(values[8] or 0),
        wordpress_writes=int(values[9] or 0),
        pdfs=int(values[10] or 0),
        mailbox_reads=int(values[11] or 0),
    )


def _actual_usage_for_scope(
    conn: sqlite3.Connection, *, scope: str, request: BudgetRequest, day_utc: str
) -> RunBudgetUsage:
    if scope == "run":
        return _read_budget_usage_for_scope(
            conn,
            llm_where="run_id = ?",
            llm_params=(request.run_id,),
            event_where="run_id = ?",
            event_params=(request.run_id,),
        )
    if scope == "day":
        return _read_budget_usage_for_scope(
            conn,
            llm_where="substr(timestamp_utc, 1, 10) = ?",
            llm_params=(day_utc,),
            event_where="day_utc = ?",
            event_params=(day_utc,),
        )
    if not request.publisher_id:
        return _empty_budget_usage()
    return _read_budget_usage_for_scope(
        conn,
        llm_where="publisher_name = ? and substr(timestamp_utc, 1, 10) = ?",
        llm_params=(request.publisher_id, day_utc),
        event_where="publisher_name = ? and day_utc = ?",
        event_params=(request.publisher_id, day_utc),
    )


def _validate_budget_request(request: BudgetRequest) -> None:
    if request.schema_version != "1.0":
        raise AppError(
            code="budget_request_schema_version_invalid",
            message="Budget request schema version is unsupported",
            retryable=False,
        )
    _validate_run_budget(request.budget)
    if (
        request.run_id != request.budget.run_id
        or not request.workflow_id.strip()
        or not request.resource_type.strip()
        or not request.operation.strip()
    ):
        raise AppError(
            code="budget_request_identity_invalid",
            message="Budget request requires matching run, workflow, resource, and operation identifiers",
            retryable=False,
        )
    if (
        request.publisher_id
        and request.budget.publisher_name
        and request.publisher_id != request.budget.publisher_name
    ):
        raise AppError(
            code="budget_request_publisher_mismatch",
            message="Budget request publisher must match the governed budget",
            retryable=False,
        )
    if (
        request.attempt_number < 0
        or request.reservation_ttl_seconds <= 0
        or request.reservation_ttl_seconds > _MAX_BUDGET_RESERVATION_TTL_SECONDS
        or not 0.0 <= float(request.forecast_confidence) <= 1.0
        or any(
            float(value) < 0
            for value in (
                request.estimated_cost_usd or 0.0,
                request.estimated_tokens,
                request.estimated_calls,
                request.estimated_steps,
                request.estimated_writes,
                request.estimated_drive_reads,
                request.estimated_pdfs,
                request.estimated_mailbox_reads,
                request.estimated_duration_seconds,
            )
        )
    ):
        raise AppError(
            code="budget_request_estimate_invalid",
            message="Budget request estimate fields are invalid",
            retryable=False,
        )


def _apply_historical_cost_forecast(request: BudgetRequest) -> BudgetRequest:
    """Use the canonical derived median only when a caller has no explicit price."""
    if request.estimated_cost_usd is not None or not all(
        (request.provider, request.model)
    ):
        return request
    median_path = _median_db_path(Path(request.budget.usage_db_path))
    if not median_path.is_file():
        return replace(
            request,
            estimated_cost_usd=0.0,
            forecast_method="unavailable",
            forecast_confidence=0.0,
        )
    try:
        with sqlite3.connect(median_path) as conn:
            row = conn.execute(
                """
                select sample_count, median_estimated_cost_usd from llm_usage_medians
                where provider = ? and task = ? and action = ? and model = ?
                  and prompt_namespace = ?
                """,
                (
                    request.provider,
                    request.operation,
                    request.operation,
                    request.model,
                    request.prompt_namespace,
                ),
            ).fetchone()
    except sqlite3.Error:
        row = None
    if row is None:
        return replace(
            request,
            estimated_cost_usd=0.0,
            forecast_method="unavailable",
            forecast_confidence=0.0,
        )
    samples = max(0, int(row[0] or 0))
    return replace(
        request,
        estimated_cost_usd=round(float(row[1] or 0.0), 6),
        forecast_method="historical_median",
        forecast_confidence=min(1.0, samples / 20.0),
    )


def _validate_override(request: BudgetRequest, *, now: datetime) -> None:
    override = request.requested_override
    if override is None:
        return
    if override.schema_version != "1.0" or not all(
        (
            override.actor.strip(),
            override.reason.strip(),
            override.scope.strip(),
            override.expires_at_utc.strip(),
            override.policy_version.strip(),
        )
    ):
        raise AppError(
            code="budget_override_audit_missing",
            message="Budget overrides require actor, reason, scope, expiry, and policy version",
            retryable=False,
        )
    if (
        override.policy_version != request.budget.policy_version
        or override.scope not in {"run", "day", "publisher", "all"}
    ):
        raise AppError(
            code="budget_override_scope_invalid",
            message="Budget override scope or policy version is invalid",
            retryable=False,
        )
    try:
        expires = datetime.fromisoformat(override.expires_at_utc.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError(
            code="budget_override_expiry_invalid",
            message="Budget override expiry must be ISO-8601 UTC",
            cause=exc,
            retryable=False,
        ) from exc
    if expires.tzinfo is None or expires <= now:
        raise AppError(
            code="budget_override_expired",
            message="Budget override has expired",
            retryable=False,
        )


def _budget_limit_breach(
    limits: RunBudgetLimits, usage: RunBudgetUsage
) -> tuple[str, float | int, float | int] | None:
    for usage_field, limit_field in _BUDGET_LIMIT_FIELDS:
        limit = getattr(limits, limit_field)
        value = getattr(usage, usage_field)
        # ``usage`` includes the proposed side effect.  A maximum of one PDF
        # must therefore admit the first PDF and stop the second one.
        if limit is not None and value > limit:
            return usage_field, value, limit
    return None


def _budget_warning(
    limits: RunBudgetLimits, usage: RunBudgetUsage, fraction: float
) -> tuple[str, float | int, float | int] | None:
    if not 0.0 < fraction < 1.0:
        return None
    for usage_field, limit_field in _BUDGET_LIMIT_FIELDS:
        limit = getattr(limits, limit_field)
        value = getattr(usage, usage_field)
        if limit is not None and value >= limit * fraction:
            return usage_field, value, limit
    return None


def _record_budget_authority_event(
    conn: sqlite3.Connection,
    *,
    request: BudgetRequest,
    decision: BudgetDecision,
    now_utc: str,
) -> None:
    override = request.requested_override
    conn.execute(
        """
        insert into budget_authority_events(
            schema_version, timestamp_utc, run_id, workflow_id, publisher_name,
            report_id, resource_type, operation, decision, reason_code,
            policy_version, reservation_key, override_actor, override_scope,
            override_reason, override_expires_at_utc, details_json
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "1.0",
            now_utc,
            request.run_id,
            request.workflow_id,
            request.publisher_id,
            request.report_id,
            request.resource_type,
            request.operation,
            decision.decision,
            decision.reason_code,
            decision.policy_version,
            decision.reservation_key,
            override.actor if override else "",
            override.scope if override else "",
            override.reason if override else "",
            override.expires_at_utc if override else "",
            json.dumps(
                {
                    "affected_limit": decision.affected_limit,
                    "next_action": decision.next_action,
                    "forecast_method": request.forecast_method,
                    "forecast_confidence": request.forecast_confidence,
                    "forecast_cost_usd": request.estimated_cost_usd or 0.0,
                    "forecast_calls": _request_usage(request).calls,
                    "forecast_usage": _request_usage(request).__dict__,
                },
                sort_keys=True,
            ),
        ),
    )


def evaluate_budget_request(request: BudgetRequest, ctx: RunContext) -> BudgetDecision:
    """Atomically decide and, when requested, reserve one future side effect.

    The canonical LLM usage ledger remains the source of actual monetary usage;
    this function stores only forecasts, decision evidence, and override audit.
    """
    _validate_budget_request(request)
    request = replace(
        request,
        reservation_ttl_seconds=min(
            request.reservation_ttl_seconds,
            request.budget.reservation_ttl_seconds,
        ),
    )
    request = _apply_historical_cost_forecast(request)
    path = Path(request.budget.usage_db_path)
    _apply_budget_authority_migrations(path, ctx)
    now = datetime.now(timezone.utc)
    _validate_override(request, now=now)
    now_utc = now.isoformat()
    day_utc = _budget_day_utc(request.budget)
    proposed = _request_usage(request)
    effect_enabled = not request.budget.enabled_effect_kinds or (
        str(request.resource_type).strip() in set(request.budget.enabled_effect_kinds)
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="budget_request",
            module=logger.name,
            fields={
                "run_id": request.run_id,
                "workflow_id": request.workflow_id,
                "publisher_id": request.publisher_id,
                "report_id": request.report_id,
                "resource_type": request.resource_type,
                "operation": request.operation,
                "attempt_number": request.attempt_number,
                "policy_version": request.budget.policy_version,
            },
        )
    )
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            conn.execute("begin immediate")
            _ensure_schema(conn)
            expired = conn.execute(
                "update budget_authority_reservations set status = 'expired' where status = 'reserved' and expires_at_utc <= ?",
                (now_utc,),
            ).rowcount
            scope_rows: list[
                tuple[str, RunBudgetUsage, RunBudgetUsage, RunBudgetUsage]
            ] = []
            for scope in ("run", "day", "publisher"):
                if scope == "publisher" and not request.publisher_id:
                    continue
                actual = _actual_usage_for_scope(
                    conn, scope=scope, request=request, day_utc=day_utc
                )
                reserved = _reservation_usage_for_scope(
                    conn, scope=scope, request=request, day_utc=day_utc, now_utc=now_utc
                )
                scope_rows.append(
                    (
                        scope,
                        actual,
                        reserved,
                        _add_budget_usage(actual, reserved, proposed),
                    )
                )
            breach: (
                tuple[
                    str,
                    tuple[str, float | int, float | int],
                    RunBudgetUsage,
                    RunBudgetUsage,
                    RunBudgetUsage,
                ]
                | None
            ) = None
            if effect_enabled:
                for scope, actual, reserved, projected in scope_rows:
                    limit_breach = _budget_limit_breach(
                        _scope_limits(request.budget, scope), projected
                    )
                    if limit_breach is not None:
                        breach = (scope, limit_breach, actual, reserved, projected)
                        break
            warning: (
                tuple[
                    str,
                    tuple[str, float | int, float | int],
                    RunBudgetUsage,
                    RunBudgetUsage,
                    RunBudgetUsage,
                ]
                | None
            ) = None
            if effect_enabled and breach is None:
                for scope, actual, reserved, projected in scope_rows:
                    limit_warning = _budget_warning(
                        _scope_limits(request.budget, scope),
                        projected,
                        request.budget.warning_fraction,
                    )
                    if limit_warning is not None:
                        warning = (scope, limit_warning, actual, reserved, projected)
                        break
            selected = breach if breach is not None else warning
            base_actual = (
                selected[2]
                if selected is not None
                else (scope_rows[0][1] if scope_rows else _empty_budget_usage())
            )
            base_reserved = (
                selected[3]
                if selected is not None
                else (scope_rows[0][2] if scope_rows else _empty_budget_usage())
            )
            base_projected = (
                selected[4]
                if selected is not None
                else (scope_rows[0][3] if scope_rows else proposed)
            )
            affected_limit = ""
            if breach:
                scope, metric = breach[0], breach[1][0]
                affected_limit = f"{scope}.{metric}"
                override = request.requested_override
                if override is not None and override.scope in {scope, "all"}:
                    decision_name, reason_code, next_action = (
                        "authorized_override",
                        "budget_override_authorized",
                        "proceed_with_audited_override",
                    )
                else:
                    decision_name = str(request.budget.limit_decision or "stop").lower()
                    reason_code, next_action = (
                        "budget_limit_reached",
                        "defer_or_request_expiry_bound_override",
                    )
            elif warning:
                affected_limit = f"{warning[0]}.{warning[1][0]}"
                decision_name, reason_code, next_action = (
                    "warn",
                    "budget_warning_threshold",
                    "proceed_and_monitor_budget",
                )
            elif effect_enabled:
                decision_name, reason_code, next_action = (
                    "allow",
                    "within_budget",
                    "proceed",
                )
            else:
                decision_name, reason_code, next_action = (
                    "allow",
                    "effect_category_disabled",
                    "proceed_without_budget_reservation",
                )
            if decision_name not in _BUDGET_DECISIONS:
                raise AppError(
                    code="budget_limit_decision_invalid",
                    message="Budget limit decision must be defer, pause, or stop",
                    retryable=False,
                )
            reservation_key = (
                request.idempotency_key
                if request.reserve_in_flight
                and effect_enabled
                and decision_name in {"allow", "warn", "authorized_override"}
                else ""
            )
            created = False
            if reservation_key:
                cursor = conn.execute(
                    """
                    insert into budget_authority_reservations(
                        reservation_key, schema_version, run_id, task_id, span_id,
                        workflow_id, publisher_name,
                        report_id, resource_type, operation, day_utc, estimated_cost_usd,
                        estimated_tokens, estimated_calls, estimated_steps, estimated_writes,
                        estimated_drive_reads, estimated_pdfs, estimated_mailbox_reads,
                        estimated_duration_seconds, status, expires_at_utc,
                        created_at_utc
                    ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'reserved', ?, ?)
                    on conflict(reservation_key) do nothing
                    """,
                    (
                        reservation_key,
                        "1.0",
                        request.run_id,
                        ctx.task_id,
                        ctx.span_id,
                        request.workflow_id,
                        request.publisher_id,
                        request.report_id,
                        request.resource_type,
                        request.operation,
                        day_utc,
                        proposed.spend_usd,
                        proposed.tokens,
                        proposed.calls,
                        proposed.steps,
                        max(proposed.drive_writes, proposed.wordpress_writes),
                        proposed.drive_reads,
                        proposed.pdfs,
                        proposed.mailbox_reads,
                        proposed.runtime_seconds,
                        (
                            now + timedelta(seconds=request.reservation_ttl_seconds)
                        ).isoformat(),
                        now_utc,
                    ),
                )
                created = cursor.rowcount == 1
            decision = BudgetDecision(
                schema_version="1.0",
                decision=decision_name,
                reason_code=reason_code,
                affected_limit=affected_limit,
                current_usage=base_actual,
                reserved_usage=base_reserved,
                projected_usage=base_projected,
                next_action=next_action,
                policy_version=request.budget.policy_version,
                reservation_key=reservation_key,
                reservation_created=created,
            )
            _record_budget_authority_event(
                conn, request=request, decision=decision, now_utc=now_utc
            )
            if decision.decision == "defer":
                _upsert_deferred_work(conn, request=request, decision=decision, now=now)
            conn.commit()
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise AppError(
            code="budget_authority_evaluation_failed",
            message="Canonical budget authority could not decide the operation",
            cause=exc,
            retryable=False,
            context={"db_path": str(path), "operation": request.operation},
        ) from exc
    fields = {
        "run_id": request.run_id,
        "workflow_id": request.workflow_id,
        "publisher_id": request.publisher_id,
        "report_id": request.report_id,
        "resource_type": request.resource_type,
        "operation": request.operation,
        "decision": decision.decision,
        "reason_code": decision.reason_code,
        "affected_limit": decision.affected_limit,
        "policy_version": decision.policy_version,
        "reservation_key": decision.reservation_key,
        "reservation_created": decision.reservation_created,
        "forecast_cost_usd": request.estimated_cost_usd or 0.0,
        "current_cost_usd": decision.current_usage.spend_usd,
        "reserved_cost_usd": decision.reserved_usage.spend_usd,
        "projected_cost_usd": decision.projected_usage.spend_usd,
        "forecast_calls": _request_usage(request).calls,
        "forecast_method": request.forecast_method,
        "forecast_confidence": request.forecast_confidence,
        "override_actor": (
            request.requested_override.actor if request.requested_override else ""
        ),
        **_usage_log_fields("forecast", _request_usage(request)),
        "override_scope": (
            request.requested_override.scope if request.requested_override else ""
        ),
        "override_expires_at_utc": (
            request.requested_override.expires_at_utc
            if request.requested_override
            else ""
        ),
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event="budget_decision",
            module=logger.name,
            fields=fields,
        )
    )
    if expired:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="reservation_expired",
                module=logger.name,
                fields={**fields, "expired_count": expired},
            )
        )
    if decision.reservation_created:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="reservation_created",
                module=logger.name,
                fields=fields,
            )
        )
    if decision.decision == "authorized_override":
        logger.info(
            log_event(
                ctx,
                role="service",
                event="override_used",
                module=logger.name,
                fields=fields,
            )
        )
    if decision.decision in {"defer", "pause", "stop"}:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="side_effect_prevented",
                module=logger.name,
                fields={
                    **fields,
                    "avoided_effect": True,
                    "avoided_calls": _request_usage(request).calls,
                    "avoided_estimated_cost_usd": request.estimated_cost_usd or 0.0,
                },
            )
        )
        if decision.decision == "defer":
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="work_deferred",
                    module=logger.name,
                    fields=fields,
                )
            )
    return decision


_DEFERRED_WORK_SELECT = """
SELECT work_key, schema_version, deferred_at_utc, run_id, workflow_id,
       publisher_name, report_id, resource_type, operation, idempotency_key,
       affected_limit, status, stage, source_id, plan_hash, reason_code,
       earliest_run_at_utc, deadline_at_utc, attempt_count, max_attempts,
       reusable_artifacts_json, lease_owner, lease_expires_at_utc,
       terminal_status, remediation_id, updated_at_utc, completed_at_utc,
       defer_count, budget_request_json
FROM budget_authority_deferred_work
"""


def _deferred_artifacts_from_json(raw: object) -> list[DeferredWorkArtifactReference]:
    try:
        payload = json.loads(str(raw or "[]"))
    except json.JSONDecodeError:
        payload = []
    artifacts: list[DeferredWorkArtifactReference] = []
    for item in payload if isinstance(payload, list) else []:
        if not isinstance(item, dict):
            continue
        kind = str(item.get("kind") or "").strip()
        reference = str(item.get("reference") or "").strip()
        if not kind or not reference:
            continue
        artifacts.append(
            DeferredWorkArtifactReference(
                schema_version=str(item.get("schema_version") or "1.0"),
                kind=kind,
                reference=reference,
                checksum=str(item.get("checksum") or ""),
            )
        )
    return artifacts


def _deferred_work_item_from_row(row: tuple[object, ...]) -> DeferredWorkItem:
    status = str(row[11] or "")
    if status not in _DEFERRED_WORK_STATUSES:
        raise AppError(
            code="deferred_work_record_read_invalid",
            message="Persisted deferred work has an unsupported status",
            retryable=False,
            context={"status": status},
        )
    return DeferredWorkItem(
        schema_version=str(row[1] or "1.0"),
        work_key=str(row[0]),
        workflow=str(row[4]),
        stage=str(row[12]),
        run_id=str(row[3]),
        resource_type=str(row[7]),
        operation=str(row[8]),
        reason_code=str(row[15]),
        affected_limit=str(row[10]),
        earliest_run_at_utc=str(row[16]),
        deadline_at_utc=str(row[17]),
        attempt_count=max(0, int(str(row[18] or 0))),
        max_attempts=max(1, int(str(row[19] or 1))),
        deferred_at_utc=str(row[2]),
        updated_at_utc=str(row[25]),
        report_id=str(row[6]),
        source_id=str(row[13]),
        publisher_id=str(row[5]),
        plan_hash=str(row[14]),
        reusable_artifacts=_deferred_artifacts_from_json(row[20]),
        idempotency_key=str(row[9]),
        status=cast(DeferredWorkStatus, status),
        lease_owner=str(row[21]),
        lease_expires_at_utc=str(row[22]),
        terminal_status=str(row[23]),
        remediation_id=str(row[24]),
        completed_at_utc=str(row[26]),
        defer_count=max(1, int(str(row[27] or 1))),
        budget_request_json=str(row[28] or "{}"),
    )


def _deferred_work_path(usage_db_path: str, ctx: RunContext) -> Path:
    raw_path = str(usage_db_path or "").strip()
    if not raw_path:
        raise AppError(
            code="deferred_work_usage_db_missing",
            message="Deferred-work operations require a canonical usage ledger path",
            retryable=False,
        )
    path = Path(raw_path)
    _apply_budget_authority_migrations(path, ctx)
    return path


def list_deferred_work(
    request: DeferredWorkListRequest,
    ctx: RunContext,
) -> DeferredWorkListResponse:
    """List durable budget-deferred work without leasing or modifying it."""

    path = _deferred_work_path(request.usage_db_path, ctx)
    statuses = [
        str(value)
        for value in request.statuses
        if str(value) in _DEFERRED_WORK_STATUSES
    ]
    clauses: list[str] = []
    params: list[object] = []
    if statuses:
        clauses.append("status IN (" + ",".join("?" for _ in statuses) + ")")
        params.extend(statuses)
    if request.workflow.strip():
        clauses.append("workflow_id=?")
        params.append(request.workflow.strip())
    query = _DEFERRED_WORK_SELECT
    if clauses:
        query += " WHERE " + " AND ".join(clauses)
    query += " ORDER BY deferred_at_utc ASC, work_key ASC LIMIT ?"
    params.append(max(1, min(500, int(request.limit))))
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            rows = conn.execute(query, tuple(params)).fetchall()
    except sqlite3.Error as exc:
        raise AppError(
            code="deferred_work_list_failed",
            message="Could not list durable deferred work",
            cause=exc,
            retryable=False,
            context={"db_path": str(path)},
        ) from exc
    response = DeferredWorkListResponse(
        schema_version="1.0",
        records=[_deferred_work_item_from_row(row) for row in rows],
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="deferred_work_listed",
            module=logger.name,
            fields={
                "record_count": len(response.records),
                "workflow": request.workflow,
            },
        )
    )
    return response


def _deferred_work_lease_expiry(now_utc: str, lease_seconds: int) -> str:
    now = _parse_deferred_work_time(now_utc, field_name="now_utc")
    return (now + timedelta(seconds=max(1, min(3600, int(lease_seconds))))).isoformat()


def claim_next_deferred_work(
    request: DeferredWorkClaimRequest,
    ctx: RunContext,
) -> DeferredWorkClaimResponse:
    """Atomically lease exactly one due item; concurrent claimers cannot overlap."""

    if not request.worker_id.strip():
        raise AppError(
            code="deferred_work_worker_id_missing",
            message="Deferred-work leasing requires a stable worker ID",
            retryable=False,
        )
    path = _deferred_work_path(request.usage_db_path, ctx)
    now_utc = _normalized_deferred_work_time(request.now_utc, field_name="now_utc")
    expiry = _deferred_work_lease_expiry(now_utc, request.lease_seconds)
    record: DeferredWorkItem | None = None
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                _DEFERRED_WORK_SELECT
                + """
                WHERE status='pending'
                  AND earliest_run_at_utc<=?
                  AND (lease_expires_at_utc='' OR lease_expires_at_utc<=?)
                ORDER BY earliest_run_at_utc ASC, deferred_at_utc ASC, work_key ASC
                LIMIT 1
                """,
                (now_utc, now_utc),
            ).fetchone()
            if row is not None:
                candidate = _deferred_work_item_from_row(row)
                updated = conn.execute(
                    """
                    UPDATE budget_authority_deferred_work
                    SET status='leased', lease_owner=?, lease_expires_at_utc=?,
                        attempt_count=attempt_count+1, updated_at_utc=?
                    WHERE work_key=? AND status='pending'
                      AND (lease_expires_at_utc='' OR lease_expires_at_utc<=?)
                    """,
                    (request.worker_id, expiry, now_utc, candidate.work_key, now_utc),
                )
                if updated.rowcount == 1:
                    record = replace(
                        candidate,
                        status="leased",
                        lease_owner=request.worker_id,
                        lease_expires_at_utc=expiry,
                        attempt_count=candidate.attempt_count + 1,
                        updated_at_utc=now_utc,
                    )
            conn.commit()
    except sqlite3.Error as exc:
        raise AppError(
            code="deferred_work_claim_failed",
            message="Could not atomically lease durable deferred work",
            cause=exc,
            retryable=True,
            context={"db_path": str(path)},
        ) from exc
    if record is not None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="deferred_work_lease_acquired",
                module=logger.name,
                fields={
                    "work_key": record.work_key,
                    "workflow": record.workflow,
                    "worker_id": request.worker_id,
                    "attempt_count": record.attempt_count,
                    "lease_expires_at_utc": record.lease_expires_at_utc,
                },
            )
        )
    return DeferredWorkClaimResponse(schema_version="1.0", record=record)


def transition_deferred_work(
    request: DeferredWorkTransitionRequest,
    ctx: RunContext,
) -> DeferredWorkTransitionResponse:
    """Finish, reschedule, or hand off only the caller's current lease."""

    if request.status not in _DEFERRED_WORK_STATUSES:
        raise AppError(
            code="deferred_work_transition_invalid",
            message="Deferred-work transition uses an unsupported status",
            retryable=False,
            context={"status": request.status},
        )
    path = _deferred_work_path(request.usage_db_path, ctx)
    now_utc = _normalized_deferred_work_time(request.now_utc, field_name="now_utc")
    keep_lease = request.status == "leased"
    artifacts_json = (
        json.dumps(
            [asdict(item) for item in request.reusable_artifacts], sort_keys=True
        )
        if request.reusable_artifacts is not None
        else None
    )
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            row = conn.execute(
                _DEFERRED_WORK_SELECT + " WHERE work_key=?", (request.work_key,)
            ).fetchone()
            if row is None:
                raise AppError(
                    code="deferred_work_not_found",
                    message="Deferred-work item was not found",
                    retryable=False,
                    context={"work_key": request.work_key},
                )
            current = _deferred_work_item_from_row(row)
            if current.status != "leased" or current.lease_owner != request.worker_id:
                raise AppError(
                    code="deferred_work_lease_not_owned",
                    message="Deferred-work transition requires the current lease owner",
                    retryable=False,
                    context={"work_key": request.work_key, "status": current.status},
                )
            values = {
                "status": request.status,
                "earliest": request.earliest_run_at_utc or current.earliest_run_at_utc,
                "terminal": request.terminal_status or current.terminal_status,
                "remediation": request.remediation_id or current.remediation_id,
                "plan_hash": request.plan_hash or current.plan_hash,
                "artifacts": artifacts_json
                if artifacts_json is not None
                else json.dumps(
                    [asdict(item) for item in current.reusable_artifacts],
                    sort_keys=True,
                ),
                "owner": current.lease_owner if keep_lease else "",
                "expiry": current.lease_expires_at_utc if keep_lease else "",
                "completed": now_utc
                if request.status == "completed"
                else current.completed_at_utc,
            }
            updated = conn.execute(
                """
                UPDATE budget_authority_deferred_work
                SET status=?, earliest_run_at_utc=?, terminal_status=?, remediation_id=?,
                    plan_hash=?, reusable_artifacts_json=?, lease_owner=?,
                    lease_expires_at_utc=?, completed_at_utc=?, updated_at_utc=?,
                    defer_count=defer_count+?
                WHERE work_key=? AND status='leased' AND lease_owner=?
                """,
                (
                    values["status"],
                    values["earliest"],
                    values["terminal"],
                    values["remediation"],
                    values["plan_hash"],
                    values["artifacts"],
                    values["owner"],
                    values["expiry"],
                    values["completed"],
                    now_utc,
                    1 if request.increment_defer_count else 0,
                    request.work_key,
                    request.worker_id,
                ),
            )
            if updated.rowcount != 1:
                raise AppError(
                    code="deferred_work_lease_lost",
                    message="Deferred-work lease changed before its transition completed",
                    retryable=False,
                    context={"work_key": request.work_key},
                )
            conn.commit()
    except sqlite3.Error as exc:
        raise AppError(
            code="deferred_work_transition_failed",
            message="Could not persist deferred-work transition",
            cause=exc,
            retryable=True,
            context={"db_path": str(path), "work_key": request.work_key},
        ) from exc
    record = replace(
        current,
        status=request.status,
        earliest_run_at_utc=str(values["earliest"]),
        terminal_status=str(values["terminal"]),
        remediation_id=str(values["remediation"]),
        plan_hash=str(values["plan_hash"]),
        reusable_artifacts=(
            request.reusable_artifacts
            if request.reusable_artifacts is not None
            else current.reusable_artifacts
        ),
        lease_owner=str(values["owner"]),
        lease_expires_at_utc=str(values["expiry"]),
        completed_at_utc=str(values["completed"]),
        updated_at_utc=now_utc,
        defer_count=current.defer_count + (1 if request.increment_defer_count else 0),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="deferred_work_transition",
            module=logger.name,
            fields={
                "work_key": record.work_key,
                "workflow": record.workflow,
                "status": record.status,
                "reason": request.reason,
                "attempt_count": record.attempt_count,
                "terminal_status": record.terminal_status,
            },
        )
    )
    return DeferredWorkTransitionResponse(schema_version="1.0", record=record)


def release_expired_deferred_work_leases(
    request: DeferredWorkLeaseReleaseRequest,
    ctx: RunContext,
) -> DeferredWorkLeaseReleaseResponse:
    path = _deferred_work_path(request.usage_db_path, ctx)
    now_utc = _normalized_deferred_work_time(request.now_utc, field_name="now_utc")
    released: list[str] = []
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            conn.execute("BEGIN IMMEDIATE")
            rows = conn.execute(
                """
                SELECT work_key FROM budget_authority_deferred_work
                WHERE status='leased' AND lease_expires_at_utc<>''
                  AND lease_expires_at_utc<=?
                ORDER BY work_key ASC
                """,
                (now_utc,),
            ).fetchall()
            released = [str(row[0]) for row in rows]
            if released:
                conn.execute(
                    """
                    UPDATE budget_authority_deferred_work
                    SET status='pending', lease_owner='', lease_expires_at_utc='',
                        updated_at_utc=?
                    WHERE status='leased' AND lease_expires_at_utc<>''
                      AND lease_expires_at_utc<=?
                    """,
                    (now_utc, now_utc),
                )
            conn.commit()
    except sqlite3.Error as exc:
        raise AppError(
            code="deferred_work_lease_release_failed",
            message="Could not release expired deferred-work leases",
            cause=exc,
            retryable=True,
            context={"db_path": str(path)},
        ) from exc
    for work_key in released:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="deferred_work_lease_expired",
                module=logger.name,
                fields={"work_key": work_key},
            )
        )
    return DeferredWorkLeaseReleaseResponse(
        schema_version="1.0", released_work_keys=released
    )


def deferred_work_metrics(
    request: DeferredWorkMetricsRequest,
    ctx: RunContext,
) -> DeferredWorkMetrics:
    """Read bounded queue health metrics without leasing or executing work."""

    path = _deferred_work_path(request.usage_db_path, ctx)
    now = _parse_deferred_work_time(request.now_utc, field_name="now_utc")
    now_utc = now.isoformat()
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            counts = conn.execute(
                """
                SELECT
                    SUM(CASE WHEN status IN ('pending','leased') THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status='pending' AND earliest_run_at_utc<=?
                              AND (deadline_at_utc='' OR deadline_at_utc>?) THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status='leased' AND lease_expires_at_utc>? THEN 1 ELSE 0 END),
                    SUM(CASE WHEN defer_count>1 THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status IN ('remediation','terminal') THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status='completed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN status IN ('completed','remediation','terminal') THEN 1 ELSE 0 END)
                FROM budget_authority_deferred_work
                """,
                (now_utc, now_utc, now_utc),
            ).fetchone()
            oldest = conn.execute(
                """
                SELECT deferred_at_utc FROM budget_authority_deferred_work
                WHERE status IN ('pending','leased')
                ORDER BY deferred_at_utc ASC LIMIT 1
                """
            ).fetchone()
    except sqlite3.Error as exc:
        raise AppError(
            code="deferred_work_metrics_failed",
            message="Could not read deferred-work metrics",
            cause=exc,
            retryable=False,
            context={"db_path": str(path)},
        ) from exc
    oldest_age = 0
    if oldest and str(oldest[0] or ""):
        oldest_age = max(
            0,
            int(
                (
                    now
                    - _parse_deferred_work_time(
                        str(oldest[0]), field_name="deferred_at_utc"
                    )
                ).total_seconds()
            ),
        )
    completed = int(counts[5] or 0)
    terminal_decisions = int(counts[6] or 0)
    response = DeferredWorkMetrics(
        schema_version="1.0",
        queue_depth=int(counts[0] or 0),
        oldest_age_seconds=oldest_age,
        due_count=int(counts[1] or 0),
        lease_count=int(counts[2] or 0),
        completion_rate=(completed / terminal_decisions if terminal_decisions else 0.0),
        repeated_deferral_count=int(counts[3] or 0),
        terminal_count=int(counts[4] or 0),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="deferred_work_metrics_read",
            module=logger.name,
            fields={
                "queue_depth": response.queue_depth,
                "due_count": response.due_count,
                "lease_count": response.lease_count,
                "terminal_count": response.terminal_count,
            },
        )
    )
    return response


def _budget_request_from_deferred_work(item: DeferredWorkItem) -> BudgetRequest:
    try:
        payload = json.loads(item.budget_request_json)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="deferred_work_budget_request_invalid",
            message="Deferred work cannot be re-evaluated because its request is invalid",
            cause=exc,
            retryable=False,
            context={"work_key": item.work_key},
        ) from exc
    if not isinstance(payload, dict) or not isinstance(payload.get("budget"), dict):
        raise AppError(
            code="deferred_work_budget_request_invalid",
            message="Deferred work is missing its canonical budget request",
            retryable=False,
            context={"work_key": item.work_key},
        )
    budget_payload = dict(payload["budget"])
    for name in ("run_limits", "day_limits", "publisher_limits"):
        if isinstance(budget_payload.get(name), dict):
            budget_payload[name] = RunBudgetLimits(**budget_payload[name])
    if isinstance(budget_payload.get("enabled_effect_kinds"), list):
        budget_payload["enabled_effect_kinds"] = tuple(
            budget_payload["enabled_effect_kinds"]
        )
    payload["budget"] = RunBudget(**budget_payload)
    override = payload.get("requested_override")
    if isinstance(override, dict):
        payload["requested_override"] = BudgetOverrideContext(**override)
    if isinstance(payload.get("reusable_artifact_references"), list):
        payload["reusable_artifact_references"] = tuple(
            tuple(str(value or "") for value in entry)
            for entry in payload["reusable_artifact_references"]
            if isinstance(entry, list) and len(entry) == 3
        )
    try:
        request = BudgetRequest(**payload)
    except TypeError as exc:
        raise AppError(
            code="deferred_work_budget_request_invalid",
            message="Deferred work has an incompatible canonical budget request",
            cause=exc,
            retryable=False,
            context={"work_key": item.work_key},
        ) from exc
    return replace(
        request,
        attempt_number=item.attempt_count,
        idempotency_key=item.idempotency_key or request.idempotency_key,
        reserve_in_flight=False,
    )


def recheck_deferred_work_budget(
    item: DeferredWorkItem, ctx: RunContext
) -> BudgetDecision:
    """Re-evaluate a leased item without reserving capacity or starting work."""

    return evaluate_budget_request(_budget_request_from_deferred_work(item), ctx)


def finalize_budget_side_effect(
    request: BudgetSideEffectFinalizeRequest, ctx: RunContext
) -> BudgetSideEffectFinalizeResponse:
    """Atomically replace an in-flight side-effect forecast with measured usage.

    The reservation and actual row share an idempotency key.  This gives SQLite
    transactions enough authority to prevent a concurrent run from spending the
    released capacity twice, without adding a lock service or queue.  Provider
    monetary actuals are finalized through :func:`reconcile_budget_reservation`
    after their existing ``llm_usage_events`` write and are never duplicated here.
    """
    valid_outcomes = {"completed", "failed", "cancelled"}
    actual = request.actual_usage
    fields = (
        "spend_usd",
        "tokens",
        "calls",
        "steps",
        "runtime_seconds",
        "retries",
        "browser_launches",
        "drive_reads",
        "drive_writes",
        "wordpress_writes",
        "pdfs",
        "mailbox_reads",
    )
    invalid_measurements = [
        field for field in fields if float(getattr(actual, field)) < 0
    ]
    if (
        request.schema_version != "1.0"
        or not str(request.usage_db_path or "").strip()
        or not str(request.reservation_key or "").strip()
        or actual.schema_version != "1.0"
        or request.outcome not in valid_outcomes
        or invalid_measurements
    ):
        raise AppError(
            code="budget_side_effect_finalize_request_invalid",
            message="Budget side-effect finalization requires non-negative measured usage",
            retryable=False,
            context={
                "invalid_measurements": invalid_measurements,
                "request_schema_valid": request.schema_version == "1.0",
                "usage_db_path_present": bool(str(request.usage_db_path or "").strip()),
                "reservation_key_present": bool(
                    str(request.reservation_key or "").strip()
                ),
                "usage_schema_valid": actual.schema_version == "1.0",
                "outcome_valid": request.outcome in valid_outcomes,
            },
        )
    if float(actual.spend_usd) != 0.0:
        raise AppError(
            code="budget_side_effect_actual_cost_duplicate_forbidden",
            message="Non-provider side-effect finalization must not record monetary cost",
            retryable=False,
        )
    path = Path(request.usage_db_path)
    _apply_budget_authority_migrations(path, ctx)
    now_utc = datetime.now(timezone.utc).isoformat()
    row: tuple[object, ...] | None = None
    actual_recorded = False
    reservation_released = False
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            conn.execute("begin immediate")
            row = conn.execute(
                """
                select run_id, workflow_id, publisher_name, report_id, resource_type,
                       task_id, span_id, operation, day_utc, status
                from budget_authority_reservations where reservation_key = ?
                """,
                (request.reservation_key,),
            ).fetchone()
            if row is None:
                existing = conn.execute(
                    "select 1 from budget_authority_actuals where reservation_key = ?",
                    (request.reservation_key,),
                ).fetchone()
                conn.commit()
                return BudgetSideEffectFinalizeResponse(
                    schema_version="1.0",
                    finalized=existing is not None,
                    actual_recorded=False,
                    reservation_released=False,
                )
            cursor = conn.execute(
                """
                insert into budget_authority_actuals(
                    reservation_key, schema_version, finalized_at_utc, run_id,
                    task_id, span_id, workflow_id, publisher_name, report_id,
                    resource_type, operation,
                    day_utc, outcome, error_code, actual_tokens, actual_calls,
                    actual_steps, actual_duration_seconds, actual_retries,
                    actual_browser_launches, actual_drive_writes, actual_drive_reads,
                    actual_wordpress_writes, actual_pdfs, actual_mailbox_reads
                ) values (?, '1.0', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(reservation_key) do nothing
                """,
                (
                    request.reservation_key,
                    now_utc,
                    str(row[0]),
                    str(row[5]),
                    str(row[6]),
                    str(row[1]),
                    str(row[2]),
                    str(row[3]),
                    str(row[4]),
                    str(row[7]),
                    str(row[8]),
                    request.outcome,
                    request.error_code,
                    int(actual.tokens),
                    int(actual.calls),
                    int(actual.steps),
                    int(actual.runtime_seconds),
                    int(actual.retries),
                    int(actual.browser_launches),
                    int(actual.drive_writes),
                    int(actual.drive_reads),
                    int(actual.wordpress_writes),
                    int(actual.pdfs),
                    int(actual.mailbox_reads),
                ),
            )
            actual_recorded = cursor.rowcount == 1
            reservation_released = (
                conn.execute(
                    """
                    update budget_authority_reservations
                    set status = 'reconciled', released_at_utc = ?, reconciled_at_utc = ?
                    where reservation_key = ? and status = 'reserved'
                    """,
                    (now_utc, now_utc, request.reservation_key),
                ).rowcount
                == 1
            )
            conn.commit()
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise AppError(
            code="budget_side_effect_finalize_failed",
            message="Canonical budget side-effect finalization failed",
            cause=exc,
            retryable=False,
            context={"db_path": str(path), "reservation_key": request.reservation_key},
        ) from exc
    response = BudgetSideEffectFinalizeResponse(
        schema_version="1.0",
        finalized=True,
        actual_recorded=actual_recorded,
        reservation_released=reservation_released,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="side_effect_actual_reconciled",
            module=logger.name,
            fields={
                "reservation_key": request.reservation_key,
                "resource_type": str(row[4]) if row is not None else "",
                "operation": str(row[5]) if row is not None else "",
                "outcome": request.outcome,
                "error_code": request.error_code,
                "actual_recorded": response.actual_recorded,
                "reservation_released": response.reservation_released,
                **_usage_log_fields("actual", actual),
            },
        )
    )
    return response


def reconcile_budget_reservation(
    request: BudgetReservationReconcileRequest, ctx: RunContext
) -> BudgetReservationReconcileResponse:
    """Release one budget forecast after durable canonical usage is appended."""
    if (
        request.schema_version != "1.0"
        or not request.usage_db_path
        or not request.reservation_key
    ):
        raise AppError(
            code="budget_reservation_reconcile_request_invalid",
            message="Reservation reconciliation requires a usage database and key",
            retryable=False,
        )
    path = Path(request.usage_db_path)
    _apply_budget_authority_migrations(path, ctx)
    now_utc = datetime.now(timezone.utc).isoformat()
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            conn.execute("begin immediate")
            row = conn.execute(
                "select estimated_cost_usd, run_id, workflow_id, publisher_name, report_id, resource_type, operation from budget_authority_reservations where reservation_key = ? and status = 'reserved'",
                (request.reservation_key,),
            ).fetchone()
            released = False
            forecast = 0.0
            if row is not None:
                forecast = float(row[0] or 0.0)
                released = (
                    conn.execute(
                        "update budget_authority_reservations set status = 'released', released_at_utc = ?, reconciled_at_utc = ? where reservation_key = ? and status = 'reserved'",
                        (
                            now_utc,
                            now_utc,
                            request.reservation_key,
                        ),
                    ).rowcount
                    == 1
                )
            conn.commit()
    except (sqlite3.Error, OSError, ValueError) as exc:
        raise AppError(
            code="budget_reservation_reconcile_failed",
            message="Canonical budget reservation could not be reconciled",
            cause=exc,
            retryable=False,
            context={"db_path": str(path)},
        ) from exc
    response = BudgetReservationReconcileResponse(
        schema_version="1.0",
        released=released,
        forecast_cost_usd=forecast,
        actual_cost_usd=float(request.actual_cost_usd),
        forecast_error_usd=round(float(request.actual_cost_usd) - forecast, 6),
    )
    fields = {
        "run_id": ctx.run_id,
        "workflow_id": ctx.task_id,
        "resource_type": str(row[5]) if row is not None else "",
        "operation": str(row[6]) if row is not None else "",
        "decision": "allow",
        "policy_version": "budget-authority-v2",
        "reservation_key": request.reservation_key,
        "released": response.released,
        "actual_cost_usd": response.actual_cost_usd,
        "forecast_cost_usd": response.forecast_cost_usd,
        "forecast_error_usd": response.forecast_error_usd,
    }
    logger.info(
        log_event(
            ctx,
            role="service",
            event="reservation_released",
            module=logger.name,
            fields=fields,
        )
    )
    if released:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="actual_usage_reconciled",
                module=logger.name,
                fields=fields,
            )
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="forecast_error",
                module=logger.name,
                fields=fields,
            )
        )
    return response


def read_budget_authority_report(
    *, usage_db_path: str, run_id: str = "", ctx: RunContext
) -> BudgetAuthorityReport:
    """Read budget-policy evidence without creating a second cost ledger."""
    path = Path(usage_db_path)
    _apply_budget_authority_migrations(path, ctx)
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            where = "where run_id = ?" if run_id else ""
            params: tuple[object, ...] = (run_id,) if run_id else ()
            rows = conn.execute(
                f"select decision, details_json from budget_authority_events {where}",
                params,
            ).fetchall()
            reservation_where = "where run_id = ?" if run_id else ""
            reservations = conn.execute(
                f"select status from budget_authority_reservations {reservation_where}",
                params,
            ).fetchall()
            actual = float(
                conn.execute(
                    f"select coalesce(sum(estimated_cost_usd), 0.0) from llm_usage_events {where}",
                    params,
                ).fetchone()[0]
                or 0.0
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="budget_authority_report_read_failed",
            message="Canonical budget policy evidence could not be read",
            cause=exc,
            retryable=False,
            context={"db_path": str(path)},
        ) from exc
    allowed = deferred = overrides = avoided_calls = orphaned = 0
    forecast = avoided_cost = 0.0
    for raw_decision, raw_details in rows:
        decision = str(raw_decision or "")
        try:
            details = json.loads(str(raw_details or "{}"))
        except json.JSONDecodeError:
            details = {}
        cost = float(details.get("forecast_cost_usd") or 0.0)
        calls = int(details.get("forecast_calls") or 0)
        forecast += cost
        if decision in {"allow", "warn", "authorized_override"}:
            allowed += 1
        if decision in {"defer", "pause", "stop"}:
            deferred += 1
            avoided_calls += calls
            avoided_cost += cost
        if decision == "authorized_override":
            overrides += 1
    for (status,) in reservations:
        if str(status) == "expired":
            orphaned += 1
    return BudgetAuthorityReport(
        schema_version="1.0",
        allowed_operations=allowed,
        deferred_or_stopped_operations=deferred,
        forecast_cost_usd=round(forecast, 6),
        actual_cost_usd=round(actual, 6),
        avoided_calls=avoided_calls,
        avoided_estimated_cost_usd=round(avoided_cost, 6),
        orphaned_reservation_recoveries=orphaned,
        overrides=overrides,
    )


def append_run_budget_side_effect(
    request: RunBudgetEventAppendRequest, ctx: RunContext
) -> RunBudgetEventAppendResponse:
    """Persist a completed external side effect in the canonical LLM ledger."""
    if request.schema_version != "1.0":
        raise AppError(
            code="run_budget_event_schema_version_invalid",
            message="Run-budget event schema version is unsupported",
            retryable=False,
        )
    _validate_run_budget(request.budget)
    if request.metric not in _RUN_BUDGET_EVENT_METRICS:
        raise AppError(
            code="run_budget_event_metric_invalid",
            message="Run-budget event metric is unsupported",
            retryable=False,
            context={"metric": request.metric},
        )
    if not str(request.event_key or "").strip() or int(request.quantity) <= 0:
        raise AppError(
            code="run_budget_event_invalid",
            message="Run-budget event requires an idempotency key and positive quantity",
            retryable=False,
        )
    if bool(str(request.override_actor or "").strip()) != bool(
        str(request.override_reason or "").strip()
    ):
        raise AppError(
            code="run_budget_override_audit_missing",
            message="Budget overrides require both actor and reason",
            retryable=False,
        )
    budget = request.budget
    day_utc = _budget_day_utc(budget)
    path = Path(budget.usage_db_path)
    _apply_budget_authority_migrations(path, ctx)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="run_budget_side_effect_append_start",
            module=logger.name,
            fields={
                "event_key": request.event_key,
                "metric": request.metric,
                "quantity": request.quantity,
                "run_id": budget.run_id,
                "day_utc": day_utc,
                "publisher_name": budget.publisher_name,
                "decision": request.decision,
                "override_actor": request.override_actor,
            },
        )
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, sqlite3.connect(path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute(
                """
                insert into run_budget_side_effect_events (
                    event_key, schema_version, timestamp_utc, run_id, task_id, span_id,
                    publisher_name,
                    day_utc, metric, quantity, decision, override_actor, override_reason
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(event_key) do nothing
                """,
                (
                    request.event_key,
                    "1.0",
                    datetime.now(timezone.utc).isoformat(),
                    budget.run_id,
                    ctx.task_id,
                    ctx.span_id,
                    budget.publisher_name,
                    day_utc,
                    request.metric,
                    int(request.quantity),
                    request.decision,
                    request.override_actor,
                    request.override_reason,
                ),
            )
            inserted = cursor.rowcount == 1
    except sqlite3.Error as exc:
        raise AppError(
            code="run_budget_event_append_failed",
            message=f"Could not persist canonical budget event to {path}",
            cause=exc,
            retryable=False,
            context={"db_path": str(path), "event_key": request.event_key},
        ) from exc
    response = RunBudgetEventAppendResponse(
        schema_version="1.0", event_key=request.event_key, inserted=inserted
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="run_budget_side_effect_append_complete",
            module=logger.name,
            fields={
                "event_key": response.event_key,
                "inserted": response.inserted,
                "metric": request.metric,
                "run_id": budget.run_id,
            },
        )
    )
    return response


def _event_key(entry: LLMUsageLedgerEntry) -> str:
    """Stable replay key; request IDs are deliberately excluded because providers may omit or reuse them."""
    payload = {
        "provider": entry.provider,
        "action": entry.action,
        "run_id": str(entry.run_id),
        "task_id": str(entry.task_id),
        "span_id": entry.span_id,
        "trace_id": entry.trace_id,
        "model": entry.model,
        "source_url": entry.source_url,
        "prompt_namespace": entry.prompt_namespace,
        "prompt_hash": entry.prompt_hash,
        "call_ordinal": int(entry.call_ordinal or 0),
        "ledger_scope": str((entry.metadata or {}).get("cost_ledger_path") or ""),
    }
    return sha256(
        json.dumps(
            payload, ensure_ascii=True, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()


def _call_identity(entry: LLMUsageLedgerEntry) -> tuple[str, ...]:
    """Fields that make an ordinal sequence local to one logical provider-call stream."""
    return (
        entry.provider,
        entry.action,
        str(entry.run_id),
        str(entry.task_id),
        entry.span_id,
        entry.trace_id,
        entry.model,
        entry.source_url,
        entry.prompt_namespace,
        entry.prompt_hash,
    )


def _resolve_call_ordinal(conn: sqlite3.Connection, entry: LLMUsageLedgerEntry) -> int:
    """Return an atomic, replay-stable ordinal without merging separate direct calls.

    A caller that already has a resolved ordinal owns replay identity. Otherwise a
    provider request ID reuses its existing ordinal (the normal accounting retry
    path); an absent request ID deliberately receives the next ordinal so two
    otherwise identical direct calls remain distinct.
    """
    if entry.call_ordinal is not None:
        return int(entry.call_ordinal)

    identity = _call_identity(entry)
    where_clause = """
        provider = ? and action = ? and run_id = ? and task_id = ? and
        span_id = ? and trace_id = ? and model = ? and source_url = ? and
        prompt_namespace = ? and prompt_hash = ?
    """
    if entry.request_id:
        replay = conn.execute(
            f"select call_ordinal from llm_usage_events where {where_clause} and request_id = ?",
            (*identity, entry.request_id),
        ).fetchone()
        if replay is not None:
            return int(replay[0])

    row = conn.execute(
        f"select coalesce(max(call_ordinal), -1) from llm_usage_events where {where_clause}",
        identity,
    ).fetchone()
    return int(row[0]) + 1 if row is not None and row[0] is not None else 0


def _validate_outcome_update(request: LLMUsageLedgerOutcomeUpdateRequest) -> None:
    if request.schema_version != "1.0":
        raise AppError(
            code="llm_usage_ledger_outcome_schema_version_invalid",
            message="LLM usage outcome update schema version is unsupported",
            retryable=False,
            context={"schema_version": request.schema_version},
        )
    if not str(request.db_path or "").strip() or not request.event_key.strip():
        raise AppError(
            code="llm_usage_ledger_outcome_identity_missing",
            message="LLM usage outcome update requires a database path and event key",
            retryable=False,
        )
    if request.parse_status not in _OUTCOME_STATUSES:
        raise AppError(
            code="llm_usage_ledger_parse_status_invalid",
            message="LLM usage parse status is unsupported",
            retryable=False,
            context={"parse_status": request.parse_status},
        )
    if request.schema_validation_status not in _OUTCOME_STATUSES:
        raise AppError(
            code="llm_usage_ledger_schema_validation_status_invalid",
            message="LLM usage schema validation status is unsupported",
            retryable=False,
            context={"schema_validation_status": request.schema_validation_status},
        )
    _validate_error_taxonomy(
        error_stage=request.error_stage,
        error_code=request.error_code,
    )


def _metadata_json(metadata: dict[str, Any]) -> str:
    try:
        return json.dumps(metadata or {}, ensure_ascii=False, sort_keys=True)
    except (TypeError, ValueError):
        return "{}"


def _median_db_path(usage_db_path: Path) -> Path:
    suffix = usage_db_path.suffix
    stem = usage_db_path.stem if suffix else usage_db_path.name
    return usage_db_path.with_name(f"{stem}_medians.sqlite")


def _ensure_median_schema(conn: sqlite3.Connection) -> None:
    existing_columns = {
        str(row[1])
        for row in conn.execute(
            "pragma llm_usage_medians.table_info(llm_usage_medians)"
        ).fetchall()
    }
    required_columns = {
        "schema_version",
        "provider",
        "task",
        "action",
        "model",
        "prompt_namespace",
        "sample_count",
        "median_input_tokens",
        "median_output_tokens",
        "median_total_tokens",
        "median_estimated_cost_usd",
        "recalculated_at_utc",
    }
    if existing_columns and not required_columns.issubset(existing_columns):
        conn.execute("drop table llm_usage_medians.llm_usage_medians")
    conn.execute(
        """
        create table if not exists llm_usage_medians.llm_usage_medians (
            schema_version text not null,
            provider text not null,
            task text not null,
            action text not null,
            model text not null,
            prompt_namespace text not null,
            sample_count integer not null,
            median_input_tokens real not null,
            median_output_tokens real not null,
            median_total_tokens real not null,
            median_estimated_cost_usd real not null,
            recalculated_at_utc text not null,
            primary key (provider, task, action, model, prompt_namespace)
        )
        """
    )


def _semantic_task(task_id: str, action: str) -> str:
    _, marker, semantic_task = task_id.rpartition(":vector_store:")
    return semantic_task if marker and semantic_task else action


def _semantic_task_event_count(conn: sqlite3.Connection, task: str) -> int:
    return semantic_task_count(conn, task)


def _run_scheduled_median_rebuild(path: Path, ctx: RunContext, path_key: str) -> None:
    reschedule = False
    try:
        rebuild_usage_medians(
            LLMUsageMedianRebuildRequest(schema_version="1.0", db_path=str(path)),
            ctx,
        )
        with _LOCK, sqlite3.connect(path) as conn:
            _ensure_schema(conn)
            dirty, snapshot = conn.execute(
                "select dirty_through_event_id, snapshot_through_event_id from llm_usage_median_state where singleton = 1"
            ).fetchone()
            reschedule = int(dirty) > int(snapshot)
    except AppError as exc:
        logger.error(
            log_event(
                ctx,
                role="service",
                event="llm_usage_ledger_median_rebuild_failed",
                module=logger.name,
                fields={"db_path": str(path), "error_code": exc.code},
            )
        )
    finally:
        with _PENDING_MEDIAN_REBUILD_LOCK:
            _PENDING_MEDIAN_REBUILD_PATHS.discard(path_key)
        if reschedule:
            _schedule_median_rebuild(path, ctx)


def _schedule_median_rebuild(path: Path, ctx: RunContext) -> bool:
    path_key = str(path.resolve())
    with _PENDING_MEDIAN_REBUILD_LOCK:
        if path_key in _PENDING_MEDIAN_REBUILD_PATHS:
            return False
        _PENDING_MEDIAN_REBUILD_PATHS.add(path_key)
    try:
        _MEDIAN_REBUILD_EXECUTOR.submit(
            _run_scheduled_median_rebuild, path, ctx, path_key
        )
    except RuntimeError:
        with _PENDING_MEDIAN_REBUILD_LOCK:
            _PENDING_MEDIAN_REBUILD_PATHS.discard(path_key)
        return False
    return True


def _rebuild_usage_medians(
    conn: sqlite3.Connection, source_db_path: Path, median_db_path: Path
) -> LLMUsageMedianRebuildResponse:
    conn.execute("attach database ? as llm_usage_medians", (str(median_db_path),))
    _ensure_median_schema(conn)
    rows = conn.execute(
        """
        select provider, semantic_task, action, model, prompt_namespace,
               input_tokens, output_tokens, total_tokens, estimated_cost_usd
        from llm_usage_events
        """
    ).fetchall()
    grouped_usage: dict[
        tuple[str, str, str, str, str], list[tuple[int, int, int, float]]
    ] = defaultdict(list)
    for row in rows:
        provider = str(row[0])
        task_id = str(row[1])
        action = str(row[2])
        key = (
            provider,
            task_id,
            action,
            str(row[3]),
            str(row[4]),
        )
        grouped_usage[key].append(
            (int(row[5]), int(row[6]), int(row[7]), float(row[8]))
        )

    recalculated_at_utc = datetime.now(timezone.utc).isoformat()
    conn.execute("delete from llm_usage_medians.llm_usage_medians")
    conn.executemany(
        """
        insert into llm_usage_medians.llm_usage_medians (
            schema_version, provider, task, action, model, prompt_namespace,
            sample_count, median_input_tokens, median_output_tokens,
            median_total_tokens, median_estimated_cost_usd, recalculated_at_utc
        ) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                "1.2",
                provider,
                task,
                action,
                model,
                prompt_namespace,
                len(usage_samples),
                float(median(sample[0] for sample in usage_samples)),
                float(median(sample[1] for sample in usage_samples)),
                float(median(sample[2] for sample in usage_samples)),
                float(median(sample[3] for sample in usage_samples)),
                recalculated_at_utc,
            )
            for (
                provider,
                task,
                action,
                model,
                prompt_namespace,
            ), usage_samples in grouped_usage.items()
        ],
    )
    snapshot_through_event_id = int(
        conn.execute("select coalesce(max(id), 0) from llm_usage_events").fetchone()[0]
    )
    conn.execute(
        """
        update llm_usage_median_state
        set snapshot_through_event_id = ?, dirty_through_event_id = case
            when dirty_through_event_id <= ? then 0 else dirty_through_event_id end,
            rebuild_in_progress = 0, updated_at_utc = ?
        where singleton = 1
        """,
        (snapshot_through_event_id, snapshot_through_event_id, recalculated_at_utc),
    )
    return LLMUsageMedianRebuildResponse(
        schema_version="1.0",
        db_path=str(source_db_path),
        median_db_path=str(median_db_path),
        median_row_count=len(grouped_usage),
    )


def _clear_failed_median_rebuild(path: Path) -> None:
    """Allow restart recovery to schedule the still-dirty durable median snapshot."""
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            _ensure_schema(conn)
            conn.execute(
                """
                update llm_usage_median_state
                set rebuild_in_progress = 0, updated_at_utc = ? where singleton = 1
                """,
                (datetime.now(timezone.utc).isoformat(),),
            )
    except (OSError, sqlite3.Error, TypeError, ValueError):
        return


def rebuild_usage_medians(
    request: LLMUsageMedianRebuildRequest, ctx: RunContext
) -> LLMUsageMedianRebuildResponse:
    _validate_median_rebuild_request(request)
    path = Path(request.db_path)
    median_path = _median_db_path(path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_ledger_median_rebuild_start",
            module=logger.name,
            fields={"db_path": str(path), "median_db_path": str(median_path)},
        )
    )
    try:
        if not path.is_file():
            raise AppError(
                code="llm_usage_median_rebuild_source_missing",
                message="LLM usage ledger database is missing",
                retryable=False,
                context={"db_path": str(path)},
            )
        with _LOCK, sqlite3.connect(path) as conn:
            _ensure_schema(conn)
            table_exists = conn.execute(
                """
                select 1 from sqlite_master
                where type = 'table' and name = 'llm_usage_events'
                """
            ).fetchone()
            if table_exists is None:
                raise AppError(
                    code="llm_usage_median_rebuild_source_missing",
                    message="LLM usage ledger table is missing",
                    retryable=False,
                    context={"db_path": str(path)},
                )
            conn.execute(
                """
                update llm_usage_median_state
                set rebuild_in_progress = 1, updated_at_utc = ? where singleton = 1
                """,
                (datetime.now(timezone.utc).isoformat(),),
            )
            rebuilt = _rebuild_usage_medians(conn, path, median_path)
    except AppError:
        _clear_failed_median_rebuild(path)
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        _clear_failed_median_rebuild(path)
        raise AppError(
            code="llm_usage_median_rebuild_failed",
            message=f"Failed to rebuild LLM usage medians from {path}",
            cause=exc,
            retryable=False,
            context={"db_path": str(path)},
        ) from exc
    response = LLMUsageMedianRebuildResponse(
        schema_version="1.0",
        db_path=str(path),
        median_db_path=rebuilt.median_db_path,
        median_row_count=rebuilt.median_row_count,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_ledger_median_rebuild_complete",
            module=logger.name,
            fields={
                "db_path": response.db_path,
                "median_db_path": response.median_db_path,
                "median_row_count": response.median_row_count,
            },
        )
    )
    return response


def append_usage(
    request: LLMUsageLedgerAppendRequest, ctx: RunContext
) -> LLMUsageLedgerAppendResponse:
    _validate_request(request)
    path = Path(request.db_path)
    median_path = _median_db_path(path)
    entry = request.entry
    event_key = ""
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_ledger_append_start",
            module=logger.name,
            fields={
                "db_path": str(path),
                "median_db_path": str(median_path),
                "provider": entry.provider,
                "action": entry.action,
                "model": entry.model,
                "publisher_name": entry.publisher_name,
                "request_id": entry.request_id or "",
                "call_ordinal": entry.call_ordinal,
                "input_tokens": entry.input_tokens,
                "output_tokens": entry.output_tokens,
                "total_tokens": entry.total_tokens,
            },
        )
    )
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with _LOCK, sqlite3.connect(path) as conn:
            _ensure_schema(conn)
            entry = replace(
                entry,
                call_ordinal=_resolve_call_ordinal(conn, entry),
            )
            event_key = _event_key(entry)
            cursor = conn.execute(
                """
                insert into llm_usage_events (
                    schema_version, timestamp_utc, provider, action,
                    run_id, task_id, span_id, trace_id, model, request_id,
                    publisher_name, report_name, source_url, input_tokens,
                    output_tokens, total_tokens, cached_input_tokens, tool_calls,
                    estimated_cost_usd, prompt_namespace, prompt_hash,
                    provider_decision, cache_decision, temperature, seed,
                    timeout_seconds, event_key, call_ordinal, provider_call_status,
                    parse_status, schema_validation_status, error_stage, error_code,
                    semantic_task, report_id, workflow, stage, plan_hash,
                    artifact_family, validation_run_id, cohort_id, workflow_run_id,
                    publisher_id, model_policy_namespace, policy_namespace,
                    configuration_hash, policy_hash,
                    producer_build_identity, repair_attempt, pricing_version,
                    pricing_status, metadata_json
                ) values (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                on conflict(event_key) do nothing
                """,
                (
                    entry.schema_version,
                    entry.timestamp_utc,
                    entry.provider,
                    entry.action,
                    str(entry.run_id),
                    str(entry.task_id),
                    entry.span_id,
                    entry.trace_id,
                    entry.model,
                    entry.request_id,
                    entry.publisher_name,
                    entry.report_name,
                    entry.source_url,
                    int(entry.input_tokens),
                    int(entry.output_tokens),
                    int(entry.total_tokens),
                    entry.cached_input_tokens,
                    int(entry.tool_calls),
                    float(entry.estimated_cost_usd),
                    entry.prompt_namespace,
                    entry.prompt_hash,
                    entry.provider_decision,
                    entry.cache_decision,
                    entry.temperature,
                    entry.seed,
                    entry.timeout_seconds,
                    event_key,
                    int(entry.call_ordinal or 0),
                    entry.provider_call_status,
                    entry.parse_status,
                    entry.schema_validation_status,
                    entry.error_stage,
                    entry.error_code,
                    entry.semantic_task
                    or _semantic_task(str(entry.task_id), entry.action),
                    entry.report_id,
                    entry.workflow,
                    entry.stage,
                    entry.plan_hash,
                    entry.artifact_family,
                    entry.validation_run_id,
                    entry.cohort_id,
                    entry.workflow_run_id,
                    entry.publisher_id,
                    entry.model_policy_namespace,
                    entry.policy_namespace,
                    entry.configuration_hash,
                    entry.policy_hash,
                    entry.producer_build_identity,
                    max(0, int(entry.repair_attempt or 0)),
                    entry.pricing_version,
                    entry.pricing_status,
                    _metadata_json(entry.metadata),
                ),
            )
            inserted = cursor.rowcount == 1
            row = conn.execute(
                "select id from llm_usage_events where event_key = ?", (event_key,)
            ).fetchone()
            row_id = int(row[0]) if row is not None else 0
            if inserted:
                conn.execute(
                    """
                    update llm_usage_median_state
                    set dirty_through_event_id = max(dirty_through_event_id, ?),
                        updated_at_utc = ?
                    where singleton = 1
                    """,
                    (row_id, datetime.now(timezone.utc).isoformat()),
                )
            median_task = _semantic_task(str(entry.task_id), entry.action)
            if inserted:
                canonical_event_count = increment_event_count(conn)
                median_task_event_count = increment_semantic_task_count(
                    conn, median_task
                )
            else:
                canonical_event_count = event_count(conn)
                median_task_event_count = _semantic_task_event_count(conn, median_task)
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise AppError(
            code="llm_usage_ledger_append_failed",
            message=f"Failed to append LLM usage record to {path}",
            cause=exc,
            retryable=False,
            context={"db_path": str(path), "provider": entry.provider},
        ) from exc
    median_rebuild_scheduled = bool(
        inserted
        and median_task_event_count % _MEDIAN_REBUILD_EVENT_INTERVAL == 0
        and _schedule_median_rebuild(path, ctx)
    )
    export_projection_due = bool(
        inserted and canonical_event_count % _USAGE_EXPORT_PROJECTION_INTERVAL == 0
    )
    if median_rebuild_scheduled:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="llm_usage_ledger_median_rebuild_scheduled",
                module=logger.name,
                fields={
                    "db_path": str(path),
                    "median_db_path": str(median_path),
                    "task": median_task,
                    "task_event_count": median_task_event_count,
                },
            )
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_ledger_append_complete",
            module=logger.name,
            fields={
                "db_path": str(path),
                "median_db_path": str(median_path),
                "median_rebuild_scheduled": median_rebuild_scheduled,
                "median_task": median_task,
                "median_task_event_count": median_task_event_count,
                "canonical_event_count": canonical_event_count,
                "export_projection_due": export_projection_due,
                "row_id": row_id,
                "event_key": event_key,
                "inserted": inserted,
                "provider": entry.provider,
                "action": entry.action,
                "model": entry.model,
            },
        )
    )
    return LLMUsageLedgerAppendResponse(
        schema_version="1.1",
        db_path=str(path),
        row_id=row_id,
        event_key=event_key,
        call_ordinal=int(entry.call_ordinal or 0),
        inserted=inserted,
        median_db_path=str(median_path),
        median_rebuild_scheduled=median_rebuild_scheduled,
        median_task=median_task,
        median_task_event_count=median_task_event_count,
        median_row_count=None,
        canonical_event_count=canonical_event_count,
        export_projection_due=export_projection_due,
    )


def update_usage_outcome(
    request: LLMUsageLedgerOutcomeUpdateRequest, ctx: RunContext
) -> LLMUsageLedgerOutcomeUpdateResponse:
    _validate_outcome_update(request)
    path = Path(request.db_path)
    projections_to_refresh: list[tuple[str, str]] = []
    try:
        with _LOCK, sqlite3.connect(path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute(
                """
                update llm_usage_events
                set parse_status = ?, schema_validation_status = ?,
                    error_stage = ?, error_code = ?
                where event_key = ?
                """,
                (
                    request.parse_status,
                    request.schema_validation_status,
                    request.error_stage,
                    request.error_code,
                    request.event_key,
                ),
            )
            updated = cursor.rowcount == 1
            if updated:
                event_row = conn.execute(
                    "select id from llm_usage_events where event_key = ?",
                    (request.event_key,),
                ).fetchone()
                if event_row is not None:
                    projections_to_refresh = _projection_checkpoint_rows(
                        conn, event_id=int(event_row[0])
                    )
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise AppError(
            code="llm_usage_ledger_outcome_update_failed",
            message=f"Failed to finalize LLM usage event in {path}",
            cause=exc,
            retryable=False,
            context={"db_path": str(path), "event_key": request.event_key},
        ) from exc
    export_refreshed = False
    for ledger_path, daily_path in projections_to_refresh:
        _reset_usage_export_checkpoint(
            db_path=str(path), ledger_path=ledger_path, daily_path=daily_path
        )
        rebuild_usage_exports(
            LLMUsageExportRebuildRequest(
                schema_version="1.0",
                db_path=str(path),
                ledger_path=ledger_path,
                daily_path=daily_path,
            ),
            ctx,
        )
        export_refreshed = True
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_ledger_outcome_updated",
            module=logger.name,
            fields={
                "db_path": str(path),
                "event_key": request.event_key,
                "updated": updated,
                "parse_status": request.parse_status,
                "schema_validation_status": request.schema_validation_status,
                "error_stage": request.error_stage,
                "error_code": request.error_code,
                "export_refreshed": export_refreshed,
            },
        )
    )
    return LLMUsageLedgerOutcomeUpdateResponse(
        schema_version="1.0",
        db_path=str(path),
        event_key=request.event_key,
        updated=updated,
        export_refreshed=export_refreshed,
    )


def _canonical_export_rows(
    conn: sqlite3.Connection, *, after_event_id: int = 0
) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        select id, timestamp_utc, run_id, task_id, span_id, action, model,
               input_tokens, output_tokens, cached_input_tokens, tool_calls,
               estimated_cost_usd, provider, request_id, publisher_name,
               report_name, source_url, prompt_namespace, prompt_hash,
               provider_decision, cache_decision, call_ordinal,
               provider_call_status, parse_status, schema_validation_status,
               error_stage, error_code, event_key, report_id, workflow, stage,
               plan_hash, artifact_family, validation_run_id, publisher_id,
               model_policy_namespace, configuration_hash, policy_hash,
               producer_build_identity, repair_attempt, pricing_version,
                pricing_status, metadata_json, cohort_id, workflow_run_id,
                policy_namespace, semantic_task
        from llm_usage_events where id > ? order by id
        """,
        (after_event_id,),
    ).fetchall()
    export_rows: list[dict[str, Any]] = []
    for row in rows:
        metadata = _safe_metadata(str(row[42]))
        export_rows.append(
            {
                "schema_version": "1.0",
                "timestamp_utc": str(row[1]),
                "run_id": str(row[2]),
                "task_id": str(row[3]),
                "span_id": str(row[4]),
                "step_name": str(row[5]),
                "model": str(row[6]),
                "input_tokens": int(row[7]),
                "output_tokens": int(row[8]),
                "cached_input_tokens": row[9],
                "tool_calls": int(row[10]),
                "estimated_cost_usd": float(row[11]),
                "extra": {
                    "canonical_event_id": int(row[0]),
                    "event_key": str(row[27]),
                    "request_id": row[13],
                    "provider": str(row[12]),
                    "action": str(row[5]),
                    "publisher_name": str(row[14]),
                    "report_name": str(row[15]),
                    "source_url": str(row[16]),
                    "prompt_namespace": str(row[17]),
                    "prompt_hash": str(row[18]),
                    "provider_decision": str(row[19]),
                    "cache_decision": str(row[20]),
                    "event_outcome": {
                        "call_ordinal": int(row[21]),
                        "provider_call_status": str(row[22]),
                        "parse_status": str(row[23]),
                        "schema_validation_status": str(row[24]),
                        "error_stage": str(row[25]) or None,
                        "error_code": str(row[26]) or None,
                    },
                    "usage_context": {
                        "report_id": str(row[28]) or "unknown",
                        "workflow": str(row[29]) or "unknown",
                        "stage": str(row[30]) or "unknown",
                        "plan_hash": str(row[31]) or "unknown",
                        "artifact_family": str(row[32]) or "unknown",
                        "validation_run_id": str(row[33]) or "unknown",
                        "publisher_id": str(row[34]) or "unknown",
                        "model_policy_namespace": str(row[35]) or "unknown",
                        "configuration_hash": str(row[36]) or "unknown",
                        "policy_hash": str(row[37]) or "unknown",
                        "producer_build_identity": str(row[38]) or "unknown",
                        "repair_attempt": int(row[39] or 0),
                        "semantic_task": str(row[46])
                        or _semantic_task(str(row[3]), str(row[5])),
                        "pricing_version": str(row[40]) or "unknown",
                        "pricing_status": str(row[41]) or "unknown",
                        "prompt_namespace": str(row[17]) or "unknown",
                        "publisher_name": str(row[14]) or "unknown",
                        "cohort_id": str(row[43]) or "unknown",
                        "workflow_run_id": str(row[44]) or "unknown",
                        "policy_namespace": str(row[45]) or "unknown",
                    },
                    "metadata": metadata,
                },
            }
        )
    return export_rows


def _safe_metadata(raw_metadata: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _stable_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        + "\n"
    ).encode("utf-8")


def _projection_segment_path(ledger_path: Path, generation_id: int) -> Path:
    """Immutable generation segment retained beside the compatibility JSONL file."""
    return (
        ledger_path.parent
        / f"{ledger_path.stem}.segments"
        / f"{generation_id:020d}.jsonl"
    )


def _projection_files_valid(
    checkpoint: sqlite3.Row | tuple[Any, ...] | None,
    ledger_path: Path,
    daily_path: Path,
) -> bool:
    """Verify both derived artifacts before using an incremental checkpoint."""
    if checkpoint is None or not ledger_path.is_file() or not daily_path.is_file():
        return False
    try:
        daily_content = daily_path.read_bytes()
        daily_payload = json.loads(daily_content.decode("utf-8"))
        state = dict(daily_payload.get("ledger_state") or {})
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
        return False
    # checkpoint tuple order is stable at all call sites below.
    event_count, source_sha256, ledger_sha256, daily_sha256, last_event_id = checkpoint[
        :5
    ]
    generation_id = checkpoint[5] if len(checkpoint) > 5 else None
    if generation_id is None:
        return False
    return (
        sha256(daily_content).hexdigest() == str(daily_sha256)
        and str(state.get("ledger_sha256") or "") == str(ledger_sha256)
        and str(state.get("source_sha256") or "") == str(source_sha256)
        and int(state.get("event_count") or -1) == int(event_count)
        and int(state.get("last_projected_event_id") or -1) == int(last_event_id)
        and int(state.get("generation_id") or -1) == int(generation_id or -1)
        and _projection_segment_path(ledger_path, int(generation_id)).is_file()
        and sha256(
            _projection_segment_path(ledger_path, int(generation_id)).read_bytes()
        ).hexdigest()
        == str(state.get("last_segment_sha256") or "")
    )


def _projection_checkpoint_rows(
    conn: sqlite3.Connection, *, event_id: int
) -> list[tuple[str, str]]:
    return [
        (str(row[0]), str(row[1]))
        for row in conn.execute(
            """
            select ledger_path, daily_path
            from llm_usage_export_checkpoints
            where last_projected_event_id >= ?
            """,
            (event_id,),
        ).fetchall()
    ]


def _acquire_projection_lease(
    conn: sqlite3.Connection,
    *,
    ledger_path: Path,
    daily_path: Path,
    holder_id: str,
    generation_id: int,
) -> None:
    now = datetime.now(timezone.utc)
    key = (str(ledger_path.resolve()), str(daily_path.resolve()))
    current = conn.execute(
        """
        select holder_id, expires_at_utc from llm_usage_projection_leases
        where ledger_path = ? and daily_path = ?
        """,
        key,
    ).fetchone()
    if (
        current is not None
        and str(current[1]) > now.isoformat()
        and str(current[0]) != holder_id
    ):
        raise AppError(
            code="llm_usage_projection_busy",
            message="Another process is materializing this usage projection",
            retryable=True,
            context={"ledger_path": key[0], "daily_path": key[1]},
        )
    conn.execute(
        """
        insert into llm_usage_projection_leases (
            ledger_path, daily_path, holder_id, expires_at_utc, generation_id
        ) values (?, ?, ?, ?, ?)
        on conflict(ledger_path, daily_path) do update set
            holder_id = excluded.holder_id,
            expires_at_utc = excluded.expires_at_utc,
            generation_id = excluded.generation_id
        """,
        (
            *key,
            holder_id,
            (now.timestamp() + _PROJECTION_LEASE_SECONDS),
            generation_id,
        ),
    )
    # ISO-8601 comparison is deliberate for portable SQLite ordering.
    conn.execute(
        """
        update llm_usage_projection_leases
        set expires_at_utc = ?
        where ledger_path = ? and daily_path = ? and holder_id = ?
        """,
        (
            datetime.fromtimestamp(
                now.timestamp() + _PROJECTION_LEASE_SECONDS, tz=timezone.utc
            ).isoformat(),
            *key,
            holder_id,
        ),
    )


def _release_projection_lease(
    *, db_path: Path, ledger_path: Path, daily_path: Path, holder_id: str
) -> None:
    with _LOCK, sqlite3.connect(db_path) as conn:
        _ensure_schema(conn)
        conn.execute(
            """
            delete from llm_usage_projection_leases
            where ledger_path = ? and daily_path = ? and holder_id = ?
            """,
            (str(ledger_path.resolve()), str(daily_path.resolve()), holder_id),
        )


def _renew_projection_lease(
    conn: sqlite3.Connection,
    *,
    ledger_path: Path,
    daily_path: Path,
    holder_id: str,
    generation_id: int,
) -> None:
    """Fence stale workers before they commit a projection checkpoint."""
    now = datetime.now(timezone.utc)
    cursor = conn.execute(
        """
        update llm_usage_projection_leases
        set expires_at_utc = ?
        where ledger_path = ? and daily_path = ? and holder_id = ?
          and generation_id = ? and expires_at_utc > ?
        """,
        (
            datetime.fromtimestamp(
                now.timestamp() + _PROJECTION_LEASE_SECONDS, tz=timezone.utc
            ).isoformat(),
            str(ledger_path.resolve()),
            str(daily_path.resolve()),
            holder_id,
            generation_id,
            now.isoformat(),
        ),
    )
    if cursor.rowcount != 1:
        raise AppError(
            code="llm_usage_projection_lease_lost",
            message="Projection lease expired or was taken over before checkpoint commit",
            retryable=True,
            context={
                "ledger_path": str(ledger_path),
                "daily_path": str(daily_path),
                "generation_id": generation_id,
            },
        )


def _rollup_metrics(
    rows: list[dict[str, Any]], key: str
) -> dict[str, dict[str, float | int]]:
    totals: dict[str, dict[str, float | int]] = {}
    for row in rows:
        if key == "date":
            bucket = str(row["timestamp_utc"])[:10] or "unknown"
        else:
            bucket = str(row.get(key) or "unknown")
        metrics = totals.setdefault(
            bucket,
            {
                "input_tokens": 0,
                "output_tokens": 0,
                "tool_calls": 0,
                "estimated_cost_usd": 0.0,
            },
        )
        metrics["input_tokens"] += int(row["input_tokens"])
        metrics["output_tokens"] += int(row["output_tokens"])
        metrics["tool_calls"] += int(row["tool_calls"])
        metrics["estimated_cost_usd"] += float(row["estimated_cost_usd"])
    return totals


def _rollup_usage_context(
    rows: list[dict[str, Any]], key: str
) -> dict[str, dict[str, float | int]]:
    """Aggregate canonical events by an explicit context dimension.

    Historical events have no new columns, so their safe, queryable bucket is
    ``unknown`` rather than a guessed report or artifact family.
    """
    normalized_rows: list[dict[str, Any]] = []
    for row in rows:
        extra = row.get("extra")
        context = (
            dict(extra.get("usage_context") or {}) if isinstance(extra, dict) else {}
        )
        normalized_rows.append({**row, key: str(context.get(key) or "unknown")})
    return _rollup_metrics(normalized_rows, key)


def _cost_total(metrics: dict[str, float | int]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "total_input_tokens": int(metrics["input_tokens"]),
        "total_output_tokens": int(metrics["output_tokens"]),
        "total_tool_calls": int(metrics["tool_calls"]),
        "estimated_cost_usd": round(float(metrics["estimated_cost_usd"]), 6),
    }


def _daily_total(day: str, metrics: dict[str, float | int]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "date_utc": day,
        "total_usd": round(float(metrics["estimated_cost_usd"]), 6),
        "input_tokens": int(metrics["input_tokens"]),
        "output_tokens": int(metrics["output_tokens"]),
        "tool_calls": int(metrics["tool_calls"]),
    }


def _daily_export_payload(
    rows: list[dict[str, Any]],
    *,
    db_path: Path,
    source_sha256: str,
    ledger_sha256: str,
    generation_id: int,
    last_segment_sha256: str,
) -> dict[str, Any]:
    by_date = _rollup_metrics(rows, "date")
    by_run = _rollup_metrics(rows, "run_id")
    by_task = _rollup_metrics(rows, "task_id")
    by_report = _rollup_usage_context(rows, "report_id")
    by_workflow = _rollup_usage_context(rows, "workflow")
    by_stage = _rollup_usage_context(rows, "stage")
    by_semantic_task = _rollup_usage_context(rows, "semantic_task")
    by_prompt = _rollup_usage_context(rows, "prompt_namespace")
    by_artifact_family = _rollup_usage_context(rows, "artifact_family")
    by_publisher = _rollup_usage_context(rows, "publisher_name")
    totals_by_date = {
        day: _daily_total(day, metrics) for day, metrics in sorted(by_date.items())
    }
    return {
        "schema_version": "1.3",
        "generated_at": max((str(row["timestamp_utc"]) for row in rows), default=""),
        "ledger_state": {
            "schema_version": "1.0",
            "source": "canonical_sqlite",
            "db_path": str(db_path),
            "event_count": len(rows),
            "generation_id": generation_id,
            "source_sha256": source_sha256,
            "ledger_sha256": ledger_sha256,
            "last_segment_sha256": last_segment_sha256,
        },
        "totals": totals_by_date,
        "totals_by_date": totals_by_date,
        "totals_by_run": {
            run_id: _cost_total(metrics) for run_id, metrics in sorted(by_run.items())
        },
        "totals_by_task": {
            task_id: _cost_total(metrics)
            for task_id, metrics in sorted(by_task.items())
        },
        "totals_by_report": {
            key: _cost_total(metrics) for key, metrics in sorted(by_report.items())
        },
        "totals_by_workflow": {
            key: _cost_total(metrics) for key, metrics in sorted(by_workflow.items())
        },
        "totals_by_stage": {
            key: _cost_total(metrics) for key, metrics in sorted(by_stage.items())
        },
        "totals_by_semantic_task": {
            key: _cost_total(metrics)
            for key, metrics in sorted(by_semantic_task.items())
        },
        "totals_by_prompt_namespace": {
            key: _cost_total(metrics) for key, metrics in sorted(by_prompt.items())
        },
        "totals_by_artifact_family": {
            key: _cost_total(metrics)
            for key, metrics in sorted(by_artifact_family.items())
        },
        "totals_by_publisher": {
            key: _cost_total(metrics) for key, metrics in sorted(by_publisher.items())
        },
    }


def _increment_cost_total(total: dict[str, Any], row: dict[str, Any]) -> None:
    total["total_input_tokens"] = int(total.get("total_input_tokens") or 0) + int(
        row["input_tokens"]
    )
    total["total_output_tokens"] = int(total.get("total_output_tokens") or 0) + int(
        row["output_tokens"]
    )
    total["total_tool_calls"] = int(total.get("total_tool_calls") or 0) + int(
        row["tool_calls"]
    )
    total["estimated_cost_usd"] = round(
        float(total.get("estimated_cost_usd") or 0.0)
        + float(row["estimated_cost_usd"]),
        6,
    )


def _increment_daily_total(total: dict[str, Any], row: dict[str, Any]) -> None:
    total["input_tokens"] = int(total.get("input_tokens") or 0) + int(
        row["input_tokens"]
    )
    total["output_tokens"] = int(total.get("output_tokens") or 0) + int(
        row["output_tokens"]
    )
    total["tool_calls"] = int(total.get("tool_calls") or 0) + int(row["tool_calls"])
    total["total_usd"] = round(
        float(total.get("total_usd") or 0.0) + float(row["estimated_cost_usd"]),
        6,
    )


def _increment_daily_export_payload(
    existing_payload: dict[str, Any],
    rows: list[dict[str, Any]],
    *,
    db_path: Path,
    source_sha256: str,
    ledger_sha256: str,
    event_count: int,
    last_projected_event_id: int,
    generation_id: int,
    last_segment_sha256: str,
) -> dict[str, Any]:
    totals_by_date = {
        str(key): dict(value)
        for key, value in dict(existing_payload.get("totals_by_date") or {}).items()
    }
    totals_by_run = {
        str(key): dict(value)
        for key, value in dict(existing_payload.get("totals_by_run") or {}).items()
    }
    totals_by_task = {
        str(key): dict(value)
        for key, value in dict(existing_payload.get("totals_by_task") or {}).items()
    }
    context_totals = {
        "report_id": {
            str(key): dict(value)
            for key, value in dict(
                existing_payload.get("totals_by_report") or {}
            ).items()
        },
        "workflow": {
            str(key): dict(value)
            for key, value in dict(
                existing_payload.get("totals_by_workflow") or {}
            ).items()
        },
        "prompt_namespace": {
            str(key): dict(value)
            for key, value in dict(
                existing_payload.get("totals_by_prompt_namespace") or {}
            ).items()
        },
        "artifact_family": {
            str(key): dict(value)
            for key, value in dict(
                existing_payload.get("totals_by_artifact_family") or {}
            ).items()
        },
        "publisher_name": {
            str(key): dict(value)
            for key, value in dict(
                existing_payload.get("totals_by_publisher") or {}
            ).items()
        },
    }
    for row in rows:
        date_key = str(row["timestamp_utc"])[:10] or "unknown"
        date_total = totals_by_date.setdefault(
            date_key,
            {
                "schema_version": "1.0",
                "date_utc": date_key,
                "total_usd": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "tool_calls": 0,
            },
        )
        _increment_daily_total(date_total, row)
        for key, totals in (
            (str(row["run_id"] or "unknown"), totals_by_run),
            (str(row["task_id"] or "unknown"), totals_by_task),
        ):
            cost_total = totals.setdefault(
                key,
                {
                    "schema_version": "1.0",
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_tool_calls": 0,
                    "estimated_cost_usd": 0.0,
                },
            )
            _increment_cost_total(cost_total, row)
        extra = row.get("extra")
        usage_context = (
            dict(extra.get("usage_context") or {}) if isinstance(extra, dict) else {}
        )
        for dimension, totals in context_totals.items():
            key = str(usage_context.get(dimension) or "unknown")
            cost_total = totals.setdefault(
                key,
                {
                    "schema_version": "1.0",
                    "total_input_tokens": 0,
                    "total_output_tokens": 0,
                    "total_tool_calls": 0,
                    "estimated_cost_usd": 0.0,
                },
            )
            _increment_cost_total(cost_total, row)
    return {
        "schema_version": "1.3",
        "generated_at": max(
            [str(existing_payload.get("generated_at") or "")]
            + [str(row["timestamp_utc"]) for row in rows]
        ),
        "ledger_state": {
            "schema_version": "1.0",
            "source": "canonical_sqlite",
            "db_path": str(db_path),
            "event_count": event_count,
            "generation_id": generation_id,
            "last_projected_event_id": last_projected_event_id,
            "source_sha256": source_sha256,
            "ledger_sha256": ledger_sha256,
            "last_segment_sha256": last_segment_sha256,
        },
        "totals": dict(sorted(totals_by_date.items())),
        "totals_by_date": dict(sorted(totals_by_date.items())),
        "totals_by_run": dict(sorted(totals_by_run.items())),
        "totals_by_task": dict(sorted(totals_by_task.items())),
        "totals_by_report": dict(sorted(context_totals["report_id"].items())),
        "totals_by_workflow": dict(sorted(context_totals["workflow"].items())),
        "totals_by_prompt_namespace": dict(
            sorted(context_totals["prompt_namespace"].items())
        ),
        "totals_by_artifact_family": dict(
            sorted(context_totals["artifact_family"].items())
        ),
        "totals_by_publisher": dict(sorted(context_totals["publisher_name"].items())),
    }


def rebuild_usage_exports(
    request: LLMUsageExportRebuildRequest, ctx: RunContext
) -> LLMUsageExportRebuildResponse:
    if request.schema_version != "1.0" or not all(
        str(value or "").strip()
        for value in (request.db_path, request.ledger_path, request.daily_path)
    ):
        raise AppError(
            code="llm_usage_export_rebuild_request_invalid",
            message="Usage export rebuild requires canonical and both derived paths",
            retryable=False,
        )
    db_path = Path(request.db_path)
    ledger_path = Path(request.ledger_path)
    daily_path = Path(request.daily_path)
    lease_holder_id = uuid.uuid4().hex
    lease_acquired = False
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_export_rebuild_start",
            module=logger.name,
            fields={
                "db_path": str(db_path),
                "ledger_path": str(ledger_path),
                "daily_path": str(daily_path),
            },
        )
    )
    try:
        with _LOCK, sqlite3.connect(db_path) as conn:
            _ensure_schema(conn)
            checkpoint = conn.execute(
                """
                select event_count, source_sha256, ledger_sha256, daily_sha256,
                       last_projected_event_id, generation_id
                from llm_usage_export_checkpoints
                where ledger_path = ? and daily_path = ?
                """,
                (str(ledger_path.resolve()), str(daily_path.resolve())),
            ).fetchone()
            canonical_event_count, highest_event_id = conn.execute(
                "select count(*), coalesce(max(id), 0) from llm_usage_events"
            ).fetchone()
            baseline_required = not _projection_files_valid(
                checkpoint, ledger_path, daily_path
            )
            last_projected_event_id = 0 if baseline_required else int(checkpoint[4])
            rows = _canonical_export_rows(conn, after_event_id=last_projected_event_id)
            if rows or baseline_required:
                generation_id = allocate_projection_generation(
                    conn,
                    ledger_path=str(ledger_path.resolve()),
                    daily_path=str(daily_path.resolve()),
                )
                _acquire_projection_lease(
                    conn,
                    ledger_path=ledger_path,
                    daily_path=daily_path,
                    holder_id=lease_holder_id,
                    generation_id=generation_id,
                )
                lease_acquired = True
        if not rows and not baseline_required:
            _release_projection_lease(
                db_path=db_path,
                ledger_path=ledger_path,
                daily_path=daily_path,
                holder_id=lease_holder_id,
            )
            lease_acquired = False
            return LLMUsageExportRebuildResponse(
                schema_version="1.1",
                db_path=str(db_path),
                ledger_path=str(ledger_path),
                daily_path=str(daily_path),
                event_count=int(checkpoint[0]),
                source_sha256=str(checkpoint[1]),
                ledger_sha256=str(checkpoint[2]),
                daily_sha256=str(checkpoint[3]),
                last_projected_event_id=last_projected_event_id,
                projected_event_count=0,
                generation_id=int(checkpoint[5]),
            )
        projected_content = b"".join(_stable_json_bytes(row) for row in rows)
        projected_sha256 = sha256(projected_content).hexdigest()
        ledger_content = projected_content
        source_sha256 = (
            projected_sha256
            if baseline_required
            else sha256(
                f"{checkpoint[1]}:{generation_id}:{projected_sha256}".encode("utf-8")
            ).hexdigest()
        )
        ledger_sha256 = source_sha256
        if baseline_required:
            daily_payload = _daily_export_payload(
                rows,
                db_path=db_path,
                source_sha256=source_sha256,
                ledger_sha256=ledger_sha256,
                generation_id=generation_id,
                last_segment_sha256=projected_sha256,
            )
            daily_payload["ledger_state"]["event_count"] = int(canonical_event_count)
            daily_payload["ledger_state"]["last_projected_event_id"] = int(
                highest_event_id
            )
        else:
            daily_payload = _increment_daily_export_payload(
                json.loads(daily_path.read_text(encoding="utf-8")),
                rows,
                db_path=db_path,
                source_sha256=source_sha256,
                ledger_sha256=ledger_sha256,
                event_count=int(canonical_event_count),
                last_projected_event_id=int(highest_event_id),
                generation_id=generation_id,
                last_segment_sha256=projected_sha256,
            )
        daily_content = _stable_json_bytes(daily_payload)
        daily_sha256 = sha256(daily_content).hexdigest()
        if baseline_required:
            file_service.write_bytes(
                WriteBytesRequest(
                    schema_version="1.0",
                    path=str(_projection_segment_path(ledger_path, generation_id)),
                    content=projected_content,
                ),
                ctx,
            )
            file_service.write_bytes(
                WriteBytesRequest(
                    schema_version="1.0", path=str(ledger_path), content=ledger_content
                ),
                ctx,
            )
        else:
            segment_path = _projection_segment_path(ledger_path, generation_id)
            file_service.write_bytes(
                WriteBytesRequest(
                    schema_version="1.0",
                    path=str(segment_path),
                    content=projected_content,
                ),
                ctx,
            )
            file_service.append_bytes(
                AppendBytesRequest(
                    schema_version="1.0",
                    path=str(ledger_path),
                    content=projected_content,
                ),
                ctx,
            )
        file_service.write_bytes(
            WriteBytesRequest(
                schema_version="1.0", path=str(daily_path), content=daily_content
            ),
            ctx,
        )
        with _LOCK, sqlite3.connect(db_path) as conn:
            _ensure_schema(conn)
            _renew_projection_lease(
                conn,
                ledger_path=ledger_path,
                daily_path=daily_path,
                holder_id=lease_holder_id,
                generation_id=generation_id,
            )
            conn.execute(
                """
                insert into llm_usage_export_checkpoints (
                    ledger_path, daily_path, event_count, source_sha256,
                    ledger_sha256, daily_sha256, completed_at_utc,
                    last_projected_event_id
                    , generation_id
                ) values (?, ?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(ledger_path, daily_path) do update set
                    event_count = excluded.event_count,
                    source_sha256 = excluded.source_sha256,
                    ledger_sha256 = excluded.ledger_sha256,
                    daily_sha256 = excluded.daily_sha256,
                    completed_at_utc = excluded.completed_at_utc,
                    last_projected_event_id = excluded.last_projected_event_id
                    , generation_id = excluded.generation_id
                """,
                (
                    str(ledger_path.resolve()),
                    str(daily_path.resolve()),
                    int(canonical_event_count),
                    source_sha256,
                    ledger_sha256,
                    daily_sha256,
                    datetime.now(timezone.utc).isoformat(),
                    int(highest_event_id),
                    generation_id,
                ),
            )
        _release_projection_lease(
            db_path=db_path,
            ledger_path=ledger_path,
            daily_path=daily_path,
            holder_id=lease_holder_id,
        )
        lease_acquired = False
    except (AppError, OSError, sqlite3.Error, TypeError, ValueError) as exc:
        if lease_acquired:
            _release_projection_lease(
                db_path=db_path,
                ledger_path=ledger_path,
                daily_path=daily_path,
                holder_id=lease_holder_id,
            )
        if isinstance(exc, AppError):
            raise
        raise AppError(
            code="llm_usage_export_rebuild_failed",
            message="Failed to rebuild derived usage exports from canonical SQLite",
            cause=exc,
            retryable=False,
            context={
                "db_path": str(db_path),
                "ledger_path": str(ledger_path),
                "daily_path": str(daily_path),
            },
        ) from exc
    response = LLMUsageExportRebuildResponse(
        schema_version="1.1",
        db_path=str(db_path),
        ledger_path=str(ledger_path),
        daily_path=str(daily_path),
        event_count=int(canonical_event_count),
        source_sha256=source_sha256,
        ledger_sha256=ledger_sha256,
        daily_sha256=daily_sha256,
        last_projected_event_id=int(highest_event_id),
        projected_event_count=len(rows),
        generation_id=generation_id,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_export_rebuild_complete",
            module=logger.name,
            fields={
                "event_count": response.event_count,
                "projected_event_count": response.projected_event_count,
                "last_projected_event_id": response.last_projected_event_id,
                "source_sha256": response.source_sha256,
                "generation_id": response.generation_id,
                "ledger_path": response.ledger_path,
                "daily_path": response.daily_path,
            },
        )
    )
    return response


def _reset_usage_export_checkpoint(
    *, db_path: str, ledger_path: str, daily_path: str
) -> None:
    with _LOCK, sqlite3.connect(db_path) as conn:
        _ensure_schema(conn)
        conn.execute(
            """
            delete from llm_usage_export_checkpoints
            where ledger_path = ? and daily_path = ?
            """,
            (str(Path(ledger_path).resolve()), str(Path(daily_path).resolve())),
        )


def get_projection_status(
    request: LLMUsageProjectionStatusRequest, ctx: RunContext
) -> LLMUsageProjectionStatusResponse:
    if request.schema_version != "1.0" or not all(
        str(value or "").strip()
        for value in (request.db_path, request.ledger_path, request.daily_path)
    ):
        raise AppError(
            code="llm_usage_projection_status_request_invalid",
            message="Projection status requires canonical and both derived paths",
            retryable=False,
        )
    db_path = Path(request.db_path)
    ledger_path = Path(request.ledger_path)
    daily_path = Path(request.daily_path)
    try:
        with _LOCK, sqlite3.connect(db_path) as conn:
            _ensure_schema(conn)
            latest_event_id, total_events = conn.execute(
                "select coalesce(max(id), 0), count(*) from llm_usage_events"
            ).fetchone()
            checkpoint = conn.execute(
                """
                select event_count, source_sha256, ledger_sha256, daily_sha256,
                       last_projected_event_id, generation_id, completed_at_utc
                from llm_usage_export_checkpoints where ledger_path = ? and daily_path = ?
                """,
                (str(ledger_path.resolve()), str(daily_path.resolve())),
            ).fetchone()
            projected_event_id = int(checkpoint[4]) if checkpoint else 0
            pending_count, pending_cost = conn.execute(
                """
                select count(*), coalesce(sum(estimated_cost_usd), 0.0)
                from llm_usage_events where id > ?
                """,
                (projected_event_id,),
            ).fetchone()
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise AppError(
            code="llm_usage_projection_status_failed",
            message="Failed to read canonical usage projection status",
            cause=exc,
            retryable=False,
            context={"db_path": str(db_path)},
        ) from exc
    files_valid = _projection_files_valid(checkpoint, ledger_path, daily_path)
    response = LLMUsageProjectionStatusResponse(
        schema_version="1.0",
        db_path=str(db_path),
        latest_event_id=int(latest_event_id),
        projected_event_id=projected_event_id,
        pending_event_count=int(pending_count),
        pending_estimated_cost_usd=round(float(pending_cost), 6),
        projection_generation_id=int(checkpoint[5]) if checkpoint else 0,
        last_successful_projection_at_utc=str(checkpoint[6]) if checkpoint else "",
        files_valid=files_valid,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_projection_status_read",
            module=logger.name,
            fields={
                "latest_event_id": response.latest_event_id,
                "projected_event_id": response.projected_event_id,
                "pending_event_count": response.pending_event_count,
                "pending_estimated_cost_usd": response.pending_estimated_cost_usd,
                "files_valid": response.files_valid,
            },
        )
    )
    return response


def finalize_usage_projection(
    request: LLMUsageProjectionStatusRequest, ctx: RunContext
) -> LLMUsageProjectionStatusResponse:
    """Materialize pending canonical usage through the shared bounded finalizer."""
    status = get_projection_status(request, ctx)
    if status.latest_event_id and (
        status.pending_event_count or not status.files_valid
    ):
        rebuild_usage_exports(
            LLMUsageExportRebuildRequest(
                schema_version="1.0",
                db_path=request.db_path,
                ledger_path=request.ledger_path,
                daily_path=request.daily_path,
            ),
            ctx,
        )
        status = get_projection_status(request, ctx)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_projection_finalized",
            module=logger.name,
            fields={
                "latest_event_id": status.latest_event_id,
                "projected_event_id": status.projected_event_id,
                "pending_event_count": status.pending_event_count,
                "files_valid": status.files_valid,
                "projection_generation_id": status.projection_generation_id,
            },
        )
    )
    return status


def evaluate_daily_spend_guardrail(
    request: LLMUsageSpendGuardrailRequest, ctx: RunContext
) -> LLMUsageSpendGuardrailResponse:
    if request.schema_version != "1.0" or not str(request.db_path or "").strip():
        raise AppError(
            code="llm_usage_spend_guardrail_request_invalid",
            message="Spend guardrail requires a canonical usage database path",
            retryable=False,
        )
    Path(request.db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)
    day_utc = datetime.now(timezone.utc).date().isoformat()
    median_forecast = 0.0
    median_sample_count = 0
    in_flight_reserved = 0.0
    reservation_created = False
    try:
        with _LOCK, sqlite3.connect(request.db_path) as conn:
            _ensure_schema(conn)
            now = datetime.now(timezone.utc)
            conn.execute(
                """
                update llm_usage_spend_reservations
                set status = 'expired'
                where status = 'reserved' and expires_at_utc <= ?
                """,
                (now.isoformat(),),
            )
            recorded = conn.execute(
                """
                select coalesce(sum(estimated_cost_usd), 0.0) from llm_usage_events
                where substr(timestamp_utc, 1, 10) = ?
                """,
                (day_utc,),
            ).fetchone()[0]
        median_path = _median_db_path(Path(request.db_path))
        if (
            all((request.provider, request.task, request.action, request.model))
            and median_path.is_file()
        ):
            with sqlite3.connect(median_path) as median_conn:
                median_row = median_conn.execute(
                    """
                    select sample_count, median_estimated_cost_usd
                    from llm_usage_medians
                    where provider = ? and task = ? and action = ? and model = ?
                      and prompt_namespace = ?
                    """,
                    (
                        request.provider,
                        request.task,
                        request.action,
                        request.model,
                        request.prompt_namespace,
                    ),
                ).fetchone()
            if median_row is not None:
                median_sample_count = int(median_row[0])
                median_forecast = round(float(median_row[1]), 6)
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise AppError(
            code="llm_usage_spend_guardrail_failed",
            message="Failed to read canonical daily spend",
            cause=exc,
            retryable=False,
            context={"db_path": request.db_path},
        ) from exc
    spend = round(float(recorded or 0.0), 6)
    try:
        with _LOCK, sqlite3.connect(request.db_path) as conn:
            conn.execute("begin immediate")
            _ensure_schema(conn)
            now = datetime.now(timezone.utc)
            existing_reservation = None
            if request.reservation_key:
                existing_reservation = conn.execute(
                    """
                    select estimated_cost_usd from llm_usage_spend_reservations
                    where reservation_key = ? and status = 'reserved'
                      and expires_at_utc > ?
                    """,
                    (request.reservation_key, now.isoformat()),
                ).fetchone()
            in_flight_reserved = round(
                float(
                    conn.execute(
                        """
                        select coalesce(sum(estimated_cost_usd), 0.0)
                        from llm_usage_spend_reservations
                        where day_utc = ? and status = 'reserved' and expires_at_utc > ?
                        """,
                        (day_utc, now.isoformat()),
                    ).fetchone()[0]
                    or 0.0
                ),
                6,
            )
            if existing_reservation is not None:
                median_forecast = round(float(existing_reservation[0]), 6)
                in_flight_reserved = round(in_flight_reserved - median_forecast, 6)
            projected_spend = round(spend + in_flight_reserved + median_forecast, 6)
            if request.stop_usd is not None and projected_spend >= float(
                request.stop_usd
            ):
                decision = "stop"
            elif request.pause_usd is not None and projected_spend >= float(
                request.pause_usd
            ):
                decision = "pause"
            elif float(request.warn_usd) >= 0.0 and projected_spend >= float(
                request.warn_usd
            ):
                decision = "warn"
            else:
                decision = "allow"
            if (
                request.reserve_in_flight
                and request.reservation_key
                and decision in {"allow", "warn"}
                and median_forecast > 0
                and existing_reservation is None
            ):
                cursor = conn.execute(
                    """
                    insert into llm_usage_spend_reservations (
                        reservation_key, day_utc, estimated_cost_usd, status,
                        expires_at_utc, created_at_utc
                    ) values (?, ?, ?, 'reserved', ?, ?)
                    """,
                    (
                        request.reservation_key,
                        day_utc,
                        median_forecast,
                        (
                            now
                            + timedelta(seconds=max(1, request.reservation_ttl_seconds))
                        ).isoformat(),
                        now.isoformat(),
                    ),
                )
                reservation_created = cursor.rowcount == 1
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise AppError(
            code="llm_usage_spend_guardrail_failed",
            message="Failed to read in-flight spend reservations",
            cause=exc,
            retryable=False,
            context={"db_path": request.db_path},
        ) from exc
    response = LLMUsageSpendGuardrailResponse(
        schema_version="1.0",
        day_utc=day_utc,
        canonical_spend_usd=spend,
        median_forecast_usd=median_forecast,
        median_sample_count=median_sample_count,
        projected_spend_usd=projected_spend,
        forecast_status="matched" if median_sample_count else "cold_start",
        warn_usd=float(request.warn_usd),
        decision=decision,
        in_flight_reserved_usd=in_flight_reserved,
        reservation_created=reservation_created,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_spend_guardrail_evaluated",
            module=logger.name,
            fields={
                "day_utc": response.day_utc,
                "canonical_spend_usd": response.canonical_spend_usd,
                "median_forecast_usd": response.median_forecast_usd,
                "median_sample_count": response.median_sample_count,
                "projected_spend_usd": response.projected_spend_usd,
                "forecast_status": response.forecast_status,
                "in_flight_reserved_usd": response.in_flight_reserved_usd,
                "reservation_created": response.reservation_created,
                "warn_usd": response.warn_usd,
                "decision": response.decision,
                "pause_usd": request.pause_usd,
                "stop_usd": request.stop_usd,
                "overrides_allowed": request.overrides_allowed,
            },
        )
    )
    return response


def release_daily_spend_reservation(
    request: LLMUsageSpendReservationReleaseRequest, ctx: RunContext
) -> LLMUsageSpendReservationReleaseResponse:
    if (
        request.schema_version != "1.0"
        or not request.db_path
        or not request.reservation_key
    ):
        raise AppError(
            code="llm_usage_spend_reservation_release_request_invalid",
            message="Spend-reservation release requires a canonical database and key",
            retryable=False,
        )
    try:
        with _LOCK, sqlite3.connect(request.db_path) as conn:
            _ensure_schema(conn)
            cursor = conn.execute(
                """
                update llm_usage_spend_reservations
                set status = 'released', released_at_utc = ?
                where reservation_key = ? and status = 'reserved'
                """,
                (datetime.now(timezone.utc).isoformat(), request.reservation_key),
            )
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise AppError(
            code="llm_usage_spend_reservation_release_failed",
            message="Failed to reconcile an in-flight LLM spend reservation",
            cause=exc,
            retryable=False,
            context={"db_path": request.db_path},
        ) from exc
    response = LLMUsageSpendReservationReleaseResponse(
        schema_version="1.0", released=cursor.rowcount == 1
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_spend_reservation_released",
            module=logger.name,
            fields={
                "reservation_key": request.reservation_key,
                "released": response.released,
            },
        )
    )
    return response


def reconcile_usage_export(
    request: LLMUsageLedgerReconciliationRequest, ctx: RunContext
) -> LLMUsageLedgerReconciliationResponse:
    if request.schema_version != "1.0":
        raise AppError(
            code="llm_usage_ledger_reconciliation_schema_version_invalid",
            message="LLM usage reconciliation schema version is unsupported",
            retryable=False,
        )
    db_path = Path(request.db_path)
    ledger_path = Path(request.ledger_path)
    daily_path = Path(request.daily_path) if request.daily_path else None
    try:
        with _LOCK, sqlite3.connect(db_path) as conn:
            _ensure_schema(conn)
            sqlite_totals = conn.execute(
                """
                select count(*), coalesce(sum(input_tokens), 0),
                       coalesce(sum(output_tokens), 0),
                       coalesce(sum(cached_input_tokens), 0),
                       coalesce(sum(estimated_cost_usd), 0.0)
                from llm_usage_events
                """
            ).fetchone()
            highest_event_id = int(
                conn.execute(
                    "select coalesce(max(id), 0) from llm_usage_events"
                ).fetchone()[0]
            )
            canonical_rows = _canonical_export_rows(conn)
            checkpoint = None
            if daily_path is not None:
                checkpoint = conn.execute(
                    """
                    select event_count, source_sha256, ledger_sha256, daily_sha256,
                           last_projected_event_id, generation_id
                    from llm_usage_export_checkpoints
                    where ledger_path = ? and daily_path = ?
                    """,
                    (str(ledger_path.resolve()), str(daily_path.resolve())),
                ).fetchone()
        export_rows = [
            json.loads(line)
            for line in ledger_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except (OSError, sqlite3.Error, TypeError, ValueError, json.JSONDecodeError) as exc:
        if request.repair and request.daily_path:
            _reset_usage_export_checkpoint(
                db_path=request.db_path,
                ledger_path=request.ledger_path,
                daily_path=request.daily_path,
            )
            rebuild_usage_exports(
                LLMUsageExportRebuildRequest(
                    schema_version="1.0",
                    db_path=request.db_path,
                    ledger_path=request.ledger_path,
                    daily_path=request.daily_path,
                ),
                ctx,
            )
            repaired = reconcile_usage_export(
                LLMUsageLedgerReconciliationRequest(
                    schema_version="1.0",
                    db_path=request.db_path,
                    ledger_path=request.ledger_path,
                    daily_path=request.daily_path,
                ),
                ctx,
            )
            return replace(repaired, repaired=True)
        raise AppError(
            code="llm_usage_ledger_reconciliation_failed",
            message="Failed to reconcile canonical LLM usage with its JSONL export",
            cause=exc,
            retryable=False,
            context={"db_path": str(db_path), "ledger_path": str(ledger_path)},
        ) from exc
    export_totals = (
        len(export_rows),
        sum(int(row.get("input_tokens") or 0) for row in export_rows),
        sum(int(row.get("output_tokens") or 0) for row in export_rows),
        sum(int(row.get("cached_input_tokens") or 0) for row in export_rows),
        sum(float(row.get("estimated_cost_usd") or 0.0) for row in export_rows),
    )
    totals_match = (
        tuple(int(value) for value in sqlite_totals[:4]) == export_totals[:4]
        and abs(float(sqlite_totals[4]) - export_totals[4]) <= 1e-9
    )
    canonical_ids = [
        int(row["extra"]["canonical_event_id"])
        for row in export_rows
        if isinstance(row.get("extra"), dict) and "canonical_event_id" in row["extra"]
    ]
    expected_canonical_ids = [
        int(row["extra"]["canonical_event_id"]) for row in canonical_rows
    ]
    canonical_projection = bool(canonical_ids)
    identity_matches = (
        canonical_ids == expected_canonical_ids if canonical_projection else True
    )
    payload_matches = export_rows == canonical_rows if canonical_projection else True
    daily_matches = True
    checkpoint_matches = True
    mismatch_reasons: list[str] = []
    if not totals_match:
        mismatch_reasons.append("totals_mismatch")
    if not identity_matches:
        mismatch_reasons.append("canonical_event_identity_mismatch")
    if not payload_matches:
        mismatch_reasons.append("canonical_event_payload_mismatch")
    if daily_path is not None:
        expected_ledger = b"".join(_stable_json_bytes(row) for row in canonical_rows)
        source_sha256 = (
            str(checkpoint[1]) if checkpoint else sha256(expected_ledger).hexdigest()
        )
        ledger_sha256 = (
            str(checkpoint[2]) if checkpoint else sha256(expected_ledger).hexdigest()
        )
        generation_id = int(checkpoint[5]) if checkpoint else 0
        segment_path = _projection_segment_path(ledger_path, generation_id)
        try:
            last_segment_sha256 = sha256(segment_path.read_bytes()).hexdigest()
        except OSError:
            last_segment_sha256 = ""
        expected_daily = _daily_export_payload(
            canonical_rows,
            db_path=db_path,
            source_sha256=source_sha256,
            ledger_sha256=ledger_sha256,
            generation_id=generation_id,
            last_segment_sha256=last_segment_sha256,
        )
        expected_daily["ledger_state"]["event_count"] = int(sqlite_totals[0])
        expected_daily["ledger_state"]["last_projected_event_id"] = highest_event_id
        try:
            daily_matches = daily_path.read_bytes() == _stable_json_bytes(
                expected_daily
            )
        except OSError:
            daily_matches = False
        checkpoint_matches = _projection_files_valid(
            checkpoint, ledger_path, daily_path
        )
        if not daily_matches:
            mismatch_reasons.append("daily_projection_mismatch")
        if not checkpoint_matches:
            mismatch_reasons.append("checkpoint_mismatch")
    matches = (
        totals_match
        and identity_matches
        and payload_matches
        and daily_matches
        and checkpoint_matches
    )
    response = LLMUsageLedgerReconciliationResponse(
        schema_version="1.0",
        db_path=str(db_path),
        ledger_path=str(ledger_path),
        sqlite_event_count=int(sqlite_totals[0]),
        export_event_count=export_totals[0],
        sqlite_input_tokens=int(sqlite_totals[1]),
        export_input_tokens=export_totals[1],
        sqlite_output_tokens=int(sqlite_totals[2]),
        export_output_tokens=export_totals[2],
        sqlite_cached_input_tokens=int(sqlite_totals[3]),
        export_cached_input_tokens=export_totals[3],
        sqlite_estimated_cost_usd=float(sqlite_totals[4]),
        export_estimated_cost_usd=export_totals[4],
        matches=matches,
        daily_matches=daily_matches,
        checkpoint_matches=checkpoint_matches,
        mismatch_reasons=tuple(mismatch_reasons),
    )
    if not response.matches and request.repair and request.daily_path:
        _reset_usage_export_checkpoint(
            db_path=request.db_path,
            ledger_path=request.ledger_path,
            daily_path=request.daily_path,
        )
        rebuild_usage_exports(
            LLMUsageExportRebuildRequest(
                schema_version="1.0",
                db_path=request.db_path,
                ledger_path=request.ledger_path,
                daily_path=request.daily_path,
            ),
            ctx,
        )
        repaired = reconcile_usage_export(
            LLMUsageLedgerReconciliationRequest(
                schema_version="1.0",
                db_path=request.db_path,
                ledger_path=request.ledger_path,
                daily_path=request.daily_path,
            ),
            ctx,
        )
        return replace(repaired, repaired=True)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_ledger_reconciliation_complete",
            module=logger.name,
            fields={
                "db_path": response.db_path,
                "ledger_path": response.ledger_path,
                "matches": response.matches,
                "sqlite_event_count": response.sqlite_event_count,
                "export_event_count": response.export_event_count,
                "daily_matches": response.daily_matches,
                "checkpoint_matches": response.checkpoint_matches,
                "mismatch_reasons": list(response.mismatch_reasons),
            },
        )
    )
    return response
