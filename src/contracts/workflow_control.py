from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from src.contracts.browser_download import BrowserDownloadSettings
from src.contracts.mailbox_acquisition import MailboxAcquisitionSettings
from src.contracts.run_budget import (  # noqa: F401
    RunBudget,
    RunBudgetDecision,
    RunBudgetUsage,
)

WorkflowGateOutcome = Literal[
    "proceed",
    "skip_duplicate",
    "defer",
    "repair",
    "hold",
    "user_action_required",
]


@dataclass(frozen=True)
class WorkflowPreflightProfile:
    schema_version: str = field(metadata={"doc": "Preflight profile schema version."})
    workflow: str = field(metadata={"doc": "Workflow this preflight profile covers."})
    planned_side_effects: list[str] = field(
        metadata={"doc": "Expensive or external side-effect families planned."}
    )
    require_llm: bool = field(
        metadata={"doc": "Whether this workflow requires model credentials/settings."}
    )
    require_drive: bool = field(
        metadata={"doc": "Whether this workflow requires Drive readiness."}
    )
    require_publish: bool = field(
        metadata={"doc": "Whether this workflow requires WordPress publish readiness."}
    )
    require_browser: bool = field(
        metadata={"doc": "Whether this workflow requires browser readiness."}
    )
    prompt_namespaces: list[str] = field(
        metadata={"doc": "Prompt namespaces required before the workflow starts."}
    )


@dataclass(frozen=True)
class WorkflowRetryPolicyConfig:
    schema_version: str = field(metadata={"doc": "Retry policy schema version."})
    policy_id: str = field(metadata={"doc": "Stable workflow.step policy ID."})
    retries: int = field(metadata={"doc": "Retry count after the initial attempt."})
    base_delay_seconds: float = field(metadata={"doc": "Delay before first retry."})
    backoff_step_seconds: float = field(
        metadata={"doc": "Additional delay per retry attempt."}
    )
    jitter_seconds: float = field(metadata={"doc": "Maximum random retry jitter."})


@dataclass(frozen=True)
class WorkflowTransition:
    schema_version: str = field(metadata={"doc": "Transition schema version."})
    from_state: str = field(metadata={"doc": "Source state."})
    to_state: str = field(metadata={"doc": "Destination state."})
    step_name: str = field(metadata={"doc": "Step that performs the transition."})
    retry_policy_ref: str = field(metadata={"doc": "Retry policy ID used by step."})
    side_effects: list[str] = field(
        metadata={"doc": "Side-effect families possible during this transition."}
    )


@dataclass(frozen=True)
class WorkflowContract:
    schema_version: str = field(metadata={"doc": "Workflow contract schema version."})
    workflow: str = field(metadata={"doc": "Workflow name."})
    version: str = field(metadata={"doc": "Workflow DAG/state-machine version."})
    states: list[str] = field(metadata={"doc": "All valid states."})
    initial_state: str = field(metadata={"doc": "Initial workflow state."})
    transitions: list[WorkflowTransition] = field(
        metadata={"doc": "Valid state transitions in deterministic order."}
    )
    prerequisites: dict[str, list[str]] = field(
        metadata={"doc": "Prerequisite checks by state or step."}
    )
    checkpoint_outputs: list[str] = field(
        metadata={"doc": "States that produce resumable checkpoint outputs."}
    )
    validation_gates: list[str] = field(
        metadata={"doc": "Validation gates enforced by the workflow."}
    )
    terminal_outcomes: list[str] = field(
        metadata={"doc": "Terminal outcomes emitted by the workflow."}
    )


@dataclass(frozen=True)
class ResolvedRetryPolicy:
    schema_version: str = field(metadata={"doc": "Resolved retry schema version."})
    workflow: str = field(metadata={"doc": "Workflow name."})
    step_name: str = field(metadata={"doc": "Step name."})
    policy_id: str = field(metadata={"doc": "Resolved policy ID."})
    policy: Any = field(metadata={"doc": "Runtime retry policy object."})


@dataclass(frozen=True)
class OperationalObservation:
    schema_version: str = field(metadata={"doc": "Observation schema version."})
    publisher: str = field(metadata={"doc": "Publisher or source owner."})
    workflow: str = field(metadata={"doc": "Workflow that produced the observation."})
    route: str = field(metadata={"doc": "Acquisition or execution route."})
    success: bool = field(metadata={"doc": "Whether the route succeeded."})
    runtime_seconds: float = field(metadata={"doc": "Observed runtime seconds."})
    cost_usd: float = field(metadata={"doc": "Observed estimated cost in USD."})
    failure_signature: str = field(
        metadata={"doc": "Stable failure signature for failed observations."}
    )
    pdf_extractable: bool = field(
        metadata={"doc": "Whether the resulting PDF was extractable."}
    )
    credential_required: bool = field(
        metadata={"doc": "Whether credentials or manual access were required."}
    )


