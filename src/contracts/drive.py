from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class DriveFile:
    schema_version: str
    file_id: str
    name: str
    modified_time: Optional[str]
    md5_checksum: Optional[str]
    version: Optional[str]


@dataclass(frozen=True)
class DriveListRequest:
    schema_version: str
    folder_id: str


@dataclass(frozen=True)
class DriveDownloadRequest:
    schema_version: str
    file: DriveFile
    cache_dir: str


@dataclass(frozen=True)
class DriveDownloadResponse:
    schema_version: str
    file: DriveFile
    local_path: str
    md5: Optional[str]
