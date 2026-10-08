from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path

import pytest

from src.contracts.report_store import ReportSourceRecordRequest
from src.contracts.run_context import RunContext
from src.contracts.workflow_queue import (
    MailboxDeliveryPayload,
    MaintenancePayload,
    PublisherDiscoveryPayload,
    PublisherDiscoveryResult,
    QueuePayload,
    ReportAcquisitionPayload,
    ReportSelectionPayload,
    SignalGenerationPayload,
    SourceIngestPayload,
    WordPressPublishPayload,
    WorkflowJob,
    WorkflowJobSubmission,
    WorkflowQueueName,
)
from src.orchestrators import workflow_queue_orchestrator as queue_orchestrator
from src.orchestrators.workflow_queue_orchestrator import (
    WorkflowQueueHandlerRegistration,
    WorkflowQueueHandlerResult,
)
from src.services.report_store_service import record_report_source
from src.utils.errors import AppError
from src.utils.logging import new_run_context
from tests._workflow_queue_registry_support import _isolated_app_config


def _ctx():
    return new_run_context(task_id="workflow-queue-registry-test")


def _workflow_job(
    *,
    queue_name: WorkflowQueueName = "vector_retention",
    job_type: str = "vector_retention.v1",
) -> WorkflowJob:
    return WorkflowJob(
        schema_version="1.0",
        job_id="workflow-job-1",
        queue_name=queue_name,
        job_type=job_type,
        job_schema_version="1.0",
        workflow_version="1.0",
        root_workflow_id="",
        parent_job_id="",
        trigger_event_id="",
        correlation_id="",
        entity_type="report",
        entity_id="report-1",
        publisher_id="publisher-1",
        source_identity_id="source-1",
        report_id="report-1",
        input_reference="retained:input",
        input_content_hash="input-hash",
        required_artifact_references=[],
        output_reference="",
        output_content_hash="",
        idempotency_key="workflow-job-1",
        deduplication_scope="test",
        priority=0,
        status="pending",
        available_at_utc="2026-07-18T00:00:00+00:00",
        attempt_count=0,
        max_attempts=3,
        lease_owner="",
        lease_expires_at_utc="",
        heartbeat_at_utc="",
        budget_profile="test",
        execution_plan_hash="plan-1",
        prompt_policy_version="",
        processing_version="queue-test.v1",
        created_at_utc="2026-07-18T00:00:00+00:00",
        updated_at_utc="2026-07-18T00:00:00+00:00",
        started_at_utc="",
        completed_at_utc="",
        error_code="",
        error_message_summary="",
        error_retryable=False,
        terminal_reason="",
        remediation_id="",
    )


def test_verified_reference_and_execution_boundary_are_typed_and_fail_closed() -> None:
    job = _workflow_job()
    payload = MaintenancePayload(
        subject_id="retained-artifact",
        input_reference="retained:artifact",
        input_content_hash="artifact-hash",
    )

    completed = queue_orchestrator.execute_workflow_queue_handler(job, payload, _ctx())

    assert completed.result.output_reference == "retained:artifact"
    assert completed.result.output_content_hash == "artifact-hash"
    assert completed.result.output_verified is True
    with pytest.raises(AppError, match="requires a retained reference"):
        queue_orchestrator._verified_reference_handler(
            job, MaintenancePayload(subject_id="missing-reference"), _ctx()
        )
    with pytest.raises(AppError, match="not registered"):
        queue_orchestrator.resolve_workflow_queue_handler("unknown", "unknown.v1")
    with pytest.raises(AppError, match="does not match"):
        queue_orchestrator.execute_workflow_queue_handler(
            job,
            PublisherDiscoveryPayload(
                publisher_id="publisher-1",
                insights_url="https://example.test/insights",
                discovery_policy_version="v1",
            ),
            _ctx(),
        )


