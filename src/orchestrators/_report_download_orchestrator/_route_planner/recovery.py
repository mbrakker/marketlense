from __future__ import annotations
import logging
import re
from dataclasses import replace
from urllib.parse import urlsplit
from src.contracts.browser_download import (
    ReportDownloadRoutePlanStep,
)
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace

from .url_rules import (
    _looks_like_listing_url,
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


def _browser_to_http_recovery_decision(
    *,
    normalized_url: str,
    candidate: PublisherInventoryCandidateTrace | None,
    browser_step: ReportDownloadRoutePlanStep,
    source_page_urls: list[str],
    provenances: set[str],
    recommended_route_kind: str,
    policy_route_family: str,
) -> tuple[str, str]:
    if policy_route_family in {"direct_pdf_probe", "http_pdf_probe"}:
        return "allowed", "policy_pdf_probe"
    if recommended_route_kind == "http_parse":
        return "allowed", "publisher_recommended_http"
    if "direct_pdf_source" in provenances:
        return "allowed", "direct_pdf_source"
    if browser_step.route_family in {
        "browser_listing_hub",
        "browser_tracker_redirect",
        "browser_email_form",
    }:
        return "blocked", f"terminal_browser_family:{browser_step.route_family}"
    if browser_step.route_family == "browser_onsite_report":
        return "deferred", "onsite_report_capture_preferred"
    if _looks_like_listing_url(normalized_url):
        return "blocked", "candidate_listing_surface"
    candidate_title = str(candidate.title or "").strip() if candidate else ""
    if _has_http_probe_signal(
        normalized_url=normalized_url,
        candidate_title=candidate_title,
        source_page_urls=source_page_urls,
    ):
        return "allowed", "candidate_has_pdf_probe_signal"
    return "deferred", "browser_route_without_http_signal"


def _has_http_probe_signal(
    *,
    normalized_url: str,
    candidate_title: str,
    source_page_urls: list[str],
) -> bool:
    path = str(urlsplit(str(normalized_url or "").strip()).path or "").casefold()
    title = str(candidate_title or "").casefold()
    if "download" in path or "pdf" in path:
        return True
    if any(marker in title for marker in _REPORT_DETAIL_SIGNAL_MARKERS):
        segments = [segment for segment in path.split("/") if segment]
        if segments:
            token_count = len([token for token in segments[-1].split("-") if token])
            if token_count >= 3 or re.search(r"\b20\d{2}\b", path):
                return True
    for source_page_url in source_page_urls:
        source_path = str(
            urlsplit(str(source_page_url or "").strip()).path or ""
        ).casefold()
        if source_path and source_path != path and "download" in path:
            return True
    return False


def _annotate_recovery_steps(
    steps: list[ReportDownloadRoutePlanStep],
) -> list[ReportDownloadRoutePlanStep]:
    annotated: list[ReportDownloadRoutePlanStep] = []
    for step in steps:
        if step.recovery_class:
            annotated.append(step)
            continue
        annotated.append(
            replace(
                step,
                recovery_class=step.route_family,
                recovery_decision=step.recovery_decision or "primary",
            )
        )
    return annotated


def _dedupe_steps(
    steps: list[ReportDownloadRoutePlanStep],
) -> list[ReportDownloadRoutePlanStep]:
    deduped: list[ReportDownloadRoutePlanStep] = []
    seen: set[tuple[str, str, str, str]] = set()
    for step in steps:
        key = (
            step.step_name,
            step.route_family,
            str(step.attempt_url or "").strip(),
            str(step.source_page_url_hint or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(step)
    return deduped


__all__ = [
    "_browser_to_http_recovery_decision",
    "_has_http_probe_signal",
    "_annotate_recovery_steps",
    "_dedupe_steps",
]
