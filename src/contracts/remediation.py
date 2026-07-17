from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

from src.contracts.retry_decision import RetryDecision

RemediationStatus = Literal[
    "pending",
    "leased",
    "retrying",
    "deferred",
    "operator_action_required",
    "terminal",
    "resolved",
    "superseded",
]

RemediationActionCode = Literal[
    "resume_valid_checkpoint",
    "retry_transient_service_call",
    "rerun_targeted_artifact_family",
    "revalidate_replaced_source",
    "poll_mailbox_delivery",
    "retry_idempotent_publication",
    "defer_for_budget",
    "escalate_credentials",
    "mark_terminal_blocker",
]


@dataclass(frozen=True)
class RemediationCheckpointReference:
    """A checkpoint that was verified when the failure was recorded.

    ``checksum_sha256`` makes the reaper fail closed if the file changes before
    execution. ``lineage_ref`` is intentionally required for resumable work.
    """

    schema_version: str = field(
        metadata={"doc": "Checkpoint reference schema version."}
    )
    path: str = field(metadata={"doc": "Canonical checkpoint path."})
    stage_name: str = field(
        metadata={"doc": "Completed stage represented by checkpoint."}
    )
    checksum_sha256: str = field(metadata={"doc": "SHA-256 of checkpoint bytes."})
    lineage_ref: str = field(metadata={"doc": "Canonical artifact-lineage reference."})
    validation_status: str = field(
        default="validated",
        metadata={
            "doc": "Validation status at record time; only validated is resumable."
        },
    )


@dataclass(frozen=True)
class RemediationArtifactReference:
    schema_version: str = field(metadata={"doc": "Artifact reference schema version."})
    name: str = field(metadata={"doc": "Stable logical artifact name."})
    reference: str = field(metadata={"doc": "Artifact path or canonical identifier."})
    checksum_sha256: str = field(
        default="", metadata={"doc": "Optional immutable checksum."}
    )
    lineage_ref: str = field(
        default="", metadata={"doc": "Optional canonical lineage reference."}
    )


@dataclass(frozen=True)
class RemediationIdempotencyKey:
    schema_version: str = field(
        metadata={"doc": "Idempotency reference schema version."}
    )
    scope: str = field(metadata={"doc": "Canonical idempotency scope."})
    key: str = field(metadata={"doc": "Stable side-effect idempotency key."})
    input_checksum: str = field(
        metadata={"doc": "Checksum bound to the idempotency key."}
    )


@dataclass(frozen=True)
class RemediationBudgetSummary:
    schema_version: str = field(metadata={"doc": "Budget summary schema version."})
    consumed: dict[str, float | int] = field(
        default_factory=dict, metadata={"doc": "Already consumed budget metrics."}
    )
    reserved: dict[str, float | int] = field(
        default_factory=dict, metadata={"doc": "Reserved budget metrics."}
    )
    remaining: dict[str, float | int] = field(
        default_factory=dict, metadata={"doc": "Remaining budget metrics when known."}
    )
    decision: str = field(
        default="allow", metadata={"doc": "Latest canonical budget decision."}
    )


