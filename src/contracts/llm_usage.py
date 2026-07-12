from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.contracts.semantic_ids import RunId, SemanticIdContract, TaskId


@dataclass(frozen=True)
class LLMUsageLedgerEntry(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "LLM usage ledger entry schema version."}
    )
    timestamp_utc: str = field(
        metadata={"doc": "UTC timestamp when provider usage was observed."}
    )
    provider: str = field(
        metadata={
            "doc": "Model provider that returned usage, e.g. openai or openrouter."
        }
    )
    action: str = field(
        metadata={"doc": "Application action or model-call step that consumed tokens."}
    )
    run_id: RunId = field(
        metadata={"doc": "Run identifier associated with the provider call."}
    )
    task_id: TaskId = field(
        metadata={"doc": "Task identifier associated with the provider call."}
    )
    span_id: str = field(
        metadata={"doc": "Span identifier associated with the provider call."}
    )
    trace_id: str = field(
        metadata={"doc": "Trace identifier associated with the provider call."}
    )
    model: str = field(metadata={"doc": "Provider model identifier used for the call."})
    request_id: Optional[str] = field(
        metadata={"doc": "Provider response/request identifier, if available."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher context for the call, if known."}
    )
    report_name: str = field(metadata={"doc": "Report context for the call, if known."})
    source_url: str = field(
        metadata={"doc": "Source/report URL context for the call, if known."}
    )
    input_tokens: int = field(
        metadata={"doc": "Input tokens reported by the provider, or 0 if unavailable."}
    )
    output_tokens: int = field(
        metadata={"doc": "Output tokens reported by the provider, or 0 if unavailable."}
    )
    total_tokens: int = field(
        metadata={
            "doc": (
                "Total tokens reported by the provider, or derived from input/output."
            )
        }
    )
    cached_input_tokens: Optional[int] = field(
        metadata={"doc": "Cached input tokens reported by the provider, if available."}
    )
    tool_calls: int = field(
        metadata={"doc": "Tool calls reported or billed for the provider call."}
    )
    estimated_cost_usd: float = field(
        metadata={"doc": "Estimated USD cost for the call from local pricing."}
    )
    prompt_namespace: str = field(
        metadata={"doc": "Prompt namespace or use-case identifier, if known."}
    )
    prompt_hash: str = field(
        metadata={"doc": "Prompt hash associated with the call, if known."}
    )
    provider_decision: str = field(
        metadata={
            "doc": (
                "Provider routing decision, e.g. openai_primary or openrouter_fallback."
            )
        }
    )
    cache_decision: str = field(
        metadata={"doc": "Semantic cache decision for the call, if known."}
    )
    temperature: Optional[float] = field(
        metadata={"doc": "Sampling temperature used for the call, if configured."}
    )
    seed: Optional[int] = field(
        metadata={"doc": "Seed used for the call, if configured and supported."}
    )
    timeout_seconds: Optional[float] = field(
        metadata={"doc": "Provider request timeout in seconds, if configured."}
    )
    call_ordinal: Optional[int] = field(
        default=None,
        metadata={
            "doc": (
                "Zero-based ordinal that distinguishes provider calls in one run "
                "context. None delegates allocation to the canonical ledger; callers "
                "replaying a call must retain the resolved ordinal."
            )
        },
    )
    provider_call_status: str = field(
        default="completed",
        metadata={"doc": "Provider transport outcome: completed or failed."},
    )
    parse_status: str = field(
        default="not_applicable",
        metadata={
            "doc": "Output parsing outcome: valid, invalid, not_validated, or not_applicable."
        },
    )
    schema_validation_status: str = field(
        default="not_applicable",
        metadata={
            "doc": "Schema validation outcome: valid, invalid, not_validated, or not_applicable."
        },
    )
    error_stage: str = field(
        default="",
        metadata={"doc": "Bounded stage that produced the terminal error, when any."},
    )
    error_code: str = field(
        default="",
        metadata={"doc": "Bounded terminal application error code, when any."},
    )
    metadata: Dict[str, Any] = field(
        default_factory=dict, metadata={"doc": "Additional non-secret usage metadata."}
    )


@dataclass(frozen=True)
class LLMUsageLedgerAppendRequest:
    schema_version: str = field(
        metadata={"doc": "LLM usage ledger append request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "SQLite database path for LLM usage records."}
    )
    entry: LLMUsageLedgerEntry = field(metadata={"doc": "LLM usage record to persist."})


@dataclass(frozen=True)
class LLMUsageLedgerAppendResponse:
    schema_version: str = field(
        metadata={"doc": "LLM usage ledger append response schema version."}
    )
    db_path: str = field(metadata={"doc": "SQLite database path used."})
    row_id: int = field(metadata={"doc": "Inserted SQLite row identifier."})
    event_key: str = field(
        metadata={"doc": "Deterministic idempotency key for this provider usage event."}
    )
    call_ordinal: int = field(
        metadata={"doc": "Resolved call ordinal used in the durable event key."}
    )
    inserted: bool = field(
        metadata={
            "doc": "Whether this call inserted a new event instead of replaying one."
        }
    )
    median_db_path: str = field(
        metadata={"doc": "SQLite database path for derived usage medians."}
    )
    median_rebuild_scheduled: bool = field(
        metadata={"doc": "Whether this write scheduled an asynchronous median rebuild."}
    )
    median_task: str = field(
        metadata={"doc": "Normalized task whose event count was evaluated."}
    )
    median_task_event_count: int = field(
        metadata={"doc": "Current durable source-event count for the normalized task."}
    )
    median_row_count: Optional[int] = field(
        metadata={
            "doc": (
                "Median rows rebuilt synchronously, or None when rebuild is "
                "asynchronous."
            )
        }
    )
    canonical_event_count: int = field(
        metadata={"doc": "Current count of canonical usage events after this write."}
    )
    export_projection_due: bool = field(
        metadata={
            "doc": "Whether this inserted event reached the export projection interval."
        }
    )


@dataclass(frozen=True)
class LLMUsageLedgerOutcomeUpdateRequest:
    schema_version: str = field(
        metadata={"doc": "LLM usage outcome update request schema version."}
    )
    db_path: str = field(metadata={"doc": "SQLite database path for the usage event."})
    event_key: str = field(
        metadata={"doc": "Deterministic key of the event to finalize."}
    )
    parse_status: str = field(
        metadata={"doc": "Final parse outcome for the provider response."}
    )
    schema_validation_status: str = field(
        metadata={"doc": "Final schema-validation outcome for the provider response."}
    )
    error_stage: str = field(
        default="", metadata={"doc": "Bounded terminal error stage, when any."}
    )
    error_code: str = field(
        default="",
        metadata={"doc": "Bounded terminal application error code, when any."},
    )


@dataclass(frozen=True)
class LLMUsageLedgerOutcomeUpdateResponse:
    schema_version: str = field(
        metadata={"doc": "LLM usage outcome update response schema version."}
    )
    db_path: str = field(metadata={"doc": "SQLite database path updated."})
    event_key: str = field(
        metadata={"doc": "Deterministic key of the finalized event."}
    )
    updated: bool = field(
        metadata={"doc": "Whether one durable usage event was updated."}
    )
    export_refreshed: bool = field(
        default=False,
        metadata={
            "doc": "Whether finalization refreshed an already materialized compatibility projection."
        },
    )


@dataclass(frozen=True)
class LLMUsageLedgerReconciliationRequest:
    schema_version: str = field(
        metadata={"doc": "Usage-ledger reconciliation request schema version."}
    )
    db_path: str = field(metadata={"doc": "Canonical SQLite usage ledger path."})
    ledger_path: str = field(metadata={"doc": "Compatibility JSONL usage export path."})
    daily_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Derived daily-rollup path required when repair is requested."
        },
    )
    repair: bool = field(
        default=False,
        metadata={
            "doc": "Whether missing or altered derived exports are rebuilt from SQLite."
        },
    )


