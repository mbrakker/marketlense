from __future__ import annotations

from dataclasses import field, dataclass
from typing import Any

from src.contracts.semantic_ids import RunId, SemanticIdContract
from src.contracts.ui_run_control import UiRunRecord


@dataclass(frozen=True)
class UiRunArtifactFingerprint:
    schema_version: str = field(
        metadata={"doc": "UI-run artifact fingerprint schema version."}
    )
    path: str = field(
        metadata={"doc": "Normalized filesystem path for the artifact candidate."}
    )
    exists: bool = field(
        metadata={
            "doc": "Whether the artifact existed when the fingerprint was captured."
        }
    )
    size_bytes: int = field(
        metadata={"doc": "Artifact size in bytes when the artifact existed, else zero."}
    )
    sha256: str = field(
        metadata={
            "doc": "SHA-256 digest for the artifact bytes when the artifact existed, else empty."
        }
    )


@dataclass(frozen=True)
class UiRunExecutionResponse(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run execution response schema version."}
    )
    run_id: RunId = field(metadata={"doc": "Run identifier being executed."})
    run_type: str = field(metadata={"doc": "Stable run type that was executed."})
    status: str = field(
        metadata={
            "doc": "Execution status for the worker payload: succeeded or failed."
        }
    )
    result_summary: dict[str, Any] = field(
        metadata={
            "doc": "Workflow-specific summary fields produced by the execution attempt."
        }
    )
    artifact_paths: list[str] = field(
        metadata={"doc": "Artifact paths produced by the execution attempt when known."}
    )
    config_snapshot: dict[str, Any] = field(
        metadata={
            "doc": "Sanitized deterministic configuration snapshot used for replay gating."
        }
    )
    config_fingerprint: str = field(
        metadata={"doc": "SHA-256 digest of the sanitized configuration snapshot."}
    )
    error_code: str = field(
        default="",
        metadata={"doc": "Typed AppError code when execution failed."},
    )
    error_message: str = field(
        default="",
        metadata={"doc": "Human-readable failure detail when execution failed."},
    )
    error_retryable: bool = field(
        default=False,
        metadata={"doc": "Whether the execution failure was retryable."},
    )
    error_severity: str = field(
        default="error",
        metadata={"doc": "Typed AppError severity when execution failed."},
    )


@dataclass(frozen=True)
class UiRunReplayManifest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run replay manifest schema version."}
    )
    run_id: RunId = field(metadata={"doc": "Original UI run identifier."})
    run_type: str = field(metadata={"doc": "Stable run type recorded for replay."})
    recorded_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the replay manifest was written."}
    )
    status: str = field(
        metadata={"doc": "Original worker terminal status captured in the manifest."}
    )
    request_payload: dict[str, Any] = field(
        metadata={"doc": "Original workflow request payload used by the worker."}
    )
    config_snapshot: dict[str, Any] = field(
        metadata={
            "doc": "Sanitized deterministic configuration snapshot recorded for replay."
        }
    )
    config_fingerprint: str = field(
        metadata={"doc": "SHA-256 digest of the sanitized configuration snapshot."}
    )
    source_tree_root: str = field(
        metadata={"doc": "Root directory used to fingerprint Python source files."}
    )
    source_tree_fingerprint: str = field(
        metadata={
            "doc": "SHA-256 digest for the Python source tree used by the original run."
        }
    )
    prompt_tree_root: str = field(
        metadata={"doc": "Root directory used to fingerprint prompt files."}
    )
    prompt_tree_fingerprint: str = field(
        metadata={"doc": "SHA-256 digest for the prompt tree used by the original run."}
    )
    result_summary: dict[str, Any] = field(
        metadata={"doc": "Original worker result summary for replay diffing."}
    )
    artifact_fingerprints: list[UiRunArtifactFingerprint] = field(
        metadata={
            "doc": "Fingerprints for artifacts recorded by the original worker attempt."
        }
    )
    error_code: str = field(
        default="",
        metadata={"doc": "Typed AppError code recorded for failed original runs."},
    )
    error_message: str = field(
        default="",
        metadata={
            "doc": "Human-readable failure detail recorded for failed original runs."
        },
    )


