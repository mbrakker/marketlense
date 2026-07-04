"""Bounded HTTP access-challenge and static email-gate probes."""

from __future__ import annotations

import logging
from dataclasses import asdict

import requests

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
from src.services._browser_report_download._http.config import (
    _HTML_FETCH_HEADERS,
    _HTML_FETCH_MAX_BYTES,
)
from src.services._browser_report_download._http.html_evidence import (
    _extract_html_title,
    _extract_text_excerpt,
    _html_to_text,
    _response_header_value,
)
from src.services._http_acquisition import execute_http_acquisition
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

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
    if str(request.delivery_email or "").strip():
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_static_email_gate_probe_skipped",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "target_url": target_url,
                    "route_family": request.route_family_hint or "",
                    "reason": "delivery_email_available",
                },
            )
        )
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
