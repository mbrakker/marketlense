"""HTML report-page probing for relevant downloadable PDF links."""

from __future__ import annotations

import logging
import re
from dataclasses import replace
from pathlib import Path
from urllib.parse import unquote, urljoin, urlsplit

import requests

from src.contracts.browser_download import (
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
)
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download._http.config import (
    _HTML_FETCH_HEADERS,
    _HTML_FETCH_MAX_BYTES,
)
from src.services._browser_report_download._http.html_evidence import (
    _response_header_value,
    extract_embedded_pdf_urls,
)
from src.services._browser_report_download._http.pdf_transfer import (
    try_direct_pdf_download,
)
from src.services._browser_report_download.logging import (
    browser_download_result_log_fields,
)
from src.services._http_acquisition import execute_http_acquisition
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_HTML_PDF_LINK_PROBE_TIMEOUT_SECONDS = 20.0
_EMAIL_ROUTE_HTML_PDF_LINK_PROBE_TIMEOUT_SECONDS = 8.0
_HTML_PDF_LINK_PROBE_ROUTE_FAMILIES = {
    "http_pdf_probe",
    "browser_email_form",
    "browser_pdf_click",
    "browser_tracker_redirect",
    "browser_listing_hub",
}
_PDF_RELEVANCE_STOPWORDS = {
    "and",
    "brief",
    "download",
    "final",
    "for",
    "from",
    "index",
    "insight",
    "insights",
    "pdf",
    "report",
    "reports",
    "sector",
    "the",
    "with",
}


def try_report_page_pdf_link_download(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    page_url: str | None = None,
) -> BrowserReportDownloadResult | None:
    if not _should_try_report_page_pdf_link_probe(request):
        return None
    target_url = (
        str(page_url or request.attempt_url or request.url).strip() or request.url
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_html_pdf_link_probe_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": target_url,
                "route_family": request.route_family_hint or "",
            },
        )
    )
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_html_pdf_link_probe",
                method="GET",
                url=target_url,
                headers=_HTML_FETCH_HEADERS,
                timeout_seconds=min(
                    _html_pdf_link_probe_timeout_seconds(request),
                    max(1.0, float(request.settings.timeout_seconds)),
                ),
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_content_type_markers=("html", "xml"),
                    max_body_bytes=_HTML_FETCH_MAX_BYTES,
                    truncate_body=True,
                ),
                error_code="browser_download_html_pdf_link_fetch_failed",
                error_message="Failed to fetch the report page while probing for embedded PDF links",
                allow_redirects=True,
                context_fields={
                    "normalized_url": normalized_url,
                    "target_url": target_url,
                },
            ),
            ctx=ctx,
            requests_module=requests,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_html_pdf_link_probe_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "target_url": target_url,
                    "error_code": "browser_download_html_pdf_link_fetch_failed",
                    "error_message": exc.message,
                },
            )
        )
        return None
    content_type_header = _response_header_value(response.headers, "content-type")
    content_type = content_type_header.casefold()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_html_pdf_link_probe_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": target_url,
                "final_url": response.final_url,
                "status_code": int(response.status_code),
                "content_type": content_type_header,
                "body_truncated": response.body_truncated,
            },
        )
    )
    if response.status_code >= 400 or (
        "html" not in content_type and "xml" not in content_type
    ):
        return None
    final_url = str(response.final_url or target_url).strip() or target_url
    pdf_candidates = _filter_relevant_pdf_candidates(
        request=request,
        page_url=final_url,
        candidates=extract_embedded_pdf_urls(
            wrapper_html=str(response.text_body or ""),
            document_url=final_url,
        ),
    )
    if not pdf_candidates:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_html_pdf_link_probe_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "target_url": target_url,
                    "error_code": "browser_download_html_pdf_link_not_found",
                    "error_message": "No relevant PDF link was found in the report page HTML",
                },
            )
        )
        return None
    for pdf_url in pdf_candidates:
        direct_result = try_direct_pdf_download(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            probe_url=pdf_url,
            route_family="report_page_pdf_link_probe",
            used_candidate_pdf_url=False,
            used_candidate_source_page=bool(request.source_page_url_hint),
        )
        if direct_result is None:
            continue
        result = replace(
            direct_result,
            route_summary=(
                "Fetch the report page HTML, extract the embedded PDF link, "
                "and save the verified PDF locally."
            ),
            route_steps=[
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=0,
                    action="open",
                    target_text=final_url,
                    target_role="url",
                    target_url=final_url,
                    result="Fetched the report page HTML",
                ),
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=1,
                    action="extract",
                    target_text=pdf_url,
                    target_role="link",
                    target_url=pdf_url,
                    result="Extracted a relevant embedded PDF link",
                ),
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=2,
                    action="open",
                    target_text=pdf_url,
                    target_role="url",
                    target_url=pdf_url,
                    result="downloaded",
                ),
            ],
            confirmation_evidence=replace(
                direct_result.confirmation_evidence,
                url_changed=(final_url != pdf_url),
            ),
            terminal_evidence=replace(
                direct_result.terminal_evidence,
                traversed_page_urls=[final_url, pdf_url],
                evidence_labels=[
                    "html_pdf_link_probe",
                    "verified",
                    "application/pdf",
                ],
            ),
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_html_pdf_link_probe_complete",
                module=logger.name,
                fields=browser_download_result_log_fields(result),
            )
        )
        return result
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_html_pdf_link_probe_fallback",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": target_url,
                "error_code": "browser_download_html_pdf_link_candidates_failed",
                "error_message": "Relevant embedded PDF links were found but none produced a valid PDF artifact",
                "candidate_count": len(pdf_candidates),
            },
        )
    )
    return None


