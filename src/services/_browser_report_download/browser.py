from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import psutil
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from importlib import import_module
from pathlib import Path
from threading import Thread
from typing import Any

from src.contracts.browser_download import (
    BrowserDownloadNetworkEvent,
    BrowserReportDownloadRequest,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.artifact import BrowserUseAgentResult
from src.services._browser_report_download.prompt import BrowserDownloadPromptBundle
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_TERMINAL_TRANSIENT_MARKERS = (
    "please wait",
    "submitting",
    "processing",
    "loading",
    "one moment",
)
_TERMINAL_STABILIZATION_POLL_SECONDS = 2.0
_TERMINAL_STABILIZATION_MAX_ATTEMPTS = 3
_AGENT_RUN_TIMEOUT_MIN_BUFFER_SECONDS = 1.0
_AGENT_RUN_TIMEOUT_STEP_BUFFER_SECONDS = 0.5
_AGENT_RUN_TIMEOUT_MAX_BUFFER_SECONDS = 30.0
_BROWSER_KILL_TIMEOUT_SECONDS = 15.0
_BROWSER_RESET_TIMEOUT_SECONDS = 10.0
_BROWSER_PROFILE_DIR_PREFIX = "browser-use-user-data-dir-profile"
_BROWSER_USE_TEMP_DIR_PATTERNS = (
    "browser-use-user-data-dir-*",
    "browser-use-downloads-*",
    "browseruse-tmp-*",
)
_STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS = 15 * 60.0
_TEMP_CLEANUP_LOG_SAMPLE_LIMIT = 5
_TIMED_OUT_AGENT_STOP_GRACE_SECONDS = 10.0
_BROWSER_AGENT_WORKER_ENV = "MARKET_LENSE_BROWSER_AGENT_WORKER"
_BROWSER_AGENT_WORKER_TIMEOUT_BUFFER_SECONDS = 30.0


@dataclass(frozen=True)
class BrowserAgentRunResult:
    schema_version: str
    raw_model_response: str
    final_page_url: str
    final_page_title: str
    final_page_html: str
    downloaded_files: list[str]
    attachment_paths: list[str]
    network_resource_urls: list[str]
    network_events: list[BrowserDownloadNetworkEvent]
    html_snapshot_path: str
    screenshot_path: str


@dataclass(frozen=True)
class TerminalSnapshot:
    page: Any
    url: str
    title: str
    html: str


@dataclass(frozen=True)
class BrowserAgentWorkerPayload:
    schema_version: str
    request: dict[str, Any]
    ctx: dict[str, Any]
    normalized_url: str
    execution_url: str
    download_dir: str
    prompt_bundle: dict[str, Any]


@dataclass(frozen=True)
class BrowserAgentWorkerResponse:
    schema_version: str
    status: str
    result: dict[str, Any] | None
    error: dict[str, Any] | None


def run_browser_report_download_agent(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    prompt_bundle: BrowserDownloadPromptBundle,
) -> BrowserAgentRunResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_request",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "execution_url": execution_url,
                "route_family_hint": request.route_family_hint or "",
                "prompt_namespace": prompt_bundle.namespace,
                "task_prompt": prompt_bundle.task_prompt,
            },
        )
    )
    browser_use = _load_browser_use_runtime(normalized_url)
    if _should_run_browser_agent_in_subprocess(browser_use):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_worker_dispatch",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "download_dir": str(download_dir),
                },
            )
        )
        return _run_browser_report_download_agent_subprocess(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            execution_url=execution_url,
            download_dir=download_dir,
            prompt_bundle=prompt_bundle,
        )
    browser: Any | None = None
    _cleanup_stale_browser_use_temp_dirs(ctx=ctx, normalized_url=normalized_url)
    preexisting_temp_dirs = {str(path) for path in _list_browser_use_temp_dirs()}
    _cleanup_managed_browser_profile_dirs(download_dir=download_dir)
    profile_dir = _new_managed_browser_profile_dir(download_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    raw_model_response = ""
    final_page_url = ""
    final_page_title = ""
    final_page_html = ""
    downloaded_files: list[str] = []
    attachment_paths: list[str] = []
    network_resource_urls: list[str] = []
    network_events: list[BrowserDownloadNetworkEvent] = []
    html_snapshot_path = ""
    screenshot_path = ""
    try:
        browser = browser_use.Browser(
            downloads_path=str(download_dir),
            user_data_dir=str(profile_dir),
            headless=not request.settings.headed,
            auto_download_pdfs=True,
            keep_alive=True,
        )
        llm = browser_use.ChatOpenRouter(
            model=request.settings.model,
            api_key=request.settings.openrouter_api_key,
            http_referer=request.settings.openrouter_http_referer,
            temperature=request.settings.temperature,
            timeout=request.settings.timeout_seconds,
        )
        agent = browser_use.Agent(
            task=prompt_bundle.task_prompt,
            llm=llm,
            browser=browser,
            output_model_schema=BrowserUseAgentResult,
        )
        history = _run_agent_history_with_timeout(
            agent=agent,
            browser=browser,
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        _prepare_browser_for_shutdown(browser)
        raw_model_response = str(history.final_result() or "").strip()
        history_final_page_url = _read_history_final_page_url(history)
        history_final_page_title = _read_history_final_page_title(history)
        attachment_paths = _read_history_attachment_paths(history)
        history_screenshot_path = _copy_history_screenshot(
            history=history,
            download_dir=download_dir,
        )
        terminal_snapshot = _capture_terminal_snapshot(browser)
        terminal_snapshot = _stabilize_terminal_snapshot(
            browser=browser,
            raw_model_response=raw_model_response,
            snapshot=terminal_snapshot,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        current_page = terminal_snapshot.page
        final_page_url = (
            terminal_snapshot.url
            or history_final_page_url
        )
        final_page_title = (
            terminal_snapshot.title
            or history_final_page_title
        )
        final_page_html = terminal_snapshot.html
        downloaded_files = [
            str(path) for path in getattr(browser, "downloaded_files", [])
        ]
        (
            network_resource_urls,
            network_events,
            html_snapshot_path,
            screenshot_path,
        ) = _capture_terminal_assets(
            browser=browser,
            page=current_page,
            download_dir=download_dir,
            final_page_html=final_page_html,
        )
        if not screenshot_path:
            screenshot_path = history_screenshot_path
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url, "error": exc.message},
            )
        )
        raise
    except Exception as exc:
        if _is_browser_start_timeout_error(exc):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_failed",
                    module=logger.name,
                    fields={"normalized_url": normalized_url, "error": str(exc)},
                )
            )
            raise AppError(
                code="browser_download_browser_start_timeout",
                message="browser-use timed out while starting the local browser session",
                cause=exc,
                retryable=True,
                context={"normalized_url": normalized_url},
            ) from exc
        if _is_no_space_error(exc):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_failed",
                    module=logger.name,
                    fields={"normalized_url": normalized_url, "error": str(exc)},
                )
            )
            raise AppError(
                code="browser_download_storage_full",
                message="The browser download runtime ran out of local disk space",
                cause=exc,
                retryable=True,
                context={"normalized_url": normalized_url},
            ) from exc
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url, "error": str(exc)},
            )
        )
        raise AppError(
            code="browser_download_agent_failed",
            message="browser-use failed to complete the report download task",
            cause=exc,
            retryable=True,
            context={"normalized_url": normalized_url},
        ) from exc
    finally:
        if browser is not None:
            _prepare_browser_for_shutdown(browser)
            _kill_browser(browser, ctx=ctx, normalized_url=normalized_url)
        _cleanup_browser_profile_dir(profile_dir)
        _cleanup_new_browser_use_temp_dirs(
            ctx=ctx,
            normalized_url=normalized_url,
            preexisting_temp_dirs=preexisting_temp_dirs,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "raw_model_response": raw_model_response,
                "downloaded_files": downloaded_files,
                "attachment_paths": attachment_paths,
                "browser_final_url": final_page_url,
                "browser_final_title": final_page_title,
                "browser_final_html_size": len(final_page_html),
                "browser_network_resource_url_count": len(network_resource_urls),
                "browser_network_event_count": len(network_events),
                "browser_html_snapshot_path": html_snapshot_path,
                "browser_screenshot_path": screenshot_path,
            },
        )
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response=raw_model_response,
        final_page_url=final_page_url,
        final_page_title=final_page_title,
        final_page_html=final_page_html,
        downloaded_files=downloaded_files,
        attachment_paths=attachment_paths,
        network_resource_urls=network_resource_urls,
        network_events=network_events,
        html_snapshot_path=html_snapshot_path,
        screenshot_path=screenshot_path,
    )


