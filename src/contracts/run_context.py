from __future__ import annotations

from dataclasses import dataclass, field

from src.contracts.semantic_ids import RunId, SemanticIdContract, TaskId


@dataclass(frozen=True)
class RunContext(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "Run context schema version."})
    run_id: RunId = field(metadata={"doc": "Unique run identifier."})
    task_id: TaskId = field(
        metadata={"doc": "Task identifier for grouping related events."}
    )
    span_id: str = field(metadata={"doc": "Span identifier for a specific operation."})
    trace_id: str = field(
        default="",
        metadata={"doc": "End-to-end trace identifier shared by all spans in one run."},
    )
    parent_span_id: str = field(
        default="",
        metadata={"doc": "Parent span identifier; empty only for the trace root span."},
    )
    span_name: str = field(
        default="",
        metadata={"doc": "Human-readable operation name for trace inspection."},
    )
    span_depth: int = field(
        default=0,
        metadata={"doc": "Zero-based nested depth of this span in the trace tree."},
    )
    producer_commit_sha: str = field(
        default="",
        metadata={
            "doc": "Trusted producer revision supplied by runtime environment, when available."
        },
    )