def _should_try_report_page_pdf_link_probe(
    request: BrowserReportDownloadRequest,
) -> bool:
    route_family = str(request.route_family_hint or "").strip()
    if route_family not in _HTML_PDF_LINK_PROBE_ROUTE_FAMILIES:
        return False
    if str(request.route_kind_hint or "").strip() == "onsite_report":
        return False
    target_url = str(request.attempt_url or request.url or "").strip()
    if not target_url or _looks_like_pdf_url(target_url):
        return False
    return True


def _html_pdf_link_probe_timeout_seconds(
    request: BrowserReportDownloadRequest,
) -> float:
    if (
        str(request.route_kind_hint or "").strip() == "email_delivery"
        or str(request.route_family_hint or "").strip() == "browser_email_form"
    ):
        return _EMAIL_ROUTE_HTML_PDF_LINK_PROBE_TIMEOUT_SECONDS
    return _HTML_PDF_LINK_PROBE_TIMEOUT_SECONDS


def _filter_relevant_pdf_candidates(
    *,
    request: BrowserReportDownloadRequest,
    page_url: str,
    candidates: list[str],
) -> list[str]:
    page_tokens = _report_relevance_tokens(page_url)
    if request.candidate_trace is not None:
        page_tokens.update(_report_relevance_tokens(request.candidate_trace.title))
        page_tokens.update(
            _report_relevance_tokens(request.candidate_trace.canonical_url)
        )
    result: list[str] = []
    for candidate in candidates:
        candidate_url = urljoin(page_url, candidate)
        if _pdf_candidate_matches_report_page(
            page_url=page_url,
            pdf_url=candidate_url,
            page_tokens=page_tokens,
        ):
            result.append(candidate_url)
    return result


def _pdf_candidate_matches_report_page(
    *,
    page_url: str,
    pdf_url: str,
    page_tokens: set[str],
) -> bool:
    pdf_tokens = _report_relevance_tokens(pdf_url)
    if page_tokens and len(page_tokens & pdf_tokens) >= 2:
        return True
    return False


def _report_relevance_tokens(value: str | None) -> set[str]:
    raw_value = str(value or "").strip()
    parsed = urlsplit(raw_value)
    token_source = parsed.path if parsed.scheme or parsed.netloc else raw_value
    token = unquote(str(token_source or "")).casefold()
    tokens = {
        match.group(0)
        for match in re.finditer(r"[a-z0-9]{2,}", token)
        if match.group(0) not in _PDF_RELEVANCE_STOPWORDS
    }
    return {value for value in tokens if len(value) >= 3 or value.isdigit()}


def _looks_like_pdf_url(value: str | None) -> bool:
    return ".pdf" in str(urlsplit(str(value or "")).path or "").casefold()
