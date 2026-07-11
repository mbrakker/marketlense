from __future__ import annotations

import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

from src.contracts.llm_usage import (
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerAppendResponse,
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


def append_usage(
    request: LLMUsageLedgerAppendRequest, ctx: RunContext
) -> LLMUsageLedgerAppendResponse:
    _validate_request(request)
    path = Path(request.db_path)
    entry = request.entry
    logger.info(
        log_event(
            ctx,
            role="service",
            event="llm_usage_ledger_append_start",
            module=logger.name,
            fields={
                "db_path": str(path),
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
            event="llm_usage_ledger_append_complete",
            module=logger.name,
            fields={
                "db_path": str(path),
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
    )
