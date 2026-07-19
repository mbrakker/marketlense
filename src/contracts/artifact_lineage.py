"""Dataclass contracts for durable, content-addressed artifact lineage."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

ARTIFACT_LINEAGE_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ArtifactLineageRegistrationRequest:
    schema_version: str = field(
        metadata={"doc": "Artifact-lineage request schema version."}
    )
    db_path: str = field(metadata={"doc": "Reports SQLite database path."})
    artifact_kind: str = field(metadata={"doc": "Semantic artifact family identifier."})
    report_id: str = field(metadata={"doc": "Owning report identifier, if applicable."})
    source_id: str = field(
        metadata={"doc": "Owning source content identifier, if known."}
    )
    storage_ref: str = field(metadata={"doc": "Canonical local storage reference."})
    producer: str = field(metadata={"doc": "Workflow stage or producer identity."})
    schema_version_used: str = field(
        metadata={"doc": "Schema version used by the artifact."}
    )
    processing_version: str = field(
        metadata={"doc": "Processor/version compatibility key."}
    )
    dependency_artifact_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Direct canonical dependency artifact identities."},
    )
    content_hash: str = field(
        default="",
        metadata={
            "doc": "Optional supplied SHA-256; service verifies it against storage."
        },
    )
    prompt_hash: str = field(
        default="",
        metadata={"doc": "Rendered prompt hash when the producer is model-backed."},
    )
    model_provider: str = field(
        default="", metadata={"doc": "Model provider when applicable."}
    )
    model_name: str = field(default="", metadata={"doc": "Model name when applicable."})
    model_parameters_hash: str = field(
        default="",
        metadata={"doc": "Deterministic model-parameter hash when applicable."},
    )
    validation_status: str = field(
        default="not_applicable", metadata={"doc": "Artifact validation status."}
    )
    metadata: dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Sanitized semantic compatibility metadata."},
    )
    compatibility: dict[str, Any] = field(
        default_factory=dict,
        metadata={
            "doc": "Versioned provenance used by the minimum-regeneration planner."
        },
    )
    lineage_status: str = field(
        default="legacy_unverified",
        metadata={
            "doc": "complete for planner-safe provenance; legacy_unverified otherwise."
        },
    )


@dataclass(frozen=True)
class ArtifactLineageRecord:
    schema_version: str = field(
        metadata={"doc": "Artifact-lineage record schema version."}
    )
    artifact_id: str = field(
        metadata={"doc": "Immutable deterministic canonical artifact identity."}
    )
    artifact_kind: str = field(metadata={"doc": "Semantic artifact family identifier."})
    report_id: str = field(metadata={"doc": "Owning report identifier, if applicable."})
    source_id: str = field(
        metadata={"doc": "Owning source content identifier, if known."}
    )
    content_hash: str = field(metadata={"doc": "Verified SHA-256 content digest."})
    storage_ref: str = field(metadata={"doc": "Canonical resolved storage reference."})
    producer: str = field(metadata={"doc": "Workflow stage or producer identity."})
    schema_version_used: str = field(
        metadata={"doc": "Schema version used by the artifact."}
    )
    processing_version: str = field(
        metadata={"doc": "Processor/version compatibility key."}
    )
    prompt_hash: str = field(metadata={"doc": "Rendered prompt hash when applicable."})
    model_provider: str = field(metadata={"doc": "Model provider when applicable."})
    model_name: str = field(metadata={"doc": "Model name when applicable."})
    model_parameters_hash: str = field(
        metadata={"doc": "Model-parameter hash when applicable."}
    )
    validation_status: str = field(metadata={"doc": "Artifact validation status."})
    state: str = field(
        metadata={"doc": "Current active, invalidated, or superseded state."}
    )
    invalidation_reason: str = field(
        default="", metadata={"doc": "Recorded invalidation reason."}
    )
    superseded_by: str = field(
        default="",
        metadata={"doc": "Replacement canonical artifact identity, when known."},
    )
    metadata: dict[str, Any] = field(
        default_factory=dict, metadata={"doc": "Sanitized compatibility metadata."}
    )
    compatibility: dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Versioned provenance used by deterministic planning."},
    )
    lineage_status: str = field(
        default="legacy_unverified",
        metadata={"doc": "Planner provenance completeness state."},
    )


@dataclass(frozen=True)
class ArtifactLineageRegistrationResponse:
    schema_version: str = field(
        metadata={"doc": "Artifact-lineage response schema version."}
    )
    record: ArtifactLineageRecord = field(
        metadata={"doc": "Persisted canonical record."}
    )
    created: bool = field(
        metadata={"doc": "True only when the immutable record was newly inserted."}
    )


@dataclass(frozen=True)
class ArtifactReuseCheckRequest:
    schema_version: str = field(metadata={"doc": "Reuse-check request schema version."})
    db_path: str = field(metadata={"doc": "Reports SQLite database path."})
    artifact_id: str = field(metadata={"doc": "Canonical artifact identity to verify."})
    expected_schema_version: str = field(
        metadata={"doc": "Required artifact schema version."}
    )
    expected_processing_version: str = field(
        metadata={"doc": "Required processor compatibility key."}
    )
    expected_prompt_hash: str = field(
        default="", metadata={"doc": "Required prompt hash when applicable."}
    )
    expected_model_name: str = field(
        default="", metadata={"doc": "Required model name when applicable."}
    )
    expected_execution_identity: str = field(
        default="",
        metadata={
            "doc": "Required model execution identity for model-derived artifact reuse."
        },
    )
    expected_validation_status: str = field(
        default="", metadata={"doc": "Required validation status when applicable."}
    )


@dataclass(frozen=True)
class ArtifactReuseCheckResponse:
    schema_version: str = field(
        metadata={"doc": "Reuse-check response schema version."}
    )
    reusable: bool = field(
        metadata={
            "doc": "True when record, compatibility, state, and content validate."
        }
    )
    reason: str = field(metadata={"doc": "Stable decision reason."})
    record: ArtifactLineageRecord | None = field(
        default=None, metadata={"doc": "Found record when available."}
    )


@dataclass(frozen=True)
class ArtifactLineageTraceRequest:
    schema_version: str = field(metadata={"doc": "Trace request schema version."})
    db_path: str = field(metadata={"doc": "Reports SQLite database path."})
    artifact_id: str = field(
        metadata={
            "doc": "Artifact identity to trace to direct and transitive dependencies."
        }
    )


@dataclass(frozen=True)
class ArtifactLineageTraceResponse:
    schema_version: str = field(metadata={"doc": "Trace response schema version."})
    records: list[ArtifactLineageRecord] = field(
        metadata={"doc": "Root-first lineage records."}
    )
    edges: list[tuple[str, str]] = field(
        metadata={"doc": "Direct (artifact, dependency) lineage edges."}
    )


@dataclass(frozen=True)
class ArtifactLineageStorageLookupRequest:
    schema_version: str = field(
        metadata={"doc": "Storage-lookup request schema version."}
    )
    db_path: str = field(metadata={"doc": "Reports SQLite database path."})
    report_id: str = field(metadata={"doc": "Owning report identifier."})
    artifact_kind: str = field(metadata={"doc": "Expected semantic artifact family."})
    storage_ref: str = field(metadata={"doc": "Canonical local storage reference."})


@dataclass(frozen=True)
class ArtifactLineageStorageLookupResponse:
    schema_version: str = field(
        metadata={"doc": "Storage-lookup response schema version."}
    )
    record: ArtifactLineageRecord | None = field(
        default=None, metadata={"doc": "Active canonical record when it exists."}
    )


@dataclass(frozen=True)
class ArtifactInvalidationRequest:
    schema_version: str = field(
        metadata={"doc": "Invalidation request schema version."}
    )
    db_path: str = field(metadata={"doc": "Reports SQLite database path."})
    change_kind: str = field(
        metadata={"doc": "One of source, prompt, template, crop, or validator."}
    )
    changed_value: str = field(
        metadata={"doc": "Changed source ID or old compatibility fingerprint."}
    )
    report_id: str = field(default="", metadata={"doc": "Optional report scope."})
    dry_run: bool = field(
        default=False, metadata={"doc": "When true, calculate without modifying state."}
    )


@dataclass(frozen=True)
class ArtifactInvalidationResponse:
    schema_version: str = field(
        metadata={"doc": "Invalidation response schema version."}
    )
    root_artifact_ids: list[str] = field(
        metadata={"doc": "Directly matched artifact identities."}
    )
    invalidated_artifact_ids: list[str] = field(
        metadata={"doc": "Root and dependent artifact identities affected."}
    )
    dry_run: bool = field(metadata={"doc": "Whether state was left unchanged."})


@dataclass(frozen=True)
class ArtifactLineageBackfillRequest:
    schema_version: str = field(metadata={"doc": "Backfill request schema version."})
    db_path: str = field(metadata={"doc": "Reports SQLite database path."})
    checkpoint_root: str = field(
        metadata={"doc": "Report-generation checkpoint root to scan."}
    )
    limit: int = field(
        default=100, metadata={"doc": "Maximum checkpoint files scanned."}
    )
    dry_run: bool = field(
        default=True,
        metadata={"doc": "When true, report potential registrations only."},
    )


@dataclass(frozen=True)
class ArtifactLineageBackfillResponse:
    schema_version: str = field(metadata={"doc": "Backfill response schema version."})
    scanned_checkpoints: int = field(
        metadata={"doc": "Number of bounded checkpoint files inspected."}
    )
    eligible_artifacts: int = field(
        metadata={"doc": "Artifact refs with readable local content."}
    )
    created_artifacts: int = field(metadata={"doc": "New immutable records created."})
    skipped_artifacts: int = field(
        metadata={"doc": "Missing or incompatible historical refs skipped."}
    )
    dry_run: bool = field(metadata={"doc": "Whether state was left unchanged."})
    incomplete_artifacts: int = field(
        default=0,
        metadata={
            "doc": "Legacy records retained but unavailable for planner-safe reuse."
        },
    )


@dataclass(frozen=True)
class ArtifactLineageAuditRequest:
    """Read-only completeness audit for durable retained-artifact lineage."""

    schema_version: str = field(
        metadata={"doc": "Artifact-lineage audit schema version."}
    )
    db_path: str = field(metadata={"doc": "Reports SQLite database path."})
    report_id: str = field(
        default="", metadata={"doc": "Optional report scope; empty audits all reports."}
    )


@dataclass(frozen=True)
class ArtifactLineageAuditItem:
    """Bounded per-artifact audit evidence without source bytes or paths."""

    schema_version: str = field(
        metadata={"doc": "Artifact-lineage audit item schema version."}
    )
    artifact_id: str = field(metadata={"doc": "Canonical immutable artifact ID."})
    report_id: str = field(metadata={"doc": "Owning report ID, if retained."})
    artifact_family: str = field(metadata={"doc": "Artifact family identifier."})
    producer: str = field(metadata={"doc": "Recorded producer identity."})
    processing_version: str = field(
        metadata={"doc": "Recorded processing compatibility version."}
    )
    state: str = field(
        metadata={"doc": "Current active, superseded, or invalidated state."}
    )
    lineage_status: str = field(
        metadata={"doc": "Retained lineage completeness state."}
    )
    missing_field_codes: tuple[str, ...] = field(
        metadata={"doc": "Deterministic bounded codes for missing or invalid proof."}
    )
    hash_state: str = field(
        metadata={"doc": "verified, missing_storage, or hash_mismatch."}
    )
    created_at_utc: str = field(
        metadata={"doc": "Retained creation time, if available."}
    )


@dataclass(frozen=True)
class ArtifactLineageAuditResponse:
    schema_version: str = field(
        metadata={"doc": "Artifact-lineage audit response schema version."}
    )
    items: list[ArtifactLineageAuditItem] = field(
        metadata={"doc": "Deterministically ordered per-artifact audit rows."}
    )
    status_counts: dict[str, int] = field(
        metadata={"doc": "Counts by lineage state/status classification."}
    )
