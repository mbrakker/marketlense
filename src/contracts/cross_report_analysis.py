from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from typing import Any, Dict, List, Literal, Optional

from src.utils.errors import AppError


CROSS_REPORT_ANALYSIS_SCHEMA_VERSION = "1.0"

PublicationMode = Literal[
    "generate_only",
    "validate_only",
    "publish_dry_run",
    "publish_live",
]
ProjectionReadinessStatus = Literal["not_projected", "projected", "failed"]
CrossReportContentClass = Literal[
    "claim",
    "finding",
    "quote",
    "metric",
    "section",
    "figure",
]
CrossReportValidationStatus = Literal["pass", "fail"]
CrossReportOutcomeStatus = Literal[
    "generated",
    "validated",
    "published",
    "skipped",
    "failed",
]
CrossReportPublishStatus = Literal[
    "not_requested",
    "dry_run",
    "published",
    "skipped",
    "error",
]


@dataclass(frozen=True)
class CrossReportAnalysisRequest:
    schema_version: str = field(metadata={"doc": "Request contract schema version."})
    request_id: str = field(
        metadata={"doc": "Stable operator or orchestrator request identifier."}
    )
    topic: str = field(
        metadata={
            "doc": "Explicit requested analysis topic; empty only when auto-theme selection is enabled."
        }
    )
    auto_theme: bool = field(
        metadata={"doc": "Whether deterministic theme selection may choose the topic."}
    )
    category_filters: List[str] = field(
        metadata={"doc": "Normalized category filters applied to projected reports."}
    )
    tag_filters: List[str] = field(
        metadata={"doc": "Normalized tag filters applied to projected reports."}
    )
    publisher_filters: List[str] = field(
        metadata={"doc": "Normalized publisher filters applied to projected reports."}
    )
    date_range_start: Optional[str] = field(
        metadata={"doc": "Inclusive report date lower bound in ISO format, if set."}
    )
    date_range_end: Optional[str] = field(
        metadata={"doc": "Inclusive report date upper bound in ISO format, if set."}
    )
    max_source_reports: int = field(
        metadata={"doc": "Maximum selected projected reports for synthesis."}
    )
    diagnostic: bool = field(
        metadata={
            "doc": "Whether diagnostic mode may inspect otherwise unpublishable source sets."
        }
    )
    override_publishability: bool = field(
        metadata={
            "doc": "Explicit operator override for publishability gates; logged by orchestrators."
        }
    )
    publication_mode: PublicationMode = field(
        metadata={"doc": "Requested publication mode for this workflow."}
    )


@dataclass(frozen=True)
class CrossReportThemeCandidate:
    schema_version: str = field(
        metadata={"doc": "Theme candidate contract schema version."}
    )
    theme_id: str = field(metadata={"doc": "Deterministic theme identifier."})
    label: str = field(metadata={"doc": "Human-readable candidate theme label."})
    rationale: str = field(
        metadata={"doc": "Short deterministic rationale for candidate creation."}
    )
    matched_tags: List[str] = field(
        metadata={"doc": "Projected tags that contributed to this theme."}
    )
    matched_categories: List[str] = field(
        metadata={"doc": "Projected categories that contributed to this theme."}
    )
    source_report_ids: List[str] = field(
        metadata={"doc": "Report IDs that support this candidate theme."}
    )
    source_publisher_count: int = field(
        metadata={"doc": "Distinct publisher count across supporting reports."}
    )
    evidence_count: int = field(
        metadata={"doc": "Count of eligible evidence rows backing this theme."}
    )
    recency_score: float = field(metadata={"doc": "Deterministic recency component."})
    density_score: float = field(
        metadata={"doc": "Deterministic evidence-density component."}
    )
    diversity_score: float = field(
        metadata={"doc": "Deterministic source/category diversity component."}
    )
    novelty_score: float = field(
        metadata={"doc": "Deterministic novelty component against recent artifacts."}
    )
    total_score: float = field(metadata={"doc": "Total deterministic theme score."})
    rejection_risks: List[str] = field(
        default_factory=list,
        metadata={"doc": "Reasons this candidate may be rejected or down-ranked."},
    )