@dataclass(frozen=True)
class OperationalMemoryRecord:
    schema_version: str = field(metadata={"doc": "Memory record schema version."})
    publisher: str = field(metadata={"doc": "Publisher or source owner."})
    workflow: str = field(metadata={"doc": "Workflow name."})
    route: str = field(metadata={"doc": "Route this record summarizes."})
    observation_count: int = field(metadata={"doc": "Total observations."})
    success_count: int = field(metadata={"doc": "Successful observations."})
    failure_count: int = field(metadata={"doc": "Failed observations."})
    success_rate: float = field(
        metadata={"doc": "Successful observations divided by total."}
    )
    average_runtime_seconds: float = field(metadata={"doc": "Mean observed runtime."})
    average_cost_usd: float = field(metadata={"doc": "Mean observed cost."})
    pdf_extractable_rate: float = field(
        metadata={"doc": "Share of observations with extractable PDFs."}
    )
    credential_required: bool = field(
        metadata={"doc": "Whether any observation required credentials."}
    )
    failure_signatures: list[str] = field(
        metadata={"doc": "Sorted failure signatures observed for this route."}
    )
    recommended_retry_policy: str = field(
        metadata={"doc": "Suggested retry policy ID for this route."}
    )


@dataclass(frozen=True)
class OperationalMemoryRecommendation:
    schema_version: str = field(
        metadata={"doc": "Memory recommendation schema version."}
    )
    publisher: str = field(metadata={"doc": "Publisher or source owner."})
    workflow: str = field(metadata={"doc": "Workflow name."})
    recommended_route: str = field(metadata={"doc": "Recommended route."})
    confidence: float = field(metadata={"doc": "Recommendation confidence 0..1."})
    reason: str = field(metadata={"doc": "Machine-readable recommendation reason."})
    failure_signatures: list[str] = field(
        metadata={"doc": "Failure signatures relevant to the recommendation."}
    )
    recommended_retry_policy: str = field(
        metadata={"doc": "Suggested retry policy ID."}
    )


@dataclass(frozen=True)
class ConcurrencyLimit:
    schema_version: str = field(metadata={"doc": "Concurrency limit schema version."})
    resource: str = field(
        metadata={"doc": "Resource family, such as model or browser."}
    )
    min_limit: int = field(metadata={"doc": "Lower bound for adaptive concurrency."})
    max_limit: int = field(metadata={"doc": "Upper bound for adaptive concurrency."})
    default_limit: int = field(metadata={"doc": "Default concurrency limit."})
    high_retry_rate: float = field(metadata={"doc": "Retry rate threshold to reduce."})
    high_latency_ms: int = field(metadata={"doc": "Latency threshold to reduce."})
    low_retry_rate: float = field(metadata={"doc": "Retry rate threshold to increase."})
    low_latency_ms: int = field(metadata={"doc": "Latency threshold to increase."})


@dataclass(frozen=True)
class ConcurrencyObservation:
    schema_version: str = field(
        metadata={"doc": "Concurrency observation schema version."}
    )
    resource: str = field(metadata={"doc": "Resource family observed."})
    current_limit: int = field(metadata={"doc": "Current concurrency limit."})
    retry_rate: float = field(metadata={"doc": "Recent retry rate."})
    p95_latency_ms: int = field(metadata={"doc": "Recent p95 latency in milliseconds."})
    sqlite_lock_count: int = field(metadata={"doc": "Recent SQLite lock count."})
    browser_failure_rate: float = field(
        metadata={"doc": "Recent browser failure rate."}
    )
    budget_burn_rate: float = field(metadata={"doc": "Recent budget burn rate 0..1+."})


@dataclass(frozen=True)
class ConcurrencyDecision:
    schema_version: str = field(
        metadata={"doc": "Concurrency decision schema version."}
    )
    resource: str = field(metadata={"doc": "Resource family."})
    previous_limit: int = field(metadata={"doc": "Previous concurrency limit."})
    selected_limit: int = field(metadata={"doc": "Selected concurrency limit."})
    reason: str = field(metadata={"doc": "Machine-readable decision reason."})
    evidence: dict[str, float | int | str] = field(
        metadata={"doc": "Sanitized metrics used by the decision."}
    )


@dataclass(frozen=True)
class RemediationReaperSettings:
    schema_version: str = field(
        metadata={"doc": "Remediation reaper settings version."}
    )
    execution_enabled: bool = field(
        default=False,
        metadata={"doc": "Feature gate; false keeps the ledger read-only."},
    )
    max_records_per_run: int = field(
        default=10, metadata={"doc": "Bounded records handled by one invocation."}
    )
    lease_seconds: int = field(
        default=60, metadata={"doc": "Bounded remediation work lease duration."}
    )


