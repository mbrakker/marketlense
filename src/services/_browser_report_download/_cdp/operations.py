from __future__ import annotations

import base64
import asyncio
import inspect
import logging
from pathlib import Path
from typing import Any

from src.contracts.browser_download import BrowserDownloadDialogEvidence
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.cdp")

from .models import (
    _CDP_ALLOWLIST,
    _CDP_OPERATION_TIMEOUT_SECONDS,
    BrowserDownloadCdpCallResult,
    BrowserDownloadTargetHygieneResult,
)

from .transport import (
    _send_raw_cdp,
    _extract_runtime_value,
    _cdp_timeout_seconds,
)

from .session import (
    _send_browser_download_cdp,
    _resolve_browser_cdp_session_for_target_id,
    _detach_transient_cdp_session,
    _resolve_root_cdp_client,
    _select_real_page_target_id,
    _select_real_page_target_info,
    _read_target_viewport_size,
    _focus_browser_use_target,
)

from .dialogs import (
    _collect_terminal_dialog_evidence_via_cdp,
)


def get_browser_download_cdp_allowlist() -> dict[str, str]:
    return dict(_CDP_ALLOWLIST)


def select_browser_download_real_page_target_info(
    targets_result: dict[str, Any],
    *,
    target_url: str = "",
    require_url_match: bool = False,
) -> dict[str, Any]:
    target = _select_real_page_target_info(
        targets_result,
        target_url=target_url,
        require_url_match=require_url_match,
    )
    return dict(target) if target is not None else {}


def call_browser_download_cdp(
    *,
    browser: Any,
    method: str,
    params: dict[str, Any] | None,
    ctx: RunContext,
    normalized_url: str,
    required: bool,
    target_url: str = "",
    prefer_transient_session: bool = False,
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
                "target_url": str(target_url or "").strip(),
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
            timeout_seconds=_cdp_timeout_seconds(normalized_method),
            target_url=target_url,
            prefer_transient_session=prefer_transient_session,
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


def ensure_browser_download_target_hygiene_via_cdp(
    *,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    target_url: str = "",
    activate: bool = False,
    required: bool = False,
) -> BrowserDownloadTargetHygieneResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_target_hygiene_started",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "target_url": str(target_url or "").strip(),
                "activate": activate,
                "required": required,
            },
        )
    )
    try:
        result = _ensure_browser_download_target_hygiene_via_cdp(
            browser=browser,
            normalized_url=normalized_url,
            target_url=target_url,
            activate=activate,
        )
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_target_hygiene_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "target_url": str(target_url or "").strip(),
                    "activate": activate,
                    "error": str(exc),
                },
            )
        )
        if required:
            raise AppError(
                code="browser_download_target_hygiene_failed",
                message="Browser target hygiene could not resolve a usable page target",
                cause=exc,
                retryable=True,
                severity="error",
                context={
                    "normalized_url": normalized_url,
                    "target_url": str(target_url or "").strip(),
                },
            ) from exc
        result = BrowserDownloadTargetHygieneResult(
            schema_version="1.0",
            status="failed",
            selected_target_id="",
            selected_url="",
            selected_title="",
            reason=str(exc),
            activated=False,
            attached=False,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_target_hygiene_completed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "status": result.status,
                "selected_target_id": result.selected_target_id,
                "selected_url": result.selected_url,
                "selected_title": result.selected_title,
                "reason": result.reason,
                "activated": result.activated,
                "attached": result.attached,
                "viewport_width": result.viewport_width,
                "viewport_height": result.viewport_height,
            },
        )
    )
    return result


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
                context={
                    "normalized_url": normalized_url,
                    "screenshot_path": str(screenshot_path),
                },
            ) from exc
        return False
    return screenshot_path.exists()


