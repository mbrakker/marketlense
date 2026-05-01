from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .runtime import BrowserDownloadRouteStep, DownloadTerminalEvidence

@dataclass(frozen=True)
class FailedAcquisitionForensicsArtifact:
    schema_version: str = field(
        metadata={"doc": "Failed-attempt forensic-artifact schema version."}
    )
    artifact_label: str = field(
        metadata={"doc": "Stable logical label for the captured artifact reference."}
    )
    source_path: str = field(
        metadata={"doc": "Original local artifact path observed during the failed attempt."}
    )
    retention_action: str = field(
        metadata={
            "doc": "Retention action applied to this artifact: `copied`, `metadata_only`, or `missing`."
        }
    )
    persisted_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Persisted forensic-copy path when retention policy copied the artifact."
        },
    )
    size_bytes: Optional[int] = field(
        default=None,
        metadata={"doc": "Persisted artifact size in bytes when a copy exists."},
    )
    md5: Optional[str] = field(
        default=None,
        metadata={"doc": "MD5 checksum of the persisted forensic artifact copy when available."},
    )


@dataclass(frozen=True)
class FailedAcquisitionForensicsPack:
    schema_version: str = field(
        metadata={"doc": "Failed acquisition forensics-pack schema version."}
    )
    pack_path: str = field(
        metadata={"doc": "Absolute JSON path of the persisted failed-attempt forensic pack."}
    )
    artifact_policy: str = field(
        metadata={"doc": "Retention policy used while persisting the forensic pack."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized landing-page URL for the failed acquisition attempt."}
    )
    source_url: str = field(
        metadata={"doc": "Original source URL for the failed acquisition attempt."}
    )
    attempt_url: str = field(
        metadata={"doc": "Concrete attempt URL used for the failed route-plan step."}
    )
    step_name: str = field(
        metadata={"doc": "Route-plan step name that failed."}
    )
    route_family: str = field(
        metadata={"doc": "Route family associated with the failed acquisition attempt."}
    )
    error_code: str = field(
        metadata={"doc": "Typed AppError code or synthesized failure code for the failed attempt."}
    )
    error_message: str = field(
        metadata={"doc": "Human-readable failure message for the failed attempt."}
    )
    error_class: str = field(
        metadata={"doc": "Stable failure class used for triage, for example `transient_app_error` or `permanent_app_error`."}
    )
    error_retryable: bool = field(
        metadata={"doc": "Whether the failed attempt was retryable according to the error taxonomy."}
    )
    error_severity: str = field(
        metadata={"doc": "Typed error severity for the failed attempt."}
    )
    route_kind_hint: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional route-kind hint attached to the failed attempt."},
    )
    route_hint: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional remembered route summary used for the failed attempt."},
    )
    route_step_hints: list[BrowserDownloadRouteStep] = field(
        default_factory=list,
        metadata={"doc": "Structured remembered route steps reused by the failed attempt."},
    )
    blocked_reason: Optional[str] = field(
        default=None,
        metadata={"doc": "Typed blocker code recovered from terminal evidence when available."},
    )
    blocked_reason_detail: Optional[str] = field(
        default=None,
        metadata={"doc": "Human-readable blocker detail recovered from terminal evidence when available."},
    )
    terminal_evidence: Optional[DownloadTerminalEvidence] = field(
        default=None,
        metadata={"doc": "Best available terminal evidence snapshot recovered for the failed attempt."},
    )
    artifacts: list[FailedAcquisitionForensicsArtifact] = field(
        default_factory=list,
        metadata={"doc": "Retained forensic artifact references for the failed attempt."},
    )
    failure_context: dict[str, object] = field(
        default_factory=dict,
        metadata={"doc": "Sanitized typed error context persisted with the forensic pack."},
    )

