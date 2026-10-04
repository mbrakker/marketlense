from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Event, Lock
from types import SimpleNamespace

import pytest

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
    ReportAnalysisPayload,
    ReportAnalysisResult,
    SourceIngestPayload,
    SourceIngestResult,
    WorkflowJobSubmission,
    WorkflowQueueControl,
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
    list_workflow_job_attempts,
    set_workflow_queue_control,
)
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0", run_id="parallel", task_id="parallel", span_id="parallel"
    )


def _request(
    *,
    max_parallel_workers: int,
    max_total_jobs: int,
    max_jobs_per_queue: int = 1,
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
            max_jobs_per_queue=max_jobs_per_queue,
            max_total_jobs=max_total_jobs,
        ),
    )


def _set_queue_concurrency(
    state_db: str,
    queue_name: str,
    limit: int,
    *,
    enabled: bool = True,
    mode: str = "active",
    emergency_stop_reason: str = "",
) -> None:
    set_workflow_queue_control(
        state_db,
        WorkflowQueueControl(
            schema_version="1.0",
            queue_name=queue_name,
            mode=mode,
            enabled=enabled,
            worker_concurrency_limit=limit,
            maximum_pending=100,
            maximum_fanout=5,
            max_attempts=3,
            lease_seconds=60,
            budget_profile="default",
            retry_delay_seconds=60,
            emergency_stop_reason=emergency_stop_reason,
            updated_at_utc="",
            updated_by="test",
        ),
        _ctx(),
    )


def _enqueue_report_acquisition_jobs(
    state_db: str, count: int
) -> list[str]:
    _set_queue_concurrency(state_db, "report_acquisition", 5)
    job_ids = []
    for index in range(count):
        job, _ = enqueue_workflow_job(
            state_db,
            WorkflowJobSubmission(
                schema_version="1.0",
                queue_name="report_acquisition",
                job_type="report_acquisition.v1",
                payload=ReportAcquisitionPayload(
                    source_identity_id=f"source-{index}",
                    source_url=f"https://example.test/report-{index}.pdf",
                    publisher_id="publisher-1",
                    input_reference=f"snapshot:report-{index}",
                    input_content_hash=f"source-hash-{index}",
                ),
                idempotency_key=f"parallel:report-acquisition:{index}",
                deduplication_scope="supervisor-parallelism",
            ),
            _ctx(),
            now_utc="2026-08-11T00:00:00+00:00",
        )
        job_ids.append(job.job_id)
    return job_ids


def _queue_handler_registration(
    *, queue_name, job_type, payload_type, result_type, handler
):
    return WorkflowQueueHandlerRegistration(
        queue_name=queue_name,
        job_type=job_type,
        payload_type=payload_type,
        result_type=result_type,
        handler=handler,
        default_retry_policy="bounded",
        default_lease_seconds=60,
        budget_profile="default",
        expected_external_effects=(),
        allowed_downstream_job_types=(),
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


def test_supervisor_never_exceeds_global_worker_cap_when_candidates_remain() -> None:
    lock = Lock()
    release = Event()
    two_started = Event()
    active = 0
    maximum_active = 0

    def worker(**kwargs):
        nonlocal active, maximum_active
        del kwargs
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            if active == 2:
                two_started.set()
        try:
            assert release.wait(timeout=5)
            return _succeeded_worker()
        finally:
            with lock:
                active -= 1

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(
                max_parallel_workers=2,
                max_total_jobs=5,
                max_jobs_per_queue=3,
            ),
            _ctx(),
            dependencies=_dependencies(worker),
        )
        try:
            assert two_started.wait(timeout=2)
        finally:
            release.set()
        result = future.result(timeout=5)

    assert result.completed_job_count == 5
    assert maximum_active == 2


