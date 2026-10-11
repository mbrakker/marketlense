from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier

import pytest

from src.contracts.workflow_queue import (
    BriefingGenerationPayload,
    PublisherDiscoveryPayload,
    SourceIngestPayload,
    ReportAcquisitionPayload,
    WordPressPublishPayload,
    WorkflowArtifactReference,
    WorkflowJobSubmission,
    WorkflowStageResult,
)
from src.services.workflow_queue_service import (
    approve_publication_package,
    cancel_workflow_job,
    claim_next_workflow_job,
    complete_workflow_job,
    enqueue_workflow_job,
    fail_workflow_job,
    freeze_briefing_opportunity,
    get_workflow_job,
    get_workflow_queue_control,
    heartbeat_workflow_job,
    list_workflow_job_attempts,
    materialize_workflow_outbox,
    record_publication_readiness,
    release_expired_workflow_leases,
    requeue_workflow_job,
    reconcile_workflow_queue,
    set_workflow_queue_control,
    start_workflow_job,
    upsert_briefing_opportunity,
)
from src.utils.errors import AppError
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="workflow-queue-test")


def _submission(
    *,
    key: str = "one",
    priority: int = 0,
    available_at_utc: str = "2026-07-18T00:00:00+00:00",
) -> WorkflowJobSubmission:
    return WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="publisher_discovery",
        job_type="publisher_discovery.v1",
        payload=PublisherDiscoveryPayload(
            publisher_id="publisher-1",
            insights_url="https://example.test/insights",
            discovery_policy_version="v1",
            input_reference="snapshot:publisher-1",
            input_content_hash="source-hash",
        ),
        idempotency_key=key,
        deduplication_scope="publisher_discovery.test",
        priority=priority,
        available_at_utc=available_at_utc,
    )


def _start(db: str, job_id: str, worker_id: str = "worker-1"):
    ctx = _ctx()
    claimed = claim_next_workflow_job(
        db,
        "publisher_discovery",
        worker_id,
        ctx,
        now_utc="2026-07-18T00:00:01+00:00",
    )
    assert claimed is not None and claimed.job_id == job_id
    return start_workflow_job(
        db, job_id, worker_id, ctx, now_utc="2026-07-18T00:00:02+00:00"
    )


def test_enqueue_deduplicates_concurrent_submissions(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")

    def submit() -> tuple[str, bool]:
        job, created = enqueue_workflow_job(
            db,
            _submission(key="dedupe"),
            _ctx(),
            now_utc="2026-07-18T00:00:00+00:00",
        )
        return job.job_id, created

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))

    assert len({item[0] for item in results}) == 1
    assert sum(1 for _, created in results if created) == 1


