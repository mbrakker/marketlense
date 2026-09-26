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
class ValidationReliabilityRepairAttempt(SemanticIdContract):
    """Content-free outcome and attribution for one retained repair candidate."""

    schema_version: str = field(
        metadata={"doc": "Repair-attempt telemetry schema version."}
    )
    report_id: str
    attempt_index: int
    failure_rule_ids: tuple[str, ...]
    failure_fingerprints: tuple[str, ...]
    resolved_failure_fingerprints: tuple[str, ...]
    persisting_failure_fingerprints: tuple[str, ...]
    introduced_failure_fingerprints: tuple[str, ...]
    introduced_hard_failure_count: int | None
    strategy_fingerprint: str
    candidate_fingerprint: str
    repair_action: str
    repair_strategy: str
    evidence_fingerprints: tuple[str, ...]
    validation_status: str
    promotion_outcome: str
    successful: bool
    abstention_or_removal: bool
    out_of_scope_mutation: bool
    repair_mode: str
    usage_attribution: str
    model_call_count: int | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    latency_ms: int | None
    prompt_identities: tuple[str, ...]
    configuration_hash: str
    policy_hash: str
    producer_build_identity: str


@dataclass(frozen=True)
class ValidationReliabilityRepairModeMetric(SemanticIdContract):
    """Comparable success and resource totals for one repair execution mode."""

    schema_version: str = field(
        metadata={"doc": "Repair-mode scorecard schema version."}
    )
    repair_mode: str
    attempt_count: int
    successful_attempt_count: int
    success_rate: float | None
    metric_attribution: str
    model_call_count: int | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    latency_ms: int | None


@dataclass(frozen=True)
class ValidationReliabilityRepairFailureClass(SemanticIdContract):
    """One bounded validator-class contribution to the repair denominator."""

    schema_version: str = field(
        metadata={"doc": "Repair failure-class metric schema version."}
    )
    failure_class: str
    attempt_count: int


@dataclass(frozen=True)
class ValidationReliabilityValidationIdentity(SemanticIdContract):
    """Current validator and run identities for one benchmark validation side."""

    schema_version: str = field(metadata={"doc": "Validation identity schema version."})
    validator_identity: str
    configuration_hash: str
    policy_hash: str
    producer_build_identity: str


@dataclass(frozen=True)
class ValidationReliabilityBenchmarkCaseAttribution(SemanticIdContract):
    """Content-free current-validator attribution for one frozen benchmark case."""

    schema_version: str = field(
        metadata={"doc": "Benchmark case attribution schema version."}
    )
    case_id: str
    report_id: str
    reproducibility_status: str
    historical_failure_fingerprints: tuple[str, ...]
    current_baseline_failure_fingerprints: tuple[str, ...]
    current_baseline_issue_fingerprints: tuple[str, ...]
    baseline_validation_identity: ValidationReliabilityValidationIdentity
    candidate_validation_identity: ValidationReliabilityValidationIdentity | None
    candidate_validation_attempt_count: int
    candidate_audit_count: int


@dataclass(frozen=True)
class ValidationReliabilityRepairScorecard(SemanticIdContract):
    """Cohort-compatible effectiveness measurement for retained repair attempts."""

    schema_version: str = field(
        metadata={"doc": "Repair-effectiveness scorecard schema version."}
    )
    measurement_status: str
    cohort_compatible: bool
    repair_chain_count: int | None
    repair_attempt_count: int | None
    success_at_1_count: int | None
    success_at_1_rate: float | None
    success_at_3_count: int | None
    success_at_3_rate: float | None
    rolled_back_attempt_count: int | None
    abstention_or_removal_attempt_count: int | None
    out_of_scope_mutation_attempt_count: int | None
    repeated_failed_strategy_evidence_attempt_count: int | None
    repeated_failed_candidate_attempt_count: int | None
    incompatible_audit_count: int
    hard_failure_introduction_count: int | None
    benchmark_case_count: int | None
    benchmark_denominator_complete: bool
    benchmark_manifest_sha256: str
    baseline_identity_sha256: str
    current_identity_sha256: str
    hard_failure_introduction_attempt_count: int | None
    hard_failure_introduction_rate: float | None
    unsupported_evidence_introduction_attempt_count: int | None
    deterministic_repair_share: float | None
    model_repair_share: float | None
    usage_attribution: str
    model_call_count: int | None
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    estimated_cost_usd: float | None
    latency_ms: int | None
    current_residual_failure_odds: float | None
    current_residual_failure_odds_state: str
    baseline_success_at_3_count: int | None
    baseline_success_at_3_rate: float | None
    baseline_usage_attribution: str
    baseline_model_call_count: int | None
    baseline_input_tokens: int | None
    baseline_output_tokens: int | None
    baseline_total_tokens: int | None
    baseline_estimated_cost_usd: float | None
    baseline_latency_ms: int | None
    baseline_residual_failure_odds: float | None
    baseline_residual_failure_odds_state: str
    residual_odds_reduction_factor: float | None
    residual_odds_reduction_state: str
    benchmark_comparison_status: str
    failure_class_distribution: tuple[ValidationReliabilityRepairFailureClass, ...]
    baseline_failure_class_distribution: tuple[
        ValidationReliabilityRepairFailureClass, ...
    ]
    attempts: tuple[ValidationReliabilityRepairAttempt, ...]
    mode_metrics: tuple[ValidationReliabilityRepairModeMetric, ...]
    reproducible_case_count: int | None = None
    no_longer_reproducible_case_count: int | None = None
    success_denominator: int | None = None
    benchmark_case_attributions: tuple[
        ValidationReliabilityBenchmarkCaseAttribution, ...
    ] = ()


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
    repair_scorecard: ValidationReliabilityRepairScorecard
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
    state_db_path: str = ""
    repair_evidence_root: str = ""
    repair_benchmark_manifest_path: str = ""
    current_schema_identity_sha256: str = ""
    repair_benchmark_case_attributions: tuple[
        ValidationReliabilityBenchmarkCaseAttribution, ...
    ] = ()


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
