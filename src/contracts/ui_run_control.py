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
    schema_version: str = field(metadata={"doc": "UI-run summary schema version."})
    run_id: RunId = field(metadata={"doc": "Unique UI run identifier."})
    run_type: str = field(metadata={"doc": "Stable run type for this workflow."})
    display_name: str = field(
        metadata={"doc": "Human-readable display name for the workflow run."}
    )
    status: str = field(
        metadata={
            "doc": "Run lifecycle status: queued, running, succeeded, failed, or canceled."
        }
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
    error_retryable: Optional[bool] = field(
        default=None,
        metadata={"doc": "Whether the recorded failure was retryable when known."},
    )
    error_severity: str = field(
        default="",
        metadata={"doc": "Typed AppError severity for failed runs when known."},
    )


@dataclass(frozen=True)
class UiRunRecord(SemanticIdContract):
    schema_version: str = field(metadata={"doc": "UI-run record schema version."})
    run_id: RunId = field(metadata={"doc": "Unique UI run identifier."})
    run_type: str = field(metadata={"doc": "Stable run type for this workflow."})
    display_name: str = field(
        metadata={"doc": "Human-readable display name for the workflow run."}
    )
    status: str = field(
        metadata={
            "doc": "Run lifecycle status: queued, running, succeeded, failed, or canceled."
        }
    )
    request_payload: dict[str, Any] = field(
        metadata={
            "doc": "Typed payload values that describe the requested workflow invocation."
        }
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
        metadata={
            "doc": "Workflow-specific summary fields persisted for UI inspection."
        },
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
    error_retryable: Optional[bool] = field(
        default=None,
        metadata={"doc": "Whether the recorded failure was retryable when known."},
    )
    error_severity: str = field(
        default="",
        metadata={"doc": "Typed AppError severity for failed runs when known."},
    )


@dataclass(frozen=True)
class UiRunDeadLetterErrorTaxonomy:
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter error taxonomy schema version."}
    )
    error_code: str = field(
        metadata={"doc": "Typed AppError code associated with the failed run."}
    )
    error_message: str = field(
        metadata={"doc": "Human-readable failure detail associated with the run."}
    )
    retryable: bool = field(
        metadata={"doc": "Whether the underlying failure was retryable."}
    )
    severity: str = field(
        metadata={"doc": "Typed AppError severity for the failed run."}
    )
    stage: str = field(
        metadata={"doc": "Stable workflow stage inferred for dead-letter triage."}
    )


@dataclass(frozen=True)
class UiRunDeadLetterIdentity:
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter identity schema version."}
    )
    publisher_name: str = field(
        default="",
        metadata={"doc": "Publisher display name when one can be inferred."},
    )
    publisher_insights_url: str = field(
        default="",
        metadata={"doc": "Publisher insights URL when one can be inferred."},
    )
    report_url: str = field(
        default="",
        metadata={"doc": "Report or landing-page URL when one can be inferred."},
    )


@dataclass(frozen=True)
class UiRunDeadLetterArtifactLinks:
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter artifact-link schema version."}
    )
    output_path: str = field(
        default="",
        metadata={"doc": "Worker output log path for the failed run."},
    )
    request_path: str = field(
        default="",
        metadata={"doc": "Serialized worker request path for the failed run."},
    )
    manifest_path: str = field(
        default="",
        metadata={
            "doc": "Replay manifest path captured for the failed run when known."
        },
    )
    artifact_paths: list[str] = field(
        default_factory=list,
        metadata={"doc": "Known artifact paths associated with the failed run."},
    )


