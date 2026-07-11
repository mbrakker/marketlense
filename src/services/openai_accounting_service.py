from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.contracts.costs import (
    CostLedgerAppendRequest,
    CostLedgerEntry,
    CostRollupRequest,
)
from src.contracts.llm_usage import (
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerEntry,
)
from src.contracts.openai import (
    OpenAIUsageAccountingRequest,
    OpenAIUsageAccountingResponse,
)
from src.contracts.run_context import RunContext
from src.services import cost_ledger_service, llm_usage_ledger_service
from src.utils.costing import estimate_cost_usd
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.openai_accounting_service")

OPENAI_ACCOUNTING_EXCEPTIONS: tuple[type[Exception], ...] = (
    AppError,
    OSError,
    ValueError,
    TypeError,
)


def _validate_request(request: OpenAIUsageAccountingRequest) -> None:
    if request.schema_version != "1.0":
        raise AppError(
            code="openai_accounting_schema_version_invalid",
            message="OpenAI accounting request schema version is unsupported",
            retryable=False,
            context={"schema_version": request.schema_version},
        )
    if not request.step_name.strip():
        raise AppError(
            code="openai_accounting_step_name_missing",
            message="OpenAI accounting step name is required",
            retryable=False,
        )
    if not request.model.strip():
        raise AppError(
            code="openai_accounting_model_missing",
            message="OpenAI accounting model is required",
            retryable=False,
        )
    if not request.provider.strip():
        raise AppError(
            code="openai_accounting_provider_missing",
            message="Provider is required for LLM usage accounting",
            retryable=False,
        )
    if not request.cost_ledger_path.strip() or not request.cost_daily_path.strip():
        raise AppError(
            code="openai_accounting_path_missing",
            message="OpenAI accounting ledger and daily paths are required",
            retryable=False,
        )
    if not request.usage_db_path.strip():
        raise AppError(
            code="openai_accounting_usage_db_path_missing",
            message="LLM usage database path is required",
            retryable=False,
        )


def _usage_total_tokens(
    *, input_tokens: int, output_tokens: int, total_tokens: int | None
) -> int:
    if total_tokens is not None:
        return int(total_tokens or 0)
    return int(input_tokens or 0) + int(output_tokens or 0)


def _cost_entry_extra(request: OpenAIUsageAccountingRequest) -> dict:
    return {
        "request_id": str(request.request_id) if request.request_id else None,
        "provider": request.provider,
        "action": request.action or request.step_name,
        "publisher_name": request.publisher_name or None,
        "report_name": request.report_name or None,
        "source_url": request.source_url or None,
        "prompt_namespace": request.prompt_namespace or None,
        "prompt_hash": request.prompt_hash or None,
        "provider_decision": request.provider_decision or None,
        "cache_decision": request.cache_decision or None,
    }


def _usage_metadata(request: OpenAIUsageAccountingRequest) -> dict:
    metadata = {
        "cost_ledger_path": request.cost_ledger_path,
        "cost_daily_path": request.cost_daily_path,
        "request_id": str(request.request_id) if request.request_id else None,
    }
    metadata.update(request.extra or {})
    return metadata


