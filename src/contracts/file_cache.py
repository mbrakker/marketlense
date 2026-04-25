from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class FileCacheMd5SidecarRecord:
    schema_version: str = field(
        metadata={"doc": "MD5 sidecar payload schema version."}
    )
    file_id: str = field(
        metadata={"doc": "Drive file identifier associated with the cached PDF."}
    )
    name: str = field(
        metadata={"doc": "Display name recorded when the sidecar was written."}
    )
    md5: str = field(metadata={"doc": "Normalized MD5 checksum for the cached PDF."})
    size_bytes: int = field(
        metadata={"doc": "Cached PDF size in bytes at sidecar write time."}
    )
    mtime_utc: int = field(
        metadata={"doc": "Cached PDF modified time rounded to epoch seconds."}
    )


@dataclass(frozen=True)
class FileCacheMd5SidecarResolveRequest:
    schema_version: str = field(
        metadata={"doc": "MD5 sidecar resolve request schema version."}
    )
    cache_path: str = field(
        metadata={"doc": "Cached PDF path whose sidecar should be inspected."}
    )
    file_id: str = field(
        metadata={"doc": "Drive file identifier used for logging and sidecar repair."}
    )
    size_bytes: Optional[int] = field(
        metadata={"doc": "Observed cached PDF size in bytes, if available."}
    )
    mtime_utc: Optional[float] = field(
        metadata={"doc": "Observed cached PDF modified time in epoch seconds, if available."}
    )


@dataclass(frozen=True)
class FileCacheMd5SidecarResolveResponse:
    schema_version: str = field(
        metadata={"doc": "MD5 sidecar resolve response schema version."}
    )
    cache_path: str = field(
        metadata={"doc": "Cached PDF path whose sidecar was inspected."}
    )
    sidecar_path: str = field(metadata={"doc": "Resolved .md5.json sidecar path."})
    sidecar_exists: bool = field(
        metadata={"doc": "Whether the sidecar file existed at inspection time."}
    )
    hit: bool = field(
        metadata={"doc": "True when the sidecar matched the observed file stat."}
    )
    reason: str = field(
        metadata={"doc": "Typed cache-sidecar result reason such as missing or matched."}
    )
    record: Optional[FileCacheMd5SidecarRecord] = field(
        default=None,
        metadata={"doc": "Parsed sidecar record when the payload was structurally valid."},
    )
    resolved_md5: Optional[str] = field(
        default=None,
        metadata={"doc": "MD5 value when the sidecar matches the observed file stat."},
    )


@dataclass(frozen=True)
class FileCacheMd5SidecarWriteRequest:
    schema_version: str = field(
        metadata={"doc": "MD5 sidecar write request schema version."}
    )
    cache_path: str = field(
        metadata={"doc": "Cached PDF path whose sidecar should be written."}
    )
    file_id: str = field(
        metadata={"doc": "Drive file identifier associated with the cached PDF."}
    )
    file_name: Optional[str] = field(
        default=None,
        metadata={"doc": "Display name recorded inside the sidecar payload."},
    )
    md5: Optional[str] = field(
        default=None,
        metadata={"doc": "Normalized or normalizable MD5 checksum to persist."},
    )
    size_bytes: Optional[int] = field(
        default=None,
        metadata={"doc": "Cached PDF size in bytes at write time."},
    )
    mtime_utc: Optional[float] = field(
        default=None,
        metadata={"doc": "Cached PDF modified time in epoch seconds at write time."},
    )


@dataclass(frozen=True)
class FileCacheMd5SidecarWriteResponse:
    schema_version: str = field(
        metadata={"doc": "MD5 sidecar write response schema version."}
    )
    cache_path: str = field(
        metadata={"doc": "Cached PDF path whose sidecar write was attempted."}
    )
    sidecar_path: str = field(metadata={"doc": "Resolved .md5.json sidecar path."})
    written: bool = field(
        metadata={"doc": "True when the sidecar was written to disk."}
    )
    reason: str = field(
        metadata={"doc": "Typed write result reason such as written or incomplete_metadata."}
    )
    record: Optional[FileCacheMd5SidecarRecord] = field(
        default=None,
        metadata={"doc": "Written sidecar record when persistence succeeded."},
    )
