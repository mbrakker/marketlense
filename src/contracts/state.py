from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from src.contracts.workflow_control import WorkflowControlObservation


@dataclass(frozen=True)
class StateCheckRequest:
    schema_version: str = field(metadata={"doc": "State check request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})


@dataclass(frozen=True)
class StateBatchCheckItem:
    schema_version: str = field(
        metadata={"doc": "State batch-check item schema version."}
    )
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})


@dataclass(frozen=True)
class StateBatchCheckRequest:
    schema_version: str = field(
        metadata={"doc": "State batch-check request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    items: List[StateBatchCheckItem] = field(
        metadata={"doc": "List of file_id+md5 pairs to check."}
    )


@dataclass(frozen=True)
class StateBatchCheckResponse:
    schema_version: str = field(
        metadata={"doc": "State batch-check response schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    processed_items: List[StateBatchCheckItem] = field(
        metadata={"doc": "Pairs found in processed state."}
    )


@dataclass(frozen=True)
class StateRecordRequest:
    schema_version: str = field(
        metadata={"doc": "State record request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    openai_file_id: Optional[str] = field(
        default=None, metadata={"doc": "OpenAI file ID, if any."}
    )
    vector_store_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Vector store ID associated with the file, if any."},
    )
    vector_store_status: Optional[str] = field(
        default=None, metadata={"doc": "Vector store status, if any."}
    )
    indexed_at_utc: Optional[str] = field(
        default=None,
        metadata={"doc": "ISO-8601 UTC timestamp when the file was indexed, if known."},
    )
    last_error: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last error encountered during vector store operations, if any."
        },
    )
    text_validation_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Extractable text validation status: pass|fail, if evaluated."
        },
    )
    text_validation_reason: Optional[str] = field(
        default=None,
        metadata={"doc": "Extractable text validation failure reason, if any."},
    )
    text_validation_pages: Optional[List[int]] = field(
        default=None,
        metadata={"doc": "Page numbers sampled for extractable text validation."},
    )
    doc_map_summary: Optional[Dict[str, object]] = field(
        default=None,
        metadata={
            "doc": "DocMap validation summary when doc_map is empty, if available."
        },
    )
    ocr_fallback_used: bool = field(
        default=False,
        metadata={"doc": "Whether OCR fallback was used to prepare the analysis PDF."},
    )
    ocr_pdf_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Filesystem path to the OCR-generated PDF used for analysis, if any."
        },
    )