def test_execution_boundary_rejects_a_registered_handler_with_disallowed_fanout() -> (
    None
):
    job = _workflow_job()
    parent_payload = MaintenancePayload(
        subject_id="retained-artifact",
        input_reference="retained:artifact",
        input_content_hash="artifact-hash",
    )

    def disallowed_handler(
        _job: WorkflowJob,
        _payload: QueuePayload,
        _ctx_value: RunContext,
    ) -> WorkflowQueueHandlerResult:
        return WorkflowQueueHandlerResult(
            result=queue_orchestrator.WorkflowStageResult(
                output_reference="retained:artifact",
                output_content_hash="artifact-hash",
                output_verified=True,
            ),
            downstream=[
                WorkflowJobSubmission(
                    schema_version="1.0",
                    queue_name="publisher_discovery",
                    job_type="publisher_discovery.v1",
                    payload=PublisherDiscoveryPayload(
                        publisher_id="publisher-1",
                        insights_url="https://example.test/insights",
                        discovery_policy_version="v1",
                    ),
                    idempotency_key="forbidden-child",
                    deduplication_scope="test",
                )
            ],
        )

    registry = {
        ("vector_retention", "vector_retention.v1"): WorkflowQueueHandlerRegistration(
            queue_name="vector_retention",
            job_type="vector_retention.v1",
            payload_type=MaintenancePayload,
            result_type=queue_orchestrator.WorkflowStageResult,
            handler=disallowed_handler,
            default_retry_policy="test",
            default_lease_seconds=60,
            budget_profile="test",
            expected_external_effects=(),
            allowed_downstream_job_types=(),
        )
    }

    with pytest.raises(AppError, match="unapproved downstream"):
        queue_orchestrator.execute_workflow_queue_handler(
            job, parent_payload, _ctx(), registry=registry
        )


def test_execution_boundary_normalizes_a_registered_result_contract() -> None:
    job = _workflow_job()
    payload = MaintenancePayload(
        subject_id="retained-artifact",
        input_reference="retained:artifact",
        input_content_hash="artifact-hash",
    )

    def generic_result_handler(
        _job: WorkflowJob,
        _payload: QueuePayload,
        _ctx_value: RunContext,
    ) -> WorkflowQueueHandlerResult:
        return WorkflowQueueHandlerResult(
            result=queue_orchestrator.WorkflowStageResult(
                output_reference="retained:artifact",
                output_content_hash="artifact-hash",
                output_verified=True,
            )
        )

    registry = {
        ("vector_retention", "vector_retention.v1"): WorkflowQueueHandlerRegistration(
            queue_name="vector_retention",
            job_type="vector_retention.v1",
            payload_type=MaintenancePayload,
            result_type=PublisherDiscoveryResult,
            handler=generic_result_handler,
            default_retry_policy="test",
            default_lease_seconds=60,
            budget_profile="test",
            expected_external_effects=(),
            allowed_downstream_job_types=(),
        )
    }

    completed = queue_orchestrator.execute_workflow_queue_handler(
        job, payload, _ctx(), registry=registry
    )

    assert isinstance(completed.result, PublisherDiscoveryResult)
    assert completed.result.output_verified is True


def test_queue_attribute_and_budget_override_parsers_preserve_operator_intent() -> None:
    base = MaintenancePayload(attributes={})
    assert queue_orchestrator._requested_budget_override(base) is None
    assert queue_orchestrator._string_list_attribute(
        MaintenancePayload(attributes={"publishers": [" publisher-1 ", ""]}),
        "publishers",
    ) == ["publisher-1"]
    assert queue_orchestrator._positive_int_attribute(base, "limit", 3) == 3
    assert queue_orchestrator._positive_float_attribute(base, "cost", 1.25) == 1.25
    assert queue_orchestrator._boolean_attribute(base, "dry_run", True) is True

    override = queue_orchestrator._requested_budget_override(
        MaintenancePayload(
            attributes={
                "budget_override_actor": "operator-1",
                "budget_override_reason": "bounded live validation",
                "budget_override_expires_at_utc": "2026-07-18T01:00:00+00:00",
                "budget_override_scope": "briefing_generation",
            }
        )
    )
    assert override is not None
    assert override.actor == "operator-1"
    assert override.scope == "briefing_generation"

    with pytest.raises(AppError, match="requires actor"):
        queue_orchestrator._requested_budget_override(
            MaintenancePayload(attributes={"budget_override_actor": "operator-1"})
        )
    with pytest.raises(AppError, match="lists of strings"):
        queue_orchestrator._string_list_attribute(
            MaintenancePayload(attributes={"publishers": "publisher-1"}),
            "publishers",
        )
    for invalid in (True, "not-an-int", 0, ["not-an-int"]):
        with pytest.raises(AppError, match="positive integers"):
            queue_orchestrator._positive_int_attribute(
                MaintenancePayload(attributes={"limit": invalid}), "limit", 1
            )
    for invalid in (True, "not-a-float", 0, ["not-a-float"]):
        with pytest.raises(AppError, match="positive numbers"):
            queue_orchestrator._positive_float_attribute(
                MaintenancePayload(attributes={"cost": invalid}), "cost", 1.0
            )
    with pytest.raises(AppError, match="must be booleans"):
        queue_orchestrator._boolean_attribute(
            MaintenancePayload(attributes={"dry_run": "yes"}), "dry_run", False
        )


