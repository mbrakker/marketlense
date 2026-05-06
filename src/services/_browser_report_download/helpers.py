"""Inspectable browser helper surface for browser report downloads.

This module owns the approved Marketlense helper surface adapted from the
browser-harness `page_info`, `capture_screenshot`, `js`, `wait_for_load`,
`ensure_real_tab`, and `http_get` patterns. It stays inside the existing
`browser_report_download_service` boundary, returns typed contracts, and does
not read prompts, choose routes, decide retries, or orchestrate workflows.

Approved helpers:
- `browser_helper_page_info`: bounded user-facing page URL/title/HTML metadata.
- `browser_helper_capture_screenshot`: screenshot-first evidence capture.
- `browser_helper_js`: bounded JavaScript inspection with typed failures.
- `browser_helper_wait_for_load`: one bounded load-state wait.
- `browser_helper_ensure_real_tab`: real-tab diagnostics excluding internals.
- `browser_helper_http_get`: bounded static HTTP fetch for inspection.
"""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
import time
from pathlib import Path
from threading import Thread
from typing import Any

from src.contracts.browser_download import (
    BrowserHelperHttpGetResult,
    BrowserHelperJsResult,
    BrowserHelperPageInfo,
    BrowserHelperRealTabResult,
    BrowserHelperScreenshot,
    BrowserHelperWaitResult,
)
from src.contracts.http_acquisition import (
    HttpAcquisitionRequest,
    HttpAcquisitionResponsePolicy,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.cdp import (
    call_browser_download_cdp,
    capture_terminal_screenshot_via_cdp,
)
from src.services._http_acquisition import execute_http_acquisition
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.helpers")

_HELPER_SCHEMA_VERSION = "1.0"
_HTML_EXCERPT_CHARS = 800
_JS_SNIPPET_CHARS = 240
_HELPER_AWAIT_TIMEOUT_SECONDS = 8.0
_INTERNAL_TARGET_URL_PREFIXES = (
    "about:",
    "chrome://",
    "chrome-extension://",
    "chrome-untrusted://",
    "devtools://",
)


def get_browser_helper_surface() -> dict[str, str]:
    return {
        "page_info": "Read bounded URL/title/HTML metadata from the active page.",
        "capture_screenshot": "Persist a screenshot through browser, page, or CDP hooks.",
        "js": "Run bounded JavaScript inspection and return structured values.",
        "wait_for_load": "Perform one explicit browser/page load-state wait.",
        "ensure_real_tab": "Diagnose a user-facing page tab and reject internal targets.",
        "http_get": "Fetch a static page through the shared bounded HTTP executor.",
    }


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


def browser_helper_capture_screenshot(
    *,
    browser: Any,
    page: Any,
    screenshot_path: Path,
    ctx: RunContext,
    normalized_url: str,
    required: bool = False,
) -> BrowserHelperScreenshot:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_screenshot_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "screenshot_path": str(screenshot_path),
                "required": required,
            },
        )
    )
    candidates = (
        ("browser", getattr(browser, "take_screenshot", None)),
        ("page", getattr(page, "screenshot", None) if page is not None else None),
        (
            "page_take_screenshot",
            getattr(page, "take_screenshot", None) if page is not None else None,
        ),
    )
    for source, candidate in candidates:
        if _try_screenshot_call(candidate=candidate, screenshot_path=screenshot_path):
            return _screenshot_result(
                ctx=ctx,
                normalized_url=normalized_url,
                screenshot_path=screenshot_path,
                source=source,
            )
    if capture_terminal_screenshot_via_cdp(
        browser=browser,
        screenshot_path=screenshot_path,
        ctx=ctx,
        normalized_url=normalized_url,
        required=False,
    ):
        return _screenshot_result(
            ctx=ctx,
            normalized_url=normalized_url,
            screenshot_path=screenshot_path,
            source="cdp",
        )
    if required:
        raise AppError(
            code="browser_helper_screenshot_failed",
            message="Browser helper could not capture a required screenshot",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "screenshot_path": str(screenshot_path),
            },
        )
    result = BrowserHelperScreenshot(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="failed",
        path="",
        source="",
        size_bytes=0,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_screenshot_failed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "screenshot_path": str(screenshot_path),
                "required": required,
            },
        )
    )
    return result


def browser_helper_js(
    *,
    page: Any,
    expression: str,
    ctx: RunContext,
    normalized_url: str,
    required: bool = False,
) -> BrowserHelperJsResult:
    snippet = _snippet(expression)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_js_start",
            module=logger.name,
            fields={"normalized_url": normalized_url, "snippet": snippet},
        )
    )
    evaluate = getattr(page, "evaluate", None) if page is not None else None
    if not callable(evaluate):
        return _js_failure(
            ctx=ctx,
            normalized_url=normalized_url,
            snippet=snippet,
            error="page.evaluate is unavailable",
            required=required,
        )
    try:
        result_value = _maybe_await(
            evaluate(_wrap_js_expression(expression)),
            timeout_seconds=_HELPER_AWAIT_TIMEOUT_SECONDS,
        )
        json.dumps(result_value, ensure_ascii=True)
    except Exception as exc:
        return _js_failure(
            ctx=ctx,
            normalized_url=normalized_url,
            snippet=snippet,
            error=str(exc),
            required=required,
        )
    result = BrowserHelperJsResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="ok",
        result=result_value,
        result_type=type(result_value).__name__,
        snippet=snippet,
        error="",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_js_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "snippet": snippet,
                "result_type": result.result_type,
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