@dataclass(frozen=True)
class UiRunReplayCaptureRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run replay manifest capture request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    run_id: RunId = field(
        metadata={"doc": "UI run identifier whose manifest should be written."}
    )
    run_type: str = field(
        metadata={"doc": "Stable run type to record in the manifest."}
    )
    status: str = field(
        metadata={"doc": "Worker terminal status being recorded for the original run."}
    )
    recorded_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the replay manifest should be recorded."}
    )
    request_payload: dict[str, Any] = field(
        metadata={"doc": "Original workflow request payload used by the worker."}
    )
    config_snapshot: dict[str, Any] = field(
        metadata={
            "doc": "Sanitized deterministic configuration snapshot used for replay gating."
        }
    )
    config_fingerprint: str = field(
        metadata={"doc": "SHA-256 digest of the sanitized configuration snapshot."}
    )
    source_tree_root: str = field(
        metadata={"doc": "Root directory used to fingerprint Python source files."}
    )
    prompt_tree_root: str = field(
        metadata={"doc": "Root directory used to fingerprint prompt files."}
    )
    artifact_paths: list[str] = field(
        metadata={"doc": "Artifact paths produced by the execution attempt when known."}
    )
    result_summary: dict[str, Any] = field(
        metadata={
            "doc": "Workflow-specific summary fields produced by the execution attempt."
        }
    )
    error_code: str = field(
        default="",
        metadata={"doc": "Typed AppError code when execution failed."},
    )
    error_message: str = field(
        default="",
        metadata={"doc": "Human-readable failure detail when execution failed."},
    )


@dataclass(frozen=True)
class UiRunReplayCaptureResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run replay manifest capture response schema version."}
    )
    manifest_path: str = field(
        metadata={"doc": "Filesystem path where the replay manifest was written."}
    )
    manifest: UiRunReplayManifest = field(
        metadata={"doc": "Persisted replay manifest captured for the original run."}
    )


@dataclass(frozen=True)
class UiRunReplayReadRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run replay manifest read request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    run_id: RunId = field(
        metadata={"doc": "UI run identifier whose replay manifest should be read."}
    )


@dataclass(frozen=True)
class UiRunReplayReadResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run replay manifest read response schema version."}
    )
    manifest_path: str = field(
        metadata={"doc": "Filesystem path where the replay manifest was loaded from."}
    )
    manifest: UiRunReplayManifest = field(
        metadata={"doc": "Loaded replay manifest for the requested UI run."}
    )


@dataclass(frozen=True)
class UiRunArtifactFingerprintRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run artifact fingerprint request schema version."}
    )
    run_id: RunId = field(
        metadata={"doc": "Run identifier used to correlate artifact fingerprint logs."}
    )
    artifact_paths: list[str] = field(
        metadata={
            "doc": "Artifact paths that should be fingerprinted for replay comparison."
        }
    )


@dataclass(frozen=True)
class UiRunArtifactFingerprintResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run artifact fingerprint response schema version."}
    )
    artifact_fingerprints: list[UiRunArtifactFingerprint] = field(
        metadata={"doc": "Fingerprint records for the requested artifact paths."}
    )


@dataclass(frozen=True)
class UiRunWorkspaceFingerprintRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run workspace fingerprint request schema version."}
    )
    run_id: RunId = field(
        metadata={"doc": "Run identifier used to correlate workspace fingerprint logs."}
    )
    source_tree_root: str = field(
        metadata={"doc": "Root directory used to fingerprint Python source files."}
    )
    prompt_tree_root: str = field(
        metadata={"doc": "Root directory used to fingerprint prompt files."}
    )