@dataclass(frozen=True)
class StateDbAccessRequest:
    schema_version: str = field(
        metadata={"doc": "State DB access check request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    timeout_seconds: float = field(
        default=0.0,
        metadata={"doc": "SQLite connection timeout in seconds for lock detection."},
    )


@dataclass(frozen=True)
class StateDbAccessResponse:
    schema_version: str = field(
        metadata={"doc": "State DB access check response schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    accessible: bool = field(
        metadata={"doc": "True when the state DB can be opened for writing."}
    )
    locked: bool = field(
        metadata={"doc": "True when the state DB is locked by another process."}
    )
    message: str = field(
        default="", metadata={"doc": "Additional detail for the access check result."}
    )


@dataclass(frozen=True)
class StateIngestCursorGetRequest:
    schema_version: str = field(
        metadata={"doc": "Ingest cursor get request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})


@dataclass(frozen=True)
class StateIngestCursorGetResponse:
    schema_version: str = field(
        metadata={"doc": "Ingest cursor get response schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    last_successful_ingest_utc: Optional[str] = field(
        default=None,
        metadata={"doc": "RFC3339 timestamp of last successful ingest run."},
    )


@dataclass(frozen=True)
class StateIngestCursorSetRequest:
    schema_version: str = field(
        metadata={"doc": "Ingest cursor set request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    last_successful_ingest_utc: str = field(
        metadata={"doc": "RFC3339 timestamp of last successful ingest run."}
    )


@dataclass(frozen=True)
class StateGetRequest:
    schema_version: str = field(metadata={"doc": "State get request schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})


@dataclass(frozen=True)
class StateGetResponse:
    schema_version: str = field(metadata={"doc": "State get response schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    processed_at: int = field(metadata={"doc": "Unix timestamp of processing."})
    openai_file_id: Optional[str] = field(
        default=None, metadata={"doc": "OpenAI file ID, if any."}
    )
    vector_store_id: Optional[str] = field(
        default=None,
        metadata={"doc": "Vector store ID associated with the file, if any."},
    )
    vector_store_status: Optional[str] = field(
        default=None, metadata={"doc": "Vector store status, if any."}
    )
    indexed_at_utc: Optional[str] = field(
        default=None,
        metadata={"doc": "ISO-8601 UTC timestamp when the file was indexed, if known."},
    )
    last_error: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Last error encountered during vector store operations, if any."
        },
    )
    text_validation_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Extractable text validation status: pass|fail, if evaluated."
        },
    )
    text_validation_reason: Optional[str] = field(
        default=None,
        metadata={"doc": "Extractable text validation failure reason, if any."},
    )
    text_validation_pages: Optional[List[int]] = field(
        default=None,
        metadata={"doc": "Page numbers sampled for extractable text validation."},
    )
    doc_map_summary: Optional[Dict[str, object]] = field(
        default=None,
        metadata={
            "doc": "DocMap validation summary when doc_map is empty, if available."
        },
    )
    ocr_fallback_used: bool = field(
        default=False,
        metadata={"doc": "Whether OCR fallback was used to prepare the analysis PDF."},
    )
    ocr_pdf_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Filesystem path to the OCR-generated PDF used for analysis, if any."
        },
    )


@dataclass(frozen=True)
class StatePublishCheckRequest:
    schema_version: str = field(
        metadata={"doc": "Publish check request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for publishing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    post_type: str = field(
        metadata={"doc": "WordPress post type slug tracked for this publish target."}
    )


@dataclass(frozen=True)
class StatePublishRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Publish record request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for publishing state."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    wp_post_id: int = field(metadata={"doc": "WordPress post ID."})
    wp_post_url: str = field(metadata={"doc": "WordPress post URL."})
    post_type: str = field(
        metadata={"doc": "WordPress post type slug used for this publish record."}
    )


@dataclass(frozen=True)
class StatePublishGetResponse:
    schema_version: str = field(
        metadata={"doc": "Publish get response schema version."}
    )
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the PDF."})
    published_at: int = field(metadata={"doc": "Unix timestamp of publish time."})
    wp_post_id: int = field(metadata={"doc": "WordPress post ID."})
    wp_post_url: str = field(metadata={"doc": "WordPress post URL."})
    post_type: str = field(
        metadata={"doc": "WordPress post type slug used for this publish record."}
    )


@dataclass(frozen=True)
class StateProcessedListRequest:
    schema_version: str = field(
        metadata={"doc": "Processed-state list request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    limit: int = field(
        default=200, metadata={"doc": "Maximum number of rows to return."}
    )


@dataclass(frozen=True)
class StateProcessedRow:
    schema_version: str = field(metadata={"doc": "Processed-state row schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum of the processed PDF."})
    processed_at: int = field(
        metadata={"doc": "Unix timestamp when processing completed."}
    )
    openai_file_id: Optional[str] = field(
        default=None, metadata={"doc": "OpenAI file ID, if any."}
    )
    vector_store_id: Optional[str] = field(
        default=None, metadata={"doc": "Vector store ID, if any."}
    )
    vector_store_status: Optional[str] = field(
        default=None, metadata={"doc": "Vector store indexing status, if any."}
    )
    indexed_at_utc: Optional[str] = field(
        default=None, metadata={"doc": "Vector store indexed timestamp, if known."}
    )
    last_error: Optional[str] = field(
        default=None, metadata={"doc": "Last error recorded for this file, if any."}
    )
    text_validation_status: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Extractable text validation status: pass|fail, if evaluated."
        },
    )
    text_validation_reason: Optional[str] = field(
        default=None,
        metadata={"doc": "Extractable text validation failure reason, if any."},
    )
    text_validation_pages: Optional[List[int]] = field(
        default=None,
        metadata={"doc": "Page numbers sampled for extractable text validation."},
    )
    doc_map_summary: Optional[Dict[str, object]] = field(
        default=None,
        metadata={
            "doc": "DocMap summary payload when processing halted on doc_map_empty, if any."
        },
    )
    ocr_fallback_used: bool = field(
        default=False,
        metadata={"doc": "Whether OCR fallback was used to prepare the analysis PDF."},
    )
    ocr_pdf_path: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Filesystem path to the OCR-generated PDF used for analysis, if any."
        },
    )


@dataclass(frozen=True)
class StateProcessedListResponse:
    schema_version: str = field(
        metadata={"doc": "Processed-state list response schema version."}
    )
    rows: List[StateProcessedRow] = field(
        metadata={"doc": "Processed-state rows ordered by recency."}
    )


@dataclass(frozen=True)
class StatePublishedListRequest:
    schema_version: str = field(
        metadata={"doc": "Published-state list request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for publishing state."})
    limit: int = field(
        default=200, metadata={"doc": "Maximum number of rows to return."}
    )


@dataclass(frozen=True)
class StatePublishedRow:
    schema_version: str = field(metadata={"doc": "Published-state row schema version."})
    file_id: str = field(metadata={"doc": "Drive file ID."})
    md5: str = field(metadata={"doc": "MD5 checksum recorded at publish time."})
    published_at: int = field(
        metadata={"doc": "Unix timestamp when publishing completed."}
    )
    wp_post_id: int = field(metadata={"doc": "WordPress post ID."})
    wp_post_url: str = field(metadata={"doc": "WordPress post URL."})
    post_type: str = field(
        metadata={"doc": "WordPress post type slug used for this publish record."}
    )


@dataclass(frozen=True)
class StatePublishedListResponse:
    schema_version: str = field(
        metadata={"doc": "Published-state list response schema version."}
    )
    rows: List[StatePublishedRow] = field(
        metadata={"doc": "Published-state rows ordered by recency."}
    )


@dataclass(frozen=True)
class StateReportDownloadRouteGetRequest:
    schema_version: str = field(
        metadata={"doc": "Report-download route get request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    normalized_url: str = field(
        metadata={"doc": "Normalized URL used as the route-memory key."}
    )


@dataclass(frozen=True)
class StateReportDownloadRouteRecordRequest:
    schema_version: str = field(
        metadata={"doc": "Report-download route record request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for processing state."})
    normalized_url: str = field(
        metadata={"doc": "Normalized URL used as the route-memory key."}
    )
    source_url: str = field(
        metadata={"doc": "Last source URL observed for the normalized route key."}
    )
    route_kind: str = field(
        metadata={"doc": "Detected route kind: `pdf_download` or `email_delivery`."}
    )
    route_summary: str = field(
        metadata={"doc": "Remembered summary of the best-known route for this URL."}
    )
    outcome: str = field(
        metadata={
            "doc": "Observed outcome: `downloaded`, `email_requested`, or `email_required`."
        }
    )
    last_downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Last downloaded local file path for this route, if any."},
    )
    last_final_page_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Last final browser URL observed for this route, if any."},
    )


@dataclass(frozen=True)
class StateReportDownloadRouteResponse:
    schema_version: str = field(
        metadata={"doc": "Report-download route response schema version."}
    )
    normalized_url: str = field(
        metadata={"doc": "Normalized URL used as the route-memory key."}
    )
    source_url: str = field(
        metadata={"doc": "Last source URL observed for the normalized route key."}
    )
    route_kind: str = field(
        metadata={"doc": "Detected route kind: `pdf_download` or `email_delivery`."}
    )
    route_summary: str = field(
        metadata={"doc": "Remembered summary of the best-known route for this URL."}
    )
    outcome: str = field(
        metadata={
            "doc": "Last observed outcome: `downloaded`, `email_requested`, or `email_required`."
        }
    )
    updated_at: int = field(
        metadata={
            "doc": "Unix timestamp when the route-memory record was last updated."
        }
    )
    last_downloaded_file_path: Optional[str] = field(
        default=None,
        metadata={"doc": "Last downloaded local file path for this route, if any."},
    )
    last_final_page_url: Optional[str] = field(
        default=None,
        metadata={"doc": "Last final browser URL observed for this route, if any."},
    )


@dataclass(frozen=True)
class WorkflowControlObservationWriteRequest:
    schema_version: str = field(
        metadata={"doc": "Workflow-control observation write request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for workflow-control state."})
    observation: WorkflowControlObservation = field(
        metadata={"doc": "Workflow-control observation to persist."}
    )


@dataclass(frozen=True)
class WorkflowControlObservationWriteResponse:
    schema_version: str = field(
        metadata={"doc": "Workflow-control observation write response schema version."}
    )
    observation: WorkflowControlObservation = field(
        metadata={"doc": "Persisted workflow-control observation."}
    )


@dataclass(frozen=True)
class WorkflowControlObservationListRequest:
    schema_version: str = field(
        metadata={"doc": "Workflow-control observation list request schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for workflow-control state."})
    workflow: str = field(
        default="",
        metadata={"doc": "Optional workflow filter."},
    )
    publisher: str = field(
        default="",
        metadata={"doc": "Optional publisher filter."},
    )
    observed_after_utc: str = field(
        default="",
        metadata={"doc": "Optional lower-bound UTC timestamp for TTL filtering."},
    )
    limit: int = field(
        default=200,
        metadata={"doc": "Maximum observations to return."},
    )


@dataclass(frozen=True)
class WorkflowControlObservationListResponse:
    schema_version: str = field(
        metadata={"doc": "Workflow-control observation list response schema version."}
    )
    observations: List[WorkflowControlObservation] = field(
        metadata={"doc": "Persisted observations sorted newest first."}
    )


@dataclass(frozen=True)
class MailDeliveryRequest:
    schema_version: str = field(
        metadata={"doc": "Mail-delivery request schema version."}
    )
    request_id: int = field(metadata={"doc": "Durable state DB request identifier."})
    idempotency_key: str = field(
        metadata={"doc": "Stable key that prevents duplicate deferred mail requests."}
    )
    source_url: str = field(metadata={"doc": "Original gated report URL."})
    report_title: str = field(
        metadata={"doc": "Report title used for delivery matching."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher used for delivery matching."}
    )
    delivery_email: str = field(
        metadata={"doc": "Mailbox address submitted to the form."}
    )
    requested_after_utc: str = field(
        metadata={"doc": "UTC watermark; older matching messages are ignored."}
    )
    route_family: str = field(
        metadata={"doc": "Browser route family that requested mail."}
    )
    route_history_id: str = field(
        metadata={"doc": "Optional browser route-history identifier for provenance."}
    )
    status: str = field(
        metadata={"doc": "Request status: pending, succeeded, failed, or abandoned."}
    )
    next_attempt_after_utc: str = field(
        metadata={"doc": "UTC timestamp when the request is eligible for another poll."}
    )
    attempt_count: int = field(
        metadata={"doc": "Mailbox acquisition attempts consumed."}
    )
    provider_cursor: str = field(
        metadata={"doc": "Provider-specific incremental cursor or watermark."}
    )
    seen_provider_message_ids: List[str] = field(
        metadata={"doc": "Provider message IDs already inspected for this request."}
    )
    outcome: str = field(metadata={"doc": "Last acquisition outcome taxonomy value."})
    selected_message_id: str = field(
        metadata={"doc": "Provider message ID that produced a successful acquisition."}
    )
    downloaded_file_path: str = field(
        metadata={"doc": "Local acquired artifact path when successful."}
    )
    error_code: str = field(metadata={"doc": "Last typed error code, if any."})
    created_at_utc: str = field(metadata={"doc": "UTC creation timestamp."})
    updated_at_utc: str = field(metadata={"doc": "UTC update timestamp."})


@dataclass(frozen=True)
class MailDeliveryRequestUpsertRequest:
    schema_version: str = field(metadata={"doc": "Mail request upsert schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for mail-delivery state."})
    idempotency_key: str = field(
        metadata={"doc": "Stable key that prevents duplicate deferred mail requests."}
    )
    source_url: str = field(metadata={"doc": "Original gated report URL."})
    report_title: str = field(
        metadata={"doc": "Report title used for delivery matching."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher used for delivery matching."}
    )
    delivery_email: str = field(
        metadata={"doc": "Mailbox address submitted to the form."}
    )
    requested_after_utc: str = field(
        metadata={"doc": "UTC watermark; older matching messages are ignored."}
    )
    route_family: str = field(
        metadata={"doc": "Browser route family that requested mail."}
    )
    route_history_id: str = field(
        default="",
        metadata={"doc": "Optional browser route-history identifier for provenance."},
    )


@dataclass(frozen=True)
class MailDeliveryRequestUpsertResponse:
    schema_version: str = field(
        metadata={"doc": "Mail request upsert response version."}
    )
    request: MailDeliveryRequest = field(metadata={"doc": "Durable request row."})
    created: bool = field(metadata={"doc": "True when a new row was inserted."})


@dataclass(frozen=True)
class MailDeliveryRequestListDueRequest:
    schema_version: str = field(
        metadata={"doc": "Due mail request list schema version."}
    )
    state_db: str = field(metadata={"doc": "SQLite path for mail-delivery state."})
    now_utc: str = field(metadata={"doc": "UTC timestamp used for due filtering."})
    limit: int = field(default=50, metadata={"doc": "Maximum due rows to return."})


@dataclass(frozen=True)
class MailDeliveryRequestListDueResponse:
    schema_version: str = field(
        metadata={"doc": "Due mail request list response version."}
    )
    requests: List[MailDeliveryRequest] = field(
        metadata={"doc": "Due pending mail-delivery requests ordered oldest first."}
    )


@dataclass(frozen=True)
class MailDeliveryRequestMarkAttemptRequest:
    schema_version: str = field(metadata={"doc": "Mail attempt update schema version."})
    state_db: str = field(metadata={"doc": "SQLite path for mail-delivery state."})
    request_id: int = field(metadata={"doc": "Durable mail request identifier."})
    status: str = field(metadata={"doc": "Updated request status."})
    next_attempt_after_utc: str = field(
        metadata={"doc": "UTC timestamp when the next attempt is eligible."}
    )
    provider_cursor: str = field(metadata={"doc": "Provider incremental cursor."})
    seen_provider_message_ids: List[str] = field(
        metadata={"doc": "Provider messages inspected by this request."}
    )
    outcome: str = field(metadata={"doc": "Last acquisition outcome taxonomy value."})
    selected_message_id: str = field(metadata={"doc": "Selected mailbox message ID."})
    downloaded_file_path: str = field(metadata={"doc": "Downloaded artifact path."})
    error_code: str = field(metadata={"doc": "Last typed error code."})


@dataclass(frozen=True)
class MailDeliveryRequestMarkAttemptResponse:
    schema_version: str = field(
        metadata={"doc": "Mail attempt update response version."}
    )
    request: MailDeliveryRequest = field(metadata={"doc": "Updated request row."})


@dataclass(frozen=True)
class MailboxCandidateRejection:
    schema_version: str = field(
        metadata={"doc": "Mailbox candidate rejection evidence schema version."}
    )
    rejection_id: int = field(metadata={"doc": "Durable rejection row ID."})
    request_id: int = field(metadata={"doc": "Mail-delivery request scope."})
    provider_message_id: str = field(metadata={"doc": "Mailbox provider message ID."})
    sender: str = field(metadata={"doc": "Sanitized sender display."})
    source_host: str = field(metadata={"doc": "Original request/source host."})
    link_host: str = field(metadata={"doc": "Rejected candidate link host."})
    publisher_affinity: str = field(metadata={"doc": "Publisher affinity decision."})
    title_token_overlap: float = field(metadata={"doc": "Title-token overlap score."})
    reason_code: str = field(metadata={"doc": "Stable rejection reason code."})
    expires_at_utc: str = field(metadata={"doc": "TTL expiry timestamp."})
    created_at_utc: str = field(metadata={"doc": "UTC creation timestamp."})


@dataclass(frozen=True)
class MailboxCandidateRejectionRecordRequest:
    schema_version: str = field(metadata={"doc": "Rejection record request version."})
    state_db: str = field(metadata={"doc": "SQLite state DB path."})
    request_id: int = field(metadata={"doc": "Mail-delivery request scope."})
    provider_message_id: str = field(metadata={"doc": "Mailbox provider message ID."})
    sender: str = field(metadata={"doc": "Sanitized or raw sender display."})
    source_host: str = field(metadata={"doc": "Original request/source host."})
    link_host: str = field(metadata={"doc": "Rejected candidate link host."})
    publisher_affinity: str = field(metadata={"doc": "Publisher affinity decision."})
    title_token_overlap: float = field(metadata={"doc": "Title-token overlap score."})
    reason_code: str = field(metadata={"doc": "Stable rejection reason code."})
    expires_at_utc: str = field(metadata={"doc": "TTL expiry timestamp."})


@dataclass(frozen=True)
class MailboxCandidateRejectionListRequest:
    schema_version: str = field(metadata={"doc": "Rejection list request version."})
    state_db: str = field(metadata={"doc": "SQLite state DB path."})
    request_id: int = field(metadata={"doc": "Mail-delivery request scope."})
    now_utc: str = field(metadata={"doc": "UTC timestamp for TTL filtering."})
    limit: int = field(default=50, metadata={"doc": "Maximum rows to return."})


@dataclass(frozen=True)
class MailboxCandidateRejectionListResponse:
    schema_version: str = field(metadata={"doc": "Rejection list response version."})
    rejections: List[MailboxCandidateRejection] = field(
        metadata={"doc": "Active request-scoped mailbox candidate rejections."}
    )
