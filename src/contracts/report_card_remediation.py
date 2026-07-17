from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from src.contracts.report_artifacts import ArtifactRegistry


@dataclass(frozen=True)
class ReportCardPublicationDateRemediationRequest:
    schema_version: str = field(
        metadata={"doc": "Report-card publication-date remediation request schema."}
    )
    file_id: str = field(metadata={"doc": "Source report file identifier."})
    artifact_registry: ArtifactRegistry = field(
        metadata={"doc": "Typed checkpoint artifact registry used for repair input."}
    )
    artifacts_payload: Dict[str, Any] = field(
        metadata={"doc": "Loaded canonical artifacts.json payload."}
    )
    doc_map_payload: Dict[str, Any] = field(
        metadata={"doc": "Loaded canonical doc_map.json payload."}
    )
    validation_payload: Dict[str, Any] = field(
        metadata={"doc": "Loaded canonical validation.json payload."}
    )
    rendered_html_path: str = field(
        metadata={"doc": "Rendered HTML artifact path recorded in the registry."}
    )
    operator_date: str = field(
        default="",
        metadata={
            "doc": "Explicit operator-supplied ISO date, if source support is absent."
        },
    )
    operator_id: str = field(
        default="",
        metadata={"doc": "Operator identifier required when operator_date is used."},
    )
    operator_reason: str = field(
        default="",
        metadata={"doc": "Operator audit reason required when operator_date is used."},
    )
    resume_stage: str = field(
        default="analysis_complete",
        metadata={"doc": "Checkpoint stage to resume after remediation."},
    )


@dataclass(frozen=True)
class ReportCardPublicationDateRemediationResult:
    schema_version: str = field(
        metadata={"doc": "Report-card publication-date remediation result schema."}
    )
    file_id: str = field(metadata={"doc": "Source report file identifier."})
    publication_date: str = field(metadata={"doc": "Normalized ISO publication date."})
    date_source: str = field(
        metadata={"doc": "Stable source label for the normalized publication date."}
    )
    audit_fields: Dict[str, str] = field(
        metadata={"doc": "Audit fields persisted with the repair decision."}
    )
    resume_stage: str = field(
        metadata={"doc": "Checkpoint stage safe to resume after remediation."}
    )
    idempotency_key: str = field(
        metadata={"doc": "Deterministic key for repeated remediation attempts."}
    )


@dataclass(frozen=True)
class ReportCardCheckpointRemediationRequest:
    """Inputs for a checkpoint-backed, render-only publication-date repair."""

    schema_version: str = field(
        metadata={"doc": "Checkpoint remediation request schema version."}
    )
    checkpoint_root: str = field(
        metadata={"doc": "Root directory containing report-generation checkpoints."}
    )
    file_id: str = field(metadata={"doc": "Source report file identifier."})
    reports_db_path: str = field(
        metadata={"doc": "Canonical reports SQLite path for artifact lineage."}
    )
    source_id: str = field(
        default="", metadata={"doc": "Source content identifier used for lineage."}
    )
    operator_date: str = field(
        default="",
        metadata={"doc": "Audited operator date when source artifacts lack one."},
    )
    operator_id: str = field(
        default="", metadata={"doc": "Operator identifier required with operator_date."}
    )
    operator_reason: str = field(
        default="", metadata={"doc": "Operator reason required with operator_date."}
    )
    state_db: str = field(
        default="",
        metadata={"doc": "Optional canonical remediation-ledger state database."},
    )


@dataclass(frozen=True)
class ReportCardCheckpointRemediationResponse:
    """Persisted repair evidence that can safely resume from analysis_complete."""

    schema_version: str = field(
        metadata={"doc": "Checkpoint remediation response schema version."}
    )
    result: ReportCardPublicationDateRemediationResult = field(
        metadata={"doc": "Audited publication-date repair decision."}
    )
    checkpoint_path: str = field(metadata={"doc": "Updated analysis checkpoint path."})
    artifacts_path: str = field(
        metadata={"doc": "Updated canonical artifacts JSON path."}
    )
    artifact_lineage_id: str = field(
        metadata={"doc": "New immutable lineage identity for repaired artifacts."}
    )
