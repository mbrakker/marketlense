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
