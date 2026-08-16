from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.contracts.run_budget import (
    RunBudget,
    RunBudgetEventAppendRequest,
    RunBudgetTaskUsageReadRequest,
    RunBudgetUsage,
    RunBudgetUsageReadRequest,
)
from src.contracts.run_context import RunContext
from src.services.llm_usage_ledger_service import (
    append_run_budget_side_effect,
    read_run_budget_task_usage,
    read_run_budget_usage,
)

if TYPE_CHECKING:
    from src.contracts.browser_download import ReportDownloadOrchestratorRequest


def build_report_download_budget(
    request: "ReportDownloadOrchestratorRequest", ctx: RunContext
) -> RunBudget | None:
    """Build the one configured acquisition budget shared by browser and Drive work."""
    if not request.settings.run_budget_enabled:
        return None
    return _configured_report_download_budget(request, ctx)


def build_report_download_telemetry_budget(
    request: "ReportDownloadOrchestratorRequest", ctx: RunContext
) -> RunBudget:
    """Build the configured ledger scope for mailbox attribution.

    Mailbox preflight is a real external read even when enforcement is disabled.
    It must therefore use the same durable run ledger as the rest of report
    acquisition instead of the mailbox service's fallback local ledger.
    """
    if request.settings.run_budget_enabled:
        return _configured_report_download_budget(request, ctx)
    return RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name=request.publisher_name,
        usage_db_path=request.settings.usage_db_path,
        day_utc=datetime.now(timezone.utc).date().isoformat(),
        policy_version=getattr(
            request.settings, "run_budget_policy_version", "budget-authority-v2"
        ),
        enabled_effect_kinds=("mailbox_read",),
    )


def _configured_report_download_budget(
    request: "ReportDownloadOrchestratorRequest", ctx: RunContext
) -> RunBudget:
    """Build the configured enforced budget for one report-acquisition run."""
    settings = request.settings
    return RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name=request.publisher_name,
        usage_db_path=settings.usage_db_path,
        day_utc=datetime.now(timezone.utc).date().isoformat(),
        max_spend_usd=settings.daily_spend_stop_usd,
        max_browser_launches=settings.run_budget_max_browser_launches,
        max_pdfs=settings.run_budget_max_pdfs,
        max_drive_writes=settings.run_budget_max_drive_writes,
        max_drive_reads=getattr(settings, "run_budget_max_drive_reads", None),
        max_mailbox_reads=getattr(settings, "run_budget_max_mailbox_reads", None),
        max_retries=getattr(settings, "run_budget_max_retries", None),
        max_runtime_seconds=getattr(settings, "run_budget_max_runtime_seconds", None),
        limit_decision=settings.run_budget_limit_decision,
        policy_version=getattr(
            settings, "run_budget_policy_version", "budget-authority-v2"
        ),
        reservation_ttl_seconds=getattr(
            settings, "run_budget_reservation_ttl_seconds", 300
        ),
        run_limits=getattr(settings, "run_budget_limits_run", None),
        day_limits=getattr(settings, "run_budget_limits_day", None),
        publisher_limits=getattr(settings, "run_budget_limits_publisher", None),
        enabled_effect_kinds=getattr(settings, "run_budget_enabled_effect_kinds", ()),
    )


def read_report_download_budget_usage(
    budget: RunBudget | None, ctx: RunContext
) -> RunBudgetUsage | None:
    """Read the latest canonical usage before an acquisition side effect."""
    if budget is None:
        return None
    return read_run_budget_usage(
        RunBudgetUsageReadRequest(schema_version="1.0", budget=budget), ctx
    ).usage


def read_report_download_run_usage(
    *,
    request: "ReportDownloadOrchestratorRequest",
    ctx: RunContext,
) -> RunBudgetUsage:
    """Read the exact run scope for telemetry without enabling budget enforcement."""
    settings = request.settings
    budget = RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name=request.publisher_name,
        usage_db_path=settings.usage_db_path,
        day_utc=datetime.now(timezone.utc).date().isoformat(),
        policy_version=getattr(
            settings, "run_budget_policy_version", "budget-authority-v2"
        ),
    )
    return read_run_budget_usage(
        RunBudgetUsageReadRequest(schema_version="1.0", budget=budget), ctx
    ).run_usage


def read_report_download_task_usage(
    *,
    request: "ReportDownloadOrchestratorRequest",
    ctx: RunContext,
) -> RunBudgetUsage:
    """Read actual acquisition usage from the canonical ledger by task scope."""
    return read_run_budget_task_usage(
        RunBudgetTaskUsageReadRequest(
            schema_version="1.0",
            budget=build_report_download_telemetry_budget(request, ctx),
            task_id=ctx.task_id,
        ),
        ctx,
    ).usage


def record_report_download_budget_event(
    *,
    budget: RunBudget | None,
    event_key: str,
    metric: str,
    ctx: RunContext,
) -> None:
    """Idempotently record one completed acquisition side effect."""
    if budget is None:
        return
    append_run_budget_side_effect(
        RunBudgetEventAppendRequest(
            schema_version="1.0",
            budget=budget,
            event_key=event_key,
            metric=metric,
            decision="allow",
        ),
        ctx,
    )