@dataclass(frozen=True)
class DeferredWorkReaperSettings:
    schema_version: str = field(
        metadata={"doc": "Deferred-work reaper settings version."}
    )
    execution_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Feature gate; false preserves queued records without leasing."
        },
    )
    max_records_per_run: int = field(
        default=10, metadata={"doc": "Bounded deferred records handled per invocation."}
    )
    lease_seconds: int = field(
        default=60, metadata={"doc": "Bounded deferred-work lease duration."}
    )
    retry_delay_seconds: int = field(
        default=3600, metadata={"doc": "Minimum delay after another defer decision."}
    )


@dataclass(frozen=True)
class WorkflowSupervisorSettings:
    schema_version: str = field(metadata={"doc": "Supervisor settings version."})
    enabled: bool = field(
        default=False, metadata={"doc": "Master supervisor feature gate."}
    )
    materialize_outbox_enabled: bool = field(default=True)
    recover_expired_leases_enabled: bool = field(default=True)
    deferred_work_enabled: bool = field(default=False)
    remediation_enabled: bool = field(default=False)
    worker_batches_enabled: bool = field(default=False)
    reconcile_enabled: bool = field(default=True)
    evidence_enabled: bool = field(default=True)
    max_jobs_per_queue: int = field(default=1)
    max_total_jobs: int = field(default=20)
    max_runtime_seconds: int = field(default=120)
    lease_seconds: int = field(default=180)


@dataclass(frozen=True)
class WorkflowControlSettings:
    schema_version: str = field(metadata={"doc": "Workflow control settings version."})
    preflight_profiles: dict[str, WorkflowPreflightProfile] = field(
        metadata={"doc": "Preflight profiles by workflow name."}
    )
    retry_policies: dict[str, dict[str, WorkflowRetryPolicyConfig]] = field(
        metadata={"doc": "Retry policies by workflow and step."}
    )
    workflow_contracts: dict[str, WorkflowContract] = field(
        metadata={"doc": "DAG/state-machine contracts by workflow name."}
    )
    concurrency: dict[str, ConcurrencyLimit] = field(
        metadata={"doc": "Adaptive concurrency limits by resource family."}
    )
    operational_memory_ttl_days: int = field(
        metadata={"doc": "Operational memory TTL in days."}
    )
    operational_memory_min_observations: int = field(
        metadata={"doc": "Minimum observations before high-confidence recommendations."}
    )
    remediation_reaper: RemediationReaperSettings = field(
        default_factory=lambda: RemediationReaperSettings(schema_version="1.0"),
        metadata={"doc": "Durable remediation reaper feature gate and bounds."},
    )
    deferred_work_reaper: DeferredWorkReaperSettings = field(
        default_factory=lambda: DeferredWorkReaperSettings(schema_version="1.0"),
        metadata={"doc": "Budget-deferred work recovery feature gate and bounds."},
    )
    supervisor: WorkflowSupervisorSettings = field(
        default_factory=lambda: WorkflowSupervisorSettings(schema_version="1.0"),
        metadata={"doc": "One-shot durable supervisor feature gates and bounds."},
    )


@dataclass(frozen=True)
class SupervisorRunRequest:
    schema_version: str = field(
        metadata={"doc": "Supervisor invocation schema version."}
    )
    state_db: str = field(metadata={"doc": "Canonical durable state database."})
    worker_id: str = field(metadata={"doc": "Stable supervisor owner identity."})
    now_utc: str = field(metadata={"doc": "Invocation clock for deterministic tests."})
    settings: WorkflowSupervisorSettings = field(
        metadata={"doc": "Resolved gates and bounds."}
    )
    usage_db_path: str = field(
        default="", metadata={"doc": "Deferred-work ledger path."}
    )


