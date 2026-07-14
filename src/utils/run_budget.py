from __future__ import annotations

from src.contracts.workflow_control import RunBudget, RunBudgetDecision, RunBudgetUsage
from src.utils.errors import AppError


_METRICS = (
    ("spend_usd", "max_spend_usd"),
    ("tokens", "max_tokens"),
    ("runtime_seconds", "max_runtime_seconds"),
    ("retries", "max_retries"),
    ("browser_launches", "max_browser_launches"),
    ("drive_writes", "max_drive_writes"),
    ("wordpress_writes", "max_wordpress_writes"),
    ("pdfs", "max_pdfs"),
)


def evaluate_run_budget(
    budget: RunBudget,
    usage: RunBudgetUsage,
    *,
    override_actor: str = "",
    override_reason: str = "",
) -> RunBudgetDecision:
    """Make a deterministic pre-side-effect budget decision."""
    breached = [
        usage_name
        for usage_name, limit_name in _METRICS
        if getattr(budget, limit_name) is not None
        and getattr(usage, usage_name) >= getattr(budget, limit_name)
    ]
    if not breached:
        return RunBudgetDecision(
            schema_version="1.0", decision="allow", breached_metrics=[],
            side_effect_allowed=True, reason="within_budget"
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
            schema_version="1.0", decision="override", breached_metrics=breached,
            side_effect_allowed=True, reason="authorized_override",
            override_actor=actor, override_reason=reason,
        )
    return RunBudgetDecision(
        schema_version="1.0", decision="stop", breached_metrics=breached,
        side_effect_allowed=False, reason="budget_limit_reached",
    )
