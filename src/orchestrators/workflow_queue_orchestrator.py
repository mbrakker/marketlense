"""Code-reviewed typed handler registry for the durable workflow queue.

The registry is deliberately not a DAG authoring system.  It defines the fixed
MarketLense graph, payload/result contracts, and the only downstream queue types
that a handler may request.  Domain adapters can be replaced incrementally while
the queue lifecycle remains unchanged.
"""

# ruff: noqa: E501

from __future__ import annotations

from dataclasses import asdict, dataclass, field, replace
from typing import Callable

from src.contracts.config import ConfigLoadRequest, IngestSettingsBuildRequest
from src.contracts.drive import DriveFile
from src.contracts.run_context import RunContext
from src.contracts.workflow_queue import (
    AnalyticsProjectionPayload,
    AnalyticsProjectionResult,
    BriefingGenerationPayload,
    BriefingGenerationResult,
    BriefingOpportunityPayload,
    BriefingOpportunityResult,
    ClaimEmbeddingPayload,
    ClaimEmbeddingResult,
    CoverGenerationPayload,
    CoverGenerationResult,
    MailboxDeliveryPayload,
    MailboxDeliveryResult,
    MaintenancePayload,
    PublicationReadinessPayload,
    PublicationReadinessResult,
    PublisherDiscoveryPayload,
    PublisherDiscoveryResult,
    QueuePayload,
    ReportAcquisitionPayload,
    ReportAcquisitionResult,
    ReportAnalysisPayload,
    ReportAnalysisResult,
    ReportRenderPayload,
    ReportRenderResult,
    ReportSelectionPayload,
    ReportSelectionResult,
    SignalCandidatePayload,
    SignalCandidateResult,
    SignalGenerationPayload,
    SignalGenerationResult,
    SourceIngestPayload,
    SourceIngestResult,
    WordPressProjectionPayload,
    WordPressProjectionResult,
    WordPressPublishPayload,
    WordPressPublishResult,
    WorkflowJob,
    WorkflowJobSubmission,
    WorkflowStageResult,
)
from src.orchestrators.report_pipeline_orchestrator import run_report_pipeline
from src.services.config_service import build_ingest_settings, load_settings
from src.utils.errors import AppError

WorkflowQueueHandler = Callable[
    [WorkflowJob, QueuePayload, RunContext], "WorkflowQueueHandlerResult"
]


@dataclass(frozen=True)
class WorkflowQueueHandlerResult:
    result: WorkflowStageResult
    downstream: list[WorkflowJobSubmission] = field(default_factory=list)
    provider_usage: dict[str, int | float | str] = field(default_factory=dict)
    external_effects: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class WorkflowQueueHandlerRegistration:
    queue_name: str
    job_type: str
    payload_type: type
    result_type: type
    handler: WorkflowQueueHandler
    default_retry_policy: str
    default_lease_seconds: int
    budget_profile: str
    expected_external_effects: tuple[str, ...]
    allowed_downstream_job_types: tuple[str, ...]


def _verified_reference_handler(
    job: WorkflowJob,
    payload: QueuePayload,
    ctx: RunContext,
) -> WorkflowQueueHandlerResult:
    """Compatibility bridge for a pre-verified canonical domain artifact.

    This is intentionally narrow: it accepts only a retained reference with a
    content hash.  It never manufactures an output or directly chains a later
    workflow.  Newly submitted operational work is routed through a stage
    adapter rather than this bridge.
    """
    del ctx
    if not payload.input_reference or not payload.input_content_hash:
        raise AppError(
            code="workflow_queue_reference_unverified",
            message="Queue compatibility execution requires a retained reference and content hash",
            retryable=False,
            context={"job_id": job.job_id, "queue_name": job.queue_name},
        )
    return WorkflowQueueHandlerResult(
        result=WorkflowStageResult(
            output_reference=payload.input_reference,
            output_content_hash=payload.input_content_hash,
            execution_plan_hash=job.execution_plan_hash,
            output_verified=True,
            summary={"mode": "verified_reference_compatibility"},
        )
    )


def _stage_child_submission(
    *,
    job: WorkflowJob,
    payload: QueuePayload,
    next_queue: str,
    next_payload: QueuePayload,
) -> WorkflowJobSubmission:
    """Create the one deterministic report-stage handoff for a checkpoint."""
    source_hash = payload.input_content_hash or getattr(payload, "source_content_hash", "")
    report_id = getattr(payload, "report_id", "") or job.report_id
    return WorkflowJobSubmission(
        schema_version="1.0",
        queue_name=next_queue,
        job_type=f"{next_queue}.v1",
        payload=next_payload,
        idempotency_key=f"{report_id}:{next_queue}:{source_hash}:{payload.processing_version}",
        deduplication_scope=f"report-stage:{next_queue}",
        root_workflow_id=job.root_workflow_id or job.job_id,
        parent_job_id=job.job_id,
        trigger_event_id=job.trigger_event_id or job.job_id,
        correlation_id=job.correlation_id or job.root_workflow_id or job.job_id,
        entity_type="report",
        entity_id=report_id,
        publisher_id=job.publisher_id,
        source_identity_id=job.source_identity_id,
        report_id=report_id,
        budget_profile="report_ingest",
    )


