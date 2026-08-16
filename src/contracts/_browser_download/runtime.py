from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.contracts.drive import DriveFile
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.contracts.run_budget import RunBudget, RunBudgetUsage

from .identity import BrowserDownloadRequiredSelectEvidence, BrowserDownloadSettings
from .playbooks import BrowserRoutePlaybookSelection


@dataclass(frozen=True)
class ReportDownloadDriveUpload:
    schema_version: str = field(
        metadata={"doc": "Report-download Drive upload result schema version."}
    )
    local_path: str = field(
        metadata={"doc": "Local artifact path considered for Drive archival."}
    )
    file_name: str = field(
        metadata={"doc": "Drive file name for the archived artifact."}
    )
    mime_type: str = field(metadata={"doc": "MIME type used for the Drive artifact."})
    folder_id: str = field(metadata={"doc": "Target Google Drive folder ID."})
    status: str = field(
        metadata={"doc": "Archival status: uploaded or skipped_duplicate."}
    )
    size: int = field(metadata={"doc": "Archived or duplicate artifact size in bytes."})
    md5: Optional[str] = field(
        metadata={"doc": "MD5 checksum of the local artifact when available."}
    )
    drive_file: DriveFile = field(
        metadata={"doc": "Metadata for the uploaded or duplicate Drive file."}
    )


@dataclass(frozen=True)
class BrowserDownloadRouteStep:
    schema_version: str = field(
        metadata={"doc": "Browser download route-step schema version."}
    )
    index: int = field(
        metadata={"doc": "Zero-based step index in the observed route execution trace."}
    )
    action: str = field(
        metadata={
            "doc": "Observed action kind, for example `open`, `click`, `fill`, or `submit`."
        }
    )
    target_text: str = field(
        metadata={
            "doc": "Human-readable target label, URL fragment, or visible copy for the step."
        }
    )
    target_role: str = field(
        metadata={
            "doc": "Observed target role, for example `button`, `link`, `form`, or `page`."
        }
    )
    target_url: str = field(
        metadata={
            "doc": "Resolved target URL associated with the step when known, else empty string."
        }
    )
    result: str = field(
        metadata={
            "doc": "Observed outcome of the step, for example `opened`, `submitted`, or `downloaded`."
        }
    )
    expected_evidence: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Post-action evidence categories expected for this step, such as `screenshot`, `page_info`, `network_event`, `artifact`, `dom_hash`, or `confirmation_text`."
        },
    )
    observed_evidence: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Post-action evidence categories actually observed for this specific step."
        },
    )
    locator_evidence: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Action-bound locator evidence for this step. A promoted locator requires the canonical `locator:<selector_type>:<selector>` entry."
        },
    )
    postcondition_evidence: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Action-bound postcondition evidence for this step. Promoted URL/text postconditions require matching `url:<substring>` or `text:<text>` entries."
        },
    )
    verification_status: str = field(
        default="",
        metadata={
            "doc": "Post-action verification status for this step: `verified`, `missing`, or `not_applicable`."
        },
    )
    locator_role: str = field(
        default="",
        metadata={
            "doc": "Observed accessible role for the acted-on control, when available."
        },
    )
    locator_name: str = field(
        default="",
        metadata={
            "doc": "Observed accessible name for a role locator, when available."
        },
    )
    locator_label: str = field(
        default="",
        metadata={
            "doc": "Observed visible or accessible form-field label, when available."
        },
    )
    locator_field_name: str = field(
        default="",
        metadata={"doc": "Observed stable HTML form-control name, when available."},
    )
    locator_data_attribute: str = field(
        default="",
        metadata={"doc": "Observed stable data attribute locator, when available."},
    )
    locator_css: str = field(
        default="",
        metadata={
            "doc": "Observed CSS locator retained only when no semantic locator is available."
        },
    )
    locator_text: str = field(
        default="",
        metadata={
            "doc": "Observed visible text locator retained only as a last locator fallback."
        },
    )
    identity_field_reference: str = field(
        default="",
        metadata={
            "doc": "Configured identity-field reference used by a fill/select action; never the identity value."
        },
    )
    expected_url_contains: str = field(
        default="",
        metadata={"doc": "Observed URL substring that held after the verified action."},
    )
    expected_text: str = field(
        default="",
        metadata={
            "doc": "Observed visible postcondition text that held after the verified action."
        },
    )


@dataclass(frozen=True)
class BrowserDownloadConfirmationEvidence:
    schema_version: str = field(
        metadata={"doc": "Browser download confirmation-evidence schema version."}
    )
    url_changed: bool = field(
        metadata={
            "doc": "Whether the page URL changed after the relevant route action."
        }
    )
    visible_confirmation_text: str = field(
        metadata={
            "doc": "Visible confirmation or status text observed after the relevant route action, else empty string."
        }
    )
    submit_button_state: str = field(
        metadata={
            "doc": "Observed submit-button state after submission, for example `unchanged`, `disabled`, or `replaced`."
        }
    )
    form_disappeared: bool = field(
        metadata={"doc": "Whether the form disappeared after a submission attempt."}
    )
    final_page_url: str = field(
        metadata={
            "doc": "Final page URL associated with the captured confirmation evidence."
        }
    )
    confirmation_score: int = field(
        default=0,
        metadata={
            "doc": "Count of independent confirmation signals captured for the terminal form state."
        },
    )
    signal_labels: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Stable labels describing which confirmation signals contributed to the score."
        },
    )


