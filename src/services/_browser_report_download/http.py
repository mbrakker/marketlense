from __future__ import annotations

import logging
import mimetypes
import re
from dataclasses import asdict, replace
from pathlib import Path
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

import requests  # type: ignore[import-untyped]

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    DownloadTerminalEvidence,
)
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.run_context import RunContext
from src.services._http_acquisition import execute_http_acquisition
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_PDF_SIGNATURE = b"%PDF-"
_PDF_URL_PATTERN = re.compile(
    r"""(?P<quote>['"])(?P<url>[^'"]+?\.pdf(?:\?[^'"]*)?)(?P=quote)""",
    re.IGNORECASE,
)
_PDF_QUERY_KEYS = (
    "download",
    "downloadurl",
    "downloaddata",
    "file",
    "fileurl",
    "asset",
    "asseturl",
    "pdf",
    "pdfurl",
    "url",
    "target",
    "redirect",
    "redirect_url",
    "redirect_uri",
    "u",
)
_PDF_MIME_TYPES = {
    "application/pdf",
    "application/x-pdf",
}
_PDF_BINARY_FALLBACK_MIME_TYPES = {
    "application/octet-stream",
    "binary/octet-stream",
}
_PDF_FETCH_HEADERS = {
    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
}
_HTML_FETCH_HEADERS = {
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "User-Agent": _PDF_FETCH_HEADERS["User-Agent"],
}
_ONSITE_CAPTURE_HTML_MARKERS = (
    "report",
    "research",
    "study",
    "analysis",
    "insight",
    "outlook",
    "survey",
    "investigation",
)
_ONSITE_CAPTURE_BLOCKED_MARKERS = (
    "captcha",
    "cloudflare",
    "access denied",
    "security checkpoint",
    "enable javascript",
)
_ACCESS_CHALLENGE_MARKERS = (
    "captcha",
    "cloudflare",
    "verify you are human",
    "checking if the site connection is secure",
    "security check",
    "security checkpoint",
    "access denied",
    "enable javascript",
)
_ACCESS_CHALLENGE_STATUS_CODES = {401, 403, 429, 503}
_ACCESS_CHALLENGE_PROBE_TIMEOUT_SECONDS = 15.0
_STATIC_EMAIL_GATE_PROBE_TIMEOUT_SECONDS = 8.0
_HTML_PDF_LINK_PROBE_TIMEOUT_SECONDS = 20.0
_EMAIL_ROUTE_HTML_PDF_LINK_PROBE_TIMEOUT_SECONDS = 8.0
_HTML_PDF_LINK_PROBE_ROUTE_FAMILIES = {
    "http_pdf_probe",
    "browser_email_form",
    "browser_pdf_click",
    "browser_tracker_redirect",
    "browser_listing_hub",
}
_STATIC_EMAIL_GATE_ROUTE_FAMILIES = {
    "browser_email_form",
    "browser_pdf_click",
    "browser_tracker_redirect",
}
_STATIC_EMAIL_FIELD_MARKERS = (
    "business email",
    "business email address",
    "work email",
    "professional email",
    "email address",
)
_STATIC_REPORT_FORM_MARKERS = (
    "download ebook",
    "download e-book",
    "download report",
    "download the report",
    "download insights",
    "get report",
    "get the report",
    "register",
    "request report",
    "submit",
    "whitepaper",
    "white paper",
)
_STATIC_FORM_PROVIDER_MARKERS = (
    "eloqua",
    "formstack",
    "gravityforms",
    "hs-form",
    "hubspot",
    "marketo",
    "mktoform",
    "pardot",
    "salesforce",
)
_STATIC_REPORT_CONTEXT_MARKERS = (
    "benchmark",
    "ebook",
    "e-book",
    "guide",
    "insight",
    "insights",
    "outlook",
    "predictions",
    "report",
    "reports",
    "research",
    "study",
    "trends",
    "whitepaper",
    "whitepapers",
    "white paper",
)
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
_HTML_FETCH_MAX_BYTES = 4 * 1024 * 1024
_PDF_FETCH_MAX_BYTES = 128 * 1024 * 1024


