from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, TYPE_CHECKING

from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace

if TYPE_CHECKING:
    from src.contracts.mailbox_acquisition import MailboxAcquisitionSettings
else:
    MailboxAcquisitionSettings = Any

from .identity import BrowserDownloadSettings
from .runtime import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    DownloadTerminalEvidence,
    ReportDownloadDriveUpload,
)


@dataclass(frozen=True)
class ReportDownloadOrchestratorRequest:
    schema_version: str = field(
        metadata={"doc": "Report download orchestrator request schema version."}
    )
    url: str = field(metadata={"doc": "Absolute report landing-page URL."})
    settings: BrowserDownloadSettings = field(
        metadata={"doc": "Browser download settings loaded from configuration."}
    )
    state_db: str = field(
        metadata={"doc": "SQLite state DB used to remember successful per-URL routes."}
    )
    reports_db: str = field(
        metadata={
            "doc": "SQLite reports DB used to store downloaded-report source rows."
        }
    )
    delivery_email: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional email address used when a report can only be delivered by email."
        },
    )
    candidate_trace: Optional[PublisherInventoryCandidateTrace] = field(
        default=None,
        metadata={
            "doc": "Optional discovery-phase candidate trace reused to choose and verify the download route."
        },
    )
    publisher_discovery_route_kind: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional publisher-level discovery route kind from the inventory/diff phase."
        },
    )
    publisher_recommended_discovery_route_kind: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional publisher-level recommended discovery route kind from the inventory/diff phase."
        },
    )
    publisher_insights_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional publisher insights URL used to resolve the target Drive folder for acquisition archival."
        },
    )
    publisher_google_folder: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional publisher Google Drive folder URL or folder ID used for acquisition archival."
        },
    )
    report_title: str = field(
        default="",
        metadata={"doc": "Optional report title for deferred mail acquisition."},
    )
    publisher_name: str = field(
        default="",
        metadata={"doc": "Optional publisher name for deferred mail acquisition."},
    )
    mailbox_settings: Optional["MailboxAcquisitionSettings"] = field(
        default=None,
        metadata={
            "doc": "Optional mailbox settings enabling autonomous deferred mail acquisition."
        },
    )
    revalidate_route_policy: bool = field(
        default=False,
        metadata={
            "doc": "Explicit operator override that permits browser and mailbox revalidation of a fresh remembered hard blocker."
        },
    )


@dataclass(frozen=True)
class ReportDownloadOrchestratorResult:
    schema_version: str = field(
        metadata={"doc": "Report download orchestrator result schema version."}
    )
    source_url: str = field(metadata={"doc": "Original URL provided by the caller."})
    normalized_url: str = field(
        metadata={"doc": "Normalized URL used for state lookup and storage."}
    )
    route_kind: str = field(
        metadata={
            "doc": "Detected delivery path: `pdf_download`, `email_delivery`, or `onsite_report`."
        }
    )
    route_family: str = field(
        metadata={
            "doc": "Planned or observed route family that produced the result, for example `direct_pdf_probe` or `browser_email_form`."
        }
    )
    route_status: str = field(
        metadata={
            "doc": "Verification status for the route result, for example `verified` or `inferred`."
        }
    )
    outcome: str = field(
        metadata={
            "doc": "Observed outcome: `downloaded`, `email_requested`, `email_required`, or `captured`."
        }
    )
    route_summary: str = field(
        metadata={"doc": "Stored summary of the best-known route for this URL."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final browser URL after orchestration completed."}
    )
    resolved_target_url: str = field(
        metadata={
            "doc": "Resolved target URL that produced the final artifact or email form state."
        }
    )
    used_memory_route: bool = field(
        metadata={
            "doc": "Whether a remembered route hint was used on the successful run."
        }
    )
    route_steps: list[BrowserDownloadRouteStep] = field(
        metadata={
            "doc": "Structured route execution trace captured for reuse and verification."
        }
    )
    confirmation_evidence: BrowserDownloadConfirmationEvidence = field(
        metadata={
            "doc": "Structured confirmation evidence captured for email-gated or ambiguous routes."
        }
    )
    terminal_evidence: DownloadTerminalEvidence = field(
        metadata={
            "doc": "Canonical terminal evidence captured for the final successful browser acquisition attempt."
        }
    )
    browser_had_structured_result: bool = field(
        metadata={
            "doc": "Whether browser-use returned a structured JSON result instead of requiring fallback salvage."
        }
    )
    used_candidate_pdf_url: bool = field(
        metadata={
            "doc": "Whether the result reused a discovery-provided candidate PDF URL."
        }
    )
    used_candidate_source_page: bool = field(
        metadata={
            "doc": "Whether the result reused a discovery-provided candidate source page URL."
        }
    )
    encountered_form_fields: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Distinct form field labels or names encountered while following the route."
        },
    )
    identity_fields_added: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "New identity keys added to the browser identity YAML after this run."
        },
    )
    blocked_reason: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Typed blocker code when the final route is blocked instead of completed."
        },
    )
    blocked_reason_detail: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Human-readable blocker detail captured from the final terminal state when available."
        },
    )
    downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Absolute local report path when the file was downloaded."},
    )
    downloaded_file_name: Optional[str] = field(
        default=None,
        metadata={"doc": "Downloaded file name when a file was saved locally."},
    )
    downloaded_mime_type: Optional[str] = field(
        default=None,
        metadata={"doc": "Detected MIME type for the downloaded file when available."},
    )
    downloaded_size_bytes: Optional[int] = field(
        default=None,
        metadata={"doc": "Downloaded file size in bytes when a local file exists."},
    )
    onsite_capture_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Absolute local path of the captured on-site report artifact when outcome=`captured`."
        },
    )
    onsite_capture_format: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Stored on-site capture format, for example `html`, `markdown`, or `html+markdown`."
        },
    )
    onsite_page_count: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Number of distinct pages or scroll segments captured for an on-site report when known."
        },
    )
    onsite_completeness_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "On-site capture completeness verdict, for example `complete`, `partial`, or `bounded_incomplete`."
        },
    )
    drive_uploads: list[ReportDownloadDriveUpload] = field(
        default_factory=list,
        metadata={
            "doc": "Drive archival results for successful local terminal artifacts."
        },
    )
