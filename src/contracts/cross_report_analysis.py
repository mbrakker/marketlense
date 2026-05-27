from __future__ import annotations

from dataclasses import MISSING, dataclass, field, fields, is_dataclass
from typing import Any, Dict, List, Literal, Optional, cast, get_origin, get_type_hints

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
CrossReportReadContentClass = Literal["claim", "finding", "quote", "metric"]
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
CrossReportEvidenceAgreementType = Literal["convergent", "divergent", "thin_coverage"]


@dataclass(frozen=True)
class CrossReportAnalysisRequest:
    schema_version: str = field(metadata={"doc": "Request contract schema version."})
    request_id: str = field(
        metadata={"doc": "Stable operator or orchestrator request identifier."}
    )
    topic: str = field(
        metadata={
            "doc": "Explicit requested analysis topic; empty only when auto-theme selection is enabled.",
            "required": False,
        }
    )
    auto_theme: bool = field(
        metadata={"doc": "Whether deterministic theme selection may choose the topic."}
    )
    category_filters: List[str] = field(
        metadata={
            "doc": "Normalized category filters applied to projected reports.",
            "required": False,
        }
    )
    tag_filters: List[str] = field(
        metadata={
            "doc": "Normalized tag filters applied to projected reports.",
            "required": False,
        }
    )
    publisher_filters: List[str] = field(
        metadata={
            "doc": "Normalized publisher filters applied to projected reports.",
            "required": False,
        }
    )
    date_range_start: Optional[str] = field(
        metadata={
            "doc": "Inclusive report date lower bound in ISO format, if set.",
            "required": False,
        }
    )
    date_range_end: Optional[str] = field(
        metadata={
            "doc": "Inclusive report date upper bound in ISO format, if set.",
            "required": False,
        }
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
        metadata={
            "doc": "Projected tags that contributed to this theme when tag evidence exists.",
            "required": False,
        }
    )
    matched_categories: List[str] = field(
        metadata={
            "doc": "Projected categories that contributed to this theme when category evidence exists.",
            "required": False,
        }
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
        metadata={
            "doc": "Tags retained for synthesis and publication metadata when available.",
            "required": False,
        }
    )
    matched_categories: List[str] = field(
        metadata={
            "doc": "Categories retained for synthesis and publication metadata when available.",
            "required": False,
        }
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
        metadata={
            "doc": "Projected category labels attached to the report.",
            "required": False,
        }
    )
    tags: List[str] = field(
        metadata={"doc": "Projected report-level tags.", "required": False}
    )
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
    category_ids: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Projected category identifiers retained for exact filtering.",
            "required": False,
        },
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
        metadata={
            "doc": "Projected categories retained for prompt metadata.",
            "required": False,
        }
    )
    tags: List[str] = field(
        metadata={
            "doc": "Projected tags retained for prompt metadata.",
            "required": False,
        }
    )
    category_ids: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Projected category identifiers retained for exact filtering.",
            "required": False,
        },
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
class CrossReportSignalScoreResult:
    schema_version: str = field(
        metadata={"doc": "Signal scoring result contract schema version."}
    )
    selected_theme: CrossReportSelectedTheme = field(
        metadata={"doc": "Selected theme used as the scoring focus."}
    )
    signal_scores: List[CrossReportSignalScore] = field(
        metadata={"doc": "Ranked deterministic signals retained for synthesis focus."}
    )
    selected_signal_ids: List[str] = field(
        metadata={"doc": "Ordered selected signal IDs passed to synthesis inputs."}
    )
    score_weights: Dict[str, float] = field(
        metadata={"doc": "YAML/configured score weights used for deterministic totals."}
    )
    raw_metric_policy: str = field(
        metadata={
            "doc": "Policy statement confirming raw metric magnitudes are not normalized or compared."
        }
    )
    dropped_signal_counts: Dict[str, int] = field(
        default_factory=dict,
        metadata={
            "doc": "Signal candidate counts dropped by deterministic reason.",
            "required": False,
        },
    )