@dataclass(frozen=True)
class LLMUsageLedgerReconciliationResponse:
    schema_version: str = field(
        metadata={"doc": "Usage-ledger reconciliation response schema version."}
    )
    db_path: str = field(metadata={"doc": "Canonical SQLite usage ledger path read."})
    ledger_path: str = field(
        metadata={"doc": "Compatibility JSONL usage export path read."}
    )
    sqlite_event_count: int = field(metadata={"doc": "Canonical SQLite event count."})
    export_event_count: int = field(
        metadata={"doc": "Compatibility export event count."}
    )
    sqlite_input_tokens: int = field(
        metadata={"doc": "Canonical SQLite input-token total."}
    )
    export_input_tokens: int = field(
        metadata={"doc": "Compatibility export input-token total."}
    )
    sqlite_output_tokens: int = field(
        metadata={"doc": "Canonical SQLite output-token total."}
    )
    export_output_tokens: int = field(
        metadata={"doc": "Compatibility export output-token total."}
    )
    sqlite_cached_input_tokens: int = field(
        metadata={"doc": "Canonical SQLite cached-input-token total."}
    )
    export_cached_input_tokens: int = field(
        metadata={"doc": "Compatibility export cached-input-token total."}
    )
    sqlite_estimated_cost_usd: float = field(
        metadata={"doc": "Canonical SQLite estimated-cost total."}
    )
    export_estimated_cost_usd: float = field(
        metadata={"doc": "Compatibility export estimated-cost total."}
    )
    matches: bool = field(
        metadata={"doc": "Whether exact integer totals and cost tolerance reconcile."}
    )
    daily_matches: bool = field(
        default=False,
        metadata={"doc": "Whether the derived daily projection matches canonical events."},
    )
    checkpoint_matches: bool = field(
        default=False,
        metadata={"doc": "Whether checkpoint hashes and event boundary match derived files."},
    )
    mismatch_reasons: tuple[str, ...] = field(
        default=(),
        metadata={"doc": "Stable reconciliation mismatch classifications, if any."},
    )
    repaired: bool = field(
        default=False,
        metadata={
            "doc": "Whether reconciliation rebuilt derived exports before matching."
        },
    )