@dataclass(frozen=True)
class CrossReportSelectedTheme:
    schema_version: str = field(
        metadata={"doc": "Selected theme contract schema version."}
    )
    theme_id: str = field(metadata={"doc": "Selected deterministic theme identifier."})
    label: str = field(metadata={"doc": "Human-readable selected theme label."})
    rationale: str = field(metadata={"doc": "Reason the theme is publishable."})
    matched_tags: List[str] = field(
        metadata={"doc": "Tags retained for synthesis and publication metadata."}
    )
    matched_categories: List[str] = field(
        metadata={"doc": "Categories retained for synthesis and publication metadata."}
    )
    source_report_ids: List[str] = field(
        metadata={"doc": "Selected report IDs supporting the theme."}
    )
    score_components: Dict[str, float] = field(
        metadata={"doc": "Named deterministic score components for auditability."}
    )
    selection_reasons: List[str] = field(
        metadata={"doc": "Reasons this theme was selected over alternatives."}
    )
    rejection_risks: List[str] = field(
        default_factory=list,
        metadata={"doc": "Known risks carried forward for validation and logging."},
    )


@dataclass(frozen=True)
class CrossReportSourceReportCandidate:
    schema_version: str = field(
        metadata={"doc": "Source candidate contract schema version."}
    )
    report_id: str = field(metadata={"doc": "Projected report identifier."})
    title: str = field(metadata={"doc": "Projected report title."})
    publisher: str = field(metadata={"doc": "Projected publisher display name."})
    publisher_id: str = field(
        metadata={"doc": "Stable publisher identifier when available."}
    )
    report_date: str = field(
        metadata={"doc": "Projected report publication date or time period."}
    )
    projection_status: ProjectionReadinessStatus = field(
        metadata={"doc": "Projection readiness status for synthesis eligibility."}
    )
    content_hash: str = field(
        metadata={"doc": "Projection content hash used for cache/idempotency keys."}
    )
    category_labels: List[str] = field(
        metadata={"doc": "Projected category labels attached to the report."}
    )
    tags: List[str] = field(metadata={"doc": "Projected report-level tags."})
    evidence_count: int = field(
        metadata={"doc": "Total eligible evidence rows for this report."}
    )
    claim_count: int = field(metadata={"doc": "Eligible projected claim count."})
    finding_count: int = field(metadata={"doc": "Eligible projected finding count."})
    quote_count: int = field(metadata={"doc": "Eligible projected quote count."})
    metric_count: int = field(metadata={"doc": "Eligible raw metric count."})
    recency_score: float = field(metadata={"doc": "Deterministic recency score."})
    relevance_score: float = field(
        metadata={"doc": "Deterministic filter/theme relevance score."}
    )
    diversity_score: float = field(
        metadata={"doc": "Deterministic publisher/category diversity score."}
    )
    density_score: float = field(
        metadata={"doc": "Deterministic evidence density score."}
    )
    total_score: float = field(metadata={"doc": "Total deterministic ranking score."})
    selection_reasons: List[str] = field(
        metadata={"doc": "Reasons this candidate is eligible or selected."}
    )
    rejection_reasons: List[str] = field(
        default_factory=list,
        metadata={"doc": "Reasons this candidate was rejected, if applicable."},
    )