@dataclass(frozen=True)
class SupervisorRunResult:
    schema_version: str = field(metadata={"doc": "Supervisor result schema version."})
    status: str = field(
        metadata={"doc": "healthy, partially_deferred, failed, busy, or disabled."}
    )
    lease_acquired: bool = field(
        metadata={"doc": "Whether singleton lease was acquired."}
    )
    materialized_job_count: int = field(default=0)
    recovered_lease_count: int = field(default=0)
    deferred_reaped_count: int = field(default=0)
    remediation_reaped_count: int = field(default=0)
    completed_job_count: int = field(default=0)
    deferred_job_count: int = field(default=0)
    reconciled_count: int = field(default=0)
    queue_health_count: int = field(default=0)
    error_codes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class PreflightRemediationAction:
    schema_version: str = field(metadata={"doc": "Remediation action schema version."})
    check_name: str = field(
        metadata={"doc": "Preflight check that produced the action."}
    )
    action: str = field(metadata={"doc": "Stable remediation action name."})
    result: str = field(
        metadata={"doc": "Action result: already_applied, blocked, or skipped."}
    )
    safe_to_auto_apply: bool = field(
        metadata={"doc": "True only for allowlisted idempotent fixes."}
    )
    side_effect_boundary: str = field(
        metadata={"doc": "Boundary that owns the side effect."}
    )
    before_status: str = field(metadata={"doc": "Preflight status before remediation."})
    after_status: str = field(
        metadata={"doc": "Status after remediation or blocker classification."}
    )
    code: str = field(metadata={"doc": "Stable check or remediation code."})
    message: str = field(metadata={"doc": "Sanitized remediation message."})
    metadata: dict[str, Any] = field(
        metadata={"doc": "Sanitized evidence for the action."}
    )


@dataclass(frozen=True)
class PreflightRemediationArtifact:
    schema_version: str = field(
        metadata={"doc": "Remediation artifact schema version."}
    )
    workflow: str = field(metadata={"doc": "Workflow remediated by the artifact."})
    actions: list[PreflightRemediationAction] = field(
        metadata={"doc": "Resolved remediation actions in deterministic order."}
    )
    auto_applied_count: int = field(
        metadata={"doc": "Count of already-applied safe fixes."}
    )
    user_action_required_count: int = field(
        metadata={"doc": "Count of blockers that still require a user."}
    )
    blocked_unsafe_count: int = field(
        metadata={"doc": "Count of unsafe actions blocked."}
    )


@dataclass(frozen=True)
class RunIntent:
    schema_version: str = field(metadata={"doc": "Run-intent contract schema version."})
    intent: str = field(
        metadata={"doc": "Operator intent in stable or natural-language form."}
    )
    subject: str = field(
        metadata={"doc": "Optional subject such as URL, file path, or topic."}
    )
    publisher: str = field(metadata={"doc": "Optional publisher scope for planning."})
    report_id: str = field(metadata={"doc": "Optional report identifier for planning."})
    requested_side_effects: list[str] = field(
        metadata={"doc": "Side effects explicitly allowed or requested by the caller."}
    )
    dry_run: bool = field(
        metadata={"doc": "Whether the caller wants read-only resolution."}
    )
    allow_automation: bool = field(
        metadata={"doc": "Whether safe automation may proceed after planning."}
    )
    metadata: dict[str, Any] = field(metadata={"doc": "Sanitized caller context."})


@dataclass(frozen=True)
class ResolvedRunIntent:
    schema_version: str = field(metadata={"doc": "Resolved run-intent schema version."})
    status: str = field(
        metadata={
            "doc": "Resolution status: resolved, ambiguous, unsupported, or blocked."
        }
    )
    intent_key: str = field(metadata={"doc": "Normalized intent key."})
    workflow: str = field(metadata={"doc": "Resolved workflow name, if unambiguous."})
    preflight_profile: str = field(
        metadata={"doc": "Workflow preflight profile to use."}
    )
    budget_profile: str = field(
        metadata={"doc": "Budget profile selected for the intent."}
    )
    resume_stage: str = field(
        metadata={"doc": "Checkpoint stage selected before execution."}
    )
    side_effect_plan: list[str] = field(
        metadata={"doc": "Planned side-effect families."}
    )
    alternatives: list[str] = field(
        metadata={"doc": "Alternative intent keys when ambiguous."}
    )
    blockers: list[str] = field(
        metadata={"doc": "Blocker codes that prevent resolution."}
    )
    explanation: str = field(
        metadata={"doc": "Short machine-readable resolution reason."}
    )


@dataclass(frozen=True)
class PipelineExecutionPlan:
    schema_version: str = field(metadata={"doc": "Execution-plan contract version."})
    intent_key: str = field(metadata={"doc": "Normalized operator intent."})
    workflow: str = field(
        metadata={"doc": "Canonical workflow selected for execution."}
    )
    profile: str = field(metadata={"doc": "Resolved preflight/profile name."})
    ordered_steps: list[str] = field(
        metadata={"doc": "Deterministic workflow steps in execution order."}
    )
    skipped_steps: list[str] = field(
        metadata={"doc": "Known steps excluded before execution with no side effect."}
    )
    blocked_steps: list[str] = field(
        metadata={"doc": "Steps blocked before execution with stable blocker codes."}
    )
    required_credentials: list[str] = field(
        metadata={"doc": "Credential boundaries required by the selected profile."}
    )
    checkpoints: list[str] = field(
        metadata={
            "doc": "Checkpoint outputs available for resume or expected from the workflow."
        }
    )
    expected_artifacts: list[str] = field(
        metadata={"doc": "Expected durable workflow artifacts before execution begins."}
    )
    planned_side_effects: list[str] = field(
        metadata={
            "doc": "External side-effect families allowed only after plan approval."
        }
    )
    idempotency_key: str = field(
        metadata={
            "doc": "Stable idempotency key derived from the scoped operator intent."
        }
    )
    executable: bool = field(
        metadata={"doc": "Whether resolution produced an unblocked canonical workflow."}
    )
    blockers: list[str] = field(
        metadata={
            "doc": "Resolution blockers that prevent execution without a new plan."
        }
    )
    budget_boundaries: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Typed budget checks required before each planned side effect."
        },
    )


