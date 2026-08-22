"""Bounded deterministic rendered-terminal probe for access-layer report URLs.

This probe starts a raw browser-use Chromium session without an Agent. It only
reads the rendered page after navigation and returns evidence when the page body
matches the existing terminal not-found markers. Every other observation falls
through to the retained browser preflight and Agent stack unchanged.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import time
from pathlib import Path
from typing import Any

from src.contracts.browser_download import (
    BrowserPreflightProbeResponse,
    BrowserPreflightProbeResult,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download._browser_runtime.runtime import (
    load_browser_session_class,
)
from src.services._browser_report_download._http.config import (
    _TERMINAL_NOT_FOUND_BODY_MARKERS,
)
from src.services._browser_report_download.browser import (
    _STANDARD_BROWSER_USER_AGENT,
    _finalize_browser_launch,
    _reserve_browser_launch,
)
from src.services._browser_report_download.preflight import _run_coroutine_in_thread
from src.utils.logging import log_event

logger = logging.getLogger(
    "market_lense.browser_report_download_service.rendered_terminal_preflight"
)

_RENDERED_TERMINAL_PREFLIGHT_TIMEOUT_SECONDS = 16.0
_RENDERED_TERMINAL_NAVIGATION_TIMEOUT_SECONDS = 10.0
_RENDERED_TERMINAL_READ_TIMEOUT_SECONDS = 3.0
_RENDERED_TERMINAL_EVENT_DRAIN_SECONDS = 0.35


def try_rendered_terminal_preflight(
    *,
    request: Any,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    browser_session_class: Any | None = None,
) -> BrowserPreflightProbeResponse | None:
    """Return terminal evidence only for an observed rendered not-found page.

    The caller invokes this only after an HTTP access-layer response. A normal
    403, a browser error, or a page without the established marker returns None
    so existing Browser Use preflight remains the next route.
    """

    started = time.monotonic()
    target_url = str(execution_url or request.attempt_url or request.url).strip()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_rendered_terminal_preflight_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "execution_url": target_url,
                "timeout_seconds": _RENDERED_TERMINAL_PREFLIGHT_TIMEOUT_SECONDS,
            },
        )
    )
    launch_budget, launch_decision = _reserve_browser_launch(
        request=request,
        ctx=ctx,
        normalized_url=normalized_url,
        idempotency_suffix="rendered-terminal-preflight",
    )
    launch_started = False
    outcome = "completed"
    error_code = ""
    observation: dict[str, str] = {}
    try:
        runtime_class = browser_session_class or load_browser_session_class(
            normalized_url=normalized_url
        )
        observation = _run_coroutine_in_thread(
            _observe_rendered_page(
                browser_session_class=runtime_class,
                request=request,
                target_url=target_url,
            ),
            timeout_seconds=_RENDERED_TERMINAL_PREFLIGHT_TIMEOUT_SECONDS,
            grace_seconds=2.0,
        )
        if not bool(observation.get("started")):
            outcome = "failed"
            error_code = "rendered_terminal_preflight_start_failed"
            return None
        launch_started = True
        html = observation.get("html", "")
        if not _is_terminal_not_found_html(html):
            return None
        return BrowserPreflightProbeResponse(
            schema_version="1.0",
            probe=BrowserPreflightProbeResult(
                schema_version="1.0",
                status="terminal_static_archive",
                started_url=target_url,
                final_url=observation.get("final_url", "") or target_url,
                final_title=observation.get("final_title", ""),
                html_size=len(html),
                event_drain_seconds=_RENDERED_TERMINAL_EVENT_DRAIN_SECONDS,
                duration_seconds=round(time.monotonic() - started, 3),
                candidate_pdf_urls=[],
                selected_pdf_url="",
                observed_event_urls=[],
                network_event_count=0,
                evidence_labels=[
                    "rendered_terminal_preflight",
                    "preflight_terminal_not_found",
                ],
                escalation_reason="terminal_static_archive",
                avoided_agent_call=True,
                false_negative_rate_sample=0.0,
            ),
        )
    except Exception as exc:
        outcome = "failed"
        error_code = "rendered_terminal_preflight_failed"
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_rendered_terminal_preflight_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "phase": _failure_phase(exc),
                    "error_type": type(exc).__name__,
                    "duration_seconds": round(time.monotonic() - started, 3),
                },
            )
        )
        return None
    finally:
        _finalize_browser_launch(
            budget=launch_budget,
            decision=launch_decision,
            ctx=ctx,
            started=launch_started,
            outcome=outcome,
            error_code=error_code,
            runtime_seconds=max(0, int(time.monotonic() - started)),
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_rendered_terminal_preflight_complete",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "status": (
                        "terminal_static_archive"
                        if _is_terminal_not_found_html(observation.get("html", ""))
                        else "escalated"
                    ),
                    "final_url": observation.get("final_url", ""),
                    "html_size": len(observation.get("html", "")),
                    "duration_seconds": round(time.monotonic() - started, 3),
                    "browser_launch_recorded": launch_started,
                },
            )
        )


async def _observe_rendered_page(
    *,
    browser_session_class: Any,
    request: Any,
    target_url: str,
) -> dict[str, str | bool]:
    browser_session = _new_browser_session(
        browser_session_class=browser_session_class,
        request=request,
    )
    started = False
    try:
        await _await_with_timeout(
            browser_session.start(),
            timeout_seconds=_RENDERED_TERMINAL_NAVIGATION_TIMEOUT_SECONDS,
        )
        started = True
        await _await_with_timeout(
            browser_session.navigate_to(target_url),
            timeout_seconds=_RENDERED_TERMINAL_NAVIGATION_TIMEOUT_SECONDS,
        )
        await asyncio.sleep(_RENDERED_TERMINAL_EVENT_DRAIN_SECONDS)
        page = await _await_with_timeout(
            browser_session.get_current_page(),
            timeout_seconds=_RENDERED_TERMINAL_READ_TIMEOUT_SECONDS,
        )
        if page is None:
            return {"started": started, "final_url": "", "final_title": "", "html": ""}
        final_url = await _read_page_value(page, "get_url")
        final_title = await _read_page_value(page, "get_title")
        html = await _await_with_timeout(
            page.evaluate(
                "() => document.documentElement?.outerHTML || document.body?.innerHTML || ''"
            ),
            timeout_seconds=_RENDERED_TERMINAL_READ_TIMEOUT_SECONDS,
        )
        return {
            "started": started,
            "final_url": str(final_url or ""),
            "final_title": str(final_title or ""),
            "html": str(html or ""),
        }
    finally:
        await _stop_browser_session(browser_session)


def _new_browser_session(*, browser_session_class: Any, request: Any) -> Any:
    kwargs = {
        "headless": not bool(request.settings.headed),
        "downloads_path": str(Path(request.settings.output_dir)),
        "user_agent": _STANDARD_BROWSER_USER_AGENT,
    }
    return browser_session_class(**kwargs)


async def _read_page_value(page: Any, method_name: str) -> str:
    method = getattr(page, method_name, None)
    if not callable(method):
        return ""
    return str(
        await _await_with_timeout(
            method(), timeout_seconds=_RENDERED_TERMINAL_READ_TIMEOUT_SECONDS
        )
        or ""
    )


async def _stop_browser_session(browser_session: Any) -> None:
    kill = getattr(browser_session, "kill", None)
    if not callable(kill):
        return
    try:
        await _await_with_timeout(
            kill(), timeout_seconds=_RENDERED_TERMINAL_READ_TIMEOUT_SECONDS
        )
    except Exception:
        return


async def _await_with_timeout(value: Any, *, timeout_seconds: float) -> Any:
    if inspect.isawaitable(value):
        return await asyncio.wait_for(value, timeout=timeout_seconds)
    return value


def _is_terminal_not_found_html(html: str) -> bool:
    normalized_html = str(html or "").casefold()
    return any(marker in normalized_html for marker in _TERMINAL_NOT_FOUND_BODY_MARKERS)


def _failure_phase(exc: Exception) -> str:
    if isinstance(exc, TimeoutError):
        return "bounded_timeout"
    return "runtime"
