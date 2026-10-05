from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
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
    WORKFLOW_QUEUE_NAMES,
    MailboxDeliveryPayload,
    MailboxDeliveryResult,
    PublisherDiscoveryPayload,
    PublisherDiscoveryResult,
    ReportAcquisitionPayload,
    ReportAcquisitionResult,
    ReportAnalysisPayload,
    ReportAnalysisResult,
    ReportSelectionPayload,
    ReportSelectionResult,
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
    materialize_workflow_outbox,
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
    max_runtime_seconds: int = 120,
    supervisor_lease_seconds: int = 180,
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
            max_runtime_seconds=max_runtime_seconds,
            lease_seconds=supervisor_lease_seconds,
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
    *,
    queue_name,
    job_type,
    payload_type,
    result_type,
    handler,
    allowed_downstream_job_types=(),
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
        allowed_downstream_job_types=allowed_downstream_job_types,
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


def test_parallel_supervisor_stops_after_one_fully_idle_queue_scan() -> None:
    calls: list[str] = []

    def worker(**kwargs):
        calls.append(str(kwargs["queue_name"]))
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")

    result = run_supervisor_once(
        _request(
            max_parallel_workers=3,
            max_total_jobs=10,
            max_jobs_per_queue=3,
        ),
        _ctx(),
        dependencies=_dependencies(worker),
    )

    assert result.completed_job_count == 0
    assert all(calls.count(queue_name) <= 3 for queue_name in WORKFLOW_QUEUE_NAMES)
    assert len(calls) <= 3 * len(WORKFLOW_QUEUE_NAMES)


def test_successful_worker_rechecks_idle_downstream_queue_without_outbox() -> None:
    lock = Lock()
    target_was_idle = Event()
    producer_completed = Event()
    target_completed = Event()
    target_queue, producer_queue = WORKFLOW_QUEUE_NAMES[:2]

    def worker(**kwargs):
        queue_name = str(kwargs["queue_name"])
        if queue_name == target_queue:
            if producer_completed.is_set():
                target_completed.set()
                return _succeeded_worker()
            target_was_idle.set()
            return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")
        if queue_name == producer_queue:
            assert target_was_idle.wait(timeout=3)
            with lock:
                if not producer_completed.is_set():
                    producer_completed.set()
                    return _succeeded_worker()
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")

    result = run_supervisor_once(
        _request(
            max_parallel_workers=2,
            max_total_jobs=2,
            max_runtime_seconds=5,
            supervisor_lease_seconds=3,
        ),
        _ctx(),
        dependencies=_dependencies(worker),
    )

    assert result.completed_job_count == 2
    assert target_was_idle.is_set()
    assert producer_completed.is_set()
    assert target_completed.is_set()


def test_parallel_supervisor_respects_runtime_after_in_flight_workers_finish() -> None:
    calls: list[str] = []
    lock = Lock()
    three_started = Event()
    release = Event()

    def worker(**kwargs):
        with lock:
            calls.append(str(kwargs["queue_name"]))
            if len(calls) == 3:
                three_started.set()
        assert release.wait(timeout=5)
        return _succeeded_worker()

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(
                max_parallel_workers=3,
                max_total_jobs=10,
                max_jobs_per_queue=3,
                max_runtime_seconds=1,
            ),
            _ctx(),
            dependencies=_dependencies(worker),
        )
        try:
            assert three_started.wait(timeout=2)
            assert not release.wait(timeout=1.1)
        finally:
            release.set()
        result = future.result(timeout=5)

    assert result.completed_job_count == 3
    assert result.deferred_job_count >= 1
    assert len(calls) == 3


def test_parallel_supervisor_renews_lease_while_workers_run() -> None:
    acquire_calls: list[str] = []
    worker_started = Event()
    lease_renewed = Event()
    release_worker = Event()

    def acquire_lease(*_args, **kwargs):
        acquire_calls.append(str(kwargs["now_utc"]))
        if len(acquire_calls) > 1:
            lease_renewed.set()
        return True

    def worker(**kwargs):
        del kwargs
        worker_started.set()
        assert release_worker.wait(timeout=5)
        return _succeeded_worker()

    request = _request(
        max_parallel_workers=2,
        max_total_jobs=1,
        supervisor_lease_seconds=1,
    )
    dependencies = replace(
        _dependencies(worker), acquire_lease=acquire_lease
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once, request, _ctx(), dependencies=dependencies
        )
        try:
            assert worker_started.wait(timeout=2)
            assert lease_renewed.wait(timeout=2)
        finally:
            release_worker.set()
        result = future.result(timeout=5)

    assert result.status == "healthy"
    assert acquire_calls[0] == request.now_utc
    assert acquire_calls[1] != request.now_utc