@dataclass(frozen=True)
class CrossReportSelectedSourceReport:
    schema_version: str = field(
        metadata={"doc": "Selected source report contract schema version."}
    )
    report_id: str = field(metadata={"doc": "Selected projected report identifier."})
    title: str = field(metadata={"doc": "Selected report title."})
    publisher: str = field(metadata={"doc": "Selected report publisher name."})
    publisher_id: str = field(
        metadata={"doc": "Stable publisher identifier when available."}
    )
    report_date: str = field(
        metadata={"doc": "Selected report publication date or time period."}
    )
    projection_status: ProjectionReadinessStatus = field(
        metadata={"doc": "Projection readiness status at selection time."}
    )
    content_hash: str = field(
        metadata={"doc": "Projection content hash used for reproducibility."}
    )
    rank: int = field(metadata={"doc": "One-based deterministic selected-source rank."})
    selection_reasons: List[str] = field(
        metadata={"doc": "Reasons the report was selected."}
    )
    evidence_count: int = field(
        metadata={"doc": "Eligible evidence count retained for synthesis."}
    )
    category_labels: List[str] = field(
        metadata={"doc": "Projected categories retained for prompt metadata."}
    )
    tags: List[str] = field(
        metadata={"doc": "Projected tags retained for prompt metadata."}
    )


@dataclass(frozen=True)
class CrossReportEvidenceReference:
    schema_version: str = field(
        metadata={"doc": "Evidence reference contract schema version."}
    )
    evidence_id: str = field(metadata={"doc": "Stable selected evidence identifier."})
    report_id: str = field(metadata={"doc": "Source projected report identifier."})
    publisher: str = field(metadata={"doc": "Source publisher display name."})
    title: str = field(metadata={"doc": "Source report title."})
    source_table: str = field(
        metadata={"doc": "Projection table or source family for this evidence row."}
    )
    entity_uid: str = field(metadata={"doc": "Projection entity UID."})
    content_class: CrossReportContentClass = field(
        metadata={"doc": "Evidence content class used by synthesis and validation."}
    )
    text: str = field(metadata={"doc": "Compact text payload supplied to synthesis."})
    source_metadata: Dict[str, Any] = field(
        metadata={"doc": "Source-specific metadata such as page, section, or citation."}
    )


@dataclass(frozen=True)
class CrossReportSignalScore:
    schema_version: str = field(metadata={"doc": "Signal score schema version."})
    signal_id: str = field(metadata={"doc": "Stable signal identifier."})
    label: str = field(metadata={"doc": "Human-readable signal label."})
    evidence_ids: List[str] = field(
        metadata={"doc": "Evidence IDs supporting this signal."}
    )
    component_scores: Dict[str, float] = field(
        metadata={"doc": "Named deterministic signal score components."}
    )
    total_score: float = field(metadata={"doc": "Total deterministic signal score."})
    reasons: List[str] = field(metadata={"doc": "Reasons this signal was retained."})


@dataclass(frozen=True)
class CrossReportRawMetricReference:
    schema_version: str = field(
        metadata={"doc": "Raw metric reference contract schema version."}
    )
    metric_id: str = field(metadata={"doc": "Stable selected metric identifier."})
    report_id: str = field(metadata={"doc": "Source projected report identifier."})
    publisher: str = field(metadata={"doc": "Source publisher display name."})
    label: str = field(metadata={"doc": "Metric label from the source projection."})
    raw_value: str = field(
        metadata={"doc": "Original metric value exactly as projected from source."}
    )
    unit: str = field(metadata={"doc": "Original metric unit, if available."})
    context: str = field(
        metadata={"doc": "Source-specific metric context and scope statement."}
    )
    evidence_id: str = field(
        metadata={"doc": "Evidence identifier backing this raw metric."}
    )
    source_metadata: Dict[str, Any] = field(
        metadata={"doc": "Source-specific metadata such as page or section."}
    )


@dataclass(frozen=True)
class CrossReportAnalysisSection:
    schema_version: str = field(
        metadata={"doc": "Generated analysis section contract schema version."}
    )
    section_id: str = field(metadata={"doc": "Stable generated section identifier."})
    heading: str = field(metadata={"doc": "Generated section heading."})
    body: str = field(metadata={"doc": "Generated section body text or HTML."})
    evidence_ids: List[str] = field(
        metadata={"doc": "Evidence IDs cited by this generated section."}
    )
    raw_metric_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Raw metric references cited by this section."},
    )


