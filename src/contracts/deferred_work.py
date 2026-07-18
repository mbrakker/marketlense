from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

DeferredWorkStatus = Literal[
    "pending", "leased", "completed", "remediation", "terminal"
]


@dataclass(frozen=True)
class DeferredWorkArtifactReference:
    """A reusable, non-secret artifact reference needed to resume work."""

    schema_version: str = field(
        metadata={"doc": "Deferred-work artifact-reference schema version."}
    )
    kind: str = field(metadata={"doc": "Stable artifact family, for example local_pdf."})
    reference: str = field(metadata={"doc": "Canonical artifact identifier or path."})
    checksum: str = field(
        default="", metadata={"doc": "Optional retained artifact checksum."}
    )


@dataclass(frozen=True)
class DeferredWorkItem:
    """One durable budget-deferred operation with a bounded recovery lifecycle."""

    schema_version: str = field(metadata={"doc": "Deferred-work item schema version."})
    work_key: str = field(metadata={"doc": "Stable durable item identifier."})
    workflow: str = field(metadata={"doc": "Workflow that owns safe resumption."})
    stage: str = field(metadata={"doc": "Latest safe workflow stage before the defer."})
    run_id: str = field(metadata={"doc": "Original governed run identifier."})
    resource_type: str = field(metadata={"doc": "Deferred external resource family."})
    operation: str = field(metadata={"doc": "Deferred operation name."})
    reason_code: str = field(metadata={"doc": "Canonical budget-decision reason."})
    affected_limit: str = field(metadata={"doc": "Budget scope and metric that blocked work."})
    earliest_run_at_utc: str = field(metadata={"doc": "Inclusive next eligible UTC time."})
    deadline_at_utc: str = field(metadata={"doc": "Exclusive auto-resume deadline UTC time."})
    attempt_count: int = field(metadata={"doc": "Leased resume attempts consumed."})
    max_attempts: int = field(metadata={"doc": "Maximum automatic resume attempts."})
    deferred_at_utc: str = field(metadata={"doc": "First canonical deferral time UTC."})
    updated_at_utc: str = field(metadata={"doc": "Last durable item update UTC."})
    report_id: str = field(default="", metadata={"doc": "Report identity when known."})
    source_id: str = field(default="", metadata={"doc": "Source identity when known."})
    publisher_id: str = field(default="", metadata={"doc": "Publisher scope when known."})
    plan_hash: str = field(default="", metadata={"doc": "Plan hash observed at deferral."})
    reusable_artifacts: list[DeferredWorkArtifactReference] = field(
        default_factory=list,
        metadata={"doc": "Retained artifacts reusable by the owning workflow."},
    )
    idempotency_key: str = field(
        default="", metadata={"doc": "Original side-effect idempotency key."}
    )
    status: DeferredWorkStatus = field(
        default="pending", metadata={"doc": "Durable recovery lifecycle status."}
    )
    lease_owner: str = field(default="", metadata={"doc": "Current bounded lease owner."})
    lease_expires_at_utc: str = field(
        default="", metadata={"doc": "UTC expiry for the current lease."}
    )
    terminal_status: str = field(
        default="", metadata={"doc": "Terminal or remediation reason, when no longer automatic."}
    )
    remediation_id: str = field(
        default="", metadata={"doc": "Existing remediation-ledger handoff, when created."}
    )
    completed_at_utc: str = field(
        default="", metadata={"doc": "Completion time UTC when successfully resumed."}
    )
    defer_count: int = field(
        default=1, metadata={"doc": "Distinct deferrals observed while work was leased."}
    )
    budget_request_json: str = field(
        default="{}",
        metadata={"doc": "Sanitized serialized canonical request used for re-evaluation."},
    )


@dataclass(frozen=True)
class DeferredWorkListRequest:
    schema_version: str = field(metadata={"doc": "Deferred-work list request schema version."})
    usage_db_path: str = field(metadata={"doc": "Canonical budget ledger database path."})
    statuses: list[DeferredWorkStatus] = field(default_factory=list)
    workflow: str = field(default="")
    limit: int = field(default=100)


