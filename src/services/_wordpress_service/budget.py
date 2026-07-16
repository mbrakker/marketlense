"""Canonical pre-write budget gate shared by WordPress service modules."""

from __future__ import annotations

from typing import Any

from src.contracts.run_budget import BudgetRequest, RunBudget
from src.contracts.run_context import RunContext
from src.services.llm_usage_ledger_service import evaluate_budget_request
from src.utils.errors import AppError


def assert_wordpress_write_authority(
    request: Any,
    ctx: RunContext,
    *,
    operation: str,
    estimated_writes: int = 1,
) -> None:
    """Obtain a typed decision before a WordPress mutation can be attempted."""
    budget = getattr(request, "run_budget", None) or RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name="",
    )
    authority = evaluate_budget_request(
        BudgetRequest(
            schema_version="1.0",
            budget=budget,
            run_id=ctx.run_id,
            workflow_id="publishing",
            publisher_id=budget.publisher_name,
            report_id=str(getattr(request, "post_id", "") or ""),
            resource_type="wordpress_write",
            operation=f"wordpress_{operation}",
            estimated_writes=max(1, estimated_writes),
            idempotency_key=f"wordpress:{operation}:{ctx.run_id}:{ctx.task_id}:{ctx.span_id}",
        ),
        ctx,
    )
    if authority.decision in {"defer", "pause", "stop"}:
        raise AppError(
            code=f"wordpress_{operation}_budget_{authority.decision}",
            message="WordPress write was blocked by the canonical budget authority",
            retryable=authority.decision in {"defer", "pause"},
            context={
                "reason_code": authority.reason_code,
                "affected_limit": authority.affected_limit,
            },
        )