@dataclass(frozen=True)
class CrossReportGeneratedAnalysisResult:
    schema_version: str = field(
        metadata={"doc": "Generated analysis result contract schema version."}
    )
    analysis_id: str = field(metadata={"doc": "Stable generated analysis identifier."})
    title: str = field(metadata={"doc": "Publish-ready generated analysis title."})
    slug: str = field(metadata={"doc": "Deterministic generated analysis slug."})
    executive_summary: str = field(
        metadata={"doc": "Generated executive summary text."}
    )
    selected_theme: CrossReportSelectedTheme = field(
        metadata={"doc": "Selected theme used for synthesis."}
    )
    selected_sources: List[CrossReportSelectedSourceReport] = field(
        metadata={"doc": "Selected reports used for synthesis."}
    )
    evidence: List[CrossReportEvidenceReference] = field(
        metadata={"doc": "Evidence references supplied to and cited by synthesis."}
    )
    signal_scores: List[CrossReportSignalScore] = field(
        metadata={"doc": "Deterministic signal scores used to focus synthesis."}
    )
    raw_metrics: List[CrossReportRawMetricReference] = field(
        metadata={"doc": "Raw source-specific metrics preserved without normalization."}
    )
    sections: List[CrossReportAnalysisSection] = field(
        metadata={"doc": "Generated structured analysis sections."}
    )
    evidence_map: Dict[str, List[str]] = field(
        metadata={"doc": "Generated claim/section references mapped to evidence IDs."}
    )
    prompt_hashes: Dict[str, str] = field(
        metadata={"doc": "Prompt hashes used for reproducibility and cache keys."}
    )
    model: str = field(metadata={"doc": "Model identifier used for synthesis."})
    cost_summary: Dict[str, Any] = field(
        metadata={"doc": "Token/cost summary when available from the LLM boundary."}
    )


@dataclass(frozen=True)
class CrossReportValidationResult:
    schema_version: str = field(
        metadata={"doc": "Validation result contract schema version."}
    )
    status: CrossReportValidationStatus = field(
        metadata={"doc": "Deterministic validation status."}
    )
    checked_evidence_ids: List[str] = field(
        metadata={"doc": "Evidence IDs observed by deterministic validation."}
    )
    missing_evidence_ids: List[str] = field(
        default_factory=list,
        metadata={"doc": "Cited evidence IDs that were absent from selected evidence."},
    )
    issues: List[str] = field(
        default_factory=list,
        metadata={"doc": "Validation issue messages or codes."},
    )
    metric_normalization_violations: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Generated phrases that imply forbidden cross-source metric normalization."
        },
    )
    prompt_budget_chars: int = field(
        default=0,
        metadata={"doc": "Rendered prompt/input character count checked by validation."},
    )
    passed: bool = field(
        default=False,
        metadata={"doc": "True when validation status is pass and no blockers exist."},
    )


@dataclass(frozen=True)
class CrossReportPublishRequestSummary:
    schema_version: str = field(
        metadata={"doc": "Publish request summary contract schema version."}
    )
    publication_mode: PublicationMode = field(
        metadata={"doc": "Publication mode requested by the operator or orchestrator."}
    )
    target_route: str = field(
        metadata={"doc": "Existing publish route or target surface identifier."}
    )
    title: str = field(metadata={"doc": "Publish-ready title."})
    slug: str = field(metadata={"doc": "Publish-ready slug."})
    artifact_path: str = field(
        metadata={"doc": "Canonical local analysis artifact path."}
    )
    validation_status: CrossReportValidationStatus = field(
        metadata={"doc": "Validation status used for publish gating."}
    )
    selected_report_ids: List[str] = field(
        metadata={"doc": "Selected source report IDs used in publish idempotency."}
    )
    selected_theme_id: str = field(
        metadata={"doc": "Selected theme ID used in publish idempotency."}
    )