@dataclass(frozen=True)
class PipelineExecutionAuthorizationRequest:
    schema_version: str = field(
        metadata={"doc": "Execution-plan authorization request schema version."}
    )
    plan: PipelineExecutionPlan = field(
        metadata={"doc": "Side-effect-free plan proposed for execution."}
    )
    expected_workflow: str = field(
        metadata={"doc": "Canonical workflow the caller is about to execute."}
    )
    requested_side_effects: list[str] = field(
        metadata={"doc": "External side-effect families requested by the caller."}
    )


@dataclass(frozen=True)
class PipelineExecutionAuthorization:
    schema_version: str = field(
        metadata={"doc": "Execution-plan authorization result schema version."}
    )
    workflow: str = field(metadata={"doc": "Authorized canonical workflow."})
    idempotency_key: str = field(
        metadata={"doc": "Stable key carried from the approved execution plan."}
    )
    plan_checksum: str = field(
        metadata={"doc": "Deterministic checksum of the approved plan contract."}
    )
    allowed_side_effects: list[str] = field(
        metadata={"doc": "Side-effect families authorized by the approved plan."}
    )


@dataclass(frozen=True)
class PublishPolicyInput:
    schema_version: str = field(
        metadata={"doc": "Publish policy input schema version."}
    )
    validation_status: str = field(
        metadata={"doc": "Validation status for the artifact."}
    )
    family_confidence: dict[str, float] = field(
        metadata={"doc": "Confidence score by artifact family."}
    )
    warnings: list[str] = field(
        metadata={"doc": "Non-fatal validation or render warnings."}
    )
    missing_metadata: list[str] = field(
        metadata={"doc": "Required metadata fields that are absent."}
    )
    editorial_risk: str = field(
        metadata={"doc": "Editorial risk level: low, medium, high."}
    )
    override: bool = field(
        metadata={"doc": "Whether an operator override was supplied."}
    )
    automation_enabled: bool = field(
        metadata={"doc": "Whether policy may publish automatically."}
    )


@dataclass(frozen=True)
class PublishPolicyDecision:
    schema_version: str = field(
        metadata={"doc": "Publish policy decision schema version."}
    )
    action: str = field(
        metadata={"doc": "Decision: publish, draft, hold, repair, or review_required."}
    )
    reason: str = field(metadata={"doc": "Stable machine-readable reason."})
    min_confidence: float = field(metadata={"doc": "Lowest confidence score observed."})
    repair_supported: bool = field(
        metadata={"doc": "Whether targeted repair is supported."}
    )
    override_used: bool = field(
        metadata={"doc": "Whether an operator override changed the action."}
    )


@dataclass(frozen=True)
class PublishRemediationTarget:
    schema_version: str = field(
        metadata={"doc": "Publish remediation target schema version."}
    )
    rule_id: str = field(metadata={"doc": "Stable validation or editorial rule ID."})
    severity: str = field(metadata={"doc": "Warning, hold, or error severity."})
    affected_section: str = field(
        metadata={"doc": "Artifact path, section, or field affected by the issue."}
    )
    repair_target: str = field(
        metadata={"doc": "Machine-readable target to route the remediation step."}
    )
    repair_action: str = field(
        metadata={
            "doc": "Recommended remediation action for the operator or supervisor."
        }
    )
    sample_text: str = field(
        metadata={
            "doc": "Sanitized excerpt that explains the issue without leaking secrets."
        }
    )


@dataclass(frozen=True)
class PublishRemediationWorkflow:
    schema_version: str = field(
        metadata={"doc": "Publish remediation workflow schema version."}
    )
    decision: str = field(
        metadata={"doc": "Publish decision: pass, warn, hold, or fail."}
    )
    policy_mode: str = field(metadata={"doc": "Policy mode used for severity routing."})
    value_band: str = field(
        metadata={"doc": "Value band used for publish risk routing."}
    )
    warning_count: int = field(metadata={"doc": "Non-fatal warning count."})
    deferred_grounding_count: int = field(
        metadata={"doc": "Count of deferred grounding remediation targets."}
    )
    hard_fail_count: int = field(metadata={"doc": "Hard-fail issue count."})
    targets: list[PublishRemediationTarget] = field(
        metadata={"doc": "Structured remediation targets in issue order."}
    )