@dataclass(frozen=True)
class DeferredWorkListResponse:
    schema_version: str = field(metadata={"doc": "Deferred-work list response schema version."})
    records: list[DeferredWorkItem] = field(default_factory=list)


@dataclass(frozen=True)
class DeferredWorkClaimRequest:
    schema_version: str = field(metadata={"doc": "Deferred-work claim request schema version."})
    usage_db_path: str = field(metadata={"doc": "Canonical budget ledger database path."})
    worker_id: str = field(metadata={"doc": "Stable worker identity acquiring the lease."})
    now_utc: str = field(metadata={"doc": "UTC time used for due and lease checks."})
    lease_seconds: int = field(default=60)


@dataclass(frozen=True)
class DeferredWorkClaimResponse:
    schema_version: str = field(metadata={"doc": "Deferred-work claim response schema version."})
    record: DeferredWorkItem | None = field(default=None)


@dataclass(frozen=True)
class DeferredWorkTransitionRequest:
    schema_version: str = field(
        metadata={"doc": "Deferred-work transition request schema version."}
    )
    usage_db_path: str = field(metadata={"doc": "Canonical budget ledger database path."})
    work_key: str = field(metadata={"doc": "Durable item receiving the transition."})
    worker_id: str = field(metadata={"doc": "Lease owner authorizing the transition."})
    status: DeferredWorkStatus = field(metadata={"doc": "Target lifecycle status."})
    reason: str = field(metadata={"doc": "Stable transition reason."})
    now_utc: str = field(metadata={"doc": "UTC transition time."})
    earliest_run_at_utc: str = field(default="")
    terminal_status: str = field(default="")
    remediation_id: str = field(default="")
    plan_hash: str = field(default="")
    reusable_artifacts: list[DeferredWorkArtifactReference] | None = field(default=None)
    increment_defer_count: bool = field(
        default=False, metadata={"doc": "Whether this transition observed another defer decision."}
    )


@dataclass(frozen=True)
class DeferredWorkTransitionResponse:
    schema_version: str = field(
        metadata={"doc": "Deferred-work transition response schema version."}
    )
    record: DeferredWorkItem = field(metadata={"doc": "Item after the durable transition."})


@dataclass(frozen=True)
class DeferredWorkLeaseReleaseRequest:
    schema_version: str = field(metadata={"doc": "Deferred-work lease release request schema version."})
    usage_db_path: str = field(metadata={"doc": "Canonical budget ledger database path."})
    now_utc: str = field(metadata={"doc": "UTC time used to identify expired leases."})


@dataclass(frozen=True)
class DeferredWorkLeaseReleaseResponse:
    schema_version: str = field(metadata={"doc": "Deferred-work lease release response schema version."})
    released_work_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DeferredWorkMetricsRequest:
    schema_version: str = field(metadata={"doc": "Deferred-work metrics request schema version."})
    usage_db_path: str = field(metadata={"doc": "Canonical budget ledger database path."})
    now_utc: str = field(metadata={"doc": "UTC observation time."})


@dataclass(frozen=True)
class DeferredWorkMetrics:
    schema_version: str = field(metadata={"doc": "Deferred-work metrics schema version."})
    queue_depth: int = field(metadata={"doc": "Pending and leased item count."})
    oldest_age_seconds: int = field(metadata={"doc": "Age of the oldest non-terminal item."})
    due_count: int = field(metadata={"doc": "Pending items due at observation time."})
    lease_count: int = field(metadata={"doc": "Currently unexpired item leases."})
    completion_rate: float = field(metadata={"doc": "Completed share of terminally decided items."})
    repeated_deferral_count: int = field(metadata={"doc": "Items deferred more than once."})
    terminal_count: int = field(metadata={"doc": "Remediation and terminal item count."})


