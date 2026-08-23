from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from src.contracts.browser_download import ReportDownloadOrchestratorRequest
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.report_download_orchestrator")

_NON_REPORT_URL_MARKERS = {
    "blog",
    "news",
    "press",
    "case-study",
    "case_study",
    "webinar",
    "podcast",
    "faq",
    "support",
    "contact",
}
_ASSET_URL_MARKERS = {
    "logo",
    "image",
    "images",
    "video",
    "webp",
    "jpg",
    "jpeg",
    "png",
    "svg",
}
_MARKETING_URL_MARKERS = {
    "demo",
    "pricing",
    "contact-sales",
    "contact_sales",
    "book-a-demo",
    "book_demo",
    "request-pricing",
    "signup",
    "sign-up",
}
_NON_REPORT_TITLE_MARKERS = {
    "case study",
    "webinar",
    "podcast",
    "press release",
    "support",
    "help center",
    "customer story",
}
_REPORT_TITLE_MARKERS = {
    "report",
    "research",
    "study",
    "survey",
    "insight",
    "analysis",
    "outlook",
    "whitepaper",
    "white paper",
    "guide",
    "playbook",
    "trend",
    "ebook",
}
_REPORT_RESOURCE_URL_MARKERS = {
    "resource",
    "resources",
    "whitepaper",
    "whitepapers",
    "guide",
    "guides",
    "playbook",
    "playbooks",
    "ebook",
    "ebooks",
}
_REPORT_SOURCE_PAGE_MARKERS = {
    "insights",
    "reports",
    "research",
    "resources",
    "publications",
}
_MIXED_CONTENT_HUB_SEGMENTS = {
    "insight",
    "insights",
    "report",
    "reports",
    "research",
    "resource",
    "resources",
    "publication",
    "publications",
    "library",
    "blog",
    "news",
}
_REPORT_DETAIL_TITLE_MARKERS = {
    "benchmark",
    "ebook",
    "e-book",
    "guide",
    "market",
    "outlook",
    "playbook",
    "prediction",
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


def assert_candidate_download_ready(
    *,
    request: ReportDownloadOrchestratorRequest,
    normalized_url: str,
    ctx: RunContext,
) -> None:
    candidate = request.candidate_trace
    if candidate is None:
        return
    if candidate.pdf_url or normalized_url.endswith(".pdf"):
        return
    readiness_score, rejection_reason, readiness_signals = (
        evaluate_candidate_download_readiness(
            request=request,
            normalized_url=normalized_url,
        )
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_readiness_evaluated",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "candidate_title": candidate.title,
                "candidate_url": candidate.canonical_url,
                "download_readiness_score": readiness_score,
                "readiness_signals": readiness_signals,
                "readiness_rejection_reason": rejection_reason or "",
            },
        )
    )
    if rejection_reason:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_readiness_rejected",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "candidate_title": candidate.title,
                    "candidate_url": candidate.canonical_url,
                    "download_readiness_score": readiness_score,
                    "readiness_signals": readiness_signals,
                    "readiness_rejection_reason": rejection_reason,
                },
            )
        )
        raise AppError(
            code=f"report_download_{rejection_reason}",
            message="The candidate URL does not look like a report acquisition target",
            retryable=False,
            context={
                "normalized_url": normalized_url,
                "candidate_title": candidate.title,
                "candidate_url": candidate.canonical_url,
                "download_readiness_score": readiness_score,
                "readiness_signals": readiness_signals,
                "readiness_rejection_reason": rejection_reason,
            },
        )


