from __future__ import annotations

import json
import logging
import sqlite3
import threading
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import median
from typing import Any

from src.contracts.llm_usage import (
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerAppendResponse,
    LLMUsageMedianRebuildRequest,
    LLMUsageMedianRebuildResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.llm_usage_ledger_service")
_LOCK = threading.Lock()


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
            metadata_json text not null
        )
        """
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
            cursor = conn.execute(
                """
                insert into llm_usage_events (
                    schema_version, timestamp_utc, provider, action,
                    run_id, task_id, span_id, trace_id, model, request_id,
                    publisher_name, report_name, source_url, input_tokens,
                    output_tokens, total_tokens, cached_input_tokens, tool_calls,
                    estimated_cost_usd, prompt_namespace, prompt_hash,
                    provider_decision, cache_decision, temperature, seed,
                    timeout_seconds, metadata_json
                ) values (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?
                )
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
                    _metadata_json(entry.metadata),
                ),
            )
            row_id = int(cursor.lastrowid or 0)
            median_result = _rebuild_usage_medians(conn, path, median_path)
    except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
        raise AppError(
            code="llm_usage_ledger_append_failed",
            message=f"Failed to append LLM usage record to {path}",
            cause=exc,
            retryable=False,
            context={"db_path": str(path), "provider": entry.provider},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_ledger_medians_rebuilt",
            module=logger.name,
            fields={
                "db_path": str(path),
                "median_db_path": median_result.median_db_path,
                "median_row_count": median_result.median_row_count,
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
                "median_db_path": median_result.median_db_path,
                "median_row_count": median_result.median_row_count,
                "row_id": row_id,
                "provider": entry.provider,
                "action": entry.action,
                "model": entry.model,
            },
        )
    )
    return LLMUsageLedgerAppendResponse(
        schema_version="1.0",
        db_path=str(path),
        row_id=row_id,
        median_db_path=median_result.median_db_path,
        median_row_count=median_result.median_row_count,
    )
