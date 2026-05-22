from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict

from src.contracts.run_context import RunContext


@dataclass(frozen=True)
class ArtifactRenderTask:
    schema_version: str = field(
        metadata={"doc": "Artifact render task contract schema version."}
    )
    step_name: str = field(
        metadata={"doc": "Stable artifact step identifier used for results and logs."}
    )
    namespace: str = field(
        metadata={"doc": "Prompt namespace used to render this artifact step."}
    )
    variables: Dict[str, Any] = field(
        metadata={"doc": "Prompt variables for the artifact step."}
    )
    ctx: RunContext = field(
        metadata={"doc": "Run context scoped to the artifact step execution."}
    )