@dataclass(frozen=True)
class UiRunWorkspaceFingerprintResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run workspace fingerprint response schema version."}
    )
    source_tree_root: str = field(
        metadata={
            "doc": "Resolved root directory used to fingerprint Python source files."
        }
    )
    source_tree_fingerprint: str = field(
        metadata={"doc": "SHA-256 digest for the resolved Python source tree."}
    )
    prompt_tree_root: str = field(
        metadata={"doc": "Resolved root directory used to fingerprint prompt files."}
    )
    prompt_tree_fingerprint: str = field(
        metadata={"doc": "SHA-256 digest for the resolved prompt tree."}
    )


@dataclass(frozen=True)
class UiRunReplayDelta:
    schema_version: str = field(metadata={"doc": "UI-run replay delta schema version."})
    field_name: str = field(
        metadata={
            "doc": "Stable field name being compared between original and replay outputs."
        }
    )
    matches: bool = field(
        metadata={"doc": "Whether the replay value matched the original value exactly."}
    )
    original_value: Any = field(
        metadata={"doc": "Original value recorded for the field being compared."}
    )
    replay_value: Any = field(
        metadata={"doc": "Replay value recorded for the field being compared."}
    )


@dataclass(frozen=True)
class UiRunReplayReport(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run replay report schema version."}
    )
    run_id: RunId = field(
        metadata={"doc": "Original UI run identifier being replayed."}
    )
    replayed_at_utc: str = field(
        metadata={
            "doc": "UTC timestamp when the replay finished and the report was generated."
        }
    )
    replay_status: str = field(
        metadata={
            "doc": "Terminal replay status after the deterministic replay attempt."
        }
    )
    source_fingerprint_match: bool = field(
        metadata={
            "doc": "Whether the current Python source tree matched the original manifest fingerprint."
        }
    )
    prompt_fingerprint_match: bool = field(
        metadata={
            "doc": "Whether the current prompt tree matched the original manifest fingerprint."
        }
    )
    config_fingerprint_match: bool = field(
        metadata={
            "doc": "Whether the current sanitized configuration snapshot matched the original manifest fingerprint."
        }
    )
    deltas: list[UiRunReplayDelta] = field(
        metadata={
            "doc": "Field-by-field output comparisons between the original run and the replay attempt."
        }
    )
    matched: bool = field(
        metadata={
            "doc": "Whether the replay matched the original environment gates and output deltas exactly."
        }
    )


@dataclass(frozen=True)
class UiRunReplayReportWriteRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run replay report write request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    run_id: RunId = field(
        metadata={"doc": "Original UI run identifier being replayed."}
    )
    report: UiRunReplayReport = field(
        metadata={"doc": "Replay report payload to persist for the requested run."}
    )


@dataclass(frozen=True)
class UiRunReplayReportWriteResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run replay report write response schema version."}
    )
    report_path: str = field(
        metadata={"doc": "Filesystem path where the replay report was written."}
    )
    report: UiRunReplayReport = field(
        metadata={"doc": "Persisted replay report payload for the requested run."}
    )


@dataclass(frozen=True)
class UiRunReplayRequest(SemanticIdContract):
    schema_version: str = field(
        metadata={"doc": "UI-run replay request schema version."}
    )
    registry_path: str = field(
        metadata={"doc": "Filesystem path to the UI-run registry SQLite database."}
    )
    run_id: RunId = field(metadata={"doc": "Original UI run identifier to replay."})


@dataclass(frozen=True)
class UiRunReplayResponse:
    schema_version: str = field(
        metadata={"doc": "UI-run replay response schema version."}
    )
    original_record: UiRunRecord = field(
        metadata={"doc": "Original persisted UI-run record loaded from the registry."}
    )
    manifest_path: str = field(
        metadata={
            "doc": "Filesystem path to the loaded replay manifest for the original run."
        }
    )
    report_path: str = field(
        metadata={
            "doc": "Filesystem path where the replay comparison report was written."
        }
    )
    report: UiRunReplayReport = field(
        metadata={"doc": "Replay comparison report generated for the requested run."}
    )