def test_supervisor_overlaps_same_queue_jobs_with_distinct_lease_owners(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "same-queue.sqlite")
    job_ids = _enqueue_report_acquisition_jobs(state_db, 3)
    lock = Lock()
    release = Event()
    three_started = Event()
    active = 0
    maximum_active = 0

    def handler(job, _payload, _ctx):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            if active == 3:
                three_started.set()
        try:
            assert release.wait(timeout=10)
            return WorkflowQueueHandlerResult(
                result=ReportAcquisitionResult(
                    output_reference=f"verified:{job.job_id}",
                    output_content_hash="output-hash",
                    output_verified=True,
                )
            )
        finally:
            with lock:
                active -= 1

    registry = {
        ("report_acquisition", "report_acquisition.v1"): (
            _queue_handler_registration(
                queue_name="report_acquisition",
                job_type="report_acquisition.v1",
                payload_type=ReportAcquisitionPayload,
                result_type=ReportAcquisitionResult,
                handler=handler,
            )
        )
    }

    def run_worker(**kwargs):
        return run_workflow_worker_once(registry=registry, **kwargs)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(
                max_parallel_workers=3,
                max_total_jobs=3,
                max_jobs_per_queue=3,
                state_db=state_db,
            ),
            _ctx(),
            dependencies=SupervisorDependencies(run_worker=run_worker),
        )
        try:
            assert three_started.wait(timeout=10)
        finally:
            release.set()
        result = future.result(timeout=15)

    assert result.status == "healthy"
    assert result.completed_job_count == 3
    assert maximum_active == 3
    statuses = [get_workflow_job(state_db, job_id, _ctx()).status for job_id in job_ids]
    assert statuses == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]
    attempts = [
        attempt
        for job_id in job_ids
        for attempt in list_workflow_job_attempts(state_db, job_id, _ctx())
    ]
    assert len(attempts) == 3
    assert len({attempt.worker_id for attempt in attempts}) == 3


def test_supervisor_respects_durable_queue_limit_and_reuses_available_capacity(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "durable-cap.sqlite")
    job_ids = _enqueue_report_acquisition_jobs(state_db, 3)
    _set_queue_concurrency(state_db, "report_acquisition", 2)
    lock = Lock()
    release = Event()
    two_started = Event()
    limit_observed = Event()
    active = 0
    maximum_active = 0

    def handler(job, _payload, _ctx):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            if active == 2:
                two_started.set()
        try:
            assert release.wait(timeout=10)
            return WorkflowQueueHandlerResult(
                result=ReportAcquisitionResult(
                    output_reference=f"verified:{job.job_id}",
                    output_content_hash="output-hash",
                    output_verified=True,
                )
            )
        finally:
            with lock:
                active -= 1

    registry = {
        ("report_acquisition", "report_acquisition.v1"): (
            _queue_handler_registration(
                queue_name="report_acquisition",
                job_type="report_acquisition.v1",
                payload_type=ReportAcquisitionPayload,
                result_type=ReportAcquisitionResult,
                handler=handler,
            )
        )
    }

    def run_worker(**kwargs):
        result = run_workflow_worker_once(registry=registry, **kwargs)
        if (
            kwargs["queue_name"] == "report_acquisition"
            and result.claimed_job_id == ""
        ):
            with lock:
                if active == 2:
                    limit_observed.set()
        return result

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(
                max_parallel_workers=3,
                max_total_jobs=3,
                max_jobs_per_queue=3,
                state_db=state_db,
            ),
            _ctx(),
            dependencies=SupervisorDependencies(run_worker=run_worker),
        )
        try:
            assert two_started.wait(timeout=10)
            assert limit_observed.wait(timeout=10)
        finally:
            release.set()
        first_pass = future.result(timeout=15)

    assert maximum_active == 2
    assert first_pass.completed_job_count == 2
    assert sum(
        get_workflow_job(state_db, job_id, _ctx()).status == "pending"
        for job_id in job_ids
    ) == 1

    second_pass = run_supervisor_once(
        _request(
            max_parallel_workers=3,
            max_total_jobs=3,
            max_jobs_per_queue=3,
            state_db=state_db,
        ),
        _ctx(),
        dependencies=SupervisorDependencies(run_worker=run_worker),
    )
    assert second_pass.completed_job_count == 1
    statuses = [get_workflow_job(state_db, job_id, _ctx()).status for job_id in job_ids]
    assert statuses == [
        "succeeded",
        "succeeded",
        "succeeded",
    ]