def test_parallel_supervisor_stops_dispatch_after_losing_lease() -> None:
    acquire_calls: list[str] = []
    worker_calls: list[str] = []
    two_workers_started = Event()
    lease_lost = Event()
    release_workers = Event()
    lock = Lock()

    def acquire_lease(*_args, **kwargs):
        acquire_calls.append(str(kwargs["now_utc"]))
        if len(acquire_calls) > 1:
            lease_lost.set()
            return False
        return True

    def worker(**kwargs):
        with lock:
            worker_calls.append(str(kwargs["queue_name"]))
            if len(worker_calls) == 2:
                two_workers_started.set()
        assert release_workers.wait(timeout=5)
        return _succeeded_worker()

    request = _request(
        max_parallel_workers=2,
        max_total_jobs=3,
        max_jobs_per_queue=3,
        supervisor_lease_seconds=1,
    )
    dependencies = replace(
        _dependencies(worker), acquire_lease=acquire_lease
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once, request, _ctx(), dependencies=dependencies
        )
        try:
            assert two_workers_started.wait(timeout=2)
            assert lease_lost.wait(timeout=2)
        finally:
            release_workers.set()
        result = future.result(timeout=5)

    assert result.status == "failed"
    assert result.error_codes == ["supervisor_lease_lost"]
    assert len(acquire_calls) == 2
    assert len(worker_calls) == 2


def test_successful_outbox_materialization_reopens_idle_queue_epoch() -> None:
    analysis_poll_started = Event()
    child_materialized = Event()
    second_scan_reached_end = Event()
    queue_calls: dict[str, int] = {}
    queue_calls_lock = Lock()
    materialize_calls = 0

    def worker(**kwargs):
        queue_name = str(kwargs["queue_name"])
        with queue_calls_lock:
            queue_calls[queue_name] = queue_calls.get(queue_name, 0) + 1
            call_number = queue_calls[queue_name]
        if queue_name == "source_ingest":
            if call_number > 1:
                return SimpleNamespace(
                    released_lease_job_ids=[], terminal_status="idle"
                )
            assert analysis_poll_started.wait(timeout=5)
            return _succeeded_worker()
        if queue_name == "report_analysis":
            if call_number == 1:
                analysis_poll_started.set()
                assert child_materialized.wait(timeout=5)
                assert second_scan_reached_end.wait(timeout=5)
                return SimpleNamespace(
                    released_lease_job_ids=[], terminal_status="idle"
                )
            if call_number == 2:
                return _succeeded_worker()
            return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")
        if queue_name == "publisher_discovery":
            if call_number == 2:
                second_scan_reached_end.set()
            return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")

    def materialize_outbox(*_args, **_kwargs):
        nonlocal materialize_calls
        materialize_calls += 1
        if materialize_calls == 2:
            child_materialized.set()
            return ["materialized-report-analysis-job"]
        return []

    dependencies = replace(
        _dependencies(worker), materialize_outbox=materialize_outbox
    )
    result = run_supervisor_once(
        _request(
            max_parallel_workers=3,
            max_total_jobs=5,
            max_jobs_per_queue=1,
        ),
        _ctx(),
        dependencies=dependencies,
    )

    assert result.completed_job_count == 2
    assert queue_calls["report_analysis"] == 4
    assert queue_calls["publisher_discovery"] == 3


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


def test_supervisor_reuses_three_same_queue_slots_for_the_backlog(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "same-queue.sqlite")
    job_ids = _enqueue_report_acquisition_jobs(state_db, 5)
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
                max_total_jobs=5,
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
    assert result.completed_job_count == 5
    assert maximum_active == 3
    statuses = [get_workflow_job(state_db, job_id, _ctx()).status for job_id in job_ids]
    assert statuses == ["succeeded"] * 5
    attempts = [
        attempt
        for job_id in job_ids
        for attempt in list_workflow_job_attempts(state_db, job_id, _ctx())
    ]
    assert len(attempts) == 5
    assert len({attempt.worker_id for attempt in attempts}) == 3


