"""Allowlisted raw-CDP helpers for the browser report-download service.

This module copies the small browser-harness `cdp(method, **params)` escape-hatch
shape into Marketlense-owned code, but keeps it constrained to terminal evidence
inspection. It is not a second browser automation route.

Approved CDP method allowlist:
- `Runtime.evaluate`: read bounded terminal state such as Performance entries.
- `Page.captureScreenshot`: persist terminal screenshots when browser-use hooks fail.
- `Target.getTargetInfo`: inspect the focused target during diagnostics.
- `Target.getTargets`: recover a real page target when browser-use sessions are unavailable.
- `Target.attachToTarget`: create a transient evidence-only CDP session.
- `Target.detachFromTarget`: clean up a transient evidence-only CDP session.
"""

from __future__ import annotations

import asyncio
import base64
import inspect
import logging
from concurrent.futures import TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from pathlib import Path
from threading import Thread
from typing import Any

from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.cdp")


_CDP_ALLOWLIST: dict[str, str] = {
    "Runtime.evaluate": "Read bounded terminal page state for evidence capture.",
    "Page.captureScreenshot": "Persist terminal screenshot evidence when browser-use screenshot hooks fail.",
    "Target.getTargetInfo": "Inspect focused target identity for diagnostics and logging.",
    "Target.getTargets": "Find a real page target when browser-use session state is unavailable.",
    "Target.attachToTarget": "Create a transient evidence-only CDP session for an allowlisted read.",
    "Target.detachFromTarget": "Clean up a transient evidence-only CDP session.",
}
_TARGET_LEVEL_METHODS = {
    "Target.getTargetInfo",
    "Target.getTargets",
    "Target.attachToTarget",
    "Target.detachFromTarget",
}
_INTERNAL_TARGET_URL_PREFIXES = (
    "about:",
    "chrome://",
    "chrome-extension://",
    "chrome-untrusted://",
    "devtools://",
)
_CDP_OPERATION_TIMEOUT_SECONDS = 8.0


@dataclass(frozen=True)
class BrowserDownloadCdpCallResult:
    schema_version: str = field(metadata={"doc": "CDP call-result schema version."})
    method: str = field(metadata={"doc": "Allowlisted Chrome DevTools Protocol method."})
    target_id: str = field(
        metadata={"doc": "Browser-use target ID used for this CDP call, else empty string."}
    )
    session_id: str = field(
        metadata={"doc": "Browser-use CDP session ID used for this CDP call, else empty string."}
    )
    status: str = field(metadata={"doc": "Call status: `ok` or `failed`."})
    result: dict[str, Any] = field(
        metadata={"doc": "Raw CDP result dictionary when the call succeeds, else empty dict."}
    )


@dataclass(frozen=True)
class _ResolvedCdpSession:
    client: Any = field(metadata={"doc": "CDP client used for the call."})
    target_id: str = field(metadata={"doc": "Resolved CDP target ID."})
    session_id: str = field(metadata={"doc": "Resolved CDP session ID."})
    transient: bool = field(
        metadata={"doc": "Whether this helper attached a temporary CDP session."}
    )


def get_browser_download_cdp_allowlist() -> dict[str, str]:
    return dict(_CDP_ALLOWLIST)


def call_browser_download_cdp(
    *,
    browser: Any,
    method: str,
    params: dict[str, Any] | None,
    ctx: RunContext,
    normalized_url: str,
    required: bool,
) -> BrowserDownloadCdpCallResult:
    normalized_method = str(method or "").strip()
    if normalized_method not in _CDP_ALLOWLIST:
        raise AppError(
            code="browser_download_cdp_method_not_allowed",
            message="The requested CDP method is not allowlisted for browser downloads",
            retryable=False,
            severity="error",
            context={
                "normalized_url": normalized_url,
                "method": normalized_method,
                "allowed_methods": sorted(_CDP_ALLOWLIST),
            },
        )
    safe_params = params if isinstance(params, dict) else {}
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_cdp_call_started",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "method": normalized_method,
                "allowlist_reason": _CDP_ALLOWLIST[normalized_method],
                "required": required,
            },
        )
    )
    target_id = ""
    session_id = ""
    try:
        raw_result, target_id, session_id = _send_browser_download_cdp(
            browser=browser,
            method=normalized_method,
            params=safe_params,
        )
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_cdp_call_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "method": normalized_method,
                    "target_id": target_id,
                    "session_id": session_id,
                    "required": required,
                    "error": str(exc),
                    "result_status": "failed",
                },
            )
        )
        if required:
            raise AppError(
                code="browser_download_cdp_call_failed",
                message="A required browser-download CDP call failed",
                cause=exc,
                retryable=True,
                severity="error",
                context={
                    "normalized_url": normalized_url,
                    "method": normalized_method,
                    "target_id": target_id,
                    "session_id": session_id,
                },
            ) from exc
        return BrowserDownloadCdpCallResult(
            schema_version="1.0",
            method=normalized_method,
            target_id=target_id,
            session_id=session_id,
            status="failed",
            result={},
        )
    result = raw_result if isinstance(raw_result, dict) else {}
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_cdp_call_completed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "method": normalized_method,
                "target_id": target_id,
                "session_id": session_id,
                "required": required,
                "result_status": "ok",
                "result_keys": sorted(str(key) for key in result.keys()),
            },
        )
    )
    return BrowserDownloadCdpCallResult(
        schema_version="1.0",
        method=normalized_method,
        target_id=target_id,
        session_id=session_id,
        status="ok",
        result=result,
    )


