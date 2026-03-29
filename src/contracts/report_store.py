from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.docpacks import DocPackPathMap
from src.contracts.publisher_profiles import PublisherProfileRecord


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


@dataclass(frozen=True)
class PublishersReplaceRequest:
    schema_version: str = field(
        metadata={"doc": "Publishers replace request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    source_page_url: str = field(
        metadata={"doc": "Original Notion page URL that the snapshot was sourced from."}
    )
    publishers: List[PublisherProfileRecord] = field(
        metadata={"doc": "Validated publisher rows to replace the current publishers table contents."}
    )


@dataclass(frozen=True)
class PublishersReplaceResponse:
    schema_version: str = field(
        metadata={"doc": "Publishers replace response schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    source_page_url: str = field(
        metadata={"doc": "Original Notion page URL that the snapshot was sourced from."}
    )
    previous_count: int = field(
        metadata={"doc": "Number of publisher rows present before replacement."}
    )
    replaced_count: int = field(
        metadata={"doc": "Number of publisher rows stored after replacement."}
    )


@dataclass(frozen=True)
class PublisherDownloadRouteGetRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher download-route get request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized URL used to find the matching publisher insights_url."}
    )


@dataclass(frozen=True)
class PublisherDownloadRouteRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher download-route record request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized URL used to identify the publisher insights_url."}
    )
    source_url: str = field(
        metadata={"doc": "Last source URL observed for the route; expected to match publisher insights_url."}
    )
    route_kind: str = field(
        metadata={"doc": "Detected route kind: `pdf_download` or `email_delivery`."}
    )
    route_summary: str = field(
        metadata={"doc": "Remembered summary of the best-known route for this publisher URL."}
    )
    outcome: str = field(
        metadata={"doc": "Observed outcome: `downloaded`, `email_requested`, or `email_required`."}
    )
    last_downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Last downloaded local file path for this publisher route, if any."},
    )
    last_final_page_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Last final browser URL observed for this publisher route, if any."},
    )


@dataclass(frozen=True)
class PublisherDownloadRouteResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher download-route response schema version."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized URL used as the publisher-route memory key."}
    )
    source_url: str = field(
        metadata={"doc": "Publisher insights URL used as the stored source URL."}
    )
    route_kind: str = field(
        metadata={"doc": "Detected route kind: `pdf_download` or `email_delivery`."}
    )
    route_summary: str = field(
        metadata={"doc": "Remembered summary of the best-known route for this publisher URL."}
    )
    outcome: str = field(
        metadata={"doc": "Last observed outcome for this publisher route."}
    )
    updated_at: int = field(
        metadata={"doc": "Unix timestamp when the publisher route-memory record was last updated."}
    )
    last_downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Last downloaded local file path for this publisher route, if any."},
    )
    last_final_page_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Last final browser URL observed for this publisher route, if any."},
    )


@dataclass(frozen=True)
class PublisherInventoryStateGetRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory-state get request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used to find the matching publisher row."}
    )


@dataclass(frozen=True)
class PublisherInventoryStateResponse:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory-state response schema version."}
    )
    publisher_name: str = field(metadata={"doc": "Publisher display name."})
    insights_url: str = field(metadata={"doc": "Stored publisher insights URL."})
    normalized_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used as the lookup key."}
    )
    google_folder: Optional[str] = field(
        default=None,
        metadata={"doc": "Curated Google Drive folder URL or folder ID for this publisher."},
    )
    inventory_route_kind: Optional[str] = field(
        default=None,
        metadata={"doc": "Remembered discovery route kind for this publisher URL."},
    )
    inventory_route_summary: Optional[str] = field(
        default=None,
        metadata={"doc": "Remembered discovery route summary for this publisher URL."},
    )
    inventory_route_last_final_page_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Last final page URL observed for the remembered discovery route."},
    )
    inventory_route_updated_at: Optional[int] = field(
        default=None,
        metadata={"doc": "Unix timestamp when the remembered discovery route was last updated."},
    )
    inventory_snapshot_drive_file_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Drive file ID of the latest stored inventory snapshot."},
    )
    inventory_snapshot_drive_file_name: Optional[str] = field(
        default=None,
        metadata={"doc": "Drive file name of the latest stored inventory snapshot."},
    )
    inventory_snapshot_sha256: Optional[str] = field(
        default=None,
        metadata={"doc": "SHA-256 hash of the latest stored inventory snapshot JSON."},
    )
    inventory_snapshot_updated_at: Optional[int] = field(
        default=None,
        metadata={"doc": "Unix timestamp when the latest stored inventory snapshot index was updated."},
    )


@dataclass(frozen=True)
class PublisherInventoryStateRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Publisher inventory-state record request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized publisher insights URL used to identify the publisher row."}
    )
    source_url: str = field(
        metadata={"doc": "Stored source insights URL for the publisher."}
    )
    route_kind: str = field(
        metadata={"doc": "Discovery route kind used successfully: http_parse or browser_render."}
    )
    route_summary: str = field(
        metadata={"doc": "Summary of the successful discovery route for reuse on later runs."}
    )
    last_final_page_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Last final page URL observed for the successful discovery route."},
    )
    snapshot_drive_file_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Drive file ID of the latest stored snapshot, when changed or already known."},
    )
    snapshot_drive_file_name: Optional[str] = field(
        default=None,
        metadata={"doc": "Drive file name of the latest stored snapshot, when changed or already known."},
    )
    snapshot_sha256: Optional[str] = field(
        default=None,
        metadata={"doc": "SHA-256 hash of the latest stored snapshot JSON, when changed or already known."},
    )