def _should_run_browser_agent_in_subprocess(browser_use: Any) -> bool:
    if os.environ.get(_BROWSER_AGENT_WORKER_ENV) == "1":
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return True


def _run_browser_report_download_agent_subprocess(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    prompt_bundle: BrowserDownloadPromptBundle,
) -> BrowserAgentRunResult:
    download_dir.mkdir(parents=True, exist_ok=True)
    payload = BrowserAgentWorkerPayload(
        schema_version="1.0",
        request=asdict(request),
        ctx=asdict(ctx),
        normalized_url=normalized_url,
        execution_url=execution_url,
        download_dir=str(download_dir),
        prompt_bundle=asdict(prompt_bundle),
    )
    payload_path = download_dir / "browser_agent_worker_request.json"
    response_path = download_dir / "browser_agent_worker_response.json"
    payload_path.write_text(
        json.dumps(asdict(payload), ensure_ascii=True),
        encoding="utf-8",
    )
    response_path.unlink(missing_ok=True)
    env = dict(os.environ)
    env[_BROWSER_AGENT_WORKER_ENV] = "1"
    timeout_seconds = (
        _resolve_agent_run_timeout_seconds(request)
        + _BROWSER_AGENT_WORKER_TIMEOUT_BUFFER_SECONDS
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_worker_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "payload_path": str(payload_path),
                "response_path": str(response_path),
                "timeout_seconds": timeout_seconds,
            },
        )
    )
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.services._browser_report_download.browser_worker",
                str(payload_path),
                str(response_path),
            ],
            check=False,
            cwd=str(Path.cwd()),
            env=env,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise AppError(
            code="browser_download_agent_timeout",
            message="browser-use did not return within the configured execution budget",
            cause=exc,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "timeout_seconds": timeout_seconds,
                "max_steps": request.settings.max_steps,
            },
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_worker_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "payload_path": str(payload_path),
                "response_path": str(response_path),
                "return_code": completed.returncode,
                "response_exists": response_path.exists(),
            },
        )
    )
    if not response_path.exists():
        raise AppError(
            code="browser_download_agent_missing_result",
            message="browser-use worker completed without writing a response payload",
            retryable=True,
            context={"normalized_url": normalized_url},
        )
    raw_response = json.loads(response_path.read_text(encoding="utf-8"))
    response = BrowserAgentWorkerResponse(
        schema_version=str(raw_response.get("schema_version", "1.0")),
        status=str(raw_response.get("status", "")).strip(),
        result=raw_response.get("result")
        if isinstance(raw_response.get("result"), dict)
        else None,
        error=raw_response.get("error")
        if isinstance(raw_response.get("error"), dict)
        else None,
    )
    if response.status == "ok" and response.result is not None:
        return _deserialize_browser_agent_run_result(response.result)
    if response.error is not None:
        raise AppError(
            code=str(response.error.get("code") or "browser_download_agent_failed"),
            message=str(
                response.error.get("message")
                or "browser-use worker failed to complete the report download task"
            ),
            retryable=bool(response.error.get("retryable", True)),
            severity=str(response.error.get("severity") or "error"),
            context=response.error.get("context")
            if isinstance(response.error.get("context"), dict)
            else {"normalized_url": normalized_url},
        )
    raise AppError(
        code="browser_download_agent_failed",
        message="browser-use worker failed to complete the report download task",
        retryable=True,
        context={"normalized_url": normalized_url},
    )


