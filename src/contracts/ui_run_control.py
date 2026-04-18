from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.contracts.semantic_ids import RunId, SemanticIdContract


@dataclass(frozen=True)
class ProcessOutputChunk:
    schema_version: str = field(
        metadata={"doc": "Process-output chunk schema version."}
    )
    path: str = field(metadata={"doc": "Output file path that was read."})
    text: str = field(metadata={"doc": "Decoded output text."})
    truncated: bool = field(
        metadata={"doc": "Whether the output was truncated to satisfy the byte budget."}
    )
    size_bytes: int = field(
        metadata={"doc": "Decoded file size in bytes at read time."}
    )


@dataclass(frozen=True)
class UiRunSummary(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run summary schema version."}
    )
    run_id: RunId = field(metadata={"doc": "Unique UI run identifier."})
    run_type: str = field(metadata={"doc": "Stable run type for this workflow."})
    display_name: str = field(
        metadata={"doc": "Human-readable display name for the workflow run."}
    )
    status: str = field(
        metadata={"doc": "Run lifecycle status: queued, running, succeeded, failed, or canceled."}
    )
    created_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the run record was created."}
    )
    started_at_utc: str = field(
        default="",
        metadata={"doc": "UTC timestamp when the worker began executing the run."},
    )
    finished_at_utc: str = field(
        default="",
        metadata={"doc": "UTC timestamp when the run reached a final state."},
    )
    output_path: str = field(
        default="", metadata={"doc": "Path to the persisted worker output log."}
    )
    pid: Optional[int] = field(
        default=None, metadata={"doc": "Worker PID when the run is or was active."}
    )
    exit_code: Optional[int] = field(
        default=None, metadata={"doc": "Worker exit code when the process ended."}
    )
    error_code: str = field(
        default="", metadata={"doc": "Typed AppError code for failed runs."}
    )


@dataclass(frozen=True)
class UiRunRecord(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run record schema version."}
    )
    run_id: RunId = field(metadata={"doc": "Unique UI run identifier."})
    run_type: str = field(metadata={"doc": "Stable run type for this workflow."})
    display_name: str = field(
        metadata={"doc": "Human-readable display name for the workflow run."}
    )
    status: str = field(
        metadata={"doc": "Run lifecycle status: queued, running, succeeded, failed, or canceled."}
    )
    request_payload: dict[str, Any] = field(
        metadata={"doc": "Typed payload values that describe the requested workflow invocation."}
    )
    command: list[str] = field(
        metadata={"doc": "Concrete command used to start the background worker."}
    )
    created_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the run record was created."}
    )
    updated_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the run record was last updated."}
    )
    started_at_utc: str = field(
        default="",
        metadata={"doc": "UTC timestamp when the worker began executing the run."},
    )
    finished_at_utc: str = field(
        default="",
        metadata={"doc": "UTC timestamp when the run reached a final state."},
    )
    output_path: str = field(
        default="", metadata={"doc": "Path to the persisted worker output log."}
    )
    request_path: str = field(
        default="", metadata={"doc": "Path to the serialized worker request JSON."}
    )
    artifact_paths: list[str] = field(
        default_factory=list,
        metadata={"doc": "Artifact file paths produced by the workflow when known."},
    )
    result_summary: dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Workflow-specific summary fields persisted for UI inspection."},
    )
    pid: Optional[int] = field(
        default=None, metadata={"doc": "Worker PID when the run is or was active."}
    )
    exit_code: Optional[int] = field(
        default=None, metadata={"doc": "Worker exit code when the process ended."}
    )
    error_code: str = field(
        default="", metadata={"doc": "Typed AppError code for failed runs."}
    )
    error_message: str = field(
        default="", metadata={"doc": "Human-readable failure detail for failed runs."}
    )


@dataclass(frozen=True)
class UiRunLaunchRequest:
    schema_version: str = field(
        metadata={"doc": "UI-run launch request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    workspace_root: str = field(
        metadata={"doc": "Workspace root used as the worker process current directory."}
    )
    run_type: str = field(metadata={"doc": "Stable run type to launch."})
    display_name: str = field(
        metadata={"doc": "Human-readable display name for the launched run."}
    )
    request_payload: dict[str, Any] = field(
        metadata={"doc": "Typed payload values that describe the requested workflow invocation."}
    )


@dataclass(frozen=True)
class UiRunLaunchResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run launch response schema version."}
    )
    record: UiRunRecord = field(
        metadata={"doc": "Persisted UI-run record created for the launch request."}
    )


@dataclass(frozen=True)
class UiRunPollRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run poll request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    run_id: RunId = field(metadata={"doc": "Run identifier to poll."})
    output_tail_bytes: int = field(
        default=32768,
        metadata={"doc": "Maximum trailing bytes of output log to read for the UI."},
    )


@dataclass(frozen=True)
class UiRunPollResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run poll response schema version."}
    )
    record: UiRunRecord = field(
        metadata={"doc": "Latest persisted run record after poll-time reconciliation."}
    )
    output_chunk: Optional[ProcessOutputChunk] = field(
        default=None,
        metadata={"doc": "Optional trailing worker output chunk for the run."},
    )


@dataclass(frozen=True)
class UiRunCancelRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run cancel request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    run_id: RunId = field(metadata={"doc": "Run identifier to cancel."})


