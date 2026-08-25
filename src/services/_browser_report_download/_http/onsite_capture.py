"""Direct onsite HTML capture and recovery eligibility classification."""

from __future__ import annotations

import logging
import multiprocessing
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlsplit

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
    HttpAcquisitionResponse,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.pdf_ocr import PdfHtmlRenderRequest
from src.contracts.run_context import RunContext
from src.services._browser_report_download._http.adobe_indesign import (
    try_embedded_adobe_indesign_capture,
)
from src.services._browser_report_download._http.config import (
    _HTML_FETCH_HEADERS,
    _HTML_FETCH_MAX_BYTES,
)
from src.services._browser_report_download._http.html_evidence import (
    _extract_html_title,
    _extract_text_excerpt,
    _html_to_text,
    extract_public_form_redirect_url,
)
from src.services._browser_report_download._http.issuu import (
    try_embedded_issuu_capture,
)
from src.services._browser_report_download.logging import (
    browser_download_result_log_fields,
)
from src.services._http_acquisition import execute_http_acquisition
from src.services.pdf_service import render_html_pdf
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_DIRECT_ONSITE_RECOVERY_CLASS = "browser_direct_onsite_http_capture"
_DETAIL_CANDIDATE_RECOVERY_CLASS = "browser_detail_candidate_http_capture"
_MIXED_CONTENT_RECOVERY_CLASS = "mixed_content_hub_http_capture"
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
_ONSITE_CAPTURE_HARD_BLOCKED_MARKERS = (
    "cloudflare",
    "access denied",
    "security checkpoint",
)
_ONSITE_CAPTURE_JAVASCRIPT_BLOCK_MARKER = "enable javascript"
_ONSITE_CAPTURE_JAVASCRIPT_BLOCK_MAX_TEXT_CHARS = 2500
_ONSITE_CAPTURE_HUMAN_VERIFICATION_MARKERS = (
    "not a robot",
    "verify you are human",
    "verify that you are human",
)
_ONSITE_PDF_RENDER_TIMEOUT_SECONDS = 30.0
_ONSITE_PDF_RENDER_MAX_PAGES = 500


@dataclass(frozen=True)
class DirectOnsiteRecoveryDecision:
    schema_version: str
    allowed: bool
    recovery_class: str
    reason: str


