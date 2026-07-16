from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from hashlib import sha256

from src.contracts.llm_usage import (
    LLMUsageExportRebuildRequest,
    LLMUsageLedgerAppendRequest,
    LLMUsageLedgerEntry,
    LLMUsageLedgerOutcomeUpdateRequest,
    LLMUsageProjectionStatusRequest,
    LLMUsageSpendReservationReleaseRequest,
)
from src.contracts.openai import (
    OpenAIUsageAccountingRequest,
    OpenAIUsageAccountingResponse,
    OpenAIUsageOutcomeUpdateRequest,
)
from src.contracts.run_budget import BudgetReservationReconcileRequest
from src.contracts.run_context import RunContext
from src.services import llm_usage_ledger_service
from src.services._llm_service.policy import spend_reservation_key
from src.utils.costing import estimate_cost_usd, resolve_model_pricing
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


def _usage_metadata(
    request: OpenAIUsageAccountingRequest,
    *,
    pricing_status: str,
    pricing_key: str,
    pricing_version: str,
    pricing_rates: dict[str, float],
) -> dict:
    metadata = {
        "cost_ledger_path": request.cost_ledger_path,
        "cost_daily_path": request.cost_daily_path,
        "request_id": str(request.request_id) if request.request_id else None,
        "pricing_status": pricing_status,
        "pricing_key": pricing_key,
        "pricing_version": pricing_version,
        "pricing_rates": pricing_rates,
        "pricing_file_sha256": sha256(
            json.dumps(request.model_pricing or {}, sort_keys=True).encode("utf-8")
        ).hexdigest(),
        "emit_cost_ledger": request.emit_cost_ledger,
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
    pricing_resolution = resolve_model_pricing(request.model, request.model_pricing)
    pricing_version = str(
        (request.extra or {}).get("pricing_version")
        or request.model_pricing.get("schema_version", "")
    )
    estimated_cost = estimate_cost_usd(
        request.model,
        input_tokens,
        output_tokens,
        tool_calls,
        pricing=request.model_pricing or {},
    )
    if pricing_resolution.status in {"missing", "invalid"}:
        logger.warning(
            log_event(
                ctx,
                role="service",
                event="openai_usage_pricing_unresolved",
                module=logger.name,
                fields={
                    "provider": request.provider,
                    "model": request.model,
                    "pricing_status": pricing_resolution.status,
                    "pricing_key": pricing_resolution.key,
                    "pricing_version": pricing_version,
                },
            )
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
    usage_db_event_key = ""
    usage_db_inserted = False
    usage_exports_projected = False
    try:
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
                    call_ordinal=request.call_ordinal,
                    provider_call_status=request.provider_call_status,
                    parse_status=request.parse_status,
                    schema_validation_status=request.schema_validation_status,
                    error_stage=request.error_stage,
                    error_code=request.error_code,
                    metadata=_usage_metadata(
                        request,
                        pricing_status=pricing_resolution.status,
                        pricing_key=pricing_resolution.key,
                        pricing_version=pricing_version,
                        pricing_rates=pricing_resolution.rates,
                    ),
                ),
            ),
            ctx,
        )
        usage_db_recorded = True
        usage_db_row_id = usage_response.row_id
        usage_db_event_key = usage_response.event_key
        usage_db_inserted = usage_response.inserted
        llm_usage_ledger_service.release_daily_spend_reservation(
            LLMUsageSpendReservationReleaseRequest(
                schema_version="1.0",
                db_path=request.usage_db_path,
                reservation_key=spend_reservation_key(
                    ctx,
                    provider=request.provider,
                    operation=request.reservation_operation or action,
                ),
            ),
            ctx,
        )
        llm_usage_ledger_service.reconcile_budget_reservation(
            BudgetReservationReconcileRequest(
                schema_version="1.0",
                usage_db_path=request.usage_db_path,
                reservation_key=spend_reservation_key(
                    ctx,
                    provider=request.provider,
                    operation=request.reservation_operation or action,
                ),
                actual_cost_usd=estimated_cost,
            ),
            ctx,
        )
        if (
            request.emit_cost_ledger
            and usage_response.inserted
            and usage_response.export_projection_due
        ):
            llm_usage_ledger_service.rebuild_usage_exports(
                LLMUsageExportRebuildRequest(
                    schema_version="1.0",
                    db_path=request.usage_db_path,
                    ledger_path=request.cost_ledger_path,
                    daily_path=request.cost_daily_path,
                ),
                ctx,
            )
            usage_exports_projected = True
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
            event_key=usage_db_event_key,
            usage_db_inserted=usage_db_inserted,
            call_ordinal=None,
            pricing_status=pricing_resolution.status,
            pricing_key=pricing_resolution.key,
            pricing_version=pricing_version,
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
                "event_key": usage_db_event_key,
                "usage_db_inserted": usage_db_inserted,
                "usage_exports_projected": usage_exports_projected,
                "call_ordinal": usage_response.call_ordinal,
                "pricing_status": pricing_resolution.status,
                "pricing_key": pricing_resolution.key,
                "pricing_version": pricing_version,
            },
        )
    )
    return OpenAIUsageAccountingResponse(
        schema_version="1.0",
        recorded=usage_exports_projected,
        estimated_cost_usd=estimated_cost,
        ledger_path=request.cost_ledger_path,
        daily_path=request.cost_daily_path,
        usage_db_path=request.usage_db_path,
        usage_db_recorded=usage_db_recorded,
        usage_db_row_id=usage_db_row_id,
        event_key=usage_db_event_key,
        usage_db_inserted=usage_db_inserted,
        call_ordinal=usage_response.call_ordinal,
        pricing_status=pricing_resolution.status,
        pricing_key=pricing_resolution.key,
        pricing_version=pricing_version,
    )


def update_usage_outcome(
    request: OpenAIUsageOutcomeUpdateRequest, ctx: RunContext
) -> bool:
    response = llm_usage_ledger_service.update_usage_outcome(
        LLMUsageLedgerOutcomeUpdateRequest(
            schema_version=request.schema_version,
            db_path=request.usage_db_path,
            event_key=request.event_key,
            parse_status=request.parse_status,
            schema_validation_status=request.schema_validation_status,
            error_stage=request.error_stage,
            error_code=request.error_code,
        ),
        ctx,
    )
    if response.updated and request.cost_ledger_path and request.cost_daily_path:
        try:
            llm_usage_ledger_service.finalize_usage_projection(
                LLMUsageProjectionStatusRequest(
                    schema_version="1.0",
                    db_path=request.usage_db_path,
                    ledger_path=request.cost_ledger_path,
                    daily_path=request.cost_daily_path,
                ),
                ctx,
            )
        except OPENAI_ACCOUNTING_EXCEPTIONS as exc:
            logger.warning(
                log_event(
                    ctx,
                    role="service",
                    event="openai_usage_projection_finalize_failed",
                    module=logger.name,
                    fields={"event_key": request.event_key, "error": str(exc)},
                )
            )
    return response.updated
