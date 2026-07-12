from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BrowserUsageWriterShutdownResponse:
    """Observable accounting-writer shutdown outcome for one browser run."""

    schema_version: str = field(
        metadata={"doc": "Browser usage-writer shutdown response schema version."}
    )
    drained: bool = field(
        metadata={"doc": "Whether every accepted event was written before timeout."}
    )
    written_events: int = field(
        metadata={"doc": "Accepted events handed to canonical accounting successfully."}
    )
    pending_events: int = field(
        metadata={"doc": "Accepted events still pending when shutdown returned."}
    )
    dropped_events: int = field(
        metadata={"doc": "Callback events rejected because intake was closed or full."}
    )