def evaluate_candidate_download_readiness(
    *,
    request: ReportDownloadOrchestratorRequest,
    normalized_url: str,
) -> tuple[float, str | None, list[str]]:
    candidate = request.candidate_trace
    if candidate is None:
        return 1.0, None, ["no_candidate_trace"]
    title = str(candidate.title or "").strip().casefold()
    url_value = str(candidate.canonical_url or normalized_url).strip().casefold()
    source_pages = [
        str(value or "").strip().casefold() for value in candidate.source_page_urls
    ]
    provenances = {
        str(value or "").strip().casefold() for value in candidate.discovery_provenances
    }
    score = 0.0
    signals: list[str] = []
    if any(marker in title for marker in _REPORT_TITLE_MARKERS):
        score += 0.5
        signals.append("report_title_marker")
    if any(marker in url_value for marker in _REPORT_TITLE_MARKERS):
        score += 0.25
        signals.append("report_url_marker")
    if any(marker in url_value for marker in _REPORT_RESOURCE_URL_MARKERS):
        score += 0.15
        signals.append("report_resource_url_marker")
    if any(
        any(marker in page for marker in _REPORT_SOURCE_PAGE_MARKERS)
        for page in source_pages
    ):
        score += 0.2
        signals.append("report_source_page")
    if candidate.max_confidence is not None:
        score += min(0.2, max(0.0, float(candidate.max_confidence)) * 0.2)
        signals.append("candidate_confidence")
    if "direct_pdf_source" in provenances:
        score += 0.3
        signals.append("direct_pdf_source")
    if (
        "browser_dom" in provenances
        or "browser_rendered_html_supplement" in provenances
    ):
        score += 0.1
        signals.append("browser_provenance")

    if any(marker in url_value for marker in _ASSET_URL_MARKERS):
        score -= 0.9
        signals.append("asset_url_marker")
        return round(score, 3), "candidate_rejected_asset_page", signals
    if any(marker in url_value for marker in _MARKETING_URL_MARKERS):
        score -= 0.7
        signals.append("marketing_url_marker")
    if any(marker in url_value for marker in _NON_REPORT_URL_MARKERS):
        score -= 0.6
        signals.append("non_report_url_marker")
    if any(marker in title for marker in _NON_REPORT_TITLE_MARKERS):
        score -= 0.7
        signals.append("non_report_title_marker")
    if _is_mixed_content_hub_candidate(
        url_value=url_value,
        title=title,
        source_pages=source_pages,
        normalized_url=normalized_url,
        has_pdf_url=bool(str(candidate.pdf_url or "").strip()),
    ):
        score -= 0.6
        signals.append("mixed_content_hub_candidate")
        return round(score, 3), "candidate_rejected_mixed_content_hub", signals

    if score >= 0.35:
        return round(score, 3), None, signals
    if any(marker in url_value for marker in _MARKETING_URL_MARKERS):
        return round(score, 3), "candidate_rejected_marketing_page", signals
    if any(marker in title for marker in _NON_REPORT_TITLE_MARKERS) or any(
        marker in url_value for marker in _NON_REPORT_URL_MARKERS
    ):
        return round(score, 3), "candidate_rejected_non_report", signals
    return round(score, 3), "candidate_rejected_non_report", signals


def _is_mixed_content_hub_candidate(
    *,
    url_value: str,
    title: str,
    source_pages: list[str],
    normalized_url: str,
    has_pdf_url: bool,
) -> bool:
    if has_pdf_url:
        return False
    parsed = urlsplit(str(url_value or normalized_url).strip())
    path = str(parsed.path or "").strip().casefold()
    if path.endswith(".pdf"):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return True
    last_segment = segments[-1]
    last_stem = _document_path_stem(last_segment)
    last_tokens = [
        token for token in last_stem.replace("_", "-").split("-") if token
    ]
    title_has_detail_signal = any(
        marker in str(title or "") for marker in _REPORT_DETAIL_TITLE_MARKERS
    )
    path_has_year = re.search(r"\b20\d{2}\b", path) is not None
    if title_has_detail_signal and (len(last_tokens) >= 3 or path_has_year):
        return False
    source_page_set = {
        _url_surface_key(value) for value in source_pages if str(value or "").strip()
    }
    candidate_surface_key = _url_surface_key(str(url_value or normalized_url))
    source_same_surface = (
        bool(source_page_set) and candidate_surface_key in source_page_set
    )
    listing_last_segment = last_stem in _MIXED_CONTENT_HUB_SEGMENTS
    listing_query = any(
        key in str(parsed.query or "").casefold()
        for key in ("page=", "offset=", "category=", "tag=", "filter=", "search=")
    )
    short_listing_under_context = (
        len(segments) <= 2
        and any(
            _document_path_stem(segment) in _MIXED_CONTENT_HUB_SEGMENTS
            for segment in segments
        )
        and len(last_tokens) < 3
    )
    return (
        source_same_surface
        or listing_last_segment
        or listing_query
        or short_listing_under_context
    )


def _url_surface_key(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    host = str(parsed.hostname or "").strip().casefold()
    path = "/".join(segment for segment in str(parsed.path or "").split("/") if segment)
    return f"{host}/{path}".rstrip("/")


def _document_path_stem(segment: str) -> str:
    return re.sub(r"\.(?:html?|aspx?)$", "", str(segment or "").casefold())