def test_supervisor_respects_durable_limit_and_reuses_queue_slots_within_pass(
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
    assert first_pass.completed_job_count == 3
    assert sum(
        get_workflow_job(state_db, job_id, _ctx()).status == "pending"
        for job_id in job_ids
    ) == 0
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


def test_parallel_supervisor_dispatches_materialized_downstream_work_in_same_pass(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "downstream-same-pass.sqlite")
    _set_queue_concurrency(state_db, "source_ingest", 3)
    _set_queue_concurrency(state_db, "report_selection", 3)
    source_job, _ = enqueue_workflow_job(
        state_db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="source_ingest",
            job_type="source_ingest.v1",
            payload=SourceIngestPayload(
                source_identity_id="source-1",
                input_reference="snapshot:source-1",
                input_content_hash="source-hash-1",
                report_id="report-1",
            ),
            idempotency_key="same-pass:source-ingest",
            deduplication_scope="supervisor-same-pass",
        ),
        _ctx(),
        now_utc="2026-08-11T00:00:00+00:00",
    )
    selection_was_idle = Event()
    selection_executed = Event()
    selection_worker_ids: list[str] = []

    def ingest(job, _payload, _ctx):
        assert selection_was_idle.wait(timeout=10)
        return WorkflowQueueHandlerResult(
            result=SourceIngestResult(
                output_reference=f"prepared:{job.job_id}",
                output_content_hash="prepared-hash",
                output_verified=True,
            ),
            downstream=[
                WorkflowJobSubmission(
                    schema_version="1.0",
                    queue_name="report_selection",
                    job_type="report_selection.v1",
                    payload=ReportSelectionPayload(report_id="report-1"),
                    idempotency_key="same-pass:report-selection",
                    deduplication_scope="supervisor-same-pass",
                    root_workflow_id=job.root_workflow_id,
                    parent_job_id=job.job_id,
                    entity_type="report",
                    entity_id="report-1",
                    report_id="report-1",
                    available_at_utc="2026-08-11T00:00:01+00:00",
                )
            ],
        )

    def select(_job, _payload, _ctx):
        selection_executed.set()
        return WorkflowQueueHandlerResult(
            result=ReportSelectionResult(
                output_reference="selected:report-1",
                output_content_hash="selection-hash",
                output_verified=True,
            )
        )

    registry = {
        ("source_ingest", "source_ingest.v1"): _queue_handler_registration(
            queue_name="source_ingest",
            job_type="source_ingest.v1",
            payload_type=SourceIngestPayload,
            result_type=SourceIngestResult,
            handler=ingest,
            allowed_downstream_job_types=("report_selection.v1",),
        ),
        ("report_selection", "report_selection.v1"): _queue_handler_registration(
            queue_name="report_selection",
            job_type="report_selection.v1",
            payload_type=ReportSelectionPayload,
            result_type=ReportSelectionResult,
            handler=select,
        ),
    }

    def run_worker(**kwargs):
        result = run_workflow_worker_once(registry=registry, **kwargs)
        if kwargs["queue_name"] == "report_selection":
            if result.terminal_status == "idle":
                selection_was_idle.set()
            elif result.terminal_status == "succeeded":
                selection_worker_ids.append(result.worker_id)
        return result

    dependencies = _dependencies(run_worker)
    dependencies = SupervisorDependencies(
        acquire_lease=dependencies.acquire_lease,
        release_lease=dependencies.release_lease,
        materialize_outbox=materialize_workflow_outbox,
        recover_leases=dependencies.recover_leases,
        run_worker=dependencies.run_worker,
        reconcile=dependencies.reconcile,
        queue_health=dependencies.queue_health,
    )

    result = run_supervisor_once(
        _request(
            max_parallel_workers=3,
            max_total_jobs=3,
            max_jobs_per_queue=3,
            state_db=state_db,
        ),
        _ctx(),
        dependencies=dependencies,
    )

    assert selection_was_idle.is_set()
    assert selection_executed.is_set()
    assert result.completed_job_count == 2
    assert get_workflow_job(state_db, source_job.job_id, _ctx()).status == "succeeded"
    assert len(selection_worker_ids) == 1


