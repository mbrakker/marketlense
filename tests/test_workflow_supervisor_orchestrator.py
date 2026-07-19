from __future__ import annotations

from types import SimpleNamespace

from src.contracts.run_context import RunContext
from src.contracts.workflow_control import (
    SupervisorRunRequest,
    WorkflowSupervisorSettings,
)
from src.orchestrators.workflow_supervisor_orchestrator import (
    SupervisorDependencies,
    run_supervisor_once,
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="run", task_id="task", span_id="span"
    )


def _request(settings: WorkflowSupervisorSettings) -> SupervisorRunRequest:
    return SupervisorRunRequest(
        schema_version="1.0",
        state_db="state.sqlite",
        usage_db_path="usage.sqlite",
        worker_id="supervisor-1",
        now_utc="2026-07-19T00:00:00Z",
        settings=settings,
    )


def test_supervisor_is_disabled_without_taking_a_lease() -> None:
    calls = []
    result = run_supervisor_once(
        _request(WorkflowSupervisorSettings(schema_version="1.0", enabled=False)),
        _ctx(),
        dependencies=SupervisorDependencies(
            acquire_lease=lambda *args, **kwargs: calls.append("lease")
        ),
    )

    assert result.status == "disabled"
    assert calls == []


def test_supervisor_composes_bounded_existing_queue_operations_once() -> None:
    calls: list[str] = []

    def worker(**kwargs):
        calls.append(f"worker:{kwargs['queue_name']}")
        return SimpleNamespace(
            released_lease_job_ids=[],
            terminal_status="succeeded"
            if kwargs["queue_name"] == "publisher_discovery"
            else "idle",
        )

    deps = SupervisorDependencies(
        acquire_lease=lambda *args, **kwargs: calls.append("acquire") or True,
        release_lease=lambda *args, **kwargs: calls.append("release"),
        materialize_outbox=lambda *args, **kwargs: (
            calls.append("materialize") or ["job-1"]
        ),
        recover_leases=lambda *args, **kwargs: calls.append("recover") or ["expired-1"],
        run_worker=worker,
        reconcile=lambda *args, **kwargs: (
            calls.append("reconcile")
            or {"released_leases": [], "repaired_outbox_events": [], "anomalies": []}
        ),
        queue_health=lambda *args, **kwargs: calls.append("health") or [],
    )
    settings = WorkflowSupervisorSettings(
        schema_version="1.0",
        enabled=True,
        worker_batches_enabled=True,
        max_jobs_per_queue=1,
        max_total_jobs=1,
    )

    result = run_supervisor_once(_request(settings), _ctx(), dependencies=deps)

    assert result.status == "healthy"
    assert result.materialized_job_count == 1
    assert result.recovered_lease_count == 1
    assert result.completed_job_count == 1
    assert calls[:4] == [
        "acquire",
        "materialize",
        "recover",
        "worker:publisher_discovery",
    ]
    assert calls[-3:] == ["reconcile", "health", "release"]


def test_supervisor_busy_and_unregistered_recovery_adapter_fail_closed() -> None:
    busy = run_supervisor_once(
        _request(WorkflowSupervisorSettings(schema_version="1.0", enabled=True)),
        _ctx(),
        dependencies=SupervisorDependencies(
            acquire_lease=lambda *args, **kwargs: False
        ),
    )
    assert busy.status == "busy"

    settings = WorkflowSupervisorSettings(
        schema_version="1.0", enabled=True, deferred_work_enabled=True
    )
    result = run_supervisor_once(
        _request(settings),
        _ctx(),
        dependencies=SupervisorDependencies(
            acquire_lease=lambda *args, **kwargs: True,
            release_lease=lambda *args, **kwargs: None,
            materialize_outbox=lambda *args, **kwargs: [],
            recover_leases=lambda *args, **kwargs: [],
            reconcile=lambda *args, **kwargs: {
                "released_leases": [],
                "repaired_outbox_events": [],
                "anomalies": [],
            },
            queue_health=lambda *args, **kwargs: [],
        ),
    )
    assert result.status == "failed"
    assert result.error_codes == ["deferred_work_adapter_unregistered"]
