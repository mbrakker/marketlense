from __future__ import annotations

from src.contracts.run_context import RunContext
from src.contracts.workflow_queue import (
    PublisherDiscoveryPayload,
    PublisherDiscoveryResult,
    ReportAcquisitionPayload,
    WorkflowJobSubmission,
)
from src.orchestrators._workflow_queue_handlers.shared import (
    WorkflowQueueHandlerRegistration,
    WorkflowQueueHandlerResult,
)
from src.orchestrators.workflow_worker_orchestrator import run_workflow_worker_once
from src.services.performance_telemetry_service import build_performance_run_artifact
from src.services.workflow_queue_service import enqueue_workflow_job


def _ctx() -> RunContext:
    return RunContext(
        schema_version="1.0",
        run_id="queue-run-1",
        task_id="queue-task-1",
        span_id="queue-root-span",
    )


def test_worker_persists_queue_wait_and_stage_wall_time(tmp_path) -> None:
    state_db = str(tmp_path / "state.sqlite")
    enqueue_workflow_job(
        state_db,
        WorkflowJobSubmission(
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
            idempotency_key="one",
            deduplication_scope="telemetry-test",
        ),
        _ctx(),
        now_utc="2026-08-10T10:00:00.000+00:00",
    )
    registry = {
        (
            "publisher_discovery",
            "publisher_discovery.v1",
        ): WorkflowQueueHandlerRegistration(
            queue_name="publisher_discovery",
            job_type="publisher_discovery.v1",
            payload_type=PublisherDiscoveryPayload,
            result_type=PublisherDiscoveryResult,
            handler=lambda job, _payload, _ctx: WorkflowQueueHandlerResult(
                result=PublisherDiscoveryResult(
                    output_reference="snapshot:publisher-1",
                    output_content_hash="source-hash",
                    output_verified=True,
                ),
                downstream=[
                    WorkflowJobSubmission(
                        schema_version="1.0",
                        queue_name="report_acquisition",
                        job_type="report_acquisition.v1",
                        payload=ReportAcquisitionPayload(
                            source_identity_id="source-1",
                            source_url="https://example.test/report.pdf",
                            publisher_id="publisher-1",
                            input_reference="snapshot:publisher-1",
                            input_content_hash="source-hash",
                        ),
                        idempotency_key="child-one",
                        deduplication_scope="telemetry-test",
                        parent_job_id=job.job_id,
                        root_workflow_id=job.root_workflow_id,
                    ),
                ],
            ),
            default_retry_policy="bounded",
            default_lease_seconds=60,
            budget_profile="default",
            expected_external_effects=(),
            allowed_downstream_job_types=("report_acquisition.v1",),
        )
    }

    result = run_workflow_worker_once(
        state_db=state_db,
        queue_name="publisher_discovery",
        worker_id="worker-1",
        ctx=_ctx(),
        registry=registry,
        now_utc="2026-08-10T10:00:01.000+00:00",
    )
    artifact = build_performance_run_artifact(state_db, "queue-run-1", _ctx())

    assert result.terminal_status == "succeeded"
    assert result.downstream_queue_names == ("report_acquisition",)
    assert artifact.stage_summaries[0].stage == "publisher_discovery"
    assert artifact.stage_summaries[0].sample_count == 1