def _deserialize_browser_agent_run_result(payload: dict[str, Any]) -> BrowserAgentRunResult:
    network_events_payload = payload.get("network_events")
    network_events: list[BrowserDownloadNetworkEvent] = []
    if isinstance(network_events_payload, list):
        for item in network_events_payload:
            if not isinstance(item, dict):
                continue
            network_events.append(
                BrowserDownloadNetworkEvent(
                    schema_version=str(item.get("schema_version", "1.0")),
                    url=str(item.get("url") or "").strip(),
                    initiator_type=str(item.get("initiator_type") or "other").strip() or "other",
                    signal_kind=str(item.get("signal_kind") or "other").strip() or "other",
                )
            )
    return BrowserAgentRunResult(
        schema_version=str(payload.get("schema_version", "1.0")),
        raw_model_response=str(payload.get("raw_model_response") or ""),
        final_page_url=str(payload.get("final_page_url") or ""),
        final_page_title=str(payload.get("final_page_title") or ""),
        final_page_html=str(payload.get("final_page_html") or ""),
        downloaded_files=[
            str(item)
            for item in payload.get("downloaded_files", [])
            if str(item or "").strip()
        ],
        attachment_paths=[
            str(item)
            for item in payload.get("attachment_paths", [])
            if str(item or "").strip()
        ],
        network_resource_urls=[
            str(item)
            for item in payload.get("network_resource_urls", [])
            if str(item or "").strip()
        ],
        network_events=network_events,
        html_snapshot_path=str(payload.get("html_snapshot_path") or ""),
        screenshot_path=str(payload.get("screenshot_path") or ""),
    )


def _capture_terminal_snapshot(browser: Any) -> TerminalSnapshot:
    page = _resolve_current_page(browser)
    return TerminalSnapshot(
        page=page,
        url=(
            str(getattr(browser, "url", "") or "").strip()
            or _read_browser_current_page_url(browser)
            or _read_page_url(page)
        ),
        title=(
            str(getattr(browser, "title", "") or "").strip()
            or _read_browser_current_page_title(browser)
            or _read_page_title(page)
        ),
        html=str(getattr(browser, "html", "") or "") or _read_page_html(page),
    )


def _stabilize_terminal_snapshot(
    *,
    browser: Any,
    raw_model_response: str,
    snapshot: TerminalSnapshot,
    ctx: RunContext,
    normalized_url: str,
) -> TerminalSnapshot:
    reason = _terminal_stabilization_reason(
        raw_model_response=raw_model_response,
        snapshot=snapshot,
    )
    if not reason:
        return snapshot
    stabilized_snapshot = snapshot
    attempts = 0
    for attempt in range(_TERMINAL_STABILIZATION_MAX_ATTEMPTS):
        attempts = attempt + 1
        time.sleep(_TERMINAL_STABILIZATION_POLL_SECONDS)
        candidate = _capture_terminal_snapshot(browser)
        stabilized_snapshot = _merge_terminal_snapshots(
            previous=stabilized_snapshot,
            candidate=candidate,
        )
        if not _terminal_stabilization_reason(
            raw_model_response=raw_model_response,
            snapshot=stabilized_snapshot,
        ):
            break
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_terminal_stabilized",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "stabilization_reason": reason,
                "attempts": attempts,
                "final_url": stabilized_snapshot.url,
                "final_title": stabilized_snapshot.title,
                "final_html_size": len(stabilized_snapshot.html),
            },
        )
    )
    return stabilized_snapshot


