from __future__ import annotations

from dataclasses import replace

from src.contracts.run_budget import RunBudget, RunBudgetDecision, RunBudgetUsage
from src.utils.errors import AppError


_METRICS = (
    ("spend_usd", "max_spend_usd"),
    ("tokens", "max_tokens"),
    ("calls", "max_calls"),
    ("steps", "max_steps"),
    ("runtime_seconds", "max_runtime_seconds"),
    ("retries", "max_retries"),
    ("browser_launches", "max_browser_launches"),
    ("drive_writes", "max_drive_writes"),
    ("drive_reads", "max_drive_reads"),
    ("wordpress_writes", "max_wordpress_writes"),
    ("pdfs", "max_pdfs"),
    ("mailbox_reads", "max_mailbox_reads"),
)


def evaluate_run_budget(
    budget: RunBudget,
    usage: RunBudgetUsage,
    *,
    override_actor: str = "",
    override_reason: str = "",
) -> RunBudgetDecision:
    """Make a deterministic pre-side-effect budget decision."""
    limit_decision = str(budget.limit_decision or "stop").strip().lower()
    if limit_decision not in {"pause", "defer", "stop"}:
        raise AppError(
            code="run_budget_limit_decision_invalid",
            message="Run-budget limit decision must be pause, defer, or stop",
            retryable=False,
            context={"limit_decision": budget.limit_decision},
        )
    breached = [
        usage_name
        for usage_name, limit_name in _METRICS
        if getattr(budget, limit_name) is not None
        # The caller supplies prospective usage, so equality consumes the
        # final permitted unit; only a value beyond the maximum is blocked.
        and getattr(usage, usage_name) > getattr(budget, limit_name)
    ]
    if not breached:
        return RunBudgetDecision(
            schema_version="1.0",
            decision=_warning_decision(budget, usage),
            breached_metrics=_warning_metrics(budget, usage),
            side_effect_allowed=True,
            reason=(
                "budget_warning" if _warning_metrics(budget, usage) else "within_budget"
            ),
        )
    actor = str(override_actor or "").strip()
    reason = str(override_reason or "").strip()
    if bool(actor) != bool(reason):
        raise AppError(
            code="run_budget_override_audit_missing",
            message="Budget overrides require both actor and reason",
            retryable=False,
            context={"breached_metrics": breached},
        )
    if actor:
        return RunBudgetDecision(
            schema_version="1.0",
            decision="override",
            breached_metrics=breached,
            side_effect_allowed=True,
            reason="authorized_override",
            override_actor=actor,
            override_reason=reason,
        )
    return RunBudgetDecision(
        schema_version="1.0",
        decision=limit_decision,
        breached_metrics=breached,
        side_effect_allowed=False,
        reason="budget_limit_reached",
    )


def proposed_run_budget_usage(
    usage: RunBudgetUsage | None, *, metric: str
) -> RunBudgetUsage:
    """Return usage including exactly one prospective external side effect."""
    if metric not in {name for name, _ in _METRICS}:
        raise AppError(
            code="run_budget_metric_invalid",
            message="Run-budget proposal uses an unsupported metric",
            retryable=False,
            context={"metric": metric},
        )
    current = usage or RunBudgetUsage(schema_version="1.0")
    return replace(current, **{metric: getattr(current, metric) + 1})


def evaluate_proposed_side_effect_budget(
    budget: RunBudget | None,
    usage: RunBudgetUsage | None,
    *,
    metric: str,
    override_actor: str = "",
    override_reason: str = "",
) -> RunBudgetDecision | None:
    """Evaluate one prospective side effect without silently treating it as free."""
    if budget is None:
        return None
    proposed = proposed_run_budget_usage(usage, metric=metric)
    return replace(
        evaluate_run_budget(
            budget,
            proposed,
            override_actor=override_actor,
            override_reason=override_reason,
        ),
        proposed_usage=proposed,
    )


def _warning_metrics(budget: RunBudget, usage: RunBudgetUsage) -> list[str]:
    warning_fraction = float(budget.warning_fraction)
    if warning_fraction <= 0 or warning_fraction >= 1:
        return []
    return [
        usage_name
        for usage_name, limit_name in _METRICS
        if getattr(budget, limit_name) is not None
        and getattr(usage, usage_name) >= getattr(budget, limit_name) * warning_fraction
    ]


def _warning_decision(budget: RunBudget, usage: RunBudgetUsage) -> str:
    return "warn" if _warning_metrics(budget, usage) else "allow"