def collect_terminal_network_entries_via_cdp(
    *,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    required: bool = False,
) -> list[dict[str, Any]]:
    expression = """
    (() => {
      const build = (entry, initiatorFallback = 'other') => ({
        url: String(entry?.name || '').trim(),
        initiator_type: String(entry?.initiatorType || initiatorFallback || 'other').trim(),
      });
      const navigationEntries = (globalThis.performance?.getEntriesByType?.('navigation') || [])
        .map((entry) => build(entry, 'navigation'));
      const resourceEntries = (globalThis.performance?.getEntriesByType?.('resource') || [])
        .map((entry) => build(entry, 'other'));
      return [...navigationEntries, ...resourceEntries];
    })()
    """
    call_result = call_browser_download_cdp(
        browser=browser,
        method="Runtime.evaluate",
        params={"expression": expression, "returnByValue": True, "awaitPromise": True},
        ctx=ctx,
        normalized_url=normalized_url,
        required=required,
    )
    if call_result.status != "ok":
        return []
    runtime_value = _extract_runtime_value(
        result=call_result.result,
        ctx=ctx,
        normalized_url=normalized_url,
        required=required,
    )
    if not isinstance(runtime_value, list):
        return []
    return [item for item in runtime_value if isinstance(item, dict)]


def capture_terminal_screenshot_via_cdp(
    *,
    browser: Any,
    screenshot_path: Path,
    ctx: RunContext,
    normalized_url: str,
    required: bool = False,
) -> bool:
    call_result = call_browser_download_cdp(
        browser=browser,
        method="Page.captureScreenshot",
        params={"format": "png", "captureBeyondViewport": True},
        ctx=ctx,
        normalized_url=normalized_url,
        required=required,
    )
    if call_result.status != "ok":
        return False
    data = str(call_result.result.get("data") or "").strip()
    if not data:
        if required:
            raise AppError(
                code="browser_download_cdp_screenshot_missing",
                message="CDP screenshot capture returned no image data",
                retryable=True,
                severity="error",
                context={"normalized_url": normalized_url},
            )
        return False
    try:
        screenshot_path.parent.mkdir(parents=True, exist_ok=True)
        screenshot_path.write_bytes(base64.b64decode(data))
    except Exception as exc:
        if required:
            raise AppError(
                code="browser_download_cdp_screenshot_write_failed",
                message="CDP screenshot capture could not be written to disk",
                cause=exc,
                retryable=True,
                severity="error",
                context={"normalized_url": normalized_url, "screenshot_path": str(screenshot_path)},
            ) from exc
        return False
    return screenshot_path.exists()


def _send_browser_download_cdp(
    *,
    browser: Any,
    method: str,
    params: dict[str, Any],
) -> tuple[dict[str, Any], str, str]:
    if method in _TARGET_LEVEL_METHODS:
        client = _resolve_root_cdp_client(browser)
        result = _send_raw_cdp(client=client, method=method, params=params, session_id="")
        return result, "", ""
    resolved_session = _resolve_browser_cdp_session(browser)
    try:
        result = _send_raw_cdp(
            client=resolved_session.client,
            method=method,
            params=params,
            session_id=resolved_session.session_id,
        )
        return result, resolved_session.target_id, resolved_session.session_id
    finally:
        if resolved_session.transient:
            _detach_transient_cdp_session(
                client=resolved_session.client,
                session_id=resolved_session.session_id,
            )


def _resolve_browser_cdp_session(browser: Any) -> _ResolvedCdpSession:
    get_session = getattr(browser, "get_or_create_cdp_session", None)
    if not callable(get_session):
        return _attach_transient_cdp_session(browser)
    try:
        session = _await_with_timeout(get_session(target_id=None, focus=False))
    except TypeError:
        session = _await_with_timeout(get_session())
    except Exception:
        return _attach_transient_cdp_session(browser)
    client = getattr(session, "cdp_client", None)
    session_id = str(getattr(session, "session_id", "") or "")
    target_id = str(getattr(session, "target_id", "") or "")
    if client is None or not session_id:
        return _attach_transient_cdp_session(browser)
    return _ResolvedCdpSession(
        client=client,
        target_id=target_id,
        session_id=session_id,
        transient=False,
    )