def _terminal_stabilization_reason(
    *,
    raw_model_response: str,
    snapshot: TerminalSnapshot,
) -> str:
    payload = _parse_raw_model_response(raw_model_response)
    email_submission_completed = payload.get("email_submission_completed") is True
    post_submit_message = str(payload.get("post_submit_message") or "").strip()
    submit_button_state = str(payload.get("submit_button_state") or "").strip().lower()
    snapshot_transient = _contains_transient_terminal_marker(
        " ".join([snapshot.title, snapshot.html])
    )
    if email_submission_completed and (
        _contains_transient_terminal_marker(post_submit_message)
        or submit_button_state == "disabled"
        or snapshot_transient
    ):
        return "transient_submit_state"
    if email_submission_completed and not snapshot.html.strip():
        return "empty_terminal_html_after_submit"
    return ""


def _parse_raw_model_response(raw_model_response: str) -> dict[str, Any]:
    token = str(raw_model_response or "").strip()
    if not token:
        return {}
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _contains_transient_terminal_marker(text: str) -> bool:
    token = str(text or "").strip().casefold()
    if not token:
        return False
    return any(marker in token for marker in _TERMINAL_TRANSIENT_MARKERS)


def _merge_terminal_snapshots(
    *,
    previous: TerminalSnapshot,
    candidate: TerminalSnapshot,
) -> TerminalSnapshot:
    html = previous.html
    candidate_html = str(candidate.html or "")
    if candidate_html.strip() and (
        not html.strip()
        or len(candidate_html) >= len(html)
        or (
            _contains_transient_terminal_marker(html)
            and not _contains_transient_terminal_marker(candidate_html)
        )
    ):
        html = candidate_html
    return TerminalSnapshot(
        page=candidate.page if candidate.page is not None else previous.page,
        url=str(candidate.url or "").strip() or previous.url,
        title=str(candidate.title or "").strip() or previous.title,
        html=html,
    )


def _capture_terminal_assets(
    *,
    browser: Any,
    page: Any,
    download_dir: Path,
    final_page_html: str,
) -> tuple[list[str], list[BrowserDownloadNetworkEvent], str, str]:
    network_events = _collect_network_events(page=page)
    network_resource_urls = _collect_network_resource_urls(
        page=page,
        final_page_html=final_page_html,
        network_events=network_events,
    )
    html_snapshot_path = _write_terminal_html_snapshot(
        download_dir=download_dir,
        final_page_html=final_page_html,
    )
    screenshot_path = _write_terminal_screenshot(
        browser=browser,
        page=page,
        download_dir=download_dir,
    )
    return network_resource_urls, network_events, html_snapshot_path, screenshot_path