@dataclass(frozen=True)
class DeferredWorkResumePlan:
    """A freshly validated, minimum plan for one leased item."""

    schema_version: str = field(
        metadata={"doc": "Deferred-work resume-plan schema version."}
    )
    plan_hash: str = field(metadata={"doc": "Fresh minimal-plan hash."})
    resume_stage: str = field(
        metadata={"doc": "Latest safe stage passed to the owning workflow."}
    )
    reusable_artifacts: list[DeferredWorkArtifactReference] = field(
        default_factory=list,
        metadata={"doc": "Validated artifacts the fresh plan may reuse."},
    )


@dataclass(frozen=True)
class DeferredWorkReaperRequest:
    schema_version: str = field(metadata={"doc": "Deferred-work reaper request schema version."})
    usage_db_path: str = field(metadata={"doc": "Canonical budget ledger database path."})
    state_db: str = field(metadata={"doc": "Canonical remediation state database path."})
    worker_id: str = field(metadata={"doc": "Stable worker identity."})
    now_utc: str = field(metadata={"doc": "UTC invocation time."})
    execution_enabled: bool = field(
        default=False,
        metadata={"doc": "Feature gate; false leaves all deferred rows untouched."},
    )
    limit: int = field(default=10, metadata={"doc": "Bounded items per invocation."})
    lease_seconds: int = field(default=60, metadata={"doc": "Bounded SQLite lease duration."})
    retry_delay_seconds: int = field(
        default=3600, metadata={"doc": "Minimum delay after a continued defer."}
    )


@dataclass(frozen=True)
class DeferredWorkReaperResponse:
    schema_version: str = field(metadata={"doc": "Deferred-work reaper response schema version."})
    inspected_count: int = field(metadata={"doc": "Leased rows inspected this invocation."})
    completed_work_keys: list[str] = field(default_factory=list)
    deferred_work_keys: list[str] = field(default_factory=list)
    remediation_work_keys: list[str] = field(default_factory=list)
    released_lease_work_keys: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DeferredWorkQueueMigrationRequest:
    """Bounded request to hand legacy due work to the canonical workflow queue.

    Legacy rows remain readable in the usage ledger.  The adapter deliberately
    migrates only workflows whose retained inputs can be verified and whose
    queue mapping is code-reviewed; it never invents a generic scheduler.
    """

    schema_version: str = field(
        metadata={"doc": "Deferred-work queue-migration request schema version."}
    )
    usage_db_path: str = field(metadata={"doc": "Canonical usage-ledger path."})
    state_db: str = field(metadata={"doc": "Canonical workflow-state database path."})
    limit: int = field(default=100, metadata={"doc": "Maximum legacy rows inspected."})


@dataclass(frozen=True)
class DeferredWorkQueueMigrationRecord:
    """One retained legacy row and its effective workflow-queue handoff."""

    schema_version: str = field(
        default="1.0", metadata={"doc": "Contract schema version."}
    )
    work_key: str = field(default="", metadata={"doc": "Legacy durable work key."})
    workflow_job_id: str = field(
        default="", metadata={"doc": "Canonical queue job when materialised."}
    )
    outcome: str = field(
        default="", metadata={"doc": "submitted, deduplicated, or unresolved."}
    )
    reason: str = field(
        default="", metadata={"doc": "Bounded non-sensitive handoff reason."}
    )


@dataclass(frozen=True)
class DeferredWorkQueueMigrationResponse:
    """Observable result of one explicit, non-destructive legacy handoff pass."""

    schema_version: str = field(
        default="1.0", metadata={"doc": "Contract schema version."}
    )
    inspected_count: int = field(
        default=0, metadata={"doc": "Legacy pending rows inspected."}
    )
    records: list[DeferredWorkQueueMigrationRecord] = field(
        default_factory=list,
        metadata={"doc": "One outcome per inspected durable legacy record."},
    )
