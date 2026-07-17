from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Literal, Optional

from src.contracts.report_generation import ReportAnalysisState
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import (
    EntityUid,
    PublisherId,
    ReportId,
    SemanticIdContract,
)


PROJECTION_SCHEMA_VERSION = "1.0"
PROJECTION_VERSION = "analytics_projection.v1"

ProjectionStatus = Literal["not_projected", "projected", "failed"]
EmbeddingStatus = Literal["pending", "embedded", "failed"]
ClaimEmbeddingStatus = Literal["embedded", "failed"]
ContentClass = Literal["evidence", "derived_evidence", "editorial"]
QueueClassification = Literal[
    "ready_to_embed",
    "already_satisfied",
    "stale_content",
    "obsolete_version",
    "terminal_failure",
    "retryable_failure",
    "invalid_payload",
    "orphaned_report",
    "blocked_by_budget",
    "unknown_requires_review",
]


@dataclass(frozen=True)
class ProjectionLineage:
    schema_version: str = field(metadata={"doc": "Lineage schema version."})
    projection_version: str = field(
        metadata={"doc": "Version of the analytics projection mapping rules."}
    )
    source_pack: str = field(
        metadata={"doc": "Analysis pack or payload source that produced this row."}
    )
    source_ref: str = field(
        metadata={"doc": "Source-local reference, identifier, or JSON path."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp when this projection was generated."}
    )
    analysis_run_id: str = field(
        metadata={"doc": "Run identifier for the analysis that produced this row."}
    )
    model: str = field(
        default="",
        metadata={"doc": "Model identifier associated with the source pack, if known."},
    )


@dataclass(frozen=True)
class AnalyticsReportRow(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Projected report row schema version."}
    )
    projection_version: str = field(
        metadata={"doc": "Version of the analytics projection mapping rules."}
    )
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    title: str = field(metadata={"doc": "Projected report title."})
    publisher: str = field(
        metadata={"doc": "Projected publisher display name, if known."}
    )
    publisher_id: Optional[PublisherId] = field(
        default=None,
        metadata={
            "doc": "Stable publisher identifier derived from publisher text, if known."
        },
    )
    source_md5: Optional[str] = field(
        default=None,
        metadata={"doc": "Source PDF MD5 checksum, if known."},
    )
    ingest_run_id: str = field(
        default="",
        metadata={"doc": "Run ID for the ingest/report-generation run."},
    )
    analysis_run_id: str = field(
        default="",
        metadata={"doc": "Run ID for the analysis phase."},
    )
    region: str = field(default="", metadata={"doc": "Projected region metadata."})
    time_period: str = field(
        default="", metadata={"doc": "Projected report time-period metadata."}
    )
    validation_status: str = field(
        default="", metadata={"doc": "Validation report status, if available."}
    )
    validation_severity: str = field(
        default="", metadata={"doc": "Validation report severity, if available."}
    )
    text_density: float = field(
        default=0.0,
        metadata={"doc": "Extracted text density recorded on the report payload."},
    )
    text_not_available: bool = field(
        default=False,
        metadata={"doc": "Whether extracted text was below the configured threshold."},
    )
    projection_generated_at_utc: str = field(
        default="",
        metadata={"doc": "UTC timestamp when the projection batch was generated."},
    )
    source_url: str = field(
        default="",
        metadata={
            "doc": "Original public source URL for the report, when available.",
            "required": False,
        },
    )


@dataclass(frozen=True)
class ReportSectionProjection(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Projected section row schema version."}
    )
    section_uid: EntityUid = field(metadata={"doc": "Stable projected section UID."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    section_id: str = field(metadata={"doc": "Source-local section identifier."})
    title: str = field(metadata={"doc": "Section title."})
    summary: str = field(metadata={"doc": "Section summary."})
    key_points: List[str] = field(metadata={"doc": "Section key points."})
    pages: List[int] = field(metadata={"doc": "One-based source pages."})
    order_index: int = field(metadata={"doc": "Zero-based order in the source pack."})
    lineage: ProjectionLineage = field(metadata={"doc": "Projection lineage metadata."})


@dataclass(frozen=True)
class ReportFindingProjection(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Projected finding row schema version."}
    )
    finding_uid: EntityUid = field(metadata={"doc": "Stable projected finding UID."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    finding_id: str = field(metadata={"doc": "Source-local finding identifier."})
    text: str = field(metadata={"doc": "Finding statement text."})
    evidence: str = field(metadata={"doc": "Supporting evidence text."})
    confidence: str = field(metadata={"doc": "Confidence descriptor or value."})
    pages: List[int] = field(metadata={"doc": "One-based source pages."})
    lineage: ProjectionLineage = field(metadata={"doc": "Projection lineage metadata."})


@dataclass(frozen=True)
class ReportMetricProjection(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Projected metric row schema version."}
    )
    metric_uid: EntityUid = field(metadata={"doc": "Stable projected metric UID."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    metric_id: str = field(metadata={"doc": "Source-local metric identifier."})
    metric: str = field(metadata={"doc": "Metric label."})
    value: str = field(metadata={"doc": "Metric value."})
    unit: str = field(metadata={"doc": "Metric unit, if present."})
    evidence_id: str = field(
        metadata={"doc": "Evidence identifier backing the metric."}
    )
    pages: List[int] = field(metadata={"doc": "One-based source pages."})
    lineage: ProjectionLineage = field(metadata={"doc": "Projection lineage metadata."})


@dataclass(frozen=True)
class ReportQuoteProjection(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Projected quote row schema version."})
    quote_uid: EntityUid = field(metadata={"doc": "Stable projected quote UID."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    quote_id: str = field(metadata={"doc": "Source-local quote identifier."})
    text: str = field(metadata={"doc": "Quote text."})
    speaker: str = field(metadata={"doc": "Speaker or source attribution."})
    citation: str = field(metadata={"doc": "Citation text, if present."})
    page: Optional[int] = field(metadata={"doc": "One-based source page, if known."})
    evidence_id: str = field(metadata={"doc": "Evidence identifier backing the quote."})
    lineage: ProjectionLineage = field(metadata={"doc": "Projection lineage metadata."})


@dataclass(frozen=True)
class ReportClaimProjection(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Projected claim row schema version."})
    claim_uid: EntityUid = field(metadata={"doc": "Stable projected claim UID."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    claim: str = field(metadata={"doc": "Claim text."})
    evidence_id: str = field(metadata={"doc": "Evidence identifier backing the claim."})
    evidence: str = field(metadata={"doc": "Evidence text backing the claim."})
    pages: List[int] = field(metadata={"doc": "One-based source pages."})
    lineage: ProjectionLineage = field(metadata={"doc": "Projection lineage metadata."})


@dataclass(frozen=True)
class ReportTagProjection(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Projected tag row schema version."})
    tag_uid: EntityUid = field(metadata={"doc": "Stable projected tag UID."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    tag: str = field(metadata={"doc": "Tag text."})
    tag_type: str = field(
        metadata={"doc": "Tag type: taxonomy, primary, or secondary."}
    )
    lineage: ProjectionLineage = field(metadata={"doc": "Projection lineage metadata."})


@dataclass(frozen=True)
class ReportCategoryProjection(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Projected category row schema version."}
    )
    category_uid: EntityUid = field(metadata={"doc": "Stable projected category UID."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    category_id: str = field(metadata={"doc": "Category identifier."})
    label: str = field(metadata={"doc": "Category label."})
    fit_score: float = field(metadata={"doc": "Fit score between 0 and 1."})
    decision: str = field(metadata={"doc": "Fit decision."})
    selected: bool = field(metadata={"doc": "Whether the category was selected."})
    evidence_sections: List[str] = field(
        metadata={"doc": "Evidence sections supporting the category fit."}
    )
    lineage: ProjectionLineage = field(metadata={"doc": "Projection lineage metadata."})


@dataclass(frozen=True)
class ReportFigureProjection(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Projected figure row schema version."}
    )
    figure_uid: EntityUid = field(metadata={"doc": "Stable projected figure UID."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    candidate_id: str = field(
        metadata={"doc": "Source candidate identifier, if known."}
    )
    image_path: str = field(metadata={"doc": "Relative image path."})
    kind: str = field(metadata={"doc": "Figure kind."})
    page: int = field(metadata={"doc": "Zero-based source page, or -1 when unknown."})
    is_primary: bool = field(metadata={"doc": "Whether this is the primary figure."})
    detected_caption: str = field(metadata={"doc": "Detected source caption."})
    generated_caption: str = field(metadata={"doc": "Generated caption, if any."})
    display_caption: str = field(metadata={"doc": "Final displayed caption."})
    caption_source: str = field(metadata={"doc": "Caption source label."})
    lineage: ProjectionLineage = field(metadata={"doc": "Projection lineage metadata."})


@dataclass(frozen=True)
class VectorProjectionQueueRow(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Vector queue row schema version."})
    entity_uid: EntityUid = field(metadata={"doc": "Projected entity UID."})
    entity_type: str = field(metadata={"doc": "Vectorizable entity type."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    text_payload: str = field(
        metadata={"doc": "Canonical text payload for future embedding."}
    )
    content_hash: str = field(
        metadata={"doc": "SHA-256 hash of canonical text and embedding metadata."}
    )
    metadata: Dict[str, Any] = field(
        metadata={"doc": "Canonical metadata for future retrieval filters."}
    )
    content_class: ContentClass = field(
        metadata={"doc": "Retrieval class: evidence, derived_evidence, or editorial."}
    )
    embedding_status: EmbeddingStatus = field(
        metadata={"doc": "Embedding lifecycle status: pending, embedded, or failed."}
    )
    embedding_version: str = field(
        metadata={"doc": "Embedding version label; empty until embedded."}
    )
    created_at_utc: str = field(metadata={"doc": "UTC timestamp when queued."})
    updated_at_utc: str = field(metadata={"doc": "UTC timestamp when updated."})


@dataclass(frozen=True)
class ClaimEmbeddingQueueItem(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Claim embedding queue item schema version."}
    )
    claim_uid: EntityUid = field(
        metadata={"doc": "Stable projected claim UID from report_claims."}
    )
    entity_uid: EntityUid = field(
        metadata={"doc": "Vector queue entity UID linked to the claim."}
    )
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    text_payload: str = field(metadata={"doc": "Canonical claim embedding text."})
    content_hash: str = field(
        metadata={"doc": "Hash of claim text and embedding-relevant metadata."}
    )
    metadata: Dict[str, Any] = field(
        metadata={"doc": "Retrieval metadata copied from vector_projection_queue."}
    )
    content_class: ContentClass = field(
        metadata={"doc": "Retrieval content class for the claim row."}
    )


@dataclass(frozen=True)
class ClaimEmbeddingRecord(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Claim embedding record version."})
    embedding_uid: EntityUid = field(
        metadata={"doc": "Deterministic embedding record UID."}
    )
    claim_uid: EntityUid = field(metadata={"doc": "Linked report_claims.claim_uid."})
    entity_uid: EntityUid = field(
        metadata={"doc": "Linked vector_projection_queue.entity_uid."}
    )
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    content_hash: str = field(metadata={"doc": "Embedded queue content hash."})
    embedding_version: str = field(metadata={"doc": "Embedding workflow version."})
    provider: str = field(metadata={"doc": "Embedding provider namespace."})
    model: str = field(metadata={"doc": "Provider embedding model ID."})
    dimensions: Optional[int] = field(
        metadata={"doc": "Vector dimensionality for embedded records."}
    )
    vector: Optional[List[float]] = field(
        metadata={"doc": "Stored embedding vector for embedded records."}
    )
    external_vector_id: str = field(
        metadata={"doc": "External vector-store ID when vectors are stored remotely."}
    )
    metadata: Dict[str, Any] = field(
        metadata={"doc": "Retrieval metadata used to filter embedded claims."}
    )
    status: ClaimEmbeddingStatus = field(
        metadata={"doc": "Embedding record lifecycle status."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp for this embedding attempt."}
    )
    updated_at_utc: str = field(
        metadata={"doc": "UTC timestamp for the latest write of this record."}
    )
    attempt_count: int = field(
        metadata={"doc": "Number of writes for this deterministic embedding record."}
    )
    error_code: str = field(metadata={"doc": "Typed error code for failed records."})
    error_message: str = field(
        metadata={"doc": "Sanitized error message for failed records."}
    )
    error_retryable: bool = field(
        metadata={"doc": "Whether the failure is retryable by an orchestrator."}
    )
    error_severity: str = field(
        metadata={"doc": "Typed failure severity for failed records."}
    )


@dataclass(frozen=True)
class ClaimEmbeddingPendingReadRequest:
    schema_version: str = field(
        metadata={"doc": "Pending claim embedding read request schema version."}
    )
    db_path: str = field(metadata={"doc": "SQLite reports DB path."})
    embedding_version: str = field(
        metadata={"doc": "Embedding version to compare against existing records."}
    )
    provider: str = field(metadata={"doc": "Embedding provider namespace."})
    model: str = field(metadata={"doc": "Embedding model ID."})
    limit: int = field(metadata={"doc": "Maximum number of claim rows to read."})


@dataclass(frozen=True)
class ClaimEmbeddingPendingReadResponse(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Pending claim embedding read response schema version."}
    )
    rows: List[ClaimEmbeddingQueueItem] = field(
        metadata={"doc": "Claim queue rows requiring embedding or re-embedding."}
    )


@dataclass(frozen=True)
class ClaimEmbeddingPersistRequest:
    schema_version: str = field(
        metadata={"doc": "Claim embedding persist request schema version."}
    )
    db_path: str = field(metadata={"doc": "SQLite reports DB path."})
    record: ClaimEmbeddingRecord = field(
        metadata={"doc": "Claim embedding record to persist."}
    )
    queue_actor: str = field(
        default="claim_embedding_workflow",
        metadata={"doc": "Workflow or operator recording the queue transition."},
    )
    queue_run_id: str = field(
        default="", metadata={"doc": "Run identifier retained with the transition."}
    )
    queue_reason_code: str = field(
        default="", metadata={"doc": "Typed reason for the queue transition."}
    )
    next_eligible_at_utc: str = field(
        default="",
        metadata={"doc": "Retry eligibility timestamp for a retryable failure."},
    )
    execution_lease_id: str = field(
        default="",
        metadata={"doc": "Optional execution lease that must be released."},
    )


@dataclass(frozen=True)
class ClaimEmbeddingPersistResponse(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Claim embedding persist response schema version."}
    )
    embedding_uid: EntityUid = field(
        metadata={"doc": "Persisted deterministic embedding UID."}
    )
    status: ClaimEmbeddingStatus = field(
        metadata={"doc": "Persisted embedding status."}
    )


@dataclass(frozen=True)
class ClaimEmbeddingReadRequest:
    schema_version: str = field(
        metadata={"doc": "Claim embedding read request schema version."}
    )
    db_path: str = field(metadata={"doc": "SQLite reports DB path."})
    claim_uids: List[str] = field(
        default_factory=list, metadata={"doc": "Optional claim UID filter."}
    )
    report_ids: List[str] = field(
        default_factory=list, metadata={"doc": "Optional report ID filter."}
    )
    topics: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Optional topic filter matched against taxonomy and category IDs."
        },
    )
    statuses: List[ClaimEmbeddingStatus] = field(
        default_factory=lambda: ["embedded"],
        metadata={"doc": "Embedding statuses to return."},
    )
    limit: int = field(default=100, metadata={"doc": "Maximum records to return."})


@dataclass(frozen=True)
class ClaimEmbeddingReadResponse(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Claim embedding read response schema version."}
    )
    embeddings: List[ClaimEmbeddingRecord] = field(
        metadata={"doc": "Durable claim embedding records."}
    )


@dataclass(frozen=True)
class ClaimEmbeddingWorkflowRequest:
    schema_version: str = field(
        metadata={"doc": "Claim embedding workflow request schema version."}
    )
    db_path: str = field(metadata={"doc": "SQLite reports DB path."})
    api_key: str = field(metadata={"doc": "Provider API key loaded from env/config."})
    provider: str = field(metadata={"doc": "Embedding provider namespace."})
    model: str = field(metadata={"doc": "Embedding model ID."})
    embedding_version: str = field(metadata={"doc": "Embedding workflow version."})
    limit: int = field(metadata={"doc": "Maximum queued claims to process."})
    timeout_seconds: Optional[float] = field(
        metadata={"doc": "Provider timeout in seconds, if set."}
    )
    ctx: RunContext = field(metadata={"doc": "Run context used for structured logs."})
    cost_ledger_path: str = field(
        default="./out/cost-ledger.jsonl",
        metadata={"doc": "Filesystem path for provider cost ledger JSONL."},
    )
    cost_daily_path: str = field(
        default="./out/cost-daily.json",
        metadata={"doc": "Filesystem path for provider daily cost rollup."},
    )
    model_pricing: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Per-model pricing table for cost estimation."},
    )
    max_reports: int = field(
        default=0,
        metadata={"doc": "Maximum distinct reports; zero preserves the row limit."},
    )
    max_estimated_tokens: int = field(
        default=0,
        metadata={"doc": "Maximum estimated input tokens; zero disables this cap."},
    )
    max_estimated_cost_usd: float = field(
        default=0.0,
        metadata={"doc": "Maximum estimated spend in USD; zero disables this cap."},
    )
    max_runtime_seconds: float = field(
        default=0.0,
        metadata={"doc": "Maximum wall-clock time; zero disables this cap."},
    )
    max_retries: int = field(
        default=3,
        metadata={"doc": "Maximum retryable failures before terminal escalation."},
    )
    max_concurrent_provider_calls: int = field(
        default=1,
        metadata={"doc": "Provider-call concurrency cap; this workflow is sequential."},
    )
    publisher_fairness_limit: int = field(
        default=0,
        metadata={
            "doc": "Maximum selected rows per publisher; zero disables fairness."
        },
    )
    report_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Optional report-scoped execution filter."},
    )
    publishers: List[str] = field(
        default_factory=list,
        metadata={"doc": "Optional publisher-scoped execution filter."},
    )
    dry_run: bool = field(
        default=False,
        metadata={"doc": "When true, admission is reported without writes or calls."},
    )
    state_db: str = field(
        default="",
        metadata={"doc": "Optional canonical remediation-ledger state database."},
    )


@dataclass(frozen=True)
class ClaimEmbeddingWorkflowResponse(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Claim embedding workflow response schema version."}
    )
    embedded_count: int = field(metadata={"doc": "Number of embedded claim records."})
    failed_count: int = field(metadata={"doc": "Number of failed claim records."})
    skipped_count: int = field(
        metadata={"doc": "Number of rows skipped before provider calls."}
    )
    processed_entity_uids: List[EntityUid] = field(
        metadata={"doc": "Entity UIDs attempted by this workflow run."}
    )
    provider_calls_avoided: int = field(
        default=0,
        metadata={"doc": "Rows resolved without a provider call."},
    )
    estimated_cost_avoided_usd: float = field(
        default=0.0,
        metadata={"doc": "Estimated spend avoided through deterministic admission."},
    )
    actual_input_tokens: int = field(
        default=0,
        metadata={"doc": "Provider-reported input tokens for completed calls."},
    )
    actual_cost_usd: float = field(
        default=0.0,
        metadata={"doc": "Estimated actual cost from provider-reported usage."},
    )
    queue_age_before_seconds: int = field(
        default=0,
        metadata={"doc": "Oldest eligible queue age before this bounded batch."},
    )
    queue_age_after_seconds: int = field(
        default=0,
        metadata={"doc": "Oldest eligible queue age after this bounded batch."},
    )
    backlog_burndown_count: int = field(
        default=0,
        metadata={"doc": "Eligible queue rows resolved by this bounded batch."},
    )
    average_provider_latency_ms: float = field(
        default=0.0,
        metadata={"doc": "Average provider-call latency for this batch."},
    )
    p95_provider_latency_ms: float = field(
        default=0.0,
        metadata={"doc": "p95 provider-call latency for this batch."},
    )


@dataclass(frozen=True)
class ClaimEmbeddingQueueHealthRequest:
    """Read-only request for deterministic claim-embedding queue classification."""

    schema_version: str = field(
        metadata={"doc": "Queue-health request schema version."}
    )
    db_path: str = field(metadata={"doc": "SQLite reports database path."})
    embedding_version: str = field(metadata={"doc": "Required embedding version."})
    provider: str = field(metadata={"doc": "Required embedding provider."})
    model: str = field(metadata={"doc": "Required embedding model."})
    report_ids: List[str] = field(
        default_factory=list, metadata={"doc": "Optional report filter."}
    )
    publishers: List[str] = field(
        default_factory=list, metadata={"doc": "Optional publisher filter."}
    )
    entity_types: List[str] = field(
        default_factory=list,
        metadata={"doc": "Optional projected entity-type filter."},
    )
    max_estimated_tokens: int = field(
        default=0,
        metadata={"doc": "Optional per-run token ceiling used for classification."},
    )
    max_estimated_cost_usd: float = field(
        default=0.0,
        metadata={"doc": "Optional per-run spend ceiling used for classification."},
    )
    model_pricing: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Pricing map used only for deterministic estimates."},
    )


@dataclass(frozen=True)
class ClaimEmbeddingQueueHealthItem(SemanticIdContract):
    """One classified queue row and the metadata needed for safe admission."""

    schema_version: str = field(metadata={"doc": "Queue-health item schema version."})
    entity_uid: EntityUid = field(metadata={"doc": "Queue entity identifier."})
    report_id: ReportId = field(metadata={"doc": "Queue report identifier."})
    entity_type: str = field(metadata={"doc": "Projected entity type."})
    publisher: str = field(metadata={"doc": "Derived publisher when available."})
    content_class: str = field(metadata={"doc": "Projected content class."})
    content_hash: str = field(metadata={"doc": "Queued content hash."})
    projection_schema_version: str = field(
        metadata={"doc": "Projection schema version for the queued row."}
    )
    embedding_status: str = field(metadata={"doc": "Current queue embedding status."})
    embedding_version: str = field(metadata={"doc": "Current queue embedding version."})
    provider: str = field(metadata={"doc": "Requested embedding provider."})
    model: str = field(metadata={"doc": "Requested embedding model."})
    error_code: str = field(metadata={"doc": "Current typed queue reason code."})
    error_retryable: bool = field(
        metadata={"doc": "Whether queue failure is retryable."}
    )
    attempt_count: int = field(metadata={"doc": "Recorded queue attempt count."})
    next_eligible_at_utc: str = field(
        metadata={"doc": "Timestamp before which retries are not eligible."}
    )
    created_at_utc: str = field(metadata={"doc": "Queue creation timestamp."})
    updated_at_utc: str = field(metadata={"doc": "Queue update timestamp."})
    age_bucket: str = field(metadata={"doc": "Deterministic queue-age bucket."})
    classification: QueueClassification = field(
        metadata={"doc": "Deterministic no-call queue classification."}
    )
    classification_reason: str = field(
        metadata={"doc": "Machine-readable classification explanation."}
    )
    estimated_tokens: int = field(
        metadata={"doc": "Deterministic input-token estimate."}
    )
    estimated_cost_usd: float = field(
        metadata={"doc": "Deterministic USD-cost estimate."}
    )
    text_payload: str = field(
        metadata={"doc": "Canonical text retained only for bounded execution."}
    )
    metadata: Dict[str, Any] = field(
        metadata={"doc": "Projected retrieval metadata for execution and fairness."}
    )


@dataclass(frozen=True)
class ClaimEmbeddingQueueHealthResponse(SemanticIdContract):
    """Read-only queue-health result, suitable for JSON artifact rendering."""

    schema_version: str = field(
        metadata={"doc": "Queue-health response schema version."}
    )
    items: List[ClaimEmbeddingQueueHealthItem] = field(
        metadata={"doc": "Deterministically ordered classified queue rows."}
    )
    classification_counts: Dict[str, int] = field(
        metadata={"doc": "Count of rows by classification."}
    )
    status_counts: Dict[str, int] = field(
        metadata={"doc": "Count of rows by current queue status."}
    )
    total_pending: int = field(
        metadata={"doc": "Total rows currently carrying pending queue status."}
    )
    oldest_pending_age_seconds: int = field(
        metadata={"doc": "Age of oldest pending or retryable row."}
    )


@dataclass(frozen=True)
class ClaimEmbeddingQueueReconcileRequest:
    """No-provider mutation request for deterministic queue reconciliation."""

    schema_version: str = field(
        metadata={"doc": "Queue-reconcile request schema version."}
    )
    health_request: ClaimEmbeddingQueueHealthRequest = field(
        metadata={"doc": "Read-only criteria used immediately before reconciliation."}
    )
    run_id: str = field(metadata={"doc": "Audit run identifier."})
    actor: str = field(metadata={"doc": "Operator or workflow name."})
    dry_run: bool = field(metadata={"doc": "When true, do not mutate the queue."})


@dataclass(frozen=True)
class ClaimEmbeddingQueueReconcileResponse(SemanticIdContract):
    """Auditable outcome of no-provider queue reconciliation."""

    schema_version: str = field(
        metadata={"doc": "Queue-reconcile response schema version."}
    )
    run_id: str = field(metadata={"doc": "Audit run identifier."})
    transitioned_entity_uids: List[EntityUid] = field(
        metadata={"doc": "Rows whose queue state changed."}
    )
    classification_counts: Dict[str, int] = field(
        metadata={"doc": "Classifications considered by reconciliation."}
    )
    provider_calls_avoided: int = field(
        metadata={"doc": "Rows resolved without provider calls."}
    )


@dataclass(frozen=True)
class AnalyticsProjectionBatch(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Projection batch schema version."})
    projection_version: str = field(
        metadata={"doc": "Version of the analytics projection mapping rules."}
    )
    report: AnalyticsReportRow = field(metadata={"doc": "Projected report row."})
    sections: List[ReportSectionProjection] = field(
        metadata={"doc": "Projected section rows."}
    )
    findings: List[ReportFindingProjection] = field(
        metadata={"doc": "Projected finding rows."}
    )
    metrics: List[ReportMetricProjection] = field(
        metadata={"doc": "Projected metric rows."}
    )
    quotes: List[ReportQuoteProjection] = field(
        metadata={"doc": "Projected quote rows."}
    )
    claims: List[ReportClaimProjection] = field(
        metadata={"doc": "Projected claim rows."}
    )
    tags: List[ReportTagProjection] = field(metadata={"doc": "Projected tag rows."})
    categories: List[ReportCategoryProjection] = field(
        metadata={"doc": "Projected category rows."}
    )
    figures: List[ReportFigureProjection] = field(
        metadata={"doc": "Projected figure rows."}
    )
    vector_queue: List[VectorProjectionQueueRow] = field(
        metadata={"doc": "Vector-ready projection queue rows."}
    )


@dataclass(frozen=True)
class AnalyticsProjectionBuildRequest:
    schema_version: str = field(
        metadata={"doc": "Projection build request schema version."}
    )
    analysis: ReportAnalysisState = field(
        metadata={"doc": "Completed report analysis state used as projection source."}
    )
    rendered_html_path: str = field(
        metadata={"doc": "Rendered HTML path from the assembled report outcome."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp for this projection attempt."}
    )


@dataclass(frozen=True)
class AnalyticsProjectionUpsertRequest:
    schema_version: str = field(
        metadata={"doc": "Analytics projection upsert request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "SQLite database path for analytics projection tables."}
    )
    batch: AnalyticsProjectionBatch = field(
        metadata={"doc": "Projection batch to persist."}
    )


@dataclass(frozen=True)
class AnalyticsProjectionUpsertResponse(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Analytics projection upsert response schema version."}
    )
    report_id: ReportId = field(
        metadata={"doc": "Canonical report identifier that was projected."}
    )
    projection_status: ProjectionStatus = field(
        metadata={"doc": "Projection status after upsert."}
    )
    projection_attempt_count: int = field(
        metadata={"doc": "Recorded projection attempt count after upsert."}
    )
    rows_upserted: int = field(metadata={"doc": "Number of projection rows upserted."})
    vector_queue_count: int = field(
        metadata={"doc": "Number of vector queue rows upserted."}
    )


@dataclass(frozen=True)
class AnalyticsProjectionFailureRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Projection failure request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "SQLite database path for analytics projection metadata."}
    )
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    projection_schema_version: str = field(
        metadata={"doc": "Projection schema version."}
    )
    projection_version: str = field(metadata={"doc": "Projection mapping version."})
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp of the failed attempt."}
    )
    error_code: str = field(metadata={"doc": "Typed projection error code."})
    error_message: str = field(metadata={"doc": "Projection error message."})
    error_retryable: bool = field(
        metadata={"doc": "Whether the projection failure is retryable."}
    )


@dataclass(frozen=True)
class AnalyticsProjectionFailureResponse(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "Projection failure response schema version."}
    )
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    projection_status: ProjectionStatus = field(
        metadata={"doc": "Projection status after failure recording."}
    )
    projection_attempt_count: int = field(
        metadata={"doc": "Recorded projection attempt count after failure."}
    )


@dataclass(frozen=True)
class AnalyticsProjectionRunRequest:
    schema_version: str = field(
        metadata={"doc": "Analytics projection run request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "SQLite database path for analytics projection tables."}
    )
    analysis: ReportAnalysisState = field(
        metadata={"doc": "Completed report analysis state used as projection source."}
    )
    rendered_html_path: str = field(
        metadata={"doc": "Rendered HTML path from the assembled report outcome."}
    )
    ctx: RunContext = field(metadata={"doc": "Run context used for structured logs."})