def test_operational_handlers_reject_incomplete_inputs_before_external_work() -> None:
    job = _workflow_job(
        queue_name="report_acquisition", job_type="report_acquisition.v1"
    )
    with pytest.raises(AppError, match="requires a source URL"):
        queue_orchestrator._report_acquisition_handler(
            job, ReportAcquisitionPayload(), _ctx()
        )
    with pytest.raises(
        AppError, match="no verified durable submission identity"
    ) as mailbox_error:
        queue_orchestrator._mailbox_delivery_handler(
            job, MailboxDeliveryPayload(), _ctx()
        )
    assert mailbox_error.value.code == "workflow_queue_mailbox_request_identity_missing"
    with pytest.raises(AppError, match="requires a current approval"):
        queue_orchestrator._wordpress_publish_handler(
            job, WordPressPublishPayload(entity_type="report"), _ctx()
        )
    with pytest.raises(AppError) as signal_manifest_error:
        queue_orchestrator._signal_generation_handler(
            job,
            SignalGenerationPayload(
                candidate_group_id="signal-group-1",
                frozen_evidence_manifest="signal-candidates:group-1",
            ),
            _ctx(),
        )
    assert signal_manifest_error.value.code == "signal_frozen_manifest_incomplete"
    with pytest.raises(AppError, match="immutable source artifact hash"):
        queue_orchestrator._report_stage_handler(
            resume_from_stage="source_prepared", next_queue="report_selection"
        )(job, SourceIngestPayload(), _ctx())


def test_source_ingest_checkpoint_hands_off_to_report_selection(
    tmp_path: Path,
    external_boundary_mocks_only,
    fake_openai,
) -> None:
    external_boundary_mocks_only.setenv("OPENAI_API_KEY", "test-openai-key")
    fake_openai.add("vector_stores.create", {"id": "vs_queue_test"})
    fake_openai.add("files.create", {"id": "file_queue_test"})
    fake_openai.add("vector_stores.files.create", {"id": "file_queue_test"})
    config_path = _isolated_app_config(tmp_path)
    source_path = Path(
        "tests/fixtures/pdf_benchmark/golden/IAS - Industry_Pulse_Report_2026_ACIG.pdf"
    ).resolve()
    source_hash = hashlib.md5(source_path.read_bytes()).hexdigest()
    record_report_source(
        ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=str(tmp_path / "reports.sqlite"),
            source_domain="publisher.example",
            report_name="Industry Pulse Report 2026",
            landing_page_url="https://publisher.example/reports/industry-pulse-2026",
            downloaded_at_utc="2026-08-10T12:00:00Z",
            md5=source_hash,
            publisher_name="Industry Analytics Summit",
        ),
        _ctx(),
    )
    job = _workflow_job(queue_name="source_ingest", job_type="source_ingest.v1")

    result = queue_orchestrator._report_stage_handler(
        resume_from_stage="",
        stop_after_stage="source_prepared",
        next_queue="report_selection",
    )(
        job,
        SourceIngestPayload(
            source_identity_id="ias-industry-pulse",
            source_artifact_reference=str(source_path),
            source_content_hash=source_hash,
            report_id="ias-industry-pulse-2026",
            parser_ocr_compatibility_version="parser.v1",
            input_reference=str(source_path),
            input_content_hash=source_hash,
            processing_version="parser.v1",
            attributes={"config_path": str(config_path)},
        ),
        _ctx(),
    )

    assert result.result.output_verified is True
    assert result.result.summary["checkpoint"] == "source_prepared"
    assert len(result.downstream) == 1
    child = result.downstream[0]
    assert child.queue_name == "report_selection"
    assert child.parent_job_id == job.job_id
    assert child.payload.attributes["admission_decision_hash"]
    assert child.idempotency_key == (
        f"ias-industry-pulse-2026:report_selection:{source_hash}:parser.v1"
    )

    selection_result = queue_orchestrator._report_stage_handler(
        resume_from_stage="source_prepared",
        stop_after_stage="selection_complete",
        next_queue="report_analysis",
    )(
        replace(
            job,
            queue_name="report_selection",
            job_type="report_selection.v1",
        ),
        ReportSelectionPayload(
            report_id="ias-industry-pulse-2026",
            source_prepared_checkpoint="source_prepared",
            input_reference=str(source_path),
            input_content_hash=source_hash,
            processing_version="parser.v1",
            attributes=child.payload.attributes,
        ),
        _ctx(),
    )
    assert selection_result.result.output_verified is True
    assert selection_result.result.summary["checkpoint"] == "selection_complete"
    assert selection_result.downstream[0].queue_name == "report_analysis"
    assert len(fake_openai.calls["vector_stores.create"]) == 1
    assert len(fake_openai.calls["files.create"]) == 1
    assert len(fake_openai.calls["vector_stores.files.create"]) == 1


# Worker lifecycle failure cases live in test_workflow_queue_worker_failures.py.
