from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.browser_download import BrowserDownloadSettings
from src.contracts.publisher_inventory import PublisherInventorySettings


@dataclass(frozen=True)
class AcquisitionAuditCandidateResult:
    schema_version: str = field(
        metadata={"doc": "Acquisition-audit candidate result schema version."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher display name for the audited candidate."}
    )
    publisher_insights_url: str = field(
        metadata={
            "doc": "Publisher insights URL used for the discovery run that surfaced this candidate."
        }
    )
    publisher_discovery_route_kind: str = field(
        metadata={
            "doc": "Discovery route kind used for the publisher run that surfaced this candidate."
        }
    )
    publisher_recommended_discovery_route_kind: str = field(
        metadata={
            "doc": "Recommended future discovery route kind for this publisher based on the run-quality summary."
        }
    )
    report_url: str = field(metadata={"doc": "Normalized candidate report URL."})
    report_title: str = field(metadata={"doc": "Normalized candidate report title."})
    discovered_on_page_number: int = field(
        metadata={
            "doc": "One-based inventory page number where the candidate was first found."
        }
    )
    source_page_urls: List[str] = field(
        metadata={
            "doc": "Distinct inventory page URLs where the candidate was observed during discovery."
        }
    )
    discovery_provenances: List[str] = field(
        metadata={
            "doc": "Distinct provenance labels describing how the candidate was discovered."
        }
    )
    acquisition_route_kind: str = field(
        metadata={
            "doc": "Observed acquisition route kind for the candidate: pdf_download, email_delivery, failed_retryable, or failed_permanent."
        }
    )
    acquisition_outcome: str = field(
        metadata={
            "doc": "Observed acquisition outcome for the candidate, for example downloaded, email_requested, email_required, failed_retryable, or failed_permanent."
        }
    )
    recommended_report_flow: str = field(
        metadata={
            "doc": "Recommended future automation flow for this report candidate."
        }
    )
    recommendation_reason: str = field(
        metadata={"doc": "Short human-readable reason for the recommended report flow."}
    )
    acquisition_route_summary: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Observed acquisition route summary when the download flow reached a terminal route."
        },
    )
    acquisition_final_page_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Final browser URL observed during acquisition when available."
        },
    )
    encountered_form_fields: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Distinct form field labels encountered during acquisition when available."
        },
    )
    downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Absolute downloaded file path when the report was acquired locally."
        },
    )
    error_code: Optional[str] = field(
        default=None,
        metadata={"doc": "Typed AppError code when acquisition failed."},
    )
    error_message: Optional[str] = field(
        default=None,
        metadata={"doc": "Human-readable acquisition failure message when available."},
    )


@dataclass(frozen=True)
class AcquisitionAuditPublisherSummary:
    schema_version: str = field(
        metadata={"doc": "Acquisition-audit publisher summary schema version."}
    )
    publisher_name: str = field(metadata={"doc": "Publisher display name."})
    insights_url: str = field(metadata={"doc": "Publisher insights URL."})
    discovery_route_kind: str = field(
        metadata={"doc": "Discovery route kind used for the audited publisher run."}
    )
    discovery_quality_band: str = field(
        metadata={"doc": "Run-quality band for the audited publisher discovery run."}
    )
    recommended_discovery_route_kind: str = field(
        metadata={"doc": "Recommended discovery route kind for the next publisher run."}
    )
    recommended_publisher_flow: str = field(
        metadata={
            "doc": "Recommended future acquisition strategy for this publisher based on candidate audit outcomes."
        }
    )
    recommendation_reason: str = field(
        metadata={
            "doc": "Short human-readable reason for the publisher-level recommendation."
        }
    )
    current_candidate_count: int = field(
        metadata={
            "doc": "Number of current normalized candidates surfaced by discovery for this publisher."
        }
    )
    downloaded_count: int = field(
        metadata={
            "doc": "Number of candidates whose acquisition flow produced a local download."
        }
    )
    email_requested_count: int = field(
        metadata={
            "doc": "Number of candidates whose acquisition flow successfully submitted an email-delivery request."
        }
    )
    email_required_count: int = field(
        metadata={
            "doc": "Number of candidates whose acquisition flow requires email completion before automation can finish."
        }
    )
    failed_count: int = field(
        metadata={"doc": "Number of candidates whose acquisition flow failed."}
    )
    discovery_provenance_counts: dict[str, int] = field(
        default_factory=dict,
        metadata={
            "doc": "Counts of discovery provenance labels observed across the publisher's current candidates."
        },
    )
    acquisition_route_counts: dict[str, int] = field(
        default_factory=dict,
        metadata={
            "doc": "Counts of acquisition route kinds observed across the publisher's audited candidates."
        },
    )
    acquisition_outcome_counts: dict[str, int] = field(
        default_factory=dict,
        metadata={
            "doc": "Counts of acquisition outcomes observed across the publisher's audited candidates."
        },
    )
    error_code: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Typed AppError code when the publisher-level discovery phase failed."
        },
    )
    error_message: Optional[str] = field(
        default=None,
        metadata={"doc": "Human-readable discovery failure message when available."},
    )


@dataclass(frozen=True)
class AcquisitionAuditBatchRequest:
    schema_version: str = field(
        metadata={"doc": "Acquisition-audit batch request schema version."}
    )
    reports_db: str = field(
        metadata={"doc": "Filesystem path to the canonical reports SQLite database."}
    )
    publisher_inventory_settings: PublisherInventorySettings = field(
        metadata={
            "doc": "Loaded publisher inventory settings used for the discovery phase of the audit."
        }
    )
    browser_download_settings: BrowserDownloadSettings = field(
        metadata={
            "doc": "Loaded browser download settings used for the acquisition phase of the audit."
        }
    )
    output_dir: str = field(
        metadata={
            "doc": "Root output directory where audit artifacts should be written."
        }
    )
    delivery_email: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional delivery email used when report acquisition reaches an email-gated route."
        },
    )
    publisher_limit: Optional[int] = field(
        default=None,
        metadata={"doc": "Optional maximum number of current publishers to audit."},
    )
    candidate_limit_per_publisher: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Optional maximum number of current candidates to audit per publisher."
        },
    )


@dataclass(frozen=True)
class AcquisitionAuditBatchResult:
    schema_version: str = field(
        metadata={"doc": "Acquisition-audit batch result schema version."}
    )
    generated_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the audit artifact was generated."}
    )
    output_path: str = field(
        metadata={
            "doc": "Filesystem path of the written acquisition-audit JSON artifact."
        }
    )
    publisher_count: int = field(
        metadata={"doc": "Number of publishers included in the audit artifact."}
    )
    candidate_count: int = field(
        metadata={"doc": "Number of audited candidates included in the artifact."}
    )
    publishers: List[AcquisitionAuditPublisherSummary] = field(
        metadata={"doc": "Publisher-level acquisition summaries."}
    )
    candidates: List[AcquisitionAuditCandidateResult] = field(
        metadata={"doc": "Candidate-level acquisition results."}
    )
