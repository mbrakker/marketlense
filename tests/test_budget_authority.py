from __future__ import annotations

import threading
import time
import json
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from src.contracts.llm_usage import LLMUsageLedgerAppendRequest, LLMUsageLedgerEntry
from src.contracts.run_budget import (
    BudgetOverrideContext,
    BudgetRequest,
    BudgetReservationReconcileRequest,
    BudgetSideEffectFinalizeRequest,
    RunBudget,
    RunBudgetLimits,
    RunBudgetUsage,
    RunBudgetUsageReadRequest,
)
from src.contracts.run_context import RunContext
from src.services.llm_usage_ledger_service import (
    append_usage,
    evaluate_budget_request,
    finalize_budget_side_effect,
    read_budget_authority_report,
    read_run_budget_usage,
    reconcile_budget_reservation,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
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

    decision = evaluate_budget_request(_request(budget, estimated_calls=2), _ctx())

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
        _request(budget, requested_override=valid, estimated_calls=2), _ctx()
    )

    assert decision.decision == "authorized_override"
    assert decision.reservation_created is True


def test_authority_reservations_are_atomic_for_concurrent_requests(tmp_path) -> None:
    budget = _budget(
        tmp_path,
        run_limits=RunBudgetLimits(schema_version="1.0", max_calls=1),
    )
    barrier = threading.Barrier(2)

    def evaluate(index: int) -> str:
        barrier.wait()
        return evaluate_budget_request(
            _request(budget, idempotency_key=f"provider:authority-run:{index}"), _ctx()
        ).decision

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(evaluate, range(2)))

    assert sorted(results) == ["stop", "warn"]


def test_authority_allows_a_proposed_effect_at_its_exact_maximum(tmp_path) -> None:
    budget = _budget(
        tmp_path,
        run_limits=RunBudgetLimits(schema_version="1.0", max_pdfs=1),
    )

    allowed = evaluate_budget_request(
        _request(
            budget,
            resource_type="pdf",
            operation="report_pipeline_pdf",
            estimated_cost_usd=None,
            estimated_calls=0,
            estimated_pdfs=1,
        ),
        _ctx(),
    )
    blocked = evaluate_budget_request(
        _request(
            budget,
            resource_type="pdf",
            operation="report_pipeline_pdf",
            estimated_cost_usd=None,
            estimated_calls=0,
            estimated_pdfs=1,
            idempotency_key="pdf:authority-run:1",
        ),
        _ctx(),
    )

    assert allowed.decision == "warn"
    assert blocked.decision == "stop"
    assert blocked.affected_limit == "run.pdfs"


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


def test_budget_reservation_ttl_bounds_default_side_effect_requests(tmp_path) -> None:
    budget = _budget(tmp_path, reservation_ttl_seconds=1)

    decision = evaluate_budget_request(_request(budget, estimated_calls=2), _ctx())

    with sqlite3.connect(budget.usage_db_path) as conn:
        created_at, expires_at = conn.execute(
            "select created_at_utc, expires_at_utc from budget_authority_reservations "
            "where reservation_key = ?",
            (decision.reservation_key,),
        ).fetchone()
    elapsed = datetime.fromisoformat(expires_at) - datetime.fromisoformat(created_at)
    assert timedelta(seconds=0) < elapsed <= timedelta(seconds=1, milliseconds=1)


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

    decision = evaluate_budget_request(_request(budget, estimated_calls=2), _ctx())

    assert decision.decision == "stop"
    assert decision.affected_limit == f"{scope_name}.calls"


def _drive_read_request(
    budget: RunBudget, *, key: str, publisher: str = "Publisher"
) -> BudgetRequest:
    return BudgetRequest(
        schema_version="1.0",
        budget=budget,
        run_id=budget.run_id,
        workflow_id="report_download",
        publisher_id=publisher,
        report_id="report-1",
        resource_type="drive_read",
        operation="drive_list_pdfs",
        estimated_drive_reads=1,
        idempotency_key=key,
        reserve_in_flight=True,
    )