def browser_helper_http_get(
    *,
    url: str,
    ctx: RunContext,
    normalized_url: str,
    timeout_seconds: float = 20.0,
    max_body_bytes: int = 262144,
) -> BrowserHelperHttpGetResult:
    token = str(url or "").strip()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_http_get_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "url": token,
                "timeout_seconds": timeout_seconds,
                "max_body_bytes": max_body_bytes,
            },
        )
    )
    try:
        response = execute_http_acquisition(
            request=HttpAcquisitionRequest(
                schema_version="1.0",
                purpose="browser_helper_http_get",
                method="GET",
                url=token,
                headers={
                    "User-Agent": "MarketlenseBrowserHelper/1.0",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                timeout_seconds=max(float(timeout_seconds), 1.0),
                response_policy=HttpAcquisitionResponsePolicy(
                    schema_version="1.0",
                    require_success_status=False,
                    capture_text=True,
                    capture_binary=False,
                    capture_content_type_markers=(),
                    max_body_bytes=max(int(max_body_bytes), 1),
                    truncate_body=True,
                ),
                error_code="browser_helper_http_get_failed",
                error_message="Browser helper HTTP GET failed",
                allow_redirects=True,
                context_fields={"normalized_url": normalized_url},
            ),
            ctx=ctx,
        )
    except AppError as exc:
        result = BrowserHelperHttpGetResult(
            schema_version="1.0",
            status="failed",
            request_url=token,
            final_url="",
            status_code=0,
            content_type="",
            body_size_bytes=0,
            body_excerpt="",
            body_truncated=False,
            error=exc.message,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_helper_http_get_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "url": token,
                    "error_code": exc.code,
                    "error": exc.message,
                },
            )
        )
        return result
    body = str(response.text_body or "")
    result = BrowserHelperHttpGetResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="ok",
        request_url=response.request_url,
        final_url=response.final_url,
        status_code=response.status_code,
        content_type=response.content_type,
        body_size_bytes=len(body.encode("utf-8")),
        body_excerpt=_excerpt(body, _HTML_EXCERPT_CHARS),
        body_truncated=response.body_truncated,
        error=None,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_http_get_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "url": result.request_url,
                "final_url": result.final_url,
                "status_code": result.status_code,
                "content_type": result.content_type,
                "body_size_bytes": result.body_size_bytes,
                "body_truncated": result.body_truncated,
            },
        )
    )
    return result


def _screenshot_result(
    *,
    ctx: RunContext,
    normalized_url: str,
    screenshot_path: Path,
    source: str,
) -> BrowserHelperScreenshot:
    result = BrowserHelperScreenshot(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="ok",
        path=str(screenshot_path),
        source=source,
        size_bytes=screenshot_path.stat().st_size if screenshot_path.exists() else 0,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_screenshot_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "path": result.path,
                "source": result.source,
                "size_bytes": result.size_bytes,
            },
        )
    )
    return result


def _try_screenshot_call(*, candidate: Any, screenshot_path: Path) -> bool:
    if not callable(candidate):
        return False
    screenshot_path.parent.mkdir(parents=True, exist_ok=True)
    call_shapes = (
        {"path": str(screenshot_path), "full_page": True},
        {"path": str(screenshot_path), "fullPage": True},
        {"path": str(screenshot_path)},
    )
    for kwargs in call_shapes:
        try:
            value = _maybe_await(candidate(**kwargs))
        except TypeError:
            continue
        except Exception:
            return False
        if screenshot_path.exists() and screenshot_path.stat().st_size > 0:
            return True
        if isinstance(value, bytes) and value:
            screenshot_path.write_bytes(value)
            return screenshot_path.exists() and screenshot_path.stat().st_size > 0
        if isinstance(value, str) and value.strip():
            screenshot_path.write_text(value, encoding="utf-8")
            return screenshot_path.exists() and screenshot_path.stat().st_size > 0
    try:
        value = _maybe_await(candidate(str(screenshot_path)))
    except Exception:
        return False
    if screenshot_path.exists() and screenshot_path.stat().st_size > 0:
        return True
    if isinstance(value, bytes) and value:
        screenshot_path.write_bytes(value)
        return screenshot_path.exists() and screenshot_path.stat().st_size > 0
    return False


def _js_failure(
    *,
    ctx: RunContext,
    normalized_url: str,
    snippet: str,
    error: str,
    required: bool,
) -> BrowserHelperJsResult:
    sanitized_error = _excerpt(error, _HTML_EXCERPT_CHARS)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_helper_js_failed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "snippet": snippet,
                "error": sanitized_error,
                "required": required,
            },
        )
    )
    if required:
        raise AppError(
            code="browser_helper_js_failed",
            message="Browser helper JavaScript evaluation failed",
            retryable=False,
            context={
                "normalized_url": normalized_url,
                "snippet": snippet,
                "error": sanitized_error,
            },
        )
    return BrowserHelperJsResult(
        schema_version=_HELPER_SCHEMA_VERSION,
        status="failed",
        result=None,
        result_type="NoneType",
        snippet=snippet,
        error=sanitized_error,
    )


def _wrap_js_expression(expression: str) -> str:
    token = str(expression or "").strip()
    if not token:
        return "() => null"
    if token.startswith("()") or token.startswith("async"):
        return token
    if re.search(r"\breturn\b", token):
        return f"async () => {{ {token} }}"
    return f"async () => ({token})"


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


def _snippet(expression: str) -> str:
    return _excerpt(
        re.sub(r"\s+", " ", str(expression or "")).strip(), _JS_SNIPPET_CHARS
    )


def _excerpt(value: str, max_chars: int) -> str:
    token = str(value or "").strip()
    if len(token) <= max_chars:
        return token
    return f"{token[: max_chars - 3]}..."