def test_supervisor_keeps_other_queues_fair_while_report_analysis_is_backlogged(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "fairness.sqlite")
    _set_queue_concurrency(state_db, "report_analysis", 5)
    _set_queue_concurrency(state_db, "source_ingest", 5)
    analysis_job_ids = []
    for index in range(3):
        job, _ = enqueue_workflow_job(
            state_db,
            WorkflowJobSubmission(
                schema_version="1.0",
                queue_name="report_analysis",
                job_type="report_analysis.v1",
                payload=ReportAnalysisPayload(report_id=f"report-{index}"),
                idempotency_key=f"fairness:analysis:{index}",
                deduplication_scope="supervisor-fairness",
            ),
            _ctx(),
            now_utc="2026-08-11T00:00:00+00:00",
        )
        analysis_job_ids.append(job.job_id)
    source_job, _ = enqueue_workflow_job(
        state_db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="source_ingest",
            job_type="source_ingest.v1",
            payload=SourceIngestPayload(
                source_identity_id="source-fair",
                source_artifact_reference="snapshot:source-fair",
                source_content_hash="source-hash",
                report_id="report-fair",
            ),
            idempotency_key="fairness:source-ingest",
            deduplication_scope="supervisor-fairness",
        ),
        _ctx(),
        now_utc="2026-08-11T00:00:00+00:00",
    )
    release = Event()
    source_started = Event()
    analysis_remaining_when_source_started = []

    def analysis_handler(job, _payload, _ctx):
        assert release.wait(timeout=10)
        return WorkflowQueueHandlerResult(
            result=ReportAnalysisResult(
                output_reference=f"analysis:{job.job_id}",
                output_content_hash="analysis-hash",
                output_verified=True,
            )
        )

    def source_handler(job, _payload, _ctx):
        analysis_remaining_when_source_started.append(
            sum(
                get_workflow_job(state_db, job_id, _ctx).status != "succeeded"
                for job_id in analysis_job_ids
            )
        )
        source_started.set()
        assert release.wait(timeout=10)
        return WorkflowQueueHandlerResult(
            result=SourceIngestResult(
                output_reference=f"ingest:{job.job_id}",
                output_content_hash="ingest-hash",
                output_verified=True,
            )
        )

    registry = {
        ("report_analysis", "report_analysis.v1"): _queue_handler_registration(
            queue_name="report_analysis",
            job_type="report_analysis.v1",
            payload_type=ReportAnalysisPayload,
            result_type=ReportAnalysisResult,
            handler=analysis_handler,
        ),
        ("source_ingest", "source_ingest.v1"): _queue_handler_registration(
            queue_name="source_ingest",
            job_type="source_ingest.v1",
            payload_type=SourceIngestPayload,
            result_type=SourceIngestResult,
            handler=source_handler,
        ),
    }

    def run_worker(**kwargs):
        return run_workflow_worker_once(registry=registry, **kwargs)

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(
                max_parallel_workers=3,
                max_total_jobs=4,
                max_jobs_per_queue=3,
                state_db=state_db,
            ),
            _ctx(),
            dependencies=SupervisorDependencies(run_worker=run_worker),
        )
        try:
            assert source_started.wait(timeout=10)
        finally:
            release.set()
        result = future.result(timeout=15)

    assert result.completed_job_count == 4
    assert get_workflow_job(state_db, source_job.job_id, _ctx()).status == "succeeded"
    assert analysis_remaining_when_source_started == [3]


@pytest.mark.parametrize(
    ("enabled", "mode", "stop_reason"),
    [
        (False, "active", ""),
        (True, "paused", ""),
        (True, "active", "operator emergency stop"),
    ],
)
def test_supervisor_respects_disabled_paused_and_emergency_stopped_queues(
    tmp_path, enabled, mode, stop_reason
) -> None:
    state_db = str(tmp_path / f"stopped-{mode}-{enabled}.sqlite")
    job_id = _enqueue_report_acquisition_jobs(state_db, 1)[0]
    _set_queue_concurrency(
        state_db,
        "report_acquisition",
        5,
        enabled=enabled,
        mode=mode,
        emergency_stop_reason=stop_reason,
    )
    registry = {
        ("report_acquisition", "report_acquisition.v1"): (
            _queue_handler_registration(
                queue_name="report_acquisition",
                job_type="report_acquisition.v1",
                payload_type=ReportAcquisitionPayload,
                result_type=ReportAcquisitionResult,
                handler=lambda *_args: WorkflowQueueHandlerResult(
                    result=ReportAcquisitionResult(
                        output_reference="unexpected",
                        output_content_hash="output-hash",
                        output_verified=True,
                    )
                ),
            )
        )
    }

    result = run_supervisor_once(
        _request(
            max_parallel_workers=3,
            max_total_jobs=3,
            max_jobs_per_queue=3,
            state_db=state_db,
        ),
        _ctx(),
        dependencies=SupervisorDependencies(
            run_worker=lambda **kwargs: run_workflow_worker_once(
                registry=registry, **kwargs
            )
        ),
    )

    assert result.completed_job_count == 0
    assert get_workflow_job(state_db, job_id, _ctx()).status == "pending"