def try_direct_onsite_capture(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    page_url: str | None = None,
    http_acquisition_executor: Callable[..., HttpAcquisitionResponse] = (
        execute_http_acquisition
    ),
) -> BrowserReportDownloadResult | None:
    decision = _direct_onsite_recovery_decision(request)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_direct_onsite_recovery_decision",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "route_family": request.route_family_hint or "",
                "route_kind": request.route_kind_hint or "",
                "recovery_class": decision.recovery_class,
                "recovery_decision": "allowed" if decision.allowed else "blocked",
                "recovery_reason": decision.reason,
            },
        )
    )
    if not decision.allowed:
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
                "recovery_class": decision.recovery_class,
                "recovery_decision": "allowed",
                "used_route_hint": bool(request.route_hint),
            },
        )
    )
    try:
        response = http_acquisition_executor(
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
                    "recovery_class": decision.recovery_class,
                    "recovery_decision": "fallback",
                    "error_code": "browser_download_html_fetch_failed",
                    "error_message": exc.message,
                },
            )
        )
        return None
    content_type_header = str(response.content_type or "").strip()
    content_type = content_type_header.casefold()
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
                "content_type": content_type_header,
                "body_truncated": response.body_truncated,
                "recovery_class": decision.recovery_class,
                "recovery_decision": "allowed",
            },
        )
    )
    if response.status_code >= 400 or (
        "html" not in content_type and "xml" not in content_type
    ):
        return None
    html = str(response.text_body or "")
    adobe_indesign_result = try_embedded_adobe_indesign_capture(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        source_page_url=str(response.final_url or target_url).strip() or target_url,
        source_page_html=html,
        http_acquisition_executor=http_acquisition_executor,
    )
    if adobe_indesign_result is not None:
        return adobe_indesign_result
    issuu_result = try_embedded_issuu_capture(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
        source_page_url=str(response.final_url or target_url).strip() or target_url,
        source_page_html=html,
        http_acquisition_executor=http_acquisition_executor,
    )
    if issuu_result is not None:
        return issuu_result
    form_redirect_url = extract_public_form_redirect_url(
        wrapper_html=html,
        document_url=str(response.final_url or target_url).strip() or target_url,
    )
    if form_redirect_url:
        try:
            redirect_response = http_acquisition_executor(
                request=HttpAcquisitionRequest(
                    schema_version="1.0",
                    purpose="browser_report_download_public_form_redirect",
                    method="GET",
                    url=form_redirect_url,
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
                    error_code="browser_download_public_form_redirect_fetch_failed",
                    error_message=(
                        "Failed to fetch the report page exposed by a public form redirect"
                    ),
                    allow_redirects=True,
                    context_fields={
                        "normalized_url": normalized_url,
                        "source_page_url": str(response.final_url or target_url),
                        "form_redirect_url": form_redirect_url,
                    },
                ),
                ctx=ctx,
                requests_module=requests,
            )
        except AppError:
            redirect_response = None
        if (
            redirect_response is not None
            and redirect_response.status_code < 400
            and not redirect_response.body_truncated
            and "html" in str(redirect_response.content_type or "").casefold()
        ):
            issuu_result = try_embedded_issuu_capture(
                request=request,
                ctx=ctx,
                normalized_url=normalized_url,
                download_dir=download_dir,
                source_page_url=(
                    str(redirect_response.final_url or form_redirect_url).strip()
                    or form_redirect_url
                ),
                source_page_html=str(redirect_response.text_body or ""),
                http_acquisition_executor=http_acquisition_executor,
            )
            if issuu_result is not None:
                return issuu_result
    if decision.reason == "unhinted_report_detail_candidate":
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_direct_onsite_attempt_fallback",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "target_url": target_url,
                    "recovery_class": decision.recovery_class,
                    "recovery_decision": "fallback",
                    "error_code": "browser_download_public_embed_unverified",
                    "error_message": (
                        "Unhinted report detail did not expose a complete verified "
                        "public Adobe InDesign embed."
                    ),
                },
            )
        )
        return None
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
                    "recovery_class": decision.recovery_class,
                    "recovery_decision": "fallback",
                    "error_code": "browser_download_direct_onsite_not_report_like",
                    "error_message": "Fetched HTML did not look like a reusable on-site report capture",
                },
            )
        )
        return None
    html_capture_path = download_dir / "onsite_capture.html"
    html_capture_path.write_text(html, encoding="utf-8")
    rendered_pdf_path = _render_onsite_html_to_pdf(
        html=html,
        output_path=download_dir / "onsite_capture.rendered.pdf",
        ctx=ctx,
    )
    capture_path = rendered_pdf_path or html_capture_path
    capture_format = "rendered_onsite_pdf" if rendered_pdf_path else "html"
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
                target_text=capture_path.name,
                target_role="file",
                target_url=final_url,
                result=(
                    "Rendered the on-site report HTML to a local PDF"
                    if rendered_pdf_path
                    else "Saved the on-site report HTML locally"
                ),
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
            artifact_validation_detail=(
                "Captured on-site report HTML and rendered it to a local PDF."
                if rendered_pdf_path
                else "Captured a remembered on-site report directly from HTML."
            ),
            confirmation_signal_count=0,
            traversed_page_urls=[final_url],
            html_snapshot_path=str(html_capture_path),
            evidence_labels=[
                "direct_html_capture",
                "onsite_report",
                *(["rendered_onsite_pdf"] if rendered_pdf_path else []),
            ],
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
        onsite_capture_format=capture_format,
        onsite_page_count=1,
        onsite_completeness_status="complete",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_direct_onsite_attempt_complete",
            module=logger.name,
            fields={
                **browser_download_result_log_fields(response_result),
                "recovery_class": decision.recovery_class,
                "recovery_decision": "complete",
            },
        )
    )
    return response_result


