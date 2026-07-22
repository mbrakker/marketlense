from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.config import AppSettings
from src.contracts.ingest import IngestSettings
from src.contracts.report_store import ReportMetadataGetResponse
from src.contracts.semantic_ids import ReportId, SemanticIdContract


@dataclass(frozen=True)
class ReportContextSection:
    section_label: str = field(
        metadata={"doc": "Human-readable section label from report evidence."}
    )
    source_pack: str = field(
        metadata={"doc": "Evidence-pack name that produced this section summary."}
    )
    summary: str = field(
        metadata={"doc": "Compact summary of the section's relevance."}
    )
    key_points: List[str] = field(
        default_factory=list,
        metadata={"doc": "High-signal bullet points supporting the section summary."},
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Report-context section schema version."}
    )


@dataclass(frozen=True)
class ReportCategoryContext(SemanticIdContract):
    report_id: ReportId = field(metadata={"doc": "Stable report identifier."})
    title: str = field(metadata={"doc": "Human-readable report title."})
    publisher: str = field(metadata={"doc": "Publisher or organization if known."})
    region: str = field(metadata={"doc": "Primary region or market focus if known."})
    time_period: str = field(
        metadata={"doc": "Primary period covered by the report if known."}
    )
    overview: str = field(
        metadata={"doc": "Compact holistic summary of the report's central subject."}
    )
    methods: List[str] = field(
        default_factory=list,
        metadata={"doc": "Methodology or study-design points."},
    )
    key_findings: List[str] = field(
        default_factory=list,
        metadata={"doc": "Most central findings extracted from evidence packs."},
    )
    limitations: List[str] = field(
        default_factory=list,
        metadata={"doc": "Important caveats or limits of the report."},
    )
    sections: List[ReportContextSection] = field(
        default_factory=list,
        metadata={"doc": "Section-level evidence summaries used for category fitting."},
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Report-context schema version."}
    )


@dataclass(frozen=True)
class ReportContextBuildRequest:
    report: ReportMetadataGetResponse = field(
        metadata={"doc": "Stored report metadata including evidence-pack paths."}
    )
    max_sections: int = field(
        default=6,
        metadata={"doc": "Maximum number of compact context sections to retain."},
    )
    max_findings: int = field(
        default=6,
        metadata={"doc": "Maximum number of key findings to retain."},
    )
    max_methods: int = field(
        default=4,
        metadata={"doc": "Maximum number of methods points to retain."},
    )
    max_limitations: int = field(
        default=4,
        metadata={"doc": "Maximum number of limitations to retain."},
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Report-context build request schema version."}
    )


@dataclass(frozen=True)
class CategoryFitCandidate:
    category_id: str = field(metadata={"doc": "Candidate category identifier."})
    label: str = field(metadata={"doc": "Human-readable category label."})
    fit_score: float = field(
        metadata={"doc": "Model-estimated fit score between 0 and 1."}
    )
    decision: str = field(
        metadata={"doc": "Decision bucket: primary, secondary, or reject."}
    )
    why_fit: str = field(
        metadata={"doc": "Short evidence-based rationale for the category fit."}
    )
    why_not_fit: str = field(
        default="",
        metadata={"doc": "Short reason the category should not be treated as central."},
    )
    evidence_sections: List[str] = field(
        default_factory=list,
        metadata={"doc": "Section labels supporting the fit decision."},
    )
    semantic_rule_status: str = field(
        default="not_evaluated",
        metadata={
            "doc": "Canonical Topic rule audit status: supported, rejected, ambiguous, or not_evaluated."
        },
    )
    supported_topic_rules: List[str] = field(
        default_factory=list,
        metadata={"doc": "Topic include rules that matched the report context."},
    )
    supported_topic_rule_ids: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Stable identifiers for include rules supported by explicit context evidence."
        },
    )
    rejected_topic_rules: List[str] = field(
        default_factory=list,
        metadata={"doc": "Topic exclusion rules that matched the report context."},
    )
    rejected_topic_rule_ids: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Stable identifiers for exclusion rules supported by explicit context evidence."
        },
    )
    rule_evidence_sections: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Referenced report-context sections used by deterministic rule evaluation."
        },
    )
    remediation_signal: str = field(
        default="",
        metadata={
            "doc": "Typed remediation signal when canonical Topic rules conflict or are stale/ambiguous."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Category-fit candidate schema version."}
    )


@dataclass(frozen=True)
class ContextCategoryFitRequest:
    context: ReportCategoryContext = field(
        metadata={"doc": "Deterministic report context used for model evaluation."}
    )
    settings: AppSettings | IngestSettings = field(
        metadata={"doc": "Resolved application settings for model configuration."}
    )
    category_mapping_path: str = field(
        metadata={"doc": "Filesystem path to category mappings YAML."}
    )
    prompt_namespace: str = field(
        default="report_vs/context_category_fit",
        metadata={"doc": "Prompt namespace used for context-first category fitting."},
    )
    publisher_name: str = field(
        default="",
        metadata={"doc": "Publisher context recorded with downstream LLM usage."},
    )
    report_name: str = field(
        default="",
        metadata={"doc": "Human-readable report context recorded with LLM usage."},
    )
    source_url: str = field(
        default="",
        metadata={
            "doc": "Source/report URL context recorded with downstream LLM usage."
        },
    )
    repair_error: str = field(
        default="",
        metadata={
            "doc": "Typed output-contract error supplied only to the one targeted repair request."
        },
    )
    repair_response: str = field(
        default="",
        repr=False,
        metadata={
            "doc": "Original failed provider output held only in memory for the one targeted repair."
        },
    )
    repair_attempt: int = field(
        default=0,
        metadata={
            "doc": "Bounded category-fit repair attempt; zero is the primary call."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Context-category fit request schema version."}
    )


@dataclass(frozen=True)
class ContextCategoryFitResponse(SemanticIdContract):
    report_id: ReportId = field(metadata={"doc": "Stable report identifier."})
    categories: List[str] = field(
        metadata={"doc": "Selected portal category identifiers in rank order."}
    )
    category_labels: List[str] = field(
        metadata={"doc": "Human-readable labels aligned with selected categories."}
    )
    fits: List[CategoryFitCandidate] = field(
        default_factory=list,
        metadata={"doc": "Model-ranked fit candidates for audit and comparison."},
    )
    request_id: Optional[str] = field(
        default=None, metadata={"doc": "Provider request ID if available."}
    )
    model: str = field(default="", metadata={"doc": "Resolved model identifier used."})
    raw_response: str = field(
        default="", metadata={"doc": "Raw model JSON text for audit/debug flows."}
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Context-category fit response schema version."}
    )
