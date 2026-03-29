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
    mime_type: Optional[str] = field(
        default=None,
        metadata={"doc": "Drive MIME type when fetched."},
    )


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


@dataclass(frozen=True)
class DriveFolderFileListRequest:
    schema_version: str = field(
        metadata={"doc": "Drive folder file-list request schema version."}
    )
    folder_id: str = field(metadata={"doc": "Drive folder ID to list files from."})
    service_account_path: str = field(
        metadata={"doc": "Filesystem path to the Google service account JSON."}
    )
    name_prefix: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional file-name prefix used to filter results."},
    )
    page_size: Optional[int] = field(
        default=None, metadata={"doc": "Optional page size for Drive list calls."}
    )
    order_by: Optional[str] = field(
        default="modifiedTime desc",
        metadata={"doc": "Optional orderBy for Drive list calls."},
    )
    supports_all_drives: bool = field(
        default=True,
        metadata={"doc": "Whether to set supportsAllDrives on list calls."},
    )
    include_items_from_all_drives: bool = field(
        default=True,
        metadata={"doc": "Whether to includeItemsFromAllDrives on list calls."},
    )
    drive_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Optional shared Drive ID for corpora=drive scope."},
    )
    limit: int = field(
        default=50,
        metadata={"doc": "Maximum number of files to return after filtering."},
    )


@dataclass(frozen=True)
class DriveFolderFileListResponse:
    schema_version: str = field(
        metadata={"doc": "Drive folder file-list response schema version."}
    )
    folder_id: str = field(metadata={"doc": "Drive folder ID searched."})
    files: list[DriveFile] = field(metadata={"doc": "Matching files in the folder."})


@dataclass(frozen=True)
class DriveUploadBytesRequest:
    schema_version: str = field(
        metadata={"doc": "Drive upload-bytes request schema version."}
    )
    folder_id: str = field(metadata={"doc": "Drive folder ID where the file should be uploaded."})
    service_account_path: str = field(
        metadata={"doc": "Filesystem path to the Google service account JSON."}
    )
    file_name: str = field(metadata={"doc": "File name to create in Drive."})
    content: bytes = field(metadata={"doc": "Binary content to upload."})
    mime_type: str = field(metadata={"doc": "MIME type for the uploaded file."})
    supports_all_drives: bool = field(
        default=True,
        metadata={"doc": "Whether to set supportsAllDrives on upload calls."},
    )


@dataclass(frozen=True)
class DriveUploadBytesResponse:
    schema_version: str = field(
        metadata={"doc": "Drive upload-bytes response schema version."}
    )
    file: DriveFile = field(metadata={"doc": "Metadata for the created Drive file."})
    size: int = field(metadata={"doc": "Uploaded content size in bytes."})
    md5: Optional[str] = field(
        metadata={"doc": "MD5 checksum of the uploaded content when known."}
    )
