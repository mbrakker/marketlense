from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from src.contracts.deferred_work import (
    DeferredWorkClaimRequest,
    DeferredWorkLeaseReleaseRequest,
    DeferredWorkListRequest,
    DeferredWorkMetricsRequest,
    DeferredWorkReaperRequest,
    DeferredWorkResumePlan,
)
from src.contracts.remediation import RemediationListRequest
from src.contracts.run_budget import BudgetRequest, RunBudget, RunBudgetLimits
from src.contracts.run_context import RunContext
from src.orchestrators.deferred_work_orchestrator import (
    DeferredWorkReaperDependencies,
    run_bounded_deferred_work_reaper,
)
from src.services.llm_usage_ledger_service import (
    claim_next_deferred_work,
    deferred_work_metrics,
    evaluate_budget_request,
    list_deferred_work,
    recheck_deferred_work_budget,
    release_expired_deferred_work_leases,
)
from src.services.state_service import list_remediation_records
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="deferred-run", task_id="task", span_id="span"
    )


def _iso(delta_seconds: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=delta_seconds)).isoformat()


def _request(
    tmp_path,
    *,
    key: str = "deferred:one",
    due: bool = True,
    deadline_seconds: int = 3600,
    max_attempts: int = 3,
) -> BudgetRequest:
    now = datetime.now(timezone.utc)
    return BudgetRequest(
        schema_version="1.0",
        budget=RunBudget(
            schema_version="1.0",
            run_id="deferred-run",
            publisher_name="Publisher",
            usage_db_path=str(tmp_path / "usage.sqlite"),
            limit_decision="defer",
            run_limits=RunBudgetLimits(schema_version="1.0", max_calls=1),
        ),
        run_id="deferred-run",
        workflow_id="report_generation",
        publisher_id="Publisher",
        report_id="report-1",
        source_id="source-hash",
        stage="source_prepared",
        plan_hash="plan-original",
        reusable_artifact_references=(
            ("local_pdf", "retained/report-1.pdf", "source-hash"),
        ),
        resource_type="llm_provider",
        operation="generate_summary",
        estimated_calls=2,
        idempotency_key=key,
        deferred_earliest_run_at_utc=(now - timedelta(seconds=1)).isoformat()
        if due
        else "",
        deferred_deadline_at_utc=(
            now + timedelta(seconds=deadline_seconds)
        ).isoformat(),
        deferred_max_attempts=max_attempts,
    )


def _item(tmp_path, *, key: str = "deferred:one", **kwargs):
    decision = evaluate_budget_request(_request(tmp_path, key=key, **kwargs), _ctx())
    assert decision.decision == "defer"
    records = list_deferred_work(
        DeferredWorkListRequest(
            schema_version="1.0",
            usage_db_path=str(tmp_path / "usage.sqlite"),
            limit=10,
        ),
        _ctx(),
    ).records
    return next(record for record in records if record.idempotency_key == key)


def _reaper_request(
    tmp_path, *, now_utc: str, limit: int = 1
) -> DeferredWorkReaperRequest:
    return DeferredWorkReaperRequest(
        schema_version="1.0",
        usage_db_path=str(tmp_path / "usage.sqlite"),
        state_db=str(tmp_path / "state.sqlite"),
        worker_id="worker-a",
        now_utc=now_utc,
        execution_enabled=True,
        limit=limit,
        lease_seconds=30,
        retry_delay_seconds=60,
    )


def _records(tmp_path):
    return list_deferred_work(
        DeferredWorkListRequest(
            schema_version="1.0", usage_db_path=str(tmp_path / "usage.sqlite"), limit=20
        ),
        _ctx(),
    ).records


def _deps(
    *,
    budget: str = "allow",
    plan_hash: str = "plan-original",
    outcome: str = "completed",
):
    return DeferredWorkReaperDependencies(
        plan_builders={
            "report_generation": lambda item, ctx: DeferredWorkResumePlan(
                schema_version="1.0",
                plan_hash=plan_hash,
                resume_stage="latest_safe",
                reusable_artifacts=list(item.reusable_artifacts),
            )
        },
        resumers={"report_generation": lambda item, plan, ctx: outcome},
        budget_check=lambda item, ctx: budget,
    )


def test_defer_is_durable_idempotent_and_not_immediately_due(tmp_path) -> None:
    request = _request(tmp_path, due=False, deadline_seconds=7200)
    assert evaluate_budget_request(request, _ctx()).decision == "defer"
    assert evaluate_budget_request(request, _ctx()).decision == "defer"

    records = _records(tmp_path)
    assert len(records) == 1
    assert records[0].status == "pending"
    assert records[0].defer_count == 1
    assert records[0].stage == "source_prepared"
    assert records[0].plan_hash == "plan-original"
    assert records[0].reusable_artifacts[0].reference == "retained/report-1.pdf"
    assert records[0].earliest_run_at_utc > records[0].deferred_at_utc

    metrics = deferred_work_metrics(
        DeferredWorkMetricsRequest(
            schema_version="1.0",
            usage_db_path=str(tmp_path / "usage.sqlite"),
            now_utc=records[0].deferred_at_utc,
        ),
        _ctx(),
    )
    assert metrics.queue_depth == 1
    assert metrics.due_count == 0