@dataclass(frozen=True)
class BrowserDownloadNetworkEvent:
    schema_version: str = field(
        metadata={"doc": "Browser download network-event schema version."}
    )
    url: str = field(
        metadata={
            "doc": "Observed request URL associated with the terminal browser state."
        }
    )
    initiator_type: str = field(
        metadata={
            "doc": "Browser-reported initiator type, for example `navigation`, `fetch`, `xmlhttprequest`, or `beacon`."
        }
    )
    signal_kind: str = field(
        metadata={
            "doc": "Stable semantic classification for the request, for example `document_request`, `submission_request`, `confirmation_request`, or `other`."
        }
    )


@dataclass(frozen=True)
class BrowserDownloadDialogEvidence:
    schema_version: str = field(
        metadata={"doc": "Browser download dialog-evidence schema version."}
    )
    dialog_type: str = field(
        metadata={
            "doc": "Observed JavaScript dialog type, for example `alert`, `confirm`, `prompt`, `beforeunload`, or `unknown`."
        }
    )
    message: str = field(
        metadata={
            "doc": "Sanitized bounded dialog message when Chrome exposed it, else empty string."
        }
    )
    page_url: str = field(
        metadata={"doc": "Page URL associated with the dialog when available."}
    )
    action_taken: str = field(
        metadata={
            "doc": "Action taken by the terminal evidence capture policy, for example `accepted`, `dismissed`, or `none`."
        }
    )
    validation_status: str = field(
        metadata={
            "doc": "Dialog handling result: `handled`, `policy_rejected`, `handled_without_opening_event`, or `failed`."
        }
    )
    target_id: str = field(
        default="",
        metadata={"doc": "CDP target ID associated with the dialog evidence."},
    )
    session_id: str = field(
        default="",
        metadata={"doc": "CDP session ID associated with the dialog evidence."},
    )


@dataclass(frozen=True)
class DownloadTerminalEvidence:
    schema_version: str = field(
        metadata={"doc": "Browser download terminal-evidence schema version."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final browser URL associated with the terminal evidence."}
    )
    final_page_title: str = field(
        metadata={"doc": "Observed final page title when available, else empty string."}
    )
    terminal_text_excerpt: str = field(
        metadata={
            "doc": "Short visible text excerpt captured from the terminal page when available, else empty string."
        }
    )
    artifact_url: str = field(
        metadata={
            "doc": "Best known artifact URL associated with the terminal state when available, else empty string."
        }
    )
    artifact_kind: str = field(
        metadata={
            "doc": "Detected artifact kind for the terminal state, for example `pdf`, `html`, `email_delivery`, `onsite_report`, or `none`."
        }
    )
    artifact_validation_status: str = field(
        metadata={
            "doc": "Artifact validation status, for example `verified`, `recovered`, `invalid`, `blocked`, `captured`, or `none`."
        }
    )
    artifact_validation_detail: str = field(
        metadata={
            "doc": "Short detail describing why the terminal artifact was accepted, recovered, blocked, or rejected."
        }
    )
    confirmation_signal_count: int = field(
        metadata={
            "doc": "Number of independent confirmation signals observed for this terminal state."
        }
    )
    traversed_page_urls: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Distinct page URLs traversed while reaching the terminal state."
        },
    )
    visited_url_timeline: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Ordered URL timeline reconstructed from route steps and terminal navigation evidence."
        },
    )
    observed_document_urls: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Observed document or PDF-like URLs recovered from browser resource evidence, DOM markup, or deterministic artifact recovery."
        },
    )
    network_events: list[BrowserDownloadNetworkEvent] = field(
        default_factory=list,
        metadata={
            "doc": "Bounded typed network events captured from browser performance/navigation evidence for terminal-state salvage and auditability."
        },
    )
    dialog_evidence: list[BrowserDownloadDialogEvidence] = field(
        default_factory=list,
        metadata={
            "doc": "Bounded JavaScript dialog and beforeunload evidence captured from terminal browser CDP events."
        },
    )
    html_snapshot_path: str = field(
        default="",
        metadata={
            "doc": "Absolute local path of the persisted terminal HTML snapshot when available."
        },
    )
    screenshot_path: str = field(
        default="",
        metadata={
            "doc": "Absolute local path of the persisted terminal screenshot when available."
        },
    )
    dom_snapshot_sha256: str = field(
        default="",
        metadata={
            "doc": "SHA-256 hash of the bounded terminal DOM snapshot when browser HTML was available."
        },
    )
    evidence_labels: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Stable labels describing the deterministic evidence captured for this terminal state."
        },
    )


