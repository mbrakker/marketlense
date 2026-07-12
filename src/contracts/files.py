from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
class ReadTextFilesRequest:
    schema_version: str = field(
        metadata={"doc": "Read-text-files request schema version."}
    )
    paths: List[str] = field(metadata={"doc": "Filesystem paths to read."})


@dataclass(frozen=True)
class ReadTextFilesResponse:
    schema_version: str = field(
        metadata={"doc": "Read-text-files response schema version."}
    )
    files: List[ReadTextResponse] = field(
        metadata={"doc": "Text files read in request order."}
    )


@dataclass(frozen=True)
class ReadJsonRequest:
    schema_version: str = field(metadata={"doc": "Read JSON request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to read and parse as JSON."})


@dataclass(frozen=True)
class ReadJsonResponse:
    schema_version: str = field(metadata={"doc": "Read JSON response schema version."})
    path: str = field(metadata={"doc": "Filesystem path read."})
    payload: Any = field(metadata={"doc": "Parsed JSON payload."})


@dataclass(frozen=True)
class JsonObjectCacheReadRequest:
    schema_version: str = field(
        metadata={"doc": "JSON object cache read request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path of the JSON cache entry."})


@dataclass(frozen=True)
class JsonObjectCacheReadResponse:
    schema_version: str = field(
        metadata={"doc": "JSON object cache read response schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path inspected."})
    found: bool = field(metadata={"doc": "True when a valid JSON object was loaded."})
    payload: Optional[Dict[str, Any]] = field(
        metadata={"doc": "Loaded JSON object, or null when unavailable."}
    )
    reason: str = field(
        metadata={
            "doc": "Stable load result: loaded, missing, invalid_json, or invalid_type."
        }
    )


@dataclass(frozen=True)
class JsonObjectCacheWriteRequest:
    schema_version: str = field(
        metadata={"doc": "JSON object cache write request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path of the JSON cache entry."})
    payload: Dict[str, Any] = field(metadata={"doc": "JSON object to persist."})


@dataclass(frozen=True)
class JsonObjectCacheWriteResponse:
    schema_version: str = field(
        metadata={"doc": "JSON object cache write response schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path written."})
    bytes_written: int = field(metadata={"doc": "Serialized byte count written."})


@dataclass(frozen=True)
class FileBundleHashRequest:
    schema_version: str = field(
        metadata={"doc": "File bundle hash request schema version."}
    )
    paths: List[str] = field(metadata={"doc": "Ordered filesystem paths to hash."})


@dataclass(frozen=True)
class FileBundleHashResponse:
    schema_version: str = field(
        metadata={"doc": "File bundle hash response schema version."}
    )
    sha256: str = field(metadata={"doc": "Deterministic SHA-256 for the file bundle."})
    file_sha256: Dict[str, str] = field(metadata={"doc": "Per-path SHA-256 digests."})


@dataclass(frozen=True)
class StructuredLogLoadRequest:
    schema_version: str = field(
        metadata={"doc": "Structured-log load request schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path of the log to inspect."})
    max_lines: int = field(
        default=5000,
        metadata={"doc": "Maximum trailing lines to parse."},
    )
    max_bytes: int = field(
        default=2_000_000,
        metadata={"doc": "Maximum trailing bytes to read."},
    )


@dataclass(frozen=True)
class StructuredLogLoadResponse:
    schema_version: str = field(
        metadata={"doc": "Structured-log load response schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path read."})
    events: List[Dict[str, Any]] = field(
        metadata={"doc": "Parsed structured events in source order."}
    )
    truncated: bool = field(
        metadata={"doc": "True when the byte bound omitted leading content."}
    )


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
    size_bytes: Optional[int] = field(
        default=None, metadata={"doc": "File size in bytes when entry is a file."}
    )
    mtime_utc: Optional[float] = field(
        default=None, metadata={"doc": "Modified time (epoch seconds), if available."}
    )


@dataclass(frozen=True)
class ListDirectoryRequest:
    schema_version: str = field(
        metadata={"doc": "List directory request schema version."}
    )
    root_dir: str = field(metadata={"doc": "Root directory to list from."})
    glob_pattern: str = field(
        default="*", metadata={"doc": "Glob pattern used for filtering."}
    )
    recursive: bool = field(
        default=False, metadata={"doc": "Whether to recurse into subdirectories."}
    )
    include_files: bool = field(
        default=True, metadata={"doc": "Include files in the response."}
    )
    include_dirs: bool = field(
        default=False, metadata={"doc": "Include directories in the response."}
    )
    limit: int = field(
        default=500, metadata={"doc": "Maximum number of entries to return."}
    )