@dataclass(frozen=True)
class RunHealthGateInput:
    schema_version: str = field(
        metadata={"doc": "Run health gate input schema version."}
    )
    workflow: str = field(metadata={"doc": "Workflow controlled by the health gate."})
    scorecard: dict[str, Any] = field(
        metadata={"doc": "Run health scorecard payload or summary."}
    )
    max_warnings: int = field(
        default=0,
        metadata={"doc": "Maximum warning count allowed before the gate fails."},
    )
    allow_threshold_override: bool = field(
        default=False,
        metadata={"doc": "Whether operator override may bypass warning thresholds."},
    )
    policy_version: str = field(
        default="run-health-gate-v1",
        metadata={"doc": "Gate policy version logged for reproducibility."},
    )
    thresholds: dict[str, float | int] = field(
        default_factory=dict,
        metadata={
            "doc": "Optional workflow-specific limits for spend, retry exhaustion, validation, crop rejection, latency, and benchmark regressions."
        },
    )


@dataclass(frozen=True)
class RunHealthGateDecision:
    schema_version: str = field(
        metadata={"doc": "Run health gate decision schema version."}
    )
    workflow: str = field(metadata={"doc": "Workflow controlled by the health gate."})
    outcome: str = field(metadata={"doc": "Gate outcome: pass, warning, or fail."})
    action: str = field(metadata={"doc": "Supervisor action: allow, hold, or notify."})
    reason: str = field(metadata={"doc": "Stable machine-readable decision reason."})
    warning_count: int = field(
        metadata={"doc": "Scorecard warning count used by the gate."}
    )
    blockers: list[str] = field(
        metadata={"doc": "Gate blockers for supervisor planning."}
    )
    policy_version: str = field(metadata={"doc": "Gate policy version."})
    threshold_override_used: bool = field(
        metadata={"doc": "Whether an override changed a failing threshold."}
    )
    scorecard_run_id: str = field(
        metadata={"doc": "Scorecard run identifier, if present."}
    )


@dataclass(frozen=True)
class AutonomousRunSupervisorInput:
    schema_version: str = field(
        metadata={"doc": "Autonomous supervisor input schema version."}
    )
    workflow: str = field(metadata={"doc": "Workflow being supervised."})
    run_id: str = field(metadata={"doc": "Current run identifier."})
    current_state: str = field(metadata={"doc": "Current workflow state."})
    latest_safe_checkpoint: str = field(
        metadata={"doc": "Latest checkpoint stage safe to resume from."}
    )
    idempotency_scope: str = field(
        metadata={"doc": "Side-effect scope used for idempotency."}
    )
    idempotency_key: str = field(metadata={"doc": "Idempotency key for side effects."})
    preflight_passed: bool = field(metadata={"doc": "Whether preflight passed."})
    validation_status: str = field(metadata={"doc": "Validation status for the run."})
    health_gate: RunHealthGateDecision = field(
        metadata={"doc": "Run health gate decision consumed by the supervisor."}
    )
    retry_action: str = field(
        default="",
        metadata={"doc": "Retry or repair action selected by retry telemetry."},
    )
    blockers: list[str] = field(
        default_factory=list,
        metadata={"doc": "Known blockers that prevent autonomous continuation."},
    )
    publish_allowed: bool = field(
        default=False,
        metadata={"doc": "Whether the current run is allowed to publish."},
    )
    duplicate_side_effect_detected: bool = field(
        default=False,
        metadata={
            "doc": "Whether idempotency state shows the side effect already occurred."
        },
    )
    duplicate: bool = field(
        default=False,
        metadata={"doc": "Compatibility alias for duplicate side-effect detection."},
    )


@dataclass(frozen=True)
class AutonomousRunSupervisorPlan:
    schema_version: str = field(
        metadata={"doc": "Autonomous supervisor plan schema version."}
    )
    selected_action: str = field(
        metadata={
            "doc": "Selected action: start, resume, repair, retry, defer, publish, notify, dead_letter, or skip_duplicate."
        }
    )
    workflow: str = field(metadata={"doc": "Workflow being supervised."})
    run_id: str = field(metadata={"doc": "Current run identifier."})
    resume_stage: str = field(
        metadata={"doc": "Checkpoint or stage selected for resume."}
    )
    idempotency_scope: str = field(
        metadata={"doc": "Idempotency scope for planned side effects."}
    )
    idempotency_key: str = field(
        metadata={"doc": "Idempotency key for planned side effects."}
    )
    retry_action: str = field(
        metadata={"doc": "Retry action selected by telemetry, if any."}
    )
    health_gate_outcome: str = field(metadata={"doc": "Run health gate outcome."})
    blockers: list[str] = field(
        metadata={"doc": "Blockers attached to the selected action."}
    )
    expected_side_effects: list[str] = field(
        metadata={"doc": "External side-effect families the plan may perform."}
    )
    preflight_passed: bool = field(metadata={"doc": "Whether preflight passed."})
    validation_status: str = field(
        metadata={"doc": "Validation status consumed by the plan."}
    )


