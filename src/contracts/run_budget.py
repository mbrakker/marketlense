from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunBudgetLimits:
    """Limits for exactly one budget scope.

    The legacy scalar fields on :class:`RunBudget` remain supported while callers
    migrate to explicit run, UTC-day, and publisher scopes.
    """

    schema_version: str = field(
        metadata={"doc": "Scoped budget limits schema version."}
    )
    max_spend_usd: float | None = field(
        default=None, metadata={"doc": "Maximum monetary spend."}
    )
    max_tokens: int | None = field(
        default=None, metadata={"doc": "Maximum provider tokens."}
    )
    max_calls: int | None = field(
        default=None, metadata={"doc": "Maximum chargeable provider calls."}
    )
    max_steps: int | None = field(
        default=None, metadata={"doc": "Maximum metered execution steps."}
    )
    max_runtime_seconds: int | None = field(
        default=None, metadata={"doc": "Maximum elapsed duration."}
    )
    max_retries: int | None = field(
        default=None, metadata={"doc": "Maximum cost-incurring retries."}
    )
    max_browser_launches: int | None = field(
        default=None, metadata={"doc": "Maximum browser launches."}
    )
    max_drive_writes: int | None = field(
        default=None, metadata={"doc": "Maximum Drive writes."}
    )
    max_wordpress_writes: int | None = field(
        default=None, metadata={"doc": "Maximum WordPress writes."}
    )
    max_pdfs: int | None = field(
        default=None, metadata={"doc": "Maximum processed PDFs."}
    )


@dataclass(frozen=True)
class BudgetOverrideContext:
    """An expiry-bound, auditable override request; never an implicit bypass."""

    schema_version: str = field(metadata={"doc": "Override context schema version."})
    actor: str = field(metadata={"doc": "Actor authorizing the override."})
    reason: str = field(metadata={"doc": "Human review reason for the override."})
    scope: str = field(metadata={"doc": "run, day, publisher, or all."})
    expires_at_utc: str = field(metadata={"doc": "UTC ISO-8601 expiry timestamp."})
    policy_version: str = field(
        metadata={"doc": "Policy version reviewed by the actor."}
    )


@dataclass(frozen=True)
class BudgetRequest:
    """One typed pre-side-effect request sent to the canonical budget owner."""

    schema_version: str = field(metadata={"doc": "Budget request schema version."})
    budget: "RunBudget" = field(
        metadata={"doc": "Canonical budget policy and ledger path."}
    )
    run_id: str = field(metadata={"doc": "Run receiving the decision."})
    workflow_id: str = field(metadata={"doc": "Workflow receiving the decision."})
    resource_type: str = field(
        metadata={"doc": "Resource family, for example llm_provider or drive_write."}
    )
    operation: str = field(metadata={"doc": "Stable operation name."})
    publisher_id: str = field(
        default="", metadata={"doc": "Publisher scope when known."}
    )
    report_id: str = field(
        default="", metadata={"doc": "Report or source scope when known."}
    )
    provider: str = field(
        default="", metadata={"doc": "Provider used for historical cost forecasting."}
    )
    model: str = field(
        default="", metadata={"doc": "Model used for historical cost forecasting."}
    )
    prompt_namespace: str = field(
        default="",
        metadata={"doc": "Prompt namespace used for historical cost forecasting."},
    )
    estimated_cost_usd: float | None = field(
        default=None, metadata={"doc": "Forecast monetary cost, when known."}
    )
    estimated_tokens: int = field(
        default=0, metadata={"doc": "Forecast provider token count."}
    )
    estimated_calls: int = field(
        default=0, metadata={"doc": "Forecast provider-call count."}
    )
    estimated_steps: int = field(
        default=0, metadata={"doc": "Forecast metered step count."}
    )
    estimated_writes: int = field(
        default=0, metadata={"doc": "Forecast external-write count."}
    )
    estimated_pdfs: int = field(
        default=0, metadata={"doc": "Forecast PDF-processing count."}
    )
    estimated_duration_seconds: int = field(
        default=0, metadata={"doc": "Forecast duration."}
    )
    forecast_method: str = field(
        default="explicit",
        metadata={"doc": "explicit, historical_median, or unavailable."},
    )
    forecast_confidence: float = field(
        default=0.0, metadata={"doc": "Forecast confidence in [0, 1]."}
    )
    attempt_number: int = field(
        default=0, metadata={"doc": "Zero-based attempt number."}
    )
    idempotency_key: str = field(
        default="", metadata={"doc": "Stable pre-side-effect idempotency key."}
    )
    reservation_ttl_seconds: int = field(
        default=300, metadata={"doc": "Bounded in-flight reservation lifetime."}
    )
    requested_override: BudgetOverrideContext | None = field(
        default=None, metadata={"doc": "Explicit override request, when any."}
    )
    reserve_in_flight: bool = field(
        default=False,
        metadata={"doc": "Whether an allowed forecast reserves capacity atomically."},
    )