@dataclass(frozen=True)
class CrossReportEvidenceAgreementGroup:
    schema_version: str = field(
        metadata={"doc": "Evidence agreement group schema version."}
    )
    group_id: str = field(metadata={"doc": "Stable evidence group identifier."})
    label: str = field(metadata={"doc": "Human-readable group label."})
    agreement_type: CrossReportEvidenceAgreementType = field(
        metadata={"doc": "Deterministic agreement label for synthesis input."}
    )
    signal_ids: List[str] = field(
        metadata={"doc": "Signal IDs that this evidence group supports."}
    )
    evidence_ids: List[str] = field(
        metadata={"doc": "Evidence IDs included in this agreement group."}
    )
    source_report_ids: List[str] = field(
        metadata={"doc": "Source report IDs represented in this group."}
    )
    publisher_count: int = field(
        metadata={"doc": "Distinct publisher count represented in this group."}
    )
    uncertainty_reasons: List[str] = field(
        metadata={"doc": "Deterministic reasons explaining agreement or uncertainty."}
    )
    prompt_input_label: str = field(
        metadata={"doc": "Compact label exposed to synthesis prompt inputs."}
    )


@dataclass(frozen=True)
class CrossReportEvidenceAgreementResult:
    schema_version: str = field(
        metadata={"doc": "Evidence agreement result schema version."}
    )
    selected_theme: CrossReportSelectedTheme = field(
        metadata={"doc": "Selected theme used when grouping evidence agreement."}
    )
    evidence_groups: List[CrossReportEvidenceAgreementGroup] = field(
        metadata={"doc": "Deterministic evidence groups passed to synthesis."}
    )
    prompt_uncertainty_inputs: List[Dict[str, Any]] = field(
        metadata={
            "doc": "Structured prompt-ready agreement and uncertainty labels with provenance."
        }
    )
    agreement_counts: Dict[str, int] = field(
        metadata={"doc": "Evidence group counts by agreement type."}
    )


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
        metadata={
            "doc": "Raw source-specific metrics preserved without normalization.",
            "required": False,
        }
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
        metadata={
            "doc": "Rendered prompt/input character count checked by validation."
        },
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
        metadata={"doc": "WordPress post ID when live publication produced one."},
    )
    post_url: Optional[str] = field(
        default=None,
        metadata={"doc": "WordPress post URL when live publication produced one."},
    )
    error_code: Optional[str] = field(
        default=None, metadata={"doc": "Typed publish error code when status is error."}
    )
    error_message: Optional[str] = field(
        default=None,
        metadata={"doc": "Sanitized publish error message when status is error."},
    )


@dataclass(frozen=True)
class CrossReportPublishPackage:
    schema_version: str = field(
        metadata={"doc": "Cross-report publish package contract schema version."}
    )
    package_id: str = field(
        metadata={"doc": "Stable package identifier used as the publish file marker."}
    )
    file_id: str = field(
        metadata={
            "doc": "Canonical pseudo file ID used by the existing publish lookup path."
        }
    )
    target_route: str = field(
        metadata={"doc": "Existing publish route or target surface identifier."}
    )
    title: str = field(metadata={"doc": "Publish-ready title."})
    slug: str = field(metadata={"doc": "Publish-ready slug."})
    excerpt: str = field(metadata={"doc": "Publish-ready excerpt or summary."})
    body_html: str = field(
        metadata={"doc": "Publish-ready body HTML fragment for WordPress."}
    )
    html_text: str = field(
        metadata={"doc": "Complete HTML document persisted for review and publishing."}
    )
    html_path: str = field(
        metadata={"doc": "Canonical local HTML publish package path."}
    )
    canonical_artifact_path: str = field(
        metadata={"doc": "Canonical local analysis JSON artifact path."}
    )
    artifact_sha256: str = field(
        metadata={"doc": "Deterministic hash of generated artifact-relevant payload."}
    )
    validation_sha256: str = field(
        metadata={"doc": "Deterministic hash of validation result payload."}
    )
    selected_theme_id: str = field(
        metadata={"doc": "Selected theme ID used in publish idempotency."}
    )
    selected_report_ids: List[str] = field(
        metadata={"doc": "Selected source report IDs represented by the package."}
    )
    source_metadata: List[Dict[str, Any]] = field(
        metadata={
            "doc": "Source report metadata map rendered and published for provenance."
        }
    )
    category_labels: List[str] = field(
        metadata={
            "doc": "Category labels carried into publish metadata.",
            "required": False,
        }
    )
    tag_labels: List[str] = field(
        metadata={"doc": "Tag labels carried into publish metadata.", "required": False}
    )
    evidence_reference_ids: List[str] = field(
        metadata={"doc": "Evidence IDs rendered into the evidence reference map."}
    )
    raw_metric_ids: List[str] = field(
        metadata={
            "doc": "Raw metric IDs rendered into the raw metric appendix when source metrics are available.",
            "required": False,
        }
    )
    prompt_hashes: Dict[str, str] = field(
        metadata={"doc": "Prompt hashes used to generate the package."}
    )
    machine_metadata: Dict[str, Any] = field(
        metadata={"doc": "Machine-readable cross-report metadata embedded in HTML."}
    )


