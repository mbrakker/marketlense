"""Developer-only browser-use diagnostics adapted from browser-harness doctor flows.

This module is intentionally kept out of production acquisition paths. It checks
local browser-use setup, CDP reachability, real-tab focus, profile/download
paths, and one bounded stale-session cleanup for operators running local tools.
"""

from __future__ import annotations

import asyncio
import inspect
import logging
import sys
from contextlib import suppress
from dataclasses import asdict
from pathlib import Path
from threading import Thread
from typing import Any

from src.contracts.browser_download import (
    BrowserDeveloperDiagnosticCheck,
    BrowserDeveloperDiagnosticsRequest,
    BrowserDeveloperDiagnosticsResult,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.cdp import (
    select_browser_download_real_page_target_info,
)
from src.services._browser_report_download.session_reuse import (
    disabled_browser_session_reuse_decision,
    resolve_browser_session_reuse,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger(
    "market_lense.browser_report_download_service.dev_diagnostics"
)

_DIAGNOSTIC_SCHEMA_VERSION = "1.0"
_DETAIL_MAX_CHARS = 500
_DEFAULT_VERIFICATION_URL = "data:text/html,<title>Marketlense%20Browser%20Doctor</title><h1>Marketlense browser doctor</h1>"


def default_browser_doctor_verification_url() -> str:
    return _DEFAULT_VERIFICATION_URL


def run_browser_developer_diagnostics(
    request: BrowserDeveloperDiagnosticsRequest,
    ctx: RunContext,
    *,
    browser_session_class: Any | None = None,
) -> BrowserDeveloperDiagnosticsResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_developer_diagnostics_start",
            module=logger.name,
            fields=asdict(request),
        )
    )
    checks: list[BrowserDeveloperDiagnosticCheck] = []
    downloads_path = _resolve_directory(
        raw_path=request.downloads_path,
        check_name="downloads_path",
        label="Downloads path",
        checks=checks,
    )
    session_reuse_decision = disabled_browser_session_reuse_decision()
    if request.session_reuse_policy.enabled:
        session_reuse_decision = resolve_browser_session_reuse(
            policy=request.session_reuse_policy,
            default_base_dir=downloads_path.parent,
            normalized_url=_normalize_verification_url(request.verification_url),
            ctx=ctx,
        )
        checks.append(
            _check(
                name="session_reuse",
                status="ok" if session_reuse_decision.accepted else "failed",
                message=(
                    "Bounded developer browser session reuse was resolved."
                    if session_reuse_decision.accepted
                    else "Bounded developer browser session reuse was rejected."
                ),
                detail=(
                    f"mode={session_reuse_decision.mode} scope={session_reuse_decision.publisher_scope} "
                    f"reused={session_reuse_decision.profile_reused} reason={session_reuse_decision.rejection_reason}"
                ),
            )
        )
    profile_path = _resolve_directory(
        raw_path=(
            session_reuse_decision.profile_path
            if session_reuse_decision.accepted
            else request.profile_path
        ),
        check_name="profile_path",
        label="Profile path",
        checks=checks,
    )
    cleanup_attempted = False
    cleanup_status = "skipped"
    cdp_url = ""
    active_tab_url = ""
    active_tab_title = ""
    browser_use_connected = False
    cdp_available = False
    real_tab_available = False
    verification_tab_activated = False
    top_level_error = ""
    try:
        session_class = browser_session_class or _load_browser_session_class()
        session_kwargs: dict[str, Any] = {
            "headless": not bool(request.headed),
            "user_data_dir": profile_path,
            "downloads_path": downloads_path,
        }
        requested_cdp_url = str(request.cdp_url or "").strip()
        if requested_cdp_url:
            session_kwargs["cdp_url"] = requested_cdp_url
        if request.keep_browser_open:
            session_kwargs["keep_alive"] = True
        flow_result = _await_diagnostic(
            _run_browser_diagnostic_flow(
                session_class=session_class,
                session_kwargs=session_kwargs,
                request=request,
                ctx=ctx,
            ),
            timeout_seconds=_flow_timeout_seconds(float(request.timeout_seconds)),
        )
        cleanup_attempted = bool(flow_result["cleanup_attempted"])
        cleanup_status = str(flow_result["cleanup_status"])
        if cleanup_attempted:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_developer_diagnostics_stale_cleanup",
                    module=logger.name,
                    fields={
                        "attempted": cleanup_attempted,
                        "status": cleanup_status,
                    },
                )
            )
        checks.extend(flow_result["checks"])
        browser_use_connected = True
        cdp_url = str(flow_result["cdp_url"])
        cdp_available = bool(flow_result["cdp_available"])
        real_tab_available = bool(flow_result["real_tab_available"])
        verification_tab_activated = bool(flow_result["verification_tab_activated"])
        active_tab_url = str(flow_result["active_tab_url"])
        active_tab_title = str(flow_result["active_tab_title"])
    except Exception as exc:
        top_level_error = _excerpt(str(exc))
        checks.append(
            _check(
                name="diagnostic_runtime",
                status="failed",
                message="Browser developer diagnostic failed.",
                detail=top_level_error,
            )
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_developer_diagnostics_failed",
                module=logger.name,
                fields={"error": top_level_error},
            )
        )
    result = BrowserDeveloperDiagnosticsResult(
        schema_version=_DIAGNOSTIC_SCHEMA_VERSION,
        status=_overall_status(checks),
        profile_path=str(profile_path),
        downloads_path=str(downloads_path),
        cdp_url=cdp_url,
        active_tab_url=active_tab_url,
        active_tab_title=active_tab_title,
        browser_use_connected=browser_use_connected,
        cdp_available=cdp_available,
        real_tab_available=real_tab_available,
        cleanup_attempted=cleanup_attempted,
        cleanup_status=cleanup_status,
        verification_tab_activated=verification_tab_activated,
        keep_browser_open=bool(request.keep_browser_open),
        checks=tuple(checks),
        error=top_level_error,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_developer_diagnostics_complete",
            module=logger.name,
            fields=asdict(result),
        )
    )
    return result


