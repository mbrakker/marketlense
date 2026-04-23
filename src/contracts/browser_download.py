from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.contracts.drive import DriveFile
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace


@dataclass(frozen=True)
class BrowserDownloadIdentityField:
    schema_version: str = field(
        metadata={"doc": "Browser download identity field schema version."}
    )
    key: str = field(
        metadata={"doc": "Stable machine key used to match this field across forms."}
    )
    label: str = field(
        metadata={"doc": "Human-readable field label stored in the identity YAML."}
    )
    value: Optional[str] = field(
        default=None,
        metadata={"doc": "Configured value used when a matching form field is found."},
    )
    aliases: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Additional labels or names that should map to this identity field."
        },
    )


@dataclass(frozen=True)
class BrowserDownloadPublisherOverride:
    schema_version: str = field(
        metadata={"doc": "Browser download publisher-override schema version."}
    )
    host_pattern: str = field(
        metadata={
            "doc": "Exact host or host suffix used to match publisher-specific identity overrides."
        }
    )
    delivery_emails: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Publisher-specific delivery email addresses ranked ahead of the global identity emails."
        },
    )
    field_values: list[BrowserDownloadIdentityField] = field(
        default_factory=list,
        metadata={
            "doc": "Publisher-specific identity field values, including enum answers and field overrides."
        },
    )


@dataclass(frozen=True)
class BrowserDownloadIdentity:
    schema_version: str = field(
        metadata={"doc": "Browser download identity schema version."}
    )
    fields: list[BrowserDownloadIdentityField] = field(
        metadata={
            "doc": "Configured identity fields available for browser form filling."
        }
    )
    delivery_emails: list[str] = field(
        default_factory=list,
        metadata={
            "doc": "Configured delivery email addresses that can be used for gated report forms."
        },
    )
    publisher_overrides: list[BrowserDownloadPublisherOverride] = field(
        default_factory=list,
        metadata={
            "doc": "Optional publisher-specific delivery-email and field-value overrides."
        },
    )


@dataclass(frozen=True)
class BrowserDownloadIdentityFieldUpsertRequest:
    schema_version: str = field(
        metadata={"doc": "Identity-field upsert request schema version."}
    )
    path: str = field(
        metadata={
            "doc": "Absolute YAML path used to persist browser form identity fields."
        }
    )
    encountered_form_fields: list[str] = field(
        metadata={
            "doc": "Distinct human-readable field labels encountered during a browser run."
        }
    )


@dataclass(frozen=True)
class BrowserDownloadIdentityFieldUpsertResponse:
    schema_version: str = field(
        metadata={"doc": "Identity-field upsert response schema version."}
    )
    path: str = field(
        metadata={"doc": "Absolute YAML path that was inspected and updated."}
    )
    added_field_keys: list[str] = field(
        metadata={
            "doc": "New identity keys added to the YAML for future manual completion."
        }
    )
    total_fields: int = field(
        metadata={
            "doc": "Total number of identity fields stored after the upsert completed."
        }
    )


