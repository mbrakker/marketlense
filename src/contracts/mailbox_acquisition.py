from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from src.contracts.browser_download import (
    BrowserDownloadSettings,
    ReportDownloadOrchestratorResult,
)


@dataclass(frozen=True)
class MailboxAcquisitionSettings:
    schema_version: str = field(
        metadata={"doc": "Mailbox acquisition settings schema version."}
    )
    provider: str = field(
        metadata={"doc": "Mailbox provider used for report-delivery polling."}
    )
    output_dir: str = field(
        metadata={"doc": "Root output directory for mailbox-acquisition artifacts."}
    )
    search_window_minutes: int = field(
        metadata={"doc": "Lookback window in minutes for delivered report mail."}
    )
    max_results: int = field(
        metadata={"doc": "Maximum mailbox messages inspected per polling attempt."}
    )
    poll_timeout_seconds: float = field(
        metadata={"doc": "Maximum wall-clock seconds to wait for delayed delivery."}
    )
    poll_interval_seconds: float = field(
        metadata={"doc": "Delay between mailbox polls when delivery has not arrived."}
    )
    gmail_oauth_client_path: str = field(
        metadata={"doc": "OAuth client JSON path for Gmail mailbox access."}
    )
    gmail_oauth_token_path: str = field(
        metadata={"doc": "OAuth token JSON path for Gmail mailbox access."}
    )
    gmail_user_id: str = field(
        metadata={"doc": "Gmail user ID passed to Gmail API calls."}
    )
    imap_host: str = field(metadata={"doc": "IMAP host for IMAP mailbox access."})
    imap_port: int = field(metadata={"doc": "IMAP SSL port."})
    imap_user: str = field(metadata={"doc": "IMAP username."})
    imap_password: str = field(metadata={"doc": "IMAP password loaded from env."})
    imap_mailbox: str = field(metadata={"doc": "IMAP mailbox folder to inspect."})


@dataclass(frozen=True)
class MailboxMessage:
    schema_version: str = field(
        metadata={"doc": "Mailbox message schema version."}
    )
    provider_message_id: str = field(
        metadata={"doc": "Provider-specific stable mailbox message ID."}
    )
    subject: str = field(metadata={"doc": "Message subject."})
    sender: str = field(metadata={"doc": "Message sender header."})
    received_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the message was received."}
    )
    text_body: str = field(metadata={"doc": "Bounded plain-text body excerpt."})
    html_body: str = field(metadata={"doc": "Bounded HTML body excerpt."})
    links: list[str] = field(
        metadata={"doc": "Distinct absolute links extracted from message bodies."}
    )
    attachment_file_names: list[str] = field(
        metadata={"doc": "Attachment file names present on the message."}
    )
    attachment_artifacts: list["MailboxAttachmentArtifact"] = field(
        default_factory=list,
        metadata={
            "doc": "Materialized PDF artifacts extracted from message attachments."
        },
    )


@dataclass(frozen=True)
class MailboxAttachment:
    schema_version: str = field(metadata={"doc": "Mailbox attachment schema version."})
    file_name: str = field(metadata={"doc": "Attachment file name from the message."})
    content_type: str = field(metadata={"doc": "Attachment content type."})
    payload: bytes = field(metadata={"doc": "Raw attachment bytes."})


@dataclass(frozen=True)
class MailboxAttachmentArtifact:
    schema_version: str = field(
        metadata={"doc": "Mailbox attachment artifact schema version."}
    )
    file_name: str = field(metadata={"doc": "Materialized PDF file name."})
    content_type: str = field(metadata={"doc": "Materialized content type."})
    size_bytes: int = field(metadata={"doc": "Materialized file size in bytes."})
    path: str = field(metadata={"doc": "Absolute local materialized file path."})
    source_container_file_name: str = field(
        metadata={"doc": "ZIP file name when the PDF was extracted from an archive."}
    )


@dataclass(frozen=True)
class MailboxAttachmentMaterializeRequest:
    schema_version: str = field(
        metadata={"doc": "Mailbox attachment materialization request schema version."}
    )
    settings: MailboxAcquisitionSettings = field(
        metadata={"doc": "Mailbox acquisition settings including output directory."}
    )
    provider_message_id: str = field(
        metadata={"doc": "Provider message ID used to namespace local artifacts."}
    )
    attachments: list[MailboxAttachment] = field(
        metadata={"doc": "Raw message attachments to materialize."}
    )


@dataclass(frozen=True)
class MailboxAttachmentMaterializeResponse:
    schema_version: str = field(
        metadata={"doc": "Mailbox attachment materialization response schema version."}
    )
    artifacts: list[MailboxAttachmentArtifact] = field(
        metadata={"doc": "Materialized PDF artifacts."}
    )


