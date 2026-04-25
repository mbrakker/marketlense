from __future__ import annotations

from dataclasses import dataclass, field


PAYLOAD_SCHEMA_VERSION = "1.0"


@dataclass(frozen=True)
class IngestUiRunPayload:
    schema_version: str = field(metadata={"doc": "UI ingest payload schema version."})
    folder_id: str | None = field(
        default=None,
        metadata={"doc": "Optional Google Drive folder ID override."},
    )
    limit: int | None = field(
        default=None,
        metadata={"doc": "Optional positive maximum number of PDFs to process."},
    )


@dataclass(frozen=True)
class CandidateExtractionUiRunPayload:
    schema_version: str = field(
        metadata={"doc": "UI candidate-extraction payload schema version."}
    )
    folder_id: str | None = field(
        default=None,
        metadata={"doc": "Optional Google Drive folder ID override."},
    )
    limit: int | None = field(
        default=None,
        metadata={"doc": "Optional positive maximum number of PDFs to process."},
    )
    file_id: str | None = field(
        default=None,
        metadata={"doc": "Optional Google Drive file ID to process."},
    )
    pdf_path: str | None = field(
        default=None,
        metadata={"doc": "Optional local PDF path for direct extraction."},
    )
    report_id: str | None = field(
        default=None,
        metadata={"doc": "Optional report ID override for local PDF extraction."},
    )


@dataclass(frozen=True)
class CoverImagesUiRunPayload:
    schema_version: str = field(
        metadata={"doc": "UI cover-image payload schema version."}
    )
    style_config_path: str = field(
        metadata={"doc": "Cover style YAML path supplied by the UI."}
    )
    limit: int | None = field(
        default=None,
        metadata={"doc": "Optional positive maximum number of covers to generate."},
    )
    file_id: str | None = field(
        default=None,
        metadata={"doc": "Optional report file ID for a single cover generation."},
    )


@dataclass(frozen=True)
class PublishUiRunPayload:
    schema_version: str = field(metadata={"doc": "UI publish payload schema version."})
    limit: int | None = field(
        default=None,
        metadata={"doc": "Optional positive maximum number of reports to publish."},
    )


@dataclass(frozen=True)
class PublisherDiscoveryUiRunPayload:
    schema_version: str = field(
        metadata={"doc": "UI publisher-discovery payload schema version."}
    )
    insights_url: str = field(
        metadata={"doc": "Required publisher insights URL to crawl."}
    )


@dataclass(frozen=True)
class ReportDownloadUiRunPayload:
    schema_version: str = field(
        metadata={"doc": "UI report-download payload schema version."}
    )
    url: str = field(metadata={"doc": "Required report landing-page URL."})
    delivery_email: str | None = field(
        default=None,
        metadata={"doc": "Optional delivery email for gated report forms."},
    )
    publisher_insights_url: str | None = field(
        default=None,
        metadata={"doc": "Optional publisher insights URL for Drive-folder lookup."},
    )
    publisher_google_folder: str | None = field(
        default=None,
        metadata={"doc": "Optional publisher Google Drive folder URL or ID."},
    )


@dataclass(frozen=True)
class AcquisitionAuditUiRunPayload:
    schema_version: str = field(
        metadata={"doc": "UI acquisition-audit payload schema version."}
    )
    publisher_limit: int | None = field(
        default=None,
        metadata={"doc": "Optional positive maximum number of publishers to audit."},
    )
    candidate_limit_per_publisher: int | None = field(
        default=None,
        metadata={"doc": "Optional positive maximum candidate count per publisher."},
    )
    delivery_email: str | None = field(
        default=None,
        metadata={"doc": "Optional delivery email used for gated report forms."},
    )
