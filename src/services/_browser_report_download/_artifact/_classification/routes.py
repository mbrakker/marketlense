"""Deterministic terminal route, outcome, blocker, and confirmation classification."""

from __future__ import annotations
import re
from pathlib import Path
from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
)
from src.services._browser_report_download.models import BrowserUseAgentResult
from src.utils.errors import AppError
from src.services._browser_report_download._artifact.evidence import (
    _normalize_evidence_categories,
)

from .evidence import (
    _message_indicates_email_delivery,
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


def _resolve_route_summary(
    *,
    raw_summary: str | None,
    route_steps: list[BrowserDownloadRouteStep],
    normalized_url: str,
    route_kind: str,
    blocked_reason: str | None,
) -> str:
    route_summary = str(raw_summary or "").strip()
    if route_summary and _is_semantic_route_summary(route_summary):
        return route_summary
    if route_steps:
        return _derive_route_summary(route_steps)
    if route_kind == "email_delivery" and blocked_reason:
        return (
            f"Open the gated page and stop when the form is blocked ({blocked_reason})."
        )
    if route_kind == "onsite_report":
        return "Open the on-site report and capture the available longread content."
    if route_summary:
        if _is_page_load_failure_summary(route_summary):
            raise AppError(
                code="browser_download_page_not_loaded",
                message="browser-use reached an empty or unloaded browser page",
                retryable=True,
                context={
                    "normalized_url": normalized_url,
                    "route_summary": route_summary,
                },
            )
        raise AppError(
            code="browser_download_route_summary_too_weak",
            message="browser-use returned a route summary without enough reusable action detail",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "route_summary": route_summary,
            },
        )
    raise AppError(
        code="browser_download_missing_route_summary",
        message="browser-use returned no reusable route summary or route steps",
        retryable=True,
        context={"normalized_url": normalized_url},
    )


def _is_page_load_failure_summary(route_summary: str) -> bool:
    lowered = " ".join(str(route_summary or "").split()).casefold()
    if not lowered:
        return False
    page_markers = ("page", "tab", "url", "content")
    failure_markers = (
        "failed to load",
        "did not load",
        "not load",
        "empty",
        "blank",
        "no content",
        "without content",
    )
    return any(marker in lowered for marker in page_markers) and any(
        marker in lowered for marker in failure_markers
    )


def _derive_route_summary(route_steps: list[BrowserDownloadRouteStep]) -> str:
    fragments: list[str] = []
    for step in route_steps[:3]:
        action = step.action or "follow"
        target = step.target_text or step.target_role or step.target_url or "page"
        result = step.result or "completed"
        fragments.append(f"{action} {target} ({result})")
    return "; then ".join(fragments).strip()


def _is_semantic_route_summary(route_summary: str) -> bool:
    normalized = " ".join(str(route_summary or "").split()).strip()
    if not normalized:
        return False
    lowered = normalized.casefold()
    tokens = [token for token in re.split(r"[^a-z0-9]+", lowered) if token]
    if len(tokens) < 4:
        return False
    has_action = any(marker in lowered for marker in _ROUTE_SUMMARY_ACTION_MARKERS)
    has_target = any(marker in lowered for marker in _ROUTE_SUMMARY_TARGET_MARKERS)
    if not has_action or not has_target:
        return False
    return (
        len(tokens) >= 6
        or bool(
            re.search(
                r"\b(first|second|then|after|until|when|once|final)\b",
                lowered,
            )
        )
        or any(
            marker in lowered
            for marker in ("completion", "finish", "saved", "sent", "submitted")
        )
    )


def _resolve_route_kind(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    route_kind: str,
    downloaded_path: Path | None,
    encountered_form_fields: list[str],
    post_submit_message: str | None,
    blocked_reason: str | None,
) -> str:
    token = str(route_kind or "").strip().lower()
    if downloaded_path is not None:
        return "pdf_download"
    if blocked_reason:
        return "email_delivery"
    if token in _BLOCKED_REASONS:
        return "email_delivery"
    if _message_indicates_email_delivery(post_submit_message):
        return "email_delivery"
    if (
        token == "onsite_report"
        or agent_result.onsite_capture_path
        or str(agent_result.onsite_completeness_status or "").strip()
    ):
        return "onsite_report"
    if encountered_form_fields:
        return "email_delivery"
    if str(request.route_family_hint or "").strip() == "browser_onsite_report":
        return "onsite_report"
    if token in _ROUTE_KINDS:
        return token
    raise AppError(
        code="browser_download_route_kind_invalid",
        message="browser-use returned an unsupported route classification",
        retryable=True,
        context={"route_kind": route_kind},
    )