@dataclass(frozen=True)
class ListDirectoryResponse:
    schema_version: str = field(
        metadata={"doc": "List directory response schema version."}
    )
    root_dir: str = field(metadata={"doc": "Root directory searched."})
    entries: List[DirectoryEntry] = field(
        metadata={"doc": "Matching directory entries."}
    )


@dataclass(frozen=True)
class DirectoryPatternSpec:
    schema_version: str = field(
        metadata={"doc": "Directory-pattern specification schema version."}
    )
    name: str = field(metadata={"doc": "Stable caller-facing pattern name."})
    root_dir: str = field(metadata={"doc": "Root directory to scan."})
    glob_pattern: str = field(metadata={"doc": "Relative glob pattern to count."})
    recursive: bool = field(
        metadata={"doc": "Whether descendants below root_dir are eligible."}
    )
    include_dirs: bool = field(
        metadata={"doc": "Whether matching directories count alongside files."}
    )


@dataclass(frozen=True)
class DirectoryPatternCountRequest:
    schema_version: str = field(
        metadata={"doc": "Grouped directory-pattern count request version."}
    )
    patterns: List[DirectoryPatternSpec] = field(
        metadata={"doc": "Pattern specifications grouped by the service by root."}
    )
    limit_per_pattern: int = field(
        default=500,
        metadata={"doc": "Maximum count reported for each pattern."},
    )


@dataclass(frozen=True)
class DirectoryPatternCountRow:
    schema_version: str = field(
        metadata={"doc": "Directory-pattern count row schema version."}
    )
    name: str = field(metadata={"doc": "Pattern name from the request."})
    root_dir: str = field(metadata={"doc": "Root directory scanned."})
    count: int = field(metadata={"doc": "Bounded matching entry count."})
    error: str = field(
        default="",
        metadata={"doc": "Sanitized listing error, empty on success."},
    )


@dataclass(frozen=True)
class DirectoryPatternCountResponse:
    schema_version: str = field(
        metadata={"doc": "Grouped directory-pattern count response version."}
    )
    rows: List[DirectoryPatternCountRow] = field(
        metadata={"doc": "Count results in request order."}
    )
    root_walk_count: int = field(metadata={"doc": "Number of distinct roots walked."})


@dataclass(frozen=True)
class FileExistsRequest:
    schema_version: str = field(metadata={"doc": "File exists request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to check."})


@dataclass(frozen=True)
class FileExistsResponse:
    schema_version: str = field(
        metadata={"doc": "File exists response schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path checked."})
    exists: bool = field(metadata={"doc": "True if the file exists."})


@dataclass(frozen=True)
class WriteBytesRequest:
    schema_version: str = field(metadata={"doc": "Write bytes request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to write."})
    content: bytes = field(metadata={"doc": "Binary content to write."})
    make_parents: bool = field(
        default=True, metadata={"doc": "Create parent directories if needed."}
    )


@dataclass(frozen=True)
class WriteBytesResponse:
    schema_version: str = field(
        metadata={"doc": "Write bytes response schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path written."})
    bytes_written: int = field(metadata={"doc": "Number of bytes written."})
    md5: str = field(metadata={"doc": "MD5 checksum of written content."})


@dataclass(frozen=True)
class AppendBytesRequest:
    schema_version: str = field(metadata={"doc": "Append-bytes request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to append."})
    content: bytes = field(metadata={"doc": "Binary content appended atomically under the service lock."})
    make_parents: bool = field(default=True, metadata={"doc": "Create parent directories if needed."})


@dataclass(frozen=True)
class AppendBytesResponse:
    schema_version: str = field(metadata={"doc": "Append-bytes response schema version."})
    path: str = field(metadata={"doc": "Filesystem path appended."})
    bytes_appended: int = field(metadata={"doc": "Number of bytes appended."})
    md5: str = field(metadata={"doc": "MD5 checksum of the appended content."})


@dataclass(frozen=True)
class PipelineStageCheckpoint:
    schema_version: str = field(
        metadata={"doc": "Pipeline checkpoint contract schema version."}
    )
    pipeline_name: str = field(
        metadata={"doc": "Canonical pipeline name that owns this checkpoint."}
    )
    file_id: str = field(metadata={"doc": "Report/source file identifier."})
    report_slug: str = field(
        metadata={"doc": "Report slug used for artifact path layout."}
    )
    stage_name: str = field(
        metadata={"doc": "Semantic stage boundary represented by this checkpoint."}
    )
    stage_status: str = field(
        metadata={"doc": "Checkpointed stage status, usually completed or failed."}
    )
    artifact_refs: Dict[str, str] = field(
        metadata={"doc": "Durable artifact references produced by the stage."}
    )
    payload: Dict[str, Any] = field(
        metadata={"doc": "JSON-serializable semantic state required for restart."}
    )
    completed_at_utc: str = field(
        metadata={"doc": "UTC ISO timestamp when the checkpoint was written."}
    )
    source_run_id: str = field(
        metadata={"doc": "Run identifier that produced the checkpoint."}
    )
    source_task_id: str = field(
        metadata={"doc": "Task identifier that produced the checkpoint."}
    )