def _collect_network_resource_urls(
    *,
    page: Any,
    final_page_html: str,
    network_events: list[BrowserDownloadNetworkEvent],
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    def add(raw_url: Any) -> None:
        token = str(raw_url or "").strip()
        if not _looks_like_documentish_url(token):
            return
        marker = token.casefold()
        if marker in seen:
            return
        seen.add(marker)
        normalized.append(token)

    if page is not None:
        for raw_url in _collect_page_resource_urls(page):
            add(raw_url)
        for raw_url in _collect_dom_candidate_urls(page):
            add(raw_url)
    for event in network_events:
        add(event.url)
    for raw_url in _extract_documentish_urls_from_html(final_page_html):
        add(raw_url)
    return normalized


def _collect_network_events(page: Any) -> list[BrowserDownloadNetworkEvent]:
    if page is None:
        return []
    try:
        raw_events = _maybe_await(
            page.evaluate(
                """
                () => {
                  const build = (entry, initiatorFallback = 'other') => ({
                    url: String(entry?.name || '').trim(),
                    initiator_type: String(entry?.initiatorType || initiatorFallback || 'other').trim(),
                  });
                  const navigationEntries = (globalThis.performance?.getEntriesByType?.('navigation') || [])
                    .map((entry) => build(entry, 'navigation'));
                  const resourceEntries = (globalThis.performance?.getEntriesByType?.('resource') || [])
                    .map((entry) => build(entry, 'other'));
                  return [...navigationEntries, ...resourceEntries];
                }
                """
            )
        )
    except Exception:
        return []
    raw_events = _coerce_evaluate_list(raw_events)
    events: list[BrowserDownloadNetworkEvent] = []
    seen: set[tuple[str, str]] = set()
    for raw_event in raw_events:
        if isinstance(raw_event, dict):
            url = str(raw_event.get("url") or raw_event.get("name") or "").strip()
            initiator_type = (
                str(
                    raw_event.get("initiator_type")
                    or raw_event.get("initiatorType")
                    or "other"
                ).strip()
                or "other"
            )
        else:
            url = str(raw_event or "").strip()
            initiator_type = "other"
        if not url or not url.casefold().startswith("http"):
            continue
        key = (url.casefold(), initiator_type.casefold())
        if key in seen:
            continue
        seen.add(key)
        events.append(
            BrowserDownloadNetworkEvent(
                schema_version="1.0",
                url=url,
                initiator_type=initiator_type,
                signal_kind=_classify_network_signal_kind(
                    url=url,
                    initiator_type=initiator_type,
                ),
            )
        )
    return events[-25:]


def _classify_network_signal_kind(*, url: str, initiator_type: str) -> str:
    lowered_url = str(url or "").strip().casefold()
    lowered_initiator = str(initiator_type or "").strip().casefold()
    if not lowered_url:
        return "other"
    if lowered_url.endswith(".pdf") or ".pdf?" in lowered_url:
        return "document_request"
    if any(marker in lowered_url for marker in ("thank", "success", "confirm", "complete", "done")):
        return "confirmation_request"
    if any(
        marker in lowered_url
        for marker in (
            "download",
            "document",
            "whitepaper",
            "research",
            "study",
            "ebook",
            "report",
        )
    ):
        return "document_request"
    if lowered_initiator in {"fetch", "xmlhttprequest", "beacon"} and any(
        marker in lowered_url
        for marker in (
            "form",
            "submit",
            "lead",
            "register",
            "request",
            "contact",
            "marketo",
            "pardot",
            "hubspot",
            "eloqua",
        )
    ):
        return "submission_request"
    if lowered_initiator == "navigation":
        return "navigation_request"
    return "other"


def _collect_page_resource_urls(page: Any) -> list[str]:
    try:
        resource_urls = _maybe_await(
            page.evaluate(
                """
                () => {
                  const entries = globalThis.performance?.getEntriesByType?.('resource') || [];
                  return entries
                    .map((entry) => String(entry?.name || '').trim())
                    .filter(Boolean)
                    .filter((url) => {
                      const lowered = url.toLowerCase();
                      return lowered.endsWith('.pdf')
                        || lowered.includes('.pdf?')
                        || lowered.includes('download')
                        || lowered.includes('document')
                        || lowered.includes('report');
                    });
                }
                """
            )
        )
    except Exception:
        return []
    resource_urls = _coerce_evaluate_list(resource_urls)
    return [str(raw_url or "").strip() for raw_url in resource_urls if str(raw_url or "").strip()]


def _collect_dom_candidate_urls(page: Any) -> list[str]:
    try:
        candidate_urls = _maybe_await(
            page.evaluate(
                """
                () => {
                  const selectors = [
                    'a[href]',
                    'iframe[src]',
                    'embed[src]',
                    'object[data]',
                    'source[src]',
                    'link[href]',
                    'meta[content]',
                  ];
                  const values = [];
                  for (const selector of selectors) {
                    for (const node of document.querySelectorAll(selector)) {
                      const value =
                        node.getAttribute('href')
                        || node.getAttribute('src')
                        || node.getAttribute('data')
                        || node.getAttribute('content')
                        || '';
                      if (value) {
                        values.push(String(value).trim());
                      }
                    }
                  }
                  return values;
                }
                """
            )
        )
    except Exception:
        return []
    candidate_urls = _coerce_evaluate_list(candidate_urls)
    return [str(raw_url or "").strip() for raw_url in candidate_urls if str(raw_url or "").strip()]


def _coerce_evaluate_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    token = str(value or "").strip()
    if not token:
        return []
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _extract_documentish_urls_from_html(html: str) -> list[str]:
    token = str(html or "")
    if not token.strip():
        return []
    urls: list[str] = []
    for match in re.finditer(
        r"""(?is)(?:href|src|data|content)\s*=\s*['"]([^'"]+)['"]""",
        token,
    ):
        candidate = str(match.group(1) or "").strip()
        if candidate:
            urls.append(candidate)
    return urls


def _looks_like_documentish_url(raw_url: str) -> bool:
    token = str(raw_url or "").strip()
    if not token:
        return False
    lowered = token.casefold()
    if not lowered.startswith("http"):
        return False
    if lowered.endswith(".pdf") or ".pdf?" in lowered:
        return True
    return any(
        marker in lowered
        for marker in (
            "download",
            "document",
            "report",
            "whitepaper",
            "research",
            "study",
            "ebook",
            "insight",
        )
    )


def _resolve_current_page(browser: Any) -> Any:
    try:
        return _maybe_await(browser.get_current_page())
    except Exception:
        return None


def _read_history_final_page_url(history: Any) -> str:
    state = _read_history_final_state(history)
    token = str(getattr(state, "url", "") or "").strip()
    if token in {"", "about:blank"}:
        return ""
    return token


def _read_history_final_page_title(history: Any) -> str:
    state = _read_history_final_state(history)
    return str(getattr(state, "title", "") or "").strip()


def _copy_history_screenshot(*, history: Any, download_dir: Path) -> str:
    state = _read_history_final_state(history)
    source_path = Path(str(getattr(state, "screenshot_path", "") or "").strip())
    if not str(source_path):
        return ""
    if not source_path.exists() or not source_path.is_file():
        return ""
    target_path = download_dir / "terminal_screenshot.png"
    try:
        if source_path.resolve() != target_path.resolve():
            shutil.copy2(source_path, target_path)
        else:
            target_path = source_path
    except OSError:
        return str(source_path)
    return str(target_path)


def _read_history_final_state(history: Any) -> Any:
    entries = getattr(history, "history", None)
    if not isinstance(entries, list) or not entries:
        return None
    last_entry = entries[-1]
    return getattr(last_entry, "state", None)


def _read_history_attachment_paths(history: Any) -> list[str]:
    action_results = getattr(history, "action_results", None)
    if not callable(action_results):
        return []
    attachments: list[str] = []
    seen: set[str] = set()
    try:
        results = action_results()
    except Exception:
        return []
    if not isinstance(results, list):
        return []
    for result in results:
        for raw_path in getattr(result, "attachments", None) or []:
            token = str(raw_path or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            attachments.append(token)
    return attachments


def _read_page_url(page: Any) -> str:
    if page is None:
        return ""
    try:
        candidate = getattr(page, "url", "")
        if callable(candidate):
            candidate = _maybe_await(candidate())
    except Exception:
        return ""
    return str(candidate or "").strip()


def _read_browser_current_page_url(browser: Any) -> str:
    candidate = getattr(browser, "get_current_page_url", None)
    if not callable(candidate):
        return ""
    try:
        value = _maybe_await(candidate())
    except Exception:
        return ""
    token = str(value or "").strip()
    if token in {"about:blank", ""}:
        return ""
    return token


def _read_page_title(page: Any) -> str:
    if page is None:
        return ""
    for attribute in ("title", "get_title"):
        try:
            candidate = getattr(page, attribute, None)
        except Exception:
            continue
        if candidate is None:
            continue
        try:
            value = _maybe_await(candidate()) if callable(candidate) else candidate
        except Exception:
            continue
        token = str(value or "").strip()
        if token:
            return token
    return ""


def _read_browser_current_page_title(browser: Any) -> str:
    candidate = getattr(browser, "get_current_page_title", None)
    if not callable(candidate):
        return ""
    try:
        value = _maybe_await(candidate())
    except Exception:
        return ""
    token = str(value or "").strip()
    if token in {"Unknown page title", ""}:
        return ""
    return token


def _read_page_html(page: Any) -> str:
    if page is None:
        return ""
    for attribute in ("content", "get_content"):
        try:
            candidate = getattr(page, attribute, None)
        except Exception:
            continue
        if candidate is None:
            continue
        try:
            value = _maybe_await(candidate()) if callable(candidate) else candidate
        except Exception:
            continue
        token = str(value or "")
        if token.strip():
            return token
    evaluate = getattr(page, "evaluate", None)
    if callable(evaluate):
        try:
            value = _maybe_await(
                evaluate("() => document.documentElement?.outerHTML || ''")
            )
        except Exception:
            return ""
        token = str(value or "")
        if token.strip():
            return token
    return str(getattr(page, "html", "") or "")


def _write_terminal_html_snapshot(
    *,
    download_dir: Path,
    final_page_html: str,
) -> str:
    token = str(final_page_html or "")
    if not token.strip():
        return ""
    snapshot_path = download_dir / "terminal_snapshot.html"
    try:
        snapshot_path.write_text(token, encoding="utf-8")
    except OSError:
        return ""
    return str(snapshot_path)


def _write_terminal_screenshot(
    *,
    browser: Any,
    page: Any,
    download_dir: Path,
) -> str:
    screenshot_path = download_dir / "terminal_screenshot.png"
    if _try_screenshot_call(
        candidate=getattr(browser, "take_screenshot", None),
        screenshot_path=screenshot_path,
    ):
        return str(screenshot_path)
    if _try_screenshot_call(
        candidate=getattr(page, "screenshot", None) if page is not None else None,
        screenshot_path=screenshot_path,
    ):
        return str(screenshot_path)
    if _try_screenshot_call(
        candidate=getattr(page, "take_screenshot", None) if page is not None else None,
        screenshot_path=screenshot_path,
    ):
        return str(screenshot_path)
    return ""


def _try_screenshot_call(*, candidate: Any, screenshot_path: Path) -> bool:
    if not callable(candidate):
        return False
    try:
        result = candidate(path=str(screenshot_path), full_page=True)
        if inspect.isawaitable(result):
            _run_awaitable(result)
    except TypeError:
        try:
            result = candidate(str(screenshot_path))
            if inspect.isawaitable(result):
                _run_awaitable(result)
        except Exception:
            return False
    except Exception:
        return False
    return screenshot_path.exists()


def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return _await_in_current_or_thread(value)
    return value


def _await_in_current_or_thread(
    awaitable: Any,
    *,
    timeout_seconds: float | None = None,
) -> Any:
    payload: dict[str, Any] = {}
    errors: list[Exception] = []

    def runner() -> None:
        try:
            payload["result"] = asyncio.run(awaitable)
        except Exception as exc:  # pragma: no cover - defensive thread bridge
            errors.append(exc)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        if timeout_seconds is None:
            return asyncio.run(awaitable)
        thread = Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout_seconds)
        if thread.is_alive():
            raise TimeoutError("awaitable execution timed out")
        if errors:
            raise errors[0]
        return payload.get("result")

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if timeout_seconds is not None and thread.is_alive():
        raise TimeoutError("awaitable execution timed out")
    if errors:
        raise errors[0]
    return payload.get("result")


def _load_browser_use_runtime(normalized_url: str) -> Any:
    os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")
    try:
        return import_module("browser_use")
    except Exception as exc:
        raise AppError(
            code="browser_use_unavailable",
            message="The local browser_use runtime is not installed in this environment",
            cause=exc,
            retryable=False,
            context={"normalized_url": normalized_url},
        ) from exc


def _run_agent_history_with_timeout(
    *,
    agent: Any,
    browser: Any,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
) -> Any:
    payload: dict[str, Any] = {}
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            payload["history"] = agent.run_sync(max_steps=request.settings.max_steps)
        except BaseException as exc:  # pragma: no cover - defensive thread bridge
            errors.append(exc)

    worker = Thread(target=runner, daemon=True)
    worker.start()
    timeout_seconds = _resolve_agent_run_timeout_seconds(request)
    worker.join(timeout_seconds)
    if worker.is_alive():
        _signal_agent_stop(agent)
        _prepare_browser_for_shutdown(browser)
        worker.join(_TIMED_OUT_AGENT_STOP_GRACE_SECONDS)
        raise AppError(
            code="browser_download_agent_timeout",
            message="browser-use did not return within the configured execution budget",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "timeout_seconds": timeout_seconds,
                "max_steps": request.settings.max_steps,
            },
        )
    if errors:
        raise errors[0]
    history = payload.get("history")
    if history is None:
        raise AppError(
            code="browser_download_agent_missing_history",
            message="browser-use completed without returning agent history",
            retryable=True,
            context={"normalized_url": normalized_url},
        )
    return history