def try_http_access_challenge_probe(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    page_url: str | None = None,
    preflight: bool = False,
) -> BrowserReportDownloadResult | None:
    target_url = (
        str(page_url or request.attempt_url or request.url).strip() or request.url
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_access_challenge_probe_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": target_url,
                "preflight": preflight,
            },
        )
    )
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_access_challenge_probe",
                method="GET",
                url=target_url,
                headers=_HTML_FETCH_HEADERS,
                timeout_seconds=min(
                    _ACCESS_CHALLENGE_PROBE_TIMEOUT_SECONDS,
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
                error_code="browser_download_access_challenge_probe_failed",
                error_message="Failed to probe the report page for an access challenge",
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
                event="browser_report_download_access_challenge_probe_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "target_url": target_url,
                    "error": exc.message,
                },
            )
        )
        return None
    text = str(response.text_body or "")
    lowered = text.casefold()
    matched_marker = next(
        (marker for marker in _ACCESS_CHALLENGE_MARKERS if marker in lowered),
        "",
    )
    blocked_status = int(response.status_code) in _ACCESS_CHALLENGE_STATUS_CODES
    challenge_detected = bool(matched_marker) and blocked_status
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_access_challenge_probe_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": target_url,
                "status_code": int(response.status_code),
                "matched_marker": matched_marker,
                "challenge_detected": challenge_detected,
                "body_truncated": response.body_truncated,
            },
        )
    )
    if not challenge_detected:
        return None
    result = _build_access_challenge_result(
        request=request,
        normalized_url=normalized_url,
        target_url=target_url,
        status_code=int(response.status_code),
        matched_marker=matched_marker,
        route_family=(
            request.route_family_hint
            or (
                "http_access_challenge_preflight"
                if preflight
                else "http_access_challenge_probe"
            )
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_access_challenge_probe_complete",
            module=logger.name,
            fields=asdict(result),
        )
    )
    return result


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
                fields=asdict(result),
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


def try_static_email_gate_probe(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    page_url: str | None = None,
) -> BrowserReportDownloadResult | None:
    if (
        str(request.route_family_hint or "").strip()
        not in _STATIC_EMAIL_GATE_ROUTE_FAMILIES
    ):
        return None
    target_url = (
        str(page_url or request.attempt_url or request.url).strip() or request.url
    )
    if not _route_context_supports_static_email_gate(
        request=request,
        target_url=target_url,
    ):
        return None
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_static_email_gate_probe_start",
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
                purpose="browser_report_download_static_email_gate_probe",
                method="GET",
                url=target_url,
                headers=_HTML_FETCH_HEADERS,
                timeout_seconds=min(
                    _STATIC_EMAIL_GATE_PROBE_TIMEOUT_SECONDS,
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
                error_code="browser_download_static_email_gate_fetch_failed",
                error_message="Failed to fetch the route-confirmed landing page while checking for an email gate",
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
        timeout_cause = isinstance(exc.cause, requests.Timeout)
        if timeout_cause and _route_context_supports_static_email_gate(
            request=request, target_url=target_url
        ):
            result = _build_static_email_gate_result(
                request=request,
                normalized_url=normalized_url,
                target_url=target_url,
                html="",
                detection_detail=(
                    "Route-confirmed email-delivery page exceeded the static "
                    "HTML preflight timeout before browser interaction."
                ),
                evidence_labels=[
                    "static_email_gate",
                    "static_fetch_timeout",
                    "email_delivery",
                ],
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_static_email_gate_probe_complete",
                    module=logger.name,
                    fields=asdict(result),
                )
            )
            return result
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_static_email_gate_probe_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "target_url": target_url,
                    "error_code": (
                        "browser_download_static_email_gate_timeout"
                        if timeout_cause
                        else "browser_download_static_email_gate_fetch_failed"
                    ),
                    "error_message": exc.message,
                },
            )
        )
        return None
    content_type_header = _response_header_value(response.headers, "content-type")
    content_type = content_type_header.casefold()
    text = str(response.text_body or "")
    final_url = str(response.final_url or target_url).strip() or target_url
    gate_detected = (
        int(response.status_code) < 400
        and ("html" in content_type or "xml" in content_type)
        and _looks_like_static_email_gate_html(text)
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_static_email_gate_probe_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": target_url,
                "final_url": final_url,
                "status_code": int(response.status_code),
                "content_type": content_type_header,
                "gate_detected": gate_detected,
                "body_truncated": response.body_truncated,
            },
        )
    )
    if not gate_detected:
        return None
    result = _build_static_email_gate_result(
        request=request,
        normalized_url=normalized_url,
        target_url=final_url,
        html=text,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_static_email_gate_probe_complete",
            module=logger.name,
            fields=asdict(result),
        )
    )
    return result


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