def test_materialized_downstream_queue_gets_spare_slot_before_other_queue_backlog() -> None:
    lock = Lock()
    two_analysis_workers_started = Event()
    release_analysis_workers = Event()
    selection_finished = Event()
    render_backlog_started = Event()
    release_render_backlog = Event()
    analysis_calls = 0
    selection_calls = 0
    render_calls = 0
    analysis_child_pending = False
    render_backlog_available = False

    def worker(**kwargs):
        nonlocal analysis_calls, render_calls
        nonlocal selection_calls
        nonlocal analysis_child_pending, render_backlog_available
        queue_name = str(kwargs["queue_name"])
        if queue_name == "report_selection":
            with lock:
                selection_calls += 1
                selection_call_number = selection_calls
            if selection_call_number > 1:
                return SimpleNamespace(
                    released_lease_job_ids=[], terminal_status="idle"
                )
            assert two_analysis_workers_started.wait(timeout=5)
            with lock:
                analysis_child_pending = True
            selection_finished.set()
            return _succeeded_worker()
        if queue_name == "report_analysis":
            with lock:
                analysis_calls += 1
                call_number = analysis_calls
                if call_number == 2:
                    two_analysis_workers_started.set()
            if call_number <= 2:
                assert release_analysis_workers.wait(timeout=10)
                return _succeeded_worker()
            if call_number == 3:
                return _succeeded_worker()
            return SimpleNamespace(
                released_lease_job_ids=[], terminal_status="idle"
            )
        if queue_name == "report_render":
            with lock:
                if not render_backlog_available:
                    return SimpleNamespace(
                        released_lease_job_ids=[], terminal_status="idle"
                    )
                render_calls += 1
                if render_calls == 1:
                    render_backlog_started.set()
            assert release_render_backlog.wait(timeout=10)
            return _succeeded_worker()
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")

    def materialize_outbox(*_args, **_kwargs):
        nonlocal analysis_child_pending, render_backlog_available
        with lock:
            if not analysis_child_pending:
                return []
            analysis_child_pending = False
            render_backlog_available = True
            return ["report-analysis-child"]

    dependencies = replace(
        _dependencies(worker), materialize_outbox=materialize_outbox
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(
                max_parallel_workers=3,
                max_total_jobs=5,
                max_jobs_per_queue=3,
            ),
            _ctx(),
            dependencies=dependencies,
        )
        try:
            assert selection_finished.wait(timeout=5)
            assert render_backlog_started.wait(timeout=3)
        finally:
            release_analysis_workers.set()
            release_render_backlog.set()
        result = future.result(timeout=15)

    assert result.completed_job_count == 5
    assert render_backlog_started.is_set()


def test_materialized_child_does_not_discard_same_queue_backlog_recheck() -> None:
    lock = Lock()
    two_analysis_workers_started = Event()
    release_analysis_workers = Event()
    render_started = Event()
    render_completed = Event()
    analysis_backlog_started = Event()
    analysis_child_pending = False
    render_pending = False
    analysis_calls = 0

    def worker(**kwargs):
        nonlocal analysis_calls, analysis_child_pending, render_pending
        queue_name = str(kwargs["queue_name"])
        if queue_name == "report_analysis":
            with lock:
                analysis_calls += 1
                call_number = analysis_calls
                if call_number == 2:
                    two_analysis_workers_started.set()
                if call_number == 3:
                    analysis_child_pending = True
            if call_number <= 2:
                assert release_analysis_workers.wait(timeout=10)
                return _succeeded_worker()
            if call_number == 3:
                assert two_analysis_workers_started.wait(timeout=5)
                return _succeeded_worker()
            if call_number == 4:
                analysis_backlog_started.set()
                return _succeeded_worker()
            return SimpleNamespace(
                released_lease_job_ids=[], terminal_status="idle"
            )
        if queue_name == "report_render":
            with lock:
                if not render_pending:
                    return SimpleNamespace(
                        released_lease_job_ids=[], terminal_status="idle"
                    )
                render_pending = False
                render_started.set()
            render_completed.set()
            return _succeeded_worker()
        if queue_name == "publisher_discovery" and render_completed.is_set():
            assert analysis_backlog_started.wait(timeout=5)
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")

    def materialize_outbox(*_args, **_kwargs):
        nonlocal analysis_child_pending, render_pending
        with lock:
            if analysis_child_pending:
                analysis_child_pending = False
                render_pending = True
                return ["report-render-child"]
        return []

    dependencies = replace(
        _dependencies(worker), materialize_outbox=materialize_outbox
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(
                max_parallel_workers=3,
                max_total_jobs=10,
                max_jobs_per_queue=3,
            ),
            _ctx(),
            dependencies=dependencies,
        )
        try:
            assert two_analysis_workers_started.wait(timeout=5)
            assert render_started.wait(timeout=3)
            assert analysis_backlog_started.wait(timeout=3)
        finally:
            release_analysis_workers.set()
        result = future.result(timeout=15)

    assert result.completed_job_count == 5
    assert render_completed.is_set()
    assert analysis_backlog_started.is_set()


