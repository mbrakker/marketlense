# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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
    source_submission = WorkflowJobSubmission(
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
    )
    source_job, _ = enqueue_workflow_job(
        state_db,
        source_submission,
        _ctx(),
        now_utc="2026-08-11T00:00:00+00:00",
    )
    selection_was_idle = Event()
    selection_executed = Event()
    selection_worker_ids: list[str] = []
    selection_job_ids: list[str] = []
    effective_side_effects: list[str] = []
    recovery_calls: list[str] = []

    def ingest(job, _payload, _ctx):
        effective_side_effects.append(f"source_ingest:{job.job_id}")
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

    def select(job, _payload, _ctx):
        selection_executed.set()
        effective_side_effects.append(f"report_selection:{job.job_id}")
        selection_job_ids.append(job.job_id)
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
        reap_deferred_work=lambda *_args: recovery_calls.append("deferred") or 0,
        reap_remediation=lambda *_args: recovery_calls.append("remediation") or 0,
    )

    base_supervisor = config_service.load_workflow_control_settings(
        ConfigLoadRequest(schema_version="1.0", path="src/config/app.yaml"),
        _ctx(),
    ).supervisor
    autonomous_supervisor = config_service.load_workflow_control_settings(
        ConfigLoadRequest(
            schema_version="1.0", path="src/config/app.autonomous_mvp.yaml"
        ),
        _ctx(),
    ).supervisor
    settings = replace(
        base_supervisor,
        enabled=autonomous_supervisor.enabled,
        deferred_work_enabled=autonomous_supervisor.deferred_work_enabled,
        remediation_enabled=autonomous_supervisor.remediation_enabled,
        worker_batches_enabled=autonomous_supervisor.worker_batches_enabled,
    )
    request = SupervisorRunRequest(
        schema_version="1.0",
        state_db=state_db,
        usage_db_path="usage.sqlite",
        worker_id="supervisor-autonomous-profile",
        now_utc="2026-08-11T00:00:00Z",
        settings=settings,
    )
    result = run_supervisor_once(
        request,
        _ctx(),
        dependencies=dependencies,
    )

    assert selection_was_idle.is_set()
    assert selection_executed.is_set()
    assert result.completed_job_count == 2
    assert result.completed_job_count <= settings.max_total_jobs
    assert settings.max_total_jobs == 60
    assert settings.max_runtime_seconds == 1200
    assert settings.lease_seconds == 180
    assert recovery_calls == ["deferred", "remediation"]
    assert get_workflow_job(state_db, source_job.job_id, _ctx()).status == "succeeded"
    assert len(selection_worker_ids) == 1

    replayed_source, created = enqueue_workflow_job(
        state_db,
        source_submission,
        _ctx(),
        now_utc="2026-08-11T00:00:03+00:00",
    )
    replay = run_supervisor_once(request, _ctx(), dependencies=dependencies)

    assert replayed_source.job_id == source_job.job_id
    assert created is False
    assert replay.status == "healthy"
    assert replay.completed_job_count == 0
    assert effective_side_effects == [
        f"source_ingest:{source_job.job_id}",
        f"report_selection:{selection_job_ids[0]}",
    ]
    assert len(list_workflow_job_attempts(state_db, source_job.job_id, _ctx())) == 1
    assert len(list_workflow_job_attempts(state_db, selection_job_ids[0], _ctx())) == 1


def test_materialized_downstream_queue_gets_spare_slot_before_other_queue_backlog() -> (
    None
):
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
            return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")
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

    dependencies = replace(_dependencies(worker), materialize_outbox=materialize_outbox)

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
            return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")
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

    dependencies = replace(_dependencies(worker), materialize_outbox=materialize_outbox)

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

    dependencies = replace(_dependencies(worker), materialize_outbox=materialize_outbox)
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

    dependencies = replace(_dependencies(worker), materialize_outbox=materialize_outbox)

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

    dependencies = replace(_dependencies(worker), materialize_outbox=materialize_outbox)

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
