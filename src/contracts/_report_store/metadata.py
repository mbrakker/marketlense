from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional, Tuple

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
class ReportSourceIdentityResolveRequest:
    schema_version: str = field(
        metadata={"doc": "Report source identity lookup request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    report_title: str = field(
        default="",
        metadata={"doc": "Human-readable report title used as a fallback lookup key."},
    )
    md5: Optional[str] = field(
        default=None,
        metadata={"doc": "Source PDF MD5 used as the preferred lookup key."},
    )
    publisher_name: Optional[str] = field(
        default=None,
        metadata={"doc": "Known publisher used to disambiguate title matches."},
    )


@dataclass(frozen=True)
class ReportSourceIdentityResolveResponse:
    schema_version: str = field(
        metadata={"doc": "Report source identity lookup response schema version."}
    )
    publisher_name: str = field(
        default="",
        metadata={"doc": "Resolved publisher display name, if known."},
    )
    report_name: str = field(
        default="",
        metadata={"doc": "Resolved source report display name, if known."},
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Resolved source or landing-page URL, if known."},
    )
    resolution_source: str = field(
        default="",
        metadata={
            "doc": "Lookup source used: md5, title_unambiguous, title_publisher_unambiguous, or unresolved."
        },
    )


@dataclass(frozen=True)
class SourcePublicationObservedValue:
    """One bounded source-page date observation retained for provenance."""

    schema_version: str = field(
        metadata={"doc": "Source-publication observation schema version."}
    )
    publication_date: str = field(
        default="",
        metadata={"doc": "Normalized source date with no invented month or day."},
    )
    publication_date_precision: str = field(
        default="",
        metadata={"doc": "Observed date precision: day, month, year, or empty."},
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Publisher page URL that exposed this observation."},
    )
    retrieved_at_utc: str = field(
        default="",
        metadata={"doc": "UTC instant when the publisher evidence was observed."},
    )
    evidence_kind: str = field(
        default="",
        metadata={"doc": "Extraction route, such as json_ld_date_published."},
    )
    evidence_locator: str = field(
        default="",
        metadata={"doc": "Bounded JSON path, meta name, or semantic DOM locator."},
    )
    evidence_value_hash: str = field(
        default="",
        metadata={"doc": "SHA-256 of the observed source date value."},
    )
    evidence_status: str = field(
        default="unknown",
        metadata={
            "doc": "verified, unknown, invalid, or conflicting observation status."
        },
    )


@dataclass(frozen=True)
class SourcePublicationMetadata:
    """Canonical persisted provenance for a report-source publication date."""

    schema_version: str = field(
        metadata={"doc": "Source-publication metadata schema version."}
    )
    source_record_id: int = field(
        default=0,
        metadata={"doc": "Canonical report_sources row identifier when resolved."},
    )
    source_identity: str = field(
        default="",
        metadata={"doc": "Stable report-source identity, never a local artifact path."},
    )
    publication_date: str = field(
        default="",
        metadata={"doc": "Normalized ISO date, year-month, or year without invention."},
    )
    publication_date_precision: str = field(
        default="",
        metadata={"doc": "day, month, year, or empty when no valid date exists."},
    )
    source_url: str = field(
        default="",
        metadata={"doc": "Publisher URL that supports the canonical date."},
    )
    retrieved_at_utc: str = field(
        default="",
        metadata={
            "doc": "UTC instant when the supporting publisher evidence was seen."
        },
    )
    evidence_kind: str = field(
        default="",
        metadata={"doc": "Canonical extraction route for the selected evidence."},
    )
    evidence_locator: str = field(
        default="",
        metadata={"doc": "Bounded location of the selected evidence in the source."},
    )
    evidence_value_hash: str = field(
        default="",
        metadata={"doc": "SHA-256 of the selected publisher-supplied value."},
    )
    evidence_status: str = field(
        default="unknown",
        metadata={
            "doc": "verified, unknown, conflicting, invalid, or legacy_unverified."
        },
    )
    contradiction_status: str = field(
        default="not_applicable",
        metadata={"doc": "none, conflicting, or not_applicable."},
    )
    observed_values: Tuple[SourcePublicationObservedValue, ...] = field(
        default_factory=tuple,
        metadata={
            "doc": "All bounded date observations retained without source-page text."
        },
    )


@dataclass(frozen=True)
class SourcePublicationMetadataExtractionRequest:
    schema_version: str = field(
        metadata={"doc": "Source-publication extraction request schema version."}
    )
    source_url: str = field(
        metadata={"doc": "Publisher page URL represented by the captured HTML."}
    )
    retrieved_at_utc: str = field(
        metadata={"doc": "UTC instant when the HTML capture was observed."}
    )
    html: str = field(
        default="",
        metadata={
            "doc": "Captured publisher HTML; never persisted or logged as standard event data."
        },
    )


@dataclass(frozen=True)
class SourcePublicationMetadataExtractionResponse:
    schema_version: str = field(
        metadata={"doc": "Source-publication extraction response schema version."}
    )
    metadata: SourcePublicationMetadata = field(
        metadata={"doc": "Deterministically extracted bounded publisher provenance."}
    )


@dataclass(frozen=True)
class SourcePublicationMetadataUpsertRequest:
    schema_version: str = field(
        metadata={"doc": "Source-publication persistence request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Reports SQLite database containing the source record."}
    )
    metadata: SourcePublicationMetadata = field(
        metadata={"doc": "Canonical metadata observation to merge idempotently."}
    )


@dataclass(frozen=True)
class SourcePublicationMetadataUpsertResponse:
    schema_version: str = field(
        metadata={"doc": "Source-publication persistence response schema version."}
    )
    metadata: SourcePublicationMetadata = field(
        metadata={
            "doc": "Merged canonical metadata after provenance-preserving persistence."
        }
    )
    changed: bool = field(
        metadata={"doc": "Whether persistence changed the stored canonical metadata."}
    )


@dataclass(frozen=True)
class ReportPublicationMetadataGetRequest:
    schema_version: str = field(
        metadata={"doc": "Report publication-metadata lookup request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Reports SQLite database containing source provenance."}
    )
    report_title: str = field(
        default="",
        metadata={"doc": "Report title used only for constrained source resolution."},
    )
    md5: Optional[str] = field(
        default=None,
        metadata={"doc": "Preferred source checksum lookup key when available."},
    )
    publisher_name: Optional[str] = field(
        default=None,
        metadata={"doc": "Publisher used to constrain title fallback resolution."},
    )


@dataclass(frozen=True)
class ReportPublicationMetadataGetResponse:
    schema_version: str = field(
        metadata={"doc": "Report publication-metadata lookup response schema version."}
    )
    metadata: SourcePublicationMetadata = field(
        metadata={
            "doc": "Resolved canonical metadata or explicit unknown legacy state."
        }
    )
    resolution_source: str = field(
        metadata={
            "doc": "md5, title_unambiguous, title_publisher_unambiguous, or unresolved."
        }
    )
