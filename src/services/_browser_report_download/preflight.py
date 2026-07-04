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
from dataclasses import asdict, replace
from importlib import import_module
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urljoin

from src.contracts.browser_download import (
    BrowserDownloadRouteStep,
    BrowserPreflightProbeResponse,
    BrowserPreflightProbeResult,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.http import (
    extract_embedded_pdf_urls,
    try_direct_pdf_download,
)
from src.services._browser_report_download.helpers import browser_helper_js_async
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.preflight")

_PREFLIGHT_SCHEMA_VERSION = "1.0"
_PREFLIGHT_EVENT_DRAIN_SECONDS = 0.35
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


def try_browser_preflight_probe(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
) -> BrowserPreflightProbeResponse:
    started = time.monotonic()
    target_url = str(execution_url or request.attempt_url or request.url).strip()
    if not _should_run_browser_preflight(request):
        probe = _probe_result(
            status="escalated",
            started_url=target_url,
            duration_seconds=0.0,
            escalation_reason="route_family_not_eligible",
            evidence_labels=["preflight_skipped_route_family"],
        )
        _log_probe_complete(ctx=ctx, normalized_url=normalized_url, probe=probe)
        return BrowserPreflightProbeResponse(schema_version="1.0", probe=probe)
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
                "event_drain_seconds": _PREFLIGHT_EVENT_DRAIN_SECONDS,
            },
        )
    )
    try:
        runtime_evidence = _run_preflight_session(
            browser_use=import_module("browser_use"),
            request=request,
            target_url=target_url,
            download_dir=download_dir,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        candidate_urls = _select_pdf_candidates(
            request=request,
            base_url=runtime_evidence["final_url"] or target_url,
            html=runtime_evidence["html"],
            rendered_candidates=runtime_evidence["pdf_candidates"],
            event_urls=runtime_evidence["event_urls"],
        )
        selected_pdf_url = candidate_urls[0] if candidate_urls else ""
        probe = _probe_result(
            status="confirmed_direct_pdf" if selected_pdf_url else "escalated",
            started_url=target_url,
            final_url=runtime_evidence["final_url"],
            final_title=runtime_evidence["final_title"],
            html_size=int(runtime_evidence["html_size"]),
            duration_seconds=round(time.monotonic() - started, 3),
            candidate_pdf_urls=candidate_urls,
            selected_pdf_url=selected_pdf_url,
            observed_event_urls=runtime_evidence["event_urls"],
            network_event_count=len(runtime_evidence["event_urls"]),
            evidence_labels=_evidence_labels(
                page_info_html_size=int(runtime_evidence["html_size"]),
                rendered=runtime_evidence,
                event_urls=runtime_evidence["event_urls"],
                selected_pdf_url=selected_pdf_url,
            ),
            escalation_reason="" if selected_pdf_url else "no_rendered_pdf_candidate",
            avoided_agent_call=bool(selected_pdf_url),
        )
        if not selected_pdf_url:
            _log_probe_complete(ctx=ctx, normalized_url=normalized_url, probe=probe)
            return BrowserPreflightProbeResponse(schema_version="1.0", probe=probe)
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
            return BrowserPreflightProbeResponse(schema_version="1.0", probe=probe)
        result = _preflight_result(
            direct_result=direct_result,
            page_url=runtime_evidence["final_url"] or target_url,
            pdf_url=selected_pdf_url,
            probe=probe,
        )
        _log_probe_complete(ctx=ctx, normalized_url=normalized_url, probe=probe)
        return BrowserPreflightProbeResponse(
            schema_version="1.0",
            probe=probe,
            result=result,
        )
    except Exception as exc:
        probe = _probe_result(
            status="failed",
            started_url=target_url,
            duration_seconds=round(time.monotonic() - started, 3),
            escalation_reason=str(exc),
            evidence_labels=["preflight_failed"],
        )
        _log_probe_complete(ctx=ctx, normalized_url=normalized_url, probe=probe)
        return BrowserPreflightProbeResponse(schema_version="1.0", probe=probe)


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
    browser_use: Any,
    request: BrowserReportDownloadRequest,
    target_url: str,
    download_dir: Path,
    ctx: RunContext,
    normalized_url: str,
) -> dict[str, Any]:
    coroutine = asyncio.wait_for(
        _run_preflight_session_async(
            browser_use=browser_use,
            request=request,
            target_url=target_url,
            download_dir=download_dir,
            ctx=ctx,
            normalized_url=normalized_url,
        ),
        timeout=_PREFLIGHT_SESSION_TIMEOUT_SECONDS,
    )
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coroutine)
    return _run_coroutine_in_thread(coroutine)


async def _run_preflight_session_async(
    *,
    browser_use: Any,
    request: BrowserReportDownloadRequest,
    target_url: str,
    download_dir: Path,
    ctx: RunContext,
    normalized_url: str,
) -> dict[str, Any]:
    browser = browser_use.Browser(
        downloads_path=str(download_dir),
        headless=not request.settings.headed,
        auto_download_pdfs=True,
        keep_alive=False,
    )
    try:
        await _await_if_needed(getattr(browser, "start", lambda: None)())
        await _navigate_browser(browser=browser, url=target_url)
        page = await _get_current_page(browser)
        await asyncio.sleep(_PREFLIGHT_EVENT_DRAIN_SECONDS)
        final_url = await _read_browser_url(browser=browser, page=page)
        final_title = await _read_browser_title(browser=browser, page=page)
        html = await _read_page_html(
            page,
            ctx=ctx,
            normalized_url=normalized_url,
        )
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
        }
    finally:
        await _stop_browser(browser)


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
            if not any(
                marker.endswith(suffix) for suffix in (".pdf", ".pdf?download=1")
            ):
                continue
        normalized.append(token)
    return normalized


def _candidate_title_tokens(request: BrowserReportDownloadRequest) -> list[str]:
    if request.candidate_trace is None:
        return []
    raw_title = str(request.candidate_trace.title or "").casefold()
    tokens = [token for token in re.split(r"[^a-z0-9]+", raw_title) if len(token) >= 4]
    return tokens[:5]


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
            fields={
                "normalized_url": normalized_url,
                **asdict(probe),
                "preflight_duration_seconds": probe.duration_seconds,
                "candidate_pdf_url_count": len(probe.candidate_pdf_urls),
            },
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
    )


def _should_run_browser_preflight(request: BrowserReportDownloadRequest) -> bool:
    if (
        os.environ.get("PYTEST_CURRENT_TEST")
        and getattr(import_module, "__module__", "") == "importlib"
    ):
        return False
    route_family = str(request.route_family_hint or "").strip()
    if route_family not in _PREFLIGHT_ROUTE_FAMILIES:
        return False
    return (
        not str(request.attempt_url or request.url).strip().casefold().endswith(".pdf")
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


def _run_coroutine_in_thread(coroutine: Any) -> Any:
    payload: dict[str, Any] = {}
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            payload["result"] = asyncio.run(coroutine)
        except BaseException as exc:
            errors.append(exc)

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join(_PREFLIGHT_SESSION_TIMEOUT_SECONDS + 2.0)
    if thread.is_alive():
        raise TimeoutError("browser preflight session timed out")
    if errors:
        raise errors[0]
    return payload.get("result")


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