def _render_onsite_html_to_pdf(
    *, html: str, output_path: Path, ctx: RunContext
) -> Path | None:
    """Create a bounded local PDF from a verified direct on-site HTML capture."""
    output_path.unlink(missing_ok=True)
    process = multiprocessing.get_context("spawn").Process(
        target=_write_onsite_html_pdf,
        args=(_html_for_pdf_rendering(html), str(output_path), ctx),
    )
    try:
        process.start()
        process.join(_ONSITE_PDF_RENDER_TIMEOUT_SECONDS)
        if process.is_alive():
            process.terminate()
            process.join()
            output_path.unlink(missing_ok=True)
            return None
        if process.exitcode != 0:
            output_path.unlink(missing_ok=True)
            return None
    except (OSError, RuntimeError, ValueError):
        if process.is_alive():
            process.terminate()
            process.join()
        output_path.unlink(missing_ok=True)
        return None
    if not output_path.is_file() or not output_path.read_bytes().startswith(b"%PDF-"):
        output_path.unlink(missing_ok=True)
        return None
    return output_path


def _write_onsite_html_pdf(html: str, output_path: str, ctx: RunContext) -> None:
    path = Path(output_path)
    try:
        response = render_html_pdf(
            PdfHtmlRenderRequest(
                schema_version="1.0",
                output_path=path.as_posix(),
                html=html,
                max_pages=_ONSITE_PDF_RENDER_MAX_PAGES,
            ),
            ctx,
        )
        if response.rendered_page_count < 1:
            path.unlink(missing_ok=True)
            raise RuntimeError("onsite HTML PDF rendering produced no pages")
    except (AppError, RuntimeError, ValueError, OSError):
        path.unlink(missing_ok=True)
        raise


def _html_for_pdf_rendering(html: str) -> str:
    """Keep report content while excluding unsupported publisher CSS."""
    without_styles = re.sub(r"(?is)<style\b[^>]*>.*?</style\s*>", "", html)
    without_stylesheets = re.sub(
        r"(?is)<link\b[^>]*\brel=[\"']?stylesheet[\"']?[^>]*>",
        "",
        without_styles,
    )
    return re.sub(
        r"(?is)<(?:audio|canvas|embed|iframe|img|object|picture|source|svg|video)\b[^>]*>(?:.*?</(?:audio|canvas|embed|iframe|object|picture|svg|video)\s*>)?",
        "",
        without_stylesheets,
    )


def _should_try_direct_onsite_capture(
    request: BrowserReportDownloadRequest,
) -> bool:
    return _direct_onsite_recovery_decision(request).allowed


