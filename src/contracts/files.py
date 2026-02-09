from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


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
class DirectoryEntry:
    schema_version: str = field(metadata={"doc": "Directory entry schema version."})
    path: str = field(metadata={"doc": "Absolute or relative path to the entry."})
    name: str = field(metadata={"doc": "Base name of the entry."})
    is_dir: bool = field(metadata={"doc": "True when the entry is a directory."})
    size_bytes: Optional[int] = field(default=None, metadata={"doc": "File size in bytes when entry is a file."})
    mtime_utc: Optional[float] = field(default=None, metadata={"doc": "Modified time (epoch seconds), if available."})


@dataclass(frozen=True)
class ListDirectoryRequest:
    schema_version: str = field(metadata={"doc": "List directory request schema version."})
    root_dir: str = field(metadata={"doc": "Root directory to list from."})
    glob_pattern: str = field(default="*", metadata={"doc": "Glob pattern used for filtering."})
    recursive: bool = field(default=False, metadata={"doc": "Whether to recurse into subdirectories."})
    include_files: bool = field(default=True, metadata={"doc": "Include files in the response."})
    include_dirs: bool = field(default=False, metadata={"doc": "Include directories in the response."})
    limit: int = field(default=500, metadata={"doc": "Maximum number of entries to return."})


@dataclass(frozen=True)
class ListDirectoryResponse:
    schema_version: str = field(metadata={"doc": "List directory response schema version."})
    root_dir: str = field(metadata={"doc": "Root directory searched."})
    entries: List[DirectoryEntry] = field(metadata={"doc": "Matching directory entries."})


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
class FileStatRequest:
    schema_version: str = field(metadata={"doc": "File stat request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to stat."})
    compute_md5: bool = field(default=False, metadata={"doc": "If true, compute the file MD5 hash."})


@dataclass(frozen=True)
class FileStatResponse:
    schema_version: str = field(metadata={"doc": "File stat response schema version."})
    path: str = field(metadata={"doc": "Filesystem path stat'ed."})
    exists: bool = field(metadata={"doc": "True if the path exists."})
    size_bytes: Optional[int] = field(metadata={"doc": "File size in bytes when available."})
    mtime_utc: Optional[float] = field(metadata={"doc": "Last modified time (epoch seconds) when available."})
    md5: Optional[str] = field(default=None, metadata={"doc": "MD5 checksum when computed."})


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