def record_usage(
    request: OpenAIUsageAccountingRequest, ctx: RunContext
) -> OpenAIUsageAccountingResponse:
    _validate_request(request)
    input_tokens = int(request.input_tokens or 0)
    output_tokens = int(request.output_tokens or 0)
    tool_calls = int(request.tool_calls or 0)
    total_tokens = _usage_total_tokens(
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=request.total_tokens,
    )
    action = request.action or request.step_name
    estimated_cost = estimate_cost_usd(
        request.model,
        input_tokens,
        output_tokens,
        tool_calls,
        pricing=request.model_pricing or {},
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_usage_accounting_start",
            module=logger.name,
            fields={
                "provider": request.provider,
                "action": action,
                "step_name": request.step_name,
                "model": request.model,
                "request_id": request.request_id or "",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "tool_calls": tool_calls,
                "cost_ledger_path": request.cost_ledger_path,
                "cost_daily_path": request.cost_daily_path,
                "usage_db_path": request.usage_db_path,
                "publisher_name": request.publisher_name,
            },
        )
    )
    timestamp_utc = datetime.now(timezone.utc).isoformat()
    usage_db_recorded = False
    usage_db_row_id = None
    try:
        if request.emit_cost_ledger:
            entry = CostLedgerEntry(
                schema_version="1.0",
                timestamp_utc=timestamp_utc,
                run_id=ctx.run_id,
                task_id=ctx.task_id,
                span_id=ctx.span_id,
                step_name=request.step_name,
                model=request.model,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cached_input_tokens=request.cached_input_tokens,
                tool_calls=tool_calls,
                estimated_cost_usd=estimated_cost,
                extra=_cost_entry_extra(request),
            )
            cost_ledger_service.append_entry(
                CostLedgerAppendRequest(
                    schema_version="1.0",
                    path=request.cost_ledger_path,
                    entry=entry,
                ),
                ctx,
            )
            cost_ledger_service.rollup_daily(
                CostRollupRequest(
                    schema_version="1.0",
                    ledger_path=request.cost_ledger_path,
                    out_path=request.cost_daily_path,
                ),
                ctx,
            )
        usage_response = llm_usage_ledger_service.append_usage(
            LLMUsageLedgerAppendRequest(
                schema_version="1.0",
                db_path=request.usage_db_path,
                entry=LLMUsageLedgerEntry(
                    schema_version="1.0",
                    timestamp_utc=timestamp_utc,
                    provider=request.provider,
                    action=action,
                    run_id=ctx.run_id,
                    task_id=ctx.task_id,
                    span_id=ctx.span_id,
                    trace_id=ctx.trace_id,
                    model=request.model,
                    request_id=request.request_id,
                    publisher_name=request.publisher_name,
                    report_name=request.report_name,
                    source_url=request.source_url,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    total_tokens=total_tokens,
                    cached_input_tokens=request.cached_input_tokens,
                    tool_calls=tool_calls,
                    estimated_cost_usd=estimated_cost,
                    prompt_namespace=request.prompt_namespace,
                    prompt_hash=request.prompt_hash,
                    provider_decision=(
                        request.provider_decision or f"{request.provider}_direct"
                    ),
                    cache_decision=request.cache_decision,
                    temperature=request.temperature,
                    seed=request.seed,
                    timeout_seconds=request.timeout_seconds,
                    metadata=_usage_metadata(request),
                ),
            ),
            ctx,
        )
        usage_db_recorded = True
        usage_db_row_id = usage_response.row_id
    except OPENAI_ACCOUNTING_EXCEPTIONS as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="openai_usage_accounting_failed",
                module=logger.name,
                fields={
                    "provider": request.provider,
                    "action": action,
                    "step_name": request.step_name,
                    "model": request.model,
                    "request_id": request.request_id or "",
                    "error": str(exc),
                    "usage_db_recorded": usage_db_recorded,
                },
            )
        )
        return OpenAIUsageAccountingResponse(
            schema_version="1.0",
            recorded=False,
            estimated_cost_usd=estimated_cost,
            ledger_path=request.cost_ledger_path,
            daily_path=request.cost_daily_path,
            error=str(exc),
            usage_db_path=request.usage_db_path,
            usage_db_recorded=usage_db_recorded,
            usage_db_row_id=usage_db_row_id,
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_usage_accounting_complete",
            module=logger.name,
            fields={
                "provider": request.provider,
                "action": action,
                "step_name": request.step_name,
                "model": request.model,
                "request_id": request.request_id or "",
                "estimated_cost_usd": estimated_cost,
                "cost_ledger_path": request.cost_ledger_path,
                "cost_daily_path": request.cost_daily_path,
                "usage_db_path": request.usage_db_path,
                "usage_db_row_id": usage_db_row_id,
            },
        )
    )
    return OpenAIUsageAccountingResponse(
        schema_version="1.0",
        recorded=request.emit_cost_ledger,
        estimated_cost_usd=estimated_cost,
        ledger_path=request.cost_ledger_path,
        daily_path=request.cost_daily_path,
        usage_db_path=request.usage_db_path,
        usage_db_recorded=usage_db_recorded,
        usage_db_row_id=usage_db_row_id,
    )