@dataclass(frozen=True)
class UiRunCancelResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run cancel response schema version."}
    )
    record: UiRunRecord = field(
        metadata={"doc": "Updated run record after the cancel request was applied."}
    )
    canceled: bool = field(
        metadata={"doc": "Whether a running worker process was terminated."}
    )


@dataclass(frozen=True)
class UiRunListRequest:
    schema_version: str = field(
        metadata={"doc": "UI-run list request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    statuses: list[str] = field(
        default_factory=list,
        metadata={"doc": "Optional status filter list."},
    )
    limit: int = field(
        default=50, metadata={"doc": "Maximum number of runs to return."}
    )


@dataclass(frozen=True)
class UiRunListResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run list response schema version."}
    )
    records: list[UiRunSummary] = field(
        metadata={"doc": "Matching run summaries sorted newest first."}
    )


@dataclass(frozen=True)
class UiRunWorkerRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run worker request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    run_id: RunId = field(metadata={"doc": "Run identifier to execute."})
    run_type: str = field(metadata={"doc": "Stable run type the worker should execute."})
    request_payload: dict[str, Any] = field(
        metadata={"doc": "Typed payload values that describe the workflow invocation."}
    )


@dataclass(frozen=True)
class UiRunRecordWriteRequest:
    schema_version: str = field(
        metadata={"doc": "UI-run record write request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    record: UiRunRecord = field(metadata={"doc": "Full run record to persist."})


@dataclass(frozen=True)
class UiRunRecordWriteResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run record write response schema version."}
    )
    record: UiRunRecord = field(metadata={"doc": "Persisted run record."})


@dataclass(frozen=True)
class UiRunRecordGetRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run record get request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    run_id: RunId = field(metadata={"doc": "Run identifier to retrieve."})


@dataclass(frozen=True)
class UiRunRecordGetResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run record get response schema version."}
    )
    record: Optional[UiRunRecord] = field(
        default=None, metadata={"doc": "Persisted run record when one exists."}
    )


@dataclass(frozen=True)
class UiRunRecordListRequest:
    schema_version: str = field(
        metadata={"doc": "UI-run record list request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    statuses: list[str] = field(
        default_factory=list,
        metadata={"doc": "Optional status filter list."},
    )
    limit: int = field(
        default=50, metadata={"doc": "Maximum number of runs to return."}
    )


@dataclass(frozen=True)
class UiRunRecordListResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run record list response schema version."}
    )
    records: list[UiRunRecord] = field(
        metadata={"doc": "Matching persisted run records sorted newest first."}
    )


@dataclass(frozen=True)
class ProcessLaunchRequest:
    schema_version: str = field(
        metadata={"doc": "Background-process launch request schema version."}
    )
    command: list[str] = field(
        metadata={"doc": "Concrete command to launch as a background process."}
    )
    cwd: str = field(metadata={"doc": "Working directory for the launched process."})
    output_path: str = field(
        metadata={"doc": "Filesystem path used to capture combined stdout and stderr."}
    )
    env: dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Optional environment overrides merged onto the current process environment."},
    )


@dataclass(frozen=True)
class ProcessLaunchResponse:
    schema_version: str = field(
        metadata={"doc": "Background-process launch response schema version."}
    )
    pid: int = field(metadata={"doc": "PID of the launched background process."})
    command: list[str] = field(
        metadata={"doc": "Concrete command used to launch the process."}
    )
    cwd: str = field(
        metadata={"doc": "Working directory used to launch the process."}
    )
    output_path: str = field(
        metadata={"doc": "Filesystem path capturing combined stdout and stderr."}
    )
    started_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the process launch completed."}
    )


@dataclass(frozen=True)
class ProcessPollRequest:
    schema_version: str = field(
        metadata={"doc": "Background-process poll request schema version."}
    )
    pid: int = field(metadata={"doc": "PID to inspect."})


@dataclass(frozen=True)
class ProcessPollResponse:
    schema_version: str = field(
        metadata={"doc": "Background-process poll response schema version."}
    )
    pid: int = field(metadata={"doc": "PID that was inspected."})
    running: bool = field(metadata={"doc": "Whether the process is still running."})


@dataclass(frozen=True)
class ProcessTerminateRequest:
    schema_version: str = field(
        metadata={"doc": "Background-process terminate request schema version."}
    )
    pid: int = field(metadata={"doc": "PID to terminate."})


@dataclass(frozen=True)
class ProcessTerminateResponse:
    schema_version: str = field(
        metadata={"doc": "Background-process terminate response schema version."}
    )
    pid: int = field(metadata={"doc": "PID that was targeted."})
    terminated: bool = field(
        metadata={"doc": "Whether the process was terminated or was already absent."}
    )


@dataclass(frozen=True)
class ProcessOutputReadRequest:
    schema_version: str = field(
        metadata={"doc": "Process-output read request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path of the output log to read."})
    max_bytes: int = field(
        default=32768,
        metadata={"doc": "Maximum trailing bytes to read from the output log."},
    )


@dataclass(frozen=True)
class ProcessOutputReadResponse:
    schema_version: str = field(
        metadata={"doc": "Process-output read response schema version."}
    )
    chunk: ProcessOutputChunk = field(
        metadata={"doc": "Decoded output chunk for the requested log file."}
    )