@dataclass(frozen=True)
class MailboxSearchRequest:
    schema_version: str = field(
        metadata={"doc": "Mailbox search request schema version."}
    )
    settings: MailboxAcquisitionSettings = field(
        metadata={"doc": "Mailbox settings used for this search."}
    )
    delivery_email: Optional[str] = field(
        metadata={"doc": "Delivery email submitted to the publisher form."}
    )
    source_url: str = field(
        metadata={"doc": "Original report-form URL that triggered email delivery."}
    )
    report_title: str = field(
        metadata={"doc": "Report title used to rank delivered mailbox links."}
    )
    publisher_name: str = field(
        metadata={"doc": "Publisher name used to rank delivered mailbox links."}
    )
    query_terms: list[str] = field(
        metadata={"doc": "Sanitized report/publisher terms used in mailbox search."}
    )
    seen_provider_message_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Provider message IDs already inspected for this request."},
    )


@dataclass(frozen=True)
class MailboxSearchResult:
    schema_version: str = field(
        metadata={"doc": "Mailbox search result schema version."}
    )
    provider: str = field(metadata={"doc": "Provider used for the search."})
    searched_at_utc: str = field(
        metadata={"doc": "UTC timestamp when the search completed."}
    )
    query: str = field(metadata={"doc": "Provider query used for the search."})
    messages: list[MailboxMessage] = field(
        metadata={"doc": "Messages returned by the mailbox search."}
    )


@dataclass(frozen=True)
class MailReportLinkCandidate:
    schema_version: str = field(
        metadata={"doc": "Selected mailbox report-link candidate schema version."}
    )
    url: str = field(metadata={"doc": "Candidate report URL extracted from mail."})
    score: float = field(metadata={"doc": "Deterministic relevance score."})
    reason: str = field(metadata={"doc": "Deterministic reason for selection."})
    provider_message_id: str = field(
        metadata={"doc": "Mailbox message that supplied this link."}
    )


@dataclass(frozen=True)
class MailReportAcquisitionRequest:
    schema_version: str = field(
        metadata={"doc": "Mail report acquisition request schema version."}
    )
    source_url: str = field(
        metadata={"doc": "Original report-form URL that requested email delivery."}
    )
    report_title: str = field(metadata={"doc": "Report title to acquire."})
    publisher_name: str = field(metadata={"doc": "Publisher name."})
    delivery_email: Optional[str] = field(
        metadata={"doc": "Submitted delivery email address."}
    )
    reports_db: str = field(
        metadata={"doc": "Reports DB used by follow-up report-download attempts."}
    )
    mailbox_settings: MailboxAcquisitionSettings = field(
        metadata={"doc": "Mailbox polling settings."}
    )
    browser_download_settings: BrowserDownloadSettings = field(
        metadata={"doc": "Browser/report-download settings for delivered links."}
    )
    requested_after_utc: Optional[str] = field(
        default=None,
        metadata={
            "doc": "Optional UTC request watermark; messages received before this instant are ignored."
        },
    )
    seen_provider_message_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Provider message IDs already inspected for this request."},
    )


@dataclass(frozen=True)
class MailReportAcquisitionResult:
    schema_version: str = field(
        metadata={"doc": "Mail report acquisition result schema version."}
    )
    source_url: str = field(metadata={"doc": "Original report-form URL."})
    outcome: str = field(
        metadata={"doc": "Observed outcome: downloaded, captured, or not_arrived_yet."}
    )
    mailbox_poll_count: int = field(
        metadata={"doc": "Number of mailbox polls attempted."}
    )
    selected_report_url: Optional[str] = field(
        metadata={"doc": "Delivered report URL selected from mailbox messages."}
    )
    selected_message_id: Optional[str] = field(
        metadata={"doc": "Provider message ID that supplied the selected URL."}
    )
    downloaded_file_path: Optional[str] = field(
        metadata={"doc": "Downloaded report file path when acquisition succeeded."}
    )
    report_download_result: Optional[ReportDownloadOrchestratorResult] = field(
        metadata={"doc": "Follow-up report-download result for the selected URL."}
    )
    acquisition_result_taxonomy: str = field(
        default="",
        metadata={
            "doc": "Fine-grained acquisition taxonomy such as mailbox_attachment_pdf or mailbox_body_pdf_link."
        },
    )
    seen_provider_message_ids: list[str] = field(
        default_factory=list,
        metadata={"doc": "Provider message IDs inspected during this acquisition."},
    )
