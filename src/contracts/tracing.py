from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class TraceBuildRequest:
    schema_version: str = field(metadata={"doc": "Trace build request schema version."})
    events: list[dict[str, Any]] = field(
        metadata={"doc": "Structured log event payloads to correlate into spans."}
    )
    trace_id: str = field(
        default="",
        metadata={"doc": "Optional trace identifier filter."},
    )
    run_id: str = field(
        default="",
        metadata={"doc": "Optional run identifier filter when trace_id is unknown."},
    )
    task_id: str = field(
        default="",
        metadata={"doc": "Optional task identifier filter within a trace or run."},
    )


@dataclass(frozen=True)
class TraceSpanSummary:
    schema_version: str = field(metadata={"doc": "Trace span summary schema version."})
    trace_id: str = field(metadata={"doc": "Trace identifier for this span."})
    span_id: str = field(metadata={"doc": "Span identifier."})
    parent_span_id: str = field(metadata={"doc": "Parent span identifier, if any."})
    span_name: str = field(metadata={"doc": "Human-readable span name."})
    span_depth: int = field(metadata={"doc": "Zero-based nested trace depth."})
    task_id: str = field(metadata={"doc": "Task identifier associated with the span."})
    role: str = field(metadata={"doc": "Most recent architectural role seen in span."})
    module: str = field(metadata={"doc": "Most recent module seen in span."})
    event_count: int = field(metadata={"doc": "Number of events in this span."})
    start_utc: str = field(metadata={"doc": "First event timestamp for this span."})
    end_utc: str = field(metadata={"doc": "Last event timestamp for this span."})
    duration_ms: float = field(
        metadata={"doc": "Observed span duration based on first/last event timestamps."}
    )
    child_span_ids: list[str] = field(
        metadata={"doc": "Direct child span identifiers sorted by first event time."}
    )


@dataclass(frozen=True)
class TraceBuildResult:
    schema_version: str = field(metadata={"doc": "Trace build result schema version."})
    trace_id: str = field(metadata={"doc": "Resolved trace identifier."})
    run_id: str = field(metadata={"doc": "Resolved run identifier."})
    task_id: str = field(metadata={"doc": "Resolved task filter, if any."})
    event_count: int = field(metadata={"doc": "Number of events included."})
    span_count: int = field(metadata={"doc": "Number of spans included."})
    root_span_ids: list[str] = field(
        metadata={"doc": "Trace root spans sorted by first event time."}
    )
    spans: list[TraceSpanSummary] = field(
        metadata={"doc": "Span summaries sorted by first event time."}
    )