def test_selection_backlog_gets_a_fair_slot_before_third_analysis_worker() -> None:
    lock = Lock()
    two_analysis_workers_started = Event()
    second_selection_completed = Event()
    analysis_overtook_selection = Event()
    selection_pending = 1
    selection_completed = 0
    selection_outbox_pending = 0
    analysis_pending = 2
    analysis_started = 0

    def worker(**kwargs):
        nonlocal selection_pending, selection_completed
        nonlocal selection_outbox_pending, analysis_pending, analysis_started
        queue_name = str(kwargs["queue_name"])
        if queue_name == "report_selection":
            with lock:
                if selection_pending <= 0:
                    return SimpleNamespace(
                        released_lease_job_ids=[], terminal_status="idle"
                    )
                selection_pending -= 1
                selection_completed += 1
                selection_outbox_pending += 1
                completed = selection_completed
                if completed == 2:
                    second_selection_completed.set()
            if completed == 1:
                assert two_analysis_workers_started.wait(timeout=5)
            return _succeeded_worker()
        if queue_name == "report_analysis":
            with lock:
                if analysis_pending <= 0:
                    return SimpleNamespace(
                        released_lease_job_ids=[], terminal_status="idle"
                    )
                analysis_pending -= 1
                analysis_started += 1
                started = analysis_started
                if started == 2:
                    two_analysis_workers_started.set()
                if started >= 3 and selection_completed < 2:
                    analysis_overtook_selection.set()
            if started <= 2:
                assert second_selection_completed.wait(timeout=5)
            return _succeeded_worker()
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")

    def materialize_outbox(*_args, **_kwargs):
        nonlocal selection_outbox_pending, selection_pending, analysis_pending
        with lock:
            if selection_outbox_pending <= 0:
                return []
            selection_outbox_pending -= 1
            analysis_pending += 1
            if selection_completed == 1:
                selection_pending = 2
            return [f"analysis-{analysis_pending}"]

    dependencies = replace(
        _dependencies(worker), materialize_outbox=materialize_outbox
    )
    result = run_supervisor_once(
        _request(
            max_parallel_workers=3,
            max_total_jobs=20,
            max_jobs_per_queue=3,
        ),
        _ctx(),
        dependencies=dependencies,
    )

    assert result.completed_job_count == 8
    assert selection_completed == 3
    assert not analysis_overtook_selection.is_set()