def _report_stage_handler(
    *,
    resume_from_stage: str,
    stop_after_stage: str | None = None,
    projection_only: bool = False,
    next_queue: str = "",
) -> WorkflowQueueHandler:
    """Adapt one retained report checkpoint to the established pipeline.

    The queue payload contains the immutable source reference only.  The report
    pipeline remains the owner of checkpoint, lineage, provider, retry and
    domain-generation decisions.
    """

    def handler(
        job: WorkflowJob, payload: QueuePayload, ctx: RunContext
    ) -> WorkflowQueueHandlerResult:
        artifact_reference = str(
            getattr(payload, "source_artifact_reference", "")
            or payload.input_reference
        ).strip()
        source_hash = str(
            getattr(payload, "source_content_hash", "")
            or payload.input_content_hash
        ).strip()
        report_id = str(getattr(payload, "report_id", "") or job.report_id).strip()
        if not artifact_reference or not source_hash or not report_id:
            raise AppError(
                code="workflow_queue_report_stage_input_incomplete",
                message="Report stage requires a report id and immutable source artifact hash",
                retryable=False,
                context={"job_id": job.job_id, "queue_name": job.queue_name},
            )
        config_path = str(payload.attributes.get("config_path", "src/config/app.yaml"))
        app_settings = load_settings(
            ConfigLoadRequest(schema_version="1.0", path=config_path), ctx
        )
        settings = build_ingest_settings(
            IngestSettingsBuildRequest(schema_version="1.0", app_settings=app_settings),
            ctx,
        )
        outcome = run_report_pipeline(
            DriveFile(
                schema_version="1.0",
                file_id=report_id,
                name=artifact_reference.replace("\\", "/").rsplit("/", 1)[-1],
                modified_time=None,
                md5_checksum=source_hash,
                mime_type="application/pdf",
            ),
            artifact_reference,
            settings,
            source_hash,
            ctx,
            resume_from_stage=resume_from_stage,
            stop_after_stage=stop_after_stage,
            projection_only=projection_only,
        )
        if outcome.status == "error":
            raise AppError(
                code="workflow_queue_report_stage_failed",
                message="The retained report pipeline returned an error outcome",
                retryable=True,
                context={"job_id": job.job_id, "report_id": report_id},
            )
        downstream: list[WorkflowJobSubmission] = []
        if next_queue:
            next_payload_types: dict[str, type[QueuePayload]] = {
                "report_selection": ReportSelectionPayload,
                "report_analysis": ReportAnalysisPayload,
                "report_render": ReportRenderPayload,
                "analytics_projection": AnalyticsProjectionPayload,
            }
            next_payload_type = next_payload_types[next_queue]
            common = {
                "input_reference": artifact_reference,
                "input_content_hash": source_hash,
                "processing_version": payload.processing_version,
                "attributes": payload.attributes,
                "report_id": report_id,
            }
            if next_queue == "report_selection":
                next_payload = next_payload_type(
                    **common,
                    source_prepared_checkpoint="source_prepared",
                )
            elif next_queue == "report_analysis":
                next_payload = next_payload_type(
                    **common,
                    selection_checkpoint="selection_complete",
                )
            elif next_queue == "report_render":
                next_payload = next_payload_type(
                    **common,
                    analysis_checkpoint="analysis_complete",
                )
            else:
                next_payload = next_payload_type(
                    **common,
                    validated_artifact_reference="analysis_complete",
                )
            downstream.append(
                _stage_child_submission(
                    job=job,
                    payload=payload,
                    next_queue=next_queue,
                    next_payload=next_payload,
                )
            )
        return WorkflowQueueHandlerResult(
            result=WorkflowStageResult(
                output_reference=str(outcome.html_path or artifact_reference),
                output_content_hash=source_hash,
                execution_plan_hash=job.execution_plan_hash,
                output_verified=outcome.status in {"processed", "skipped"},
                summary={
                    "pipeline_status": outcome.status,
                    "checkpoint": stop_after_stage or "analytics_projected",
                },
            ),
            downstream=downstream,
        )

    return handler