@dataclass(frozen=True)
class PipelineCheckpointWriteRequest:
    schema_version: str = field(
        metadata={"doc": "Pipeline checkpoint write request schema version."}
    )
    checkpoint_root: str = field(
        metadata={"doc": "Root directory where pipeline checkpoints are stored."}
    )
    checkpoint: PipelineStageCheckpoint = field(
        metadata={"doc": "Checkpoint payload to persist."}
    )


@dataclass(frozen=True)
class PipelineCheckpointWriteResponse:
    schema_version: str = field(
        metadata={"doc": "Pipeline checkpoint write response schema version."}
    )
    checkpoint_path: str = field(
        metadata={"doc": "Filesystem path where the checkpoint was written."}
    )
    bytes_written: int = field(
        metadata={"doc": "Serialized checkpoint byte count written."}
    )


@dataclass(frozen=True)
class PipelineCheckpointReadRequest:
    schema_version: str = field(
        metadata={"doc": "Pipeline checkpoint read request schema version."}
    )
    checkpoint_root: str = field(
        metadata={"doc": "Root directory where pipeline checkpoints are stored."}
    )
    pipeline_name: str = field(metadata={"doc": "Canonical pipeline name."})
    file_id: str = field(metadata={"doc": "Report/source file identifier."})
    stage_name: str = field(metadata={"doc": "Semantic stage boundary name."})


@dataclass(frozen=True)
class PipelineCheckpointReadResponse:
    schema_version: str = field(
        metadata={"doc": "Pipeline checkpoint read response schema version."}
    )
    checkpoint_path: str = field(
        metadata={"doc": "Filesystem path inspected for the checkpoint."}
    )
    found: bool = field(metadata={"doc": "True when a checkpoint was found."})
    checkpoint: Optional[PipelineStageCheckpoint] = field(
        default=None, metadata={"doc": "Parsed checkpoint when found."}
    )


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
    compute_md5: bool = field(
        default=False, metadata={"doc": "If true, compute the file MD5 hash."}
    )


@dataclass(frozen=True)
class FileStatResponse:
    schema_version: str = field(metadata={"doc": "File stat response schema version."})
    path: str = field(metadata={"doc": "Filesystem path stat'ed."})
    exists: bool = field(metadata={"doc": "True if the path exists."})
    is_file: bool = field(
        default=False,
        metadata={"doc": "True when the existing path is a regular file."},
    )
    is_dir: bool = field(
        default=False,
        metadata={"doc": "True when the existing path is a directory."},
    )
    size_bytes: Optional[int] = field(
        default=None,
        metadata={"doc": "File size in bytes when available."},
    )
    mtime_utc: Optional[float] = field(
        default=None,
        metadata={"doc": "Last modified time (epoch seconds) when available."},
    )
    md5: Optional[str] = field(
        default=None, metadata={"doc": "MD5 checksum when computed."}
    )


@dataclass(frozen=True)
class DeleteFileRequest:
    schema_version: str = field(metadata={"doc": "Delete file request schema version."})
    path: str = field(metadata={"doc": "Filesystem path to delete."})
    missing_ok: bool = field(
        default=True, metadata={"doc": "If true, missing files do not raise errors."}
    )


@dataclass(frozen=True)
class DeleteFileResponse:
    schema_version: str = field(
        metadata={"doc": "Delete file response schema version."}
    )
    path: str = field(metadata={"doc": "Filesystem path deleted."})
    deleted: bool = field(metadata={"doc": "True if the file was deleted."})


@dataclass(frozen=True)
class PdfCacheTextReadRequest:
    schema_version: str = field(
        metadata={"doc": "PDF cache text read request schema version."}
    )
    cache_dir: str = field(
        metadata={"doc": "Root cache directory used by PDF text extraction."}
    )
    md5: str = field(
        metadata={"doc": "PDF MD5 key used under cache_dir/pdf_cache/<md5>/."}
    )


@dataclass(frozen=True)
class PdfCacheTextReadResponse:
    schema_version: str = field(
        metadata={"doc": "PDF cache text read response schema version."}
    )
    text: str = field(
        metadata={"doc": "Cached text content, empty string when missing/unreadable."}
    )
    source_path: str = field(
        default="",
        metadata={"doc": "Path of the cache file used when content is available."},
    )