@dataclass(frozen=True)
class RemediationRecord:
    """Canonical durable record for one deterministically deduplicated failure."""

    schema_version: str = field(metadata={"doc": "Remediation record schema version."})
    remediation_id: str = field(metadata={"doc": "Stable remediation identifier."})
    dedupe_key: str = field(
        metadata={"doc": "Stable current-failure deduplication key."}
    )
    workflow: str = field(metadata={"doc": "Workflow that owns recovery."})
    run_id: str = field(metadata={"doc": "Workflow run ID."})
    task_id: str = field(metadata={"doc": "Workflow task ID."})
    span_id: str = field(metadata={"doc": "Workflow span ID."})
    report_id: str = field(
        default="", metadata={"doc": "Affected report ID, if known."}
    )
    source_id: str = field(
        default="", metadata={"doc": "Affected source ID, if known."}
    )
    publisher_id: str = field(
        default="", metadata={"doc": "Affected publisher ID, if known."}
    )
    input_checksum: str = field(
        default="", metadata={"doc": "Deterministic input checksum."}
    )
    failed_stage: str = field(default="", metadata={"doc": "Failed workflow stage."})
    operation: str = field(
        default="", metadata={"doc": "Failed operation within the stage."}
    )
    error_code: str = field(default="", metadata={"doc": "Typed AppError code."})
    error_classification: str = field(
        default="unknown", metadata={"doc": "Closed remediation classification."}
    )
    retry_decision: RetryDecision | None = field(
        default=None, metadata={"doc": "Existing retry-policy decision."}
    )
    status: RemediationStatus = field(
        default="pending", metadata={"doc": "Current remediation state."}
    )
    checkpoint: RemediationCheckpointReference | None = field(
        default=None, metadata={"doc": "Candidate resumable checkpoint."}
    )
    reusable_artifacts: list[RemediationArtifactReference] = field(
        default_factory=list, metadata={"doc": "Validated reusable artifacts."}
    )
    committed_side_effects: list[str] = field(
        default_factory=list, metadata={"doc": "Known committed external effects."}
    )
    idempotency_keys: list[RemediationIdempotencyKey] = field(
        default_factory=list, metadata={"doc": "Side-effect proof references."}
    )
    budget: RemediationBudgetSummary = field(
        default_factory=lambda: RemediationBudgetSummary(schema_version="1.0"),
        metadata={"doc": "Consumed, reserved, and remaining budget."},
    )
    attempt_count: int = field(
        default=0, metadata={"doc": "Durable reaper attempts consumed."}
    )
    max_attempts: int = field(
        default=1, metadata={"doc": "Maximum durable reaper attempts."}
    )
    cooldown_seconds: int = field(
        default=0, metadata={"doc": "Minimum delay between attempts."}
    )
    next_eligible_at_utc: str = field(
        default="", metadata={"doc": "Next time eligible for leasing."}
    )
    action_code: RemediationActionCode = field(
        default="mark_terminal_blocker",
        metadata={"doc": "Policy-approved remediation action."},
    )
    operator_next_action: str = field(
        default="", metadata={"doc": "Concise operator instruction."}
    )
    runbook_ref: str = field(
        default="docs/ops/recovery.md", metadata={"doc": "Runbook reference."}
    )
    created_at_utc: str = field(default="", metadata={"doc": "Creation timestamp."})
    updated_at_utc: str = field(default="", metadata={"doc": "Last update timestamp."})
    resolved_at_utc: str = field(
        default="", metadata={"doc": "Resolution timestamp, if resolved."}
    )
    lease_owner: str = field(default="", metadata={"doc": "Current lease owner."})
    lease_expires_at_utc: str = field(
        default="", metadata={"doc": "Current lease expiry."}
    )
    diagnostics: dict[str, Any] = field(
        default_factory=dict, metadata={"doc": "Operator-only sanitized diagnostics."}
    )


@dataclass(frozen=True)
class RemediationUpsertRequest:
    schema_version: str = field(
        metadata={"doc": "Remediation upsert request schema version."}
    )
    state_db: str = field(metadata={"doc": "Canonical state database path."})
    record: RemediationRecord = field(
        metadata={"doc": "Record to create or deterministically update."}
    )


@dataclass(frozen=True)
class RemediationUpsertResponse:
    schema_version: str = field(
        metadata={"doc": "Remediation upsert response schema version."}
    )
    record: RemediationRecord = field(metadata={"doc": "Persisted current record."})
    created: bool = field(metadata={"doc": "Whether a new durable record was created."})
    deduplicated: bool = field(
        metadata={"doc": "Whether an existing current record was reused."}
    )


@dataclass(frozen=True)
class RemediationListRequest:
    schema_version: str = field(
        metadata={"doc": "Remediation list request schema version."}
    )
    state_db: str = field(metadata={"doc": "Canonical state database path."})
    statuses: list[str] = field(
        default_factory=list, metadata={"doc": "Optional status filter."}
    )
    workflow: str = field(default="", metadata={"doc": "Optional workflow filter."})
    limit: int = field(default=100, metadata={"doc": "Maximum number of records."})


@dataclass(frozen=True)
class RemediationListResponse:
    schema_version: str = field(
        metadata={"doc": "Remediation list response schema version."}
    )
    records: list[RemediationRecord] = field(
        metadata={"doc": "Current remediation records."}
    )


@dataclass(frozen=True)
class RemediationSoakReportRequest:
    """Read-only operational summary of canonical remediation state."""

    schema_version: str = field(
        metadata={"doc": "Remediation soak-report request schema version."}
    )
    state_db: str = field(metadata={"doc": "Canonical state database path."})
    now_utc: str = field(
        metadata={"doc": "UTC observation time used for lease eligibility."}
    )
    runbook_error_codes: list[str] = field(
        default_factory=list,
        metadata={"doc": "Failure codes with an approved operator runbook mapping."},
    )


