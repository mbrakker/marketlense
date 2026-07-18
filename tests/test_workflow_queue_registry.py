from __future__ import annotations

from src.contracts.workflow_queue import (
    WORKFLOW_QUEUE_NAMES,
    MaintenancePayload,
    PublicationReadinessPayload,
    PublisherDiscoveryPayload,
    WorkflowJobSubmission,
)
from src.orchestrators.workflow_queue_orchestrator import (
    WorkflowQueueHandlerRegistration,
    default_workflow_queue_registry,
)
from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once
from src.services.workflow_queue_service import enqueue_workflow_job, get_workflow_job
from src.utils.errors import AppError
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="workflow-queue-registry-test")


def test_registry_covers_each_canonical_queue_once_with_typed_job_name() -> None:
    registry = default_workflow_queue_registry()
    assert {queue for queue, _ in registry} == set(WORKFLOW_QUEUE_NAMES)
    assert len(registry) == len(WORKFLOW_QUEUE_NAMES)
    for (queue_name, job_type), registration in registry.items():
        assert job_type == f"{queue_name}.v1"
        assert registration.payload_type is not object
        assert registration.budget_profile
        assert registration.result_type is not object
        assert len(registration.allowed_downstream_job_types) == len(
            set(registration.allowed_downstream_job_types)
        )


def test_worker_claims_runs_and_completes_a_verified_reference_job(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(
        db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="vector_retention",
            job_type="vector_retention.v1",
            payload=MaintenancePayload(
                subject_id="verified-artifact",
                input_reference="verified:inventory-snapshot",
                input_content_hash="snapshot-hash",
            ),
            idempotency_key="publisher-1:v1",
            deduplication_scope="vector-retention",
        ),
        _ctx(),
    )

    outcome = run_workflow_worker_once(
        state_db=db,
        queue_name="vector_retention",
        worker_id="worker-1",
        ctx=_ctx(),
    )

    assert outcome.claimed_job_id == job.job_id
    assert outcome.terminal_status == "succeeded"
    completed = get_workflow_job(db, job.job_id, _ctx())
    assert completed.status == "succeeded"
    assert completed.output_reference == "verified:inventory-snapshot"


def test_operational_discovery_handler_fails_closed_without_an_insights_url(
    tmp_path,
) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(
        db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="publisher_discovery",
            job_type="publisher_discovery.v1",
            payload=PublisherDiscoveryPayload(
                publisher_id="publisher-1", discovery_policy_version="v1"
            ),
            idempotency_key="publisher-1:incomplete",
            deduplication_scope="publisher_discovery",
        ),
        _ctx(),
    )

    outcome = run_workflow_worker_once(
        state_db=db,
        queue_name="publisher_discovery",
        worker_id="worker-1",
        ctx=_ctx(),
    )

    assert outcome.terminal_status == "dead_letter"
    assert get_workflow_job(db, job.job_id, _ctx()).error_code == (
        "workflow_queue_discovery_input_incomplete"
    )


def test_publication_readiness_handler_fails_closed_without_lineage(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(
        db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="publication_readiness",
            job_type="publication_readiness.v1",
            payload=PublicationReadinessPayload(
                entity_type="report",
                entity_package_reference="retained:package",
                package_checksum="package-hash",
                validation_reference="retained:validation",
            ),
            idempotency_key="package-hash",
            deduplication_scope="publication-readiness",
        ),
        _ctx(),
    )

    outcome = run_workflow_worker_once(
        state_db=db,
        queue_name="publication_readiness",
        worker_id="worker-1",
        ctx=_ctx(),
    )

    assert outcome.terminal_status == "dead_letter"
    assert get_workflow_job(db, job.job_id, _ctx()).error_code == (
        "workflow_queue_publication_readiness_incomplete"
    )


def test_worker_classifies_canonical_pipeline_budget_stop_as_deferral(tmp_path) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(
        db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name="publisher_discovery",
            job_type="publisher_discovery.v1",
            payload=PublisherDiscoveryPayload(
                publisher_id="publisher-1",
                insights_url="https://example.test/insights",
                discovery_policy_version="v1",
                input_reference="verified:inventory-snapshot",
                input_content_hash="snapshot-hash",
            ),
            idempotency_key="publisher-1:budget",
            deduplication_scope="publisher_discovery",
        ),
        _ctx(),
    )

    def budget_limited(*_args):
        raise AppError(
            code="report_pipeline_pdf_budget_stop",
            message="blocked by budget",
            retryable=True,
        )

    registration = default_workflow_queue_registry()[
        ("publisher_discovery", "publisher_discovery.v1")
    ]
    registry_key = ("publisher_discovery", "publisher_discovery.v1")
    registry = {
        registry_key: WorkflowQueueHandlerRegistration(
            **{**registration.__dict__, "handler": budget_limited}
        )
    }
    outcome = run_workflow_worker_once(
        state_db=db,
        queue_name="publisher_discovery",
        worker_id="worker-1",
        ctx=_ctx(),
        registry=registry,
    )

    assert outcome.terminal_status == "budget_deferred"
    assert get_workflow_job(db, job.job_id, _ctx()).status == "budget_deferred"