def _finalize_drive_read(budget: RunBudget, key: str, *, actual_reads: int) -> None:
    finalize_budget_side_effect(
        BudgetSideEffectFinalizeRequest(
            schema_version="1.0",
            usage_db_path=budget.usage_db_path,
            reservation_key=key,
            actual_usage=RunBudgetUsage(schema_version="1.0", drive_reads=actual_reads),
        ),
        _ctx(),
    )


def test_side_effect_actual_reconciliation_releases_unused_capacity_and_is_idempotent(
    tmp_path,
) -> None:
    budget = _budget(
        tmp_path,
        run_limits=RunBudgetLimits(schema_version="1.0", max_drive_reads=2),
    )
    reserved = evaluate_budget_request(
        _drive_read_request(budget, key="read:one"), _ctx()
    )
    assert reserved.decision == "allow"

    _finalize_drive_read(budget, reserved.reservation_key, actual_reads=0)
    replay = finalize_budget_side_effect(
        BudgetSideEffectFinalizeRequest(
            schema_version="1.0",
            usage_db_path=budget.usage_db_path,
            reservation_key=reserved.reservation_key,
            actual_usage=RunBudgetUsage(schema_version="1.0", drive_reads=0),
        ),
        _ctx(),
    )
    assert replay.actual_recorded is False
    assert replay.reservation_released is False

    next_read = evaluate_budget_request(
        _drive_read_request(budget, key="read:two"), _ctx()
    )
    assert next_read.decision == "allow"
    usage = read_run_budget_usage(
        RunBudgetUsageReadRequest(schema_version="1.0", budget=budget), _ctx()
    ).usage
    assert usage.drive_reads == 0


def test_authority_day_scope_spans_runs_and_publisher_scope_isolated(tmp_path) -> None:
    usage_db_path = str(tmp_path / "usage.sqlite")
    day_limits = RunBudgetLimits(schema_version="1.0", max_drive_reads=1)
    run_a = RunBudget(
        schema_version="1.0",
        run_id="run-a",
        publisher_name="Publisher A",
        usage_db_path=usage_db_path,
        day_utc="2026-07-16",
        day_limits=day_limits,
    )
    ctx_a = RunContext(
        schema_version="1.0", run_id="run-a", task_id="task", span_id="a"
    )
    first = evaluate_budget_request(
        _drive_read_request(run_a, key="day:a", publisher="Publisher A"), ctx_a
    )
    finalize_budget_side_effect(
        BudgetSideEffectFinalizeRequest(
            schema_version="1.0",
            usage_db_path=usage_db_path,
            reservation_key=first.reservation_key,
            actual_usage=RunBudgetUsage(schema_version="1.0", drive_reads=1),
        ),
        ctx_a,
    )
    run_b = replace(run_a, run_id="run-b", publisher_name="Publisher B")
    ctx_b = RunContext(
        schema_version="1.0", run_id="run-b", task_id="task", span_id="b"
    )
    blocked_by_day = evaluate_budget_request(
        _drive_read_request(run_b, key="day:b", publisher="Publisher B"), ctx_b
    )
    assert blocked_by_day.decision == "stop"
    assert blocked_by_day.affected_limit == "day.drive_reads"

    publisher_budget = replace(
        run_a,
        day_limits=None,
        publisher_limits=RunBudgetLimits(schema_version="1.0", max_drive_reads=2),
    )
    isolated = evaluate_budget_request(
        _drive_read_request(
            replace(publisher_budget, run_id="run-c", publisher_name="Publisher B"),
            key="publisher:b",
            publisher="Publisher B",
        ),
        RunContext(schema_version="1.0", run_id="run-c", task_id="task", span_id="c"),
    )
    assert isolated.decision == "allow"


