"""Canonical budget context for final WordPress publication side effects."""

from datetime import datetime, timezone

from src.contracts.publish import PublishSettings
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
from src.utils.errors import AppError


def build_publish_budget(
    settings: PublishSettings, ctx: RunContext
) -> RunBudget | None:
    """Build the canonical budget for final WordPress publication writes."""
    if not settings.run_budget_enabled or not settings.usage_db_path:
        return None
    return RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name="",
        usage_db_path=settings.usage_db_path,
        projection_ledger_path=settings.projection_ledger_path,
        projection_daily_path=settings.projection_daily_path,
        projection_pending_event_threshold=settings.projection_pending_event_threshold,
        day_utc=datetime.now(timezone.utc).date().isoformat(),
        max_wordpress_writes=settings.run_budget_max_wordpress_writes,
        limit_decision=settings.run_budget_limit_decision,
    )


def read_publish_budget_usage(
    budget: RunBudget | None, ctx: RunContext
) -> RunBudgetUsage | None:
    """Read release-ready canonical usage before a final publication write.

    The SQLite ledger remains authoritative for the numbers.  Derived exports are
    nevertheless release evidence: a missing, invalid, or materially stale
    projection must stop a public write rather than being silently discarded.
    """
    if budget is None:
        return None
    response = read_run_budget_usage(
        RunBudgetUsageReadRequest(schema_version="1.0", budget=budget), ctx
    )
    if response.projection_outcome not in {
        "not_configured",
        "current",
        "bounded_lag_accounted",
    }:
        raise AppError(
            code="publish_budget_projection_not_release_ready",
            message=(
                "Final publication requires current or bounded canonical LLM "
                "projection evidence"
            ),
            retryable=False,
            context={
                "projection_outcome": response.projection_outcome,
                "pending_event_count": response.projection_pending_event_count,
                "pending_estimated_cost_usd": (
                    response.projection_pending_estimated_cost_usd
                ),
            },
        )
    return response.usage


def record_publish_budget_write(
    budget: RunBudget | None, *, event_key: str, ctx: RunContext
) -> None:
    """Idempotently record one completed final WordPress publication write."""
    if budget is None:
        return
    append_run_budget_side_effect(
        RunBudgetEventAppendRequest(
            schema_version="1.0",
            budget=budget,
            event_key=event_key,
            metric="wordpress_writes",
            decision="allow",
        ),
        ctx,
    )
