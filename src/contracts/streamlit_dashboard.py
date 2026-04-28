from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class LogFileDiscoveryRequest:
    schema_version: str = field(
        metadata={"doc": "Log file discovery request schema version."}
    )
    log_dir: str = field(
        metadata={"doc": "Directory that contains structured log files."}
    )
    file_prefix: str = field(
        metadata={"doc": "Log file prefix used for glob filtering."}
    )
    limit: int = field(
        default=100, metadata={"doc": "Maximum number of files to return."}
    )


@dataclass(frozen=True)
class LogFileRecord:
    schema_version: str = field(metadata={"doc": "Log file record schema version."})
    path: str = field(metadata={"doc": "Absolute path to the log file."})
    name: str = field(metadata={"doc": "Base filename."})
    mtime_utc: Optional[float] = field(
        default=None, metadata={"doc": "Last modified timestamp (epoch seconds)."}
    )
    size_bytes: Optional[int] = field(
        default=None, metadata={"doc": "File size in bytes when available."}
    )


@dataclass(frozen=True)
class LogFileDiscoveryResponse:
    schema_version: str = field(
        metadata={"doc": "Log file discovery response schema version."}
    )
    records: list[LogFileRecord] = field(
        metadata={"doc": "Discovered log files sorted by modified time descending."}
    )


@dataclass(frozen=True)
class LogEventLoadRequest:
    schema_version: str = field(
        metadata={"doc": "Log event load request schema version."}
    )
    log_paths: list[str] = field(metadata={"doc": "Log file paths to parse."})
    max_lines_per_file: int = field(
        default=5000,
        metadata={"doc": "Maximum number of trailing lines to parse per file."},
    )


@dataclass(frozen=True)
class LogEventLoadResponse:
    schema_version: str = field(
        metadata={"doc": "Log event load response schema version."}
    )
    events: list[dict[str, Any]] = field(
        metadata={"doc": "Parsed structured events sorted by timestamp ascending."}
    )


@dataclass(frozen=True)
class JsonPayloadReadRequest:
    schema_version: str = field(
        metadata={"doc": "JSON payload read request schema version."}
    )
    path: str = field(metadata={"doc": "Path to JSON file."})


@dataclass(frozen=True)
class JsonPayloadReadResponse:
    schema_version: str = field(
        metadata={"doc": "JSON payload read response schema version."}
    )
    path: str = field(metadata={"doc": "Path that was read."})
    payload: dict[str, Any] | list[Any] | None = field(
        metadata={"doc": "Decoded JSON payload when parse succeeds."}
    )


@dataclass(frozen=True)
class StorageTarget:
    schema_version: str = field(metadata={"doc": "Storage target schema version."})
    name: str = field(metadata={"doc": "Logical target name."})
    path: str = field(metadata={"doc": "Filesystem path to inspect."})


@dataclass(frozen=True)
class StorageHealthRequest:
    schema_version: str = field(
        metadata={"doc": "Storage health request schema version."}
    )
    targets: list[StorageTarget] = field(
        metadata={"doc": "Storage targets to inspect."}
    )


@dataclass(frozen=True)
class StorageHealthRow:
    schema_version: str = field(metadata={"doc": "Storage health row schema version."})
    name: str = field(metadata={"doc": "Logical target name."})
    path: str = field(metadata={"doc": "Filesystem path inspected."})
    exists: bool = field(metadata={"doc": "Whether the path exists."})
    size_bytes: Optional[int] = field(
        default=None, metadata={"doc": "Size in bytes when available."}
    )
    modified_utc: str = field(
        default="", metadata={"doc": "Human-readable UTC modification timestamp."}
    )
    error: str = field(default="", metadata={"doc": "Error message when stat fails."})


@dataclass(frozen=True)
class StorageHealthResponse:
    schema_version: str = field(
        metadata={"doc": "Storage health response schema version."}
    )
    rows: list[StorageHealthRow] = field(metadata={"doc": "Storage health rows."})


@dataclass(frozen=True)
class ValidationArtifactSummaryRequest:
    schema_version: str = field(
        metadata={"doc": "Validation artifact summary request schema version."}
    )
    output_dir: str = field(metadata={"doc": "Output directory root."})
    limit: int = field(
        default=200,
        metadata={"doc": "Maximum number of validation files to summarize."},
    )


@dataclass(frozen=True)
class ValidationArtifactSummaryRow:
    schema_version: str = field(
        metadata={"doc": "Validation artifact summary row schema version."}
    )
    path: str = field(metadata={"doc": "Validation file path."})
    status: str = field(metadata={"doc": "Validation status extracted from payload."})
    severity: str = field(
        metadata={"doc": "Validation severity extracted from payload."}
    )
    chip_level: str = field(
        metadata={"doc": "UI chip level derived from status/severity."}
    )
    modified_utc: str = field(
        default="", metadata={"doc": "Last modified timestamp in UTC string format."}
    )


