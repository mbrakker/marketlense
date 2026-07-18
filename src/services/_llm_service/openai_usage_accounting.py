"""Canonical OpenAI usage-accounting persistence for the LLM service boundary."""

from __future__ import annotations

from typing import Any

from src.contracts.openai import (
    OpenAIUsageAccountingRequest,
    OpenAIUsageAccountingResponse,
    OpenAIUsageOutcomeUpdateRequest,
)
from src.contracts.run_context import RunContext
from src.services import openai_accounting_service


def _semantic_usage_action(*, step_name: str, source_request: Any | None) -> str:
    prompt_namespace = str(
        getattr(source_request, "prompt_namespace", "") or ""
    ).strip()
    if not prompt_namespace:
        return step_name
    namespace_parts = [part for part in prompt_namespace.split("/") if part]
    if namespace_parts[:1] == ["report_vs"]:
        namespace_parts = namespace_parts[1:]
    return ":".join(namespace_parts) or step_name


def record_usage_accounting(
    *,
    ctx: RunContext,
    step_name: str,
    model: str,
    input_tokens: int | None,
    output_tokens: int | None,
    tool_calls: int,
    cost_ledger_path: str,
    cost_daily_path: str,
    model_pricing: dict,
    request_id: str | None,
    cached_input_tokens: int | None = None,
    provider: str = "openai",
    action: str | None = None,
    reservation_operation: str = "",
    total_tokens: int | None = None,
    source_request: Any | None = None,
    call_ordinal: int = 0,
    parse_status: str = "not_applicable",
    schema_validation_status: str = "not_applicable",
) -> OpenAIUsageAccountingResponse:
    source = source_request
    cache_decision = ""
    if source is not None and hasattr(source, "response_cache_enabled"):
        cache_decision = (
            "enabled"
            if bool(getattr(source, "response_cache_enabled", False))
            else "disabled"
        )
    if int(cached_input_tokens or 0) > 0:
        cache_decision = "provider_hit"
    return openai_accounting_service.record_usage(
        OpenAIUsageAccountingRequest(
            schema_version="1.0",
            step_name=step_name,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
            cached_input_tokens=cached_input_tokens,
            tool_calls=int(tool_calls or 0),
            cost_ledger_path=cost_ledger_path,
            cost_daily_path=cost_daily_path,
            model_pricing=model_pricing or {},
            request_id=request_id,
            provider=provider,
            action=action
            or _semantic_usage_action(step_name=step_name, source_request=source),
            reservation_operation=reservation_operation or step_name,
            usage_db_path=str(
                getattr(source, "usage_db_path", "") or "./state/llm_usage.sqlite"
            ),
            publisher_name=str(
                getattr(source, "publisher_name", "")
                or getattr(source, "publisher", "")
                or ""
            ),
            report_name=str(
                getattr(source, "report_name", "")
                or getattr(source, "report_title", "")
                or getattr(source, "title", "")
                or ""
            ),
            report_id=str(getattr(source, "report_id", "") or ""),
            source_url=str(
                getattr(source, "source_url", "")
                or getattr(source, "landing_page_url", "")
                or getattr(source, "url", "")
                or ""
            ),
            prompt_namespace=str(getattr(source, "prompt_namespace", "") or ""),
            prompt_hash=str(
                getattr(source, "prompt_hash", "")
                or getattr(source, "prompt_sha256", "")
                or getattr(source, "prompt_user_sha256", "")
                or ""
            ),
            provider_decision=str(
                getattr(source, "provider_decision", "") or "openai_primary"
            ),
            cache_decision=cache_decision,
            temperature=getattr(source, "temperature", None),
            seed=getattr(source, "seed", None),
            timeout_seconds=getattr(source, "timeout_seconds", None),
            call_ordinal=call_ordinal,
            parse_status=parse_status,
            schema_validation_status=schema_validation_status,
            workflow=str(getattr(source, "workflow", "") or ""),
            stage=str(getattr(source, "stage", "") or ""),
            plan_hash=str(getattr(source, "plan_hash", "") or ""),
            artifact_family=str(getattr(source, "artifact_family", "") or ""),
            extra={
                "schema_name": str(getattr(source, "schema_name", "") or ""),
                "response_cache_dir": str(
                    getattr(source, "response_cache_dir", "") or ""
                ),
                "workflow": str(getattr(source, "workflow", "") or ""),
                "stage": str(getattr(source, "stage", "") or ""),
                "plan_hash": str(getattr(source, "plan_hash", "") or ""),
                "artifact_family": str(getattr(source, "artifact_family", "") or ""),
            },
        ),
        ctx,
    )


def finalize_usage_accounting(
    *,
    accounting: OpenAIUsageAccountingResponse,
    ctx: RunContext,
    parse_status: str,
    schema_validation_status: str,
    error_stage: str = "",
    error_code: str = "",
) -> None:
    if not accounting.usage_db_recorded or not accounting.event_key:
        return
    openai_accounting_service.update_usage_outcome(
        OpenAIUsageOutcomeUpdateRequest(
            schema_version="1.0",
            usage_db_path=accounting.usage_db_path,
            event_key=accounting.event_key,
            parse_status=parse_status,
            schema_validation_status=schema_validation_status,
            error_stage=error_stage,
            error_code=error_code,
            cost_ledger_path=accounting.ledger_path,
            cost_daily_path=accounting.daily_path,
        ),
        ctx,
    )