@dataclass(frozen=True)
class LLMUsageExportRebuildRequest:
    schema_version: str = field(
        metadata={"doc": "Canonical usage-export rebuild request schema version."}
    )
    db_path: str = field(metadata={"doc": "Canonical SQLite usage ledger path."})
    ledger_path: str = field(
        metadata={"doc": "Derived compatibility JSONL export path."}
    )
    daily_path: str = field(
        metadata={"doc": "Derived compatibility daily-rollup path."}
    )


@dataclass(frozen=True)
class LLMUsageExportRebuildResponse:
    schema_version: str = field(
        metadata={"doc": "Canonical usage-export rebuild response schema version."}
    )
    db_path: str = field(metadata={"doc": "Canonical SQLite usage ledger path read."})
    ledger_path: str = field(metadata={"doc": "Derived JSONL export path written."})
    daily_path: str = field(metadata={"doc": "Derived daily-rollup path written."})
    event_count: int = field(metadata={"doc": "Canonical event count projected."})
    source_sha256: str = field(
        metadata={"doc": "Stable hash of canonical projected rows."}
    )
    ledger_sha256: str = field(metadata={"doc": "Hash of the JSONL export bytes."})
    daily_sha256: str = field(metadata={"doc": "Hash of the daily-rollup bytes."})
    last_projected_event_id: int = field(
        metadata={"doc": "Highest canonical event ID included in the derived exports."}
    )
    projected_event_count: int = field(
        metadata={"doc": "New canonical events incorporated by this projection."}
    )
    generation_id: int = field(
        default=0,
        metadata={"doc": "Monotonic durable generation assigned to this projection."},
    )


@dataclass(frozen=True)
class LLMUsageProjectionStatusRequest:
    schema_version: str = field(
        metadata={"doc": "Usage projection-status request schema version."}
    )
    db_path: str = field(metadata={"doc": "Canonical SQLite usage ledger path."})
    ledger_path: str = field(metadata={"doc": "Derived compatibility JSONL path."})
    daily_path: str = field(metadata={"doc": "Derived daily-rollup path."})


@dataclass(frozen=True)
class LLMUsageProjectionStatusResponse:
    schema_version: str = field(
        metadata={"doc": "Usage projection-status response schema version."}
    )
    db_path: str = field(metadata={"doc": "Canonical SQLite usage ledger path."})
    latest_event_id: int = field(metadata={"doc": "Latest durable canonical event ID."})
    projected_event_id: int = field(metadata={"doc": "Latest event ID materialized in exports."})
    pending_event_count: int = field(metadata={"doc": "Canonical events not yet materialized."})
    pending_estimated_cost_usd: float = field(
        metadata={"doc": "Estimated cost of canonical events pending materialization."}
    )
    projection_generation_id: int = field(
        metadata={"doc": "Latest durable projection generation, or zero before first projection."}
    )
    last_successful_projection_at_utc: str = field(
        metadata={"doc": "UTC timestamp of the latest successful projection, if any."}
    )
    files_valid: bool = field(
        metadata={"doc": "Whether existing derived files match the durable checkpoint."}
    )


@dataclass(frozen=True)
class LLMUsageSpendGuardrailRequest:
    schema_version: str = field(metadata={"doc": "Spend-guardrail request schema version."})
    db_path: str = field(metadata={"doc": "Canonical SQLite usage ledger path."})
    warn_usd: float = field(metadata={"doc": "UTC daily spend threshold that emits a warning."})
    pause_usd: float | None = field(
        default=None, metadata={"doc": "UTC daily spend threshold that defers new calls."}
    )
    stop_usd: float | None = field(
        default=None, metadata={"doc": "UTC daily spend threshold that hard-stops new calls."}
    )
    overrides_allowed: bool = field(
        default=False, metadata={"doc": "Whether operator overrides may bypass a pause or stop."}
    )


@dataclass(frozen=True)
class LLMUsageSpendGuardrailResponse:
    schema_version: str = field(metadata={"doc": "Spend-guardrail response schema version."})
    day_utc: str = field(metadata={"doc": "UTC day evaluated for canonical spend."})
    canonical_spend_usd: float = field(metadata={"doc": "Canonical spend recorded for the UTC day."})
    warn_usd: float = field(metadata={"doc": "Configured UTC daily warning threshold."})
    decision: str = field(metadata={"doc": "Explicit guardrail decision: allow, warn, pause, or stop."})


@dataclass(frozen=True)
class LLMUsageMedianRebuildRequest:
    schema_version: str = field(
        metadata={"doc": "LLM usage median rebuild request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "SQLite database path for the source LLM usage ledger."}
    )


@dataclass(frozen=True)
class LLMUsageMedianRebuildResponse:
    schema_version: str = field(
        metadata={"doc": "LLM usage median rebuild response schema version."}
    )
    db_path: str = field(metadata={"doc": "SQLite usage ledger path read."})
    median_db_path: str = field(
        metadata={"doc": "SQLite median database path rewritten from the ledger."}
    )
    median_row_count: int = field(
        metadata={"doc": "Number of median rows rebuilt from source usage records."}
    )