def collect_terminal_dialog_evidence_via_cdp(
    *,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    allow_beforeunload: bool = False,
    target_url: str = "",
    required: bool = False,
) -> list[BrowserDownloadDialogEvidence]:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_dialog_drain_started",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "allow_beforeunload": allow_beforeunload,
                "target_url": str(target_url or "").strip(),
            },
        )
    )
    try:
        evidence = _collect_terminal_dialog_evidence_via_cdp(
            browser=browser,
            normalized_url=normalized_url,
            allow_beforeunload=allow_beforeunload,
            target_url=target_url,
        )
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_dialog_drain_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "allow_beforeunload": allow_beforeunload,
                    "target_url": str(target_url or "").strip(),
                    "error": str(exc),
                },
            )
        )
        if required:
            raise AppError(
                code="browser_download_dialog_drain_failed",
                message="Browser terminal dialog drain failed",
                cause=exc,
                retryable=True,
                severity="error",
                context={
                    "normalized_url": normalized_url,
                    "target_url": str(target_url or "").strip(),
                },
            ) from exc
        return []
    for item in evidence:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_dialog_evidence",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "dialog_type": item.dialog_type,
                    "message": item.message,
                    "page_url": item.page_url,
                    "action_taken": item.action_taken,
                    "validation_status": item.validation_status,
                    "target_id": item.target_id,
                    "session_id": item.session_id,
                },
            )
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_dialog_drain_completed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "dialog_evidence_count": len(evidence),
                "allow_beforeunload": allow_beforeunload,
            },
        )
    )
    return evidence


def capture_print_pdf_via_cdp(
    *,
    browser: Any,
    pdf_path: Path,
    ctx: RunContext,
    normalized_url: str,
    required: bool = False,
    target_url: str = "",
    prefer_transient_session: bool = False,
) -> bool:
    call_result = call_browser_download_cdp(
        browser=browser,
        method="Page.printToPDF",
        params={
            "printBackground": True,
            "preferCSSPageSize": True,
            "displayHeaderFooter": False,
        },
        ctx=ctx,
        normalized_url=normalized_url,
        required=required,
        target_url=target_url,
        prefer_transient_session=prefer_transient_session,
    )
    if call_result.status != "ok":
        return False
    return _write_print_pdf_capture(
        result=call_result.result,
        pdf_path=pdf_path,
        ctx=ctx,
        normalized_url=normalized_url,
        required=required,
    )


async def capture_print_pdf_via_cdp_async(
    *,
    browser: Any,
    pdf_path: Path,
    ctx: RunContext,
    normalized_url: str,
    target_url: str,
) -> bool:
    """Capture a rendered PDF on Browser Use's already-running event loop."""

    target_id = ""
    session_id = ""
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_cdp_call_started",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "method": "Page.printToPDF",
                "allowlist_reason": _CDP_ALLOWLIST["Page.printToPDF"],
                "required": False,
                "target_url": target_url,
            },
        )
    )
    client = _resolve_root_cdp_client(browser)
    try:
        targets = await _send_raw_cdp_async(
            client=client,
            method="Target.getTargets",
            params={},
            session_id="",
        )
        target_id = _select_real_page_target_id(
            targets,
            target_url=target_url,
            require_url_match=True,
        )
        if not target_id:
            raise RuntimeError(
                "no real page target matched the requested CDP target URL"
            )
        attached = await _send_raw_cdp_async(
            client=client,
            method="Target.attachToTarget",
            params={"targetId": target_id, "flatten": True},
            session_id="",
        )
        session_id = str(attached.get("sessionId") or "").strip()
        if not session_id:
            raise RuntimeError("CDP target attach returned no session ID")
        result = await _send_raw_cdp_async(
            client=client,
            method="Page.printToPDF",
            params={
                "printBackground": True,
                "preferCSSPageSize": True,
                "displayHeaderFooter": False,
            },
            session_id=session_id,
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
                    "method": "Page.printToPDF",
                    "target_id": target_id,
                    "session_id": session_id,
                    "required": False,
                    "error": str(exc),
                    "result_status": "failed",
                },
            )
        )
        return False
    finally:
        if session_id:
            try:
                await _send_raw_cdp_async(
                    client=client,
                    method="Target.detachFromTarget",
                    params={"sessionId": session_id},
                    session_id="",
                )
            except Exception:
                pass
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_cdp_call_completed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "method": "Page.printToPDF",
                "target_id": target_id,
                "session_id": session_id,
                "required": False,
                "result_status": "ok",
                "result_keys": sorted(str(key) for key in result.keys()),
            },
        )
    )
    return _write_print_pdf_capture(
        result=result,
        pdf_path=pdf_path,
        ctx=ctx,
        normalized_url=normalized_url,
        required=False,
    )


