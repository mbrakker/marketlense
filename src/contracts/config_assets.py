from __future__ import annotations

from dataclasses import field, dataclass
from typing import Any, Optional


@dataclass(frozen=True)
class ConfigAssetReadRequest:
    schema_version: str = field(
        metadata={"doc": "Config-asset read request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to the config asset."})
    format: str = field(
        metadata={"doc": "Asset format: yaml, json, or text."}
    )
    expected_root_type: str = field(
        default="any",
        metadata={"doc": "Optional decoded payload root type: any, mapping, or list."},
    )


@dataclass(frozen=True)
class ConfigAssetReadResponse:
    schema_version: str = field(
        metadata={"doc": "Config-asset read response schema version."}
    )
    path: str = field(metadata={"doc": "Resolved filesystem path that was read."})
    format: str = field(metadata={"doc": "Resolved asset format."})
    content: str = field(metadata={"doc": "Raw file content."})
    payload: dict[str, Any] | list[Any] | None = field(
        metadata={"doc": "Decoded payload for YAML or JSON assets when applicable."}
    )
    root_type: str = field(
        metadata={"doc": "Decoded payload root type: mapping, list, scalar, or none."}
    )
    sha256: str = field(metadata={"doc": "SHA-256 hash of the raw file content."})
    size_bytes: int = field(metadata={"doc": "File size in bytes."})
    modified_utc: Optional[float] = field(
        default=None, metadata={"doc": "Last-modified time in epoch seconds."}
    )


@dataclass(frozen=True)
class ConfigAssetWriteRequest:
    schema_version: str = field(
        metadata={"doc": "Config-asset write request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path to write."})
    format: str = field(
        metadata={"doc": "Asset format: yaml, json, or text."}
    )
    content: str = field(
        metadata={"doc": "Raw content to validate and write."}
    )
    expected_root_type: str = field(
        default="any",
        metadata={"doc": "Optional decoded payload root type: any, mapping, or list."},
    )
    make_backup: bool = field(
        default=True,
        metadata={"doc": "Whether to create a timestamped backup before overwriting."},
    )


@dataclass(frozen=True)
class ConfigAssetWriteResponse:
    schema_version: str = field(
        metadata={"doc": "Config-asset write response schema version."}
    )
    path: str = field(metadata={"doc": "Resolved filesystem path that was written."})
    format: str = field(metadata={"doc": "Resolved asset format."})
    root_type: str = field(
        metadata={"doc": "Decoded payload root type after validation."}
    )
    sha256: str = field(metadata={"doc": "SHA-256 hash of the written raw content."})
    bytes_written: int = field(metadata={"doc": "Number of bytes written to disk."})
    modified_utc: Optional[float] = field(
        default=None, metadata={"doc": "Last-modified time in epoch seconds."}
    )
    backup_path: Optional[str] = field(
        default=None, metadata={"doc": "Backup file path when a backup was created."}
    )
