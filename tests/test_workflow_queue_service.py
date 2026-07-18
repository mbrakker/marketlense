from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import pytest

from src.contracts.workflow_queue import (
    BriefingGenerationPayload,
    PublisherDiscoveryPayload,
    ReportAcquisitionPayload,
    WordPressPublishPayload,
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
    materialize_workflow_outbox,
    record_publication_readiness,
    release_expired_workflow_leases,
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
