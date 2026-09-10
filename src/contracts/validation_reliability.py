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
class ValidationReliabilityFirstAttemptStage(SemanticIdContract):
    """First-attempt and eventual result for one report lifecycle transition."""

    schema_version: str = field(metadata={"doc": "First-attempt stage schema version."})
    from_state: str
    to_state: str
    first_pass: bool
    eventual_success: bool
    first_failure_code: str
    first_failure_stage: str
    recovery_type: str
    attempts_required: int
    operator_intervention: bool
    terminal_failure: bool
    verified_replay: bool
    terminal_disposition: str
    usage_attribution: str
    provider_call_count_before_recovery: int | None
    input_tokens_before_recovery: int | None
    output_tokens_before_recovery: int | None
    total_tokens_before_recovery: int | None
    estimated_cost_usd_before_recovery: float | None


@dataclass(frozen=True)
class ValidationReliabilityFirstAttemptEntity(SemanticIdContract):
    """Retained first-attempt evidence and final disposition for one report."""

    schema_version: str = field(
        metadata={"doc": "First-attempt entity schema version."}
    )
    entity_key: str
    report_id: str
    first_attempt_number: int
    first_attempt_admitted: bool
    eventual_admitted: bool
    first_pass: bool
    eventual_success: bool
    bounded_recovery: bool
    operator_intervention: bool
    terminal_failure: bool
    verified_replay: bool
    attempts_required: int
    terminal_disposition: str
    stages: tuple[ValidationReliabilityFirstAttemptStage, ...]


@dataclass(frozen=True)
class ValidationReliabilityFirstAttemptTransition(SemanticIdContract):
    """Separate first-attempt and eventual conversion for one transition."""

    schema_version: str = field(
        metadata={"doc": "First-attempt transition schema version."}
    )
    from_state: str
    to_state: str
    first_attempt_eligible_entity_count: int
    first_pass_entity_count: int
    first_pass_conversion_rate: float
    eventual_eligible_entity_count: int
    eventual_success_entity_count: int
    eventual_conversion_rate: float
    bounded_recovery_entity_count: int
    bounded_recovery_rate: float
    operator_intervention_entity_count: int
    operator_intervention_rate: float
    terminal_failure_entity_count: int
    terminal_failure_rate: float
    verified_replay_entity_count: int
    verified_replay_rate: float


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
    first_attempt_entities: tuple[ValidationReliabilityFirstAttemptEntity, ...]
    first_attempt_transitions: tuple[ValidationReliabilityFirstAttemptTransition, ...]
    first_attempt_failure_pareto: tuple[ValidationFailureParetoEntry, ...]
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