def _resolve_agent_run_timeout_seconds(
    request: BrowserReportDownloadRequest,
) -> float:
    buffer_seconds = min(
        _AGENT_RUN_TIMEOUT_MAX_BUFFER_SECONDS,
        max(
            _AGENT_RUN_TIMEOUT_MIN_BUFFER_SECONDS,
            float(request.settings.max_steps) * _AGENT_RUN_TIMEOUT_STEP_BUFFER_SECONDS,
        ),
    )
    return float(request.settings.timeout_seconds) + buffer_seconds


def _signal_agent_stop(agent: Any) -> None:
    _prime_agent_timing_fields(agent)
    stop_method = getattr(agent, "stop", None)
    if not callable(stop_method):
        return
    try:
        stop_method()
    except Exception:
        return


def _prime_agent_timing_fields(agent: Any) -> None:
    now = time.time()
    for attribute_name in ("_session_start_time", "_task_start_time"):
        if hasattr(agent, attribute_name):
            continue
        try:
            setattr(agent, attribute_name, now)
        except Exception:
            continue


def _prepare_browser_for_shutdown(browser: Any) -> None:
    try:
        setattr(browser, "_intentional_stop", True)
    except Exception:
        pass
    browser_profile = getattr(browser, "browser_profile", None)
    if browser_profile is not None:
        try:
            setattr(browser_profile, "cdp_url", None)
        except Exception:
            pass
    reconnect_task = getattr(browser, "_reconnect_task", None)
    if reconnect_task is not None:
        try:
            if not reconnect_task.done():
                reconnect_task.cancel()
            setattr(browser, "_reconnect_task", None)
        except Exception:
            pass
    try:
        setattr(browser, "_reconnecting", False)
    except Exception:
        pass
    reconnect_event = getattr(browser, "_reconnect_event", None)
    if reconnect_event is not None:
        try:
            reconnect_event.set()
        except Exception:
            pass