@dataclass(frozen=True)
class AutonomousRunSupervisorExecution:
    schema_version: str = field(
        metadata={"doc": "Supervisor execution schema version."}
    )
    selected_action: str = field(metadata={"doc": "Plan action that was dispatched."})
    workflow: str = field(metadata={"doc": "Workflow dispatched by the supervisor."})
    run_id: str = field(metadata={"doc": "Run identifier."})
    idempotency_key: str = field(
        metadata={"doc": "Idempotency key enforced by the caller."}
    )
    status: str = field(
        metadata={"doc": "Execution status: completed, skipped, deferred, or failed."}
    )
    outcome: str = field(metadata={"doc": "Registered handler outcome."})
    attempt_count: int = field(metadata={"doc": "Bounded dispatch attempt count."})
    error_code: str = field(
        default="", metadata={"doc": "Typed handler failure code when dispatch fails."}
    )


@dataclass(frozen=True)
class WorkflowControlObservation:
    schema_version: str = field(
        metadata={"doc": "Workflow-control observation schema version."}
    )
    observed_at_utc: str = field(metadata={"doc": "UTC timestamp for the observation."})
    run_id: str = field(
        metadata={"doc": "Run identifier that produced the observation."}
    )
    workflow: str = field(metadata={"doc": "Workflow name."})
    step_name: str = field(metadata={"doc": "Workflow step name."})
    route: str = field(metadata={"doc": "Route or strategy used for the step."})
    publisher: str = field(metadata={"doc": "Publisher scope, if applicable."})
    report_key: str = field(
        metadata={"doc": "Report key, URL, or artifact ID, if applicable."}
    )
    outcome: str = field(
        metadata={"doc": "Step outcome such as succeeded, failed, skipped, or held."}
    )
    error_code: str = field(
        metadata={"doc": "Typed AppError code when the step failed."}
    )
    error_retryable: bool = field(
        metadata={"doc": "Whether the failure was retryable."}
    )
    error_severity: str = field(metadata={"doc": "Typed error severity when present."})
    latency_ms: int = field(metadata={"doc": "Observed latency in milliseconds."})
    cost_usd: float = field(metadata={"doc": "Estimated step cost in USD."})
    retry_count: int = field(metadata={"doc": "Retries consumed by the step."})
    resource_pressure: dict[str, float | int | str] = field(
        metadata={"doc": "Sanitized resource-pressure signals."}
    )


@dataclass(frozen=True)
class PreLlmDataQualityInput:
    schema_version: str = field(
        metadata={"doc": "Pre-LLM data quality input schema version."}
    )
    file_id: str = field(metadata={"doc": "Report file identifier."})
    md5: str = field(metadata={"doc": "Report file checksum."})
    already_processed: bool = field(
        metadata={"doc": "Whether state already contains this file/checksum."}
    )
    duplicate_report: bool = field(
        metadata={"doc": "Whether this report is a duplicate of known content."}
    )
    text_char_count: int = field(metadata={"doc": "Extracted text character count."})
    supported_file_type: bool = field(
        metadata={"doc": "Whether the file type can be processed."}
    )
    report_like: bool = field(
        metadata={
            "doc": "Whether deterministic signals classify content as report-like."
        }
    )
    stale_already_processed: bool = field(
        metadata={"doc": "Whether cached processing is stale enough to repair."}
    )
    publisher_matches: bool = field(
        metadata={"doc": "Whether publisher evidence matches expected scope."}
    )
    publication_date_evidence: bool = field(
        metadata={"doc": "Whether publication date evidence exists."}
    )
    visual_candidate_count: int = field(
        metadata={"doc": "Count of usable deterministic visual candidates."}
    )
    known_gated_lead_form: bool = field(
        metadata={"doc": "Whether prior evidence shows a lead-form blocker."}
    )


@dataclass(frozen=True)
class PreLlmDataQualityDecision:
    schema_version: str = field(
        metadata={"doc": "Pre-LLM gate decision schema version."}
    )
    outcome: WorkflowGateOutcome = field(metadata={"doc": "Gate outcome."})
    expensive_work_allowed: bool = field(
        metadata={"doc": "Whether model-heavy work may start."}
    )
    reason: str = field(metadata={"doc": "Stable machine-readable reason."})
    source_signals: dict[str, Any] = field(
        metadata={"doc": "Sanitized deterministic source signals."}
    )
    remediation: str = field(
        metadata={"doc": "Next remediation or continuation action."}
    )


