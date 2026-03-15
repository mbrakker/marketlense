from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.docpacks import DocPackPayloadMap
from src.contracts.report_models import ReportPayload


@dataclass(frozen=True)
class ValidationIssue:
    message: str = field(
        metadata={"doc": "Human-readable description of the validation issue."}
    )
    severity: str = field(
        metadata={"doc": "Severity level for the issue: error|warning|info."}
    )
    affected_section: str = field(
        metadata={
            "doc": "Section or artifact impacted by the issue (e.g., insights, quotes)."
        }
    )
    rule_id: str = field(
        default="",
        metadata={
            "doc": "Machine-readable validation rule identifier for routing and reporting."
        },
    )
    repair_target: str = field(
        default="",
        metadata={
            "doc": "Normalized regeneration target key when the issue can be auto-repaired."
        },
    )
    entity_id: str = field(
        default="",
        metadata={
            "doc": "Optional stable entity identifier within the affected section."
        },
    )
    schema_version: str = field(
        default="1.0", metadata={"doc": "Validation issue schema version."}
    )


@dataclass(frozen=True)
class ValidationReport:
    schema_version: str = field(metadata={"doc": "Validation report schema version."})
    status: str = field(
        metadata={"doc": "pass|fail aggregate status across all validation checks."}
    )
    issues: List[ValidationIssue] = field(
        default_factory=list,
        metadata={"doc": "Ordered list of issues found during validation."},
    )
    severity: str = field(
        default="pass",
        metadata={"doc": "Highest severity encountered: pass|warning|error."},
    )
    source_path: str = field(
        default="",
        metadata={
            "doc": "Filesystem path to the persisted validation report, if stored."
        },
    )

    def to_dict(self) -> dict:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "severity": self.severity,
            "source_path": self.source_path,
            "issues": [
                {
                    "schema_version": issue.schema_version,
                    "message": issue.message,
                    "severity": issue.severity,
                    "affected_section": issue.affected_section,
                    "rule_id": issue.rule_id,
                    "repair_target": issue.repair_target,
                    "entity_id": issue.entity_id,
                }
                for issue in self.issues
            ],
        }


@dataclass(frozen=True)
class ValidationRequest:
    schema_version: str = field(metadata={"doc": "Validation request schema version."})
    report_id: str = field(
        metadata={"doc": "Unique identifier for the report being validated."}
    )
    report: ReportPayload = field(
        metadata={"doc": "Normalized report payload ready for semantic validation."}
    )
    artifacts: dict = field(
        default_factory=dict,
        metadata={"doc": "Artifacts payload generated for the report."},
    )
    evidence_packs: DocPackPayloadMap = field(
        default_factory=dict,
        metadata={
            "doc": "Evidence-pack payload mapping used to ground the report content."
        },
    )
    vector_store_id: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Vector store ID for retrieval-grounded checks, if available."
        },
    )
