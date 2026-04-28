from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Dict, Any, List

from src.contracts.semantic_ids import RunId, SemanticIdContract, TaskId


@dataclass(frozen=True)
class CostLedgerEntry(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Cost ledger entry schema version."})
    timestamp_utc: str = field(
        metadata={"doc": "ISO-8601 UTC timestamp when the call completed."}
    )
    run_id: RunId = field(metadata={"doc": "Run identifier."})
    task_id: TaskId = field(metadata={"doc": "Task identifier."})
    span_id: str = field(metadata={"doc": "Span identifier for the model call."})
    step_name: str = field(
        metadata={"doc": "Logical step name, e.g., openai_analyze or rank_candidates."}
    )
    model: str = field(metadata={"doc": "Model ID used for the call."})
    input_tokens: int = field(metadata={"doc": "Number of input tokens billed."})
    output_tokens: int = field(metadata={"doc": "Number of output tokens billed."})
    cached_input_tokens: Optional[int] = field(
        default=None, metadata={"doc": "Input tokens served from cache, if reported."}
    )
    tool_calls: int = field(
        default=0, metadata={"doc": "Number of tool calls billed, if any."}
    )
    estimated_cost_usd: float = field(
        default=0.0, metadata={"doc": "Estimated USD cost for the call."}
    )
    extra: Dict[str, Any] = field(
        default_factory=dict, metadata={"doc": "Optional additional metadata."}
    )


@dataclass(frozen=True)
class CostLedgerAppendRequest:
    schema_version: str = field(
        metadata={"doc": "Cost ledger append request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to the ledger JSONL file."})
    entry: CostLedgerEntry = field(metadata={"doc": "Ledger entry to append."})


@dataclass(frozen=True)
class CostLedgerAppendResponse:
    schema_version: str = field(
        metadata={"doc": "Cost ledger append response schema version."}
    )
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
    schema_version: str = field(
        metadata={"doc": "Cost rollup response schema version."}
    )
    out_path: str = field(metadata={"doc": "Path to the written rollup JSON file."})
    totals_by_date: Dict[str, DailyCostTotal] = field(
        metadata={"doc": "Aggregated totals keyed by date (YYYY-MM-DD)."}
    )
    totals_by_run: Dict[str, "CostTotals"] = field(
        metadata={"doc": "Aggregated totals keyed by run_id."}
    )
    totals_by_task: Dict[str, "CostTotals"] = field(
        metadata={"doc": "Aggregated totals keyed by task_id."}
    )

    @property
    def totals(self) -> Dict[str, DailyCostTotal]:
        return self.totals_by_date


@dataclass(frozen=True)
class CostTotals:
    schema_version: str = field(metadata={"doc": "Cost totals schema version."})
    total_input_tokens: int = field(
        metadata={"doc": "Sum of input tokens for the scope."}
    )
    total_output_tokens: int = field(
        metadata={"doc": "Sum of output tokens for the scope."}
    )
    total_tool_calls: int = field(metadata={"doc": "Sum of tool calls for the scope."})
    estimated_cost_usd: float = field(
        metadata={"doc": "Estimated USD cost for the scope."}
    )


@dataclass(frozen=True)
class StepCostTotal:
    schema_version: str = field(metadata={"doc": "Step cost total schema version."})
    step_name: str = field(metadata={"doc": "Step name used for cost aggregation."})
    total_input_tokens: int = field(
        metadata={"doc": "Sum of input tokens for this step."}
    )
    total_output_tokens: int = field(
        metadata={"doc": "Sum of output tokens for this step."}
    )
    total_tool_calls: int = field(metadata={"doc": "Sum of tool calls for this step."})
    estimated_cost_usd: float = field(
        metadata={"doc": "Estimated USD cost for this step."}
    )


@dataclass(frozen=True)
class CostReportRequest(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Cost report request schema version."})
    ledger_path: str = field(
        metadata={"doc": "Path to the ledger JSONL file to analyze."}
    )
    date_utc: Optional[str] = field(
        default=None, metadata={"doc": "Optional UTC date (YYYY-MM-DD) filter."}
    )
    run_id: Optional[RunId] = field(
        default=None, metadata={"doc": "Optional run_id filter."}
    )
    top_n: int = field(
        default=5, metadata={"doc": "Number of top-cost steps to return."}
    )


@dataclass(frozen=True)
class CostReportResponse:
    schema_version: str = field(
        metadata={"doc": "Cost report response schema version."}
    )
    filter_type: str = field(
        metadata={"doc": "Filter type applied: 'date' or 'run_id'."}
    )
    filter_value: str = field(metadata={"doc": "Filter value applied."})
    totals: CostTotals = field(metadata={"doc": "Totals for the selected filter."})
    top_steps: List[StepCostTotal] = field(
        metadata={"doc": "Top steps by estimated cost for the filter."}
    )
    matched_entries: int = field(
        metadata={"doc": "Number of ledger entries included in the report."}
    )


@dataclass(frozen=True)
class CostReportingRequest:
    schema_version: str = field(
        metadata={"doc": "Cost reporting orchestrator request schema version."}
    )
    report_request: Optional[CostReportRequest] = field(
        default=None,
        metadata={"doc": "Optional request for filtered cost reporting."},
    )
    rollup_request: Optional[CostRollupRequest] = field(
        default=None,
        metadata={"doc": "Optional request for daily rollup generation."},
    )


@dataclass(frozen=True)
class CostReportingResponse:
    schema_version: str = field(
        metadata={"doc": "Cost reporting orchestrator response schema version."}
    )
    report: Optional[CostReportResponse] = field(
        default=None,
        metadata={"doc": "Generated filtered cost report, when requested."},
    )
    rollup: Optional[CostRollupResponse] = field(
        default=None,
        metadata={"doc": "Generated daily rollup output, when requested."},
    )