@dataclass(frozen=True)
class BudgetDecision:
    """Canonical result for a pre-side-effect budget request."""

    schema_version: str = field(metadata={"doc": "Budget decision schema version."})
    decision: str = field(
        metadata={"doc": "allow, warn, defer, pause, stop, or authorized_override."}
    )
    reason_code: str = field(
        metadata={"doc": "Stable machine-readable decision reason."}
    )
    affected_limit: str = field(
        metadata={"doc": "Scope.metric limit that controlled the decision."}
    )
    current_usage: "RunBudgetUsage" = field(
        metadata={"doc": "Observed canonical usage before the request."}
    )
    reserved_usage: "RunBudgetUsage" = field(
        metadata={"doc": "Active in-flight usage before this request."}
    )
    projected_usage: "RunBudgetUsage" = field(
        metadata={"doc": "Usage after the proposed operation."}
    )
    next_action: str = field(
        metadata={"doc": "Actionable continuation or remediation."}
    )
    policy_version: str = field(metadata={"doc": "Decision policy version."})
    reservation_key: str = field(
        default="", metadata={"doc": "Reservation key used when capacity was held."}
    )
    reservation_created: bool = field(
        default=False, metadata={"doc": "Whether this request created a reservation."}
    )


@dataclass(frozen=True)
class BudgetReservationReconcileRequest:
    """Release a forecast once the canonical provider event records actual use."""

    schema_version: str = field(
        metadata={"doc": "Reservation reconciliation schema version."}
    )
    usage_db_path: str = field(
        metadata={"doc": "Canonical usage-ledger database path."}
    )
    reservation_key: str = field(
        metadata={"doc": "Reservation to reconcile idempotently."}
    )
    actual_cost_usd: float = field(
        default=0.0, metadata={"doc": "Actual canonical cost recorded for the call."}
    )


@dataclass(frozen=True)
class BudgetReservationReconcileResponse:
    schema_version: str = field(
        metadata={"doc": "Reservation reconciliation response schema version."}
    )
    released: bool = field(
        metadata={"doc": "Whether an active reservation was released."}
    )
    forecast_cost_usd: float = field(
        default=0.0, metadata={"doc": "Forecasted cost that was reserved."}
    )
    actual_cost_usd: float = field(
        default=0.0, metadata={"doc": "Actual cost reconciled to canonical usage."}
    )
    forecast_error_usd: float = field(
        default=0.0, metadata={"doc": "Actual minus forecast monetary error."}
    )


@dataclass(frozen=True)
class BudgetAuthorityReport:
    """Derived policy evidence; actual monetary charges remain in LLM usage events."""

    schema_version: str = field(
        metadata={"doc": "Budget authority report schema version."}
    )
    allowed_operations: int = field(
        metadata={"doc": "Allowed or warned budget decisions."}
    )
    deferred_or_stopped_operations: int = field(
        metadata={"doc": "Deferred, paused, or stopped operations."}
    )
    forecast_cost_usd: float = field(
        metadata={"doc": "Forecast cost considered by decisions."}
    )
    actual_cost_usd: float = field(
        metadata={"doc": "Actual reconciled canonical provider cost."}
    )
    avoided_calls: int = field(
        metadata={"doc": "Forecast calls prevented by a denial."}
    )
    avoided_estimated_cost_usd: float = field(
        metadata={"doc": "Forecast spend avoided by a denial."}
    )
    orphaned_reservation_recoveries: int = field(
        metadata={"doc": "Expired unreconciled reservation count."}
    )
    overrides: int = field(metadata={"doc": "Authorized expiry-bound override count."})