@dataclass(frozen=True)
class UiRunDeadLetterRecord(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter record schema version."}
    )
    run_id: RunId = field(
        metadata={"doc": "Failed UI run identifier tracked in the dead-letter ledger."}
    )
    run_type: str = field(
        metadata={"doc": "Stable run type associated with the failed run."}
    )
    display_name: str = field(
        metadata={"doc": "Human-readable workflow name associated with the failed run."}
    )
    run_status: str = field(
        metadata={"doc": "Persisted UI-run status that produced the dead letter."}
    )
    triage_status: str = field(
        metadata={
            "doc": "Dead-letter workflow status: open, recovery_requested, or discarded."
        }
    )
    triage_category: str = field(
        metadata={"doc": "Typed dead-letter category inferred for operator triage."}
    )
    triage_reason: str = field(
        metadata={"doc": "Short human-readable explanation for the triage category."}
    )
    failed_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the run first entered dead-letter state."}
    )
    updated_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the dead-letter record was last updated."}
    )
    error_taxonomy: UiRunDeadLetterErrorTaxonomy = field(
        metadata={"doc": "Structured error taxonomy captured for the failed run."}
    )
    identity: UiRunDeadLetterIdentity = field(
        metadata={"doc": "Publisher/report identity metadata inferred for the run."}
    )
    artifact_links: UiRunDeadLetterArtifactLinks = field(
        metadata={"doc": "Known artifact and evidence links for the failed run."}
    )
    result_summary: dict[str, Any] = field(
        default_factory=dict,
        metadata={"doc": "Workflow-specific summary fields captured before failure."},
    )
    recovery_run_id: str = field(
        default="",
        metadata={"doc": "Replacement run identifier when recovery was requested."},
    )
    last_action: str = field(
        default="",
        metadata={"doc": "Most recent dead-letter action recorded for the run."},
    )
    last_action_note: str = field(
        default="",
        metadata={"doc": "Operator/system note stored with the most recent action."},
    )
    last_action_at_utc: str = field(
        default="",
        metadata={"doc": "UTC timestamp of the most recent dead-letter action."},
    )


@dataclass(frozen=True)
class UiRunDeadLetterActionRecord:
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter action-record schema version."}
    )
    run_id: RunId = field(
        metadata={"doc": "Dead-letter run identifier associated with the action."}
    )
    action: str = field(
        metadata={"doc": "Stable dead-letter action name that was recorded."}
    )
    actor: str = field(
        metadata={"doc": "Actor identifier for the action, for example system or ui."}
    )
    created_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the action was recorded."}
    )
    note: str = field(
        default="",
        metadata={"doc": "Optional operator/system note stored with the action."},
    )
    related_run_id: str = field(
        default="",
        metadata={
            "doc": "Replacement run identifier when the action launched a recovery attempt."
        },
    )


