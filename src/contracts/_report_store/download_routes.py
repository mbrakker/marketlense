from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    DownloadTerminalEvidence,
    PublisherDownloadRoutePolicySignal,
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
        metadata={
            "doc": "Normalized URL used to find the matching publisher insights_url."
        }
    )
    publisher_scope_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional publisher, source, or listing URL used to aggregate route policy across report URLs on the same publisher domain."
        },
    )


@dataclass(frozen=True)
class PublisherPrivateApiCandidateObservationRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Private-API candidate observation request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    fingerprint: str = field(
        metadata={"doc": "Stable private-API candidate fingerprint."}
    )
    publisher_host: str = field(
        metadata={"doc": "Publisher host associated with the candidate."}
    )
    source_url: str = field(
        metadata={"doc": "Source URL whose verified run produced the observation."}
    )
    endpoint_pattern: str = field(
        metadata={"doc": "Endpoint pattern derived from repeated observations."}
    )
    method: str = field(metadata={"doc": "Validated HTTP method."})
    request_shape_summary: str = field(
        metadata={"doc": "Reviewable request shape summary."}
    )
    response_pdf_url_json_pointer: str = field(
        metadata={"doc": "JSON pointer that extracts the PDF URL."}
    )
    expected_status_codes: List[int] = field(
        metadata={"doc": "Accepted HTTP status codes."}
    )
    required_response_markers: List[str] = field(
        metadata={"doc": "Required response markers."}
    )
    fallback_route_family: str = field(
        metadata={"doc": "Route family used when the endpoint is stale."}
    )
    route_family: str = field(
        metadata={"doc": "Browser route family replaced by the deterministic route."}
    )
    route_kind: str = field(
        metadata={"doc": "Route kind produced by the deterministic route."}
    )
    evidence_labels: List[str] = field(
        default_factory=list,
        metadata={"doc": "Evidence labels backing the observation."},
    )
    observed_at: str = field(
        default="",
        metadata={"doc": "UTC ISO timestamp when the observation was validated."},
    )
    min_success_count: int = field(
        default=3,
        metadata={"doc": "Minimum observation count required for promotion."},
    )
    min_distinct_source_urls: int = field(
        default=2,
        metadata={"doc": "Minimum distinct source URL count required for promotion."},
    )


@dataclass(frozen=True)
class PublisherPrivateApiCandidateObservationRecordResponse:
    schema_version: str = field(
        metadata={"doc": "Private-API candidate observation response schema version."}
    )
    fingerprint: str = field(
        metadata={"doc": "Stable private-API candidate fingerprint."}
    )
    success_count: int = field(
        metadata={"doc": "Validated success count after this observation."}
    )
    distinct_source_url_count: int = field(
        metadata={"doc": "Distinct source URL count after this observation."}
    )
    eligible_for_promotion: bool = field(
        metadata={
            "doc": "Whether this candidate has crossed automatic promotion thresholds."
        }
    )
    already_promoted: bool = field(
        metadata={"doc": "Whether this candidate was already promoted to a playbook."}
    )
    promoted_playbook_id: str = field(
        default="",
        metadata={"doc": "Playbook ID recorded after promotion, if any."},
    )


