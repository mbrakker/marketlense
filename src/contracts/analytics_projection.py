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
ContentClass = Literal["evidence", "derived_evidence", "editorial"]


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
    schema_version: str = field(metadata={"doc": "Projected report row schema version."})
    projection_version: str = field(
        metadata={"doc": "Version of the analytics projection mapping rules."}
    )
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    title: str = field(metadata={"doc": "Projected report title."})
    publisher: str = field(metadata={"doc": "Projected publisher display name, if known."})
    publisher_id: Optional[PublisherId] = field(
        default=None,
        metadata={"doc": "Stable publisher identifier derived from publisher text, if known."},
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


@dataclass(frozen=True)
class ReportSectionProjection(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Projected section row schema version."})
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
    schema_version: str = field(metadata={"doc": "Projected finding row schema version."})
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
    schema_version: str = field(metadata={"doc": "Projected metric row schema version."})
    metric_uid: EntityUid = field(metadata={"doc": "Stable projected metric UID."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    metric_id: str = field(metadata={"doc": "Source-local metric identifier."})
    metric: str = field(metadata={"doc": "Metric label."})
    value: str = field(metadata={"doc": "Metric value."})
    unit: str = field(metadata={"doc": "Metric unit, if present."})
    evidence_id: str = field(metadata={"doc": "Evidence identifier backing the metric."})
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
    tag_type: str = field(metadata={"doc": "Tag type: taxonomy, primary, or secondary."})
    lineage: ProjectionLineage = field(metadata={"doc": "Projection lineage metadata."})


@dataclass(frozen=True)
class ReportCategoryProjection(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Projected category row schema version."})
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
    schema_version: str = field(metadata={"doc": "Projected figure row schema version."})
    figure_uid: EntityUid = field(metadata={"doc": "Stable projected figure UID."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    candidate_id: str = field(metadata={"doc": "Source candidate identifier, if known."})
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
    text_payload: str = field(metadata={"doc": "Canonical text payload for future embedding."})
    content_hash: str = field(metadata={"doc": "SHA-256 hash of canonical text and embedding metadata."})
    metadata: Dict[str, Any] = field(metadata={"doc": "Canonical metadata for future retrieval filters."})
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
class AnalyticsProjectionBatch(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Projection batch schema version."})
    projection_version: str = field(
        metadata={"doc": "Version of the analytics projection mapping rules."}
    )
    report: AnalyticsReportRow = field(metadata={"doc": "Projected report row."})
    sections: List[ReportSectionProjection] = field(metadata={"doc": "Projected section rows."})
    findings: List[ReportFindingProjection] = field(metadata={"doc": "Projected finding rows."})
    metrics: List[ReportMetricProjection] = field(metadata={"doc": "Projected metric rows."})
    quotes: List[ReportQuoteProjection] = field(metadata={"doc": "Projected quote rows."})
    claims: List[ReportClaimProjection] = field(metadata={"doc": "Projected claim rows."})
    tags: List[ReportTagProjection] = field(metadata={"doc": "Projected tag rows."})
    categories: List[ReportCategoryProjection] = field(metadata={"doc": "Projected category rows."})
    figures: List[ReportFigureProjection] = field(metadata={"doc": "Projected figure rows."})
    vector_queue: List[VectorProjectionQueueRow] = field(
        metadata={"doc": "Vector-ready projection queue rows."}
    )


@dataclass(frozen=True)
class AnalyticsProjectionBuildRequest:
    schema_version: str = field(metadata={"doc": "Projection build request schema version."})
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
    schema_version: str = field(metadata={"doc": "Analytics projection upsert request schema version."})
    db_path: str = field(metadata={"doc": "SQLite database path for analytics projection tables."})
    batch: AnalyticsProjectionBatch = field(metadata={"doc": "Projection batch to persist."})


@dataclass(frozen=True)
class AnalyticsProjectionUpsertResponse(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Analytics projection upsert response schema version."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier that was projected."})
    projection_status: ProjectionStatus = field(metadata={"doc": "Projection status after upsert."})
    projection_attempt_count: int = field(metadata={"doc": "Recorded projection attempt count after upsert."})
    rows_upserted: int = field(metadata={"doc": "Number of projection rows upserted."})
    vector_queue_count: int = field(metadata={"doc": "Number of vector queue rows upserted."})


@dataclass(frozen=True)
class AnalyticsProjectionFailureRequest(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Projection failure request schema version."})
    db_path: str = field(metadata={"doc": "SQLite database path for analytics projection metadata."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    projection_schema_version: str = field(metadata={"doc": "Projection schema version."})
    projection_version: str = field(metadata={"doc": "Projection mapping version."})
    generated_at_utc: str = field(metadata={"doc": "UTC timestamp of the failed attempt."})
    error_code: str = field(metadata={"doc": "Typed projection error code."})
    error_message: str = field(metadata={"doc": "Projection error message."})
    error_retryable: bool = field(metadata={"doc": "Whether the projection failure is retryable."})


@dataclass(frozen=True)
class AnalyticsProjectionFailureResponse(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Projection failure response schema version."})
    report_id: ReportId = field(metadata={"doc": "Canonical report identifier."})
    projection_status: ProjectionStatus = field(metadata={"doc": "Projection status after failure recording."})
    projection_attempt_count: int = field(metadata={"doc": "Recorded projection attempt count after failure."})


@dataclass(frozen=True)
class AnalyticsProjectionRunRequest:
    schema_version: str = field(metadata={"doc": "Analytics projection run request schema version."})
    db_path: str = field(metadata={"doc": "SQLite database path for analytics projection tables."})
    analysis: ReportAnalysisState = field(
        metadata={"doc": "Completed report analysis state used as projection source."}
    )
    rendered_html_path: str = field(
        metadata={"doc": "Rendered HTML path from the assembled report outcome."}
    )
    ctx: RunContext = field(metadata={"doc": "Run context used for structured logs."})

