from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from .common import (
    CrossReportContentClass,
    CrossReportEvidenceAgreementType,
    ProjectionReadinessStatus,
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
    source_url: str = field(
        default="",
        metadata={
            "doc": "Original public source URL for the report, when available.",
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
    source_url: str = field(
        default="",
        metadata={
            "doc": "Original public source URL for the selected report, when available.",
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
