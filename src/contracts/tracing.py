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
class TraceDiagnostic:
    schema_version: str = field(metadata={"doc": "Trace diagnostic schema version."})
    code: str = field(metadata={"doc": "Stable diagnostic code."})
    severity: str = field(metadata={"doc": "Diagnostic severity."})
    message: str = field(metadata={"doc": "Human-readable diagnostic message."})
    span_id: str = field(metadata={"doc": "Span associated with the diagnostic."})
    event_index: int = field(metadata={"doc": "Zero-based index in the filtered event list."})
    field_name: str = field(metadata={"doc": "Field associated with the diagnostic."})
    parent_span_id: str = field(
        default="",
        metadata={"doc": "Broken or missing parent span identifier, if applicable."},
    )


@dataclass(frozen=True)
class TraceWorkflowStageSummary:
    schema_version: str = field(
        metadata={"doc": "Trace workflow-stage summary schema version."}
    )
    workflow_name: str = field(metadata={"doc": "Workflow family detected in the trace."})
    span_ids: list[str] = field(
        metadata={"doc": "Span identifiers associated with this workflow."}
    )
    roles_seen: list[str] = field(
        metadata={"doc": "Architectural roles observed for this workflow."}
    )
    module_count: int = field(
        metadata={"doc": "Number of distinct modules observed for this workflow."}
    )
    event_count: int = field(
        metadata={"doc": "Number of events associated with this workflow."}
    )
    has_orchestrator: bool = field(
        metadata={"doc": "True when an orchestrator span is present."}
    )
    has_generator: bool = field(
        metadata={"doc": "True when a generator span is present."}
    )
    has_service: bool = field(metadata={"doc": "True when a service span is present."})
    complete: bool = field(
        metadata={
            "doc": "True when orchestrator, generator, and service roles are all present."
        }
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
    diagnostics: list[TraceDiagnostic] = field(
        default_factory=list,
        metadata={"doc": "Trace integrity diagnostics sorted by event/span order."},
    )
    diagnostic_count: int = field(
        default=0,
        metadata={"doc": "Number of trace integrity diagnostics."},
    )
    valid: bool = field(
        default=True,
        metadata={"doc": "True when no trace integrity diagnostics were found."},
    )
    workflow_stages: list[TraceWorkflowStageSummary] = field(
        default_factory=list,
        metadata={"doc": "Workflow boundary coverage summaries."},
    )
