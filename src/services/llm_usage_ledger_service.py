from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from statistics import median
from typing import Any

from src.contracts.files import WriteBytesRequest
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
)
from src.contracts.run_context import RunContext
from src.services import file_service
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.llm_usage_ledger_service")
_LOCK = threading.Lock()
_MEDIAN_REBUILD_EXECUTOR = ThreadPoolExecutor(
    max_workers=1, thread_name_prefix="llm_usage_median_rebuild"
)
_PENDING_MEDIAN_REBUILD_PATHS: set[str] = set()
_PENDING_MEDIAN_REBUILD_LOCK = threading.Lock()
_MEDIAN_REBUILD_EVENT_INTERVAL = 20
_USAGE_EXPORT_PROJECTION_INTERVAL = 20
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
    }
    for column, definition in migrations.items():
        if column not in existing_columns:
            conn.execute(
                f"alter table llm_usage_events add column {column} {definition}"
            )
    conn.execute(
        "update llm_usage_events set event_key = 'legacy:' || id where event_key is null or event_key = ''"
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
    rows = conn.execute("select task_id, action from llm_usage_events").fetchall()
    return sum(_semantic_task(str(row[0]), str(row[1])) == task for row in rows)


def _run_scheduled_median_rebuild(path: Path, ctx: RunContext, path_key: str) -> None:
    try:
        rebuild_usage_medians(
            LLMUsageMedianRebuildRequest(schema_version="1.0", db_path=str(path)),
            ctx,
        )
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
        select provider, task_id, action, model, prompt_namespace,
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
            _semantic_task(task_id, action),
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
    return LLMUsageMedianRebuildResponse(
        schema_version="1.0",
        db_path=str(source_db_path),
        median_db_path=str(median_db_path),
        median_row_count=len(grouped_usage),
    )


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
            rebuilt = _rebuild_usage_medians(conn, path, median_path)
    except AppError:
        raise
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
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
                    metadata_json
                ) values (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
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
                    _metadata_json(entry.metadata),
                ),
            )
            inserted = cursor.rowcount == 1
            row = conn.execute(
                "select id from llm_usage_events where event_key = ?", (event_key,)
            ).fetchone()
            row_id = int(row[0]) if row is not None else 0
            canonical_event_count = int(
                conn.execute("select count(*) from llm_usage_events").fetchone()[0]
            )
            median_task = _semantic_task(str(entry.task_id), entry.action)
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
        inserted
        and canonical_event_count % _USAGE_EXPORT_PROJECTION_INTERVAL == 0
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
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise AppError(
            code="llm_usage_ledger_outcome_update_failed",
            message=f"Failed to finalize LLM usage event in {path}",
            cause=exc,
            retryable=False,
            context={"db_path": str(path), "event_key": request.event_key},
        ) from exc
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
            },
        )
    )
    return LLMUsageLedgerOutcomeUpdateResponse(
        schema_version="1.0",
        db_path=str(path),
        event_key=request.event_key,
        updated=updated,
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
               error_stage, error_code, event_key, metadata_json
        from llm_usage_events where id > ? order by id
        """,
        (after_event_id,),
    ).fetchall()
    export_rows: list[dict[str, Any]] = []
    for row in rows:
        metadata = _safe_metadata(str(row[28]))
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
    rows: list[dict[str, Any]], *, db_path: Path, source_sha256: str, ledger_sha256: str
) -> dict[str, Any]:
    by_date = _rollup_metrics(rows, "date")
    by_run = _rollup_metrics(rows, "run_id")
    by_task = _rollup_metrics(rows, "task_id")
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
            "source_sha256": source_sha256,
            "ledger_sha256": ledger_sha256,
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
            "last_projected_event_id": last_projected_event_id,
            "source_sha256": source_sha256,
            "ledger_sha256": ledger_sha256,
        },
        "totals": dict(sorted(totals_by_date.items())),
        "totals_by_date": dict(sorted(totals_by_date.items())),
        "totals_by_run": dict(sorted(totals_by_run.items())),
        "totals_by_task": dict(sorted(totals_by_task.items())),
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
                       last_projected_event_id
                from llm_usage_export_checkpoints
                where ledger_path = ? and daily_path = ?
                """,
                (str(ledger_path.resolve()), str(daily_path.resolve())),
            ).fetchone()
            canonical_event_count, highest_event_id = conn.execute(
                "select count(*), coalesce(max(id), 0) from llm_usage_events"
            ).fetchone()
            baseline_required = (
                checkpoint is None
                or int(checkpoint[4]) == 0
                or not ledger_path.is_file()
                or not daily_path.is_file()
            )
            last_projected_event_id = 0 if baseline_required else int(checkpoint[4])
            rows = _canonical_export_rows(
                conn, after_event_id=last_projected_event_id
            )
        if not rows and not baseline_required:
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
            )
        existing_ledger = b"" if baseline_required else ledger_path.read_bytes()
        ledger_content = existing_ledger + b"".join(
            _stable_json_bytes(row) for row in rows
        )
        source_sha256 = sha256(ledger_content).hexdigest()
        ledger_sha256 = source_sha256
        if baseline_required:
            daily_payload = _daily_export_payload(
                rows,
                db_path=db_path,
                source_sha256=source_sha256,
                ledger_sha256=ledger_sha256,
            )
            daily_payload["ledger_state"]["event_count"] = int(
                canonical_event_count
            )
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
            )
        daily_content = _stable_json_bytes(daily_payload)
        daily_sha256 = sha256(daily_content).hexdigest()
        file_service.write_bytes(
            WriteBytesRequest(
                schema_version="1.0", path=str(ledger_path), content=ledger_content
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
            conn.execute(
                """
                insert into llm_usage_export_checkpoints (
                    ledger_path, daily_path, event_count, source_sha256,
                    ledger_sha256, daily_sha256, completed_at_utc,
                    last_projected_event_id
                ) values (?, ?, ?, ?, ?, ?, ?, ?)
                on conflict(ledger_path, daily_path) do update set
                    event_count = excluded.event_count,
                    source_sha256 = excluded.source_sha256,
                    ledger_sha256 = excluded.ledger_sha256,
                    daily_sha256 = excluded.daily_sha256,
                    completed_at_utc = excluded.completed_at_utc,
                    last_projected_event_id = excluded.last_projected_event_id
                """,
                (
                    str(ledger_path.resolve()),
                    str(daily_path.resolve()),
                    int(canonical_event_count),
                    source_sha256,
                    ledger_sha256,
                    daily_sha256,
                    max((str(row["timestamp_utc"]) for row in rows), default=""),
                    int(highest_event_id),
                ),
            )
    except (AppError, OSError, sqlite3.Error, TypeError, ValueError) as exc:
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
    matches = (
        tuple(int(value) for value in sqlite_totals[:4]) == export_totals[:4]
        and abs(float(sqlite_totals[4]) - export_totals[4]) <= 1e-9
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
            },
        )
    )
    return response
