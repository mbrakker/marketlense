"""Typed contracts for deterministic lineage-driven execution planning.

The planner consumes an already-observed retained graph.  It never reads files,
constructs clients, or performs workflow work; those responsibilities stay at
the report-store and orchestrator boundaries.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class ExecutionCompatibilityVersions:
    """Current compatibility keys compared against retained provenance."""

    schema_version: str = field(
        default=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        kw_only=True,
        metadata={"doc": "Execution-compatibility contract schema version."},
    )
    schema_versions: dict[str, str] = field(default_factory=dict)
    processing_versions: dict[str, str] = field(default_factory=dict)
    prompt_versions: dict[str, str] = field(default_factory=dict)
    model_policy_versions: dict[str, str] = field(default_factory=dict)
    validator_versions: dict[str, str] = field(default_factory=dict)
    crop_profiles: dict[str, str] = field(default_factory=dict)
    template_render_versions: dict[str, str] = field(default_factory=dict)
    parser_version: str = ""
    ocr_policy_version: str = ""


@dataclass(frozen=True)
class RetainedArtifact:
    """A lineage node plus the caller's current storage observation."""

    schema_version: str = field(
        default=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        kw_only=True,
        metadata={"doc": "Retained-artifact contract schema version."},
    )
    artifact_id: str
    artifact_kind: str
    report_id: str
    source_id: str
    content_hash: str
    storage_ref: str
    state: str
    schema_version_used: str
    processing_version: str
    validation_status: str
    dependency_artifact_ids: list[str] = field(default_factory=list)
    compatibility: dict[str, object] = field(default_factory=dict)
    lineage_status: str = "legacy_unverified"
    storage_available: bool = False
    observed_content_hash: str = ""


@dataclass(frozen=True)
class RetainedArtifactGraph:
    """A complete, deterministic report-scoped artifact graph."""

    schema_version: str = field(
        default=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        kw_only=True,
        metadata={"doc": "Retained-artifact graph contract schema version."},
    )
    artifacts: list[RetainedArtifact] = field(default_factory=list)
    edges: list[tuple[str, str]] = field(default_factory=list)


@dataclass(frozen=True)
class MinimalExecutionPlanInput:
    """Pure input for calculating the least safe execution plan."""

    schema_version: str = field(
        metadata={"doc": "Minimal execution-plan input schema version."}
    )
    execution_intent: str
    report_id: str
    source_id: str
    current_source_content_hashes: dict[str, str]
    retained_graph: RetainedArtifactGraph
    requested_output_families: list[str]
    current_compatibility: ExecutionCompatibilityVersions
    source_metadata_hash: str = ""
    current_publication_state: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ArtifactInvalidation:
    schema_version: str = field(
        default=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        kw_only=True,
        metadata={"doc": "Artifact-invalidation contract schema version."},
    )
    artifact_id: str
    artifact_kind: str
    artifact_family: str
    reason: str


@dataclass(frozen=True)
class MissingLineageBlocker:
    schema_version: str = field(
        default=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        kw_only=True,
        metadata={"doc": "Missing-lineage blocker contract schema version."},
    )
    artifact_id: str
    artifact_kind: str
    reason: str


@dataclass(frozen=True)
class EstimatedWorkCategory:
    schema_version: str = field(
        default=MINIMAL_EXECUTION_PLAN_SCHEMA_VERSION,
        kw_only=True,
        metadata={"doc": "Estimated-work category contract schema version."},
    )
    category: str
    estimated_calls: int
    estimated_cost_usd: float | None = None


@dataclass(frozen=True)
class MinimalExecutionPlan:
    """Auditable plan that an orchestrator may consume without re-planning."""

    schema_version: str = field(
        metadata={"doc": "Minimal execution-plan contract schema version."}
    )
    execution_intent: str
    report_id: str
    reusable_artifacts: list[str]
    invalid_artifacts: list[ArtifactInvalidation]
    required_stages: list[str]
    skipped_stages: list[str]
    required_external_calls: list[str]
    expected_side_effects: list[str]
    estimated_cost_call_categories: list[EstimatedWorkCategory]
    missing_lineage_blockers: list[MissingLineageBlocker]
    publication_prerequisites: list[str]
    plan_hash: str
    required_prompt_families: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Exact independently materialized prompt families to regenerate."
        },
    )
    reused_prompt_families: list[str] = field(
        default_factory=list,
        metadata={"doc": "Validated prompt families reused without provider calls."},
    )


@dataclass(frozen=True)
class MinimalExecutionPlanBuildRequest:
    """Service request that observes persisted lineage before pure planning."""

    schema_version: str = field(
        metadata={"doc": "Execution-plan build request schema version."}
    )
    db_path: str
    execution_input: MinimalExecutionPlanInput
    source_path: str = ""


@dataclass(frozen=True)
class MinimalExecutionPlanBuildResponse:
    schema_version: str = field(
        metadata={"doc": "Execution-plan build response schema version."}
    )
    plan: MinimalExecutionPlan


@dataclass(frozen=True)
class ExecutionPlanRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Execution-plan audit-record request schema version."}
    )
    db_path: str
    plan: MinimalExecutionPlan
    execution_mode: str


@dataclass(frozen=True)
class ExecutionPlanResultRequest:
    schema_version: str = field(
        metadata={"doc": "Execution-plan result-record request schema version."}
    )
    db_path: str
    plan_hash: str
    report_id: str
    execution_intent: str
    actual_stages: list[str]
    actual_external_calls: list[str]
    execution_status: str
    actual_side_effects: list[str] = field(default_factory=list)
    duration_ms: int = 0
    actual_cost_usd: float | None = None
    estimated_avoided_cost_usd: float | None = None
    reusable_artifact_ids: list[str] = field(default_factory=list)
    actual_prompt_families: list[str] = field(
        default_factory=list,
        metadata={"doc": "Observed model-backed family calls for plan reconciliation."},
    )


@dataclass(frozen=True)
class ValidatedReportArtifactReadRequest:
    """Future-safe cross-report read request without source-PDF re-ingestion."""

    schema_version: str = field(
        metadata={"doc": "Validated report-artifact read request schema version."}
    )
    db_path: str
    report_id: str
    artifact_families: list[str]
    current_compatibility: ExecutionCompatibilityVersions
    current_source_content_hashes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ValidatedReportArtifactReadResponse:
    schema_version: str = field(
        metadata={"doc": "Validated report-artifact read response schema version."}
    )
    artifacts: list[RetainedArtifact]
    plan: MinimalExecutionPlan