@dataclass(frozen=True)
class CrossReportAnalysisArtifact:
    schema_version: str = field(
        metadata={"doc": "Persisted analysis artifact contract schema version."}
    )
    artifact_type: str = field(
        metadata={"doc": "Stable artifact type identifier for replay and review."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the artifact was generated."}
    )
    request_fingerprint: str = field(
        metadata={
            "doc": "Deterministic fingerprint of request, source, prompt, and config inputs."
        }
    )
    idempotency_key: str = field(
        metadata={"doc": "Orchestrator idempotency key associated with this artifact."}
    )
    selected_report_ids: List[str] = field(
        metadata={"doc": "Selected projected report IDs represented in the artifact."}
    )
    projection_content_hashes: Dict[str, Dict[str, str]] = field(
        metadata={"doc": "Projection content hashes keyed by report ID and entity UID."}
    )
    prompt_hashes: Dict[str, str] = field(
        metadata={"doc": "Prompt hashes used to generate the analysis."}
    )
    config_fingerprint: Dict[str, Any] = field(
        metadata={"doc": "Generation-relevant configuration values used for replay."}
    )
    validation_status: CrossReportValidationStatus = field(
        metadata={"doc": "Deterministic validation status at persistence time."}
    )
    request: CrossReportAnalysisRequest = field(
        metadata={"doc": "Validated business request used for synthesis."}
    )
    generated_result: CrossReportGeneratedAnalysisResult = field(
        metadata={"doc": "Generated analysis payload."}
    )
    validation_result: CrossReportValidationResult = field(
        metadata={"doc": "Validation result for the generated analysis."}
    )
    publish_request: CrossReportPublishRequestSummary = field(
        metadata={"doc": "Publish request summary derived for downstream routing."}
    )
    publish_result: CrossReportPublishResultSummary = field(
        metadata={"doc": "Publish result summary known at persistence time."}
    )
    publish_package: CrossReportPublishPackage = field(
        metadata={"doc": "Publish package generated for review or publication."}
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


@dataclass(frozen=True)
class CrossReportAnalysisOrchestratorRequest:
    schema_version: str = field(
        metadata={"doc": "Cross-report orchestrator request schema version."}
    )
    analysis_request: CrossReportAnalysisRequest = field(
        metadata={"doc": "Business request for cross-report analysis generation."}
    )
    projected_data_request: "CrossReportProjectedDataReadRequest" = field(
        metadata={"doc": "Analytics-store projected data read request."}
    )
    idempotency_db_path: str = field(
        metadata={"doc": "SQLite idempotency database path for orchestrator reuse."}
    )
    output_root: str = field(
        metadata={"doc": "Output root used to derive the planned artifact path."}
    )
    max_evidence_items: int = field(
        default=48,
        metadata={"doc": "Maximum evidence items assembled before synthesis."},
    )
    max_signals: int = field(
        default=8,
        metadata={"doc": "Maximum signal scores retained before synthesis."},
    )
    max_prompt_chars: int = field(
        default=60000,
        metadata={"doc": "Maximum prompt/input character budget for validation."},
    )
    retry_retries: int = field(
        default=2,
        metadata={"doc": "Maximum retries for retryable service/generator failures."},
    )
    retry_base_delay_seconds: float = field(
        default=1.0,
        metadata={"doc": "Base retry delay controlled by the orchestrator."},
    )
    retry_backoff_step_seconds: float = field(
        default=1.0,
        metadata={"doc": "Linear retry backoff step controlled by the orchestrator."},
    )
    retry_jitter_seconds: float = field(
        default=0.25,
        metadata={"doc": "Retry jitter controlled by the orchestrator."},
    )
    publish_target_route: str = field(
        default="wordpress:ml_report",
        metadata={"doc": "Publication target route reserved for later publish stages."},
    )


@dataclass(frozen=True)
class CrossReportProjectedDataReadRequest:
    schema_version: str = field(
        metadata={"doc": "Projected data read request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "SQLite reports database path containing projection tables."}
    )
    publisher_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Case-insensitive publisher names or IDs to include."},
    )
    date_range_start: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Inclusive projection/report date lower bound in YYYY-MM-DD format."
        },
    )
    date_range_end: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Inclusive projection/report date upper bound in YYYY-MM-DD format."
        },
    )
    category_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Case-insensitive category IDs or labels to include."},
    )
    tag_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Case-insensitive projected tags to include."},
    )
    content_classes: List[CrossReportReadContentClass] = field(
        default_factory=list,
        metadata={
            "doc": "Projected evidence classes to return; empty means claims, findings, quotes, and metrics."
        },
    )
    minimum_projection_status: ProjectionReadinessStatus = field(
        default="projected",
        metadata={
            "doc": "Minimum projection status to include: projected includes only ready reports."
        },
    )


