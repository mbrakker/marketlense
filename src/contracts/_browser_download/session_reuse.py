from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class BrowserDownloadSessionReusePolicy:
    schema_version: str = field(
        metadata={"doc": "Browser-download session reuse policy schema version."}
    )
    enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether browser-use may reuse a bounded persistent profile for this run."
        },
    )
    mode: str = field(
        default="disabled",
        metadata={
            "doc": "Reuse mode: `disabled`, `developer_canary`, or `same_publisher_batch`."
        },
    )
    session_key: str = field(
        default="",
        metadata={"doc": "Explicit caller-provided key for the reusable browser profile."},
    )
    publisher_scope: str = field(
        default="",
        metadata={
            "doc": "Publisher/domain scope allowed to use this session key."
        },
    )
    ttl_seconds: float = field(
        default=0.0,
        metadata={
            "doc": "Maximum age in seconds before the reusable browser profile expires."
        },
    )
    base_dir: str = field(
        default="",
        metadata={
            "doc": "Optional root directory for reusable browser profiles; defaults under the configured output directory."
        },
    )
    cleanup_expired: bool = field(
        default=True,
        metadata={"doc": "Whether expired reusable profiles are removed during resolution."},
    )
    allow_cross_publisher: bool = field(
        default=False,
        metadata={
            "doc": "Whether the same session key may be reused across publisher scopes."
        },
    )


@dataclass(frozen=True)
class BrowserDownloadSessionReuseDecision:
    schema_version: str = field(
        metadata={"doc": "Browser-download session reuse decision schema version."}
    )
    enabled: bool = field(metadata={"doc": "Whether reuse was requested."})
    accepted: bool = field(metadata={"doc": "Whether reuse is allowed for this run."})
    mode: str = field(metadata={"doc": "Normalized reuse mode."})
    session_key_hash: str = field(
        metadata={"doc": "Short non-secret hash of the explicit session key."}
    )
    publisher_scope: str = field(metadata={"doc": "Normalized publisher scope."})
    profile_path: str = field(
        metadata={"doc": "Resolved profile directory for this run, if accepted."}
    )
    profile_reused: bool = field(
        metadata={"doc": "Whether the resolved reusable profile already existed and was fresh."}
    )
    ttl_seconds: float = field(metadata={"doc": "Effective TTL in seconds."})
    expires_at_epoch_seconds: float = field(
        metadata={"doc": "Profile expiry timestamp in epoch seconds, or 0 when disabled."}
    )
    cleanup_removed_count: int = field(
        metadata={"doc": "Number of expired reusable profile directories removed."}
    )
    rejection_reason: str = field(
        default="",
        metadata={"doc": "Typed reason reuse was rejected, else empty string."},
    )