def test_enqueue_rejects_same_key_with_incompatible_input(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    original, created = enqueue_workflow_job(db, _submission(key="same-key"), _ctx())
    incompatible = replace(
        _submission(key="same-key"),
        payload=replace(
            _submission(key="same-key").payload,
            input_content_hash="different-source-hash",
        ),
    )

    assert created is True
    with pytest.raises(AppError) as error:
        enqueue_workflow_job(db, incompatible, _ctx())

    assert error.value.code == "workflow_queue_idempotency_conflict"
    assert error.value.retryable is False
    assert "input_content_hash" in error.value.context["incompatible_fields"]
    persisted = get_workflow_job(db, original.job_id, _ctx())
    assert persisted is not None
    assert persisted.input_content_hash == "source-hash"


def test_enqueue_reuses_compatible_job_when_only_schedule_changes(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    original, _ = enqueue_workflow_job(
        db,
        _submission(key="same-key", priority=1),
        _ctx(),
        now_utc="2026-07-18T00:00:00+00:00",
    )
    compatible = replace(
        _submission(
            key="same-key",
            priority=9,
            available_at_utc="2026-07-18T00:05:00+00:00",
        ),
        max_attempts=7,
    )

    reused, created = enqueue_workflow_job(
        db, compatible, _ctx(), now_utc="2026-07-18T00:01:00+00:00"
    )

    assert (reused.job_id, created) == (original.job_id, False)


@pytest.mark.parametrize(
    ("changed_field", "expected_field"),
    [
        ("queue_name", "queue_name"),
        ("job_type", "job_type"),
        ("policy_version", "payload"),
        ("artifact_reference", "required_artifact_references"),
        ("entity_identity", "publisher_id"),
    ],
)
def test_enqueue_rejects_reused_key_for_semantic_changes(
    tmp_path, changed_field: str, expected_field: str
) -> None:
    db = str(tmp_path / "state.sqlite")
    key = f"semantic-change-{changed_field}"
    original = _submission(key=key)
    enqueue_workflow_job(db, original, _ctx())
    if changed_field == "queue_name":
        changed = replace(
            original,
            queue_name="source_ingest",
            job_type="source_ingest.v1",
            payload=SourceIngestPayload(
                source_identity_id="identity-1",
                source_artifact_reference="artifact:source.pdf",
                source_content_hash="source-hash",
                report_id="report-1",
                input_reference="snapshot:report-1",
                input_content_hash="source-hash",
            ),
        )
    elif changed_field == "job_type":
        changed = replace(original, job_type="publisher_discovery.v2")
    elif changed_field == "policy_version":
        changed = replace(
            original,
            payload=replace(original.payload, discovery_policy_version="v2"),
        )
    elif changed_field == "artifact_reference":
        changed = replace(
            original,
            payload=replace(
                original.payload,
                required_artifact_references=[
                    WorkflowArtifactReference(
                        kind="source_pdf",
                        reference="artifact:new.pdf",
                        content_hash="new-hash",
                    )
                ],
            ),
        )
    else:
        changed = replace(original, publisher_id="publisher-2")

    with pytest.raises(AppError) as error:
        enqueue_workflow_job(db, changed, _ctx())

    assert error.value.code == "workflow_queue_idempotency_conflict"
    assert expected_field in error.value.context["incompatible_fields"]


def test_concurrent_incompatible_submissions_keep_one_immutable_job(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    barrier = Barrier(2)

    def submit(content_hash: str):
        submission = replace(
            _submission(key="concurrent-semantic-change"),
            payload=replace(
                _submission(key="concurrent-semantic-change").payload,
                input_content_hash=content_hash,
            ),
        )
        barrier.wait()
        try:
            job, created = enqueue_workflow_job(db, submission, _ctx())
            return ("created" if created else "reused", job.job_id, content_hash)
        except AppError as exc:
            return ("conflict", exc.code, content_hash)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, ["hash-a", "hash-b"]))

    assert sorted(item[0] for item in outcomes) == ["conflict", "created"]
    assert next(item[1] for item in outcomes if item[0] == "conflict") == (
        "workflow_queue_idempotency_conflict"
    )
    persisted = get_workflow_job(db, outcomes[0][1], _ctx())
    if persisted is None:
        persisted = get_workflow_job(db, outcomes[1][1], _ctx())
    assert persisted is not None
    assert persisted.input_content_hash in {"hash-a", "hash-b"}


def test_claim_orders_by_priority_then_due_time(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    low, _ = enqueue_workflow_job(db, _submission(key="low", priority=1), _ctx())
    high, _ = enqueue_workflow_job(db, _submission(key="high", priority=5), _ctx())
    claimed = claim_next_workflow_job(
        db,
        "publisher_discovery",
        "worker-1",
        _ctx(),
        now_utc="2026-07-18T00:00:01+00:00",
    )
    assert claimed is not None and claimed.job_id == high.job_id
    assert claimed.job_id != low.job_id


def test_atomic_claim_allows_only_one_worker(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    enqueue_workflow_job(db, _submission(), _ctx())

    def claim(worker: str):
        return claim_next_workflow_job(
            db,
            "publisher_discovery",
            worker,
            _ctx(),
            now_utc="2026-07-18T00:00:01+00:00",
        )

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(claim, ["worker-1", "worker-2"]))
    assert sum(item is not None for item in outcomes) == 1


def test_heartbeat_and_expired_lease_reject_stale_completion(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(db, _submission(), _ctx())
    running = _start(db, job.job_id)
    heartbeated = heartbeat_workflow_job(
        db,
        running.job_id,
        "worker-1",
        _ctx(),
        now_utc="2026-07-18T00:01:00+00:00",
    )
    assert heartbeated.lease_expires_at_utc > "2026-07-18T00:01:00+00:00"
    released = release_expired_workflow_leases(
        db,
        _ctx(),
        now_utc="2026-07-19T00:00:00+00:00",
    )
    assert running.job_id in released
    with pytest.raises(AppError) as error:
        complete_workflow_job(
            db,
            running.job_id,
            "worker-1",
            WorkflowStageResult(
                output_reference="snapshot",
                output_content_hash="hash",
                output_verified=True,
            ),
            [],
            _ctx(),
            now_utc="2026-07-19T00:00:01+00:00",
        )
    assert error.value.code == "workflow_queue_status_invalid"


def test_expired_running_lease_closes_attempt_and_terminalizes_exhaustion(
    tmp_path,
) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(
        db, replace(_submission(key="lease-expiry"), max_attempts=2), _ctx()
    )

    first_claim = claim_next_workflow_job(
        db,
        "publisher_discovery",
        "worker-1",
        _ctx(),
        now_utc="2026-07-18T00:00:01+00:00",
    )
    assert first_claim is not None
    start_workflow_job(
        db, job.job_id, "worker-1", _ctx(), now_utc="2026-07-18T00:00:02+00:00"
    )
    expired_first = release_expired_workflow_leases(
        db, _ctx(), now_utc="2026-07-19T00:00:00+00:00"
    )
    after_first = get_workflow_job(db, job.job_id, _ctx())
    first_attempt = list_workflow_job_attempts(db, job.job_id, _ctx())[0]

    assert expired_first == [job.job_id]
    assert after_first.status == "pending"
    assert after_first.attempt_count == 1
    assert first_attempt.completed_at_utc == "2026-07-19T00:00:00+00:00"
    assert first_attempt.outcome == "lease_expired"
    assert first_attempt.error_code == "workflow_queue_lease_expired"
    assert (
        release_expired_workflow_leases(db, _ctx(), now_utc="2026-07-19T00:00:00+00:00")
        == []
    )

    second_claim = claim_next_workflow_job(
        db,
        "publisher_discovery",
        "worker-2",
        _ctx(),
        now_utc="2026-07-19T00:00:01+00:00",
    )
    assert second_claim is not None and second_claim.job_id == job.job_id
    start_workflow_job(
        db, job.job_id, "worker-2", _ctx(), now_utc="2026-07-19T00:00:02+00:00"
    )

    expired_final = release_expired_workflow_leases(
        db, _ctx(), now_utc="2026-07-20T00:00:00+00:00"
    )
    terminal = get_workflow_job(db, job.job_id, _ctx())
    attempts = list_workflow_job_attempts(db, job.job_id, _ctx())
    assert expired_final == [job.job_id]
    assert terminal.status == "dead_letter"
    assert terminal.error_code == "workflow_queue_attempts_exhausted"
    assert terminal.terminal_reason == "lease_expired_attempts_exhausted"
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    assert [attempt.outcome for attempt in attempts] == [
        "lease_expired",
        "lease_expired",
    ]


def test_expired_lease_before_start_does_not_consume_an_attempt(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(
        db, replace(_submission(key="lease-before-start"), max_attempts=1), _ctx()
    )
    claimed = claim_next_workflow_job(
        db,
        "publisher_discovery",
        "worker-1",
        _ctx(),
        now_utc="2026-07-18T00:00:01+00:00",
    )
    assert claimed is not None and claimed.job_id == job.job_id

    released = release_expired_workflow_leases(
        db, _ctx(), now_utc="2026-07-19T00:00:00+00:00"
    )
    pending = get_workflow_job(db, job.job_id, _ctx())
    assert released == [job.job_id]
    assert pending.status == "pending"
    assert pending.attempt_count == 0
    assert list_workflow_job_attempts(db, job.job_id, _ctx()) == []


def test_expired_worker_attempt_is_reclaimed_and_completed_by_restarted_worker(
    tmp_path,
) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(
        db, replace(_submission(key="worker-restart"), max_attempts=2), _ctx()
    )
    first = _start(db, job.job_id, worker_id="worker-before-crash")

    released = release_expired_workflow_leases(
        db, _ctx(), now_utc="2026-07-19T00:00:00+00:00"
    )
    assert released == [job.job_id]

    claimed = claim_next_workflow_job(
        db,
        "publisher_discovery",
        "worker-after-restart",
        _ctx(),
        now_utc="2026-07-19T00:00:01+00:00",
    )
    assert claimed is not None and claimed.job_id == first.job_id
    second = start_workflow_job(
        db,
        job.job_id,
        "worker-after-restart",
        _ctx(),
        now_utc="2026-07-19T00:00:02+00:00",
    )
    completed = complete_workflow_job(
        db,
        job.job_id,
        "worker-after-restart",
        WorkflowStageResult(
            output_reference="recovered-output",
            output_content_hash="recovered-hash",
            output_verified=True,
        ),
        [],
        _ctx(),
        now_utc="2026-07-19T00:00:03+00:00",
    )

    attempts = list_workflow_job_attempts(db, job.job_id, _ctx())
    assert second.attempt_count == 2
    assert completed.status == "succeeded"
    assert [attempt.worker_id for attempt in attempts] == [
        "worker-before-crash",
        "worker-after-restart",
    ]
    assert [attempt.outcome for attempt in attempts] == ["lease_expired", "succeeded"]


def test_retry_budget_defer_cancel_and_explicit_requeue(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(db, _submission(key="retry"), _ctx())
    _start(db, job.job_id)
    deferred = fail_workflow_job(
        db,
        job.job_id,
        "worker-1",
        AppError("budget_day_exhausted", "defer", retryable=True),
        _ctx(),
        now_utc="2026-07-18T00:00:03+00:00",
        budget_deferred=True,
    )
    assert deferred.status == "budget_deferred"
    with pytest.raises(AppError):
        cancel_workflow_job(db, job.job_id, "operator", _ctx())
    # A terminal attempt is the only state that requires explicit requeue.
    pending_job, _ = enqueue_workflow_job(db, _submission(key="cancel"), _ctx())
    cancelled = cancel_workflow_job(db, pending_job.job_id, "operator", _ctx())
    assert cancelled.status == "cancelled"


def test_explicit_requeue_grants_one_bounded_attempt_and_preserves_history(
    tmp_path,
) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(
        db, replace(_submission(key="requeue-once"), max_attempts=1), _ctx()
    )
    first = _start(db, job.job_id)
    failed = fail_workflow_job(
        db,
        first.job_id,
        "worker-1",
        AppError("worker_failed", "first attempt failed", retryable=False),
        _ctx(),
        now_utc="2026-07-18T00:00:03+00:00",
    )
    assert failed.status == "dead_letter"

    requeued = requeue_workflow_job(
        db, job.job_id, "operator", _ctx(), now_utc="2026-07-18T00:00:04+00:00"
    )
    assert requeued.status == "pending"
    assert requeued.attempt_count == 1
    assert requeued.max_attempts == 2
    with pytest.raises(AppError) as repeated:
        requeue_workflow_job(
            db,
            job.job_id,
            "operator",
            _ctx(),
            now_utc="2026-07-18T00:00:04+00:00",
        )
    assert repeated.value.code == "workflow_queue_requeue_invalid"

    claimed = claim_next_workflow_job(
        db,
        "publisher_discovery",
        "worker-2",
        _ctx(),
        now_utc="2026-07-18T00:00:05+00:00",
    )
    assert claimed is not None and claimed.job_id == job.job_id
    second = start_workflow_job(
        db,
        job.job_id,
        "worker-2",
        _ctx(),
        now_utc="2026-07-18T00:00:06+00:00",
    )
    terminal = fail_workflow_job(
        db,
        second.job_id,
        "worker-2",
        AppError("worker_failed_again", "second attempt failed", retryable=False),
        _ctx(),
        now_utc="2026-07-18T00:00:07+00:00",
    )

    attempts = list_workflow_job_attempts(db, job.job_id, _ctx())
    assert terminal.status == "dead_letter"
    assert terminal.attempt_count == terminal.max_attempts == 2
    assert [attempt.attempt_number for attempt in attempts] == [1, 2]
    assert [attempt.outcome for attempt in attempts] == ["dead_letter", "dead_letter"]
    with sqlite3.connect(db) as conn:
        details = conn.execute(
            "SELECT details_json FROM workflow_job_transitions "
            "WHERE job_id=? AND reason='operator_requeue'",
            (job.job_id,),
        ).fetchone()
    assert details is not None
    assert json.loads(details[0]) == {"granted_max_attempts": 2}


def test_pause_and_depth_controls_prevent_claim_or_unbounded_enqueue(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    control = get_workflow_queue_control(db, "publisher_discovery", _ctx())
    paused = set_workflow_queue_control(
        db,
        replace(
            control,
            mode="paused",
            enabled=False,
            emergency_stop_reason="maintenance",
            maximum_pending=1,
            updated_by="operator",
        ),
        _ctx(),
    )
    enqueue_workflow_job(db, _submission(key="one"), _ctx())
    assert (
        claim_next_workflow_job(
            db,
            paused.queue_name,
            "worker-1",
            _ctx(),
            now_utc="2026-07-18T00:00:01+00:00",
        )
        is None
    )
    with pytest.raises(AppError) as error:
        enqueue_workflow_job(db, _submission(key="two"), _ctx())
    assert error.value.code == "workflow_queue_at_capacity"


def test_completion_outbox_materialises_one_effective_child(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    parent, _ = enqueue_workflow_job(db, _submission(), _ctx())
    _start(db, parent.job_id)
    child = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="report_acquisition",
        job_type="report_acquisition.v1",
        payload=ReportAcquisitionPayload(
            source_url="https://example.test/report.pdf",
            acquisition_policy_version="v1",
            input_reference="source:https://example.test/report.pdf",
            input_content_hash="source-hash",
        ),
        idempotency_key="source:v1",
        deduplication_scope="report_acquisition",
        root_workflow_id=parent.root_workflow_id,
        parent_job_id=parent.job_id,
    )
    complete_workflow_job(
        db,
        parent.job_id,
        "worker-1",
        WorkflowStageResult(
            output_reference="snapshot",
            output_content_hash="snapshot-hash",
            output_verified=True,
        ),
        [child],
        _ctx(),
        now_utc="2026-07-18T00:00:03+00:00",
    )
    materialised = materialize_workflow_outbox(db, "outbox-worker", _ctx())
    assert len(materialised) == 1
    assert materialize_workflow_outbox(db, "outbox-worker", _ctx()) == []
    assert get_workflow_job(db, materialised[0], _ctx()).parent_job_id == parent.job_id


@pytest.mark.parametrize(
    ("attempt_count", "max_attempts", "expected_status"),
    [(0, 3, "retry_wait"), (2, 3, "dead_letter")],
)
def test_reconciliation_reclaims_expired_outbox_lease(
    tmp_path, attempt_count: int, max_attempts: int, expected_status: str
) -> None:
    db = str(tmp_path / "state.sqlite")
    parent, _ = enqueue_workflow_job(db, _submission(), _ctx())
    _start(db, parent.job_id)
    child = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="report_acquisition",
        job_type="report_acquisition.v1",
        payload=ReportAcquisitionPayload(
            source_url="https://example.test/report.pdf",
            acquisition_policy_version="v1",
            input_reference="source:https://example.test/report.pdf",
            input_content_hash="source-hash",
        ),
        idempotency_key="source:v1",
        deduplication_scope="report_acquisition",
        root_workflow_id=parent.root_workflow_id,
        parent_job_id=parent.job_id,
    )
    complete_workflow_job(
        db,
        parent.job_id,
        "worker-1",
        WorkflowStageResult(
            output_reference="snapshot",
            output_content_hash="snapshot-hash",
            output_verified=True,
        ),
        [child],
        _ctx(),
        now_utc="2026-07-18T00:00:03+00:00",
    )
    with sqlite3.connect(db) as conn:
        event_id = conn.execute("SELECT event_id FROM workflow_outbox").fetchone()[0]
        conn.execute(
            "UPDATE workflow_outbox SET status='leased',lease_owner='crashed-worker',"
            "lease_expires_at_utc='2026-07-18T00:01:00+00:00',attempt_count=?,"
            "max_attempts=? "
            "WHERE event_id=?",
            (attempt_count, max_attempts, event_id),
        )

    reconcile_workflow_queue(db, _ctx(), now_utc="2026-07-18T00:01:01+00:00")

    with sqlite3.connect(db) as conn:
        status, attempts, error_code = conn.execute(
            "SELECT status,attempt_count,error_code FROM workflow_outbox "
            "WHERE event_id=?",
            (event_id,),
        ).fetchone()
    assert (status, attempts, error_code) == (
        expected_status,
        attempt_count + 1,
        "workflow_outbox_lease_expired",
    )
    if expected_status == "retry_wait":
        materialised = materialize_workflow_outbox(
            db,
            "outbox-recovery-worker",
            _ctx(),
            now_utc="2026-07-18T00:02:02+00:00",
        )
        assert len(materialised) == 1
        assert (
            materialize_workflow_outbox(
                db,
                "outbox-recovery-worker",
                _ctx(),
                now_utc="2026-07-18T00:02:03+00:00",
            )
            == []
        )
        with sqlite3.connect(db) as conn:
            status, job_id, child_count = conn.execute(
                "SELECT o.status,o.materialised_job_id,"
                "(SELECT COUNT(*) FROM workflow_jobs WHERE deduplication_scope=? "
                "AND idempotency_key=?) FROM workflow_outbox o WHERE o.event_id=?",
                (child.deduplication_scope, child.idempotency_key, event_id),
            ).fetchone()
        assert status == "materialised"
        assert job_id == materialised[0]
        assert child_count == 1


def test_reconciliation_links_child_created_before_outbox_ack(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    parent, _ = enqueue_workflow_job(db, _submission(), _ctx())
    _start(db, parent.job_id)
    child = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="report_acquisition",
        job_type="report_acquisition.v1",
        payload=ReportAcquisitionPayload(
            source_url="https://example.test/report.pdf",
            acquisition_policy_version="v1",
            input_reference="source:https://example.test/report.pdf",
            input_content_hash="source-hash",
        ),
        idempotency_key="source:v1",
        deduplication_scope="report_acquisition",
        root_workflow_id=parent.root_workflow_id,
        parent_job_id=parent.job_id,
    )
    complete_workflow_job(
        db,
        parent.job_id,
        "worker-1",
        WorkflowStageResult(
            output_reference="snapshot",
            output_content_hash="snapshot-hash",
            output_verified=True,
        ),
        [child],
        _ctx(),
        now_utc="2026-07-18T00:00:03+00:00",
    )
    existing_child, created = enqueue_workflow_job(db, child, _ctx())
    assert created is True
    with sqlite3.connect(db) as conn:
        event_id = conn.execute("SELECT event_id FROM workflow_outbox").fetchone()[0]
        conn.execute(
            "UPDATE workflow_outbox SET status='leased',lease_owner='crashed-worker',"
            "lease_expires_at_utc='2026-07-18T00:01:00+00:00',attempt_count=2,"
            "max_attempts=3 WHERE event_id=?",
            (event_id,),
        )

    reconcile_workflow_queue(db, _ctx(), now_utc="2026-07-18T00:01:01+00:00")

    with sqlite3.connect(db) as conn:
        status, job_id, attempts = conn.execute(
            "SELECT status,materialised_job_id,attempt_count FROM workflow_outbox "
            "WHERE event_id=?",
            (event_id,),
        ).fetchone()
        child_count = conn.execute(
            "SELECT COUNT(*) FROM workflow_jobs WHERE deduplication_scope=? "
            "AND idempotency_key=?",
            (child.deduplication_scope, child.idempotency_key),
        ).fetchone()[0]
    assert (status, job_id, attempts, child_count) == (
        "materialised",
        existing_child.job_id,
        3,
        1,
    )


def test_outbox_materializer_cannot_ack_a_renewed_lease(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    parent, _ = enqueue_workflow_job(db, _submission(), _ctx())
    _start(db, parent.job_id)
    child = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="report_acquisition",
        job_type="report_acquisition.v1",
        payload=ReportAcquisitionPayload(
            source_url="https://example.test/report.pdf",
            acquisition_policy_version="v1",
            input_reference="source:https://example.test/report.pdf",
            input_content_hash="source-hash",
        ),
        idempotency_key="source:v1",
        deduplication_scope="report_acquisition",
        root_workflow_id=parent.root_workflow_id,
        parent_job_id=parent.job_id,
    )
    complete_workflow_job(
        db,
        parent.job_id,
        "worker-1",
        WorkflowStageResult(
            output_reference="snapshot",
            output_content_hash="snapshot-hash",
            output_verified=True,
        ),
        [child],
        _ctx(),
        now_utc="2026-07-18T00:00:03+00:00",
    )
    with sqlite3.connect(db) as conn:
        event_id = conn.execute("SELECT event_id FROM workflow_outbox").fetchone()[0]
        conn.execute(
            """CREATE TRIGGER renew_outbox_lease_after_child_insert
            AFTER INSERT ON workflow_jobs
            BEGIN
                UPDATE workflow_outbox
                SET lease_owner='renewed-owner',
                    lease_expires_at_utc='2026-07-18T00:05:00+00:00'
                WHERE event_id='"""
            + str(event_id)
            + """' AND status='leased';
            END;"""
        )

    assert (
        materialize_workflow_outbox(
            db,
            "outbox-worker",
            _ctx(),
            now_utc="2026-07-18T00:01:00+00:00",
        )
        == []
    )
    with sqlite3.connect(db) as conn:
        status, owner, job_id = conn.execute(
            "SELECT status,lease_owner,materialised_job_id FROM workflow_outbox "
            "WHERE event_id=?",
            (event_id,),
        ).fetchone()
    assert (status, owner, job_id) == ("leased", "renewed-owner", "")

    reconcile_workflow_queue(db, _ctx(), now_utc="2026-07-18T00:05:01+00:00")
    recovered = materialize_workflow_outbox(
        db,
        "outbox-worker-2",
        _ctx(),
        now_utc="2026-07-18T00:06:02+00:00",
    )
    assert len(recovered) == 1
    with sqlite3.connect(db) as conn:
        status, job_id, child_count = conn.execute(
            "SELECT o.status,o.materialised_job_id,"
            "(SELECT COUNT(*) FROM workflow_jobs WHERE deduplication_scope=? "
            "AND idempotency_key=?) FROM workflow_outbox o WHERE o.event_id=?",
            (child.deduplication_scope, child.idempotency_key, event_id),
        ).fetchone()
    assert status == "materialised"
    assert job_id == recovered[0]
    assert child_count == 1


def test_approval_and_briefing_opportunity_are_durable_and_idempotent(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    readiness = record_publication_readiness(
        db,
        package_checksum="package-hash",
        entity_type="report",
        package_reference="output/report.html",
        validation_reference="validation",
        lineage_reference="lineage",
        required_asset_status="ready",
        readiness_status="awaiting_review",
        reason="",
        ctx=_ctx(),
    )
    publish = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="wordpress_publish",
        job_type="wordpress_publish.v1",
        payload=WordPressPublishPayload(
            entity_type="report",
            entity_package_reference=readiness.package_reference,
            package_checksum=readiness.package_checksum,
            approval_id="assigned-by-approval",
            input_reference=readiness.package_reference,
            input_content_hash=readiness.package_checksum,
            dry_run=True,
        ),
        idempotency_key="wordpress:package-hash",
        deduplication_scope="wordpress_publish",
    )
    approved = approve_publication_package(
        db,
        package_checksum="package-hash",
        actor_id="operator-1",
        note="reviewed",
        publish_submission=publish,
        ctx=_ctx(),
    )
    repeat = approve_publication_package(
        db,
        package_checksum="package-hash",
        actor_id="operator-2",
        note="repeat",
        publish_submission=publish,
        ctx=_ctx(),
    )
    assert approved.approval_id == repeat.approval_id
    materialized = materialize_workflow_outbox(db, "outbox-worker", _ctx())
    assert len(materialized) == 1
    published_job = get_workflow_job(db, materialized[0], _ctx())
    assert published_job is not None
    assert approved.approval_id in published_job.payload_json
    assert '"dry_run":true' in published_job.payload_json
    opportunity = upsert_briefing_opportunity(
        db,
        topic="retail",
        geography="EU",
        rolling_window="30d",
        briefing_policy_version="v1",
        source_hashes=["a", "b", "a"],
        publisher_ids=["publisher-a", "publisher-b"],
        minimum_distinct_reports=2,
        minimum_publisher_diversity=2,
        ctx=_ctx(),
    )
    assert opportunity.status == "eligible"
    assert opportunity.source_hashes == ["a", "b"]


def test_eligible_briefing_freezes_source_set_once(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    opportunity = upsert_briefing_opportunity(
        db,
        topic="retail",
        geography="EU",
        rolling_window="30d",
        briefing_policy_version="v1",
        source_hashes=["a", "b"],
        publisher_ids=["publisher-a", "publisher-b"],
        minimum_distinct_reports=2,
        minimum_publisher_diversity=2,
        ctx=_ctx(),
    )
    generation = WorkflowJobSubmission(
        schema_version="1.0",
        queue_name="briefing_generation",
        job_type="briefing_generation.v1",
        payload=BriefingGenerationPayload(
            opportunity_id=opportunity.opportunity_id,
            frozen_source_manifest="manifest:retail:30d",
            selected_topic="retail",
            sorted_source_hashes=["a", "b"],
            input_reference="manifest:retail:30d",
            input_content_hash="manifest-hash",
        ),
        idempotency_key="briefing:retail:a:b:v1",
        deduplication_scope="briefing_generation",
    )
    frozen = freeze_briefing_opportunity(
        db,
        opportunity_id=opportunity.opportunity_id,
        frozen_source_manifest="manifest:retail:30d",
        generation_submission=generation,
        ctx=_ctx(),
    )
    repeat = freeze_briefing_opportunity(
        db,
        opportunity_id=opportunity.opportunity_id,
        frozen_source_manifest="ignored",
        generation_submission=generation,
        ctx=_ctx(),
    )
    assert frozen.status == "frozen"
    assert frozen.frozen_source_hashes == ["a", "b"]
    assert repeat.frozen_source_manifest == "manifest:retail:30d"
