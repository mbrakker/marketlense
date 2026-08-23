"""Bounded browser preflight probes before full browser-use agent runs.

This module copies the browser-harness pattern of cheap `page_info`, `js`,
`http_get`, and event-drain inspection into the existing Marketlense browser
download service boundary. It is a bounded probe, not a route planner: it can
confirm a rendered direct PDF link or record why the full agent is still needed.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import os
import re
import time
from dataclasses import dataclass, replace
from importlib import import_module
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urljoin

from src.contracts.browser_download import (
    BrowserDownloadRouteStep,
    BrowserPreflightProbeResponse,
    BrowserPreflightProbeResult,
    BrowserPreflightReuseState,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download._browser_runtime.runtime import (
    load_browser_use_runtime,
)
from src.services._browser_report_download._http.config import (
    _TERMINAL_NOT_FOUND_BODY_MARKERS,
)
from src.services._browser_report_download.browser import (
    BrowserPreflightSession,
    close_browser_preflight_session,
    start_browser_preflight_session,
)
from src.services._browser_report_download.helpers import browser_helper_js_async
from src.services._browser_report_download.http import (
    extract_embedded_pdf_urls,
    try_direct_pdf_download,
)
from src.services._browser_report_download.logging import (
    browser_preflight_probe_log_fields,
)
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.preflight")

_PREFLIGHT_SCHEMA_VERSION = "1.0"
_PREFLIGHT_EVENT_DRAIN_SECONDS = 0.35
_PREFLIGHT_REDIRECT_SETTLE_SECONDS = 2.0
_PREFLIGHT_SESSION_TIMEOUT_SECONDS = 24.0
_PREFLIGHT_ROUTE_FAMILIES = {
    "",
    "browser_pdf_click",
    "browser_email_form",
    "browser_tracker_redirect",
    "browser_listing_hub",
}
_PDF_URL_PATTERN = re.compile(r"https?://[^\s\"'<>]+?\.pdf(?:[?#][^\s\"'<>]*)?", re.I)
_NON_REPORT_PDF_MARKERS = {
    "cookie",
    "dpa",
    "legal",
    "privacy",
    "terms",
}
_TITLE_TOKEN_STOPWORDS = {
    "analysis",
    "annual",
    "download",
    "ebook",
    "global",
    "guide",
    "paper",
    "report",
    "reports",
    "research",
    "study",
    "whitepaper",
}


@dataclass(frozen=True)
class BrowserPreflightProbeExecution:
    """Typed probe result plus an unpersisted browser lease for escalation."""

    response: BrowserPreflightProbeResponse
    browser_session: BrowserPreflightSession | None


def try_browser_preflight_probe(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    force_for_http_access_status: bool = False,
) -> BrowserPreflightProbeResponse:
    """Run a bounded preflight and always release its browser before returning."""
    execution = _run_browser_preflight_probe(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        execution_url=execution_url,
        download_dir=download_dir,
        retain_browser_session=False,
        force_for_http_access_status=force_for_http_access_status,
    )
    return execution.response


def try_browser_preflight_probe_with_session(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    force_for_http_access_status: bool = False,
) -> BrowserPreflightProbeExecution:
    """Retain the live browser only when the probe must escalate to Browser Use."""
    return _run_browser_preflight_probe(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        execution_url=execution_url,
        download_dir=download_dir,
        retain_browser_session=True,
        force_for_http_access_status=force_for_http_access_status,
    )


def _run_browser_preflight_probe(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    retain_browser_session: bool,
    force_for_http_access_status: bool,
) -> BrowserPreflightProbeExecution:
    started = time.monotonic()
    target_url = str(execution_url or request.attempt_url or request.url).strip()
    skip_reason = _preflight_skip_reason(
        request,
        force_for_http_access_status=force_for_http_access_status,
    )
    if skip_reason:
        probe = _probe_result(
            status="escalated",
            started_url=target_url,
            duration_seconds=0.0,
            escalation_reason=skip_reason,
            evidence_labels=["preflight_skipped", skip_reason],
            reuse_state=BrowserPreflightReuseState(
                schema_version="1.0",
                status="skipped",
                final_url=target_url,
                candidate_pdf_urls=[],
            ),
        )
        _log_probe_complete(ctx=ctx, normalized_url=normalized_url, probe=probe)
        return BrowserPreflightProbeExecution(
            response=BrowserPreflightProbeResponse(schema_version="1.0", probe=probe),
            browser_session=None,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_browser_preflight_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "execution_url": target_url,
                "route_family_hint": request.route_family_hint or "",
                "force_for_http_access_status": force_for_http_access_status,
                "event_drain_seconds": _PREFLIGHT_EVENT_DRAIN_SECONDS,
            },
        )
    )
    browser_session: BrowserPreflightSession | None = None
    response: BrowserPreflightProbeResponse | None = None
    terminal_outcome = "failed"
    terminal_error_code = "browser_preflight_failed"
    verified_artifact_count = 0
    phase = "runtime_load"
    try:
        try:
            browser_use = import_module("browser_use")
        except ModuleNotFoundError:
            browser_use = load_browser_use_runtime(normalized_url=normalized_url)
        phase = "browser_session_create"
        browser_session = start_browser_preflight_session(
            browser_use=browser_use,
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
        )
        phase = "browser_start"
        runtime_evidence = _run_preflight_session(
            browser=browser_session.browser,
            request=request,
            target_url=target_url,
            download_dir=download_dir,
            ctx=ctx,
            normalized_url=normalized_url,
            event_loop_runner=browser_session.event_loop_runner,
        )
        phase = "rendered_page_read"
        candidate_urls = _select_pdf_candidates(
            request=request,
            base_url=runtime_evidence["final_url"] or target_url,
            html=runtime_evidence["html"],
            rendered_candidates=runtime_evidence["pdf_candidates"],
            event_urls=runtime_evidence["event_urls"],
        )
        selected_pdf_url = candidate_urls[0] if candidate_urls else ""
        terminal_not_found = _is_terminal_not_found_page(
            title=runtime_evidence["final_title"],
            html=runtime_evidence["html"],
        )
        terminal_access_forbidden = _is_terminal_access_forbidden_page(
            title=runtime_evidence["final_title"],
            html=runtime_evidence["html"],
        )
        terminal_static_archive = terminal_not_found or terminal_access_forbidden
        probe = _probe_result(
            status=(
                "confirmed_direct_pdf"
                if selected_pdf_url
                else "terminal_static_archive"
                if terminal_static_archive
                else "escalated"
            ),
            started_url=target_url,
            final_url=runtime_evidence["final_url"],
            final_title=runtime_evidence["final_title"],
            html_size=int(runtime_evidence["html_size"]),
            duration_seconds=round(time.monotonic() - started, 3),
            candidate_pdf_urls=candidate_urls,
            selected_pdf_url=selected_pdf_url,
            observed_event_urls=runtime_evidence["event_urls"],
            network_event_count=len(runtime_evidence["event_urls"]),
            evidence_labels=[
                *_evidence_labels(
                page_info_html_size=int(runtime_evidence["html_size"]),
                rendered=runtime_evidence,
                event_urls=runtime_evidence["event_urls"],
                selected_pdf_url=selected_pdf_url,
                ),
                *(["preflight_terminal_not_found"] if terminal_not_found else []),
                *(
                    ["preflight_terminal_access_forbidden"]
                    if terminal_access_forbidden
                    else []
                ),
            ],
            escalation_reason=(
                ""
                if selected_pdf_url
                else "terminal_static_archive"
                if terminal_static_archive
                else "no_rendered_pdf_candidate"
            ),
            avoided_agent_call=bool(selected_pdf_url or terminal_static_archive),
            reuse_state=_reuse_state_from_runtime(
                runtime_evidence=runtime_evidence,
                candidate_pdf_urls=candidate_urls,
            ),
        )
        if not selected_pdf_url:
            _log_probe_complete(ctx=ctx, normalized_url=normalized_url, probe=probe)
            response = BrowserPreflightProbeResponse(schema_version="1.0", probe=probe)
            terminal_outcome = "completed"
            if retain_browser_session:
                return BrowserPreflightProbeExecution(
                    response=response,
                    browser_session=browser_session,
                )
            return BrowserPreflightProbeExecution(
                response=response,
                browser_session=None,
            )
        direct_result = try_direct_pdf_download(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            probe_url=selected_pdf_url,
            route_family="browser_preflight_js_pdf_probe",
            used_candidate_pdf_url=False,
            used_candidate_source_page=bool(request.source_page_url_hint),
        )
        if direct_result is None:
            probe = replace(
                probe,
                status="escalated",
                escalation_reason="rendered_pdf_candidate_download_failed",
                avoided_agent_call=False,
                false_negative_rate_sample=0.0,
            )
            _log_probe_complete(ctx=ctx, normalized_url=normalized_url, probe=probe)
            response = BrowserPreflightProbeResponse(schema_version="1.0", probe=probe)
            terminal_outcome = "completed"
            if retain_browser_session:
                return BrowserPreflightProbeExecution(
                    response=response,
                    browser_session=browser_session,
                )
            return BrowserPreflightProbeExecution(
                response=response,
                browser_session=None,
            )
        result = _preflight_result(
            direct_result=direct_result,
            page_url=runtime_evidence["final_url"] or target_url,
            pdf_url=selected_pdf_url,
            probe=probe,
        )
        _log_probe_complete(ctx=ctx, normalized_url=normalized_url, probe=probe)
        response = BrowserPreflightProbeResponse(
            schema_version="1.0", probe=probe, result=result
        )
        terminal_outcome = "completed"
        verified_artifact_count = 1
        return BrowserPreflightProbeExecution(
            response=response,
            browser_session=None,
        )
    except Exception as exc:
        probe = _probe_result(
            status="failed",
            started_url=target_url,
            duration_seconds=round(time.monotonic() - started, 3),
            escalation_reason=f"preflight_failed:{phase}:{type(exc).__name__}",
            evidence_labels=["preflight_failed", f"preflight_phase_{phase}"],
        )
        _log_probe_complete(ctx=ctx, normalized_url=normalized_url, probe=probe)
        response = BrowserPreflightProbeResponse(schema_version="1.0", probe=probe)
        return BrowserPreflightProbeExecution(
            response=response,
            browser_session=None,
        )
    finally:
        if browser_session is not None and not browser_session.closed:
            if (
                retain_browser_session
                and response is not None
                and response.result is None
            ):
                pass
            else:
                close_browser_preflight_session(
                    session=browser_session,
                    ctx=ctx,
                    normalized_url=normalized_url,
                    outcome=terminal_outcome,
                    error_code=(
                        terminal_error_code if terminal_outcome == "failed" else ""
                    ),
                    verified_artifact_count=verified_artifact_count,
                )


def observe_browser_preflight_agent_outcome(
    *,
    probe: BrowserPreflightProbeResult,
    result: BrowserReportDownloadResult,
    ctx: RunContext,
    normalized_url: str,
) -> None:
    false_negative_rate_sample = 0.0
    if (
        probe.status == "escalated"
        and result.route_kind == "pdf_download"
        and result.outcome == "downloaded"
        and probe.escalation_reason == "no_rendered_pdf_candidate"
    ):
        false_negative_rate_sample = 1.0
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_browser_preflight_agent_outcome",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "probe_status": probe.status,
                "probe_escalation_reason": probe.escalation_reason,
                "agent_route_kind": result.route_kind,
                "agent_outcome": result.outcome,
                "avoided_agent_call": False,
                "preflight_duration_seconds": probe.duration_seconds,
                "false_negative_rate_sample": false_negative_rate_sample,
                "candidate_pdf_url_count": len(probe.candidate_pdf_urls),
                "evidence_labels": list(probe.evidence_labels),
            },
        )
    )


def _preflight_result(
    *,
    direct_result: BrowserReportDownloadResult,
    page_url: str,
    pdf_url: str,
    probe: BrowserPreflightProbeResult,
) -> BrowserReportDownloadResult:
    extraction_evidence = _route_step_evidence(probe)
    return replace(
        direct_result,
        route_family="browser_preflight_js_pdf_probe",
        route_summary=(
            "Open the page in a bounded browser preflight, drain rendered DOM and "
            "resource events, extract the rendered PDF link, and save the verified PDF locally."
        ),
        route_steps=[
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="open",
                target_text=page_url,
                target_role="url",
                target_url=page_url,
                result="Rendered the report page in browser preflight",
                expected_evidence=["page_info"],
                observed_evidence=["page_info"],
                verification_status="verified",
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=1,
                action="extract",
                target_text=pdf_url,
                target_role="link",
                target_url=pdf_url,
                result="Extracted a rendered PDF link before full agent launch",
                expected_evidence=extraction_evidence,
                observed_evidence=extraction_evidence,
                verification_status="verified",
            ),
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=2,
                action="open",
                target_text=pdf_url,
                target_role="url",
                target_url=pdf_url,
                result="downloaded",
                expected_evidence=["artifact"],
                observed_evidence=["artifact"],
                verification_status="verified",
            ),
        ],
        terminal_evidence=replace(
            direct_result.terminal_evidence,
            traversed_page_urls=[page_url, pdf_url],
            observed_document_urls=[pdf_url],
            evidence_labels=[
                "browser_preflight_js_pdf_probe",
                *probe.evidence_labels,
                *(
                    ["preflight_reuse_state_available"]
                    if probe.reuse_state is not None
                    else []
                ),
                "verified",
                "application/pdf",
            ],
        ),
    )


def _route_step_evidence(probe: BrowserPreflightProbeResult) -> list[str]:
    evidence = [
        item
        for item in (
            "page_info",
            "js_rendered_dom",
            "network_event",
            "rendered_pdf_candidate",
        )
        if item in probe.evidence_labels
    ]
    return evidence or ["page_info"]


def _run_preflight_session(
    *,
    browser: Any,
    request: BrowserReportDownloadRequest,
    target_url: str,
    download_dir: Path,
    ctx: RunContext,
    normalized_url: str,
    event_loop_runner: asyncio.Runner | None = None,
) -> dict[str, Any]:
    coroutine = asyncio.wait_for(
        _run_preflight_session_async(
            browser=browser,
            request=request,
            target_url=target_url,
            download_dir=download_dir,
            ctx=ctx,
            normalized_url=normalized_url,
        ),
        timeout=_PREFLIGHT_SESSION_TIMEOUT_SECONDS,
    )
    return _run_preflight_coroutine(
        coroutine,
        timeout_seconds=_PREFLIGHT_SESSION_TIMEOUT_SECONDS,
        grace_seconds=2.0,
        event_loop_runner=event_loop_runner,
    )


async def _run_preflight_session_async(
    *,
    browser: Any,
    request: BrowserReportDownloadRequest,
    target_url: str,
    download_dir: Path,
    ctx: RunContext,
    normalized_url: str,
) -> dict[str, Any]:
    await _await_if_needed(getattr(browser, "start", lambda: None)())
    await _navigate_browser(browser=browser, url=target_url)
    settle_deadline = time.monotonic() + _PREFLIGHT_REDIRECT_SETTLE_SECONDS
    while True:
        page = await _get_current_page(browser)
        await asyncio.sleep(_PREFLIGHT_EVENT_DRAIN_SECONDS)
        final_url = await _read_browser_url(browser=browser, page=page)
        final_title = await _read_browser_title(browser=browser, page=page)
        html = await _read_page_html(
            page,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        if _is_terminal_not_found_page(title=final_title, html=html):
            break
        if html.strip() or time.monotonic() >= settle_deadline:
            break
    rendered = await _inspect_rendered_page(
        page=page,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    event_urls = await _drain_event_urls(
        page=page,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    return {
        "final_url": final_url or str(rendered.get("location_href") or target_url),
        "final_title": final_title or str(rendered.get("title") or ""),
        "html": html,
        "html_size": int(rendered.get("html_size") or len(html or "")),
        "pdf_candidates": rendered.get("pdf_candidates") or [],
        "event_urls": event_urls,
        "cookie_names": rendered.get("cookie_names") or [],
        "local_storage_keys": rendered.get("local_storage_keys") or [],
    }


async def _inspect_rendered_page(
    *,
    page: Any,
    ctx: RunContext,
    normalized_url: str,
) -> dict[str, Any]:
    script = """
    () => {
      const values = [];
      const push = (value) => {
        const token = String(value || '').trim();
        if (token) values.push(token);
      };
      for (const node of document.querySelectorAll('a[href], iframe[src], embed[src], object[data], [data-href], [data-url]')) {
        push(node.href || node.src || node.data || node.getAttribute('data-href') || node.getAttribute('data-url'));
      }
      const html = document.documentElement?.outerHTML || '';
      const pdfMatches = html.match(/https?:\\/\\/[^\\s"'<>]+?\\.pdf(?:[?#][^\\s"'<>]*)?/gi) || [];
      for (const value of pdfMatches) push(value);
      const formText = Array.from(document.querySelectorAll('form, input, select, textarea, button'))
        .slice(0, 40)
        .map((node) => String(node.innerText || node.textContent || node.getAttribute('aria-label') || node.getAttribute('name') || node.getAttribute('placeholder') || '').trim())
        .filter(Boolean);
      return {
        pdf_candidates: Array.from(new Set(values)),
        form_text: formText,
        location_href: window.location.href,
        title: document.title,
        html_size: html.length,
        cookie_names: document.cookie ? document.cookie.split(';').map((item) => item.split('=')[0].trim()).filter(Boolean) : [],
        local_storage_keys: (() => {
          try {
            return Object.keys(window.localStorage || {});
          } catch (_err) {
            return [];
          }
        })(),
      };
    }
    """
    result = await browser_helper_js_async(
        page=page,
        expression=script,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    return (
        result.result
        if result.status == "ok" and isinstance(result.result, dict)
        else {}
    )


async def _drain_event_urls(
    *,
    page: Any,
    ctx: RunContext,
    normalized_url: str,
) -> list[str]:
    script = """
    () => {
      const entries = [
        ...(globalThis.performance?.getEntriesByType?.('navigation') || []),
        ...(globalThis.performance?.getEntriesByType?.('resource') || []),
      ];
      return entries.map((entry) => String(entry?.name || '').trim()).filter(Boolean);
    }
    """
    result = await browser_helper_js_async(
        page=page,
        expression=script,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if result.status != "ok" or not isinstance(result.result, list):
        return []
    return _normalize_urls([str(value or "").strip() for value in result.result])


def _select_pdf_candidates(
    *,
    request: BrowserReportDownloadRequest,
    base_url: str,
    html: str,
    rendered_candidates: Any,
    event_urls: list[str],
) -> list[str]:
    raw_candidates: list[str] = []
    if isinstance(rendered_candidates, list):
        raw_candidates.extend(str(value or "").strip() for value in rendered_candidates)
    raw_candidates.extend(
        extract_embedded_pdf_urls(wrapper_html=html, document_url=base_url)
    )
    raw_candidates.extend(event_urls)
    for match in _PDF_URL_PATTERN.finditer(str(html or "")):
        raw_candidates.append(match.group(0))
    normalized = []
    for raw_candidate in raw_candidates:
        token = str(raw_candidate or "").strip()
        if not token:
            continue
        resolved = urljoin(base_url, token)
        if any(marker in resolved for marker in ('"', "'", "<", ">", "\n", "\r")):
            continue
        lowered = resolved.casefold()
        if not (lowered.endswith(".pdf") or ".pdf?" in lowered or ".pdf#" in lowered):
            continue
        normalized.append(resolved)
    return _filter_relevant_candidates(request=request, candidates=normalized)


def _is_terminal_not_found_page(*, title: str, html: str) -> bool:
    normalized_html = str(html or "").casefold()
    return any(marker in normalized_html for marker in _TERMINAL_NOT_FOUND_BODY_MARKERS)


def _is_terminal_access_forbidden_page(*, title: str, html: str) -> bool:
    normalized_title = str(title or "").casefold()
    normalized_html = str(html or "").casefold()
    has_403_title = "403 forbidden" in normalized_title
    has_403_body = (
        "error 403 forbidden" in normalized_html
        or "<h1>403 forbidden" in normalized_html
    )
    return has_403_title and has_403_body


def _filter_relevant_candidates(
    *,
    request: BrowserReportDownloadRequest,
    candidates: list[str],
) -> list[str]:
    title_tokens = _candidate_title_tokens(request)
    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        token = str(candidate or "").strip()
        if not token:
            continue
        marker = token.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        if _looks_like_non_report_pdf_url(token):
            continue
        if title_tokens and not any(title in marker for title in title_tokens):
            continue
        normalized.append(token)
    return normalized


def _candidate_title_tokens(request: BrowserReportDownloadRequest) -> list[str]:
    raw_parts = [str(request.report_title or "")]
    if request.candidate_trace is not None:
        raw_parts.append(str(request.candidate_trace.title or ""))
    raw_title = " ".join(raw_parts).casefold()
    tokens: list[str] = []
    seen: set[str] = set()
    for token in re.split(r"[^a-z0-9]+", raw_title):
        if len(token) < 4:
            continue
        if token in _TITLE_TOKEN_STOPWORDS:
            continue
        if re.fullmatch(r"20\d{2}", token):
            continue
        if token in seen:
            continue
        seen.add(token)
        tokens.append(token)
    return tokens[:8]


def _looks_like_non_report_pdf_url(value: str) -> bool:
    lowered = str(value or "").casefold()
    if not lowered:
        return False
    tokens = {
        match.group(0)
        for match in re.finditer(r"[a-z0-9]+", lowered)
        if len(match.group(0)) >= 3
    }
    return bool(tokens & _NON_REPORT_PDF_MARKERS)


def _evidence_labels(
    *,
    page_info_html_size: int,
    rendered: dict[str, Any],
    event_urls: list[str],
    selected_pdf_url: str,
) -> list[str]:
    labels: list[str] = []
    if page_info_html_size > 0 or rendered:
        labels.append("page_info")
    if rendered:
        labels.append("js_rendered_dom")
    if event_urls:
        labels.append("network_event")
    if selected_pdf_url:
        labels.append("rendered_pdf_candidate")
    return labels


def _log_probe_complete(
    *,
    ctx: RunContext,
    normalized_url: str,
    probe: BrowserPreflightProbeResult,
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_browser_preflight_complete",
            module=logger.name,
            fields=browser_preflight_probe_log_fields(
                normalized_url=normalized_url,
                probe=probe,
            ),
        )
    )


def _probe_result(
    *,
    status: str,
    started_url: str,
    duration_seconds: float,
    final_url: str = "",
    final_title: str = "",
    html_size: int = 0,
    candidate_pdf_urls: list[str] | None = None,
    selected_pdf_url: str = "",
    observed_event_urls: list[str] | None = None,
    network_event_count: int = 0,
    evidence_labels: list[str] | None = None,
    escalation_reason: str = "",
    avoided_agent_call: bool = False,
    reuse_state: BrowserPreflightReuseState | None = None,
) -> BrowserPreflightProbeResult:
    return BrowserPreflightProbeResult(
        schema_version=_PREFLIGHT_SCHEMA_VERSION,
        status=status,
        started_url=started_url,
        final_url=final_url,
        final_title=final_title,
        html_size=html_size,
        event_drain_seconds=_PREFLIGHT_EVENT_DRAIN_SECONDS,
        duration_seconds=duration_seconds,
        candidate_pdf_urls=_normalize_urls(candidate_pdf_urls or []),
        selected_pdf_url=selected_pdf_url,
        observed_event_urls=_normalize_urls(observed_event_urls or []),
        network_event_count=network_event_count,
        evidence_labels=_normalize_labels(evidence_labels or []),
        escalation_reason=escalation_reason,
        avoided_agent_call=avoided_agent_call,
        false_negative_rate_sample=0.0,
        reuse_state=reuse_state,
    )


def _preflight_skip_reason(
    request: BrowserReportDownloadRequest,
    *,
    force_for_http_access_status: bool = False,
) -> str:
    if (
        os.environ.get("PYTEST_CURRENT_TEST")
        and getattr(import_module, "__module__", "") == "importlib"
    ):
        return "pytest_importlib_guard"
    route_family = str(request.route_family_hint or "").strip()
    if route_family not in _PREFLIGHT_ROUTE_FAMILIES:
        return "route_family_not_eligible"
    if str(request.attempt_url or request.url).strip().casefold().endswith(".pdf"):
        return "direct_pdf_url"
    if (
        route_family in {"browser_email_form", "browser_listing_hub"}
        and not force_for_http_access_status
        and not _has_preflight_positive_evidence(request)
    ):
        return "preflight_evidence_insufficient_for_route_family"
    return ""


def _should_run_browser_preflight(
    request: BrowserReportDownloadRequest,
    *,
    force_for_http_access_status: bool = False,
) -> bool:
    return not _preflight_skip_reason(
        request,
        force_for_http_access_status=force_for_http_access_status,
    )


def _has_preflight_positive_evidence(request: BrowserReportDownloadRequest) -> bool:
    if str(request.source_page_url_hint or "").strip():
        return True
    candidate_trace = request.candidate_trace
    if candidate_trace is not None:
        for attr in ("pdf_url", "source_page_url", "url"):
            value = str(getattr(candidate_trace, attr, "") or "").strip().casefold()
            if value.endswith(".pdf") or ".pdf?" in value:
                return True
    for playbook in request.selected_playbooks:
        if getattr(playbook, "private_api_evidence", None):
            return True
    return False


def _reuse_state_from_runtime(
    *,
    runtime_evidence: dict[str, Any],
    candidate_pdf_urls: list[str],
) -> BrowserPreflightReuseState:
    return BrowserPreflightReuseState(
        schema_version="1.0",
        status="available",
        final_url=str(runtime_evidence.get("final_url") or "").strip(),
        cookie_names=_normalize_labels(runtime_evidence.get("cookie_names") or []),
        local_storage_keys=_normalize_labels(
            runtime_evidence.get("local_storage_keys") or []
        ),
        candidate_pdf_urls=_normalize_urls(candidate_pdf_urls),
        cleanup_required=False,
    )


def _normalize_urls(raw_urls: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_url in raw_urls:
        token = str(raw_url or "").strip()
        if not token:
            continue
        marker = token.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(token)
    return normalized


def _normalize_labels(raw_labels: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_label in raw_labels:
        token = str(raw_label or "").strip()
        if not token:
            continue
        marker = token.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(token)
    return normalized


def _run_coroutine_in_thread(
    coroutine: Any,
    *,
    timeout_seconds: float,
    grace_seconds: float,
) -> Any:
    """Bound preflight execution even if a browser coroutine ignores cancellation."""
    payload: dict[str, Any] = {}
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            payload["result"] = asyncio.run(coroutine)
        except BaseException as exc:
            errors.append(exc)

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join(max(0.01, timeout_seconds) + max(0.0, grace_seconds))
    if thread.is_alive():
        raise TimeoutError("browser preflight session timed out")
    if errors:
        raise errors[0]
    return payload.get("result")


def _run_preflight_coroutine(
    coroutine: Any,
    *,
    timeout_seconds: float,
    grace_seconds: float,
    event_loop_runner: asyncio.Runner | None = None,
) -> Any:
    """Keep Browser Use on the worker main thread unless a loop is already active.

    The acquisition supervisor already process-isolates synchronous report
    attempts.  Running BrowserSession on that worker's main event loop avoids
    moving its lifecycle onto a daemon thread, while active-loop callers still
    use the bounded watchdog bridge below.
    """
    if event_loop_runner is not None:
        return event_loop_runner.run(coroutine)
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    return _run_coroutine_in_thread(
        coroutine,
        timeout_seconds=timeout_seconds,
        grace_seconds=grace_seconds,
    )


async def _await_if_needed(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


async def _navigate_browser(*, browser: Any, url: str) -> None:
    for name in ("navigate_to", "goto", "open"):
        candidate = getattr(browser, name, None)
        if not callable(candidate):
            continue
        await _await_if_needed(candidate(url))
        return
    raise RuntimeError("browser preflight cannot navigate with this browser runtime")


async def _get_current_page(browser: Any) -> Any:
    current_page = getattr(browser, "get_current_page", None)
    if callable(current_page):
        page = await _await_if_needed(current_page())
    else:
        page = getattr(browser, "page", None)
    if page is None:
        raise RuntimeError("browser preflight could not access current page")
    return page


async def _stop_browser(browser: Any) -> None:
    for name in ("kill", "stop", "close"):
        candidate = getattr(browser, name, None)
        if not callable(candidate):
            continue
        try:
            await _await_if_needed(candidate())
        except Exception:
            continue
        return


async def _read_browser_url(*, browser: Any, page: Any) -> str:
    for owner, names in (
        (browser, ("get_current_page_url",)),
        (page, ("url",)),
        (browser, ("url",)),
    ):
        for name in names:
            value = getattr(owner, name, None)
            if callable(value):
                value = await _await_if_needed(value())
            token = str(value or "").strip()
            if token:
                return token
    return ""


async def _read_browser_title(*, browser: Any, page: Any) -> str:
    for owner, names in (
        (browser, ("get_current_page_title",)),
        (page, ("title",)),
        (browser, ("title",)),
    ):
        for name in names:
            value = getattr(owner, name, None)
            if callable(value):
                value = await _await_if_needed(value())
            token = str(value or "").strip()
            if token:
                return token
    return ""


async def _read_page_html(
    page: Any,
    *,
    ctx: RunContext,
    normalized_url: str,
) -> str:
    for name in ("content", "get_content"):
        candidate = getattr(page, name, None)
        if not callable(candidate):
            continue
        value = await _await_if_needed(candidate())
        html = str(value or "")
        if html:
            return html
    result = await browser_helper_js_async(
        page=page,
        expression="return document.documentElement?.outerHTML || ''",
        ctx=ctx,
        normalized_url=normalized_url,
    )
    return str(result.result or "") if result.status == "ok" else ""
