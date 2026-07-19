from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class AcquisitionAttemptResourceSummary:
    """Bounded scalar resource envelope for one governed acquisition attempt."""

    schema_version: str = field(metadata={"doc": "Resource-summary schema version."})
    attempt_id: str = field(
        metadata={"doc": "Stable idempotency identifier for the attempt."}
    )
    publisher_id: str = field(
        metadata={"doc": "Publisher identifier or bounded empty value."}
    )
    source_identity_id: str = field(
        metadata={"doc": "Canonical source identity when resolved, else empty."}
    )
    source_identity_status: str = field(
        metadata={"doc": "resolved, unresolved, or legacy_incomplete."}
    )
    normalized_url: str = field(metadata={"doc": "Normalized acquisition URL."})
    route_family: str = field(metadata={"doc": "Route family used or suppressed."})
    route_policy_version: str = field(
        metadata={"doc": "Configured route policy version."}
    )
    source_policy_compatibility_hash: str = field(
        metadata={"doc": "Hash of suppression-compatible route policy inputs."}
    )
    started_at_utc: str = field(metadata={"doc": "UTC attempt start timestamp."})
    completed_at_utc: str = field(metadata={"doc": "UTC terminal timestamp."})
    elapsed_ms: int = field(
        metadata={"doc": "Non-negative measured elapsed milliseconds."}
    )
    terminal_outcome: str = field(metadata={"doc": "success, failed, or suppressed."})
    browser_launches: int = field(
        default=0, metadata={"doc": "Observed browser launches."}
    )
    browser_steps: int = field(
        default=0, metadata={"doc": "Observed structured browser steps."}
    )
    page_navigations: int = field(
        default=0, metadata={"doc": "Observed page navigations."}
    )
    screenshots: int = field(default=0, metadata={"doc": "Observed screenshots."})
    browser_model_calls: int = field(
        default=0, metadata={"doc": "Canonical browser-model call count."}
    )
    input_tokens: int = field(
        default=0, metadata={"doc": "Canonical browser-model input tokens."}
    )
    cached_input_tokens: int = field(
        default=0, metadata={"doc": "Canonical browser-model cached input tokens."}
    )
    output_tokens: int = field(
        default=0, metadata={"doc": "Canonical browser-model output tokens."}
    )
    drive_reads: int = field(
        default=0, metadata={"doc": "Canonical material Drive reads."}
    )
    drive_writes: int = field(default=0, metadata={"doc": "Canonical Drive writes."})
    mailbox_reads: int = field(default=0, metadata={"doc": "Canonical mailbox reads."})
    retry_count: int = field(default=0, metadata={"doc": "Canonical retry attempts."})
    terminal_reason: str = field(
        default="", metadata={"doc": "Typed bounded terminal reason."}
    )
    verified_artifact_hash: str = field(
        default="",
        metadata={"doc": "Verified algorithm-prefixed artifact hash when available."},
    )
    estimated_cost_usd: float = field(
        default=0.0, metadata={"doc": "Canonical estimated browser-model cost in USD."}
    )
    avoided_operations: tuple[str, ...] = field(
        default_factory=tuple,
        metadata={"doc": "Bounded operation names avoided by policy."},
    )
    incomplete_fields: tuple[str, ...] = field(
        default_factory=tuple,
        metadata={
            "doc": "Fields unavailable for this record; never interpreted as zero."
        },
    )
    revalidation_override: bool = field(
        default=False,
        metadata={
            "doc": "Whether an operator explicitly revalidated a suppressed route."
        },
    )


@dataclass(frozen=True)
class AcquisitionAttemptResourceRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Resource-record request schema version."}
    )
    db_path: str = field(metadata={"doc": "Reports SQLite database path."})
    summary: AcquisitionAttemptResourceSummary = field(
        metadata={"doc": "Bounded acquisition resource summary to persist."}
    )


@dataclass(frozen=True)
class AcquisitionAttemptResourceRecordResponse:
    schema_version: str = field(
        metadata={"doc": "Resource-record response schema version."}
    )
    attempt_id: str = field(metadata={"doc": "Persisted attempt identifier."})
    created: bool = field(
        metadata={"doc": "Whether a new resource record was written."}
    )
    superseded_suppression_count: int = field(
        default=0,
        metadata={
            "doc": "Active suppressions superseded by a successful revalidation."
        },
    )


@dataclass(frozen=True)
class AcquisitionResourceAggregateRequest:
    schema_version: str = field(
        metadata={"doc": "Acquisition aggregate request schema version."}
    )
    db_path: str = field(metadata={"doc": "Reports SQLite database path."})
    publisher_id: Optional[str] = field(
        default=None, metadata={"doc": "Optional exact publisher filter."}
    )
    route_family: Optional[str] = field(
        default=None, metadata={"doc": "Optional exact route-family filter."}
    )


