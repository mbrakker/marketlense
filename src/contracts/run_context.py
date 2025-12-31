from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RunContext:
    schema_version: str = field(metadata={"doc": "Run context schema version."})
    run_id: str = field(metadata={"doc": "Unique run identifier."})
    task_id: str = field(metadata={"doc": "Task identifier for grouping related events."})
    span_id: str = field(metadata={"doc": "Span identifier for a specific operation."})