def _resolve_directory(
    *,
    raw_path: str,
    check_name: str,
    label: str,
    checks: list[BrowserDeveloperDiagnosticCheck],
) -> Path:
    token = str(raw_path or "").strip()
    if not token:
        raise AppError(
            code="browser_developer_diagnostics_path_missing",
            message=f"{label} is required for browser developer diagnostics",
            retryable=False,
            context={"check_name": check_name},
        )
    path = Path(token).expanduser().resolve()
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe_path = path / ".marketlense-browser-doctor-write-test"
        probe_path.write_text("ok", encoding="utf-8")
        probe_path.unlink(missing_ok=True)
    except Exception as exc:
        checks.append(
            _check(
                name=check_name,
                status="failed",
                message=f"{label} is not writable.",
                detail=str(exc),
            )
        )
        raise AppError(
            code="browser_developer_diagnostics_path_unwritable",
            message=f"{label} is not writable",
            cause=exc,
            retryable=False,
            context={"path": str(path), "check_name": check_name},
        ) from exc
    checks.append(
        _check(
            name=check_name,
            status="ok",
            message=f"{label} exists and is writable.",
            detail=str(path),
        )
    )
    return path


def _attempt_stale_browser_cleanup(
    *,
    browser_session: Any,
    preserve_cdp_url: bool,
    timeout_seconds: float,
) -> str:
    try:
        reconnect_task = getattr(browser_session, "_reconnect_task", None)
        if reconnect_task is not None and hasattr(reconnect_task, "done"):
            if not reconnect_task.done():
                reconnect_task.cancel()
                try:
                    _await_diagnostic(reconnect_task, timeout_seconds=timeout_seconds)
                except (asyncio.CancelledError, TimeoutError):
                    pass
            setattr(browser_session, "_reconnect_task", None)
        if not preserve_cdp_url:
            browser_profile = getattr(browser_session, "browser_profile", None)
            profile_cdp_url = str(getattr(browser_profile, "cdp_url", "") or "").strip()
            if browser_profile is not None and profile_cdp_url:
                try:
                    setattr(browser_profile, "cdp_url", None)
                except Exception:
                    pass
        return "ok"
    except Exception as exc:
        return f"failed:{_excerpt(str(exc))}"


