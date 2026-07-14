from __future__ import annotations

import pytest

from src.contracts.workflow_control import RunBudget, RunBudgetUsage
from src.utils.errors import AppError
from src.utils.run_budget import evaluate_run_budget


def _budget() -> RunBudget:
    return RunBudget(schema_version="1.0", run_id="run-1", publisher_name="Publisher", max_spend_usd=1.0, max_tokens=10, max_runtime_seconds=None, max_retries=None, max_browser_launches=1, max_drive_writes=None, max_wordpress_writes=None, max_pdfs=None)


def test_run_budget_stops_side_effect_at_limit() -> None:
    result = evaluate_run_budget(_budget(), RunBudgetUsage(schema_version="1.0", spend_usd=1.0))
    assert result.decision == "stop"
    assert result.side_effect_allowed is False
    assert result.breached_metrics == ["spend_usd"]


def test_run_budget_allows_audited_override() -> None:
    result = evaluate_run_budget(_budget(), RunBudgetUsage(schema_version="1.0", browser_launches=1), override_actor="operator", override_reason="approved incident recovery")
    assert result.decision == "override"
    assert result.side_effect_allowed is True


def test_run_budget_rejects_partial_override_audit() -> None:
    with pytest.raises(AppError) as exc_info:
        evaluate_run_budget(_budget(), RunBudgetUsage(schema_version="1.0", tokens=10), override_actor="operator")
    assert exc_info.value.code == "run_budget_override_audit_missing"