@dataclass(frozen=True)
class PreBrowserDocTypePrediction:
    schema_version: str = field(
        metadata={"doc": "Pre-browser doc-type prediction schema version."}
    )
    predicted_doc_type: str = field(
        metadata={
            "doc": "Predicted lightweight document type before browser startup, for example `direct_pdf`, `report_page_pdf_link`, or `browser_required`."
        }
    )
    predicted_route_family: str = field(
        metadata={
            "doc": "Predicted route family that should be attempted first based on lightweight pre-browser evidence."
        }
    )
    probe_url: str = field(
        metadata={
            "doc": "Resolved URL that should be probed first before browser startup."
        }
    )
    confidence_score: float = field(
        metadata={
            "doc": "Deterministic confidence score between 0.0 and 1.0 for the predicted document type."
        }
    )
    decision_reason: str = field(
        metadata={
            "doc": "Short human-readable explanation of the strongest evidence supporting the prediction."
        }
    )
    requires_browser: bool = field(
        metadata={
            "doc": "Whether the prediction still requires full browser automation after lightweight preflight checks."
        }
    )
    evidence_labels: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Stable labels describing which deterministic pre-browser signals contributed to the prediction."
        },
    )


@dataclass(frozen=True)
class BrowserReportDownloadRequest:
    schema_version: str = field(
        metadata={"doc": "Browser report download request schema version."}
    )
    url: str = field(
        metadata={"doc": "Absolute source URL for the report landing page."}
    )
    settings: BrowserDownloadSettings = field(
        metadata={"doc": "Browser-use execution settings."}
    )
    delivery_email: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional email address to submit when a report is gated behind email delivery."
        },
    )
    route_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously successful route summary used to bias the next browser attempt."
        },
    )
    route_step_hints: list[BrowserDownloadRouteStep] = field(
        default_factory=list,
        metadata={
            "doc": "Previously successful structured route steps reused to bias the next browser attempt when available."
        },
    )
    route_kind_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously observed route kind (`pdf_download`, `email_delivery`, or `onsite_report`) when available."
        },
    )
    candidate_trace: Optional[PublisherInventoryCandidateTrace] = field(
        default=None,
        metadata={
            "doc": "Optional discovery-phase candidate trace reused to plan and verify the download route."
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
    attempt_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional execution URL chosen by the download planner for this attempt when it differs from the source URL."
        },
    )
    route_family_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional planned route family for this attempt, for example `direct_pdf_probe` or `browser_email_form`."
        },
    )
    source_page_url_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional discovery source page URL to revisit when the candidate URL is thin, gated, or tracker-like."
        },
    )
    report_title: str = field(
        default="",
        metadata={
            "doc": "Optional expected report title used by route shortcuts to reject unrelated artifacts."
        },
    )
    selected_playbooks: list[BrowserRoutePlaybookSelection] = field(
        default_factory=list,
        metadata={
            "doc": "Fresh browser route playbooks selected for this attempt and cited in the browser-use prompt."
        },
    )
    publisher_name: str = field(
        default="",
        metadata={"doc": "Publisher name associated with this browser-use action."},
    )
    run_budget: RunBudget | None = field(
        default=None,
        metadata={
            "doc": "Optional shared pre-side-effect budget for this browser launch."
        },
    )
    run_budget_usage: RunBudgetUsage | None = field(
        default=None,
        metadata={"doc": "Current shared budget usage before this browser launch."},
    )


@dataclass(frozen=True)
class BrowserReportDownloadResult:
    schema_version: str = field(
        metadata={"doc": "Browser report download result schema version."}
    )
    source_url: str = field(metadata={"doc": "Original URL provided by the caller."})
    normalized_url: str = field(
        metadata={"doc": "Normalized URL used for route-memory lookup and storage."}
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
        metadata={"doc": "Concise summary of the successful browser route."}
    )
    final_page_url: str = field(
        metadata={"doc": "Final browser URL after the agent finished."}
    )
    resolved_target_url: str = field(
        metadata={
            "doc": "Resolved target URL that produced the final artifact or email form state."
        }
    )
    used_route_hint: bool = field(
        metadata={"doc": "Whether the execution used a previously stored route hint."}
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
            "doc": "Canonical terminal evidence captured for successful or failed browser acquisition attempts."
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
    required_select_evidence: list[BrowserDownloadRequiredSelectEvidence] = field(
        default_factory=list,
        metadata={
            "doc": "Observed required-select labels, names, and visible options retained for safe identity learning."
        },
    )
    blocked_reason: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Typed blocker code when the browser reached a blocked email-gated or static terminal state."
        },
    )
    blocked_reason_detail: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Human-readable blocker detail captured from the terminal state when available."
        },
    )
    downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Absolute path of the downloaded report when outcome=`downloaded`."
        },
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
            "doc": "Absolute path of the captured on-site report artifact when outcome=`captured`."
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
