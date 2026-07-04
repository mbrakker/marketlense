from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


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
    success_rate: float = field(metadata={"doc": "Successful observations divided by total."})
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
    recommended_retry_policy: str = field(metadata={"doc": "Suggested retry policy ID."})


@dataclass(frozen=True)
class ConcurrencyLimit:
    schema_version: str = field(metadata={"doc": "Concurrency limit schema version."})
    resource: str = field(metadata={"doc": "Resource family, such as model or browser."})
    min_limit: int = field(metadata={"doc": "Lower bound for adaptive concurrency."})
    max_limit: int = field(metadata={"doc": "Upper bound for adaptive concurrency."})
    default_limit: int = field(metadata={"doc": "Default concurrency limit."})
    high_retry_rate: float = field(metadata={"doc": "Retry rate threshold to reduce."})
    high_latency_ms: int = field(metadata={"doc": "Latency threshold to reduce."})
    low_retry_rate: float = field(metadata={"doc": "Retry rate threshold to increase."})
    low_latency_ms: int = field(metadata={"doc": "Latency threshold to increase."})


@dataclass(frozen=True)
class ConcurrencyObservation:
    schema_version: str = field(metadata={"doc": "Concurrency observation schema version."})
    resource: str = field(metadata={"doc": "Resource family observed."})
    current_limit: int = field(metadata={"doc": "Current concurrency limit."})
    retry_rate: float = field(metadata={"doc": "Recent retry rate."})
    p95_latency_ms: int = field(metadata={"doc": "Recent p95 latency in milliseconds."})
    sqlite_lock_count: int = field(metadata={"doc": "Recent SQLite lock count."})
    browser_failure_rate: float = field(metadata={"doc": "Recent browser failure rate."})
    budget_burn_rate: float = field(metadata={"doc": "Recent budget burn rate 0..1+."})


@dataclass(frozen=True)
class ConcurrencyDecision:
    schema_version: str = field(metadata={"doc": "Concurrency decision schema version."})
    resource: str = field(metadata={"doc": "Resource family."})
    previous_limit: int = field(metadata={"doc": "Previous concurrency limit."})
    selected_limit: int = field(metadata={"doc": "Selected concurrency limit."})
    reason: str = field(metadata={"doc": "Machine-readable decision reason."})
    evidence: dict[str, float | int | str] = field(
        metadata={"doc": "Sanitized metrics used by the decision."}
    )


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