def _looks_like_static_email_gate_html(html: str) -> bool:
    token = str(html or "")
    if not token.strip():
        return False
    lowered = token.casefold()
    plain_text = _html_to_text(token).casefold()
    has_form = "<form" in lowered or "mktoform" in lowered or "hs-form" in lowered
    has_email = any(marker in plain_text for marker in _STATIC_EMAIL_FIELD_MARKERS)
    has_report_cta = any(marker in plain_text for marker in _STATIC_REPORT_FORM_MARKERS)
    has_form_provider = any(
        marker in lowered or marker in plain_text
        for marker in _STATIC_FORM_PROVIDER_MARKERS
    )
    has_report_context = any(
        marker in lowered or marker in plain_text
        for marker in _STATIC_REPORT_CONTEXT_MARKERS
    )
    if has_form and has_email and has_report_cta:
        return True
    if has_form_provider and has_report_cta and has_report_context:
        return True
    if has_form and has_form_provider and has_report_context:
        return True
    return False


def _route_context_supports_static_email_gate(
    *,
    request: BrowserReportDownloadRequest,
    target_url: str,
) -> bool:
    if str(request.route_kind_hint or "").strip() != "email_delivery":
        return False
    if (
        str(request.route_family_hint or "").strip()
        not in _STATIC_EMAIL_GATE_ROUTE_FAMILIES
    ):
        return False
    context_parts = [
        request.url,
        request.attempt_url or "",
        target_url,
        request.source_page_url_hint or "",
        request.route_hint or "",
        request.publisher_discovery_route_kind or "",
        request.publisher_recommended_discovery_route_kind or "",
    ]
    if request.candidate_trace is not None:
        context_parts.extend(
            [
                request.candidate_trace.title,
                request.candidate_trace.canonical_url,
                " ".join(request.candidate_trace.source_page_urls),
                " ".join(request.candidate_trace.discovery_provenances),
            ]
        )
    context = " ".join(str(part or "") for part in context_parts).casefold()
    return any(marker in context for marker in _STATIC_REPORT_CONTEXT_MARKERS)


def _build_static_email_gate_result(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
    target_url: str,
    html: str,
    detection_detail: str = "Detected an email-gated report form before browser interaction.",
    evidence_labels: list[str] | None = None,
) -> BrowserReportDownloadResult:
    title = _extract_html_title(html)
    if not title and request.candidate_trace is not None:
        title = str(request.candidate_trace.title or "").strip()
    if not title:
        title = normalized_url
    excerpt = _extract_text_excerpt(html) or detection_detail
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="email_delivery",
        route_family="browser_email_form",
        route_status="inferred",
        outcome="email_required",
        route_summary="Detected an email-gated report form in the landing-page HTML before browser interaction.",
        final_page_url=target_url,
        resolved_target_url=target_url,
        used_route_hint=False,
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="open",
                target_text=target_url,
                target_role="url",
                target_url=target_url,
                result="Fetched the report landing page HTML",
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=1,
                action="inspect",
                target_text="email-gated report form",
                target_role="form",
                target_url=target_url,
                result="Detected form, email field, and report download/request CTA",
            ),
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=(target_url != request.url),
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=target_url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=target_url,
            final_page_title=title,
            terminal_text_excerpt=excerpt,
            artifact_url=target_url,
            artifact_kind="email_delivery",
            artifact_validation_status="blocked",
            artifact_validation_detail=detection_detail,
            confirmation_signal_count=0,
            traversed_page_urls=[target_url],
            evidence_labels=evidence_labels or ["static_email_gate", "email_delivery"],
        ),
        browser_had_structured_result=False,
        used_candidate_pdf_url=False,
        used_candidate_source_page=bool(request.source_page_url_hint),
        encountered_form_fields=[],
        blocked_reason=None,
        blocked_reason_detail=None,
        downloaded_file_path=None,
        downloaded_file_name=None,
        downloaded_mime_type=None,
        downloaded_size_bytes=None,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
    )


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


def _response_header_value(headers: object, key: str) -> str:
    expected = str(key or "").casefold()
    if not hasattr(headers, "items"):
        return ""
    for header_key, value in headers.items():
        if str(header_key or "").casefold() == expected:
            return str(value or "")
    return ""


