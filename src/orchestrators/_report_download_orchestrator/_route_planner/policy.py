from __future__ import annotations
import logging
import re
from dataclasses import replace
from src.contracts.browser_download import (
    PublisherDownloadRouteMemory,
    PublisherDownloadRoutePolicySignal,
    ReportDownloadRoutePlanStep,
)
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace

from .url_rules import (
    _clean_string_list,
    _looks_like_email_form_url,
    _looks_like_pdf,
)

logger = logging.getLogger("market_lense.report_download_route_planner")
_BROWSER_DISCOVERY_PROVENANCES = {
    "browser_dom",
    "browser_rendered_html_supplement",
}
_PDF_FIRST_DISCOVERY_PROVENANCES = {
    "direct_pdf_source",
}
_TRACKER_HOST_MARKERS = {
    "lnk",
    "trk",
    "click",
    "go",
    "email",
    "hubspot",
    "pardot",
    "marketo",
}
_TRACKER_SHORT_PATH_MARKERS = {
    "go",
    "lnk",
    "trk",
}
_LISTING_PATH_MARKERS = {
    "insights",
    "reports",
    "research",
    "resources",
    "publications",
    "library",
}
_EDITORIAL_NON_REPORT_MARKERS = {
    "blog",
    "news",
    "press",
    "case-study",
    "case_study",
    "webinar",
}
_EDITORIAL_REPORT_MARKERS = {
    "report",
    "reports",
    "guide",
    "guides",
    "insight",
    "insights",
    "playbook",
    "research",
    "analysis",
    "study",
    "survey",
    "trend",
    "trends",
    "whitepaper",
    "whitepapers",
}
_BROWSER_TO_HTTP_RECOVERY_CLASS = "browser_to_http_pdf_probe"
_DIRECT_PDF_RECOVERY_CLASS = "direct_pdf_probe"
_HTTP_PDF_RECOVERY_CLASS = "http_pdf_probe"
_REPORT_DETAIL_SIGNAL_MARKERS = {
    "benchmark",
    "download",
    "ebook",
    "e-book",
    "guide",
    "market",
    "outlook",
    "playbook",
    "predictions",
    "report",
    "research",
    "study",
    "survey",
    "trend",
    "trends",
    "whitepaper",
    "white paper",
}
_EMAIL_GATE_PATH_MARKERS = {
    "gated-content-form",
    "download",
    "downloads",
    "ebook",
    "ebooks",
    "whitepaper",
    "whitepapers",
    "asset",
    "assets",
    "register",
    "form",
}
_EMAIL_GATE_PARENT_SEGMENTS = {
    "report",
    "reports",
    "resources",
}
_EMAIL_GATE_DETAIL_TITLE_MARKERS = {
    "benchmark",
    "ebook",
    "e-book",
    "guide",
    "outlook",
    "predictions",
    "report",
    "research",
    "study",
    "trends",
    "whitepaper",
    "white paper",
}
_ONSITE_LONGREAD_SEGMENTS = {
    "insight",
    "insights",
    "research",
    "analysis",
    "survey",
    "outlook",
}
_DIRECT_ONSITE_REPORT_SEGMENTS = {
    "guide",
    "guides",
    "insight",
    "playbook",
    "playbooks",
    "research",
    "analysis",
    "survey",
    "outlook",
}
_DIRECT_ONSITE_REPORT_PATH_PHRASES = {
    "year-in-review",
}
_DIRECT_ONSITE_DIGITAL_YEAR_SEGMENT_RX = re.compile(
    r"^(?:digital|global-digital)-20\d{2}(?:-|$)"
)
_ONSITE_EXCLUDED_SEGMENTS = {
    "resources",
    "reports",
    "report",
    "download",
    "downloads",
    "ebook",
    "whitepaper",
    "whitepapers",
    "asset",
    "assets",
    "form",
    "register",
}
_TRACKER_QUERY_KEYS = (
    "url",
    "target",
    "dest",
    "destination",
    "redirect",
    "redirect_url",
    "redirect_uri",
    "u",
    "r",
)


def _preferred_policy_signal(
    remembered_route: PublisherDownloadRouteMemory | None,
) -> PublisherDownloadRoutePolicySignal | None:
    if remembered_route is None:
        return None
    for signal in remembered_route.route_policy:
        if signal.attempts < 2:
            continue
        if signal.verified_successes < 1:
            continue
        if signal.rank_score < 0.45:
            continue
        if signal.confidence_score < 0.45 and signal.success_rate < 0.5:
            continue
        return signal
    return None


def _preferred_publisher_policy_signal(
    *,
    remembered_route: PublisherDownloadRouteMemory | None,
    normalized_url: str,
    candidate: PublisherInventoryCandidateTrace | None,
) -> PublisherDownloadRoutePolicySignal | None:
    if remembered_route is None:
        return None
    candidate_pdf_url = str(candidate.pdf_url or "").strip() if candidate else ""
    source_page_urls = _clean_string_list(
        candidate.source_page_urls if candidate is not None else []
    )
    candidate_title = (
        str(candidate.title or "").strip() if candidate is not None else ""
    )
    for signal in remembered_route.publisher_route_policy:
        if signal.attempts < 3:
            continue
        if signal.verified_successes < 2:
            continue
        if signal.success_rate < 0.667:
            continue
        if signal.rank_score < 0.65:
            continue
        if signal.confidence_score < 0.65:
            continue
        if (
            signal.blocked_attempts
            and (signal.blocked_attempts / signal.attempts) > 0.25
        ):
            continue
        if not _publisher_policy_signal_matches_context(
            signal=signal,
            normalized_url=normalized_url,
            candidate_pdf_url=candidate_pdf_url,
            candidate_title=candidate_title,
            source_page_urls=source_page_urls,
        ):
            continue
        return signal
    return None


