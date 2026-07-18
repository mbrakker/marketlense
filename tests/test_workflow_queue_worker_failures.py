from __future__ import annotations

import pytest

from src.contracts.workflow_queue import (
    WORKFLOW_QUEUE_NAMES,
    BriefingGenerationPayload,
    BriefingOpportunityPayload,
    ClaimEmbeddingPayload,
    CoverGenerationPayload,
    MaintenancePayload,
    PublicationReadinessPayload,
    PublisherDiscoveryPayload,
    SignalCandidatePayload,
    SignalGenerationPayload,
    WordPressProjectionPayload,
    WordPressPublishPayload,
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
    return new_run_context(task_id="workflow-queue-worker-failure-test")


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


@pytest.mark.parametrize(
    ("queue_name", "job_type", "payload", "expected_status", "error_code"),
    [
        (
            "publisher_discovery",
            "publisher_discovery.v1",
            PublisherDiscoveryPayload(
                publisher_id="publisher-1", discovery_policy_version="v1"
            ),
            "dead_letter",
            "workflow_queue_discovery_input_incomplete",
        ),
        (
            "publication_readiness",
            "publication_readiness.v1",
            PublicationReadinessPayload(
                entity_type="report",
                entity_package_reference="retained:package",
                package_checksum="package-hash",
                validation_reference="retained:validation",
            ),
            "dead_letter",
            "workflow_queue_publication_readiness_incomplete",
        ),
        (
            "briefing_opportunity",
            "briefing_opportunity.v1",
            BriefingOpportunityPayload(
                topic="rates",
                rolling_window="2026-W29",
                source_hashes=["source-a"],
                briefing_policy_version="v1",
                attributes={"publisher_ids": "not-a-list"},  # type: ignore[dict-item]
            ),
            "dead_letter",
            "workflow_queue_briefing_publishers_invalid",
        ),
        (
            "signal_candidate",
            "signal_candidate.v1",
            SignalCandidatePayload(
                report_id="report-1",
                projection_reference="projection:report-1",
                signal_selection_policy_version="v1",
                input_reference="projection:report-1",
                input_content_hash="projection-hash",
                attributes={"topic": "rates", "max_signals": "not-an-int"},
            ),
            "dead_letter",
            "workflow_queue_attribute_invalid",
        ),
        (
            "claim_embedding",
            "claim_embedding.v1",
            ClaimEmbeddingPayload(
                claim_id="claim-1",
                embedding_row_id="embedding-1",
                model_version="text-embedding-3-small",
                input_reference="analytics:claim:claim-1",
                input_content_hash="claim-hash",
                attributes={"dry_run": True, "limit": "not-an-int"},
            ),
            "dead_letter",
            "workflow_queue_attribute_invalid",
        ),
        (
            "wordpress_publish",
            "wordpress_publish.v1",
            WordPressPublishPayload(
                entity_type="briefing",
                entity_package_reference="missing:briefing-artifact",
                package_checksum="package-hash",
                approval_id="not-an-approval",
                input_reference="missing:briefing-artifact",
                input_content_hash="package-hash",
            ),
            "blocked",
            "stale_approval",
        ),
        (
            "wordpress_projection",
            "wordpress_projection.v1",
            WordPressProjectionPayload(
                entity_type="briefing",
                wordpress_id="123",
                published_entity_reference="",
                input_content_hash="package-hash",
            ),
            "dead_letter",
            "workflow_queue_wordpress_projection_input_incomplete",
        ),
        (
            "signal_generation",
            "signal_generation.v1",
            SignalGenerationPayload(),
            "dead_letter",
            "workflow_queue_signal_generation_input_incomplete",
        ),
        (
            "briefing_generation",
            "briefing_generation.v1",
            BriefingGenerationPayload(),
            "dead_letter",
            "workflow_queue_briefing_generation_input_incomplete",
        ),
        (
            "cover_generation",
            "cover_generation.v1",
            CoverGenerationPayload(entity_type="signal"),
            "dead_letter",
            "workflow_queue_cover_generation_input_incomplete",
        ),
    ],
)
def test_worker_fails_closed_for_invalid_queue_inputs(
    tmp_path,
    queue_name,
    job_type,
    payload,
    expected_status,
    error_code,
) -> None:
    db = str(tmp_path / "state.sqlite")
    job, _ = enqueue_workflow_job(
        db,
        WorkflowJobSubmission(
            schema_version="1.0",
            queue_name=queue_name,
            job_type=job_type,
            payload=payload,
            idempotency_key=f"{job_type}:invalid",
            deduplication_scope="queue-worker-invalid-input",
        ),
        _ctx(),
    )

    outcome = run_workflow_worker_once(
        state_db=db,
        queue_name=queue_name,
        worker_id="worker-1",
        ctx=_ctx(),
    )

    assert outcome.terminal_status == expected_status
    assert get_workflow_job(db, job.job_id, _ctx()).error_code == error_code


@pytest.mark.parametrize(
    ("error_code", "retryable", "expected_status"),
    [
        ("report_pipeline_pdf_budget_stop", True, "budget_deferred"),
        ("cross_report_prompt_budget_exceeded", False, "dead_letter"),
    ],
)
def test_worker_classifies_canonical_pipeline_budget_stop_and_immutable_input(
    tmp_path,
    error_code: str,
    retryable: bool,
    expected_status: str,
) -> None:
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
            idempotency_key=f"publisher-1:{error_code}",
            deduplication_scope="publisher-discovery-error-classification",
        ),
        _ctx(),
    )

    def limited_handler(*_args):
        raise AppError(
            code=error_code,
            message="controlled worker classification input",
            retryable=retryable,
        )

    registration = default_workflow_queue_registry()[
        ("publisher_discovery", "publisher_discovery.v1")
    ]
    registry = {
        (
            "publisher_discovery",
            "publisher_discovery.v1",
        ): WorkflowQueueHandlerRegistration(
            **{**registration.__dict__, "handler": limited_handler}
        )
    }
    outcome = run_workflow_worker_once(
        state_db=db,
        queue_name="publisher_discovery",
        worker_id="worker-1",
        ctx=_ctx(),
        registry=registry,
    )

    assert outcome.terminal_status == expected_status
    assert get_workflow_job(db, job.job_id, _ctx()).status == expected_status
