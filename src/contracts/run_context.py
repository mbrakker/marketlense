from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RunContext:
    schema_version: str
    run_id: str
    task_id: str
    span_id: str