def _publisher_policy_signal_matches_context(
    *,
    signal: PublisherDownloadRoutePolicySignal,
    normalized_url: str,
    candidate_pdf_url: str,
    candidate_title: str,
    source_page_urls: list[str],
) -> bool:
    route_family = str(signal.route_family or "").strip()
    if candidate_pdf_url and route_family not in {"direct_pdf_probe", "http_pdf_probe"}:
        return False
    if _looks_like_pdf(normalized_url) and route_family not in {
        "direct_pdf_probe",
        "http_pdf_probe",
    }:
        return False
    if route_family == "browser_onsite_report":
        return not _looks_like_email_form_url(
            normalized_url,
            candidate_title=candidate_title,
            source_page_urls=source_page_urls,
        )
    return True


def _apply_policy_route_family(
    step: ReportDownloadRoutePlanStep,
    *,
    policy_signal: PublisherDownloadRoutePolicySignal | None,
) -> ReportDownloadRoutePlanStep:
    if policy_signal is None:
        return step
    route_family = str(policy_signal.route_family or "").strip()
    if route_family not in {
        "browser_email_form",
        "browser_onsite_report",
        "browser_pdf_click",
        "browser_tracker_redirect",
        "browser_listing_hub",
    }:
        return step
    return replace(
        step,
        step_name=_policy_step_name(route_family),
        route_family=route_family,
        route_kind_hint=_route_kind_hint_for_policy_family(route_family),
        fallback_on_retryable_error=False,
    )


def _policy_step_name(route_family: str) -> str:
    if route_family == "browser_email_form":
        return "report_download_policy_browser_email_form"
    if route_family == "browser_onsite_report":
        return "report_download_policy_browser_onsite_report"
    if route_family == "browser_listing_hub":
        return "report_download_policy_browser_listing_hub"
    if route_family == "browser_tracker_redirect":
        return "report_download_policy_browser_tracker_redirect"
    return "report_download_policy_browser_candidate"


def _route_kind_hint_for_policy_family(route_family: str) -> str | None:
    if route_family == "browser_email_form":
        return "email_delivery"
    if route_family == "browser_onsite_report":
        return "onsite_report"
    return None


def _default_route_family_for_kind(route_kind: str) -> str:
    if str(route_kind or "").strip() == "onsite_report":
        return "browser_onsite_report"
    if str(route_kind or "").strip() == "email_delivery":
        return "browser_email_form"
    return "browser_pdf_click"


def _should_reuse_memory_route(
    remembered_route: PublisherDownloadRouteMemory | None,
) -> bool:
    if remembered_route is None:
        return False
    if not remembered_route.exact_route_found:
        return False
    if remembered_route.route_status != "verified":
        return False
    if remembered_route.outcome not in {"downloaded", "email_requested", "captured"}:
        return False
    if (
        remembered_route.route_kind == "onsite_report"
        and str(remembered_route.onsite_completeness_status or "").strip().lower()
        != "complete"
    ):
        return False
    route_family = _canonical_memory_route_family(
        route_kind=remembered_route.route_kind,
        route_family=remembered_route.route_family,
    )
    if not remembered_route.browser_had_structured_result and route_family not in {
        "direct_pdf_probe",
        "http_pdf_probe",
    }:
        return False
    minimum_confidence = 0.5
    if route_family in {"direct_pdf_probe", "http_pdf_probe"}:
        minimum_confidence = 0.35
    elif remembered_route.route_kind == "email_delivery":
        minimum_confidence = 0.45
    elif remembered_route.route_kind == "onsite_report":
        minimum_confidence = 0.6
    if remembered_route.confidence_score < minimum_confidence:
        return False
    required_successes = (
        1
        if route_family in {"direct_pdf_probe", "http_pdf_probe", "browser_email_form"}
        else 2
    )
    if remembered_route.verified_successes >= required_successes:
        return True
    return (
        remembered_route.confidence_score >= 0.75
        and remembered_route.verified_successes >= 1
    )


def _has_actionable_email_memory_hint(
    remembered_route: PublisherDownloadRouteMemory | None,
) -> bool:
    if remembered_route is None:
        return False
    if remembered_route.route_kind != "email_delivery":
        return False
    if remembered_route.outcome not in {"email_required", "email_requested"}:
        return False
    if not remembered_route.browser_had_structured_result:
        return False
    summary = str(remembered_route.route_summary or "").casefold()
    if "not found" in summary:
        return False
    if "capture" in summary and "onsite" in summary and "form" not in summary:
        return False
    action_text = " ".join(
        " ".join(
            [
                str(step.action or ""),
                str(step.target_text or ""),
                str(step.target_role or ""),
                str(step.result or ""),
            ]
        )
        for step in remembered_route.route_steps
    ).casefold()
    form_markers = {
        "download",
        "email",
        "form",
        "request",
        "submit",
    }
    if action_text and any(marker in action_text for marker in form_markers):
        return True
    return any(marker in summary for marker in {"fill", "form", "submit"})


def _canonical_memory_route_family(*, route_kind: str, route_family: str) -> str:
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
    if not token:
        return _default_route_family_for_kind(route_kind)
    return token


__all__ = [
    "_preferred_policy_signal",
    "_preferred_publisher_policy_signal",
    "_publisher_policy_signal_matches_context",
    "_apply_policy_route_family",
    "_policy_step_name",
    "_route_kind_hint_for_policy_family",
    "_default_route_family_for_kind",
    "_should_reuse_memory_route",
    "_has_actionable_email_memory_hint",
    "_canonical_memory_route_family",
]
