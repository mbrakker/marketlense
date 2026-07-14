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


def build_publish_budget(settings: PublishSettings, ctx: RunContext) -> RunBudget | None:
    """Build the canonical budget for final WordPress publication writes."""
    if not settings.run_budget_enabled or not settings.usage_db_path:
        return None
    return RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name="",
        usage_db_path=settings.usage_db_path,
        day_utc=datetime.now(timezone.utc).date().isoformat(),
        max_wordpress_writes=settings.run_budget_max_wordpress_writes,
        limit_decision=settings.run_budget_limit_decision,
    )


def read_publish_budget_usage(
    budget: RunBudget | None, ctx: RunContext
) -> RunBudgetUsage | None:
    """Read the current canonical usage before a final publication write."""
    if budget is None:
        return None
    return read_run_budget_usage(
        RunBudgetUsageReadRequest(schema_version="1.0", budget=budget), ctx
    ).usage


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
