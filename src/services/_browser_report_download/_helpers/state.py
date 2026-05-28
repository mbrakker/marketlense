"""Browser page state helpers for report-download automation.

This module owns deterministic page metadata, load-state waits, real-tab
diagnostics, browser/page readers, and shared bounded await/excerpt helpers.
It does not perform JavaScript inspection, coordinate interaction, or HTTP
acquisition.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from threading import Thread
from typing import Any

from src.contracts.browser_download import (
    BrowserHelperPageInfo,
    BrowserHelperRealTabResult,
    BrowserHelperWaitResult,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.cdp import call_browser_download_cdp
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.helpers")

__all__ = (
    "_HELPER_SCHEMA_VERSION",
    "_HTML_EXCERPT_CHARS",
    "_HELPER_AWAIT_TIMEOUT_SECONDS",
    "_INTERNAL_TARGET_URL_PREFIXES",
    "browser_helper_page_info",
    "browser_helper_wait_for_load",
    "browser_helper_ensure_real_tab",
    "_log_wait_result",
    "_find_real_tab_via_cdp",
    "_log_real_tab_result",
    "_first_non_empty",
    "_looks_like_browser_use_session",
    "_read_browser_url",
    "_read_browser_title",
    "_read_browser_html",
    "_read_browser_current_page_url",
    "_read_browser_current_page_title",
    "_read_page_url",
    "_read_page_title",
    "_read_page_html",
    "_is_real_tab_url",
    "_maybe_await",
    "_await_async",
    "_excerpt",
)


_HELPER_SCHEMA_VERSION = "1.0"


_HTML_EXCERPT_CHARS = 800


_HELPER_AWAIT_TIMEOUT_SECONDS = 8.0


_INTERNAL_TARGET_URL_PREFIXES = (
    "about:",
    "brave://",
    "chrome://",
    "chrome-error://",
    "chrome-extension://",
    "chrome-search://",
    "chrome-untrusted://",
    "devtools://",
    "edge://",
    "opera://",
    "vivaldi://",
)


def browser_helper_page_info(
    *,
    browser: Any,
    page: Any,
    ctx: RunContext,
    normalized_url: str,
) -> BrowserHelperPageInfo:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_page_info_start",
            module=logger.name,
            fields={"normalized_url": normalized_url},
        )
    )
    source_labels: list[str] = []
    url, url_source = _first_non_empty(
        (
            ("browser.url", _read_browser_url(browser)),
            ("browser.current_page_url", _read_browser_current_page_url(browser)),
            ("page.url", _read_page_url(page)),
        )
    )
    title, title_source = _first_non_empty(
        (
            ("browser.title", _read_browser_title(browser)),
            (
                "browser.current_page_title",
                _read_browser_current_page_title(browser),
            ),
            ("page.title", _read_page_title(page)),
        )
    )
    html, html_source = _first_non_empty(
        (
            ("browser.html", _read_browser_html(browser)),
            ("page.html", _read_page_html(page)),
        )
    )
    for source in (url_source, title_source, html_source):
        if source:
            source_labels.append(source)
    result = BrowserHelperPageInfo(
        schema_version=_HELPER_SCHEMA_VERSION,
        url=url,
        title=title,
        html_size=len(html),
        html=html,
        html_excerpt=_excerpt(html, _HTML_EXCERPT_CHARS),
        is_real_tab=_is_real_tab_url(url),
        source_labels=tuple(source_labels),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_page_info_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "url": result.url,
                "title": result.title,
                "html_size": result.html_size,
                "is_real_tab": result.is_real_tab,
                "source_labels": list(result.source_labels),
            },
        )
    )
    return result


def browser_helper_wait_for_load(
    *,
    browser: Any,
    page: Any,
    ctx: RunContext,
    normalized_url: str,
    state: str = "networkidle",
    timeout_seconds: float = 8.0,
    required: bool = False,
) -> BrowserHelperWaitResult:
    waited_for = str(state or "networkidle").strip() or "networkidle"
    started = time.monotonic()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_wait_for_load_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "state": waited_for,
                "timeout_seconds": timeout_seconds,
            },
        )
    )
    try:
        wait_for_load_state = (
            getattr(page, "wait_for_load_state", None) if page is not None else None
        )
        if callable(wait_for_load_state):
            try:
                value = wait_for_load_state(
                    waited_for,
                    timeout=int(timeout_seconds * 1000),
                )
            except TypeError:
                value = wait_for_load_state(waited_for)
            _maybe_await(value, timeout_seconds=timeout_seconds)
        else:
            wait = getattr(browser, "wait", None)
            if callable(wait):
                _maybe_await(wait(min(max(timeout_seconds, 0.0), 2.0)))
            elif _looks_like_browser_use_session(browser):
                time.sleep(min(max(timeout_seconds, 0.0), 2.0))
            else:
                raise RuntimeError(
                    "no browser or page load wait primitive is available"
                )
    except Exception as exc:
        elapsed = round(time.monotonic() - started, 3)
        if required:
            raise AppError(
                code="browser_helper_wait_for_load_failed",
                message="Browser helper wait_for_load failed",
                cause=exc,
                retryable=True,
                context={"normalized_url": normalized_url, "state": waited_for},
            ) from exc
        result = BrowserHelperWaitResult(
            schema_version=_HELPER_SCHEMA_VERSION,
            status="failed",
            waited_for=waited_for,
            elapsed_seconds=elapsed,
            error=str(exc),
        )
        _log_wait_result(ctx=ctx, normalized_url=normalized_url, result=result)
        return result
    result = BrowserHelperWaitResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="ok",
        waited_for=waited_for,
        elapsed_seconds=round(time.monotonic() - started, 3),
        error="",
    )
    _log_wait_result(ctx=ctx, normalized_url=normalized_url, result=result)
    return result


def browser_helper_ensure_real_tab(
    *,
    browser: Any,
    page: Any,
    ctx: RunContext,
    normalized_url: str,
    required: bool = False,
) -> BrowserHelperRealTabResult:
    page_info = browser_helper_page_info(
        browser=browser,
        page=page,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if page_info.is_real_tab:
        result = BrowserHelperRealTabResult(
            schema_version=_HELPER_SCHEMA_VERSION,
            status="ok",
            is_real_tab=True,
            url=page_info.url,
            title=page_info.title,
            target_id="",
            error="",
        )
        _log_real_tab_result(ctx=ctx, normalized_url=normalized_url, result=result)
        return result
    result = _find_real_tab_via_cdp(
        browser=browser,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if result.is_real_tab:
        _log_real_tab_result(ctx=ctx, normalized_url=normalized_url, result=result)
        return result
    if required:
        raise AppError(
            code="browser_helper_real_tab_unavailable",
            message="Browser helper could not find a user-facing browser tab",
            retryable=True,
            context={"normalized_url": normalized_url, "error": result.error},
        )
    _log_real_tab_result(ctx=ctx, normalized_url=normalized_url, result=result)
    return result


def _log_wait_result(
    *,
    ctx: RunContext,
    normalized_url: str,
    result: BrowserHelperWaitResult,
) -> None:
    event = (
        "browser_helper_wait_for_load_complete"
        if result.status == "ok"
        else "browser_helper_wait_for_load_failed"
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "status": result.status,
                "waited_for": result.waited_for,
                "elapsed_seconds": result.elapsed_seconds,
                "error": result.error,
            },
        )
    )


def _find_real_tab_via_cdp(
    *,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
) -> BrowserHelperRealTabResult:
    try:
        call_result = call_browser_download_cdp(
            browser=browser,
            method="Target.getTargets",
            params={},
            ctx=ctx,
            normalized_url=normalized_url,
            required=False,
        )
    except Exception as exc:
        return BrowserHelperRealTabResult(
            schema_version=_HELPER_SCHEMA_VERSION,
            status="failed",
            is_real_tab=False,
            url="",
            title="",
            target_id="",
            error=str(exc),
        )
    targets = call_result.result.get("targetInfos")
    if not isinstance(targets, list):
        targets = []
    for raw_target in reversed(targets):
        if not isinstance(raw_target, dict):
            continue
        target_type = str(raw_target.get("type") or "").strip()
        url = str(raw_target.get("url") or "").strip()
        if target_type != "page" or not _is_real_tab_url(url):
            continue
        return BrowserHelperRealTabResult(
            schema_version=_HELPER_SCHEMA_VERSION,
            status="ok",
            is_real_tab=True,
            url=url,
            title=str(raw_target.get("title") or "").strip(),
            target_id=str(raw_target.get("targetId") or "").strip(),
            error="",
        )
    return BrowserHelperRealTabResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="failed",
        is_real_tab=False,
        url="",
        title="",
        target_id="",
        error="no user-facing page target found",
    )


def _log_real_tab_result(
    *,
    ctx: RunContext,
    normalized_url: str,
    result: BrowserHelperRealTabResult,
) -> None:
    event = (
        "browser_helper_real_tab_complete"
        if result.status == "ok"
        else "browser_helper_real_tab_failed"
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event=event,
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "status": result.status,
                "is_real_tab": result.is_real_tab,
                "url": result.url,
                "title": result.title,
                "target_id": result.target_id,
                "error": result.error,
            },
        )
    )


def _first_non_empty(candidates: tuple[tuple[str, str], ...]) -> tuple[str, str]:
    for label, value in candidates:
        token = str(value or "")
        if token.strip():
            return token, label
    return "", ""


def _looks_like_browser_use_session(browser: Any) -> bool:
    return callable(getattr(browser, "navigate_to", None)) and callable(
        getattr(browser, "get_current_page", None)
    )


def _read_browser_url(browser: Any) -> str:
    token = str(getattr(browser, "url", "") or "").strip()
    return "" if token in {"", "about:blank"} else token


def _read_browser_title(browser: Any) -> str:
    return str(getattr(browser, "title", "") or "").strip()


def _read_browser_html(browser: Any) -> str:
    return str(getattr(browser, "html", "") or "")


def _read_browser_current_page_url(browser: Any) -> str:
    candidate = getattr(browser, "get_current_page_url", None)
    if not callable(candidate):
        return ""
    try:
        value = _maybe_await(candidate())
    except Exception:
        return ""
    token = str(value or "").strip()
    return "" if token in {"", "about:blank"} else token


def _read_browser_current_page_title(browser: Any) -> str:
    candidate = getattr(browser, "get_current_page_title", None)
    if not callable(candidate):
        return ""
    try:
        value = _maybe_await(candidate())
    except Exception:
        return ""
    token = str(value or "").strip()
    return "" if token in {"", "Unknown page title"} else token


def _read_page_url(page: Any) -> str:
    if page is None:
        return ""
    try:
        candidate = getattr(page, "url", "")
        if callable(candidate):
            candidate = _maybe_await(candidate())
    except Exception:
        return ""
    token = str(candidate or "").strip()
    return "" if token in {"", "about:blank"} else token


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


def _is_real_tab_url(url: str) -> bool:
    token = str(url or "").strip()
    if not token:
        return False
    return not any(token.startswith(prefix) for prefix in _INTERNAL_TARGET_URL_PREFIXES)


def _maybe_await(value: Any, *, timeout_seconds: float | None = None) -> Any:
    if not inspect.isawaitable(value):
        return value
    timeout = timeout_seconds or _HELPER_AWAIT_TIMEOUT_SECONDS
    payload: dict[str, Any] = {}
    errors: list[BaseException] = []

    async def awaitable() -> Any:
        return await value

    def runner() -> None:
        try:
            payload["result"] = asyncio.run(
                asyncio.wait_for(awaitable(), timeout=timeout)
            )
        except BaseException as exc:
            errors.append(exc)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(awaitable(), timeout=timeout))

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError("browser helper operation timed out")
    if errors:
        raise errors[0]
    return payload.get("result")


async def _await_async(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value


def _excerpt(value: str, max_chars: int) -> str:
    token = str(value or "").strip()
    if len(token) <= max_chars:
        return token
    return f"{token[: max_chars - 3]}..."
