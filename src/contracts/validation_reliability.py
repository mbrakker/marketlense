"""Typed contracts for deterministic validation-run reliability telemetry."""

from __future__ import annotations

from dataclasses import dataclass, field

from src.contracts.semantic_ids import SemanticIdContract, ValidationRunId


@dataclass(frozen=True)
class ValidationReliabilityTransition(SemanticIdContract):
    """One deterministic conversion between two validation lifecycle states."""

    schema_version: str = field(
        metadata={"doc": "Reliability-transition schema version."}
    )
    from_state: str
    to_state: str
    eligible_entity_count: int
    completed_entity_count: int
    conversion_rate: float


@dataclass(frozen=True)
class ValidationReliabilityFailureCode(SemanticIdContract):
    """One failure-code contribution to the deterministic Pareto ordering."""

    schema_version: str = field(
        metadata={"doc": "Reliability failure-code schema version."}
    )
    failure_code: str
    failure_count: int


@dataclass(frozen=True)
class ValidationReliabilityFailureTransition(SemanticIdContract):
    """Observed failures while moving from one lifecycle state to the next."""

    schema_version: str = field(
        metadata={"doc": "Reliability failure-transition schema version."}
    )
    from_state: str
    to_state: str
    failure_count: int
    failure_codes: tuple[ValidationReliabilityFailureCode, ...]
    median_duration_ms: int
    p95_duration_ms: int
    provider_call_count_before_failure: int
    input_tokens_before_failure: int
    output_tokens_before_failure: int
    total_tokens_before_failure: int
    estimated_cost_usd_before_failure: float
    successful_recovery_count: int
    successful_recovery_rate: float
    operator_intervention_count: int
    operator_intervention_rate: float
    full_rerun_count: int
    full_rerun_rate: float


@dataclass(frozen=True)
class ValidationFailureParetoEntry(SemanticIdContract):
    """Deterministically ranked failure-code aggregate across a validation run."""

    schema_version: str = field(
        metadata={"doc": "Failure Pareto entry schema version."}
    )
    rank: int
    failure_code: str
    failure_count: int
    cumulative_failure_count: int
    cumulative_failure_rate: float
    transition_pairs: tuple[str, ...]


@dataclass(frozen=True)
class ValidationReliabilityArtifact(SemanticIdContract):
    """The retained validation-run funnel, failure metrics, and Pareto report."""

    schema_version: str = field(
        metadata={"doc": "Reliability artifact schema version."}
    )
    validation_run_id: ValidationRunId
    cohort_id: str
    workflow_run_id: str
    configuration_hash: str
    policy_hash: str
    producer_build_identity: str
    transitions: tuple[ValidationReliabilityTransition, ...]
    failed_transitions: tuple[ValidationReliabilityFailureTransition, ...]
    failure_pareto: tuple[ValidationFailureParetoEntry, ...]
    artifact_hash: str = field(
        default="", metadata={"doc": "Hash of this artifact excluding itself."}
    )


@dataclass(frozen=True)
class ValidationReliabilityBuildRequest(SemanticIdContract):
    """Inputs for materializing canonical validation reliability telemetry."""

    schema_version: str = field(
        metadata={"doc": "Reliability artifact build request schema version."}
    )
    reports_db_path: str
    usage_db_path: str
    validation_run_id: ValidationRunId


@dataclass(frozen=True)
class ValidationReliabilityWriteRequest(SemanticIdContract):
    """Inputs for atomically retaining one reliability artifact."""

    schema_version: str = field(
        metadata={"doc": "Reliability artifact write request schema version."}
    )
    artifact_path: str
    artifact: ValidationReliabilityArtifact


@dataclass(frozen=True)
class ValidationReliabilityWriteResponse(SemanticIdContract):
    """Stable reference to one retained reliability artifact."""

    schema_version: str = field(
        metadata={"doc": "Reliability artifact write response schema version."}
    )
    artifact_path: str
    artifact_hash: str
