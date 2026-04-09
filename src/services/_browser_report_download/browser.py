from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import shutil
import time
from dataclasses import dataclass
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


@dataclass(frozen=True)
class BrowserAgentRunResult:
    schema_version: str
    raw_model_response: str
    final_page_url: str
    final_page_title: str
    final_page_html: str
    downloaded_files: list[str]
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
    browser: Any | None = None
    raw_model_response = ""
    final_page_url = ""
    final_page_title = ""
    final_page_html = ""
    downloaded_files: list[str] = []
    network_resource_urls: list[str] = []
    network_events: list[BrowserDownloadNetworkEvent] = []
    html_snapshot_path = ""
    screenshot_path = ""
    try:
        browser = browser_use.Browser(
            downloads_path=str(download_dir),
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
        history = agent.run_sync(max_steps=request.settings.max_steps)
        raw_model_response = str(history.final_result() or "").strip()
        history_final_page_url = _read_history_final_page_url(history)
        history_final_page_title = _read_history_final_page_title(history)
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
    except Exception as exc:
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
            _kill_browser(browser, ctx=ctx, normalized_url=normalized_url)
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
        network_resource_urls=network_resource_urls,
        network_events=network_events,
        html_snapshot_path=html_snapshot_path,
        screenshot_path=screenshot_path,
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


def _await_in_current_or_thread(awaitable: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable)

    payload: dict[str, Any] = {}
    errors: list[Exception] = []

    def runner() -> None:
        try:
            payload["result"] = asyncio.run(awaitable)
        except Exception as exc:  # pragma: no cover - defensive thread bridge
            errors.append(exc)

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
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


def _kill_browser(browser: Any, *, ctx: RunContext, normalized_url: str) -> None:
    try:
        kill_result = browser.kill()
        if inspect.isawaitable(kill_result):
            _run_awaitable(kill_result)
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


def _run_awaitable(awaitable: Any) -> None:
    _await_in_current_or_thread(awaitable)