async def _run_browser_diagnostic_flow(
    *,
    session_class: Any,
    session_kwargs: dict[str, Any],
    request: BrowserDeveloperDiagnosticsRequest,
    ctx: RunContext,
) -> dict[str, Any]:
    del ctx
    timeout_seconds = float(request.timeout_seconds)
    browser_session = session_class(**session_kwargs)
    checks: list[BrowserDeveloperDiagnosticCheck] = []
    cleanup_attempted = False
    cleanup_status = "skipped"
    try:
        if request.cleanup_stale_once:
            cleanup_attempted = True
            cleanup_status = _attempt_stale_browser_cleanup(
                browser_session=browser_session,
                preserve_cdp_url=bool(str(request.cdp_url or "").strip()),
                timeout_seconds=timeout_seconds,
            )
            checks.append(
                _check(
                    name="stale_connection_cleanup",
                    status="ok" if cleanup_status == "ok" else "warning",
                    message="Attempted one bounded stale browser-use cleanup.",
                    detail=cleanup_status,
                )
            )
        await _await_async_operation(browser_session.start(), timeout_seconds=timeout_seconds)
        cdp_url = _read_cdp_url(browser_session)
        checks.append(
            _check(
                name="browser_use_connectivity",
                status="ok",
                message="browser-use session started successfully.",
                detail=cdp_url,
            )
        )
        verification_url = _normalize_verification_url(request.verification_url)
        client = getattr(browser_session, "cdp_client", None)
        if client is None:
            raise RuntimeError("browser-use CDP client is unavailable")
        created = await _send_raw_cdp_async(
            client=client,
            method="Target.createTarget",
            params={"url": verification_url},
            session_id="",
            timeout_seconds=timeout_seconds,
        )
        opened_target_id = str(created.get("targetId") or "").strip()
        if not opened_target_id:
            raise RuntimeError("CDP Target.createTarget returned no target ID")
        if request.activate_verification_tab:
            await _send_raw_cdp_async(
                client=client,
                method="Target.activateTarget",
                params={"targetId": opened_target_id},
                session_id="",
                timeout_seconds=timeout_seconds,
            )
        target_url = (
            verification_url
            if verification_url.startswith(("http://", "https://"))
            else ""
        )
        target_info = await _wait_for_real_target_info_async(
            client=client,
            target_url=target_url,
            timeout_seconds=timeout_seconds,
        )
        selected_target_id = str(target_info.get("targetId") or "").strip()
        active_tab_url = str(target_info.get("url") or "").strip()
        active_tab_title = str(target_info.get("title") or "").strip()
        viewport_width = 0
        viewport_height = 0
        attached = False
        if selected_target_id:
            viewport_width, viewport_height, attached = await _probe_target_viewport_async(
                browser_session=browser_session,
                client=client,
                target_id=selected_target_id,
                timeout_seconds=timeout_seconds,
            )
            if request.activate_verification_tab:
                await _send_raw_cdp_async(
                    client=client,
                    method="Target.activateTarget",
                    params={"targetId": selected_target_id},
                    session_id="",
                    timeout_seconds=timeout_seconds,
                )
                await _focus_browser_use_target_async(
                    browser_session=browser_session,
                    target_id=selected_target_id,
                    timeout_seconds=min(timeout_seconds, 5.0),
                )
        tab_ok = _is_user_facing_tab(active_tab_url)
        cdp_ok = bool(selected_target_id and viewport_width > 0 and viewport_height > 0)
        checks.append(
            _check(
                name="active_tab",
                status="ok" if tab_ok else "failed",
                message="CDP opened and inspected an active verification tab.",
                detail=(
                    f"opened_target={opened_target_id} title={active_tab_title} "
                    f"url={active_tab_url}"
                ),
            )
        )
        checks.append(
            _check(
                name="cdp_and_real_tab",
                status="ok" if cdp_ok else "failed",
                message=(
                    "CDP responded and a real page target was available."
                    if cdp_ok
                    else "CDP did not expose a usable real page target."
                ),
                detail=(
                    f"target={selected_target_id} activated={bool(request.activate_verification_tab and selected_target_id)} "
                    f"attached={attached} viewport={viewport_width}x{viewport_height}"
                ),
            )
        )
        return {
            "cleanup_attempted": cleanup_attempted,
            "cleanup_status": cleanup_status,
            "checks": checks,
            "cdp_url": cdp_url,
            "cdp_available": cdp_ok,
            "real_tab_available": bool(selected_target_id),
            "verification_tab_activated": bool(
                request.activate_verification_tab and selected_target_id
            ),
            "active_tab_url": active_tab_url,
            "active_tab_title": active_tab_title,
        }
    finally:
        if not request.keep_browser_open:
            await _kill_browser_session_async(
                browser_session=browser_session,
                timeout_seconds=timeout_seconds,
            )


