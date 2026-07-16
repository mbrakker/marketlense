from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.contracts.llm_usage import LLMUsageLedgerAppendRequest, LLMUsageLedgerEntry
from src.contracts.run_budget import (
    BudgetOverrideContext,
    BudgetRequest,
    BudgetReservationReconcileRequest,
    RunBudget,
    RunBudgetLimits,
)
from src.contracts.run_context import RunContext
from src.services.llm_usage_ledger_service import (
    append_usage,
    evaluate_budget_request,
    read_budget_authority_report,
    reconcile_budget_reservation,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="authority-run",
        task_id="authority-task",
        span_id="authority-span",
    )


def _budget(tmp_path, **values: object) -> RunBudget:
    base = RunBudget(
        schema_version="1.0",
        run_id="authority-run",
        publisher_name="Publisher",
        usage_db_path=str(tmp_path / "usage.sqlite"),
        limit_decision="stop",
    )
    return replace(base, **values)


def _request(budget: RunBudget, **values: object) -> BudgetRequest:
    base = BudgetRequest(
        schema_version="1.0",
        budget=budget,
        run_id="authority-run",
        workflow_id="report_download",
        publisher_id="Publisher",
        report_id="report-1",
        resource_type="llm_provider",
        operation="summary",
        provider="openai",
        model="gpt-5-mini",
        estimated_cost_usd=0.1,
        estimated_calls=1,
        idempotency_key="provider:authority-run:0",
        reserve_in_flight=True,
    )
    return replace(base, **values)


@pytest.mark.parametrize(
    ("limit_decision", "expected"),
    (("stop", "stop"), ("pause", "pause"), ("defer", "defer")),
)
def test_authority_returns_each_blocking_outcome(
    tmp_path, limit_decision, expected
) -> None:
    budget = _budget(
        tmp_path,
        limit_decision=limit_decision,
        run_limits=RunBudgetLimits(schema_version="1.0", max_calls=1),
    )

    decision = evaluate_budget_request(_request(budget), _ctx())

    assert decision.decision == expected
    assert decision.reason_code == "budget_limit_reached"
    assert decision.affected_limit == "run.calls"
    assert decision.next_action == "defer_or_request_expiry_bound_override"


def test_authority_allows_and_warns_before_limit(tmp_path) -> None:
    budget = _budget(
        tmp_path,
        run_limits=RunBudgetLimits(schema_version="1.0", max_calls=5),
    )

    allowed = evaluate_budget_request(_request(budget), _ctx())
    warning = evaluate_budget_request(
        _request(budget, idempotency_key="provider:authority-run:1", estimated_calls=3),
        _ctx(),
    )

    assert allowed.decision == "allow"
    assert allowed.reservation_created is True
    assert warning.decision == "warn"
    assert warning.reserved_usage.calls == 1


def test_authority_rejects_expired_override_and_audits_valid_override(tmp_path) -> None:
    budget = _budget(
        tmp_path,
        run_limits=RunBudgetLimits(schema_version="1.0", max_calls=1),
    )
    expired = BudgetOverrideContext(
        schema_version="1.0",
        actor="operator",
        reason="incident",
        scope="run",
        expires_at_utc="2000-01-01T00:00:00+00:00",
        policy_version="budget-authority-v2",
    )
    with pytest.raises(AppError) as exc_info:
        evaluate_budget_request(_request(budget, requested_override=expired), _ctx())
    assert exc_info.value.code == "budget_override_expired"

    valid = replace(
        expired,
        expires_at_utc=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
    )
    decision = evaluate_budget_request(
        _request(budget, requested_override=valid), _ctx()
    )

    assert decision.decision == "authorized_override"
    assert decision.reservation_created is True


def test_authority_reservations_are_atomic_for_concurrent_requests(tmp_path) -> None:
    budget = _budget(
        tmp_path,
        run_limits=RunBudgetLimits(schema_version="1.0", max_calls=2),
    )
    barrier = threading.Barrier(2)

    def evaluate(index: int) -> str:
        barrier.wait()
        return evaluate_budget_request(
            _request(budget, idempotency_key=f"provider:authority-run:{index}"), _ctx()
        ).decision

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(evaluate, range(2)))

    assert sorted(results) == ["allow", "stop"]