@dataclass(frozen=True)
class BrowserDownloadSettings:
    schema_version: str = field(
        metadata={"doc": "Browser download settings schema version."}
    )
    openrouter_api_key: str = field(
        metadata={"doc": "OpenRouter API key used by the local browser-use agent."}
    )
    model: str = field(
        metadata={"doc": "Model ID used by the local browser-use agent."}
    )
    temperature: float = field(
        metadata={"doc": "Sampling temperature for the browser-use agent."}
    )
    timeout_seconds: float = field(
        metadata={"doc": "Per-model timeout in seconds for browser-use LLM calls."}
    )
    max_steps: int = field(
        metadata={"doc": "Maximum browser-use agent steps per report download run."}
    )
    output_dir: str = field(
        metadata={"doc": "Root directory where browser-managed downloads are stored."}
    )
    state_db: str = field(
        metadata={"doc": "SQLite state DB used to remember successful per-URL routes."}
    )
    reports_db: str = field(
        metadata={
            "doc": "SQLite reports DB used to store downloaded-report source rows."
        }
    )
    identity_config_path: str = field(
        metadata={
            "doc": "Absolute YAML path used to load browser form identity values."
        }
    )
    identity_profile: BrowserDownloadIdentity = field(
        metadata={"doc": "Loaded browser form identity fields supplied to browser-use."}
    )
    openrouter_http_referer: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional HTTP-Referer header sent to OpenRouter for browser-use requests."
        },
    )
    headed: bool = field(
        default=False,
        metadata={
            "doc": "Whether to run the local browser visibly instead of headless."
        },
    )
    retry_retries: int = field(
        default=1,
        metadata={"doc": "Retry count for orchestrated browser download attempts."},
    )
    retry_base_delay_seconds: float = field(
        default=1.0,
        metadata={"doc": "Base delay before the first browser download retry."},
    )
    retry_backoff_step_seconds: float = field(
        default=1.0,
        metadata={"doc": "Linear backoff step added per browser download retry."},
    )
    retry_jitter_seconds: float = field(
        default=0.25,
        metadata={"doc": "Maximum jitter added to browser download retry delays."},
    )
    drive_upload_enabled: bool = field(
        default=False,
        metadata={
            "doc": "Whether successful report acquisitions should upload local terminal artifacts to Google Drive."
        },
    )
    drive_upload_required: bool = field(
        default=True,
        metadata={
            "doc": "Whether Drive archival failure should fail the report download workflow."
        },
    )
    drive_upload_google_sa_path: str = field(
        default="",
        metadata={
            "doc": "Filesystem path to the Google service account JSON used for Drive archival when auth mode is service_account."
        },
    )
    drive_upload_auth_mode: str = field(
        default="service_account",
        metadata={"doc": "Drive auth mode used for report acquisition archival."},
    )
    drive_upload_oauth_client_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional OAuth desktop client JSON path used for report acquisition archival."
        },
    )
    drive_upload_oauth_token_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "OAuth authorized-user token JSON path used for report acquisition archival."
        },
    )
    drive_upload_supports_all_drives: bool = field(
        default=True,
        metadata={"doc": "Whether Drive archival upload calls support shared drives."},
    )
    drive_upload_include_items_from_all_drives: bool = field(
        default=True,
        metadata={
            "doc": "Whether duplicate checks for Drive archival include items from shared drives."
        },
    )
    drive_upload_drive_id: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional shared Drive ID used when checking for duplicate archived artifacts."
        },
    )


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


@dataclass(frozen=True)
class ReportDownloadRoutePlanStep:
    schema_version: str = field(
        metadata={"doc": "Report download route-plan step schema version."}
    )
    step_name: str = field(
        metadata={"doc": "Stable orchestrator step name for this route attempt."}
    )
    route_family: str = field(
        metadata={
            "doc": "Planned route family for this attempt, for example `direct_pdf_probe` or `browser_email_form`."
        }
    )
    attempt_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Concrete URL the service should attempt first for this route step when known."
        },
    )
    route_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously successful route summary reused for this attempt when available."
        },
    )
    route_step_hints: list[BrowserDownloadRouteStep] = field(
        default_factory=list,
        metadata={
            "doc": "Previously successful structured route steps reused for this attempt when available."
        },
    )
    route_kind_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Previously observed route kind reused for this attempt when available."
        },
    )
    source_page_url_hint: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Discovery source page URL to revisit when the candidate URL is thin, gated, or tracker-like."
        },
    )
    uses_memory_route: bool = field(
        default=False,
        metadata={"doc": "Whether this step reuses remembered route memory."},
    )
    fallback_on_retryable_error: bool = field(
        default=False,
        metadata={
            "doc": "Whether the orchestrator should continue to the next planned step when this attempt fails with a retryable error."
        },
    )