def _registration(
    queue_name: str,
    payload_type: type,
    result_type: type,
    *,
    handler: WorkflowQueueHandler = _verified_reference_handler,
    downstream: tuple[str, ...] = (),
    effects: tuple[str, ...] = (),
    budget_profile: str = "default",
    retry_policy: str = "workflow_queue.default.v1",
    lease_seconds: int = 900,
) -> WorkflowQueueHandlerRegistration:
    return WorkflowQueueHandlerRegistration(
        queue_name=queue_name,
        job_type=f"{queue_name}.v1",
        payload_type=payload_type,
        result_type=result_type,
        handler=handler,
        default_retry_policy=retry_policy,
        default_lease_seconds=lease_seconds,
        budget_profile=budget_profile,
        expected_external_effects=effects,
        allowed_downstream_job_types=downstream,
    )


def default_workflow_queue_registry() -> dict[
    tuple[str, str], WorkflowQueueHandlerRegistration
]:
    """Return the fixed, typed MarketLense workflow graph."""
    registrations = (
        _registration(
            "publisher_discovery",
            PublisherDiscoveryPayload,
            PublisherDiscoveryResult,
            downstream=("report_acquisition.v1",),
            effects=("browser", "drive"),
            budget_profile="publisher_inventory",
        ),
        _registration(
            "report_acquisition",
            ReportAcquisitionPayload,
            ReportAcquisitionResult,
            downstream=("mailbox_delivery.v1", "source_ingest.v1"),
            effects=("browser", "drive"),
            budget_profile="browser_acquisition",
            lease_seconds=1200,
        ),
        _registration(
            "mailbox_delivery",
            MailboxDeliveryPayload,
            MailboxDeliveryResult,
            downstream=("source_ingest.v1",),
            effects=("mailbox", "browser", "drive"),
            budget_profile="mailbox_delivery",
        ),
        _registration(
            "source_ingest",
            SourceIngestPayload,
            SourceIngestResult,
            handler=_report_stage_handler(
                resume_from_stage="", stop_after_stage="source_prepared", next_queue="report_selection"
            ),
            downstream=("report_selection.v1",),
            effects=("pdf", "ocr"),
            budget_profile="report_ingest",
            lease_seconds=1800,
        ),
        _registration(
            "report_selection",
            ReportSelectionPayload,
            ReportSelectionResult,
            handler=_report_stage_handler(
                resume_from_stage="source_prepared", stop_after_stage="selection_complete", next_queue="report_analysis"
            ),
            downstream=("report_analysis.v1",),
            effects=("pdf", "vision"),
            budget_profile="report_ingest",
            lease_seconds=1800,
        ),
        _registration(
            "report_analysis",
            ReportAnalysisPayload,
            ReportAnalysisResult,
            handler=_report_stage_handler(
                resume_from_stage="selection_complete", stop_after_stage="analysis_complete", next_queue="report_render"
            ),
            downstream=("artifact_repair.v1", "report_render.v1"),
            effects=("model", "vector"),
            budget_profile="high_quality",
            retry_policy="report_generation.report_pipeline.v1",
            lease_seconds=3600,
        ),
        _registration(
            "report_render",
            ReportRenderPayload,
            ReportRenderResult,
            handler=_report_stage_handler(
                resume_from_stage="analysis_complete", stop_after_stage="render_complete", next_queue="analytics_projection"
            ),
            downstream=(
                "analytics_projection.v1",
                "cover_generation.v1",
                "publication_readiness.v1",
            ),
            effects=("filesystem",),
            budget_profile="report_render",
        ),
        _registration(
            "analytics_projection",
            AnalyticsProjectionPayload,
            AnalyticsProjectionResult,
            handler=_report_stage_handler(
                resume_from_stage="analysis_complete", projection_only=True
            ),
            downstream=(
                "claim_embedding.v1",
                "signal_candidate.v1",
                "briefing_opportunity.v1",
            ),
            budget_profile="analytics_projection",
        ),
        _registration(
            "claim_embedding",
            ClaimEmbeddingPayload,
            ClaimEmbeddingResult,
            effects=("embedding",),
            budget_profile="embedding",
        ),
        _registration(
            "signal_candidate",
            SignalCandidatePayload,
            SignalCandidateResult,
            downstream=("signal_generation.v1",),
            budget_profile="signal_candidate",
        ),
        _registration(
            "signal_generation",
            SignalGenerationPayload,
            SignalGenerationResult,
            downstream=("cover_generation.v1", "publication_readiness.v1"),
            effects=("model",),
            budget_profile="high_quality",
            lease_seconds=3600,
        ),
        _registration(
            "briefing_opportunity",
            BriefingOpportunityPayload,
            BriefingOpportunityResult,
            downstream=("briefing_generation.v1",),
            budget_profile="briefing_opportunity",
        ),
        _registration(
            "briefing_generation",
            BriefingGenerationPayload,
            BriefingGenerationResult,
            downstream=("cover_generation.v1", "publication_readiness.v1"),
            effects=("model",),
            budget_profile="cross_report_analysis",
            lease_seconds=3600,
        ),
        _registration(
            "cover_generation",
            CoverGenerationPayload,
            CoverGenerationResult,
            budget_profile="cover_generation",
        ),
        _registration(
            "publication_readiness",
            PublicationReadinessPayload,
            PublicationReadinessResult,
            downstream=("wordpress_publish.v1",),
            budget_profile="publishing",
        ),
        _registration(
            "wordpress_publish",
            WordPressPublishPayload,
            WordPressPublishResult,
            downstream=("wordpress_projection.v1",),
            effects=("wordpress",),
            budget_profile="publishing",
        ),
        _registration(
            "wordpress_projection",
            WordPressProjectionPayload,
            WordPressProjectionResult,
            effects=("wordpress",),
            budget_profile="wordpress_projection",
        ),
        _registration(
            "artifact_repair",
            MaintenancePayload,
            WorkflowStageResult,
            downstream=("report_analysis.v1",),
            budget_profile="maintenance",
        ),
        _registration(
            "source_revalidation",
            MaintenancePayload,
            WorkflowStageResult,
            downstream=("report_acquisition.v1",),
            effects=("browser",),
            budget_profile="maintenance",
        ),
        _registration(
            "malformed_pdf_revalidation",
            MaintenancePayload,
            WorkflowStageResult,
            downstream=("source_ingest.v1",),
            effects=("pdf",),
            budget_profile="maintenance",
        ),
        _registration(
            "recategorization",
            MaintenancePayload,
            WorkflowStageResult,
            downstream=("analytics_projection.v1",),
            budget_profile="maintenance",
        ),
        _registration(
            "vector_retention", MaintenancePayload, WorkflowStageResult, budget_profile="maintenance"
        ),
        _registration(
            "wordpress_category_update",
            MaintenancePayload,
            WorkflowStageResult,
            effects=("wordpress",),
            budget_profile="maintenance",
        ),
        _registration(
            "public_render_repair",
            MaintenancePayload,
            WorkflowStageResult,
            downstream=("report_render.v1",),
            budget_profile="maintenance",
        ),
        _registration(
            "cost_reconciliation", MaintenancePayload, WorkflowStageResult, budget_profile="maintenance"
        ),
        _registration(
            "release_evidence_generation",
            MaintenancePayload,
            WorkflowStageResult,
            budget_profile="maintenance",
        ),
    )
    registry = {(item.queue_name, item.job_type): item for item in registrations}
    if len(registry) != len(registrations):
        raise RuntimeError(
            "Workflow queue registry contains duplicate queue/job registrations"
        )
    return registry