def _build_access_challenge_result(
    *,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
    target_url: str,
    status_code: int,
    matched_marker: str,
    route_family: str,
) -> BrowserReportDownloadResult:
    detail = (
        "HTTP access challenge detected before browser interaction "
        f"(status {status_code}, marker: {matched_marker})."
    )
    return BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="email_delivery",
        route_family=route_family,
        route_status="inferred",
        outcome="email_required",
        route_summary="Access challenge blocked the report form before browser completion.",
        final_page_url=target_url,
        resolved_target_url=target_url,
        used_route_hint=False,
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="open",
                target_text=target_url,
                target_role="url",
                target_url=target_url,
                result=detail,
            )
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=target_url,
            confirmation_score=0,
            signal_labels=["http_access_challenge"],
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=target_url,
            final_page_title="Access challenge",
            terminal_text_excerpt=detail,
            artifact_url=target_url,
            artifact_kind="email_delivery",
            artifact_validation_status="blocked",
            artifact_validation_detail=detail,
            confirmation_signal_count=0,
            traversed_page_urls=[target_url],
            evidence_labels=["blocked", "http_access_challenge", "blocked_captcha"],
        ),
        browser_had_structured_result=False,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        encountered_form_fields=[],
        blocked_reason="blocked_captcha",
        blocked_reason_detail=detail,
        downloaded_file_path=None,
        downloaded_file_name=None,
        downloaded_mime_type=None,
        downloaded_size_bytes=None,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
    )


def try_direct_pdf_download(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    probe_url: str | None = None,
    route_family: str = "direct_pdf_probe",
    used_candidate_pdf_url: bool = False,
    used_candidate_source_page: bool = False,
) -> BrowserReportDownloadResult | None:
    target_url = str(probe_url or normalized_url).strip() or normalized_url
    destination_name = Path(urlsplit(target_url).path).name or "download.pdf"
    destination_path = download_dir / destination_name
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_direct_pdf_attempt_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": target_url,
                "route_family": route_family,
                "destination_path": str(destination_path),
            },
        )
    )
    try:
        download_pdf_from_url(
            pdf_url=target_url,
            destination_path=destination_path,
            timeout_seconds=request.settings.timeout_seconds,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        downloaded_path = ensure_downloaded_pdf(
            downloaded_path=destination_path,
            ctx=ctx,
            normalized_url=normalized_url,
            document_url=target_url,
            timeout_seconds=request.settings.timeout_seconds,
        )
        downloaded_mime_type = resolve_downloaded_mime_type(
            reported_mime_type=None,
            downloaded_path=downloaded_path,
        )
        validate_downloaded_pdf_artifact(
            downloaded_path=downloaded_path,
            downloaded_mime_type=downloaded_mime_type,
            normalized_url=normalized_url,
        )
    except AppError as exc:
        destination_path.unlink(missing_ok=True)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_direct_pdf_attempt_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "error_code": exc.code,
                    "error_message": exc.message,
                },
            )
        )
        if not exc.retryable:
            raise
        return None

    response = BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="pdf_download",
        route_family=route_family,
        route_status="verified",
        outcome="downloaded",
        route_summary="Open the direct PDF URL and save the returned PDF file locally.",
        final_page_url=target_url,
        resolved_target_url=target_url,
        used_route_hint=False,
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="open",
                target_text=target_url,
                target_role="url",
                target_url=target_url,
                result="downloaded",
            )
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=target_url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=target_url,
            final_page_title="",
            terminal_text_excerpt="",
            artifact_url=target_url,
            artifact_kind="pdf",
            artifact_validation_status="verified",
            artifact_validation_detail="Validated local PDF artifact.",
            confirmation_signal_count=0,
            traversed_page_urls=[target_url],
        ),
        browser_had_structured_result=False,
        used_candidate_pdf_url=used_candidate_pdf_url,
        used_candidate_source_page=used_candidate_source_page,
        encountered_form_fields=[],
        blocked_reason=None,
        blocked_reason_detail=None,
        downloaded_file_path=str(destination_path),
        downloaded_file_name=destination_path.name,
        downloaded_mime_type=resolve_downloaded_mime_type(
            reported_mime_type=None,
            downloaded_path=destination_path,
        ),
        downloaded_size_bytes=destination_path.stat().st_size,
        onsite_capture_path=None,
        onsite_capture_format=None,
        onsite_page_count=None,
        onsite_completeness_status=None,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_direct_pdf_attempt_complete",
            module=logger.name,
            fields=asdict(response),
        )
    )
    return response