def test_retryable_failure_releases_slot_for_remaining_same_queue_jobs(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "retry-capacity.sqlite")
    job_ids = _enqueue_report_acquisition_jobs(state_db, 3)
    handled: list[str] = []

    def handler(job, _payload, _ctx):
        handled.append(job.job_id)
        if job.job_id == job_ids[0]:
            raise AppError(
                code="test_retryable_queue_failure",
                message="retry the first queued job later",
                retryable=True,
            )
        return WorkflowQueueHandlerResult(
            result=ReportAcquisitionResult(
                output_reference=f"verified:{job.job_id}",
                output_content_hash="output-hash",
                output_verified=True,
            )
        )

    registry = {
        ("report_acquisition", "report_acquisition.v1"): (
            _queue_handler_registration(
                queue_name="report_acquisition",
                job_type="report_acquisition.v1",
                payload_type=ReportAcquisitionPayload,
                result_type=ReportAcquisitionResult,
                handler=handler,
            )
        )
    }
    result = run_supervisor_once(
        _request(
            max_parallel_workers=3,
            max_total_jobs=3,
            max_jobs_per_queue=3,
            state_db=state_db,
        ),
        _ctx(),
        dependencies=SupervisorDependencies(
            run_worker=lambda **kwargs: run_workflow_worker_once(
                registry=registry, **kwargs
            )
        ),
    )

    assert result.completed_job_count == 2
    assert result.deferred_job_count == 1
    assert sorted(handled) == sorted(job_ids)
    assert get_workflow_job(state_db, job_ids[0], _ctx()).status == "retry_wait"
    assert list_workflow_job_attempts(state_db, job_ids[0], _ctx())[0].outcome == (
        "retry_wait"
    )
    statuses = [
        get_workflow_job(state_db, job_id, _ctx()).status for job_id in job_ids[1:]
    ]
    assert statuses == [
        "succeeded",
        "succeeded",
    ]


def test_single_same_queue_job_is_attempted_once_with_expanded_dispatch_limit(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "single-job.sqlite")
    job_id = _enqueue_report_acquisition_jobs(state_db, 1)[0]
    registry = {
        ("report_acquisition", "report_acquisition.v1"): (
            _queue_handler_registration(
                queue_name="report_acquisition",
                job_type="report_acquisition.v1",
                payload_type=ReportAcquisitionPayload,
                result_type=ReportAcquisitionResult,
                handler=lambda job, _payload, _ctx: WorkflowQueueHandlerResult(
                    result=ReportAcquisitionResult(
                        output_reference=f"verified:{job.job_id}",
                        output_content_hash="output-hash",
                        output_verified=True,
                    )
                ),
            )
        )
    }
    result = run_supervisor_once(
        _request(
            max_parallel_workers=3,
            max_total_jobs=3,
            max_jobs_per_queue=3,
            state_db=state_db,
        ),
        _ctx(),
        dependencies=SupervisorDependencies(
            run_worker=lambda **kwargs: run_workflow_worker_once(
                registry=registry, **kwargs
            )
        ),
    )

    assert result.completed_job_count == 1
    assert get_workflow_job(state_db, job_id, _ctx()).status == "succeeded"
    assert len(list_workflow_job_attempts(state_db, job_id, _ctx())) == 1


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
    assert settings.supervisor.max_jobs_per_queue == 3
