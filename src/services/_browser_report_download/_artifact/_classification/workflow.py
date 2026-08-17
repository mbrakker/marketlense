"""Deterministic terminal route, outcome, blocker, and confirmation classification."""

from __future__ import annotations
from pathlib import Path
from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
)
from src.utils.errors import AppError

from .evidence import (
    _confirmation_evidence_verifies_email_delivery,
    _count_confirmation_signals,
)

_ROUTE_KINDS = {"pdf_download", "email_delivery", "onsite_report"}
_BLOCKED_REASONS = {
    "blocked_email_domain",
    "blocked_captcha",
    "blocked_static_archive",
    "blocked_missing_identity_field",
    "blocked_unknown_required_enum",
    "blocked_no_progress",
}
_ROUTE_SUMMARY_ACTION_MARKERS = (
    "open",
    "click",
    "fill",
    "enter",
    "submit",
    "select",
    "choose",
    "use",
    "wait",
    "download",
    "inspect",
    "apply",
    "expand",
    "navigate",
)
_ROUTE_SUMMARY_TARGET_MARKERS = (
    "button",
    "link",
    "page",
    "form",
    "field",
    "email",
    "report",
    "pdf",
    "cta",
    "tab",
    "filter",
    "modal",
    "screen",
    "prompt",
)
_SUCCESS_URL_MARKERS = ("thank", "success", "confirm", "complete", "done")
_FORM_SUCCESS_TEXT_MARKERS = (
    "thank you",
    "thanks for",
    "thanks.",
    "submission received",
    "request received",
    "form submitted",
    "successfully submitted",
)
_TRANSIENT_SUBMIT_MESSAGE_MARKERS = (
    "please wait",
    "submitting",
    "processing",
    "loading",
    "one moment",
)
_EMAIL_DOMAIN_BLOCK_MARKERS = (
    "business email",
    "work email",
    "corporate email",
    "company email",
    "valid business email",
    "professional email",
)
_CAPTCHA_MARKERS = ("captcha", "recaptcha", "hcaptcha", "i am human", "not a robot")
_STATIC_ARCHIVE_MARKERS = (
    "archived",
    "archive",
    "no longer available",
    "unavailable",
    "coming soon",
)
_UNKNOWN_ENUM_MARKERS = (
    "select",
    "choose",
    "dropdown",
    "industry",
    "country",
    "location",
    "state",
    "region",
    "department",
    "role",
    "job level",
)
_REPORT_NOT_FOUND_MARKERS = (
    "specific report",
    "not found",
    "0 matches found",
    "zero matches",
    "no matches found",
    "could not find",
    "unable to find",
)


def _classify_route_result(
    *,
    route_kind: str,
    downloaded_path: Path | None,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
    encountered_form_fields: list[str],
    email_submission_completed: bool | None,
    blocked_reason: str | None,
    onsite_capture_path: str | None,
    onsite_completeness_status: str | None,
) -> tuple[str, str, int]:
    confirmation_signal_count = _count_confirmation_signals(confirmation_evidence)
    if downloaded_path is not None:
        return "downloaded", "verified", confirmation_signal_count
    if route_kind == "onsite_report":
        if not onsite_capture_path or not Path(onsite_capture_path).is_file():
            raise AppError(
                code="browser_download_onsite_capture_missing",
                message="browser-use classified the route as an on-site report but no local capture artifact was found",
                retryable=True,
                context={"final_page_url": confirmation_evidence.final_page_url},
            )
        completeness = str(onsite_completeness_status or "").strip().lower()
        route_status = "verified" if completeness == "complete" else "inferred"
        return "captured", route_status, confirmation_signal_count
    if route_kind != "email_delivery":
        raise AppError(
            code="browser_download_missing_file",
            message="No PDF artifact was produced for a non-email route",
            retryable=True,
        )
    if blocked_reason:
        return "email_required", "inferred", confirmation_signal_count
    if _confirmation_evidence_verifies_email_delivery(confirmation_evidence):
        return "email_requested", "verified", confirmation_signal_count
    if email_submission_completed is True:
        return "email_required", "inferred", confirmation_signal_count
    if encountered_form_fields or email_submission_completed is False:
        return "email_required", "inferred", confirmation_signal_count
    raise AppError(
        code="browser_download_email_submission_missing",
        message="browser-use did not produce enough evidence to verify an email-gated route",
        retryable=True,
        context={"final_page_url": confirmation_evidence.final_page_url},
    )


__all__ = [
    "_classify_route_result",
]
