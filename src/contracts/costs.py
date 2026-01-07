from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass(frozen=True)
class CostLedgerEntry:
    schema_version: str = field(metadata={"doc": "Cost ledger entry schema version."})
    timestamp_utc: str = field(metadata={"doc": "ISO-8601 UTC timestamp when the call completed."})
    run_id: str = field(metadata={"doc": "Run identifier."})
    task_id: str = field(metadata={"doc": "Task identifier."})
    span_id: str = field(metadata={"doc": "Span identifier for the model call."})
    step_name: str = field(metadata={"doc": "Logical step name, e.g., openai_analyze or rank_candidates."})
    model: str = field(metadata={"doc": "Model ID used for the call."})
    input_tokens: int = field(metadata={"doc": "Number of input tokens billed."})
    output_tokens: int = field(metadata={"doc": "Number of output tokens billed."})
    cached_input_tokens: Optional[int] = field(default=None, metadata={"doc": "Input tokens served from cache, if reported."})
    tool_calls: int = field(default=0, metadata={"doc": "Number of tool calls billed, if any."})
    estimated_cost_usd: float = field(default=0.0, metadata={"doc": "Estimated USD cost for the call."})
    extra: Dict[str, Any] = field(default_factory=dict, metadata={"doc": "Optional additional metadata."})


@dataclass(frozen=True)
class CostLedgerAppendRequest:
    schema_version: str = field(metadata={"doc": "Cost ledger append request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the ledger JSONL file."})
    entry: CostLedgerEntry = field(metadata={"doc": "Ledger entry to append."})


@dataclass(frozen=True)
class CostLedgerAppendResponse:
    schema_version: str = field(metadata={"doc": "Cost ledger append response schema version."})
    path: str = field(metadata={"doc": "Filesystem path to the ledger JSONL file."})


@dataclass(frozen=True)
class DailyCostTotal:
    schema_version: str = field(metadata={"doc": "Daily cost total schema version."})
    date_utc: str = field(metadata={"doc": "UTC date (YYYY-MM-DD)."})
    total_usd: float = field(metadata={"doc": "Total estimated USD cost for the day."})
    input_tokens: int = field(metadata={"doc": "Total input tokens for the day."})
    output_tokens: int = field(metadata={"doc": "Total output tokens for the day."})
    tool_calls: int = field(metadata={"doc": "Total tool calls for the day."})


@dataclass(frozen=True)
class CostRollupRequest:
    schema_version: str = field(metadata={"doc": "Cost rollup request schema version."})
    ledger_path: str = field(metadata={"doc": "Path to the ledger JSONL file."})
    out_path: str = field(metadata={"doc": "Path to write the daily rollup JSON file."})


@dataclass(frozen=True)
class CostRollupResponse:
    schema_version: str = field(metadata={"doc": "Cost rollup response schema version."})
    out_path: str = field(metadata={"doc": "Path to the written rollup JSON file."})
    totals: Dict[str, DailyCostTotal] = field(metadata={"doc": "Aggregated totals keyed by date (YYYY-MM-DD)."})