def test_authority_expires_orphaned_reservation_and_reconciles_actual_cost(
    tmp_path,
) -> None:
    budget = _budget(
        tmp_path,
        run_limits=RunBudgetLimits(schema_version="1.0", max_calls=3),
    )
    first = evaluate_budget_request(_request(budget, reservation_ttl_seconds=1), _ctx())
    assert first.reservation_created is True

    append_usage(
        LLMUsageLedgerAppendRequest(
            schema_version="1.0",
            db_path=budget.usage_db_path,
            entry=LLMUsageLedgerEntry(
                schema_version="1.0",
                timestamp_utc=datetime.now(timezone.utc).isoformat(),
                provider="openai",
                action="summary",
                run_id="authority-run",
                task_id="authority-task",
                span_id="authority-span",
                trace_id="authority-trace",
                model="gpt-5-mini",
                request_id="authority-response",
                publisher_name="Publisher",
                report_name="report-1",
                source_url="",
                input_tokens=1,
                output_tokens=1,
                total_tokens=2,
                cached_input_tokens=0,
                tool_calls=0,
                estimated_cost_usd=0.12,
                prompt_namespace="",
                prompt_hash="",
                provider_decision="openai_primary",
                cache_decision="disabled",
                temperature=None,
                seed=None,
                timeout_seconds=30.0,
            ),
        ),
        _ctx(),
    )

    released = reconcile_budget_reservation(
        BudgetReservationReconcileRequest(
            schema_version="1.0",
            usage_db_path=budget.usage_db_path,
            reservation_key=first.reservation_key,
            actual_cost_usd=0.12,
        ),
        _ctx(),
    )
    assert released.released is True
    assert released.forecast_error_usd == pytest.approx(0.02)

    orphan = evaluate_budget_request(
        _request(
            budget,
            idempotency_key="provider:authority-run:orphan",
            reservation_ttl_seconds=1,
        ),
        _ctx(),
    )
    assert orphan.reservation_created is True
    time.sleep(1.05)
    recovered = evaluate_budget_request(
        _request(budget, idempotency_key="provider:authority-run:after-orphan"), _ctx()
    )
    assert recovered.reservation_created is True
    report = read_budget_authority_report(
        usage_db_path=budget.usage_db_path, run_id="authority-run", ctx=_ctx()
    )
    assert report.actual_cost_usd == pytest.approx(0.12)
    assert report.orphaned_reservation_recoveries == 1


def test_browser_worker_crash_reservation_expires_before_later_call(tmp_path) -> None:
    budget = _budget(
        tmp_path,
        run_limits=RunBudgetLimits(schema_version="1.0", max_calls=2),
    )
    crashed_worker = evaluate_budget_request(
        _request(
            budget,
            resource_type="browser_use_model",
            operation="browser_use_llm_call",
            idempotency_key="browser-worker:crashed",
            reservation_ttl_seconds=1,
        ),
        _ctx(),
    )
    assert crashed_worker.reservation_created is True

    time.sleep(1.05)
    resumed = evaluate_budget_request(
        _request(
            budget,
            resource_type="browser_use_model",
            operation="browser_use_llm_call",
            idempotency_key="browser-worker:resumed",
        ),
        _ctx(),
    )

    assert resumed.decision == "allow"
    report = read_budget_authority_report(
        usage_db_path=budget.usage_db_path, run_id="authority-run", ctx=_ctx()
    )
    assert report.orphaned_reservation_recoveries == 1


@pytest.mark.parametrize(
    ("scope_name", "budget_field"),
    (("run", "run_limits"), ("day", "day_limits"), ("publisher", "publisher_limits")),
)
def test_authority_enforces_each_configured_scope(
    tmp_path, scope_name, budget_field
) -> None:
    budget = _budget(
        tmp_path,
        **{budget_field: RunBudgetLimits(schema_version="1.0", max_calls=1)},
    )

    decision = evaluate_budget_request(_request(budget), _ctx())

    assert decision.decision == "stop"
    assert decision.affected_limit == f"{scope_name}.calls"
