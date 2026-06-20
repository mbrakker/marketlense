from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List

from src.contracts._cross_report_analysis import CrossReportValidationStatus
from .selection import (
    CrossReportEvidenceReference,
    CrossReportRawMetricReference,
    CrossReportSelectedSourceReport,
    CrossReportSelectedTheme,
    CrossReportSignalScore,
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
    decision_focus: str = field(
        metadata={"doc": "Grounded decision statement for briefing-card presentation."}
    )
    executive_takeaways: List[str] = field(
        metadata={"doc": "Exactly two grounded executive takeaways."}
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