@dataclass(frozen=True)
class ModelCallAuditRecord:
    schema_version: str = field(metadata={"doc": "Model call audit schema version."})
    operation: str = field(metadata={"doc": "LLM service operation name."})
    scope: str = field(metadata={"doc": "LLM client policy scope."})
    provider_decision: str = field(metadata={"doc": "Provider routing decision."})
    prompt_namespace: str = field(
        metadata={"doc": "Prompt namespace used for the call."}
    )
    prompt_hash: str = field(
        metadata={"doc": "Prompt service or caller supplied prompt hash."}
    )
    rendered_prompt_redaction_hash: str = field(
        metadata={
            "doc": "Hash of rendered prompt text after redaction boundary selection."
        }
    )
    model: str = field(metadata={"doc": "Model requested or resolved for the call."})
    temperature: float | None = field(
        metadata={"doc": "Temperature parameter, if supported."}
    )
    seed: int | None = field(metadata={"doc": "Seed parameter, if supplied."})
    seed_supported: bool = field(
        metadata={"doc": "Whether seed was supplied and auditable."}
    )
    schema_name: str = field(metadata={"doc": "Output schema name, if any."})
    output_schema_version: str = field(
        metadata={"doc": "Output schema version, if any."}
    )
    response_id: str = field(
        metadata={"doc": "Provider response identifier, if available."}
    )
    input_tokens: int | None = field(
        metadata={"doc": "Input token count, if reported."}
    )
    output_tokens: int | None = field(
        metadata={"doc": "Output token count, if reported."}
    )
    total_tokens: int | None = field(
        metadata={"doc": "Total token count, if reported."}
    )
    estimated_cost_usd: float = field(metadata={"doc": "Estimated cost when known."})
    cache_key: str = field(metadata={"doc": "Semantic cache key when known."})
    cache_decision: str = field(
        metadata={"doc": "Cache decision: enabled, disabled, hit, or write."}
    )
    validation_result: str = field(
        metadata={"doc": "Validation result for the response."}
    )


@dataclass(frozen=True)
class ModelCallReplayBundle:
    schema_version: str = field(
        metadata={"doc": "Model call replay bundle schema version."}
    )
    audit_record: ModelCallAuditRecord = field(metadata={"doc": "Source audit record."})
    replay_inputs: dict[str, Any] = field(
        metadata={"doc": "Deterministic replay inputs."}
    )
    live_provider_call_allowed: bool = field(
        metadata={
            "doc": "False unless an explicit operator override enables live replay."
        }
    )


@dataclass(frozen=True)
class MailDeliveryWorkflowRunRequest:
    schema_version: str = field(
        metadata={"doc": "Mail-delivery workflow run request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite state DB path."})
    reports_db: str = field(metadata={"doc": "Report metadata DB path."})
    mailbox_settings: MailboxAcquisitionSettings = field(
        metadata={"doc": "Mailbox acquisition settings."}
    )
    browser_download_settings: BrowserDownloadSettings = field(
        metadata={"doc": "Browser-download settings for delivered links."}
    )
    now_utc: str = field(metadata={"doc": "UTC due-list timestamp."})
    limit: int = field(default=20, metadata={"doc": "Maximum due requests to process."})


@dataclass(frozen=True)
class MailDeliveryWorkflowItemResult:
    schema_version: str = field(metadata={"doc": "Mail-delivery item result version."})
    request_id: int = field(metadata={"doc": "State DB mail request ID."})
    status: str = field(metadata={"doc": "Updated status."})
    outcome: str = field(metadata={"doc": "Acquisition outcome or error taxonomy."})
    selected_message_id: str = field(metadata={"doc": "Selected mailbox message ID."})
    downloaded_file_path: str = field(metadata={"doc": "Acquired artifact path."})
    error_code: str = field(metadata={"doc": "Typed error code, if any."})


@dataclass(frozen=True)
class MailDeliveryWorkflowRunResult:
    schema_version: str = field(
        metadata={"doc": "Mail-delivery workflow run result schema version."}
    )
    processed_count: int = field(metadata={"doc": "Due rows attempted."})
    succeeded_count: int = field(metadata={"doc": "Rows that succeeded."})
    deferred_count: int = field(metadata={"doc": "Rows deferred for retry."})
    failed_count: int = field(metadata={"doc": "Rows marked failed."})
    results: list[MailDeliveryWorkflowItemResult] = field(
        metadata={"doc": "Per-request workflow results."}
    )


WorkflowContinuation = Callable[[], Any]
