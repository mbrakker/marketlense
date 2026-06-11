"""Deterministic terminal route, outcome, blocker, and confirmation classification."""

from __future__ import annotations

from src.services._browser_report_download._artifact._classification.evidence import (
    _normalize_encountered_form_fields,
    _extract_form_fields_from_html,
    _html_contains_form,
    _html_contains_submit_control,
    _build_confirmation_evidence,
    _upgrade_confirmation_evidence_from_terminal_html,
    _resolve_terminal_confirmation_text_from_html,
    _build_network_confirmation_signal_labels,
    _resolve_blocked_reason,
    _resolve_blocked_reason_detail,
    _count_confirmation_signals,
    _confirmation_evidence_verifies_email_delivery,
    _build_confirmation_signal_labels,
    _message_indicates_email_delivery,
    _message_indicates_transient_submit_state,
    _message_indicates_confirmed_email_delivery,
    _message_indicates_unknown_required_enum,
    _message_indicates_form_success,
    _url_indicates_confirmation,
    _has_missing_identity_field,
    _identity_semantic_families,
    _normalize_explicit_blocked_reason,
    _message_mentions_enum_selection_failure,
    _has_unconfigured_enum_field,
    _resolve_salvaged_blocked_reason,
)

from src.services._browser_report_download._artifact._classification.routes import (
    _resolve_route_summary,
    _is_page_load_failure_summary,
    _derive_route_summary,
    _is_semantic_route_summary,
    _resolve_route_kind,
    _resolve_route_steps,
    _looks_like_report_not_found_terminal,
    _agent_result_indicates_report_not_found,
    _normalize_agent_route_steps_for_completeness,
    _resolve_route_family,
    _canonical_route_family,
    _route_step_haystack,
)

from src.services._browser_report_download._artifact._classification.workflow import (
    _classify_route_result,
)

_ROUTE_KINDS = {"pdf_download", "email_delivery", "onsite_report"}
_BLOCKED_REASONS = {
    "blocked_email_domain",
    "blocked_captcha",
    "blocked_static_archive",
    "blocked_missing_identity_field",
    "blocked_unknown_required_enum",
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

__all__ = [
    "_normalize_encountered_form_fields",
    "_extract_form_fields_from_html",
    "_html_contains_form",
    "_html_contains_submit_control",
    "_build_confirmation_evidence",
    "_upgrade_confirmation_evidence_from_terminal_html",
    "_resolve_terminal_confirmation_text_from_html",
    "_build_network_confirmation_signal_labels",
    "_resolve_blocked_reason",
    "_resolve_blocked_reason_detail",
    "_count_confirmation_signals",
    "_confirmation_evidence_verifies_email_delivery",
    "_build_confirmation_signal_labels",
    "_message_indicates_email_delivery",
    "_message_indicates_transient_submit_state",
    "_message_indicates_confirmed_email_delivery",
    "_message_indicates_unknown_required_enum",
    "_message_indicates_form_success",
    "_url_indicates_confirmation",
    "_has_missing_identity_field",
    "_identity_semantic_families",
    "_normalize_explicit_blocked_reason",
    "_message_mentions_enum_selection_failure",
    "_has_unconfigured_enum_field",
    "_resolve_salvaged_blocked_reason",
    "_resolve_route_summary",
    "_is_page_load_failure_summary",
    "_derive_route_summary",
    "_is_semantic_route_summary",
    "_resolve_route_kind",
    "_resolve_route_steps",
    "_looks_like_report_not_found_terminal",
    "_agent_result_indicates_report_not_found",
    "_normalize_agent_route_steps_for_completeness",
    "_resolve_route_family",
    "_canonical_route_family",
    "_route_step_haystack",
    "_classify_route_result",
]