def resolve_workflow_queue_handler(
    queue_name: str,
    job_type: str,
    *,
    registry: dict[tuple[str, str], WorkflowQueueHandlerRegistration] | None = None,
) -> WorkflowQueueHandlerRegistration:
    item = (registry or default_workflow_queue_registry()).get((queue_name, job_type))
    if item is None:
        raise AppError(
            code="workflow_queue_handler_unregistered",
            message="Workflow queue and job type are not registered together",
            retryable=False,
            context={"queue_name": queue_name, "job_type": job_type},
        )
    return item


def execute_workflow_queue_handler(
    job: WorkflowJob,
    payload: QueuePayload,
    ctx: RunContext,
    *,
    registry: dict[tuple[str, str], WorkflowQueueHandlerRegistration] | None = None,
) -> WorkflowQueueHandlerResult:
    registration = resolve_workflow_queue_handler(
        job.queue_name, job.job_type, registry=registry
    )
    if not isinstance(payload, registration.payload_type):
        raise AppError(
            code="workflow_queue_handler_payload_invalid",
            message="Worker payload does not match the registered typed handler",
            retryable=False,
            context={"queue_name": job.queue_name, "job_type": job.job_type},
        )
    execution = registration.handler(job, payload, ctx)
    if not isinstance(execution.result, registration.result_type):
        execution = replace(
            execution,
            result=registration.result_type(**asdict(execution.result)),
        )
    disallowed = sorted(
        child.job_type
        for child in execution.downstream
        if child.job_type not in registration.allowed_downstream_job_types
    )
    if disallowed:
        raise AppError(
            code="workflow_queue_downstream_unregistered",
            message="Handler attempted an unapproved downstream queue transition",
            retryable=False,
            context={"job_id": job.job_id, "job_types": disallowed},
        )
    return execution