def try_direct_onsite_capture(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    page_url: str | None = None,
) -> BrowserReportDownloadResult | None:
    if not _should_try_direct_onsite_capture(request):
        return None
    target_url = (
        str(page_url or request.attempt_url or request.url).strip() or request.url
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_direct_onsite_attempt_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": target_url,
                "route_family": request.route_family_hint or "",
                "used_route_hint": bool(request.route_hint),
            },
        )
    )
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_direct_onsite_capture",
                method="GET",
                url=target_url,
                headers=_HTML_FETCH_HEADERS,
                timeout_seconds=request.settings.timeout_seconds,
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_content_type_markers=("html", "xml"),
                    max_body_bytes=_HTML_FETCH_MAX_BYTES,
                    truncate_body=True,
                ),
                error_code="browser_download_html_fetch_failed",
                error_message="Failed to fetch terminal HTML for on-site capture recovery",
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
                event="browser_report_download_direct_onsite_attempt_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "target_url": target_url,
                    "error_code": "browser_download_html_fetch_failed",
                    "error_message": exc.message,
                },
            )
        )
        return None
    content_type = str(response.headers.get("content-type", "")).casefold()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_direct_onsite_attempt_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": target_url,
                "final_url": response.final_url,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "body_truncated": response.body_truncated,
            },
        )
    )
    if response.status_code >= 400 or (
        "html" not in content_type and "xml" not in content_type
    ):
        return None
    html = str(response.text_body or "")
    if not _looks_like_onsite_capture_html(
        html,
        request=request,
        final_url=str(response.final_url or target_url).strip() or target_url,
    ):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_direct_onsite_attempt_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "target_url": target_url,
                    "error_code": "browser_download_direct_onsite_not_report_like",
                    "error_message": "Fetched HTML did not look like a reusable on-site report capture",
                },
            )
        )
        return None
    capture_path = download_dir / "onsite_capture.html"
    capture_path.write_text(html, encoding="utf-8")
    final_url = str(response.final_url or target_url).strip() or target_url
    final_title = _extract_html_title(html)
    terminal_excerpt = _extract_text_excerpt(html)
    response_result = BrowserReportDownloadResult(
        schema_version="1.0",
        source_url=request.url,
        normalized_url=normalized_url,
        route_kind="onsite_report",
        route_family="browser_onsite_report",
        route_status="verified",
        outcome="captured",
        route_summary="Open the on-site report URL and capture the HTML article directly.",
        final_page_url=final_url,
        resolved_target_url=final_url,
        used_route_hint=bool(request.route_hint),
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="open",
                target_text=final_url,
                target_role="url",
                target_url=final_url,
                result="Fetched the on-site report HTML directly",
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=1,
                action="extract",
                target_text="onsite_capture.html",
                target_role="file",
                target_url=final_url,
                result="Saved the on-site report HTML locally",
            ),
        ],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=(final_url != target_url),
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url=final_url,
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=final_url,
            final_page_title=final_title,
            terminal_text_excerpt=terminal_excerpt,
            artifact_url=final_url,
            artifact_kind="onsite_report",
            artifact_validation_status="verified",
            artifact_validation_detail="Captured a remembered on-site report directly from HTML.",
            confirmation_signal_count=0,
            traversed_page_urls=[final_url],
            evidence_labels=["direct_html_capture", "onsite_report"],
        ),
        browser_had_structured_result=False,
        used_candidate_pdf_url=False,
        used_candidate_source_page=bool(request.source_page_url_hint),
        encountered_form_fields=[],
        blocked_reason=None,
        blocked_reason_detail=None,
        downloaded_file_path=None,
        downloaded_file_name=None,
        downloaded_mime_type=None,
        downloaded_size_bytes=None,
        onsite_capture_path=str(capture_path),
        onsite_capture_format="html",
        onsite_page_count=1,
        onsite_completeness_status="complete",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_direct_onsite_attempt_complete",
            module=logger.name,
            fields=asdict(response_result),
        )
    )
    return response_result


