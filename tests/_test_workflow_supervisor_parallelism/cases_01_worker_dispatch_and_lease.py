# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._support_cases import *  # noqa: F401,F403


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


def test_ready_downstream_work_precedes_same_queue_backlog_after_success() -> None:
    lock = Lock()
    render_polled_idle = Event()
    render_completed = Event()
    order: list[str] = []
    analysis_calls = 0
    render_ready = False

    def worker(**kwargs):
        nonlocal analysis_calls, render_ready
        queue_name = str(kwargs["queue_name"])
        if queue_name == "report_analysis":
            with lock:
                analysis_calls += 1
                call_number = analysis_calls
            if call_number == 1:
                assert render_polled_idle.wait(timeout=5)
                with lock:
                    render_ready = True
                order.append("analysis:1")
            else:
                assert render_completed.wait(timeout=5)
                with lock:
                    order.append(f"analysis:{call_number}")
            return _succeeded_worker(
                downstream_queue_names=(("report_render",) if call_number == 1 else ())
            )
        if queue_name == "report_render":
            with lock:
                if render_ready:
                    render_ready = False
                    order.append("render")
                    render_completed.set()
                    return _succeeded_worker()
            render_polled_idle.set()
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")

    result = run_supervisor_once(
        _request(
            max_parallel_workers=3,
            max_total_jobs=3,
            max_jobs_per_queue=1,
        ),
        _ctx(),
        dependencies=_dependencies(worker),
    )

    assert result.completed_job_count == 3
    assert order[:3] == ["analysis:1", "render", "analysis:2"], order


def test_actual_render_children_precede_analysis_backlog() -> None:
    lock = Lock()
    order: list[str] = []
    analysis_started = Event()
    release_analysis = Event()
    render_completed = False
    analytics_completed = False
    analysis_completed = False
    readiness_completed = False
    claim_embedding_completed = False

    def worker(**kwargs):
        nonlocal analytics_completed, render_completed, analysis_completed
        nonlocal readiness_completed, claim_embedding_completed
        queue_name = str(kwargs["queue_name"])
        if queue_name == "report_analysis":
            with lock:
                if analysis_completed:
                    return SimpleNamespace(
                        released_lease_job_ids=[], terminal_status="idle"
                    )
            analysis_started.set()
            assert release_analysis.wait(timeout=5)
            with lock:
                analysis_completed = True
                order.append("report_analysis")
            return _succeeded_worker()
        if queue_name == "report_render":
            with lock:
                render_should_complete = not render_completed
            if render_should_complete:
                assert analysis_started.wait(timeout=5)
                with lock:
                    if not render_completed:
                        render_completed = True
                        order.append("report_render")
                        return _succeeded_worker(
                            downstream_queue_names=(
                                "analytics_projection",
                                "publication_readiness",
                            )
                        )
            return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")
        with lock:
            if (
                queue_name == "analytics_projection"
                and render_completed
                and not analytics_completed
            ):
                analytics_completed = True
                order.append("analytics_projection")
                return _succeeded_worker(downstream_queue_names=("claim_embedding",))
            if (
                queue_name == "publication_readiness"
                and render_completed
                and not readiness_completed
            ):
                readiness_completed = True
                order.append("publication_readiness")
                return _succeeded_worker()
            if (
                queue_name == "claim_embedding"
                and analytics_completed
                and not claim_embedding_completed
            ):
                claim_embedding_completed = True
                order.append("claim_embedding")
                release_analysis.set()
                return _succeeded_worker()
        return SimpleNamespace(released_lease_job_ids=[], terminal_status="idle")

    result = run_supervisor_once(
        _request(
            max_parallel_workers=2,
            max_total_jobs=5,
            max_jobs_per_queue=1,
            max_runtime_seconds=5,
        ),
        _ctx(),
        dependencies=_dependencies(worker),
    )

    assert result.completed_job_count == 5
    assert order == [
        "report_render",
        "analytics_projection",
        "publication_readiness",
        "claim_embedding",
        "report_analysis",
    ]


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
    dependencies = replace(_dependencies(worker), acquire_lease=acquire_lease)

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
    dependencies = replace(_dependencies(worker), acquire_lease=acquire_lease)

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

    dependencies = replace(_dependencies(worker), materialize_outbox=materialize_outbox)
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
