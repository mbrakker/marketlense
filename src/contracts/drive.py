from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DriveFile:
    schema_version: str = field(metadata={"doc": "Drive file schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    name: Optional[str] = field(metadata={"doc": "Drive file name, if fetched."})
    modified_time: Optional[str] = field(metadata={"doc": "Drive modified time, if available."})
    md5_checksum: Optional[str] = field(metadata={"doc": "Drive MD5 checksum, if provided."})


@dataclass(frozen=True)
class DriveListRequest:
    schema_version: str = field(metadata={"doc": "Drive list request schema version."})
    folder_id: str = field(metadata={"doc": "Drive folder ID to list PDFs from."})
    service_account_path: str = field(metadata={"doc": "Filesystem path to the Google service account JSON."})
    page_size: Optional[int] = field(default=None, metadata={"doc": "Optional page size for Drive list calls."})
    order_by: Optional[str] = field(default=None, metadata={"doc": "Optional orderBy for Drive list calls."})
    modified_after: Optional[str] = field(default=None, metadata={"doc": "Optional modifiedTime lower bound (RFC3339)."})
    list_mode: str = field(default="full", metadata={"doc": "List mode: full or metadata."})
    supports_all_drives: bool = field(default=True, metadata={"doc": "Whether to set supportsAllDrives on list calls."})
    include_items_from_all_drives: bool = field(default=True, metadata={"doc": "Whether to includeItemsFromAllDrives on list calls."})
    drive_id: Optional[str] = field(default=None, metadata={"doc": "Optional shared Drive ID for corpora=drive scope."})


@dataclass(frozen=True)
class DriveFileMetadataRequest:
    schema_version: str = field(metadata={"doc": "Drive file metadata request schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    service_account_path: str = field(metadata={"doc": "Filesystem path to the Google service account JSON."})


@dataclass(frozen=True)
class DriveFileMetadataResponse:
    schema_version: str = field(metadata={"doc": "Drive file metadata response schema version."})
    file: DriveFile = field(metadata={"doc": "Drive file metadata."})


@dataclass(frozen=True)
class DriveDownloadRequest:
    schema_version: str = field(metadata={"doc": "Drive download request schema version."})
    file: DriveFile = field(metadata={"doc": "Drive file to download."})
    service_account_path: str = field(metadata={"doc": "Filesystem path to the Google service account JSON."})


@dataclass(frozen=True)
class DriveDownloadResponse:
    schema_version: str = field(metadata={"doc": "Drive download response schema version."})
    file: DriveFile = field(metadata={"doc": "Drive file metadata."})
    content: bytes = field(metadata={"doc": "Downloaded file bytes."})
    md5: Optional[str] = field(metadata={"doc": "MD5 checksum of the downloaded content."})
    size: int = field(metadata={"doc": "Size of the downloaded content in bytes."})


@dataclass(frozen=True)
class DriveDownloadToPathRequest:
    schema_version: str = field(metadata={"doc": "Drive download-to-path request schema version."})
    file: DriveFile = field(metadata={"doc": "Drive file to download."})
    service_account_path: str = field(metadata={"doc": "Filesystem path to the Google service account JSON."})
    output_path: str = field(metadata={"doc": "Filesystem path to write the downloaded PDF."})
    make_parents: bool = field(default=True, metadata={"doc": "Create parent directories if needed."})


@dataclass(frozen=True)
class DriveDownloadToPathResponse:
    schema_version: str = field(metadata={"doc": "Drive download-to-path response schema version."})
    file: DriveFile = field(metadata={"doc": "Drive file metadata."})
    output_path: str = field(metadata={"doc": "Filesystem path written."})
    md5: Optional[str] = field(metadata={"doc": "MD5 checksum of the downloaded content."})
    size: int = field(metadata={"doc": "Size of the downloaded content in bytes."})