async def wait_for_browser_download_target_async(
    *,
    browser: Any,
    target_url: str,
    timeout_seconds: float,
) -> bool:
    """Wait only for a known public page target before a deterministic action."""

    deadline = asyncio.get_running_loop().time() + max(0.01, timeout_seconds)
    while True:
        try:
            client = _resolve_root_cdp_client(browser)
            targets = await _send_raw_cdp_async(
                client=client,
                method="Target.getTargets",
                params={},
                session_id="",
            )
            if _select_real_page_target_id(
                targets,
                target_url=target_url,
                require_url_match=True,
            ):
                return True
        except Exception:
            pass
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.5)


async def open_browser_download_target_async(
    *,
    browser: Any,
    target_url: str,
    timeout_seconds: float,
) -> bool:
    """Open and wait for an exact public target without Browser Use page state."""

    deadline = asyncio.get_running_loop().time() + max(0.01, timeout_seconds)
    opened = False
    while True:
        try:
            client = _resolve_root_cdp_client(browser)
            if not opened:
                await _send_raw_cdp_async(
                    client=client,
                    method="Target.createTarget",
                    params={"url": target_url},
                    session_id="",
                )
                opened = True
            targets = await _send_raw_cdp_async(
                client=client,
                method="Target.getTargets",
                params={},
                session_id="",
            )
            if _select_real_page_target_id(
                targets,
                target_url=target_url,
                require_url_match=True,
            ):
                return True
        except Exception:
            pass
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(0.5)


async def wait_for_browser_document_text_async(
    *,
    browser: Any,
    target_url: str,
    expected_text: str,
    timeout_seconds: float,
) -> bool:
    """Wait for the selected public page to expose its playbook postcondition."""

    expected = expected_text.strip().casefold()
    if not expected:
        return False
    deadline = asyncio.get_running_loop().time() + max(0.01, timeout_seconds)
    client: Any = None
    session_id = ""
    try:
        while True:
            try:
                client = _resolve_root_cdp_client(browser)
                targets = await _send_raw_cdp_async(
                    client=client,
                    method="Target.getTargets",
                    params={},
                    session_id="",
                )
                target_id = _select_real_page_target_id(
                    targets,
                    target_url=target_url,
                    require_url_match=True,
                )
                if target_id and not session_id:
                    attached = await _send_raw_cdp_async(
                        client=client,
                        method="Target.attachToTarget",
                        params={"targetId": target_id, "flatten": True},
                        session_id="",
                    )
                    session_id = str(attached.get("sessionId") or "").strip()
                if session_id:
                    response = await _send_raw_cdp_async(
                        client=client,
                        method="Runtime.evaluate",
                        params={
                            "expression": (
                                "(() => ({readyState: document.readyState, "
                                "title: document.title || '', bodyText: "
                                "(document.body?.innerText || '').slice(0, 12000)}))()"
                            ),
                            "returnByValue": True,
                        },
                        session_id=session_id,
                    )
                    value = response.get("result", {}).get("value", {})
                    if isinstance(value, dict):
                        content = " ".join(
                            str(value.get(field) or "")
                            for field in ("title", "bodyText")
                        ).casefold()
                        ready_state = str(value.get("readyState") or "").casefold()
                        if (
                            ready_state in {"interactive", "complete"}
                            and expected in content
                        ):
                            return True
            except Exception:
                pass
            if asyncio.get_running_loop().time() >= deadline:
                return False
            await asyncio.sleep(0.5)
    finally:
        if session_id and client is not None:
            try:
                await _send_raw_cdp_async(
                    client=client,
                    method="Target.detachFromTarget",
                    params={"sessionId": session_id},
                    session_id="",
                )
            except Exception:
                pass


async def _send_raw_cdp_async(
    *,
    client: Any,
    method: str,
    params: dict[str, Any],
    session_id: str,
) -> dict[str, Any]:
    send_raw = getattr(client, "send_raw", None)
    if not callable(send_raw):
        raise RuntimeError(f"CDP client cannot send {method}")
    result = send_raw(method, params, session_id=session_id or None)
    if inspect.isawaitable(result):
        result = await result
    return result if isinstance(result, dict) else {}