@dataclass(frozen=True)
class UiRunFailureClassification:
    schema_version: str = field(
        metadata={"doc": "UI-run failure classification schema version."}
    )
    action: str = field(
        metadata={
            "doc": "Recommended next action: retry_now, retry_later, resume_from_checkpoint, request_credential, cleanup_transient_resource, publish_only_continuation, or mark_permanent."
        }
    )
    reason: str = field(
        metadata={"doc": "Structured human-readable reason for the recommendation."}
    )
    side_effect_warning: str = field(
        metadata={"doc": "Warning about side effects or duplicate-work risk."}
    )
    retryable: bool = field(
        metadata={"doc": "Whether automated retry is considered safe."}
    )
    resume_stage: str = field(
        default="",
        metadata={"doc": "Checkpoint stage to resume from when applicable."},
    )
    suggested_command: str = field(
        default="",
        metadata={"doc": "Operator command or credential action hint when applicable."},
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
        metadata={
            "doc": "Typed payload values that describe the requested workflow invocation."
        }
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
    schema_version: str = field(metadata={"doc": "UI-run poll request schema version."})
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
    failure_classification: Optional[UiRunFailureClassification] = field(
        default=None,
        metadata={"doc": "Recommended failure recovery action for failed runs."},
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
    schema_version: str = field(metadata={"doc": "UI-run list request schema version."})
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
    run_type: str = field(
        metadata={"doc": "Stable run type the worker should execute."}
    )
    request_payload: dict[str, Any] = field(
        metadata={"doc": "Typed payload values that describe the workflow invocation."}
    )


@dataclass(frozen=True)
class UiRunWorkerRequestWriteRequest:
    schema_version: str = field(
        metadata={"doc": "UI-run worker-request persistence schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    worker_request: UiRunWorkerRequest = field(
        metadata={"doc": "Fully populated worker request to persist."}
    )


@dataclass(frozen=True)
class UiRunWorkerRequestWriteResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run worker-request persistence response version."}
    )
    request_path: str = field(
        metadata={"doc": "Resolved filesystem path of the persisted request JSON."}
    )
    worker_request: UiRunWorkerRequest = field(
        metadata={"doc": "Worker request persisted at request_path."}
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
class UiRunDeadLetterListRequest:
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter list request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    triage_statuses: list[str] = field(
        default_factory=list,
        metadata={"doc": "Optional dead-letter triage-status filter list."},
    )
    limit: int = field(
        default=50, metadata={"doc": "Maximum number of dead-letter records to return."}
    )


@dataclass(frozen=True)
class UiRunDeadLetterListResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter list response schema version."}
    )
    records: list[UiRunDeadLetterRecord] = field(
        metadata={"doc": "Matching dead-letter records sorted newest first."}
    )


@dataclass(frozen=True)
class UiRunDeadLetterActionListRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter action-list request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    run_id: RunId = field(
        metadata={"doc": "Dead-letter run identifier whose actions should be listed."}
    )
    limit: int = field(
        default=20, metadata={"doc": "Maximum number of action records to return."}
    )


@dataclass(frozen=True)
class UiRunDeadLetterActionListResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter action-list response schema version."}
    )
    actions: list[UiRunDeadLetterActionRecord] = field(
        metadata={"doc": "Recorded dead-letter actions sorted newest first."}
    )


@dataclass(frozen=True)
class UiRunDeadLetterActionRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter action request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    run_id: RunId = field(metadata={"doc": "Dead-letter run identifier to update."})
    action: str = field(
        metadata={"doc": "Dead-letter action to record: retry_requested or discarded."}
    )
    actor: str = field(
        default="ui",
        metadata={"doc": "Actor label recorded with the action."},
    )
    note: str = field(
        default="",
        metadata={"doc": "Optional operator note recorded with the action."},
    )
    related_run_id: str = field(
        default="",
        metadata={
            "doc": "Replacement run identifier recorded when recovery is requested."
        },
    )


@dataclass(frozen=True)
class UiRunDeadLetterActionResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run dead-letter action response schema version."}
    )
    record: UiRunDeadLetterRecord = field(
        metadata={"doc": "Updated dead-letter record after the action was recorded."}
    )
    action_record: UiRunDeadLetterActionRecord = field(
        metadata={"doc": "Persisted dead-letter action record."}
    )


@dataclass(frozen=True)
class UiRunDeadLetterReapRequest:
    schema_version: str = field(
        metadata={"doc": "Dead-letter reaper request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    workspace_root: str = field(
        metadata={"doc": "Workspace root used for replacement workers."}
    )
    cooldown_seconds: int = field(
        default=300,
        metadata={
            "doc": "Minimum age of an open retryable dead letter before recovery."
        },
    )
    limit: int = field(
        default=10, metadata={"doc": "Maximum recovery launches in one reaper pass."}
    )
    max_recovery_attempts: int = field(
        default=3,
        metadata={
            "doc": "Maximum recovery launches permitted across one replacement chain."
        },
    )
    actor: str = field(
        default="system",
        metadata={"doc": "Actor recorded for automated recovery actions."},
    )


@dataclass(frozen=True)
class UiRunDeadLetterReapResponse:
    schema_version: str = field(
        metadata={"doc": "Dead-letter reaper response schema version."}
    )
    inspected_count: int = field(
        metadata={"doc": "Open dead-letter records inspected."}
    )
    recovered_run_ids: list[RunId] = field(
        metadata={"doc": "Original run IDs that launched one replacement run."}
    )
    held_run_ids: list[RunId] = field(
        metadata={"doc": "Original run IDs intentionally not retried."}
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
        metadata={
            "doc": "Optional environment overrides merged onto the current process environment."
        },
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
    cwd: str = field(metadata={"doc": "Working directory used to launch the process."})
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