def ensure_downloaded_pdf(
    *,
    downloaded_path: Path | None,
    ctx: RunContext,
    normalized_url: str,
    document_url: str,
    timeout_seconds: float,
) -> Path | None:
    if downloaded_path is None:
        return None
    if is_pdf_file(downloaded_path):
        return downloaded_path

    wrapper_html = _read_text_if_small(downloaded_path, max_bytes=64 * 1024)
    embedded_pdf_url = _extract_embedded_pdf_url(
        wrapper_html=wrapper_html,
        document_url=document_url,
    )
    if embedded_pdf_url:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_wrapper_detected",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "downloaded_file_path": str(downloaded_path),
                    "embedded_pdf_url": embedded_pdf_url,
                },
            )
        )
        download_pdf_from_url(
            pdf_url=embedded_pdf_url,
            destination_path=downloaded_path,
            timeout_seconds=timeout_seconds,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        if is_pdf_file(downloaded_path):
            return downloaded_path

    raise AppError(
        code="browser_download_invalid_pdf",
        message="Downloaded file is not a valid PDF",
        retryable=True,
        context={
            "normalized_url": normalized_url,
            "downloaded_file_path": str(downloaded_path),
            "document_url": document_url,
        },
    )


def fetch_html_from_url(
    *,
    page_url: str,
    timeout_seconds: float,
    ctx: RunContext,
    normalized_url: str,
) -> str:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_html_fetch_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "page_url": page_url,
            },
        )
    )
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_terminal_html_fetch",
                method="GET",
                url=page_url,
                headers=_HTML_FETCH_HEADERS,
                timeout_seconds=timeout_seconds,
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_content_type_markers=("html", "xml"),
                    max_body_bytes=_HTML_FETCH_MAX_BYTES,
                    truncate_body=True,
                ),
                error_code="browser_download_html_fetch_failed",
                error_message="Failed to fetch terminal HTML for on-site capture recovery",
                allow_redirects=True,
                context_fields={
                    "normalized_url": normalized_url,
                    "page_url": page_url,
                },
            ),
            ctx=ctx,
            requests_module=requests,
        )
    except AppError as exc:
        raise AppError(
            code="browser_download_html_fetch_failed",
            message="Failed to fetch terminal HTML for on-site capture recovery",
            cause=exc,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "page_url": page_url,
            },
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_html_fetch_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "page_url": page_url,
                "status_code": response.status_code,
                "content_type": response.headers.get("content-type", ""),
                "body_truncated": response.body_truncated,
            },
        )
    )
    if response.status_code >= 400:
        raise AppError(
            code="browser_download_html_fetch_failed",
            message="Terminal HTML fetch returned an error status",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "page_url": page_url,
                "status_code": response.status_code,
            },
        )
    content_type = str(response.headers.get("content-type", "")).casefold()
    if "html" not in content_type and "xml" not in content_type:
        raise AppError(
            code="browser_download_html_fetch_invalid_content_type",
            message="Terminal HTML fetch did not return HTML content",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "page_url": page_url,
                "content_type": response.headers.get("content-type", ""),
            },
        )
    return str(response.text_body or "")


def resolve_downloaded_mime_type(
    *,
    reported_mime_type: str | None,
    downloaded_path: Path | None,
) -> str | None:
    if downloaded_path is None:
        return None
    reported = str(reported_mime_type or "").strip().lower() or None
    guessed = _guess_mime_type(downloaded_path)
    if guessed == "application/pdf":
        if (
            reported
            and reported not in _PDF_MIME_TYPES
            and reported not in _PDF_BINARY_FALLBACK_MIME_TYPES
        ):
            return reported
        return guessed
    return reported or guessed


def validate_downloaded_pdf_artifact(
    *,
    downloaded_path: Path | None,
    downloaded_mime_type: str | None,
    normalized_url: str,
) -> None:
    if downloaded_path is None:
        return
    if not is_pdf_file(downloaded_path):
        raise AppError(
            code="browser_download_invalid_pdf",
            message="Downloaded file is not a valid PDF",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "downloaded_file_path": str(downloaded_path),
            },
        )
    lowered_mime = str(downloaded_mime_type or "").strip().lower()
    if (
        lowered_mime
        and lowered_mime not in _PDF_MIME_TYPES
        and lowered_mime not in _PDF_BINARY_FALLBACK_MIME_TYPES
    ):
        raise AppError(
            code="browser_download_invalid_pdf_metadata",
            message="Downloaded file metadata does not match a PDF artifact",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "downloaded_file_path": str(downloaded_path),
                "downloaded_mime_type": downloaded_mime_type,
            },
        )
    if (
        downloaded_path.suffix.lower() != ".pdf"
        and lowered_mime not in _PDF_MIME_TYPES
        and lowered_mime not in _PDF_BINARY_FALLBACK_MIME_TYPES
    ):
        raise AppError(
            code="browser_download_invalid_pdf_metadata",
            message="Downloaded file is missing PDF-identifying metadata",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "downloaded_file_path": str(downloaded_path),
                "downloaded_mime_type": downloaded_mime_type,
            },
        )