def _cleanup_browser_profile_dir(profile_dir: Path) -> None:
    try:
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)
    except OSError:
        return


def _new_managed_browser_profile_dir(download_dir: Path) -> Path:
    return download_dir / (
        f"{_BROWSER_PROFILE_DIR_PREFIX}-{os.getpid()}-{int(time.time() * 1000)}"
    )


def _cleanup_managed_browser_profile_dirs(
    *,
    download_dir: Path,
    active_profile_dir: Path | None = None,
) -> None:
    if not download_dir.exists() or not download_dir.is_dir():
        return
    for candidate in download_dir.glob(f"{_BROWSER_PROFILE_DIR_PREFIX}*"):
        if active_profile_dir is not None and candidate == active_profile_dir:
            continue
        _cleanup_browser_profile_dir(candidate)


def _cleanup_stale_browser_use_temp_dirs(
    *,
    ctx: RunContext,
    normalized_url: str,
) -> None:
    now = time.time()
    stale_dirs: list[Path] = []
    for path in _list_browser_use_temp_dirs():
        try:
            age_seconds = now - path.stat().st_mtime
        except OSError:
            continue
        if age_seconds < _STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS:
            continue
        stale_dirs.append(path)
    removed = _remove_browser_use_temp_dirs(stale_dirs)
    if removed:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_stale_temp_cleanup",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "removed_count": len(removed),
                    "removed_sample": removed[:_TEMP_CLEANUP_LOG_SAMPLE_LIMIT],
                },
            )
        )


