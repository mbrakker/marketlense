from __future__ import annotations

import logging
from datetime import datetime, timezone

from src.contracts.costs import (
    CostLedgerAppendRequest,
    CostLedgerEntry,
    CostRollupRequest,
)
from src.contracts.openai import (
    OpenAIUsageAccountingRequest,
    OpenAIUsageAccountingResponse,
)
from src.contracts.run_context import RunContext
from src.services import cost_ledger_service
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
    if not request.cost_ledger_path.strip() or not request.cost_daily_path.strip():
        raise AppError(
            code="openai_accounting_path_missing",
            message="OpenAI accounting ledger and daily paths are required",
            retryable=False,
        )


def record_usage(
    request: OpenAIUsageAccountingRequest, ctx: RunContext
) -> OpenAIUsageAccountingResponse:
    _validate_request(request)
    input_tokens = int(request.input_tokens or 0)
    output_tokens = int(request.output_tokens or 0)
    tool_calls = int(request.tool_calls or 0)
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
                "step_name": request.step_name,
                "model": request.model,
                "request_id": request.request_id or "",
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "tool_calls": tool_calls,
                "cost_ledger_path": request.cost_ledger_path,
                "cost_daily_path": request.cost_daily_path,
            },
        )
    )
    try:
        entry = CostLedgerEntry(
            schema_version="1.0",
            timestamp_utc=datetime.now(timezone.utc).isoformat(),
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
            extra={
                "request_id": str(request.request_id) if request.request_id else None
            },
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
    except OPENAI_ACCOUNTING_EXCEPTIONS as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="openai_usage_accounting_failed",
                module=logger.name,
                fields={
                    "step_name": request.step_name,
                    "model": request.model,
                    "request_id": request.request_id or "",
                    "error": str(exc),
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
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="openai_usage_accounting_complete",
            module=logger.name,
            fields={
                "step_name": request.step_name,
                "model": request.model,
                "request_id": request.request_id or "",
                "estimated_cost_usd": estimated_cost,
                "cost_ledger_path": request.cost_ledger_path,
                "cost_daily_path": request.cost_daily_path,
            },
        )
    )
    return OpenAIUsageAccountingResponse(
        schema_version="1.0",
        recorded=True,
        estimated_cost_usd=estimated_cost,
        ledger_path=request.cost_ledger_path,
        daily_path=request.cost_daily_path,
    )
