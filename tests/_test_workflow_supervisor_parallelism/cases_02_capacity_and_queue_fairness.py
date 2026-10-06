# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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


def test_supervisor_reuses_five_same_queue_slots_for_the_backlog(
    tmp_path,
) -> None:
    state_db = str(tmp_path / "same-queue.sqlite")
    job_ids = _enqueue_report_acquisition_jobs(state_db, 5)
    lock = Lock()
    release = Event()
    five_started = Event()
    active = 0
    maximum_active = 0

    def handler(job, _payload, _ctx):
        nonlocal active, maximum_active
        with lock:
            active += 1
            maximum_active = max(maximum_active, active)
            if active == 5:
                five_started.set()
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
                max_parallel_workers=5,
                max_total_jobs=5,
                max_jobs_per_queue=5,
                state_db=state_db,
            ),
            _ctx(),
            dependencies=SupervisorDependencies(run_worker=run_worker),
        )
        try:
            assert five_started.wait(timeout=10)
        finally:
            release.set()
        result = future.result(timeout=15)

    assert result.status == "healthy"
    assert result.completed_job_count == 5
    assert maximum_active == 5
    statuses = [get_workflow_job(state_db, job_id, _ctx()).status for job_id in job_ids]
    assert statuses == ["succeeded"] * 5
    attempts = [
        attempt
        for job_id in job_ids
        for attempt in list_workflow_job_attempts(state_db, job_id, _ctx())
    ]
    assert len(attempts) == 5
    assert len({attempt.worker_id for attempt in attempts}) == 5


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
        if kwargs["queue_name"] == "report_acquisition" and result.claimed_job_id == "":
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
    assert (
        sum(
            get_workflow_job(state_db, job_id, _ctx()).status == "pending"
            for job_id in job_ids
        )
        == 0
    )
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