@dataclass(frozen=True)
class CrossReportProjectedDataReadResponse:
    schema_version: str = field(
        metadata={"doc": "Projected data read response schema version."}
    )
    source_candidates: List[CrossReportSourceReportCandidate] = field(
        default_factory=list,
        metadata={"doc": "Projected report inventory rows adapted for selection."},
    )
    evidence: List[CrossReportEvidenceReference] = field(
        default_factory=list,
        metadata={"doc": "Projected claims, findings, and quotes adapted as evidence."},
    )
    raw_metrics: List[CrossReportRawMetricReference] = field(
        default_factory=list,
        metadata={"doc": "Projected raw metrics preserved as source-bound facts."},
    )
    content_hashes: Dict[str, Dict[str, str]] = field(
        default_factory=dict,
        metadata={
            "doc": "Vector projection content hashes keyed by report ID and entity UID."
        },
    )
    excluded_report_counts: Dict[str, int] = field(
        default_factory=dict,
        metadata={"doc": "Counts of reports excluded by status or request filters."},
    )


@dataclass(frozen=True)
class CrossReportSourceSelectionResult:
    schema_version: str = field(
        metadata={"doc": "Source selection result contract schema version."}
    )
    selected_sources: List[CrossReportSelectedSourceReport] = field(
        default_factory=list,
        metadata={"doc": "Ranked source reports retained for synthesis."},
    )
    ranked_candidates: List[CrossReportSourceReportCandidate] = field(
        default_factory=list,
        metadata={"doc": "Eligible candidates after deterministic scoring."},
    )
    rejected_candidates: List[CrossReportSourceReportCandidate] = field(
        default_factory=list,
        metadata={"doc": "Candidates rejected by filters or max-source limits."},
    )
    cleaned_filters: Dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Normalized request filters used for deterministic scoring."},
    )
    excluded_report_counts: Dict[str, int] = field(
        default_factory=dict,
        metadata={"doc": "Rejected report counts grouped by deterministic reason."},
    )


@dataclass(frozen=True)
class CrossReportThemeSelectionResult:
    schema_version: str = field(
        metadata={"doc": "Theme selection result contract schema version."}
    )
    selected_theme: CrossReportSelectedTheme = field(
        metadata={"doc": "Selected deterministic theme for synthesis."}
    )
    theme_candidates: List[CrossReportThemeCandidate] = field(
        default_factory=list,
        metadata={"doc": "Ranked deterministic theme candidates."},
    )
    rejected_theme_candidates: List[CrossReportThemeCandidate] = field(
        default_factory=list,
        metadata={"doc": "Theme candidates rejected by deterministic gates."},
    )


