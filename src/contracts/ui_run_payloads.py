from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


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


@dataclass(frozen=True)
class CrossReportAnalysisUiRunPayload:
    schema_version: str = field(
        metadata={"doc": "UI cross-report analysis payload schema version."}
    )
    topic: str = field(
        default="",
        metadata={"doc": "Operator topic; optional only when auto-theme is enabled."},
    )
    auto_theme: bool = field(
        default=True,
        metadata={"doc": "Whether deterministic automatic theme selection may run."},
    )
    category_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected category filters selected in the UI."},
    )
    tag_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected tag filters selected in the UI."},
    )
    publisher_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected publisher filters selected in the UI."},
    )
    date_range_start: str | None = field(
        default=None,
        metadata={"doc": "Optional inclusive YYYY-MM-DD lower date bound."},
    )
    date_range_end: str | None = field(
        default=None,
        metadata={"doc": "Optional inclusive YYYY-MM-DD upper date bound."},
    )
    max_source_reports: int | None = field(
        default=None,
        metadata={"doc": "Optional positive selected-source cap."},
    )
    max_evidence_items: int | None = field(
        default=None,
        metadata={"doc": "Optional positive evidence input cap."},
    )
    max_prompt_chars: int | None = field(
        default=None,
        metadata={"doc": "Optional positive rendered prompt character cap."},
    )
    publication_mode: str = field(
        default="generate_only",
        metadata={"doc": "Publication mode requested by the UI."},
    )
    output_root: str = field(
        default="",
        metadata={"doc": "Optional output root override."},
    )
    idempotency_db: str = field(
        default="",
        metadata={"doc": "Optional idempotency database override."},
    )
    request_id: str = field(
        default="",
        metadata={"doc": "Optional stable request id override."},
    )
    diagnostic: bool = field(
        default=False,
        metadata={"doc": "Whether diagnostic mode may inspect weak source sets."},
    )
    override_publishability: bool = field(
        default=False,
        metadata={"doc": "Explicit operator override for publishability gates."},
    )


@dataclass(frozen=True)
class SignalCandidateExtractionUiRunPayload:
    schema_version: str = field(
        metadata={"doc": "UI Signal candidate extraction payload schema version."}
    )
    topic: str = field(metadata={"doc": "Operator-selected Signal topic."})
    category_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected category filters selected in the UI."},
    )
    tag_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected tag filters selected in the UI."},
    )
    publisher_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected publisher filters selected in the UI."},
    )
    date_range_start: str | None = field(
        default=None,
        metadata={"doc": "Optional inclusive YYYY-MM-DD lower date bound."},
    )
    date_range_end: str | None = field(
        default=None,
        metadata={"doc": "Optional inclusive YYYY-MM-DD upper date bound."},
    )
    max_source_reports: int | None = field(
        default=None,
        metadata={"doc": "Optional positive selected-source cap."},
    )
    max_evidence_items: int | None = field(
        default=None,
        metadata={"doc": "Optional positive evidence input cap."},
    )
    max_signals: int | None = field(
        default=None,
        metadata={"doc": "Optional positive Signal candidate cap."},
    )
    extraction_request_id: str = field(
        default="",
        metadata={"doc": "Optional stable extraction request id override."},
    )
    signal_store_db: str = field(
        default="",
        metadata={"doc": "Optional Signal candidate store database override."},
    )


@dataclass(frozen=True)
class SignalPostUiRunPayload:
    schema_version: str = field(
        metadata={"doc": "UI Signal post workflow payload schema version."}
    )
    topic: str = field(metadata={"doc": "Operator-selected Signal topic."})
    category_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected category filters selected in the UI."},
    )
    tag_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected tag filters selected in the UI."},
    )
    publisher_filters: List[str] = field(
        default_factory=list,
        metadata={"doc": "Projected publisher filters selected in the UI."},
    )
    date_range_start: str | None = field(
        default=None,
        metadata={"doc": "Optional inclusive YYYY-MM-DD lower date bound."},
    )
    date_range_end: str | None = field(
        default=None,
        metadata={"doc": "Optional inclusive YYYY-MM-DD upper date bound."},
    )
    max_source_reports: int | None = field(
        default=None,
        metadata={"doc": "Optional positive selected-source cap."},
    )
    max_evidence_items: int | None = field(
        default=None,
        metadata={"doc": "Optional positive evidence input cap."},
    )
    minimum_source_reports: int | None = field(
        default=None,
        metadata={"doc": "Optional positive minimum source-report requirement."},
    )
    minimum_evidence_items: int | None = field(
        default=None,
        metadata={"doc": "Optional positive minimum evidence-item requirement."},
    )
    publication_mode: str = field(
        default="publish_dry_run",
        metadata={"doc": "Publication mode requested by the UI."},
    )
    request_id: str = field(
        default="",
        metadata={"doc": "Optional stable Signal workflow request id override."},
    )
    output_root: str = field(
        default="",
        metadata={"doc": "Optional output root override."},
    )
    signal_store_db: str = field(
        default="",
        metadata={"doc": "Optional Signal candidate store database override."},
    )


@dataclass(frozen=True)
class UiRunReplayUiRunPayload:
    schema_version: str = field(
        metadata={"doc": "UI-run replay payload schema version."}
    )
    run_id: str = field(metadata={"doc": "Original UI run identifier to replay."})
    registry_path: str = field(
        default="",
        metadata={"doc": "Optional UI-run registry path override."},
    )
