from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(frozen=True)
class ReportMetadataUpsertRequest:
    schema_version: str = field(metadata={"doc": "Metadata upsert request schema version."})
    db_path: str = field(metadata={"doc": "Filesystem path to the report metadata SQLite database."})
    file_id: str = field(metadata={"doc": "Drive file ID for the report."})
    title: str = field(metadata={"doc": "Human-friendly report title."})
    publisher: Optional[str] = field(default=None, metadata={"doc": "Publisher or organization for the report, if known."})
    taxonomy: List[str] = field(default_factory=list, metadata={"doc": "List of taxonomy tags/categories."})
    categories: List[str] = field(default_factory=list, metadata={"doc": "List of assigned category IDs."})
    region: Optional[str] = field(default=None, metadata={"doc": "Geographic region or market focus for the report, if known."})
    time_period: Optional[str] = field(default=None, metadata={"doc": "Primary time period covered by the report, if known."})
    source_url: Optional[str] = field(default=None, metadata={"doc": "Primary source URL associated with the report."})
    html_path: Optional[str] = field(default=None, metadata={"doc": "Filesystem path to the rendered HTML, if available."})
    md5: Optional[str] = field(default=None, metadata={"doc": "MD5 checksum of the source PDF, if available."})


@dataclass(frozen=True)
class ReportMetadataGetRequest:
    schema_version: str = field(metadata={"doc": "Metadata get request schema version."})
    db_path: str = field(metadata={"doc": "Filesystem path to the report metadata SQLite database."})
    file_id: str = field(metadata={"doc": "Drive file ID for the report."})


@dataclass(frozen=True)
class ReportMetadataGetResponse:
    schema_version: str = field(metadata={"doc": "Metadata get response schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID for the report."})
    title: str = field(metadata={"doc": "Human-friendly report title."})
    created_at: int = field(metadata={"doc": "Unix timestamp when the metadata record was created."})
    updated_at: int = field(metadata={"doc": "Unix timestamp when the metadata record was last updated."})
    publisher: Optional[str] = field(default=None, metadata={"doc": "Publisher or organization for the report, if known."})
    taxonomy: List[str] = field(default_factory=list, metadata={"doc": "List of taxonomy tags/categories."})
    categories: List[str] = field(default_factory=list, metadata={"doc": "List of assigned category IDs."})
    region: Optional[str] = field(default=None, metadata={"doc": "Geographic region or market focus for the report, if known."})
    time_period: Optional[str] = field(default=None, metadata={"doc": "Primary time period covered by the report, if known."})
    source_url: Optional[str] = field(default=None, metadata={"doc": "Primary source URL associated with the report."})
    html_path: Optional[str] = field(default=None, metadata={"doc": "Filesystem path to the rendered HTML, if available."})
    md5: Optional[str] = field(default=None, metadata={"doc": "MD5 checksum of the source PDF, if available."})


@dataclass(frozen=True)
class ReportMetadataListRequest:
    schema_version: str = field(metadata={"doc": "Metadata list request schema version."})
    db_path: str = field(metadata={"doc": "Filesystem path to the report metadata SQLite database."})


@dataclass(frozen=True)
class ReportMetadataListResponse:
    schema_version: str = field(metadata={"doc": "Metadata list response schema version."})
    records: List[ReportMetadataGetResponse] = field(metadata={"doc": "All report metadata records."})
