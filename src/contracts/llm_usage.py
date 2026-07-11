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
    median_db_path: str = field(
        metadata={
            "doc": "SQLite database path where usage medians were rebuilt."
        }
    )
    median_row_count: int = field(
        metadata={
            "doc": "Number of per-call-family median rows rebuilt from the ledger."
        }
    )


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
