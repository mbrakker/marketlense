from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(frozen=True)
class ReadTextRequest:
    schema_version: str = field(metadata={"doc": "Read text request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to read."})


@dataclass(frozen=True)
class ReadTextResponse:
    schema_version: str = field(metadata={"doc": "Read text response schema version."})
    path: str = field(metadata={"doc": "Filesystem path read."})
    content: str = field(metadata={"doc": "Text content."})


@dataclass(frozen=True)
class ReadBytesRequest:
    schema_version: str = field(metadata={"doc": "Read bytes request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to read."})


@dataclass(frozen=True)
class ReadBytesResponse:
    schema_version: str = field(metadata={"doc": "Read bytes response schema version."})
    path: str = field(metadata={"doc": "Filesystem path read."})
    content: bytes = field(metadata={"doc": "Binary content."})


@dataclass(frozen=True)
class ListHtmlRequest:
    schema_version: str = field(metadata={"doc": "List HTML request schema version."})
    root_dir: str = field(metadata={"doc": "Root directory to list HTML files from."})


@dataclass(frozen=True)
class ListHtmlResponse:
    schema_version: str = field(metadata={"doc": "List HTML response schema version."})
    root_dir: str = field(metadata={"doc": "Root directory searched."})
    html_paths: List[str] = field(metadata={"doc": "HTML file paths."})


@dataclass(frozen=True)
class FileExistsRequest:
    schema_version: str = field(metadata={"doc": "File exists request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to check."})


@dataclass(frozen=True)
class FileExistsResponse:
    schema_version: str = field(metadata={"doc": "File exists response schema version."})
    path: str = field(metadata={"doc": "Filesystem path checked."})
    exists: bool = field(metadata={"doc": "True if the file exists."})


@dataclass(frozen=True)
class WriteBytesRequest:
    schema_version: str = field(metadata={"doc": "Write bytes request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to write."})
    content: bytes = field(metadata={"doc": "Binary content to write."})
    make_parents: bool = field(default=True, metadata={"doc": "Create parent directories if needed."})


@dataclass(frozen=True)
class WriteBytesResponse:
    schema_version: str = field(metadata={"doc": "Write bytes response schema version."})
    path: str = field(metadata={"doc": "Filesystem path written."})
    bytes_written: int = field(metadata={"doc": "Number of bytes written."})
    md5: str = field(metadata={"doc": "MD5 checksum of written content."})


@dataclass(frozen=True)
class FileHashRequest:
    schema_version: str = field(metadata={"doc": "File hash request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to hash."})


@dataclass(frozen=True)
class FileHashResponse:
    schema_version: str = field(metadata={"doc": "File hash response schema version."})
    path: str = field(metadata={"doc": "Filesystem path hashed."})
    md5: str = field(metadata={"doc": "MD5 checksum of the file."})


@dataclass(frozen=True)
class DeleteFileRequest:
    schema_version: str = field(metadata={"doc": "Delete file request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to delete."})
    missing_ok: bool = field(default=True, metadata={"doc": "If true, missing files do not raise errors."})


@dataclass(frozen=True)
class DeleteFileResponse:
    schema_version: str = field(metadata={"doc": "Delete file response schema version."})
    path: str = field(metadata={"doc": "Filesystem path deleted."})
    deleted: bool = field(metadata={"doc": "True if the file was deleted."})