@dataclass(frozen=True)
class PublisherPrivateApiCandidatePromotedRequest:
    schema_version: str = field(
        metadata={"doc": "Private-API candidate promoted request schema version."}
    )
    db_path: str = field(
        metadata={"doc": "Filesystem path to the report metadata SQLite database."}
    )
    fingerprint: str = field(
        metadata={"doc": "Stable private-API candidate fingerprint."}
    )
    playbook_id: str = field(
        metadata={"doc": "Playbook ID written for this promoted candidate."}
    )
    promoted_at: str = field(
        metadata={"doc": "UTC ISO timestamp when promotion completed."}
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
        metadata={
            "doc": "Last source URL observed for the route; expected to match publisher insights_url."
        }
    )
    route_kind: str = field(
        metadata={
            "doc": "Detected route kind: `pdf_download`, `email_delivery`, or `onsite_report`."
        }
    )
    route_summary: str = field(
        metadata={
            "doc": "Remembered summary of the best-known route for this publisher URL."
        }
    )
    outcome: str = field(
        metadata={
            "doc": "Observed outcome: `downloaded`, `email_requested`, `email_required`, or `captured`."
        }
    )
    route_family: str = field(
        metadata={
            "doc": "Observed route family, for example `direct_pdf_probe` or `browser_email_form`."
        }
    )
    route_status: str = field(
        metadata={
            "doc": "Verification status for the route result, for example `verified` or `inferred`."
        }
    )
    resolved_target_url: str = field(
        metadata={
            "doc": "Resolved target URL that produced the final artifact or email form state."
        }
    )
    route_steps: List[BrowserDownloadRouteStep] = field(
        metadata={
            "doc": "Structured route execution trace stored for later reuse and debugging."
        }
    )
    confirmation_evidence: BrowserDownloadConfirmationEvidence = field(
        metadata={
            "doc": "Structured confirmation evidence stored for email-gated or ambiguous routes."
        }
    )
    terminal_evidence: DownloadTerminalEvidence = field(
        metadata={
            "doc": "Canonical terminal evidence stored for successful or failed route classification."
        }
    )
    browser_had_structured_result: bool = field(
        metadata={
            "doc": "Whether browser-use returned a structured result instead of requiring fallback salvage."
        }
    )
    used_candidate_pdf_url: bool = field(
        metadata={
            "doc": "Whether the successful route reused a discovery-provided candidate PDF URL."
        }
    )
    used_candidate_source_page: bool = field(
        metadata={
            "doc": "Whether the successful route reused a discovery-provided candidate source page URL."
        }
    )
    candidate_pdf_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Discovery-provided candidate PDF URL snapshot recorded with the route attempt."
        },
    )
    candidate_source_page_urls: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Discovery source page URLs snapshot recorded with the route attempt."
        },
    )
    candidate_discovery_provenances: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Discovery provenance labels snapshot recorded with the route attempt."
        },
    )
    publisher_discovery_route_kind: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Publisher-level discovery route kind snapshot recorded with the route attempt."
        },
    )
    publisher_recommended_discovery_route_kind: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Publisher-level recommended discovery route kind snapshot recorded with the route attempt."
        },
    )
    blocked_reason: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Typed blocker code when the route reached a blocked terminal state."
        },
    )
    blocked_reason_detail: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Human-readable blocker detail captured from the terminal state when available."
        },
    )
    last_downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last downloaded local file path for this publisher route, if any."
        },
    )
    last_final_page_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last final browser URL observed for this publisher route, if any."
        },
    )
    onsite_capture_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last local on-site capture path for this publisher route, if any."
        },
    )
    onsite_capture_format: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Stored on-site capture format for this publisher route, if any."
        },
    )
    onsite_page_count: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Stored on-site captured page count for this publisher route, if any."
        },
    )
    onsite_completeness_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Stored on-site capture completeness verdict for this publisher route, if any."
        },
    )
    attempts: int = field(
        default=0,
        metadata={
            "doc": "Total attempts recorded for this normalized route after this write."
        },
    )
    verified_successes: int = field(
        default=0,
        metadata={
            "doc": "Total verified successes recorded for this normalized route after this write."
        },
    )
    last_n_outcomes: List[str] = field(
        default_factory=list,
        metadata={"doc": "Recent outcomes backing this route-memory record."},
    )
    confidence_score: float = field(
        default=0.0,
        metadata={
            "doc": "Confidence score assigned to this remembered route after projection."
        },
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
        metadata={
            "doc": "Detected route kind: `pdf_download`, `email_delivery`, or `onsite_report`."
        }
    )
    route_summary: str = field(
        metadata={
            "doc": "Remembered summary of the best-known route for this publisher URL."
        }
    )
    outcome: str = field(
        metadata={"doc": "Last observed outcome for this publisher route."}
    )
    route_family: str = field(
        metadata={
            "doc": "Observed route family, for example `direct_pdf_probe` or `browser_email_form`."
        }
    )
    route_status: str = field(
        metadata={
            "doc": "Verification status for the route result, for example `verified` or `inferred`."
        }
    )
    resolved_target_url: str = field(
        metadata={
            "doc": "Resolved target URL that produced the final artifact or email form state."
        }
    )
    route_steps: List[BrowserDownloadRouteStep] = field(
        metadata={
            "doc": "Structured route execution trace stored for later reuse and debugging."
        }
    )
    confirmation_evidence: BrowserDownloadConfirmationEvidence = field(
        metadata={
            "doc": "Structured confirmation evidence stored for email-gated or ambiguous routes."
        }
    )
    terminal_evidence: DownloadTerminalEvidence = field(
        metadata={
            "doc": "Canonical terminal evidence stored for successful or failed route classification."
        }
    )
    browser_had_structured_result: bool = field(
        metadata={
            "doc": "Whether browser-use returned a structured result instead of requiring fallback salvage."
        }
    )
    used_candidate_pdf_url: bool = field(
        metadata={
            "doc": "Whether the remembered route reused a discovery-provided candidate PDF URL."
        }
    )
    used_candidate_source_page: bool = field(
        metadata={
            "doc": "Whether the remembered route reused a discovery-provided candidate source page URL."
        }
    )
    updated_at: int = field(
        metadata={
            "doc": "Unix timestamp when the publisher route-memory record was last updated."
        }
    )
    candidate_pdf_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Discovery-provided candidate PDF URL snapshot recorded with the route attempt."
        },
    )
    candidate_source_page_urls: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Discovery source page URLs snapshot recorded with the route attempt."
        },
    )
    candidate_discovery_provenances: List[str] = field(
        default_factory=list,
        metadata={
            "doc": "Discovery provenance labels snapshot recorded with the route attempt."
        },
    )
    publisher_discovery_route_kind: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Publisher-level discovery route kind snapshot recorded with the route attempt."
        },
    )
    publisher_recommended_discovery_route_kind: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Publisher-level recommended discovery route kind snapshot recorded with the route attempt."
        },
    )
    blocked_reason: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Typed blocker code when the route reached a blocked terminal state."
        },
    )
    blocked_reason_detail: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Human-readable blocker detail captured from the terminal state when available."
        },
    )
    last_downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last downloaded local file path for this publisher route, if any."
        },
    )
    last_final_page_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last final browser URL observed for this publisher route, if any."
        },
    )
    onsite_capture_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last local on-site capture path for this publisher route, if any."
        },
    )
    onsite_capture_format: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Stored on-site capture format for this publisher route, if any."
        },
    )
    onsite_page_count: Optional[int] = field(
        default=None,
        metadata={
            "doc": "Stored on-site captured page count for this publisher route, if any."
        },
    )
    onsite_completeness_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Stored on-site capture completeness verdict for this publisher route, if any."
        },
    )
    attempts: int = field(
        default=0,
        metadata={
            "doc": "Total remembered attempts recorded for this normalized route."
        },
    )
    verified_successes: int = field(
        default=0,
        metadata={
            "doc": "Total remembered verified successes recorded for this normalized route."
        },
    )
    last_n_outcomes: List[str] = field(
        default_factory=list,
        metadata={"doc": "Recent outcomes backing this route-memory record."},
    )
    confidence_score: float = field(
        default=0.0,
        metadata={"doc": "Confidence score assigned to this remembered route."},
    )
    exact_route_found: bool = field(
        default=True,
        metadata={
            "doc": "Whether this response includes exact normalized-URL route memory; false means only broader publisher-scope policy was available."
        },
    )
    publisher_scope_url: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Publisher, source, or listing URL used to aggregate publisher-scope route policy when available."
        },
    )
    route_policy: List[PublisherDownloadRoutePolicySignal] = field(
        default_factory=list,
        metadata={
            "doc": "Ranked route-family policy signals learned from exact normalized-URL route history."
        },
    )
    publisher_route_policy: List[PublisherDownloadRoutePolicySignal] = field(
        default_factory=list,
        metadata={
            "doc": "Ranked route-family policy signals learned from same-publisher route history outside the exact URL."
        },
    )
