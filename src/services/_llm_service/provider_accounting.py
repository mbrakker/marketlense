"""Provider failure accounting shared by canonical LLM adapters."""

from __future__ import annotations

import logging
from typing import Any

from src.contracts.run_context import RunContext
from src.services._llm_service.openai_usage_accounting import (
    record_usage_accounting,
)
from src.services._llm_service.provider_timing import ProviderCallTiming
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.llm_service.openai")


def record_failed_provider_call(
    *,
    ctx: RunContext,
    step_name: str,
    model: str,
    source_request: Any,
    provider_timing: ProviderCallTiming | None,
    error_code: str,
    retryable: bool,
) -> None:
    """Append one bounded failure row without masking the provider exception."""

    if provider_timing is None or provider_timing.provider_call_status != "failed":
        return
    try:
        record_usage_accounting(
            ctx=ctx,
            step_name=step_name,
            model=model,
            input_tokens=None,
            output_tokens=None,
            total_tokens=None,
            tool_calls=0,
            cost_ledger_path=str(
                getattr(source_request, "cost_ledger_path", "")
                or "./out/cost-ledger.jsonl"
            ),
            cost_daily_path=str(
                getattr(source_request, "cost_daily_path", "")
                or "./out/cost-daily.json"
            ),
            model_pricing=getattr(source_request, "model_pricing", None) or {},
            request_id=None,
            source_request=source_request,
            provider_timing=provider_timing,
            provider_call_status="failed",
            provider_error_code=error_code,
            provider_retryable=retryable,
            parse_status="not_applicable",
            schema_validation_status="not_applicable",
        )
    except Exception as exc:
        logger.warning(
            log_event(
                ctx,
                role="service",
                event="llm_provider_failure_accounting_failed",
                module=logger.name,
                fields={
                    "operation": provider_timing.operation,
                    "step_name": step_name,
                    "error_code": error_code,
                    "accounting_error_type": type(exc).__name__,
                },
            )
        )