def test_source_ingest_backlog_progresses_before_deeper_report_stages() -> None:
    lock = Lock()
    three_sources_started = Event()
    release_initial_sources = Event()
    source_started = 0
    source_completed = 0
    materialized_sources = 0
    selection_pending = 0
    selection_outbox_pending = 0
    analysis_pending = 0
    analysis_started = 0
    source_progress_overtaken = Event()

    def worker(**kwargs):
        nonlocal source_started, source_completed, selection_pending
        nonlocal analysis_started
        nonlocal selection_outbox_pending, analysis_pending
        queue_name = str(kwargs["queue_name"])
        if queue_name == "source_ingest":
            with lock:
                if source_started == 5:
                    return SimpleNamespace(
                        released_lease_job_ids=[], terminal_status="idle"
                    )
                source_started += 1
                call_number = source_started
                if source_started == 3:
                    three_sources_started.set()
            if call_number <= 3:
                assert release_initial_sources.wait(timeout=10)
            with lock:
                source_completed += 1
            return _succeeded_worker()
        if queue_name == "report_selection":
            with lock:
                if selection_pending <= 0:
                    return SimpleNamespace(
                        released_lease_job_ids=[], terminal_status="idle"
                    )
                selection_pending -= 1
                selection_outbox_pending += 1
            return _succeeded_worker()
        if queue_name == "report_analysis":
            with lock:
                if analysis_pending <= 0:
                    return SimpleNamespace(
                        released_lease_job_ids=[], terminal_status="idle"
                    )
                analysis_pending -= 1
                analysis_started += 1
                if analysis_started == 3 and source_started < 5:
                    source_progress_overtaken.set()
            return _succeeded_worker()
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")

    def materialize_outbox(*_args, **_kwargs):
        nonlocal materialized_sources, selection_pending, selection_outbox_pending
        nonlocal analysis_pending
        with lock:
            if materialized_sources < source_completed:
                materialized_sources += 1
                selection_pending += 1
                return [f"selection-{materialized_sources}"]
            if selection_outbox_pending:
                selection_outbox_pending -= 1
                analysis_pending += 1
                return [f"analysis-{analysis_pending}"]
        return []

    dependencies = replace(
        _dependencies(worker), materialize_outbox=materialize_outbox
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(
                max_parallel_workers=3,
                max_total_jobs=20,
                max_jobs_per_queue=3,
            ),
            _ctx(),
            dependencies=dependencies,
        )
        try:
            assert three_sources_started.wait(timeout=5)
            release_initial_sources.set()
            result = future.result(timeout=20)
        finally:
            release_initial_sources.set()

    assert source_started == 5
    assert not source_progress_overtaken.is_set()
    assert result.completed_job_count == 15


def test_downstream_work_runs_before_same_queue_upstream_backlog_drains() -> None:
    lock = Lock()
    render_was_idle = Event()
    render_started = Event()
    release_upstream_backlog = Event()
    upstream_calls = 0
    upstream_completed = 0
    outbox_pending = 0
    downstream_ready = 0
    downstream_completed = 0

    def worker(**kwargs):
        nonlocal upstream_calls, upstream_completed, outbox_pending
        nonlocal downstream_ready, downstream_completed
        queue_name = str(kwargs["queue_name"])
        if queue_name == "report_analysis":
            with lock:
                if upstream_calls >= 5:
                    return SimpleNamespace(
                        released_lease_job_ids=[], terminal_status="idle"
                    )
                upstream_calls += 1
                call_number = upstream_calls
            if call_number == 1:
                assert render_was_idle.wait(timeout=5)
            else:
                assert release_upstream_backlog.wait(timeout=5)
            with lock:
                upstream_completed += 1
                outbox_pending += 1
            return _succeeded_worker()
        if queue_name == "report_render":
            with lock:
                if downstream_ready:
                    downstream_ready -= 1
                    downstream_completed += 1
                    render_started.set()
                    return _succeeded_worker()
            render_was_idle.set()
            return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")

    def materialize_outbox(*_args, **_kwargs):
        nonlocal outbox_pending, downstream_ready
        with lock:
            if outbox_pending:
                outbox_pending -= 1
                downstream_ready += 1
                return [f"report-render-{downstream_ready}"]
        return []

    dependencies = replace(
        _dependencies(worker), materialize_outbox=materialize_outbox
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            run_supervisor_once,
            _request(
                max_parallel_workers=3,
                max_total_jobs=10,
                max_jobs_per_queue=3,
            ),
            _ctx(),
            dependencies=dependencies,
        )
        try:
            assert render_started.wait(timeout=3)
            with lock:
                assert upstream_completed < 5
        finally:
            release_upstream_backlog.set()
        result = future.result(timeout=10)

    assert result.completed_job_count == 10
    assert upstream_calls == 5
    assert downstream_completed == 5


def test_project_supervisor_configuration_uses_the_tested_three_worker_cap() -> None:
    settings = config_service.load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path="src/config/app.yaml"), _ctx()
    )

    assert settings.supervisor.max_parallel_workers == 3
    assert settings.supervisor.max_jobs_per_queue == 3
    assert settings.supervisor.max_runtime_seconds == 1200
    assert settings.supervisor.lease_seconds == 180