@dataclass(frozen=True)
class ReportDownloadRoutePlanRequest:
    schema_version: str = field(
        metadata={"doc": "Report download route-plan request schema version."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized candidate URL used as the route-memory key."}
    )
    remembered_route: Optional["PublisherDownloadRouteMemory"] = field(
        default=None,
        metadata={"doc": "Previously remembered download route when available."},
    )
    candidate_trace: Optional[PublisherInventoryCandidateTrace] = field(
        default=None,
        metadata={
            "doc": "Optional discovery-phase candidate trace reused to choose and verify route order."
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


@dataclass(frozen=True)
class ReportDownloadRoutePlanResponse:
    schema_version: str = field(
        metadata={"doc": "Report download route-plan response schema version."}
    )
    steps: list[ReportDownloadRoutePlanStep] = field(
        metadata={"doc": "Ordered download attempts the orchestrator should execute."}
    )
    planning_reason: str = field(
        metadata={
            "doc": "Short human-readable explanation of why this route order was chosen."
        }
    )


@dataclass(frozen=True)
class PublisherDownloadRoutePolicySignal:
    schema_version: str = field(
        metadata={"doc": "Publisher route-policy signal schema version."}
    )
    route_family: str = field(
        metadata={
            "doc": "Route family this policy signal describes, for example `http_pdf_probe` or `browser_email_form`."
        }
    )
    route_kind: str = field(
        metadata={
            "doc": "Most recent or dominant route kind observed for this route family."
        }
    )
    attempts: int = field(
        metadata={"doc": "Number of recorded attempts for this route family."}
    )
    verified_successes: int = field(
        metadata={
            "doc": "Number of verified successful outcomes recorded for this route family."
        }
    )
    blocked_attempts: int = field(
        metadata={
            "doc": "Number of attempts that ended with a typed blocker for this route family."
        }
    )
    success_rate: float = field(
        metadata={
            "doc": "Verified-success ratio for this route family, rounded to three decimals."
        }
    )
    confidence_score: float = field(
        metadata={"doc": "Policy confidence score for preferring this route family."}
    )
    rank_score: float = field(
        metadata={
            "doc": "Planner ranking score derived from success rate, confidence, recency, and blocker penalty."
        }
    )
    last_outcome: str = field(
        metadata={"doc": "Most recent outcome observed for this route family."}
    )
    last_route_status: str = field(
        metadata={
            "doc": "Most recent verification status observed for this route family."
        }
    )
    last_blocked_reason: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Most recent typed blocker reason observed for this route family, if any."
        },
    )
    recent_outcomes: list[str] = field(
        default_factory=list,
        metadata={"doc": "Recent outcome labels observed for this route family."},
    )


@dataclass(frozen=True)
class PublisherDownloadRouteMemory:
    schema_version: str = field(
        metadata={"doc": "Publisher remembered download-route schema version."}
    )
    route_kind: str = field(
        metadata={"doc": "Remembered route kind previously observed for this URL."}
    )
    route_summary: str = field(
        metadata={"doc": "Remembered route summary previously observed for this URL."}
    )
    outcome: str = field(
        metadata={"doc": "Remembered route outcome previously observed for this URL."}
    )
    route_family: str = field(
        metadata={"doc": "Remembered route family previously observed for this URL."}
    )
    route_status: str = field(
        metadata={
            "doc": "Remembered route verification status previously observed for this URL."
        }
    )
    resolved_target_url: str = field(
        metadata={"doc": "Remembered resolved target URL for this route."}
    )
    route_steps: list[BrowserDownloadRouteStep] = field(
        default_factory=list,
        metadata={
            "doc": "Remembered structured route steps previously observed for this URL."
        },
    )
    attempts: int = field(
        default=0,
        metadata={
            "doc": "Remembered attempt count backing this route-memory record when available."
        },
    )
    verified_successes: int = field(
        default=0,
        metadata={
            "doc": "Remembered verified success count backing this route-memory record when available."
        },
    )
    last_n_outcomes: list[str] = field(
        default_factory=list,
        metadata={"doc": "Recent remembered outcomes for this route when available."},
    )
    confidence_score: float = field(
        default=0.0,
        metadata={"doc": "Confidence score for reusing this remembered route."},
    )
    exact_route_found: bool = field(
        default=True,
        metadata={
            "doc": "Whether this memory includes exact normalized-URL route history; false means only broader publisher-scope policy was available."
        },
    )
    browser_had_structured_result: bool = field(
        default=True,
        metadata={
            "doc": "Whether the remembered success came from a structured browser result instead of fallback salvage."
        },
    )
    onsite_completeness_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Remembered on-site completeness verdict when the route kind is `onsite_report`."
        },
    )
    route_policy: list[PublisherDownloadRoutePolicySignal] = field(
        default_factory=list,
        metadata={
            "doc": "Ranked route-family policy signals learned from exact normalized-URL route history."
        },
    )
    publisher_route_policy: list[PublisherDownloadRoutePolicySignal] = field(
        default_factory=list,
        metadata={
            "doc": "Ranked route-family policy signals learned from same-publisher route history outside the exact URL."
        },
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
