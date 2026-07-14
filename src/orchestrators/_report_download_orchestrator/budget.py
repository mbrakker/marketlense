from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING

from src.contracts.run_budget import (
    RunBudget,
    RunBudgetEventAppendRequest,
    RunBudgetUsage,
    RunBudgetUsageReadRequest,
)
from src.contracts.run_context import RunContext
from src.services.llm_usage_ledger_service import (
    append_run_budget_side_effect,
    read_run_budget_usage,
)

if TYPE_CHECKING:
    from src.contracts.browser_download import ReportDownloadOrchestratorRequest


def build_report_download_budget(
    request: "ReportDownloadOrchestratorRequest", ctx: RunContext
) -> RunBudget | None:
    """Build the one configured acquisition budget shared by browser and Drive work."""
    settings = request.settings
    if not settings.run_budget_enabled:
        return None
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
        limit_decision=settings.run_budget_limit_decision,
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