async def _wait_for_real_target_info_async(
    *,
    client: Any,
    target_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = asyncio.get_running_loop().time() + max(0.1, timeout_seconds)
    last_targets: dict[str, Any] = {}
    while True:
        last_targets = await _send_raw_cdp_async(
            client=client,
            method="Target.getTargets",
            params={},
            session_id="",
            timeout_seconds=min(3.0, max(0.1, timeout_seconds)),
        )
        target = select_browser_download_real_page_target_info(
            last_targets,
            target_url=target_url,
            require_url_match=bool(target_url),
        )
        if target:
            return target
        if asyncio.get_running_loop().time() >= deadline:
            fallback = select_browser_download_real_page_target_info(last_targets)
            return fallback if not target_url else {}
        await asyncio.sleep(0.25)


async def _probe_target_viewport_async(
    *,
    browser_session: Any,
    client: Any,
    target_id: str,
    timeout_seconds: float,
) -> tuple[int, int, bool]:
    session_id = ""
    attached = False
    try:
        get_session = getattr(browser_session, "get_or_create_cdp_session", None)
        if callable(get_session):
            with suppress(Exception):
                session = await _await_async_operation(
                    get_session(target_id=target_id, focus=False),
                    timeout_seconds=min(timeout_seconds, 5.0),
                )
                session_id = str(getattr(session, "session_id", "") or "").strip()
        if not session_id:
            attached_result = await _send_raw_cdp_async(
                client=client,
                method="Target.attachToTarget",
                params={"targetId": target_id, "flatten": True},
                session_id="",
                timeout_seconds=timeout_seconds,
            )
            session_id = str(attached_result.get("sessionId") or "").strip()
            attached = bool(session_id)
        if not session_id:
            return 0, 0, attached
        metrics = await _send_raw_cdp_async(
            client=client,
            method="Page.getLayoutMetrics",
            params={},
            session_id=session_id,
            timeout_seconds=timeout_seconds,
        )
        return (*_read_viewport_size(metrics), attached)
    finally:
        if attached and session_id:
            with suppress(Exception):
                await _send_raw_cdp_async(
                    client=client,
                    method="Target.detachFromTarget",
                    params={"sessionId": session_id},
                    session_id="",
                    timeout_seconds=min(timeout_seconds, 5.0),
                )


async def _focus_browser_use_target_async(
    *,
    browser_session: Any,
    target_id: str,
    timeout_seconds: float,
) -> None:
    get_session = getattr(browser_session, "get_or_create_cdp_session", None)
    if not callable(get_session):
        return
    with suppress(Exception):
        await _await_async_operation(
            get_session(target_id=target_id, focus=True),
            timeout_seconds=timeout_seconds,
        )


async def _send_raw_cdp_async(
    *,
    client: Any,
    method: str,
    params: dict[str, Any],
    session_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    send_raw = getattr(client, "send_raw", None)
    if not callable(send_raw):
        raise RuntimeError(f"CDP client cannot send {method}")
    result = await _await_async_operation(
        send_raw(method, params, session_id=session_id or None),
        timeout_seconds=timeout_seconds,
    )
    return result if isinstance(result, dict) else {}


async def _await_async_operation(value: Any, *, timeout_seconds: float) -> Any:
    if not inspect.isawaitable(value):
        return value
    return await asyncio.wait_for(value, timeout=max(0.1, timeout_seconds))


async def _kill_browser_session_async(
    *,
    browser_session: Any,
    timeout_seconds: float,
) -> None:
    kill = getattr(browser_session, "kill", None)
    if not callable(kill):
        return
    with suppress(Exception):
        await _await_async_operation(kill(), timeout_seconds=timeout_seconds)


def _read_viewport_size(metrics: dict[str, Any]) -> tuple[int, int]:
    for container_key in (
        "visualViewport",
        "layoutViewport",
        "cssVisualViewport",
        "cssLayoutViewport",
    ):
        container = metrics.get(container_key)
        if not isinstance(container, dict):
            continue
        width = _coerce_dimension(container.get("clientWidth", container.get("width")))
        height = _coerce_dimension(
            container.get("clientHeight", container.get("height"))
        )
        if width > 0 and height > 0:
            return width, height
    return 0, 0


def _coerce_dimension(value: Any) -> int:
    try:
        parsed = int(float(str(value)))
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _flow_timeout_seconds(timeout_seconds: float) -> float:
    return max(float(timeout_seconds) * 5.0, float(timeout_seconds) + 30.0)


def _load_browser_session_class() -> Any:
    try:
        from browser_use.browser.session import BrowserSession

        return BrowserSession
    except ModuleNotFoundError:
        repo_root = Path(__file__).resolve().parents[3]
        vendored_root = repo_root / "tools" / "browser-use"
        if str(vendored_root) not in sys.path:
            sys.path.insert(0, str(vendored_root))
        from browser_use.browser.session import BrowserSession

        return BrowserSession


def _await_diagnostic(value: Any, *, timeout_seconds: float) -> Any:
    if not inspect.isawaitable(value):
        return value
    timeout = max(0.1, float(timeout_seconds or 0.1))
    payload: dict[str, Any] = {}
    errors: list[BaseException] = []

    async def awaitable() -> Any:
        return await asyncio.wait_for(value, timeout=timeout)

    def runner() -> None:
        try:
            payload["result"] = asyncio.run(awaitable())
        except BaseException as exc:  # pragma: no cover - defensive thread bridge
            errors.append(exc)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(awaitable())

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout)
    if thread.is_alive():
        raise TimeoutError("browser developer diagnostic operation timed out")
    if errors:
        raise errors[0]
    return payload.get("result")


def _read_cdp_url(browser_session: Any) -> str:
    for source in (
        browser_session,
        getattr(browser_session, "browser_profile", None),
    ):
        if source is None:
            continue
        token = str(getattr(source, "cdp_url", "") or "").strip()
        if token:
            return token
    return ""


def _normalize_verification_url(raw_url: str) -> str:
    token = str(raw_url or "").strip()
    return token or _DEFAULT_VERIFICATION_URL


def _is_user_facing_tab(raw_url: str) -> bool:
    token = str(raw_url or "").strip()
    return bool(token) and not token.startswith(("about:", "chrome:", "devtools:"))


def _overall_status(checks: list[BrowserDeveloperDiagnosticCheck]) -> str:
    if any(check.status == "failed" for check in checks):
        return "failed"
    if any(check.status == "warning" for check in checks):
        return "warning"
    return "ok"


def _check(
    *,
    name: str,
    status: str,
    message: str,
    detail: str = "",
) -> BrowserDeveloperDiagnosticCheck:
    return BrowserDeveloperDiagnosticCheck(
        schema_version=_DIAGNOSTIC_SCHEMA_VERSION,
        name=str(name or "").strip(),
        status=str(status or "").strip(),
        message=_excerpt(message),
        detail=_excerpt(detail),
    )


def _coerce_string(value: object) -> str:
    return str(value or "").strip()


def _excerpt(value: object) -> str:
    token = str(value or "").strip()
    if len(token) <= _DETAIL_MAX_CHARS:
        return token
    return token[: _DETAIL_MAX_CHARS - 3].rstrip() + "..."