def _direct_onsite_recovery_decision(
    request: BrowserReportDownloadRequest,
) -> DirectOnsiteRecoveryDecision:
    route_family = str(request.route_family_hint or "").strip()
    route_kind = str(request.route_kind_hint or "").strip()
    if request.candidate_trace is not None and _looks_like_mixed_content_hub_candidate(
        request
    ):
        return DirectOnsiteRecoveryDecision(
            schema_version="1.0",
            allowed=False,
            recovery_class=_MIXED_CONTENT_RECOVERY_CLASS,
            reason="mixed_content_hub_candidate",
        )
    if route_family == "browser_onsite_report" and route_kind == "onsite_report":
        if request.candidate_trace is not None:
            return DirectOnsiteRecoveryDecision(
                schema_version="1.0",
                allowed=True,
                recovery_class=_DIRECT_ONSITE_RECOVERY_CLASS,
                reason="onsite_report_candidate_trace",
            )
        if _looks_like_report_detail_candidate(request):
            return DirectOnsiteRecoveryDecision(
                schema_version="1.0",
                allowed=True,
                recovery_class=_DIRECT_ONSITE_RECOVERY_CLASS,
                reason="onsite_report_detail_url",
            )
        actions = {
            str(step.action or "").strip().lower() for step in request.route_step_hints
        }
        if "extract" in actions:
            return DirectOnsiteRecoveryDecision(
                schema_version="1.0",
                allowed=True,
                recovery_class=_DIRECT_ONSITE_RECOVERY_CLASS,
                reason="onsite_report_extract_step",
            )
        hint = str(request.route_hint or "").casefold()
        if "extract" in hint or "capture" in hint:
            return DirectOnsiteRecoveryDecision(
                schema_version="1.0",
                allowed=True,
                recovery_class=_DIRECT_ONSITE_RECOVERY_CLASS,
                reason="onsite_report_route_hint",
            )
        return DirectOnsiteRecoveryDecision(
            schema_version="1.0",
            allowed=False,
            recovery_class=_DIRECT_ONSITE_RECOVERY_CLASS,
            reason="onsite_report_without_capture_signal",
        )
    if (
        request.candidate_trace is not None
        and route_family == "browser_pdf_click"
        and route_kind in {"", "pdf_download"}
        and not str(request.candidate_trace.pdf_url or "").strip()
    ):
        if _looks_like_report_detail_candidate(request):
            return DirectOnsiteRecoveryDecision(
                schema_version="1.0",
                allowed=True,
                recovery_class=_DETAIL_CANDIDATE_RECOVERY_CLASS,
                reason="report_detail_candidate",
            )
        return DirectOnsiteRecoveryDecision(
            schema_version="1.0",
            allowed=False,
            recovery_class=_DETAIL_CANDIDATE_RECOVERY_CLASS,
            reason="candidate_without_detail_signal",
        )
    if route_family == "browser_email_form" and route_kind in {"", "email_delivery"}:
        if _looks_like_report_detail_candidate(request):
            return DirectOnsiteRecoveryDecision(
                schema_version="1.0",
                allowed=True,
                recovery_class=_DETAIL_CANDIDATE_RECOVERY_CLASS,
                reason="email_form_report_detail_candidate",
            )
        return DirectOnsiteRecoveryDecision(
            schema_version="1.0",
            allowed=False,
            recovery_class=_DETAIL_CANDIDATE_RECOVERY_CLASS,
            reason="email_form_without_detail_signal",
        )
    if (
        not route_family
        and not route_kind
        and _looks_like_report_detail_candidate(request)
    ):
        return DirectOnsiteRecoveryDecision(
            schema_version="1.0",
            allowed=True,
            recovery_class=_DETAIL_CANDIDATE_RECOVERY_CLASS,
            reason="unhinted_report_detail_candidate",
        )
    return DirectOnsiteRecoveryDecision(
        schema_version="1.0",
        allowed=False,
        recovery_class="unsupported_direct_onsite_http_capture",
        reason="unsupported_route_context",
    )


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
    if _looks_like_mixed_content_hub_candidate(request):
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


def _looks_like_mixed_content_hub_candidate(
    request: BrowserReportDownloadRequest,
) -> bool:
    candidate = request.candidate_trace
    target_url = str(
        (candidate.canonical_url if candidate is not None else "")
        or request.attempt_url
        or request.url
    ).strip()
    parsed = urlsplit(target_url)
    path = str(parsed.path or "").strip().casefold()
    if not path or path.endswith(".pdf"):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return True
    last_segment = segments[-1]
    last_tokens = [
        token for token in last_segment.replace("_", "-").split("-") if token
    ]
    title = str(candidate.title or "").casefold() if candidate is not None else ""
    title_has_detail_signal = any(
        marker in title
        for marker in {
            "benchmark",
            "ebook",
            "guide",
            "outlook",
            "playbook",
            "report",
            "research",
            "study",
            "survey",
            "trend",
            "whitepaper",
            "white paper",
        }
    )
    path_has_year = re.search(r"\b20\d{2}\b", path) is not None
    if title_has_detail_signal and (len(last_tokens) >= 3 or path_has_year):
        return False
    source_surfaces = {
        _url_surface_key(value)
        for value in (candidate.source_page_urls if candidate is not None else [])
        if str(value or "").strip()
    }
    same_as_source = (
        bool(source_surfaces) and _url_surface_key(target_url) in source_surfaces
    )
    listing_last_segment = last_segment in _MIXED_CONTENT_HUB_SEGMENTS
    short_listing = (
        len(segments) <= 2
        and any(segment in _MIXED_CONTENT_HUB_SEGMENTS for segment in segments)
        and len(last_tokens) < 3
    )
    listing_query = any(
        marker in str(parsed.query or "").casefold()
        for marker in ("page=", "offset=", "category=", "tag=", "filter=", "search=")
    )
    return same_as_source or listing_last_segment or short_listing or listing_query