@dataclass(frozen=True)
class RunBudget:
    """Explicit limits for one run, UTC day, and publisher scope."""

    schema_version: str = field(metadata={"doc": "Run-budget schema version."})
    run_id: str = field(
        metadata={"doc": "Stable run identifier governed by this budget."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher scope, or empty for global work."}
    )
    usage_db_path: str = field(
        default="./state/llm_usage.sqlite",
        metadata={
            "doc": "Canonical SQLite ledger for LLM and side-effect budget usage."
        },
    )
    projection_ledger_path: str = field(
        default="",
        metadata={
            "doc": "Optional derived JSONL path checked without rebuilding projections."
        },
    )
    projection_daily_path: str = field(
        default="",
        metadata={
            "doc": "Optional derived daily-rollup path checked without rebuilding projections."
        },
    )
    projection_pending_event_threshold: int = field(
        default=50,
        metadata={
            "doc": "Maximum pending canonical events treated as normal accounted lag."
        },
    )
    day_utc: str = field(
        default="", metadata={"doc": "UTC day scope in YYYY-MM-DD form."}
    )
    max_spend_usd: float | None = field(
        default=None, metadata={"doc": "Maximum spend before a stop decision."}
    )
    max_tokens: int | None = field(
        default=None, metadata={"doc": "Maximum token count before a stop decision."}
    )
    max_calls: int | None = field(
        default=None,
        metadata={"doc": "Maximum chargeable provider calls before a stop decision."},
    )
    max_steps: int | None = field(
        default=None,
        metadata={"doc": "Maximum metered execution steps before a stop decision."},
    )
    max_runtime_seconds: int | None = field(
        default=None,
        metadata={"doc": "Maximum elapsed runtime before a stop decision."},
    )
    max_retries: int | None = field(
        default=None, metadata={"doc": "Maximum retry count before a stop decision."}
    )
    max_browser_launches: int | None = field(
        default=None,
        metadata={"doc": "Maximum browser launches before a stop decision."},
    )
    max_drive_writes: int | None = field(
        default=None, metadata={"doc": "Maximum Drive writes before a stop decision."}
    )
    max_wordpress_writes: int | None = field(
        default=None,
        metadata={"doc": "Maximum WordPress writes before a stop decision."},
    )
    max_pdfs: int | None = field(
        default=None, metadata={"doc": "Maximum PDFs processed before a stop decision."}
    )
    warning_fraction: float = field(
        default=0.8,
        metadata={
            "doc": "Fraction of any configured limit that emits a warn decision."
        },
    )
    limit_decision: str = field(
        default="stop",
        metadata={
            "doc": "pause, defer, or stop decision applied once a limit is reached."
        },
    )
    policy_version: str = field(
        default="budget-authority-v2",
        metadata={"doc": "Configuration-controlled budget enforcement policy version."},
    )
    reservation_ttl_seconds: int = field(
        default=300,
        metadata={"doc": "Default bounded TTL for forecast reservations."},
    )
    run_limits: RunBudgetLimits | None = field(
        default=None, metadata={"doc": "Explicit limits for this run scope."}
    )
    day_limits: RunBudgetLimits | None = field(
        default=None, metadata={"doc": "Explicit limits for the UTC-day scope."}
    )
    publisher_limits: RunBudgetLimits | None = field(
        default=None,
        metadata={"doc": "Explicit limits for the publisher UTC-day scope."},
    )


@dataclass(frozen=True)
class RunBudgetUsage:
    schema_version: str = field(metadata={"doc": "Run-budget usage schema version."})
    spend_usd: float = field(
        default=0.0, metadata={"doc": "Observed plus reserved spend."}
    )
    tokens: int = field(default=0, metadata={"doc": "Observed token count."})
    calls: int = field(
        default=0, metadata={"doc": "Observed chargeable provider calls."}
    )
    steps: int = field(default=0, metadata={"doc": "Observed metered execution steps."})
    runtime_seconds: int = field(default=0, metadata={"doc": "Elapsed runtime."})
    retries: int = field(default=0, metadata={"doc": "Retry attempts consumed."})
    browser_launches: int = field(
        default=0, metadata={"doc": "Browser launches consumed."}
    )
    drive_writes: int = field(default=0, metadata={"doc": "Drive writes consumed."})
    wordpress_writes: int = field(
        default=0, metadata={"doc": "WordPress writes consumed."}
    )
    pdfs: int = field(default=0, metadata={"doc": "PDFs processed."})


@dataclass(frozen=True)
class RunBudgetDecision:
    schema_version: str = field(metadata={"doc": "Run-budget decision schema version."})
    decision: str = field(
        metadata={"doc": "allow, warn, pause, defer, stop, or override."}
    )
    breached_metrics: list[str] = field(
        metadata={"doc": "Stable metric names at or above their limit."}
    )
    side_effect_allowed: bool = field(
        metadata={"doc": "Whether the proposed side effect may start."}
    )
    reason: str = field(metadata={"doc": "Human-readable bounded decision reason."})
    override_actor: str = field(
        default="", metadata={"doc": "Authorized override actor when used."}
    )
    override_reason: str = field(
        default="", metadata={"doc": "Authorized override reason when used."}
    )
    proposed_usage: RunBudgetUsage | None = field(
        default=None,
        metadata={"doc": "Usage including the requested side effect, when evaluated."},
    )


@dataclass(frozen=True)
class RunBudgetUsageReadRequest:
    """Read canonical budget usage across the governed run, day, and publisher."""

    schema_version: str = field(metadata={"doc": "Usage-read request schema version."})
    budget: RunBudget = field(
        metadata={"doc": "Budget scopes and canonical ledger path."}
    )


@dataclass(frozen=True)
class RunBudgetUsageReadResponse:
    """Conservative merged usage plus the contributing scope snapshots."""

    schema_version: str = field(metadata={"doc": "Usage-read response schema version."})
    usage: RunBudgetUsage = field(
        metadata={"doc": "Metric-wise maximum across configured scopes."}
    )
    run_usage: RunBudgetUsage = field(
        metadata={"doc": "Usage for the exact run identifier."}
    )
    day_usage: RunBudgetUsage = field(metadata={"doc": "Usage for the UTC day."})
    publisher_usage: RunBudgetUsage = field(
        metadata={"doc": "Usage for the publisher in the UTC day."}
    )
    event_count: int = field(
        metadata={"doc": "Durable non-LLM side-effect events contributing to the read."}
    )
    projection_outcome: str = field(
        default="not_configured",
        metadata={
            "doc": "current, bounded_lag_accounted, fresh_projection_recommended, checkpoint_missing, derived_files_invalid, or not_configured."
        },
    )
    projection_pending_event_count: int = field(
        default=0,
        metadata={
            "doc": "Canonical usage events absent from derived exports but included in the budget read."
        },
    )
    projection_pending_estimated_cost_usd: float = field(
        default=0.0,
        metadata={"doc": "Canonical pending cost included in the budget read."},
    )


@dataclass(frozen=True)
class RunBudgetEventAppendRequest:
    """Idempotently persist one completed non-LLM budget side effect."""

    schema_version: str = field(
        metadata={"doc": "Budget-event request schema version."}
    )
    budget: RunBudget = field(
        metadata={"doc": "Budget identity and canonical ledger path."}
    )
    event_key: str = field(
        metadata={"doc": "Stable idempotency key for the completed side effect."}
    )
    metric: str = field(
        metadata={"doc": "Budget metric consumed by this completed side effect."}
    )
    quantity: int = field(
        default=1, metadata={"doc": "Positive integer quantity consumed."}
    )
    decision: str = field(
        default="allow", metadata={"doc": "Pre-side-effect budget decision."}
    )
    override_actor: str = field(
        default="", metadata={"doc": "Authorized override actor, when used."}
    )
    override_reason: str = field(
        default="", metadata={"doc": "Authorized override reason, when used."}
    )


@dataclass(frozen=True)
class RunBudgetEventAppendResponse:
    """Durable outcome for a non-LLM budget event write."""

    schema_version: str = field(
        metadata={"doc": "Budget-event response schema version."}
    )
    event_key: str = field(metadata={"doc": "Stable event idempotency key."})
    inserted: bool = field(
        metadata={"doc": "Whether this call created a new durable event."}
    )
