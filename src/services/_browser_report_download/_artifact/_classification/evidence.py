"""Deterministic terminal route, outcome, blocker, and confirmation classification."""

from __future__ import annotations

import re

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadNetworkEvent,
    BrowserReportDownloadRequest,
)
from src.services._browser_report_download._artifact import (
    _VERIFIED_EMAIL_SIGNAL_MARKERS,
)
from src.services._browser_report_download._artifact.evidence import (
    _extract_visible_text_from_html,
)
from src.services._browser_report_download.models import BrowserUseAgentResult
from src.services._browser_report_download.request import (
    resolve_effective_identity_fields,
)
from src.services._config_service.identity import (
    identity_field_match_tokens,
    normalize_browser_download_identity_key,
)
from src.utils.url_utils import normalize_url

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


def _normalize_encountered_form_fields(raw_fields: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_field in raw_fields:
        token = str(raw_field or "").strip()
        if not token:
            continue
        dedupe_key = token.casefold()
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        normalized.append(token)
    return normalized


def _extract_form_fields_from_html(html: str) -> list[str]:
    labels: list[str] = []
    for match in re.finditer(r"(?is)<label[^>]*>(.*?)</label>", str(html or "")):
        token = _extract_visible_text_from_html(match.group(1), max_chars=80)
        if token:
            labels.append(token)
    for pattern in (
        r'(?i)\bplaceholder=["\']([^"\']+)["\']',
        r'(?i)\bname=["\']([^"\']+)["\']',
        r'(?i)\baria-label=["\']([^"\']+)["\']',
    ):
        for match in re.finditer(pattern, str(html or "")):
            token = str(match.group(1) or "").strip()
            if token:
                labels.append(token)
    return _normalize_encountered_form_fields(labels)


def _html_contains_form(html: str) -> bool:
    token = str(html or "").casefold()
    return (
        "<form" in token
        or "<input" in token
        or "<select" in token
        or "<textarea" in token
    )


def _html_contains_submit_control(html: str) -> bool:
    token = str(html or "").casefold()
    return 'type="submit"' in token or "type='submit'" in token or ">submit<" in token


def _build_confirmation_evidence(
    *,
    agent_result: BrowserUseAgentResult,
    final_url: str,
    network_events: list[BrowserDownloadNetworkEvent],
) -> BrowserDownloadConfirmationEvidence:
    visible_confirmation_text = str(agent_result.post_submit_message or "").strip()
    effective_final_url = str(final_url or agent_result.final_page_url or "").strip()
    url_changed = bool(agent_result.confirmation_url_changed) or (
        bool(effective_final_url)
        and bool(str(agent_result.final_page_url or "").strip())
        and normalize_url(effective_final_url)
        != normalize_url(str(agent_result.final_page_url or "").strip())
    )
    signal_labels = _build_confirmation_signal_labels(
        visible_confirmation_text=visible_confirmation_text,
        final_page_url=effective_final_url,
        url_changed=url_changed,
        submit_button_state=str(agent_result.submit_button_state or "").strip()
        or "unchanged",
        form_disappeared=bool(agent_result.form_disappeared),
        email_submission_completed=agent_result.email_submission_completed,
        network_signal_labels=_build_network_confirmation_signal_labels(
            network_events=network_events,
        ),
    )
    return BrowserDownloadConfirmationEvidence(
        schema_version="1.0",
        url_changed=url_changed,
        visible_confirmation_text=visible_confirmation_text,
        submit_button_state=str(agent_result.submit_button_state or "").strip()
        or "unchanged",
        form_disappeared=bool(agent_result.form_disappeared),
        final_page_url=effective_final_url,
        confirmation_score=len(signal_labels),
        signal_labels=signal_labels,
    )


def _upgrade_confirmation_evidence_from_terminal_html(
    *,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
    email_submission_completed: bool | None,
    encountered_form_fields: list[str],
    html: str,
) -> BrowserDownloadConfirmationEvidence:
    token = str(html or "").strip()
    if not token:
        return confirmation_evidence
    terminal_confirmation_text = _resolve_terminal_confirmation_text_from_html(
        html=token,
        fallback_text=confirmation_evidence.visible_confirmation_text,
    )
    if (
        email_submission_completed is not True
        and not encountered_form_fields
        and not _message_indicates_confirmed_email_delivery(terminal_confirmation_text)
    ):
        return confirmation_evidence
    terminal_text_confirms_delivery = (
        _message_indicates_confirmed_email_delivery(terminal_confirmation_text)
        or _message_indicates_email_delivery(terminal_confirmation_text)
        or _message_indicates_form_success(terminal_confirmation_text)
    )
    form_disappeared = confirmation_evidence.form_disappeared or (
        bool(encountered_form_fields)
        and not _html_contains_form(token)
        and terminal_text_confirms_delivery
    )
    if (
        terminal_confirmation_text == confirmation_evidence.visible_confirmation_text
        and form_disappeared == confirmation_evidence.form_disappeared
    ):
        return confirmation_evidence
    signal_labels = _build_confirmation_signal_labels(
        visible_confirmation_text=terminal_confirmation_text,
        final_page_url=confirmation_evidence.final_page_url,
        url_changed=confirmation_evidence.url_changed,
        submit_button_state=confirmation_evidence.submit_button_state,
        form_disappeared=form_disappeared,
        email_submission_completed=(
            True
            if (
                email_submission_completed is True
                or _message_indicates_email_delivery(terminal_confirmation_text)
                or _message_indicates_form_success(terminal_confirmation_text)
            )
            else email_submission_completed
        ),
    )
    return BrowserDownloadConfirmationEvidence(
        schema_version=confirmation_evidence.schema_version,
        url_changed=confirmation_evidence.url_changed,
        visible_confirmation_text=terminal_confirmation_text,
        submit_button_state=confirmation_evidence.submit_button_state,
        form_disappeared=form_disappeared,
        final_page_url=confirmation_evidence.final_page_url,
        confirmation_score=len(signal_labels),
        signal_labels=signal_labels,
    )


def _resolve_terminal_confirmation_text_from_html(
    *,
    html: str,
    fallback_text: str,
) -> str:
    terminal_text = _extract_visible_text_from_html(html, max_chars=800)
    if not terminal_text:
        return fallback_text
    if _message_indicates_email_delivery(
        terminal_text
    ) or _message_indicates_form_success(terminal_text):
        return terminal_text
    if _message_indicates_transient_submit_state(
        fallback_text
    ) and not _message_indicates_transient_submit_state(terminal_text):
        return terminal_text
    return fallback_text


def _build_network_confirmation_signal_labels(
    *,
    network_events: list[BrowserDownloadNetworkEvent],
) -> list[str]:
    labels: list[str] = []
    if any(event.signal_kind == "submission_request" for event in network_events):
        labels.append("network_submission_request")
    if any(event.signal_kind == "confirmation_request" for event in network_events):
        labels.append("network_confirmation_request")
    return labels


def _resolve_blocked_reason(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
    agent_result: BrowserUseAgentResult,
    encountered_form_fields: list[str],
    final_url: str,
) -> str | None:
    post_submit_message = str(agent_result.post_submit_message or "").strip()
    if _message_indicates_confirmed_email_delivery(post_submit_message):
        return None
    explicit = str(agent_result.blocked_reason or "").strip().lower()
    route_kind_token = str(agent_result.route_kind or "").strip().lower()
    blocker_haystack = " ".join(
        [
            post_submit_message,
            str(agent_result.blocked_reason_detail or "").strip(),
            str(agent_result.final_page_title or "").strip(),
        ]
    ).casefold()
    if explicit:
        normalized_explicit = _normalize_explicit_blocked_reason(
            request=request,
            delivery_email=delivery_email,
            explicit_blocked_reason=explicit,
            encountered_form_fields=encountered_form_fields,
            blocker_haystack=blocker_haystack,
        )
        if normalized_explicit:
            return normalized_explicit
    if route_kind_token in _BLOCKED_REASONS:
        normalized_kind = _normalize_explicit_blocked_reason(
            request=request,
            delivery_email=delivery_email,
            explicit_blocked_reason=route_kind_token,
            encountered_form_fields=encountered_form_fields,
            blocker_haystack=blocker_haystack,
        )
        if normalized_kind:
            return normalized_kind
    if _message_indicates_email_delivery(post_submit_message):
        return None
    if agent_result.email_submission_completed is True:
        return None
    if any(marker in blocker_haystack for marker in _EMAIL_DOMAIN_BLOCK_MARKERS):
        return "blocked_email_domain"
    if any(marker in blocker_haystack for marker in _CAPTCHA_MARKERS):
        return "blocked_captcha"
    if any(marker in blocker_haystack for marker in _STATIC_ARCHIVE_MARKERS) or any(
        marker in str(final_url or "").casefold() for marker in _STATIC_ARCHIVE_MARKERS
    ):
        return "blocked_static_archive"
    if _has_missing_identity_field(
        request=request,
        delivery_email=delivery_email,
        encountered_form_fields=encountered_form_fields,
    ):
        return "blocked_missing_identity_field"
    if _has_unconfigured_enum_field(
        request=request,
        encountered_form_fields=encountered_form_fields,
    ):
        return "blocked_unknown_required_enum"
    if encountered_form_fields and _message_indicates_unknown_required_enum(
        blocker_haystack
    ):
        return "blocked_unknown_required_enum"
    return None


def _resolve_blocked_reason_detail(
    *,
    agent_result: BrowserUseAgentResult,
    blocked_reason: str | None,
) -> str | None:
    if not blocked_reason:
        return None
    detail = str(agent_result.blocked_reason_detail or "").strip()
    if detail:
        return detail
    return (
        str(
            agent_result.post_submit_message or agent_result.terminal_text_excerpt or ""
        ).strip()
        or blocked_reason
    )


def _count_confirmation_signals(
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
) -> int:
    if confirmation_evidence.signal_labels:
        return len(confirmation_evidence.signal_labels)
    count = 0
    if _message_indicates_email_delivery(
        confirmation_evidence.visible_confirmation_text
    ):
        count += 1
    elif _message_indicates_form_success(
        confirmation_evidence.visible_confirmation_text
    ):
        count += 1
    if confirmation_evidence.url_changed and _url_indicates_confirmation(
        confirmation_evidence.final_page_url
    ):
        count += 1
    if confirmation_evidence.submit_button_state in {"disabled", "replaced"}:
        count += 1
    if confirmation_evidence.form_disappeared:
        count += 1
    if "network_submission_request" in confirmation_evidence.signal_labels:
        count += 1
    if "network_confirmation_request" in confirmation_evidence.signal_labels:
        count += 1
    return count


def _confirmation_evidence_verifies_email_delivery(
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
) -> bool:
    signal_labels = set(confirmation_evidence.signal_labels)
    if _message_indicates_confirmed_email_delivery(
        confirmation_evidence.visible_confirmation_text
    ):
        return True
    if _message_indicates_transient_submit_state(
        confirmation_evidence.visible_confirmation_text
    ) and not (
        signal_labels
        & {
            "delivery_text",
            "success_text",
            "success_url",
            "form_disappeared",
            "network_confirmation_request",
        }
    ):
        return False
    return _count_confirmation_signals(confirmation_evidence) >= 2 and (
        "submit_observed" in signal_labels
        or any(marker in signal_labels for marker in _VERIFIED_EMAIL_SIGNAL_MARKERS)
    )


def _build_confirmation_signal_labels(
    *,
    visible_confirmation_text: str,
    final_page_url: str,
    url_changed: bool,
    submit_button_state: str,
    form_disappeared: bool,
    email_submission_completed: bool | None,
    network_signal_labels: list[str] | None = None,
) -> list[str]:
    labels: list[str] = []
    if email_submission_completed is True:
        labels.append("submit_observed")
    if _message_indicates_email_delivery(visible_confirmation_text):
        labels.append("delivery_text")
    elif _message_indicates_form_success(visible_confirmation_text):
        labels.append("success_text")
    if url_changed and _url_indicates_confirmation(final_page_url):
        labels.append("success_url")
    if submit_button_state in {"disabled", "replaced"}:
        labels.append(f"button_state_{submit_button_state}")
    if form_disappeared:
        labels.append("form_disappeared")
    for label in network_signal_labels or []:
        if label not in labels:
            labels.append(label)
    return labels


def _message_indicates_email_delivery(message: str | None) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    if any(
        marker in token
        for marker in (
            "fill out the form",
            "fill out form",
            "form below",
            "complete the form",
            "submit the form",
        )
    ):
        return False
    email_markers = ("email", "inbox", "mailbox", "mail")
    delivery_markers = (
        "check",
        "sent",
        "send",
        "receive",
        "receiving",
        "delivered",
        "delivery",
        "download link",
        "link",
    )
    return any(marker in token for marker in email_markers) and any(
        marker in token for marker in delivery_markers
    )


def _message_indicates_transient_submit_state(message: str) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    if _message_indicates_confirmed_email_delivery(token) or any(
        marker in token for marker in _FORM_SUCCESS_TEXT_MARKERS
    ):
        return False
    return any(marker in token for marker in _TRANSIENT_SUBMIT_MESSAGE_MARKERS)


def _message_indicates_confirmed_email_delivery(message: str | None) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    strong_markers = (
        "sent directly to your inbox",
        "sent to your inbox",
        "sent to your email",
        "will be sent to your inbox",
        "will be sent to your email",
        "will be sent directly to your inbox",
        "copy of the report will be sent",
        "check your inbox",
        "download link",
        "emailed to you",
        "inbox shortly",
    )
    return any(marker in token for marker in strong_markers)


def _message_indicates_unknown_required_enum(message: str) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    required_markers = (
        "this field is required",
        "required field",
        "selection is required",
        "please select",
        "select an option",
        "choose an option",
        "dropdown",
        "not correctly filled",
        "not correctly selected",
        "did not resolve",
        "not confirmed",
        "valid lookup selection",
        "could not be successfully filled",
        "could not be successfully selected",
        "could not successfully select",
        "could not be selected",
        "failed to submit",
        "preventing form submission",
        "fill this field",
        "заполните это поле",
    )
    return any(marker in token for marker in required_markers) and any(
        marker in token for marker in _UNKNOWN_ENUM_MARKERS
    )


def _message_indicates_form_success(message: str) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    if _message_indicates_email_delivery(token):
        return True
    return any(marker in token for marker in _FORM_SUCCESS_TEXT_MARKERS)


def _url_indicates_confirmation(url: str) -> bool:
    lowered = str(url or "").strip().casefold()
    return any(marker in lowered for marker in _SUCCESS_URL_MARKERS)


def _has_missing_identity_field(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
    encountered_form_fields: list[str],
) -> bool:
    configured_tokens: set[str] = set()
    semantic_families: set[str] = set()
    for field in resolve_effective_identity_fields(request):
        value = str(field.value or "").strip()
        if field.key == "work_email" and delivery_email:
            value = delivery_email
        if not value:
            continue
        field_tokens = identity_field_match_tokens(field)
        configured_tokens.update(field_tokens)
        semantic_families.update(_identity_semantic_families(field_tokens))
    for field_name in encountered_form_fields:
        token = normalize_browser_download_identity_key(field_name)
        if not token:
            continue
        field_families = _identity_semantic_families({token})
        if "email" in field_families and "email" not in semantic_families:
            return True
        needs_direct_match = field_families & {
            "name",
            "company",
            "role",
            "phone",
            "website",
            "country",
            "city",
            "region",
        }
        if needs_direct_match and not (
            configured_tokens.intersection({token})
            or semantic_families & needs_direct_match
        ):
            return True
    return False


def _identity_semantic_families(tokens: set[str]) -> set[str]:
    families: set[str] = set()
    lowered = {
        str(token or "").strip().casefold()
        for token in tokens
        if str(token or "").strip()
    }
    if any("email" in token for token in lowered):
        families.add("email")
    if any(
        "name" in token or token in {"given", "surname", "family"} for token in lowered
    ):
        families.add("name")
    if any(
        marker in token
        for token in lowered
        for marker in ("company", "organization", "business", "employer", "workplace")
    ):
        families.add("company")
    if any(marker in token for token in lowered for marker in ("title", "role", "job")):
        families.add("role")
    if any(
        marker in token
        for token in lowered
        for marker in ("phone", "telephone", "mobile")
    ):
        families.add("phone")
    if any(
        marker in token for token in lowered for marker in ("website", "site", "domain")
    ):
        families.add("website")
    if any("country" in token for token in lowered):
        families.add("country")
    if any(marker in token for token in lowered for marker in ("city", "town")):
        families.add("city")
    if any(
        marker in token
        for token in lowered
        for marker in ("state", "region", "province")
    ):
        families.add("region")
    return families


def _normalize_explicit_blocked_reason(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
    explicit_blocked_reason: str,
    encountered_form_fields: list[str],
    blocker_haystack: str,
) -> str | None:
    token = str(explicit_blocked_reason or "").strip().lower()
    if token not in _BLOCKED_REASONS:
        return None
    if token == "blocked_missing_identity_field" and (
        _message_indicates_unknown_required_enum(blocker_haystack)
        or _message_mentions_enum_selection_failure(blocker_haystack)
    ):
        return "blocked_unknown_required_enum"
    if token == "blocked_missing_identity_field":
        if _has_missing_identity_field(
            request=request,
            delivery_email=delivery_email,
            encountered_form_fields=encountered_form_fields,
        ):
            return token
        return None
    if token != "blocked_unknown_required_enum":
        return token
    if any(marker in blocker_haystack for marker in _UNKNOWN_ENUM_MARKERS):
        return token
    if _has_unconfigured_enum_field(
        request=request,
        encountered_form_fields=encountered_form_fields,
    ) or _message_indicates_unknown_required_enum(blocker_haystack):
        return token
    if _has_missing_identity_field(
        request=request,
        delivery_email=delivery_email,
        encountered_form_fields=encountered_form_fields,
    ):
        return "blocked_missing_identity_field"
    return None


def _message_mentions_enum_selection_failure(message: str) -> bool:
    token = str(message or "").strip().casefold()
    if not token:
        return False
    if not any(marker in token for marker in _UNKNOWN_ENUM_MARKERS):
        return False
    failure_markers = (
        "could not",
        "failed",
        "failure",
        "not confirmed",
        "not properly",
        "not selected",
        "preventing",
        "submission",
        "unsuccessful",
    )
    return any(marker in token for marker in failure_markers)


def _has_unconfigured_enum_field(
    *,
    request: BrowserReportDownloadRequest,
    encountered_form_fields: list[str],
) -> bool:
    configured_tokens = {
        str(field.key or "").strip().casefold()
        for field in resolve_effective_identity_fields(request)
        if str(field.value or "").strip()
    }
    for field_name in encountered_form_fields:
        token = str(field_name or "").strip().casefold()
        if not token:
            continue
        if not any(marker in token for marker in _UNKNOWN_ENUM_MARKERS):
            continue
        normalized_token = re.sub(r"[^a-z0-9]+", "_", token).strip("_")
        if normalized_token not in configured_tokens:
            return True
    return False


def _resolve_salvaged_blocked_reason(
    *,
    request: BrowserReportDownloadRequest,
    delivery_email: str | None,
    encountered_form_fields: list[str],
    final_url: str,
    final_page_title: str,
    terminal_text_excerpt: str,
) -> str | None:
    haystack = " ".join(
        [
            str(final_page_title or "").strip(),
            str(terminal_text_excerpt or "").strip(),
            " ".join(encountered_form_fields),
        ]
    ).casefold()
    if any(marker in haystack for marker in _EMAIL_DOMAIN_BLOCK_MARKERS):
        return "blocked_email_domain"
    if any(marker in haystack for marker in _CAPTCHA_MARKERS):
        return "blocked_captcha"
    if any(marker in haystack for marker in _STATIC_ARCHIVE_MARKERS) or any(
        marker in str(final_url or "").casefold() for marker in _STATIC_ARCHIVE_MARKERS
    ):
        return "blocked_static_archive"
    if _has_missing_identity_field(
        request=request,
        delivery_email=delivery_email,
        encountered_form_fields=encountered_form_fields,
    ):
        return "blocked_missing_identity_field"
    if _has_unconfigured_enum_field(
        request=request,
        encountered_form_fields=encountered_form_fields,
    ):
        return "blocked_unknown_required_enum"
    return None


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
]
