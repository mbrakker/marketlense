from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunBudget:
    """Explicit limits for one run, UTC day, and publisher scope."""

    schema_version: str = field(metadata={"doc": "Run-budget schema version."})
    run_id: str = field(metadata={"doc": "Stable run identifier governed by this budget."})
    publisher_name: str = field(metadata={"doc": "Publisher scope, or empty for global work."})
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
