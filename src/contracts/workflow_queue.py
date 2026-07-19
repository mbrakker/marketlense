"""Typed contracts for the durable MarketLense workflow queue.

The queue only carries small, immutable references and scalar routing context.
Domain artefacts, prompts, source text, PDFs, vectors and credentials remain in
their existing canonical stores.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

WorkflowQueueName = Literal[
    "publisher_discovery",
    "report_acquisition",
    "mailbox_delivery",
    "source_ingest",
    "report_selection",
    "report_analysis",
    "report_render",
    "analytics_projection",
    "claim_embedding",
    "signal_candidate",
    "signal_generation",
    "briefing_opportunity",
    "briefing_generation",
    "cover_generation",
    "publication_readiness",
    "wordpress_publish",
    "wordpress_projection",
    "artifact_repair",
    "source_revalidation",
    "malformed_pdf_revalidation",
    "recategorization",
    "vector_retention",
    "wordpress_category_update",
    "public_render_repair",
    "cost_reconciliation",
    "release_evidence_generation",
]

WorkflowJobStatus = Literal[
    "pending",
    "leased",
    "running",
    "succeeded",
    "retry_wait",
    "budget_deferred",
    "blocked",
    "dead_letter",
    "cancelled",
]

QueueControlMode = Literal["active", "paused", "draining"]

WORKFLOW_QUEUE_NAMES: tuple[str, ...] = (
    "publisher_discovery",
    "report_acquisition",
    "mailbox_delivery",
    "source_ingest",
    "report_selection",
    "report_analysis",
    "report_render",
    "analytics_projection",
    "claim_embedding",
    "signal_candidate",
    "signal_generation",
    "briefing_opportunity",
    "briefing_generation",
    "cover_generation",
    "publication_readiness",
    "wordpress_publish",
    "wordpress_projection",
    "artifact_repair",
    "source_revalidation",
    "malformed_pdf_revalidation",
    "recategorization",
    "vector_retention",
    "wordpress_category_update",
    "public_render_repair",
    "cost_reconciliation",
    "release_evidence_generation",
)


@dataclass(frozen=True)
class WorkflowArtifactReference:
    schema_version: str = field(
        default="1.0", metadata={"doc": "Contract schema version."}
    )
    kind: str = ""
    reference: str = ""
    content_hash: str = ""


@dataclass(frozen=True)
class WorkflowQueuePayload:
    """Common non-sensitive reference payload accepted by every queue."""

    schema_version: str = field(
        default="1.0", metadata={"doc": "Contract schema version."}
    )
    input_reference: str = ""
    input_content_hash: str = ""
    required_artifact_references: list[WorkflowArtifactReference] = field(
        default_factory=list
    )
    processing_version: str = ""
    prompt_policy_version: str = ""
    attributes: dict[str, str | int | bool | list[str]] = field(default_factory=dict)


@dataclass(frozen=True)
class PublisherDiscoveryPayload(WorkflowQueuePayload):
    publisher_id: str = ""
    insights_url: str = ""
    discovery_policy_version: str = ""
    inventory_window: str = ""
    prior_snapshot_reference: str = ""


@dataclass(frozen=True)
class ReportAcquisitionPayload(WorkflowQueuePayload):
    source_identity_id: str = ""
    source_url: str = ""
    publisher_id: str = ""
    acquisition_route_context: str = ""
    acquisition_policy_version: str = ""
    report_title: str = ""
    publisher_name: str = ""
    delivery_email_reference: str = ""


@dataclass(frozen=True)
class MailboxDeliveryPayload(WorkflowQueuePayload):
    delivery_request_id: str = ""
    source_url: str = ""
    publisher_id: str = ""
    report_title: str = ""
    request_watermark: str = ""
    deadline_at_utc: str = ""
    retry_policy_version: str = ""


@dataclass(frozen=True)
class SourceIngestPayload(WorkflowQueuePayload):
    source_identity_id: str = ""
    source_artifact_reference: str = ""
    source_content_hash: str = ""
    report_id: str = ""
    parser_ocr_compatibility_version: str = ""


@dataclass(frozen=True)
class ReportSelectionPayload(WorkflowQueuePayload):
    report_id: str = ""
    source_prepared_checkpoint: str = ""
    selection_profile: str = ""


@dataclass(frozen=True)
class ReportAnalysisPayload(WorkflowQueuePayload):
    report_id: str = ""
    selection_checkpoint: str = ""
    model_routing_policy_version: str = ""
    validator_compatibility_version: str = ""


@dataclass(frozen=True)
class ReportRenderPayload(WorkflowQueuePayload):
    report_id: str = ""
    analysis_checkpoint: str = ""
    template_version: str = ""
    presentation_version: str = ""


@dataclass(frozen=True)
class AnalyticsProjectionPayload(WorkflowQueuePayload):
    report_id: str = ""
    validated_artifact_reference: str = ""


@dataclass(frozen=True)
class ClaimEmbeddingPayload(WorkflowQueuePayload):
    claim_id: str = ""
    embedding_row_id: str = ""
    model_version: str = ""


@dataclass(frozen=True)
class SignalCandidatePayload(WorkflowQueuePayload):
    report_id: str = ""
    projection_reference: str = ""
    signal_selection_policy_version: str = ""
    embedding_ready: bool = False


@dataclass(frozen=True)
class SignalGenerationPayload(WorkflowQueuePayload):
    candidate_group_id: str = ""
    frozen_evidence_manifest: str = ""
    model_routing_policy_version: str = ""


@dataclass(frozen=True)
class BriefingOpportunityPayload(WorkflowQueuePayload):
    report_id: str = ""
    projection_event_id: str = ""
    topic: str = ""
    geography: str = ""
    rolling_window: str = ""
    source_hashes: list[str] = field(default_factory=list)
    briefing_policy_version: str = ""


@dataclass(frozen=True)
class BriefingGenerationPayload(WorkflowQueuePayload):
    opportunity_id: str = ""
    frozen_source_manifest: str = ""
    selected_topic: str = ""
    sorted_source_hashes: list[str] = field(default_factory=list)
    model_routing_policy_version: str = ""
    generation_configuration_hash: str = ""


@dataclass(frozen=True)
class CoverGenerationPayload(WorkflowQueuePayload):
    entity_type: str = ""
    entity_package_reference: str = ""
    visual_semantics: str = ""
    template_version: str = ""


@dataclass(frozen=True)
class PublicationReadinessPayload(WorkflowQueuePayload):
    entity_type: str = ""
    entity_package_reference: str = ""
    package_checksum: str = ""
    validation_reference: str = ""
    lineage_reference: str = ""
    required_asset_status: str = ""


@dataclass(frozen=True)
class WordPressPublishPayload(WorkflowQueuePayload):
    entity_type: str = ""
    entity_package_reference: str = ""
    package_checksum: str = ""
    approval_id: str = ""
    target_site: str = ""
    dry_run: bool = False


@dataclass(frozen=True)
class WordPressProjectionPayload(WorkflowQueuePayload):
    published_entity_reference: str = ""
    wordpress_id: str = ""
    entity_type: str = ""


@dataclass(frozen=True)
class MaintenancePayload(WorkflowQueuePayload):
    subject_id: str = ""
    maintenance_policy_version: str = ""


QueuePayload = (
    PublisherDiscoveryPayload
    | ReportAcquisitionPayload
    | MailboxDeliveryPayload
    | SourceIngestPayload
    | ReportSelectionPayload
    | ReportAnalysisPayload
    | ReportRenderPayload
    | AnalyticsProjectionPayload
    | ClaimEmbeddingPayload
    | SignalCandidatePayload
    | SignalGenerationPayload
    | BriefingOpportunityPayload
    | BriefingGenerationPayload
    | CoverGenerationPayload
    | PublicationReadinessPayload
    | WordPressPublishPayload
    | WordPressProjectionPayload
    | MaintenancePayload
)


@dataclass(frozen=True)
class WorkflowJob:
    """Current effective state for one at-least-once delivered queue job."""

    schema_version: str = field(metadata={"doc": "Contract schema version."})
    job_id: str
    queue_name: str
    job_type: str
    job_schema_version: str
    workflow_version: str
    root_workflow_id: str
    parent_job_id: str
    trigger_event_id: str
    correlation_id: str
    entity_type: str
    entity_id: str
    publisher_id: str
    source_identity_id: str
    report_id: str
    input_reference: str
    input_content_hash: str
    required_artifact_references: list[WorkflowArtifactReference]
    output_reference: str
    output_content_hash: str
    idempotency_key: str
    deduplication_scope: str
    priority: int
    status: WorkflowJobStatus
    available_at_utc: str
    attempt_count: int
    max_attempts: int
    lease_owner: str
    lease_expires_at_utc: str
    heartbeat_at_utc: str
    budget_profile: str
    execution_plan_hash: str
    prompt_policy_version: str
    processing_version: str
    created_at_utc: str
    updated_at_utc: str
    started_at_utc: str
    completed_at_utc: str
    error_code: str
    error_message_summary: str
    error_retryable: bool
    terminal_reason: str
    remediation_id: str
    payload_json: str = "{}"


@dataclass(frozen=True)
class WorkflowStageResult:
    schema_version: str = field(
        default="1.0", metadata={"doc": "Contract schema version."}
    )
    output_reference: str = ""
    output_content_hash: str = ""
    execution_plan_hash: str = ""
    output_verified: bool = False
    summary: dict[str, str | int | bool] = field(default_factory=dict)


@dataclass(frozen=True)
class PublisherDiscoveryResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class ReportAcquisitionResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class MailboxDeliveryResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class SourceIngestResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class ReportSelectionResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class ReportAnalysisResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class ReportRenderResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class AnalyticsProjectionResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class ClaimEmbeddingResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class SignalCandidateResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class SignalGenerationResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class BriefingOpportunityResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class BriefingGenerationResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class CoverGenerationResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class PublicationReadinessResult(WorkflowStageResult):
    readiness_state: str = "not_publishable"


@dataclass(frozen=True)
class WordPressPublishResult(WorkflowStageResult):
    wordpress_id: str = ""
    wordpress_url: str = ""


@dataclass(frozen=True)
class WordPressProjectionResult(WorkflowStageResult):
    pass


@dataclass(frozen=True)
class WorkflowJobSubmission:
    schema_version: str = field(metadata={"doc": "Contract schema version."})
    queue_name: str
    job_type: str
    payload: QueuePayload
    idempotency_key: str
    deduplication_scope: str
    workflow_version: str = "1.0"
    root_workflow_id: str = ""
    parent_job_id: str = ""
    trigger_event_id: str = ""
    correlation_id: str = ""
    entity_type: str = ""
    entity_id: str = ""
    publisher_id: str = ""
    source_identity_id: str = ""
    report_id: str = ""
    priority: int = 0
    available_at_utc: str = ""
    max_attempts: int = 0
    budget_profile: str = ""
    execution_plan_hash: str = ""


@dataclass(frozen=True)
class WorkflowJobAttempt:
    schema_version: str = field(metadata={"doc": "Contract schema version."})
    attempt_id: str
    job_id: str
    attempt_number: int
    worker_id: str
    started_at_utc: str
    completed_at_utc: str
    input_content_hash: str
    output_content_hash: str
    execution_plan_hash: str
    budget_decision: str
    provider_usage_json: str
    external_effects_json: str
    outcome: str
    error_code: str


@dataclass(frozen=True)
class WorkflowQueueControl:
    schema_version: str = field(metadata={"doc": "Contract schema version."})
    queue_name: str
    mode: QueueControlMode
    enabled: bool
    worker_concurrency_limit: int
    maximum_pending: int
    maximum_fanout: int
    max_attempts: int
    lease_seconds: int
    budget_profile: str
    retry_delay_seconds: int
    emergency_stop_reason: str
    updated_at_utc: str
    updated_by: str


@dataclass(frozen=True)
class WorkflowQueuePolicy:
    """Validated configuration default; durable controls may override it."""

    schema_version: str = field(
        default="1.0", metadata={"doc": "Contract schema version."}
    )
    queue_name: str = ""
    enabled: bool = True
    max_workers: int = 1
    max_attempts: int = 3
    lease_seconds: int = 900
    maximum_pending: int = 100
    maximum_fanout: int = 10
    budget_profile: str = "default"
    retry_delay_seconds: int = 60


@dataclass(frozen=True)
class WorkflowQueueHealth:
    schema_version: str = field(metadata={"doc": "Contract schema version."})
    queue_name: str
    status_counts: dict[str, int]
    oldest_pending_age_seconds: int
    oldest_due_age_seconds: int
    lease_expiry_count: int
    throughput_24h: int
    completion_rate: float
    retry_rate: float
    terminal_rate: float
    mean_runtime_seconds: float
    p95_runtime_seconds: float
    mean_attempts: float
    outbox_pending_count: int
    reconciliation_anomaly_count: int


@dataclass(frozen=True)
class WorkflowQueueEvidenceSummary:
    """Bounded scalar queue state used by release-evidence validation."""

    schema_version: str = field(
        default="1.0", metadata={"doc": "Contract schema version."}
    )
    state_schema_version: int = 0
    job_count: int = 0
    transition_counts: dict[str, int] = field(default_factory=dict)
    status_counts: dict[str, int] = field(default_factory=dict)
    outbox_status_counts: dict[str, int] = field(default_factory=dict)
    publication_readiness_counts: dict[str, int] = field(default_factory=dict)
    approval_count: int = 0
    external_effect_count: int = 0


@dataclass(frozen=True)
class PublicationReadinessRecord:
    schema_version: str = field(metadata={"doc": "Contract schema version."})
    package_checksum: str
    entity_type: str
    package_reference: str
    validation_reference: str
    lineage_reference: str
    required_asset_status: str
    readiness_status: str
    reason: str
    created_at_utc: str
    updated_at_utc: str


@dataclass(frozen=True)
class PublicationApprovalRecord:
    schema_version: str = field(metadata={"doc": "Contract schema version."})
    approval_id: str
    package_checksum: str
    actor_id: str
    note: str
    action: str
    created_at_utc: str


@dataclass(frozen=True)
class BriefingOpportunity:
    schema_version: str = field(metadata={"doc": "Contract schema version."})
    opportunity_id: str
    opportunity_key: str
    topic: str
    geography: str
    rolling_window: str
    briefing_policy_version: str
    source_hashes: list[str]
    publisher_ids: list[str]
    frozen_source_manifest: str
    frozen_source_hashes: list[str]
    status: str
    generation_job_id: str
    last_generated_at_utc: str
    created_at_utc: str
    updated_at_utc: str