def _attach_transient_cdp_session(browser: Any) -> _ResolvedCdpSession:
    client = _resolve_root_cdp_client(browser)
    targets_result = _send_raw_cdp(
        client=client,
        method="Target.getTargets",
        params={},
        session_id="",
    )
    target_id = _select_real_page_target_id(targets_result)
    if not target_id:
        raise RuntimeError("no real page target is available for CDP evidence capture")
    attach_result = _send_raw_cdp(
        client=client,
        method="Target.attachToTarget",
        params={"targetId": target_id, "flatten": True},
        session_id="",
    )
    session_id = str(attach_result.get("sessionId") or "").strip()
    if not session_id:
        raise RuntimeError("CDP target attach returned no session ID")
    return _ResolvedCdpSession(
        client=client,
        target_id=target_id,
        session_id=session_id,
        transient=True,
    )


def _detach_transient_cdp_session(*, client: Any, session_id: str) -> None:
    token = str(session_id or "").strip()
    if not token:
        return
    try:
        _send_raw_cdp(
            client=client,
            method="Target.detachFromTarget",
            params={"sessionId": token},
            session_id="",
        )
    except Exception:
        return


def _resolve_root_cdp_client(browser: Any) -> Any:
    try:
        client = getattr(browser, "cdp_client", None)
    except Exception as exc:
        raise RuntimeError("browser CDP client is unavailable") from exc
    if client is None:
        raise RuntimeError("browser CDP client is unavailable")
    return client


def _select_real_page_target_id(targets_result: dict[str, Any]) -> str:
    raw_targets = targets_result.get("targetInfos")
    if not isinstance(raw_targets, list):
        return ""
    candidates: list[str] = []
    for raw_target in raw_targets:
        if not isinstance(raw_target, dict):
            continue
        target_type = str(raw_target.get("type") or raw_target.get("target_type") or "").strip()
        if target_type != "page":
            continue
        url = str(raw_target.get("url") or "").strip()
        if any(url.startswith(prefix) for prefix in _INTERNAL_TARGET_URL_PREFIXES):
            continue
        target_id = str(raw_target.get("targetId") or raw_target.get("target_id") or "").strip()
        if target_id:
            candidates.append(target_id)
    return candidates[-1] if candidates else ""


def _send_raw_cdp(
    *,
    client: Any,
    method: str,
    params: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    send_raw = getattr(client, "send_raw", None)
    if callable(send_raw):
        result = _await_cdp_client_operation(
            client=client,
            value=send_raw(method, params, session_id=session_id or None),
        )
        return result if isinstance(result, dict) else {}
    send = getattr(client, "send", None)
    domain, command = method.split(".", 1)
    domain_sender = getattr(send, domain, None) if send is not None else None
    command_sender = getattr(domain_sender, command, None) if domain_sender is not None else None
    if not callable(command_sender):
        raise RuntimeError(f"CDP client cannot send {method}")
    kwargs: dict[str, Any] = {"params": params}
    if session_id:
        kwargs["session_id"] = session_id
    result = _await_cdp_client_operation(
        client=client,
        value=command_sender(**kwargs),
    )
    return result if isinstance(result, dict) else {}


def _extract_runtime_value(
    *,
    result: dict[str, Any],
    ctx: RunContext,
    normalized_url: str,
    required: bool,
) -> Any:
    if result.get("exceptionDetails"):
        description = str(result.get("exceptionDetails") or "").strip()
        if required:
            raise AppError(
                code="browser_download_cdp_runtime_exception",
                message="CDP Runtime.evaluate reported a JavaScript exception",
                retryable=False,
                severity="error",
                context={"normalized_url": normalized_url, "exception": description},
            )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_cdp_runtime_exception",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "result_status": "failed",
                    "error": description,
                },
            )
        )
        return None
    value_payload = result.get("result")
    if isinstance(value_payload, dict) and "value" in value_payload:
        return value_payload.get("value")
    if "value" in result:
        return result.get("value")
    return None


def _await_with_timeout(value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    payload: dict[str, Any] = {}
    errors: list[BaseException] = []

    async def awaitable() -> Any:
        return await value

    def runner() -> None:
        try:
            payload["result"] = asyncio.run(awaitable())
        except BaseException as exc:  # pragma: no cover - defensive thread bridge
            errors.append(exc)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(asyncio.wait_for(awaitable(), timeout=_CDP_OPERATION_TIMEOUT_SECONDS))

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join(_CDP_OPERATION_TIMEOUT_SECONDS)
    if thread.is_alive():
        raise TimeoutError("CDP operation timed out")
    if errors:
        raise errors[0]
    return payload.get("result")


def _await_cdp_client_operation(*, client: Any, value: Any) -> Any:
    if not inspect.isawaitable(value):
        return value
    handler_task = getattr(client, "_message_handler_task", None)
    client_loop = None
    if handler_task is not None:
        try:
            client_loop = handler_task.get_loop()
        except Exception:
            client_loop = None
    if client_loop is not None and client_loop.is_running():
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is not client_loop:
            future = asyncio.run_coroutine_threadsafe(value, client_loop)
            try:
                return future.result(timeout=_CDP_OPERATION_TIMEOUT_SECONDS)
            except FutureTimeoutError as exc:
                future.cancel()
                raise TimeoutError("CDP operation timed out") from exc
    return _await_with_timeout(value)
