from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.docpacks import DocPackPathMap


@dataclass(frozen=True)
class ReportMetadataUpsertRequest:
    schema_version: str = field(
        metadata={"doc": "Metadata upsert request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    file_id: str = field(metadata={"doc": "Drive file ID for the report."})
    title: str = field(metadata={"doc": "Human-friendly report title."})
    file_name: Optional[str] = field(
        default=None, metadata={"doc": "Source PDF filename for the report, if known."}
    )
    publisher: Optional[str] = field(
        default=None,
        metadata={"doc": "Publisher or organization for the report, if known."},
    )
    taxonomy: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "List of report metadata tags extracted from evidence; these tags do not drive portal category assignment."
        },
    )
    categories: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "List of assigned portal category IDs produced by the context-first category fit."
        },
    )
    region: Optional[str] = field(
        default=None,
        metadata={"doc": "Geographic region or market focus for the report, if known."},
    )
    time_period: Optional[str] = field(
        default=None,
        metadata={"doc": "Primary time period covered by the report, if known."},
    )
    source_url: Optional[str] = field(
        default=None, metadata={"doc": "Primary source URL associated with the report."}
    )
    html_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Filesystem path to the rendered HTML, if available."},
    )
    md5: Optional[str] = field(
        default=None, metadata={"doc": "MD5 checksum of the source PDF, if available."}
    )
    page_count: Optional[int] = field(
        default=None, metadata={"doc": "Total pages in the source PDF, if known."}
    )
    contents_page_number: int = field(
        default=0,
        metadata={
            "doc": "One-based page number for detected contents/index page; 0 when not found."
        },
    )
    pdf_metadata: dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Flattened PDF metadata for the source document."},
    )
    analysis_mode: str = field(
        default="vector_store",
        metadata={"doc": "Analysis mode used to generate the report (vector_store)."},
    )
    vector_store_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Vector store ID used for evidence pack generation, if any."},
    )
    evidence_pack_paths: DocPackPathMap = field(
        default_factory=dict,
        metadata={"doc": "Mapping of evidence-pack names to stored JSON paths."},
    )


@dataclass(frozen=True)
class ReportMetadataDbAccessRequest:
    schema_version: str = field(
        metadata={"doc": "Report metadata DB access check request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    timeout_seconds: float = field(
        default=0.0,
        metadata={"doc": "SQLite connection timeout in seconds for lock detection."},
    )


@dataclass(frozen=True)
class ReportMetadataDbAccessResponse:
    schema_version: str = field(
        metadata={"doc": "Report metadata DB access check response schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    accessible: bool = field(
        metadata={"doc": "True when the metadata DB can be opened for writing."}
    )
    locked: bool = field(
        metadata={"doc": "True when the metadata DB is locked by another process."}
    )
    message: str = field(
        default="", metadata={"doc": "Additional detail for the access check result."}
    )


@dataclass(frozen=True)
class ReportMetadataGetRequest:
    schema_version: str = field(
        metadata={"doc": "Metadata get request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    file_id: str = field(metadata={"doc": "Drive file ID for the report."})


@dataclass(frozen=True)
class ReportMetadataGetResponse:
    schema_version: str = field(
        metadata={"doc": "Metadata get response schema version."}
    )
    file_id: str = field(metadata={"doc": "Drive file ID for the report."})
    title: str = field(metadata={"doc": "Human-friendly report title."})
    created_at: int = field(
        metadata={"doc": "Unix timestamp when the metadata record was created."}
    )
    updated_at: int = field(
        metadata={"doc": "Unix timestamp when the metadata record was last updated."}
    )
    file_name: Optional[str] = field(
        default=None, metadata={"doc": "Source PDF filename for the report, if known."}
    )
    publisher: Optional[str] = field(
        default=None,
        metadata={"doc": "Publisher or organization for the report, if known."},
    )
    taxonomy: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "List of report metadata tags extracted from evidence; these tags do not drive portal category assignment."
        },
    )
    categories: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "List of assigned portal category IDs produced by the context-first category fit."
        },
    )
    region: Optional[str] = field(
        default=None,
        metadata={"doc": "Geographic region or market focus for the report, if known."},
    )
    time_period: Optional[str] = field(
        default=None,
        metadata={"doc": "Primary time period covered by the report, if known."},
    )
    source_url: Optional[str] = field(
        default=None, metadata={"doc": "Primary source URL associated with the report."}
    )
    html_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Filesystem path to the rendered HTML, if available."},
    )
    md5: Optional[str] = field(
        default=None, metadata={"doc": "MD5 checksum of the source PDF, if available."}
    )
    page_count: Optional[int] = field(
        default=None, metadata={"doc": "Total pages in the source PDF, if known."}
    )
    contents_page_number: int = field(
        default=0,
        metadata={
            "doc": "One-based page number for detected contents/index page; 0 when not found."
        },
    )
    pdf_metadata: dict[str, str] = field(
        default_factory=dict,
        metadata={"doc": "Flattened PDF metadata for the source document."},
    )
    analysis_mode: str = field(
        default="vector_store",
        metadata={"doc": "Analysis mode used to generate the report (vector_store)."},
    )
    vector_store_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Vector store ID used for evidence pack generation, if any."},
    )
    evidence_pack_paths: DocPackPathMap = field(
        default_factory=dict,
        metadata={"doc": "Mapping of evidence-pack names to stored JSON paths."},
    )


@dataclass(frozen=True)
class ReportMetadataListRequest:
    schema_version: str = field(
        metadata={"doc": "Metadata list request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )


@dataclass(frozen=True)
class ReportMetadataListResponse:
    schema_version: str = field(
        metadata={"doc": "Metadata list response schema version."}
    )
    records: List[ReportMetadataGetResponse] = field(
        metadata={"doc": "All report metadata records."}
    )


@dataclass(frozen=True)
class ReportSourceRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Report-source record request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    source_domain: str = field(
        metadata={"doc": "Source domain where the report landing page lives."}
    )
    report_name: str = field(
        metadata={"doc": "Human-readable report name derived from the downloaded file."}
    )
    landing_page_url: str = field(
        metadata={"doc": "Landing-page URL where the report download path was found."}
    )
    downloaded_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the report download completed."}
    )
    md5: str = field(
        metadata={"doc": "MD5 checksum of the downloaded report file."}
    )


@dataclass(frozen=True)
class ReportSourceRecordResponse:
    schema_version: str = field(
        metadata={"doc": "Report-source record response schema version."}
    )
    record_id: int = field(
        metadata={"doc": "Auto-incremented SQLite row ID for the stored source record."}
    )
    source_domain: str = field(
        metadata={"doc": "Source domain where the report landing page lives."}
    )
    report_name: str = field(
        metadata={"doc": "Human-readable report name derived from the downloaded file."}
    )
    landing_page_url: str = field(
        metadata={"doc": "Landing-page URL where the report download path was found."}
    )
    downloaded_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the report download completed."}
    )
    md5: str = field(
        metadata={"doc": "MD5 checksum of the downloaded report file."}
    )
