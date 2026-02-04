from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class DriveFile:
    schema_version: str = field(metadata={"doc": "Drive file schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    name: str = field(metadata={"doc": "Drive file name."})
    modified_time: Optional[str] = field(metadata={"doc": "Drive modified time, if available."})
    md5_checksum: Optional[str] = field(metadata={"doc": "Drive MD5 checksum, if provided."})
    version: Optional[str] = field(metadata={"doc": "Drive file version, if provided."})


@dataclass(frozen=True)
class DriveListRequest:
    schema_version: str = field(metadata={"doc": "Drive list request schema version."})
    folder_id: str = field(metadata={"doc": "Drive folder ID to list PDFs from."})
    service_account_path: str = field(metadata={"doc": "Filesystem path to the Google service account JSON."})


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