@dataclass(frozen=True)
class CrossReportPublishabilityResult:
    schema_version: str = field(
        metadata={"doc": "Publishability gate result contract schema version."}
    )
    selected_theme_id: str = field(
        metadata={"doc": "Selected theme evaluated by the publishability gate."}
    )
    publishable: bool = field(
        metadata={"doc": "True when the selected source set may proceed."}
    )
    override_applied: bool = field(
        metadata={"doc": "Whether an explicit operator override allowed continuation."}
    )
    diagnostic: bool = field(
        metadata={"doc": "Whether diagnostic mode allowed non-publishable inspection."}
    )
    source_report_count: int = field(
        metadata={"doc": "Selected source report count checked by the gate."}
    )
    source_publisher_count: int = field(
        metadata={"doc": "Distinct selected source publisher count."}
    )
    evidence_count: int = field(
        metadata={"doc": "Selected source evidence count checked by the gate."}
    )
    checked_policy_fields: Dict[str, Any] = field(
        metadata={"doc": "Policy thresholds and validation prerequisites checked."}
    )
    issues: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Deterministic publishability issues found by the gate.",
            "required": False,
        },
    )


@dataclass(frozen=True)
class CrossReportEvidenceInputResult:
    schema_version: str = field(
        metadata={"doc": "Evidence input assembly result contract schema version."}
    )
    selected_sources: List[CrossReportSelectedSourceReport] = field(
        metadata={"doc": "Selected source reports used for evidence assembly."}
    )
    evidence: List[CrossReportEvidenceReference] = field(
        metadata={"doc": "Bounded evidence references supplied to synthesis."}
    )
    raw_metrics: List[CrossReportRawMetricReference] = field(
        default_factory=list,
        metadata={
            "doc": "Source-bound raw metric references supplied without normalization.",
            "required": False,
        },
    )
    evidence_by_report_id: Dict[str, List[str]] = field(
        default_factory=dict,
        metadata={"doc": "Selected evidence IDs grouped by source report ID."},
    )
    dropped_evidence_counts: Dict[str, int] = field(
        default_factory=dict,
        metadata={
            "doc": "Evidence or raw-metric rows dropped by reason during assembly.",
            "required": False,
        },
    )
    prompt_input_chars: int = field(
        default=0,
        metadata={"doc": "Approximate bounded prompt-input character count."},
    )


def validate_cross_report_contract(contract: object) -> None:
    contract_type = type(contract)
    if (
        not is_dataclass(contract)
        or contract_type.__module__ != __name__
        or not contract_type.__name__.startswith("CrossReport")
    ):
        _raise_invalid(
            contract_type.__name__,
            "<root>",
            "expected cross-report dataclass contract",
        )
        return
    _validate_contract_value(contract, path=contract_type.__name__)


def _raise_invalid(path: str, field_name: str, reason: str) -> None:
    raise AppError(
        code="cross_report_contract_invalid",
        message=f"Invalid cross-report contract field {path}: {reason}",
        retryable=False,
        severity="error",
        context={"path": path, "field": field_name, "reason": reason},
    )


def _field_is_required(field_def: Any) -> bool:
    if field_def.metadata.get("required") is False:
        return False
    return field_def.default is MISSING and field_def.default_factory is MISSING


def _field_is_list_typed(annotation: Any) -> bool:
    return annotation in {list, List} or get_origin(annotation) in {list, List}


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
    type_hints = get_type_hints(type(instance))
    for field_def in fields(cast(Any, instance)):
        field_value = getattr(instance, field_def.name)
        field_path = f"{path}.{field_def.name}"
        field_annotation = type_hints.get(field_def.name, field_def.type)
        if field_def.name == "schema_version":
            if field_value != CROSS_REPORT_ANALYSIS_SCHEMA_VERSION:
                _raise_invalid(field_path, field_def.name, "unsupported schema version")
        if _field_is_list_typed(field_annotation) and field_value is None:
            _raise_invalid(field_path, field_def.name, "list field cannot be null")
        if _field_is_required(field_def) and _empty_required_value(field_value):
            _raise_invalid(field_path, field_def.name, "required value is empty")
        _validate_contract_value(field_value, path=field_path)