def _url_surface_key(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    host = str(parsed.hostname or "").strip().casefold()
    path = "/".join(segment for segment in str(parsed.path or "").split("/") if segment)
    return f"{host}/{path}".rstrip("/")


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
    if any(marker in plain_lowered for marker in _ONSITE_CAPTURE_HARD_BLOCKED_MARKERS):
        return False
    if (
        _ONSITE_CAPTURE_JAVASCRIPT_BLOCK_MARKER in plain_lowered
        and len(plain_text) < _ONSITE_CAPTURE_JAVASCRIPT_BLOCK_MAX_TEXT_CHARS
    ):
        return False
    if "captcha" in plain_lowered and any(
        marker in plain_lowered for marker in _ONSITE_CAPTURE_HUMAN_VERIFICATION_MARKERS
    ):
        return False
    if _request_is_planned_email_form(request) and _html_contains_lead_capture_form(
        token
    ):
        return False
    if len(plain_text) < 800:
        return False
    if _request_is_planned_email_form(
        request
    ) and _email_form_html_looks_like_full_report(
        request=request,
        final_url=final_url,
        title=_extract_html_title(token),
        plain_text=plain_text,
    ):
        return True
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


def _request_is_planned_email_form(
    request: BrowserReportDownloadRequest | None,
) -> bool:
    if request is None:
        return False
    return str(request.route_family_hint or "").strip() == "browser_email_form"


def _html_contains_lead_capture_form(html: str) -> bool:
    token = str(html or "")
    if not token.strip():
        return False
    for match in re.finditer(r"(?is)<form\b[^>]*>(.*?)</form>", token):
        form_html = match.group(1)
        form_text = _html_to_text(form_html).casefold()
        form_lowered = form_html.casefold()
        has_control = bool(re.search(r"(?is)<(?:input|select|textarea)\b", form_html))
        if not has_control:
            continue
        lead_markers = (
            "email",
            "e-mail",
            "company",
            "organization",
            "country",
            "state",
            "phone",
            "job",
            "role",
            "first name",
            "last name",
            "download",
            "submit",
        )
        if any(
            marker in form_lowered or marker in form_text for marker in lead_markers
        ):
            return True
        has_search_only_marker = (
            'type="search"' in form_lowered
            or "type='search'" in form_lowered
            or "search" in form_text
        )
        if not has_search_only_marker and re.search(
            r"(?is)<(?:select|textarea)\b",
            form_html,
        ):
            return True
    return False


def _email_form_html_looks_like_full_report(
    *,
    request: BrowserReportDownloadRequest | None,
    final_url: str | None,
    title: str,
    plain_text: str,
) -> bool:
    if request is None or len(str(plain_text or "")) < 2500:
        return False
    context = " ".join(
        [
            str(final_url or ""),
            str(request.url or ""),
            str(request.attempt_url or ""),
            str(title or ""),
        ]
    ).casefold()
    title_or_path_markers = {
        "analysis",
        "benchmark",
        "findings",
        "guide",
        "outlook",
        "report",
        "research",
        "study",
        "survey",
        "trend",
        "whitepaper",
        "white paper",
    }
    if not any(marker in context for marker in title_or_path_markers):
        return False
    text = str(plain_text or "").casefold()
    body_markers = {
        "analysis",
        "findings",
        "key findings",
        "methodology",
        "report",
        "research",
        "section",
        "threat",
    }
    marker_count = sum(1 for marker in body_markers if marker in text)
    return marker_count >= 2