@dataclass(frozen=True)
class ValidationArtifactSummaryResponse:
    schema_version: str = field(
        metadata={"doc": "Validation artifact summary response schema version."}
    )
    rows: list[ValidationArtifactSummaryRow] = field(
        metadata={"doc": "Validation artifact summary rows."}
    )


@dataclass(frozen=True)
class ReportRowsLoadRequest:
    schema_version: str = field(
        metadata={"doc": "Report row load request schema version."}
    )
    reports_db: str = field(metadata={"doc": "Reports DB path."})


@dataclass(frozen=True)
class ReportRowsLoadResponse:
    schema_version: str = field(
        metadata={"doc": "Report row load response schema version."}
    )
    rows: list[dict[str, Any]] = field(
        metadata={
            "doc": "Serialized report metadata rows sorted by updated_at descending."
        }
    )


@dataclass(frozen=True)
class StateRowsLoadRequest:
    schema_version: str = field(
        metadata={"doc": "State row load request schema version."}
    )
    state_db: str = field(metadata={"doc": "State DB path."})
    kind: str = field(metadata={"doc": "State row kind: processed or published."})
    limit: int = field(
        default=1000, metadata={"doc": "Maximum number of rows to return."}
    )


@dataclass(frozen=True)
class StateRowsLoadResponse:
    schema_version: str = field(
        metadata={"doc": "State row load response schema version."}
    )
    rows: list[dict[str, Any]] = field(metadata={"doc": "Serialized state rows."})


@dataclass(frozen=True)
class LockSnapshotLoadRequest:
    schema_version: str = field(
        metadata={"doc": "Lock snapshot load request schema version."}
    )
    lock_path: str = field(metadata={"doc": "Path to lock file."})


@dataclass(frozen=True)
class LockSnapshot:
    schema_version: str = field(metadata={"doc": "Lock snapshot schema version."})
    found: bool = field(metadata={"doc": "Whether a lock is present."})
    owner_id: str = field(
        default="", metadata={"doc": "Lock owner identifier, when present."}
    )
    pid: Optional[int] = field(
        default=None, metadata={"doc": "Process id of lock owner, when present."}
    )
    error: str = field(
        default="", metadata={"doc": "Error details when lock retrieval fails."}
    )


@dataclass(frozen=True)
class LedgerEntriesLoadRequest:
    schema_version: str = field(
        metadata={"doc": "Ledger entries load request schema version."}
    )
    ledger_path: str = field(metadata={"doc": "Cost ledger file path."})
    limit: int = field(
        default=2000, metadata={"doc": "Maximum number of trailing entries to return."}
    )


@dataclass(frozen=True)
class LedgerEntriesLoadResponse:
    schema_version: str = field(
        metadata={"doc": "Ledger entries load response schema version."}
    )
    entries: list[dict[str, Any]] = field(
        metadata={"doc": "Parsed JSON ledger entries."}
    )


@dataclass(frozen=True)
class DirectoryCountCheck:
    schema_version: str = field(
        metadata={"doc": "Directory count check schema version."}
    )
    name: str = field(metadata={"doc": "Logical check name."})
    root_dir: str = field(metadata={"doc": "Root directory for glob search."})
    glob_pattern: str = field(metadata={"doc": "Glob pattern to count."})
    recursive: bool = field(metadata={"doc": "Whether to recurse into subdirectories."})
    include_dirs: bool = field(
        metadata={"doc": "Whether matches should include directories instead of files."}
    )


@dataclass(frozen=True)
class DirectoryCountsRequest:
    schema_version: str = field(
        metadata={"doc": "Directory count request schema version."}
    )
    checks: list[DirectoryCountCheck] = field(
        metadata={"doc": "Directory count checks to run."}
    )
    limit: int = field(default=5000, metadata={"doc": "Per-check maximum count limit."})


@dataclass(frozen=True)
class DirectoryCountRow:
    schema_version: str = field(metadata={"doc": "Directory count row schema version."})
    name: str = field(metadata={"doc": "Logical check name."})
    root: str = field(metadata={"doc": "Root directory used for the count."})
    count: int = field(metadata={"doc": "Number of matching entries found."})
    error: str = field(
        default="", metadata={"doc": "Error details when listing fails."}
    )


@dataclass(frozen=True)
class DirectoryCountsResponse:
    schema_version: str = field(
        metadata={"doc": "Directory count response schema version."}
    )
    rows: list[DirectoryCountRow] = field(
        metadata={"doc": "Directory count rows for all checks."}
    )