def test_legacy_limits_do_not_apply_to_other_runs_on_the_same_day(tmp_path) -> None:
    prior_budget = _budget(tmp_path, run_id="prior-run")
    prior_request = _request(
        prior_budget,
        run_id="prior-run",
        resource_type="drive_write",
        operation="drive_upload_bytes",
        estimated_cost_usd=None,
        estimated_calls=0,
        estimated_writes=1,
        idempotency_key="drive:prior-run:upload",
    )
    prior_decision = evaluate_budget_request(prior_request, _ctx())
    finalize_budget_side_effect(
        BudgetSideEffectFinalizeRequest(
            schema_version="1.0",
            usage_db_path=prior_budget.usage_db_path,
            reservation_key=prior_decision.reservation_key,
            actual_usage=RunBudgetUsage(schema_version="1.0", drive_writes=2),
        ),
        _ctx(),
    )
    current_budget = _budget(
        tmp_path,
        run_id="current-run",
        max_drive_writes=1,
    )

    decision = evaluate_budget_request(
        _request(
            current_budget,
            run_id="current-run",
            resource_type="pdf_process",
            operation="acquire_report_pdf",
            estimated_cost_usd=None,
            estimated_calls=0,
            estimated_pdfs=1,
            idempotency_key="pdf:current-run:acquire",
        ),
        _ctx(),
    )

    assert decision.decision == "allow"


def test_defer_persists_actionable_work_and_cold_start_forecast_is_audited(
    tmp_path,
) -> None:
    budget = _budget(
        tmp_path,
        limit_decision="defer",
        run_limits=RunBudgetLimits(schema_version="1.0", max_calls=1),
    )
    deferred = evaluate_budget_request(
        _request(budget, idempotency_key="defer:one", estimated_calls=2), _ctx()
    )
    assert deferred.decision == "defer"
    cold = evaluate_budget_request(
        _request(
            _budget(tmp_path),
            idempotency_key="cold:one",
            estimated_cost_usd=None,
        ),
        _ctx(),
    )
    assert cold.decision == "allow"
    with sqlite3.connect(budget.usage_db_path) as conn:
        work = conn.execute(
            "select status, next_action from budget_authority_deferred_work"
        ).fetchone()
        details_raw = conn.execute(
            "select details_json from budget_authority_events where reservation_key = ?",
            ("cold:one",),
        ).fetchone()[0]
    assert work == ("pending", "defer_or_request_expiry_bound_override")
    assert json.loads(details_raw)["forecast_method"] == "unavailable"


def test_override_audit_persists_actor_reason_scope_and_expiry(tmp_path) -> None:
    budget = _budget(
        tmp_path,
        run_limits=RunBudgetLimits(schema_version="1.0", max_calls=1),
    )
    override = BudgetOverrideContext(
        schema_version="1.0",
        actor="on-call-operator",
        reason="approved incident recovery",
        scope="run",
        expires_at_utc=(datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(),
        policy_version=budget.policy_version,
    )
    evaluate_budget_request(_request(budget, requested_override=override), _ctx())
    with sqlite3.connect(budget.usage_db_path) as conn:
        audit = conn.execute(
            "select override_actor, override_reason, override_scope, override_expires_at_utc "
            "from budget_authority_events"
        ).fetchone()
    assert audit == (
        "on-call-operator",
        "approved incident recovery",
        "run",
        override.expires_at_utc,
    )


def test_retry_budget_stop_prevents_the_second_side_effect_attempt(tmp_path) -> None:
    budget = _budget(
        tmp_path,
        run_limits=RunBudgetLimits(schema_version="1.0", max_retries=1),
    )
    attempts = {"count": 0}

    def fail_once() -> None:
        attempts["count"] += 1
        raise AppError(code="provider_transient", message="retry", retryable=True)

    with pytest.raises(AppError) as exc_info:
        run_with_retry(
            step_name="expensive_provider_step",
            operation=fail_once,
            ctx=_ctx(),
            logger=logging.getLogger("market_lense.test_budget_authority"),
            module_name="market_lense.test_budget_authority",
            policy=RetryPolicy(
                retries=2,
                base_delay_seconds=0.0,
                backoff_step_seconds=0.0,
                budget=budget,
                budget_workflow_id="report_download",
            ),
            retry_event="retry",
            sleep_fn=lambda _seconds: None,
        )
    assert exc_info.value.code == "retry_budget_stop"
    assert attempts["count"] == 2