@dataclass(frozen=True)
class AcquisitionResourceAggregate:
    schema_version: str = field(
        metadata={"doc": "Acquisition aggregate schema version."}
    )
    publisher_id: str = field(metadata={"doc": "Publisher grouping key."})
    route_family: str = field(metadata={"doc": "Route-family grouping key."})
    sample_size: int = field(metadata={"doc": "Recorded-attempt count."})
    incomplete_record_count: int = field(
        metadata={"doc": "Records with unavailable fields, distinct from zero usage."}
    )
    verified_acquisition_count: int = field(
        metadata={"doc": "Verified successful acquisitions."}
    )
    success_rate: float = field(metadata={"doc": "Verified-acquisition fraction."})
    estimated_cost_usd: float = field(
        metadata={"doc": "Canonical summed estimated cost."}
    )
    cost_per_verified_acquisition_usd: Optional[float] = field(
        metadata={"doc": "Cost per verified acquisition, absent with no successes."}
    )
    median_elapsed_ms: Optional[int] = field(metadata={"doc": "Median elapsed time."})
    p95_elapsed_ms: Optional[int] = field(
        metadata={"doc": "Nearest-rank p95 elapsed time."}
    )
    browser_steps_per_verified_acquisition: Optional[float] = field(
        metadata={"doc": "Browser steps divided by verified acquisitions."}
    )
    terminal_failure_count: int = field(metadata={"doc": "Failed terminal attempts."})
    avoided_browser_launches: int = field(
        metadata={"doc": "Suppression-avoided browser launches."}
    )
    avoided_browser_model_calls: int = field(
        metadata={"doc": "Suppression-avoided browser model calls."}
    )


@dataclass(frozen=True)
class AcquisitionResourceAggregateResponse:
    schema_version: str = field(
        metadata={"doc": "Acquisition aggregate response schema version."}
    )
    aggregates: list[AcquisitionResourceAggregate] = field(
        default_factory=list, metadata={"doc": "Deterministically ordered aggregates."}
    )


@dataclass(frozen=True)
class AcquisitionRouteSuppressionRequest:
    schema_version: str = field(
        metadata={"doc": "Route-suppression evaluation schema version."}
    )
    db_path: str = field(metadata={"doc": "Reports SQLite database path."})
    normalized_url: str = field(metadata={"doc": "Exact normalized source URL."})
    publisher_id: str = field(
        metadata={"doc": "Publisher identifier or bounded empty value."}
    )
    route_family: str = field(metadata={"doc": "Candidate browser route family."})
    policy_version: str = field(metadata={"doc": "Configured policy version."})
    source_policy_compatibility_hash: str = field(
        metadata={"doc": "Hash binding decisions to compatible policy."}
    )
    enabled: bool = field(metadata={"doc": "Whether suppression is currently enabled."})
    minimum_sample_size: int = field(
        metadata={"doc": "Configured sample threshold, at least three."}
    )
    terminal_failure_threshold: float = field(
        metadata={"doc": "Configured terminal failure fraction."}
    )
    terminal_failure_classes: tuple[str, ...] = field(
        metadata={"doc": "Typed terminal reasons eligible for suppression."}
    )
    ttl_seconds: int = field(metadata={"doc": "Configured decision TTL."})
    revalidation_override: bool = field(
        default=False, metadata={"doc": "Explicit operator revalidation override."}
    )
    now_utc: str = field(
        default="",
        metadata={"doc": "Optional UTC instant for deterministic evaluation."},
    )


@dataclass(frozen=True)
class AcquisitionRouteSuppressionResponse:
    schema_version: str = field(
        metadata={"doc": "Route-suppression response schema version."}
    )
    suppressed: bool = field(
        metadata={"doc": "Whether browser/provider work must be skipped."}
    )
    decision_id: str = field(
        default="", metadata={"doc": "Durable active decision identifier."}
    )
    reason: str = field(
        default="", metadata={"doc": "Operator-visible bounded decision reason."}
    )
    sample_size: int = field(default=0, metadata={"doc": "Compatible attempt count."})
    terminal_failure_count: int = field(
        default=0, metadata={"doc": "Eligible terminal failures."}
    )
    terminal_failure_rate: float = field(
        default=0.0, metadata={"doc": "Eligible terminal-failure fraction."}
    )
    expires_at_utc: str = field(
        default="", metadata={"doc": "Active decision expiry, if any."}
    )