def _resolve_route_steps(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    raw_summary: str | None,
    resolved_target_url: str,
    downloaded_path: Path | None,
    confirmation_evidence: BrowserDownloadConfirmationEvidence,
) -> list[BrowserDownloadRouteStep]:
    steps: list[BrowserDownloadRouteStep] = []
    for index, raw_step in enumerate(agent_result.route_steps):
        action = str(raw_step.action or "").strip() or "follow"
        target_text = str(raw_step.target_text or "").strip()
        target_role = str(raw_step.target_role or "").strip() or "page"
        target_url = str(raw_step.target_url or "").strip()
        result = str(raw_step.result or "").strip() or "completed"
        steps.append(
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=int(raw_step.index) if raw_step.index is not None else index,
                action=action,
                target_text=target_text,
                target_role=target_role,
                target_url=target_url,
                result=result,
                expected_evidence=_normalize_evidence_categories(
                    raw_step.expected_evidence
                ),
                observed_evidence=_normalize_evidence_categories(
                    raw_step.observed_evidence
                ),
                verification_status=str(raw_step.verification_status or "").strip(),
            )
        )
    if steps:
        return steps
    if not _is_semantic_route_summary(str(raw_summary or "").strip()):
        return []
    fallback_result = "downloaded" if downloaded_path is not None else "completed"
    if (
        confirmation_evidence.visible_confirmation_text
        or confirmation_evidence.url_changed
    ):
        fallback_result = "submitted"
    return [
        BrowserDownloadRouteStep(
            schema_version="1.0",
            index=0,
            action="open",
            target_text=str(request.attempt_url or request.url).strip(),
            target_role="url",
            target_url=resolved_target_url,
            result=fallback_result,
            expected_evidence=[],
            observed_evidence=[],
            verification_status="",
        )
    ]


def _looks_like_report_not_found_terminal(
    *,
    request: BrowserReportDownloadRequest,
    route_summary: str,
    route_steps: list[BrowserDownloadRouteStep],
    final_url: str,
    terminal_text_excerpt: str,
) -> bool:
    candidate_title = (
        str(request.candidate_trace.title or "").strip().casefold()
        if request.candidate_trace is not None
        else ""
    )
    haystack = " ".join(
        [
            str(route_summary or ""),
            str(final_url or ""),
            str(terminal_text_excerpt or ""),
            *[_route_step_haystack(step) for step in route_steps],
        ]
    ).casefold()
    if not haystack.strip():
        return False
    has_not_found_marker = any(
        marker in haystack for marker in _REPORT_NOT_FOUND_MARKERS
    )
    explicit_not_found = has_not_found_marker and (
        (
            "not found" in haystack
            and ("specific report" in haystack or "target report" in haystack)
        )
        or "0 matches found" in haystack
        or "no matches found" in haystack
        or "could not find" in haystack
        or "unable to find" in haystack
    )
    if not explicit_not_found:
        return False
    if not candidate_title:
        return True
    return (
        candidate_title in haystack
        or "specific report" in haystack
        or "target report" in haystack
    )


def _agent_result_indicates_report_not_found(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    final_url: str,
) -> bool:
    route_steps = _normalize_agent_route_steps_for_completeness(agent_result)
    return _looks_like_report_not_found_terminal(
        request=request,
        route_summary=str(agent_result.route_summary or "").strip(),
        route_steps=route_steps,
        final_url=final_url,
        terminal_text_excerpt=str(agent_result.terminal_text_excerpt or "").strip(),
    )


def _normalize_agent_route_steps_for_completeness(
    agent_result: BrowserUseAgentResult,
) -> list[BrowserDownloadRouteStep]:
    steps: list[BrowserDownloadRouteStep] = []
    for index, raw_step in enumerate(agent_result.route_steps):
        steps.append(
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=int(raw_step.index) if raw_step.index is not None else index,
                action=str(raw_step.action or "").strip() or "follow",
                target_text=str(raw_step.target_text or "").strip(),
                target_role=str(raw_step.target_role or "").strip() or "page",
                target_url=str(raw_step.target_url or "").strip(),
                result=str(raw_step.result or "").strip() or "completed",
                expected_evidence=_normalize_evidence_categories(
                    raw_step.expected_evidence
                ),
                observed_evidence=_normalize_evidence_categories(
                    raw_step.observed_evidence
                ),
                verification_status=str(raw_step.verification_status or "").strip(),
            )
        )
    return steps


def _resolve_route_family(
    *,
    request: BrowserReportDownloadRequest,
    agent_result: BrowserUseAgentResult,
    route_kind: str,
) -> str:
    token = str(agent_result.route_family or "").strip()
    hinted = str(request.route_family_hint or "").strip()
    canonical = _canonical_route_family(
        route_kind=route_kind,
        route_family=token or hinted,
    )
    if canonical:
        return canonical
    if route_kind == "onsite_report":
        return "browser_onsite_report"
    if route_kind == "email_delivery":
        return "browser_email_form"
    return "browser_pdf_click"


def _canonical_route_family(*, route_kind: str, route_family: str) -> str:
    token = str(route_family or "").strip()
    if route_kind == "email_delivery" and token in {
        "",
        "browser_pdf_click",
        "browser_pdf_download",
    }:
        return "browser_email_form"
    if route_kind == "onsite_report" and token in {
        "",
        "browser_pdf_click",
        "browser_pdf_download",
    }:
        return "browser_onsite_report"
    if route_kind == "pdf_download" and not token:
        return "browser_pdf_click"
    return token


def _route_step_haystack(step: BrowserDownloadRouteStep) -> str:
    return " ".join(
        [
            str(step.target_text or "").strip().casefold(),
            str(step.result or "").strip().casefold(),
            str(step.target_url or "").strip().casefold(),
        ]
    )


__all__ = [
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
]
