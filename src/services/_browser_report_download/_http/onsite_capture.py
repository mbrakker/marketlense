"""Direct onsite HTML capture and recovery eligibility classification."""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from pathlib import Path
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
)
from src.services._http_acquisition import execute_http_acquisition
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
_ONSITE_CAPTURE_BLOCKED_MARKERS = (
    "captcha",
    "cloudflare",
    "access denied",
    "security checkpoint",
    "enable javascript",
)


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
                    "recovery_class": decision.recovery_class,
                    "recovery_decision": "fallback",
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
            fields={
                **asdict(response_result),
                "recovery_class": decision.recovery_class,
                "recovery_decision": "complete",
            },
        )
    )
    return response_result


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
