from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field

from pydantic import BaseModel, Field

from src.contracts.browser_download import (
    BrowserDownloadDialogEvidence,
    BrowserDownloadNetworkEvent,
)


@dataclass(frozen=True)
class BrowserAgentRunResult:
    schema_version: str
    raw_model_response: str
    final_page_url: str
    final_page_title: str
    final_page_html: str
    downloaded_files: list[str]
    attachment_paths: list[str]
    network_resource_urls: list[str]
    network_events: list[BrowserDownloadNetworkEvent]
    html_snapshot_path: str
    screenshot_path: str
    print_pdf_capture_path: str = ""
    print_pdf_capture_provenance: str = ""
    dialog_evidence: list[BrowserDownloadDialogEvidence] = dataclass_field(
        default_factory=list
    )


class BrowserUseRouteStep(BaseModel):
    index: int | None = Field(default=None)
    action: str | None = Field(default=None)
    target_text: str | None = Field(default=None)
    target_role: str | None = Field(default=None)
    target_url: str | None = Field(default=None)
    result: str | None = Field(default=None)
    expected_evidence: list[str] = Field(default_factory=list)
    observed_evidence: list[str] = Field(default_factory=list)
    verification_status: str | None = Field(default=None)
    locator_role: str | None = Field(
        default=None,
        description="Observed accessible role for the control, when available.",
    )
    locator_name: str | None = Field(
        default=None, description="Observed accessible name used with the role locator."
    )
    locator_label: str | None = Field(
        default=None, description="Observed visible or accessible form-field label."
    )
    locator_field_name: str | None = Field(
        default=None, description="Observed stable HTML form-control name."
    )
    locator_data_attribute: str | None = Field(
        default=None, description="Observed stable data attribute locator."
    )
    locator_css: str | None = Field(
        default=None,
        description="Observed CSS locator only when no semantic locator is available.",
    )
    locator_text: str | None = Field(
        default=None,
        description="Observed visible text locator only as a final fallback.",
    )
    identity_field_reference: str | None = Field(
        default=None,
        description="Configured identity key used for fill/select, for example `identity.delivery_email`; never return an identity value.",
    )
    expected_url_contains: str | None = Field(
        default=None, description="Observed URL substring after the verified action."
    )
    expected_text: str | None = Field(
        default=None,
        description="Observed visible postcondition text after the verified action.",
    )


class BrowserUseRequiredSelectEvidence(BaseModel):
    field_label: str = Field(description="Visible required select label.")
    field_name: str = Field(default="", description="HTML or accessibility name.")
    options: list[str] = Field(
        default_factory=list, description="Visible option labels."
    )
    selected_value: str = Field(
        default="",
        description="Visible option selected through an allowed fallback, when any.",
    )
    classifier_confidence: float = Field(
        default=0.0, description="Confidence that this is a required select."
    )


class BrowserUseAgentResult(BaseModel):
    route_kind: str = Field(
        description="Either `pdf_download`, `email_delivery`, or `onsite_report`."
    )
    route_summary: str | None = Field(
        default=None,
        description="Short description of the working clicks/forms for this URL.",
    )
    route_family: str | None = Field(
        default=None,
        description="Observed route family for this execution attempt when the agent can classify it.",
    )
    resolved_target_url: str | None = Field(
        default=None,
        description="Resolved target URL that produced the final artifact or email form state.",
    )
    final_page_url: str | None = Field(
        default=None,
        description="Final browser URL after the task completed.",
    )
    email_submission_completed: bool | None = Field(
        default=None,
        description="True only when an email-gated form was actually submitted.",
    )
    downloaded_file_path: str | None = Field(
        default=None,
        description="Absolute local path of the downloaded file when one was saved.",
    )
    downloaded_file_name: str | None = Field(
        default=None,
        description="Downloaded file name when available.",
    )
    downloaded_mime_type: str | None = Field(
        default=None,
        description="Downloaded file MIME type when known.",
    )
    encountered_form_fields: list[str] = Field(
        default_factory=list,
        description="Distinct form field labels or names encountered during the route.",
    )
    required_select_evidence: list[BrowserUseRequiredSelectEvidence] = Field(
        default_factory=list,
        description="Required-select evidence captured when no approved identity value matches.",
    )
    route_steps: list[BrowserUseRouteStep] = Field(
        default_factory=list,
        description="Ordered structured action trace for the successful route when the agent can provide it.",
    )
    post_submit_message: str | None = Field(
        default=None,
        description="Visible confirmation or status text shown after a form submission attempt.",
    )
    confirmation_url_changed: bool | None = Field(
        default=None,
        description="Whether the page URL changed after the submission or route-completing action.",
    )
    submit_button_state: str | None = Field(
        default=None,
        description="Observed submit-button state after submission, for example `disabled` or `replaced`.",
    )
    form_disappeared: bool | None = Field(
        default=None,
        description="Whether the form disappeared after submission.",
    )
    blocked_reason: str | None = Field(
        default=None,
        description="Typed blocker code when the flow is blocked instead of completed.",
    )
    blocked_reason_detail: str | None = Field(
        default=None,
        description="Human-readable blocker detail captured from the terminal state when available.",
    )
    final_page_title: str | None = Field(
        default=None,
        description="Observed final page title when available.",
    )
    terminal_text_excerpt: str | None = Field(
        default=None,
        description="Short visible text excerpt captured from the terminal page when available.",
    )
    traversed_page_urls: list[str] = Field(
        default_factory=list,
        description="Distinct page URLs traversed while reaching the terminal state.",
    )
    onsite_capture_path: str | None = Field(
        default=None,
        description="Absolute local path of the captured on-site report artifact when available.",
    )
    onsite_capture_format: str | None = Field(
        default=None,
        description="Stored on-site capture format when available.",
    )
    onsite_page_count: int | None = Field(
        default=None,
        description="Number of distinct pages or scroll segments captured for an on-site report when available.",
    )
    onsite_completeness_status: str | None = Field(
        default=None,
        description="On-site capture completeness verdict when available.",
    )