def _cleanup_new_browser_use_temp_dirs(
    *,
    ctx: RunContext,
    normalized_url: str,
    preexisting_temp_dirs: set[str],
) -> None:
    new_dirs = [
        path
        for path in _list_browser_use_temp_dirs()
        if str(path) not in preexisting_temp_dirs
    ]
    removed = _remove_browser_use_temp_dirs(new_dirs)
    if removed:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_run_temp_cleanup",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "removed_count": len(removed),
                    "removed_sample": removed[:_TEMP_CLEANUP_LOG_SAMPLE_LIMIT],
                },
            )
        )


def _list_browser_use_temp_dirs() -> list[Path]:
    try:
        temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    except OSError:
        return []
    if not temp_root.exists() or not temp_root.is_dir():
        return []
    discovered: list[Path] = []
    seen: set[str] = set()
    for pattern in _BROWSER_USE_TEMP_DIR_PATTERNS:
        for candidate in temp_root.glob(pattern):
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if not resolved.is_dir() or resolved.parent != temp_root:
                continue
            marker = str(resolved)
            if marker in seen:
                continue
            seen.add(marker)
            discovered.append(resolved)
    return discovered


def _remove_browser_use_temp_dirs(paths: list[Path]) -> list[str]:
    removed: list[str] = []
    for path in paths:
        try:
            if path.exists():
                shutil.rmtree(path)
        except OSError:
            continue
        if not path.exists():
            removed.append(path.name)
    return removed


def _kill_browser(browser: Any, *, ctx: RunContext, normalized_url: str) -> None:
    if _force_stop_local_browser_process(
        browser,
        ctx=ctx,
        normalized_url=normalized_url,
    ):
        return
    try:
        kill_result = browser.kill()
        if inspect.isawaitable(kill_result):
            _run_awaitable(kill_result, timeout_seconds=_BROWSER_KILL_TIMEOUT_SECONDS)
        return
    except Exception as exc:
        reset_method = getattr(browser, "reset", None)
        if callable(reset_method):
            try:
                reset_result = reset_method()
                if inspect.isawaitable(reset_result):
                    _run_awaitable(
                        reset_result,
                        timeout_seconds=_BROWSER_RESET_TIMEOUT_SECONDS,
                    )
                return
            except Exception as exc:
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="browser_report_download_browser_kill_failed",
                        module=logger.name,
                        fields={
                            "normalized_url": normalized_url,
                            "error": str(exc),
                        },
                    )
                )
                return
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_browser_kill_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "error": str(exc),
                },
            )
        )


def _force_stop_local_browser_process(
    browser: Any,
    *,
    ctx: RunContext,
    normalized_url: str,
) -> bool:
    watchdog = getattr(browser, "_local_browser_watchdog", None)
    process = getattr(watchdog, "_subprocess", None) if watchdog is not None else None
    pid = getattr(process, "pid", None)
    if pid is None:
        return False
    try:
        root_process = psutil.Process(int(pid))
        process_tree = [*root_process.children(recursive=True), root_process]
        for candidate in reversed(process_tree):
            try:
                candidate.terminate()
            except psutil.Error:
                continue
        _, alive = psutil.wait_procs(
            process_tree,
            timeout=_BROWSER_KILL_TIMEOUT_SECONDS / 2.0,
        )
        for candidate in alive:
            try:
                candidate.kill()
            except psutil.Error:
                continue
        if alive:
            psutil.wait_procs(
                alive,
                timeout=_BROWSER_KILL_TIMEOUT_SECONDS / 2.0,
            )
        setattr(watchdog, "_subprocess", None)
        temp_dirs = list(getattr(watchdog, "_temp_dirs_to_cleanup", []) or [])
        for temp_dir in temp_dirs:
            try:
                shutil.rmtree(Path(temp_dir), ignore_errors=True)
            except OSError:
                continue
        setattr(watchdog, "_temp_dirs_to_cleanup", [])
        original_user_data_dir = getattr(watchdog, "_original_user_data_dir", None)
        browser_profile = getattr(browser, "browser_profile", None)
        if original_user_data_dir is not None and browser_profile is not None:
            try:
                setattr(browser_profile, "user_data_dir", original_user_data_dir)
            except Exception:
                pass
        setattr(watchdog, "_original_user_data_dir", None)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_browser_process_force_stopped",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "browser_pid": int(pid),
                    "terminated_process_count": len(process_tree),
                },
            )
        )
        return True
    except (psutil.Error, OSError, ValueError) as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_browser_process_force_stop_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "browser_pid": pid,
                    "error": str(exc),
                },
            )
        )
        return False


def _run_awaitable(awaitable: Any, *, timeout_seconds: float | None = None) -> None:
    _await_in_current_or_thread(awaitable, timeout_seconds=timeout_seconds)


def _is_no_space_error(exc: BaseException) -> bool:
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return True
    return "no space left on device" in str(exc).casefold()


def _is_browser_start_timeout_error(exc: BaseException) -> bool:
    token = str(exc).casefold()
    return "browserstartevent" in token and "timed out" in token