@dataclass(frozen=True)
class RemediationSoakReportResponse:
    """Read-only evidence used to decide whether the reaper may be activated."""

    schema_version: str = field(
        metadata={"doc": "Remediation soak-report response schema version."}
    )
    created_record_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Records created in the retained remediation history."},
    )
    deduplicated_record_ids: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Retained duplicate-observation record IDs; repeats are events."
        },
    )
    stale_lease_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Expired leased or retrying records; no lease is released."},
    )
    eligible_record_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Pending or deferred records currently eligible for a lease."},
    )
    held_record_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Records requiring operator action or marked terminal."},
    )
    missing_runbook_error_codes: list[str] = field(
        default_factory=list,
        metadata={"doc": "Observed error codes without an approved runbook mapping."},
    )


@dataclass(frozen=True)
class RemediationClaimRequest:
    schema_version: str = field(
        metadata={"doc": "Remediation lease-claim request schema version."}
    )
    state_db: str = field(metadata={"doc": "Canonical state database path."})
    worker_id: str = field(metadata={"doc": "Stable bounded-reaper worker ID."})
    now_utc: str = field(
        metadata={"doc": "UTC time used for deterministic eligibility."}
    )
    lease_seconds: int = field(default=60, metadata={"doc": "Bounded lease duration."})


@dataclass(frozen=True)
class RemediationClaimResponse:
    schema_version: str = field(
        metadata={"doc": "Remediation claim response schema version."}
    )
    record: RemediationRecord | None = field(
        default=None, metadata={"doc": "Claimed record, if eligible work exists."}
    )


@dataclass(frozen=True)
class RemediationTransitionRequest:
    schema_version: str = field(
        metadata={"doc": "Remediation transition request schema version."}
    )
    state_db: str = field(metadata={"doc": "Canonical state database path."})
    remediation_id: str = field(metadata={"doc": "Record to transition."})
    status: RemediationStatus = field(metadata={"doc": "Destination state."})
    reason: str = field(metadata={"doc": "Stable transition reason."})
    actor: str = field(
        default="system", metadata={"doc": "Worker or operator causing transition."}
    )
    next_eligible_at_utc: str = field(
        default="", metadata={"doc": "Optional future eligibility time."}
    )
    increment_attempt: bool = field(
        default=False, metadata={"doc": "Whether durable attempt count increases."}
    )


@dataclass(frozen=True)
class RemediationTransitionResponse:
    schema_version: str = field(
        metadata={"doc": "Remediation transition response schema version."}
    )
    record: RemediationRecord = field(metadata={"doc": "Record after transition."})


@dataclass(frozen=True)
class RemediationExpiredLeaseReleaseRequest:
    schema_version: str = field(
        metadata={"doc": "Expired lease release request schema version."}
    )
    state_db: str = field(metadata={"doc": "Canonical state database path."})
    now_utc: str = field(metadata={"doc": "UTC time used to identify expired leases."})


@dataclass(frozen=True)
class RemediationExpiredLeaseReleaseResponse:
    schema_version: str = field(
        metadata={"doc": "Expired lease release response schema version."}
    )
    released_ids: list[str] = field(
        metadata={"doc": "Leases returned to pending state."}
    )


@dataclass(frozen=True)
class RemediationReaperRequest:
    schema_version: str = field(
        metadata={"doc": "Bounded reaper request schema version."}
    )
    state_db: str = field(metadata={"doc": "Canonical state database path."})
    worker_id: str = field(metadata={"doc": "Stable reaper worker identifier."})
    now_utc: str = field(metadata={"doc": "UTC eligibility clock."})
    limit: int = field(
        default=10, metadata={"doc": "Maximum records processed in this invocation."}
    )
    lease_seconds: int = field(default=60, metadata={"doc": "Bounded lease duration."})
    execution_enabled: bool = field(
        default=False, metadata={"doc": "Explicit feature gate for any automatic work."}
    )


@dataclass(frozen=True)
class RemediationReaperResponse:
    schema_version: str = field(
        metadata={"doc": "Bounded reaper response schema version."}
    )
    inspected_count: int = field(metadata={"doc": "Records claimed and inspected."})
    resolved_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Remediations resolved without duplicate side effects."},
    )
    deferred_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Remediations deferred by policy or budget."},
    )
    held_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Records held for an operator or terminal blocker."},
    )
    released_lease_ids: list[str] = field(
        default_factory=list, metadata={"doc": "Expired leases recovered before work."}
    )