def is_pdf_file(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            return handle.read(len(_PDF_SIGNATURE)) == _PDF_SIGNATURE
    except OSError:
        return False


def download_pdf_from_url(
    *,
    pdf_url: str,
    destination_path: Path,
    timeout_seconds: float,
    ctx: RunContext,
    normalized_url: str,
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_pdf_fetch_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "pdf_url": pdf_url,
                "destination_path": str(destination_path),
            },
        )
    )
    temp_path = destination_path.with_suffix(destination_path.suffix + ".part")
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_report_download_pdf_fetch",
                method="GET",
                url=pdf_url,
                headers=_PDF_FETCH_HEADERS,
                timeout_seconds=timeout_seconds,
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=True,
                    capture_text=False,
                    stream_to_path=str(temp_path),
                    max_stream_bytes=_PDF_FETCH_MAX_BYTES,
                ),
                error_code="browser_download_pdf_fetch_failed",
                error_message="Failed to fetch the real PDF from the wrapper page",
                context_fields={
                    "normalized_url": normalized_url,
                    "pdf_url": pdf_url,
                    "destination_path": str(destination_path),
                },
                body_too_large_code="browser_download_pdf_fetch_failed",
                body_too_large_message="Fetched PDF exceeded the configured size cap",
                write_error_code="browser_download_pdf_write_failed",
                write_error_message="Failed to write the fetched PDF to disk",
            ),
            ctx=ctx,
            requests_module=requests,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_pdf_fetch_response",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "pdf_url": pdf_url,
                    "status_code": response.status_code,
                    "content_type": response.content_type,
                    "streamed_bytes": response.streamed_bytes,
                    "used_pooled_session": response.used_pooled_session,
                },
            )
        )
        temp_path.replace(destination_path)
    except AppError as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise exc


def _should_try_direct_onsite_capture(
    request: BrowserReportDownloadRequest,
) -> bool:
    route_family = str(request.route_family_hint or "").strip()
    route_kind = str(request.route_kind_hint or "").strip()
    if route_family == "browser_onsite_report" and route_kind == "onsite_report":
        if request.candidate_trace is not None:
            return True
        actions = {
            str(step.action or "").strip().lower() for step in request.route_step_hints
        }
        if "extract" in actions:
            return True
        hint = str(request.route_hint or "").casefold()
        return "extract" in hint or "capture" in hint
    if (
        request.candidate_trace is not None
        and route_family == "browser_pdf_click"
        and route_kind in {"", "pdf_download"}
        and not str(request.candidate_trace.pdf_url or "").strip()
    ):
        return _looks_like_report_detail_candidate(request)
    return False


def _looks_like_report_detail_candidate(request: BrowserReportDownloadRequest) -> bool:
    candidate = request.candidate_trace
    target_url = str(
        (candidate.canonical_url if candidate is not None else "")
        or request.attempt_url
        or request.url
    ).strip()
    path = str(urlsplit(target_url).path or "").strip().lower()
    if not path or path.endswith(".pdf"):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        return False
    last_segment_tokens = [token for token in segments[-1].split("-") if token]
    if len(last_segment_tokens) < 2:
        return False
    title = str(candidate.title or "").casefold() if candidate is not None else ""
    report_markers = {
        "analysis",
        "guide",
        "insight",
        "playbook",
        "report",
        "research",
        "study",
        "survey",
        "trend",
        "whitepaper",
    }
    return any(marker in path for marker in report_markers) or any(
        marker in title for marker in report_markers
    )


def _looks_like_onsite_capture_html(
    html: str,
    *,
    request: BrowserReportDownloadRequest | None = None,
    final_url: str | None = None,
) -> bool:
    token = str(html or "")
    if not token.strip():
        return False
    lowered = token.casefold()
    plain_text = _html_to_text(token)
    plain_lowered = plain_text.casefold()
    if any(marker in plain_lowered for marker in _ONSITE_CAPTURE_BLOCKED_MARKERS):
        return False
    if len(plain_text) < 800:
        return False
    if "<article" in lowered:
        return True
    strong_non_article_markers = {
        "complete report",
        "full report",
        "read the report",
    }
    if any(marker in plain_lowered for marker in strong_non_article_markers) and any(
        marker in plain_lowered for marker in _ONSITE_CAPTURE_HTML_MARKERS
    ):
        return True
    return _route_context_supports_direct_onsite_capture(
        request=request,
        final_url=final_url,
        title=_extract_html_title(token),
        plain_text=plain_text,
    )


