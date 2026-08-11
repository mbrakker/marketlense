from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace

from src.contracts.config import ConfigLoadRequest
from src.contracts.run_context import RunContext
from src.contracts.workflow_control import (
    SupervisorRunRequest,
    WorkflowSupervisorSettings,
)
from src.contracts.workflow_queue import (
    MailboxDeliveryPayload,
    MailboxDeliveryResult,
    PublisherDiscoveryPayload,
    PublisherDiscoveryResult,
    ReportAcquisitionPayload,
    ReportAcquisitionResult,
    WorkflowJobSubmission,
)
from src.orchestrators.workflow_queue_orchestrator import (
    WorkflowQueueHandlerRegistration,
    WorkflowQueueHandlerResult,
)
from src.orchestrators.workflow_supervisor_orchestrator import (
    SupervisorDependencies,
    run_supervisor_once,
)
from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once
from src.services import config_service
from src.services.workflow_queue_service import (
    enqueue_workflow_job,
    get_workflow_job,
)


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="parallel", task_id="parallel", span_id="parallel"
    )


def _request(
    *,
    max_parallel_workers: int,
    max_total_jobs: int,
    state_db: str = "state.sqlite",
) -> SupervisorRunRequest:
    return SupervisorRunRequest(
        schema_version="1.0",
        state_db=state_db,
        usage_db_path="usage.sqlite",
        worker_id="supervisor-parallel",
        now_utc="2026-08-11T00:00:00Z",
        settings=WorkflowSupervisorSettings(
            schema_version="1.0",
            enabled=True,
            worker_batches_enabled=True,
            max_parallel_workers=max_parallel_workers,
            max_jobs_per_queue=1,
            max_total_jobs=max_total_jobs,
        ),
    )


def _dependencies(worker) -> SupervisorDependencies:
    return SupervisorDependencies(
        acquire_lease=lambda *args, **kwargs: True,
        release_lease=lambda *args, **kwargs: None,
        materialize_outbox=lambda *args, **kwargs: [],
        recover_leases=lambda *args, **kwargs: [],
        run_worker=worker,
        reconcile=lambda *args, **kwargs: {
            "released_leases": [],
            "repaired_outbox_events": [],
            "anomalies": [],
        },
        queue_health=lambda *args, **kwargs: [],
    )


def _succeeded_worker(**kwargs):
    del kwargs
    return SimpleNamespace(released_lease_job_ids=[], terminal_status="succeeded")


def test_supervisor_overlaps_independent_workers_when_parallelism_is_enabled() -> None:
    lock = Lock()
    release = Event()
    three_workers_started = Event()
    active = 0
    maximum_active = 0

    def worker(**kwargs):
        nonlocal active, maximum_active
        del kwargs
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            if active == 3:
                three_workers_started.set()
        try:
            assert release.wait(timeout=5)
            return SimpleNamespace(
                released_lease_job_ids=[], terminal_status="succeeded"
            )
        finally:
            with lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(max_parallel_workers=3, max_total_jobs=3),
            _ctx(),
            dependencies=_dependencies(worker),
        )
        try:
            assert three_workers_started.wait(timeout=1)
        finally:
            release.set()
        result = future.result(timeout=5)

    assert result.completed_job_count == 3
    assert maximum_active == 3


def test_supervisor_never_exceeds_total_job_cap_with_parallel_workers() -> None:
    calls: list[str] = []

    def worker(**kwargs):
        calls.append(str(kwargs["queue_name"]))
        return _succeeded_worker()

    result = run_supervisor_once(
        _request(max_parallel_workers=3, max_total_jobs=2),
        _ctx(),
        dependencies=_dependencies(worker),
    )

    assert result.completed_job_count == 2
    assert len(calls) == 2


def test_parallel_supervisor_persists_three_real_queue_worker_outcomes(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "state.sqlite")
    submissions = (
        (
            "publisher_discovery",
            "publisher_discovery.v1",
            PublisherDiscoveryPayload(
                publisher_id="publisher-1",
                insights_url="https://example.test/insights",
                discovery_policy_version="v1",
                input_reference="snapshot:publisher-1",
                input_content_hash="source-hash",
            ),
            PublisherDiscoveryResult,
        ),
        (
            "report_acquisition",
            "report_acquisition.v1",
            ReportAcquisitionPayload(
                source_identity_id="source-1",
                source_url="https://example.test/report.pdf",
                publisher_id="publisher-1",
                input_reference="snapshot:report-1",
                input_content_hash="source-hash",
            ),
            ReportAcquisitionResult,
        ),
        (
            "mailbox_delivery",
            "mailbox_delivery.v1",
            MailboxDeliveryPayload(
                delivery_request_id="delivery-1",
                source_url="https://example.test/report.pdf",
                publisher_id="publisher-1",
                input_reference="snapshot:delivery-1",
                input_content_hash="source-hash",
            ),
            MailboxDeliveryResult,
        ),
    )
    active = 0
    maximum_active = 0
    lock = Lock()
    release = Event()
    three_workers_started = Event()
    registry = {}
    job_ids = []
    for queue_name, job_type, payload, result_type in submissions:
        job, _ = enqueue_workflow_job(
            state_db,
            WorkflowJobSubmission(
                schema_version="1.0",
                queue_name=queue_name,
                job_type=job_type,
                payload=payload,
                idempotency_key=f"parallel:{queue_name}",
                deduplication_scope="supervisor-parallelism",
            ),
            _ctx(),
            now_utc="2026-08-11T00:00:00+00:00",
        )
        job_ids.append(job.job_id)

        def handler(job, _payload, _ctx, *, _result_type=result_type):
            nonlocal active, maximum_active
            with lock:
                active += 1
                maximum_active = max(maximum_active, active)
                if active == 3:
                    three_workers_started.set()
            try:
                assert release.wait(timeout=10)
                return WorkflowQueueHandlerResult(
                    result=_result_type(
                        output_reference=f"verified:{job.job_id}",
                        output_content_hash="output-hash",
                        output_verified=True,
                    )
                )
            finally:
                with lock:
                    active -= 1

        registry[(queue_name, job_type)] = WorkflowQueueHandlerRegistration(
            queue_name=queue_name,
            job_type=job_type,
            payload_type=type(payload),
            result_type=result_type,
            handler=handler,
            default_retry_policy="bounded",
            default_lease_seconds=60,
            budget_profile="default",
            expected_external_effects=(),
            allowed_downstream_job_types=(),
        )

    def run_worker(**kwargs):
        return run_workflow_worker_once(registry=registry, **kwargs)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(
                max_parallel_workers=3,
                max_total_jobs=3,
                state_db=state_db,
            ),
            _ctx(),
            dependencies=SupervisorDependencies(run_worker=run_worker),
        )
        try:
            assert three_workers_started.wait(timeout=10)
        finally:
            release.set()
        result = future.result(timeout=10)

    assert result.status == "healthy"
    assert result.completed_job_count == 3
    assert maximum_active == 3
    persisted_statuses = [
        get_workflow_job(state_db, job_id, _ctx()).status for job_id in job_ids
    ]
    assert persisted_statuses == ["succeeded", "succeeded", "succeeded"]


def test_project_supervisor_configuration_uses_the_tested_three_worker_cap() -> None:
    settings = config_service.load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path="src/config/app.yaml"), _ctx()
    )

    assert settings.supervisor.max_parallel_workers == 3