@dataclass(frozen=True)
class CrossReportPublishResultSummary:
    schema_version: str = field(
        metadata={"doc": "Publish result summary contract schema version."}
    )
    publication_mode: PublicationMode = field(
        metadata={"doc": "Publication mode that was evaluated."}
    )
    status: CrossReportPublishStatus = field(
        metadata={"doc": "Publish outcome status from the existing publish pathway."}
    )
    target_route: str = field(metadata={"doc": "Publish route that was evaluated."})
    idempotency_reused: bool = field(
        metadata={"doc": "Whether an existing publish outcome was reused."}
    )
    post_id: Optional[int] = field(
        default=None,
        metadata={"doc": "WordPress post ID when live publication produced one."}
    )
    post_url: Optional[str] = field(
        default=None,
        metadata={"doc": "WordPress post URL when live publication produced one."}
    )
    error_code: Optional[str] = field(
        default=None,
        metadata={"doc": "Typed publish error code when status is error."}
    )
    error_message: Optional[str] = field(
        default=None,
        metadata={"doc": "Sanitized publish error message when status is error."}
    )


@dataclass(frozen=True)
class CrossReportOrchestratorOutcome:
    schema_version: str = field(
        metadata={"doc": "Orchestrator outcome contract schema version."}
    )
    run_id: str = field(metadata={"doc": "Run identifier for structured logs."})
    task_id: str = field(metadata={"doc": "Task identifier for structured logs."})
    status: CrossReportOutcomeStatus = field(
        metadata={"doc": "Final orchestrator workflow status."}
    )
    artifact_path: str = field(
        metadata={"doc": "Canonical generated analysis artifact path."}
    )
    request: CrossReportAnalysisRequest = field(
        metadata={"doc": "Validated request that started the workflow."}
    )
    generated_result: CrossReportGeneratedAnalysisResult = field(
        metadata={"doc": "Generated analysis result, if synthesis completed."}
    )
    validation_result: CrossReportValidationResult = field(
        metadata={"doc": "Deterministic validation result."}
    )
    publish_request: CrossReportPublishRequestSummary = field(
        metadata={"doc": "Publish request summary evaluated by the orchestrator."}
    )
    publish_result: CrossReportPublishResultSummary = field(
        metadata={"doc": "Publish result summary from the publish boundary."}
    )
    idempotency_key: str = field(
        metadata={"doc": "Idempotency key for generation and publication reuse."}
    )
    idempotency_reused: bool = field(
        metadata={"doc": "Whether this orchestrator outcome reused a prior result."}
    )
    state_transitions: List[str] = field(
        metadata={"doc": "Ordered workflow state transitions recorded by orchestrator."}
    )


def validate_cross_report_contract(contract: object) -> None:
    _validate_contract_value(contract, path=type(contract).__name__)


def _raise_invalid(path: str, field_name: str, reason: str) -> None:
    raise AppError(
        code="cross_report_contract_invalid",
        message=f"Invalid cross-report contract field {path}: {reason}",
        retryable=False,
        severity="error",
        context={"path": path, "field": field_name, "reason": reason},
    )


def _field_is_required(field_def: Any) -> bool:
    return field_def.default is MISSING and field_def.default_factory is MISSING


def _empty_required_value(value: object) -> bool:
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    return False


def _validate_contract_value(value: object, *, path: str) -> None:
    if is_dataclass(value):
        _validate_dataclass_instance(value, path=path)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_contract_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _validate_contract_value(item, path=f"{path}.{key}")


def _validate_dataclass_instance(instance: object, *, path: str) -> None:
    for field_def in fields(instance):
        field_value = getattr(instance, field_def.name)
        field_path = f"{path}.{field_def.name}"
        if field_def.name == "schema_version":
            if field_value != CROSS_REPORT_ANALYSIS_SCHEMA_VERSION:
                _raise_invalid(field_path, field_def.name, "unsupported schema version")
        if _field_is_required(field_def) and _empty_required_value(field_value):
            _raise_invalid(field_path, field_def.name, "required value is empty")
        _validate_contract_value(field_value, path=field_path)
