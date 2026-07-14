from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunBudget:
    """Explicit limits for one run, UTC day, and publisher scope."""

    schema_version: str = field(metadata={"doc": "Run-budget schema version."})
    run_id: str = field(metadata={"doc": "Stable run identifier governed by this budget."})
    publisher_name: str = field(metadata={"doc": "Publisher scope, or empty for global work."})
    usage_db_path: str = field(
        default="./state/llm_usage.sqlite",
        metadata={"doc": "Canonical SQLite ledger for LLM and side-effect budget usage."},
    )
    day_utc: str = field(default="", metadata={"doc": "UTC day scope in YYYY-MM-DD form."})
    max_spend_usd: float | None = field(default=None, metadata={"doc": "Maximum spend before a stop decision."})
    max_tokens: int | None = field(default=None, metadata={"doc": "Maximum token count before a stop decision."})
    max_runtime_seconds: int | None = field(default=None, metadata={"doc": "Maximum elapsed runtime before a stop decision."})
    max_retries: int | None = field(default=None, metadata={"doc": "Maximum retry count before a stop decision."})
    max_browser_launches: int | None = field(default=None, metadata={"doc": "Maximum browser launches before a stop decision."})
    max_drive_writes: int | None = field(default=None, metadata={"doc": "Maximum Drive writes before a stop decision."})
    max_wordpress_writes: int | None = field(default=None, metadata={"doc": "Maximum WordPress writes before a stop decision."})
    max_pdfs: int | None = field(default=None, metadata={"doc": "Maximum PDFs processed before a stop decision."})
    warning_fraction: float = field(default=0.8, metadata={"doc": "Fraction of any configured limit that emits a warn decision."})
    limit_decision: str = field(default="stop", metadata={"doc": "pause, defer, or stop decision applied once a limit is reached."})


@dataclass(frozen=True)
class RunBudgetUsage:
    schema_version: str = field(metadata={"doc": "Run-budget usage schema version."})
    spend_usd: float = field(default=0.0, metadata={"doc": "Observed plus reserved spend."})
    tokens: int = field(default=0, metadata={"doc": "Observed token count."})
    runtime_seconds: int = field(default=0, metadata={"doc": "Elapsed runtime."})
    retries: int = field(default=0, metadata={"doc": "Retry attempts consumed."})
    browser_launches: int = field(default=0, metadata={"doc": "Browser launches consumed."})
    drive_writes: int = field(default=0, metadata={"doc": "Drive writes consumed."})
    wordpress_writes: int = field(default=0, metadata={"doc": "WordPress writes consumed."})
    pdfs: int = field(default=0, metadata={"doc": "PDFs processed."})


@dataclass(frozen=True)
class RunBudgetDecision:
    schema_version: str = field(metadata={"doc": "Run-budget decision schema version."})
    decision: str = field(metadata={"doc": "allow, warn, pause, defer, stop, or override."})
    breached_metrics: list[str] = field(metadata={"doc": "Stable metric names at or above their limit."})
    side_effect_allowed: bool = field(metadata={"doc": "Whether the proposed side effect may start."})
    reason: str = field(metadata={"doc": "Human-readable bounded decision reason."})
    override_actor: str = field(default="", metadata={"doc": "Authorized override actor when used."})
    override_reason: str = field(default="", metadata={"doc": "Authorized override reason when used."})
    proposed_usage: RunBudgetUsage | None = field(default=None, metadata={"doc": "Usage including the requested side effect, when evaluated."})


@dataclass(frozen=True)
class RunBudgetUsageReadRequest:
    """Read canonical budget usage across the governed run, day, and publisher."""

    schema_version: str = field(metadata={"doc": "Usage-read request schema version."})
    budget: RunBudget = field(metadata={"doc": "Budget scopes and canonical ledger path."})


@dataclass(frozen=True)
class RunBudgetUsageReadResponse:
    """Conservative merged usage plus the contributing scope snapshots."""

    schema_version: str = field(metadata={"doc": "Usage-read response schema version."})
    usage: RunBudgetUsage = field(metadata={"doc": "Metric-wise maximum across configured scopes."})
    run_usage: RunBudgetUsage = field(metadata={"doc": "Usage for the exact run identifier."})
    day_usage: RunBudgetUsage = field(metadata={"doc": "Usage for the UTC day."})
    publisher_usage: RunBudgetUsage = field(metadata={"doc": "Usage for the publisher in the UTC day."})
    event_count: int = field(metadata={"doc": "Durable non-LLM side-effect events contributing to the read."})


@dataclass(frozen=True)
class RunBudgetEventAppendRequest:
    """Idempotently persist one completed non-LLM budget side effect."""

    schema_version: str = field(metadata={"doc": "Budget-event request schema version."})
    budget: RunBudget = field(metadata={"doc": "Budget identity and canonical ledger path."})
    event_key: str = field(metadata={"doc": "Stable idempotency key for the completed side effect."})
    metric: str = field(metadata={"doc": "Budget metric consumed by this completed side effect."})
    quantity: int = field(default=1, metadata={"doc": "Positive integer quantity consumed."})
    decision: str = field(default="allow", metadata={"doc": "Pre-side-effect budget decision."})
    override_actor: str = field(default="", metadata={"doc": "Authorized override actor, when used."})
    override_reason: str = field(default="", metadata={"doc": "Authorized override reason, when used."})


@dataclass(frozen=True)
class RunBudgetEventAppendResponse:
    """Durable outcome for a non-LLM budget event write."""

    schema_version: str = field(metadata={"doc": "Budget-event response schema version."})
    event_key: str = field(metadata={"doc": "Stable event idempotency key."})
    inserted: bool = field(metadata={"doc": "Whether this call created a new durable event."})