def test_atomic_claim_prevents_duplicate_execution_and_restart_recovers_expired_lease(
    tmp_path,
) -> None:
    item = _item(tmp_path)
    now = _iso(30)

    def claim(worker: str):
        return claim_next_deferred_work(
            DeferredWorkClaimRequest(
                schema_version="1.0",
                usage_db_path=str(tmp_path / "usage.sqlite"),
                worker_id=worker,
                now_utc=now,
                lease_seconds=1,
            ),
            _ctx(),
        ).record

    with ThreadPoolExecutor(max_workers=2) as executor:
        claimed = list(executor.map(claim, ["worker-a", "worker-b"]))
    active = [record for record in claimed if record is not None]
    assert len(active) == 1
    assert active[0].work_key == item.work_key

    released = release_expired_deferred_work_leases(
        DeferredWorkLeaseReleaseRequest(
            schema_version="1.0",
            usage_db_path=str(tmp_path / "usage.sqlite"),
            now_utc=_iso(90),
        ),
        _ctx(),
    )
    assert released.released_work_keys == [item.work_key]
    restarted = claim("worker-restarted")
    assert restarted is not None
    assert restarted.lease_owner == "worker-restarted"
    assert restarted.attempt_count == 2


def test_repeated_defer_then_budget_reset_rebuilds_plan_and_completes(tmp_path) -> None:
    item = _item(tmp_path)
    assert recheck_deferred_work_budget(item, _ctx()).decision == "defer"
    first_now = _iso(30)
    still_deferred = run_bounded_deferred_work_reaper(
        _reaper_request(tmp_path, now_utc=first_now),
        _ctx(),
        dependencies=_deps(budget="defer"),
    )
    assert still_deferred.deferred_work_keys == [item.work_key]
    waiting = _records(tmp_path)[0]
    assert waiting.status == "pending"
    assert waiting.defer_count == 2
    assert waiting.earliest_run_at_utc > first_now

    resumed = run_bounded_deferred_work_reaper(
        _reaper_request(tmp_path, now_utc=_iso(120)),
        _ctx(),
        dependencies=_deps(budget="allow", plan_hash="plan-after-budget-reset"),
    )
    assert resumed.completed_work_keys == [item.work_key]
    completed = _records(tmp_path)[0]
    assert completed.status == "completed"
    assert completed.plan_hash == "plan-after-budget-reset"
    assert completed.completed_at_utc


def test_missing_artifact_and_deadline_expiry_handoff_to_remediation(tmp_path) -> None:
    missing = _item(tmp_path, key="deferred:missing")
    deadline = _item(tmp_path, key="deferred:deadline", deadline_seconds=1)
    missing_deps = DeferredWorkReaperDependencies(
        plan_builders={
            "report_generation": lambda item, ctx: (_ for _ in ()).throw(
                AppError(
                    code="deferred_work_required_artifact_missing",
                    message="retained artifact missing",
                    retryable=False,
                )
            )
        },
        resumers={"report_generation": lambda item, plan, ctx: "completed"},
        budget_check=lambda item, ctx: "allow",
    )
    result = run_bounded_deferred_work_reaper(
        _reaper_request(tmp_path, now_utc=_iso(120), limit=2),
        _ctx(),
        dependencies=missing_deps,
    )
    assert sorted(result.remediation_work_keys) == sorted(
        [missing.work_key, deadline.work_key]
    )
    by_key = {record.work_key: record for record in _records(tmp_path)}
    assert by_key[missing.work_key].status == "remediation"
    assert by_key[missing.work_key].terminal_status == "plan_or_resume_failed"
    assert by_key[deadline.work_key].terminal_status == "deadline_expired"
    remediations = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0", state_db=str(tmp_path / "state.sqlite"), limit=10
        ),
        _ctx(),
    ).records
    assert len(remediations) == 2
    assert all(record.status == "operator_action_required" for record in remediations)


def test_stop_and_attempt_exhaustion_are_terminal_remediation_not_defer(
    tmp_path,
) -> None:
    stopped = _item(tmp_path, key="deferred:stop")
    exhausted = _item(tmp_path, key="deferred:exhausted", max_attempts=1)
    stopped_result = run_bounded_deferred_work_reaper(
        _reaper_request(tmp_path, now_utc=_iso(30), limit=1),
        _ctx(),
        dependencies=_deps(budget="stop"),
    )
    assert stopped_result.remediation_work_keys == [stopped.work_key]

    first = run_bounded_deferred_work_reaper(
        _reaper_request(tmp_path, now_utc=_iso(30), limit=1),
        _ctx(),
        dependencies=_deps(budget="defer"),
    )
    assert first.deferred_work_keys == [exhausted.work_key]
    second = run_bounded_deferred_work_reaper(
        _reaper_request(tmp_path, now_utc=_iso(120), limit=1),
        _ctx(),
        dependencies=_deps(budget="allow"),
    )
    assert second.remediation_work_keys == [exhausted.work_key]
    by_key = {record.work_key: record for record in _records(tmp_path)}
    assert by_key[stopped.work_key].terminal_status == "budget_stop"
    assert by_key[exhausted.work_key].terminal_status == "attempt_budget_exhausted"


def test_feature_flag_preserves_pending_records_without_leasing(tmp_path) -> None:
    item = _item(tmp_path)
    response = run_bounded_deferred_work_reaper(
        replace(_reaper_request(tmp_path, now_utc=_iso(30)), execution_enabled=False),
        _ctx(),
        dependencies=_deps(),
    )
    assert response.inspected_count == 0
    assert _records(tmp_path)[0].work_key == item.work_key
    assert _records(tmp_path)[0].status == "pending"