def _write_print_pdf_capture(
    *,
    result: dict[str, Any],
    pdf_path: Path,
    ctx: RunContext,
    normalized_url: str,
    required: bool,
) -> bool:
    data = str(result.get("data") or "").strip()
    if not data:
        if required:
            raise AppError(
                code="browser_download_cdp_print_pdf_missing",
                message="CDP print-to-PDF returned no PDF data",
                retryable=True,
                severity="error",
                context={"normalized_url": normalized_url},
            )
        return False
    try:
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(base64.b64decode(data))
    except Exception as exc:
        if required:
            raise AppError(
                code="browser_download_cdp_print_pdf_write_failed",
                message="CDP print-to-PDF output could not be written to disk",
                cause=exc,
                retryable=True,
                severity="error",
                context={"normalized_url": normalized_url, "pdf_path": str(pdf_path)},
            ) from exc
        return False
    if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
        return False
    if not pdf_path.read_bytes().startswith(b"%PDF"):
        pdf_path.unlink(missing_ok=True)
        if required:
            raise AppError(
                code="browser_download_cdp_print_pdf_invalid",
                message="CDP print-to-PDF output was not a PDF artifact",
                retryable=True,
                severity="error",
                context={"normalized_url": normalized_url, "pdf_path": str(pdf_path)},
            )
        return False
    return True


def _ensure_browser_download_target_hygiene_via_cdp(
    *,
    browser: Any,
    normalized_url: str,
    target_url: str,
    activate: bool,
) -> BrowserDownloadTargetHygieneResult:
    client = _resolve_root_cdp_client(browser)
    targets_result = _send_raw_cdp(
        client=client,
        method="Target.getTargets",
        params={},
        session_id="",
        timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
    )
    selected_target = _select_real_page_target_info(
        targets_result,
        target_url=target_url,
        require_url_match=bool(str(target_url or "").strip()),
    )
    if selected_target is None:
        return BrowserDownloadTargetHygieneResult(
            schema_version="1.0",
            status="rejected",
            selected_target_id="",
            selected_url="",
            selected_title="",
            reason="no user-facing page target matched target hygiene policy",
            activated=False,
            attached=False,
        )
    target_id = str(
        selected_target.get("targetId") or selected_target.get("target_id") or ""
    ).strip()
    selected_url = str(selected_target.get("url") or "").strip()
    selected_title = str(selected_target.get("title") or "").strip()
    resolved_session = _resolve_browser_cdp_session_for_target_id(
        browser=browser,
        target_id=target_id,
        timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
    )
    viewport_width, viewport_height, viewport_status = _read_target_viewport_size(
        client=resolved_session.client,
        session_id=resolved_session.session_id,
    )
    activated = False
    previous_focus_target_id = str(
        getattr(browser, "agent_focus_target_id", "") or ""
    ).strip()
    if viewport_status == "zero_size":
        if resolved_session.transient:
            _detach_transient_cdp_session(
                client=resolved_session.client,
                session_id=resolved_session.session_id,
            )
        return BrowserDownloadTargetHygieneResult(
            schema_version="1.0",
            status="rejected",
            selected_target_id=target_id,
            selected_url=selected_url,
            selected_title=selected_title,
            reason="selected page target has zero-size viewport",
            activated=False,
            attached=True,
            viewport_width=viewport_width,
            viewport_height=viewport_height,
        )
    try:
        if activate:
            _send_raw_cdp(
                client=client,
                method="Target.activateTarget",
                params={"targetId": target_id},
                session_id="",
                timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
            )
            activated = True
            _focus_browser_use_target(browser=browser, target_id=target_id)
    finally:
        if resolved_session.transient:
            _detach_transient_cdp_session(
                client=resolved_session.client,
                session_id=resolved_session.session_id,
            )
    status = (
        "reattached"
        if previous_focus_target_id and previous_focus_target_id != target_id
        else "ok"
    )
    reason = (
        "selected user-facing target differs from previous browser-use focus"
        if status == "reattached"
        else f"selected user-facing target with viewport status {viewport_status}"
    )
    return BrowserDownloadTargetHygieneResult(
        schema_version="1.0",
        status=status,
        selected_target_id=target_id,
        selected_url=selected_url,
        selected_title=selected_title,
        reason=reason,
        activated=activated,
        attached=True,
        viewport_width=viewport_width,
        viewport_height=viewport_height,
    )
