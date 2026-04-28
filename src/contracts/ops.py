from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class OpsStorageHealthItem:
    schema_version: str = field(metadata={"doc": "Storage health item schema version."})
    name: str = field(metadata={"doc": "Logical storage target name."})
    path: str = field(metadata={"doc": "Filesystem path of the target."})
    exists: bool = field(metadata={"doc": "Whether the target exists on disk."})
    size_bytes: Optional[int] = field(
        default=None, metadata={"doc": "Size in bytes when available."}
    )
    modified_utc: str = field(
        default="",
        metadata={"doc": "ISO timestamp string for the last modification time."},
    )
    error: str = field(default="", metadata={"doc": "Error message when stat failed."})


@dataclass(frozen=True)
class OpsLockSnapshot:
    schema_version: str = field(metadata={"doc": "Lock snapshot schema version."})
    found: bool = field(metadata={"doc": "Whether an active lock was found."})
    owner_id: str = field(
        default="", metadata={"doc": "Lock owner identifier, if present."}
    )
    pid: Optional[int] = field(
        default=None, metadata={"doc": "Owner process id, if present."}
    )
    error: str = field(
        default="", metadata={"doc": "Lookup error, if lock inspection failed."}
    )


@dataclass(frozen=True)
class OpsDashboardSnapshotRequest:
    schema_version: str = field(
        metadata={"doc": "Ops snapshot request schema version."}
    )
    output_dir: str = field(metadata={"doc": "Output directory path."})
    cache_dir: str = field(metadata={"doc": "Cache directory path."})
    state_db: str = field(metadata={"doc": "State database path."})
    reports_db: str = field(metadata={"doc": "Reports database path."})
    ingest_lock_path: str = field(metadata={"doc": "Ingest lock file path."})
    processed_limit: int = field(
        default=1000, metadata={"doc": "Maximum processed state rows to retrieve."}
    )
    published_limit: int = field(
        default=1000, metadata={"doc": "Maximum published state rows to retrieve."}
    )
    report_limit: int = field(
        default=2000, metadata={"doc": "Maximum report metadata rows to retrieve."}
    )


@dataclass(frozen=True)
class OpsDashboardSnapshotResponse:
    schema_version: str = field(
        metadata={"doc": "Ops snapshot response schema version."}
    )
    reports: List[dict] = field(
        metadata={"doc": "Report metadata rows serialized as dictionaries."}
    )
    processed: List[dict] = field(
        metadata={"doc": "Processed state rows serialized as dictionaries."}
    )
    published: List[dict] = field(
        metadata={"doc": "Published state rows serialized as dictionaries."}
    )
    lock: OpsLockSnapshot = field(metadata={"doc": "Current ingest lock snapshot."})
    storage_health: List[OpsStorageHealthItem] = field(
        metadata={"doc": "Storage and DB stat summary."}
    )