def _route_context_supports_direct_onsite_capture(
    *,
    request: BrowserReportDownloadRequest | None,
    final_url: str | None,
    title: str,
    plain_text: str,
) -> bool:
    if request is None:
        return False
    route_family = str(request.route_family_hint or "").strip()
    route_kind = str(request.route_kind_hint or "").strip()
    if route_family != "browser_onsite_report" or route_kind != "onsite_report":
        return False
    if len(plain_text) < 2500:
        return False
    context = " ".join(
        [
            str(final_url or ""),
            str(request.url or ""),
            str(request.attempt_url or ""),
            str(title or ""),
            str(
                request.candidate_trace.title
                if request.candidate_trace is not None
                else ""
            ),
        ]
    ).casefold()
    positive_markers = {
        "analysis",
        "benchmark",
        "findings",
        "guide",
        "insight",
        "outlook",
        "report",
        "research",
        "study",
        "survey",
        "trend",
        "year in review",
        "year-in-review",
    }
    return any(marker in context for marker in positive_markers)


def _extract_html_title(html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", str(html or ""))
    if not match:
        return ""
    return " ".join(str(match.group(1) or "").split()).strip()


def _html_to_text(html: str) -> str:
    token = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", str(html or ""))
    token = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", token)
    token = re.sub(r"(?is)<[^>]+>", " ", token)
    token = re.sub(r"\s+", " ", token)
    return token.strip()


def _extract_text_excerpt(html: str, *, limit: int = 280) -> str:
    plain_text = _html_to_text(html)
    if len(plain_text) <= limit:
        return plain_text
    return plain_text[:limit].rstrip() + "..."


def _guess_mime_type(downloaded_path: Path | None) -> str | None:
    if downloaded_path is None:
        return None
    if is_pdf_file(downloaded_path):
        return "application/pdf"
    guessed, _ = mimetypes.guess_type(downloaded_path.name)
    if guessed:
        return guessed
    if downloaded_path.suffix.lower() == ".pdf":
        return "application/pdf"
    return None


def _read_text_if_small(path: Path, *, max_bytes: int) -> str:
    try:
        if path.stat().st_size > max_bytes:
            return ""
        return path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""


def _extract_embedded_pdf_url(*, wrapper_html: str, document_url: str) -> str | None:
    for candidate in extract_embedded_pdf_urls(
        wrapper_html=wrapper_html,
        document_url=document_url,
    ):
        return candidate
    return None


def extract_embedded_pdf_urls(*, wrapper_html: str, document_url: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for payload in (
        str(wrapper_html or ""),
        unquote(str(wrapper_html or "")),
        document_url,
        unquote(str(document_url or "")),
    ):
        for match in _PDF_URL_PATTERN.finditer(payload):
            raw_url = str(match.group("url") or "").strip()
            if not raw_url:
                continue
            _append_pdf_candidate(
                candidates,
                seen,
                candidate=urljoin(document_url, raw_url),
            )
        parsed = urlsplit(payload)
        if not parsed.query:
            continue
        query = parse_qs(parsed.query, keep_blank_values=False)
        for key in _PDF_QUERY_KEYS:
            values = query.get(key)
            if not values:
                continue
            for value in values:
                token = unquote(str(value or "").strip())
                if not token:
                    continue
                if token.startswith("http://") or token.startswith("https://"):
                    _append_pdf_candidate(candidates, seen, candidate=token)
                elif ".pdf" in token.casefold():
                    _append_pdf_candidate(
                        candidates,
                        seen,
                        candidate=urljoin(document_url, token),
                    )
    return candidates


def _append_pdf_candidate(
    candidates: list[str],
    seen: set[str],
    *,
    candidate: str,
) -> None:
    token = str(candidate or "").strip()
    if not token:
        return
    marker = token.casefold()
    if ".pdf" not in marker:
        return
    if marker in seen:
        return
    seen.add(marker)
    candidates.append(token)
