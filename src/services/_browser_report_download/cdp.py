"""Allowlisted raw-CDP helpers for the browser report-download service.

This module copies the small browser-harness `cdp(method, **params)` escape-hatch
shape into Marketlense-owned code, but keeps it constrained to terminal evidence
inspection. It is not a second browser automation route.

Approved CDP method allowlist:
- `Runtime.evaluate`: read bounded terminal state such as Performance entries.
- `Page.enable`: subscribe to bounded terminal Page events such as JavaScript dialogs.
- `Page.captureScreenshot`: persist terminal screenshots when browser-use hooks fail.
- `Page.printToPDF`: persist browser-rendered PDF captures for printable on-site reports.
- `Page.getLayoutMetrics`: reject zero-size or stale terminal targets before evidence capture.
- `Page.handleJavaScriptDialog`: unblock terminal JavaScript dialogs according to policy.
- `Target.getTargetInfo`: inspect the focused target during diagnostics.
- `Target.getTargets`: recover a real page target when browser-use sessions are unavailable.
- `Target.attachToTarget`: create a transient evidence-only CDP session.
- `Target.detachFromTarget`: clean up a transient evidence-only CDP session.
- `Target.activateTarget`: focus a verified user-facing target when headed evidence needs it.
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

from src.contracts.browser_download import BrowserDownloadDialogEvidence
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service.cdp")


_CDP_ALLOWLIST: dict[str, str] = {
    "Runtime.evaluate": "Read bounded terminal page state for evidence capture.",
    "Page.enable": "Subscribe to bounded terminal Page events such as JavaScript dialogs.",
    "Page.captureScreenshot": "Persist terminal screenshot evidence when browser-use screenshot hooks fail.",
    "Page.printToPDF": "Persist browser-rendered PDF captures for printable on-site reports.",
    "Page.getLayoutMetrics": "Reject zero-size or stale terminal targets before evidence capture.",
    "Page.handleJavaScriptDialog": "Handle terminal JavaScript dialogs according to browser-download policy.",
    "Target.getTargetInfo": "Inspect focused target identity for diagnostics and logging.",
    "Target.getTargets": "Find a real page target when browser-use session state is unavailable.",
    "Target.attachToTarget": "Create a transient evidence-only CDP session for an allowlisted read.",
    "Target.detachFromTarget": "Clean up a transient evidence-only CDP session.",
    "Target.activateTarget": "Focus a verified user-facing target when headed evidence needs it.",
}
_TARGET_LEVEL_METHODS = {
    "Target.getTargetInfo",
    "Target.getTargets",
    "Target.attachToTarget",
    "Target.detachFromTarget",
    "Target.activateTarget",
}
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
_CDP_OPERATION_TIMEOUT_SECONDS = 8.0
_CDP_PRINT_TO_PDF_TIMEOUT_SECONDS = 30.0
_CDP_DIALOG_DRAIN_SECONDS = 0.75
_CDP_DIALOG_MESSAGE_MAX_CHARS = 300


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
class BrowserDownloadTargetHygieneResult:
    schema_version: str = field(
        metadata={"doc": "Browser target-hygiene result schema version."}
    )
    status: str = field(
        metadata={
            "doc": "Target hygiene status: `ok`, `reattached`, `rejected`, or `failed`."
        }
    )
    selected_target_id: str = field(
        metadata={"doc": "Selected user-facing CDP target ID, else empty string."}
    )
    selected_url: str = field(
        metadata={"doc": "Selected target URL, else empty string."}
    )
    selected_title: str = field(
        metadata={"doc": "Selected target title, else empty string."}
    )
    reason: str = field(
        metadata={"doc": "Short diagnostic explaining the target hygiene decision."}
    )
    activated: bool = field(
        metadata={"doc": "Whether the helper explicitly activated the selected target."}
    )
    attached: bool = field(
        metadata={"doc": "Whether the selected target had or received a CDP session."}
    )
    viewport_width: int = field(
        default=0,
        metadata={"doc": "Observed target viewport width, or 0 when unavailable."},
    )
    viewport_height: int = field(
        default=0,
        metadata={"doc": "Observed target viewport height, or 0 when unavailable."},
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
    target_url: str = "",
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
                context={"normalized_url": normalized_url, "screenshot_path": str(screenshot_path)},
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
    )
    if call_result.status != "ok":
        return False
    data = str(call_result.result.get("data") or "").strip()
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


def _collect_terminal_dialog_evidence_via_cdp(
    *,
    browser: Any,
    normalized_url: str,
    allow_beforeunload: bool,
    target_url: str,
) -> list[BrowserDownloadDialogEvidence]:
    resolved_session = _resolve_browser_cdp_session(
        browser,
        timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
        target_url=target_url,
    )
    evidence: list[BrowserDownloadDialogEvidence] = []
    client = resolved_session.client

    async def on_dialog_opening(params: Any, event_session_id: str | None = None) -> None:
        session_id = str(event_session_id or resolved_session.session_id or "").strip()
        if session_id and session_id != resolved_session.session_id:
            return
        event = params if isinstance(params, dict) else {}
        action_taken, validation_status, accept = _dialog_policy_action(
            event.get("type"),
            allow_beforeunload=allow_beforeunload,
        )
        handle_status = validation_status
        try:
            await client.send_raw(
                "Page.handleJavaScriptDialog",
                {"accept": accept},
                session_id=session_id or None,
            )
        except Exception:
            handle_status = "failed"
        evidence.append(
            BrowserDownloadDialogEvidence(
                schema_version="1.0",
                dialog_type=_normalize_dialog_type(event.get("type")),
                message=_sanitize_dialog_message(event.get("message")),
                page_url=str(event.get("url") or normalized_url or "").strip(),
                action_taken=action_taken,
                validation_status=handle_status,
                target_id=resolved_session.target_id,
                session_id=session_id,
            )
        )

    _register_page_dialog_opening_handler(client, on_dialog_opening)
    try:
        _send_raw_cdp(
            client=client,
            method="Page.enable",
            params={},
            session_id=resolved_session.session_id,
            timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
        )
        _await_with_timeout(
            asyncio.sleep(_CDP_DIALOG_DRAIN_SECONDS),
            timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
        )
        if not evidence:
            unknown_evidence = _try_handle_unknown_terminal_dialog(
                client=client,
                normalized_url=normalized_url,
                allow_beforeunload=allow_beforeunload,
                target_id=resolved_session.target_id,
                session_id=resolved_session.session_id,
            )
            if unknown_evidence is not None:
                evidence.append(unknown_evidence)
    finally:
        _unregister_cdp_event_handler(client, "Page.javascriptDialogOpening")
        if resolved_session.transient:
            _detach_transient_cdp_session(
                client=resolved_session.client,
                session_id=resolved_session.session_id,
            )
    return evidence


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


def _register_page_dialog_opening_handler(client: Any, callback: Any) -> None:
    register = getattr(client, "register", None)
    page_register = getattr(register, "Page", None) if register is not None else None
    opening_register = (
        getattr(page_register, "javascriptDialogOpening", None)
        if page_register is not None
        else None
    )
    if not callable(opening_register):
        raise RuntimeError("CDP client cannot register Page.javascriptDialogOpening")
    opening_register(callback)


def _unregister_cdp_event_handler(client: Any, method: str) -> None:
    registry = getattr(client, "_event_registry", None)
    unregister = getattr(registry, "unregister", None) if registry is not None else None
    if not callable(unregister):
        return
    try:
        unregister(method)
    except Exception:
        return


def _try_handle_unknown_terminal_dialog(
    *,
    client: Any,
    normalized_url: str,
    allow_beforeunload: bool,
    target_id: str,
    session_id: str,
) -> BrowserDownloadDialogEvidence | None:
    accept = bool(allow_beforeunload)
    try:
        _send_raw_cdp(
            client=client,
            method="Page.handleJavaScriptDialog",
            params={"accept": accept},
            session_id=session_id,
            timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
        )
    except Exception:
        return None
    return BrowserDownloadDialogEvidence(
        schema_version="1.0",
        dialog_type="unknown",
        message="",
        page_url=str(normalized_url or "").strip(),
        action_taken=(
            "accepted_without_opening_event" if accept else "dismissed_without_opening_event"
        ),
        validation_status="handled_without_opening_event",
        target_id=target_id,
        session_id=session_id,
    )


def _dialog_policy_action(
    raw_dialog_type: Any,
    *,
    allow_beforeunload: bool,
) -> tuple[str, str, bool]:
    dialog_type = _normalize_dialog_type(raw_dialog_type)
    if dialog_type == "alert":
        return "accepted", "handled", True
    if dialog_type == "beforeunload":
        if allow_beforeunload:
            return "accepted_beforeunload_for_teardown", "handled", True
        return "dismissed_beforeunload_by_policy", "policy_rejected", False
    if dialog_type in {"confirm", "prompt"}:
        return f"dismissed_{dialog_type}_by_policy", "policy_rejected", False
    return "dismissed_unknown_by_policy", "policy_rejected", False


def _normalize_dialog_type(raw_dialog_type: Any) -> str:
    token = str(raw_dialog_type or "").strip().casefold()
    if token in {"alert", "confirm", "prompt", "beforeunload"}:
        return token
    return "unknown"


def _sanitize_dialog_message(raw_message: Any) -> str:
    token = " ".join(str(raw_message or "").replace("\x00", " ").split())
    if len(token) <= _CDP_DIALOG_MESSAGE_MAX_CHARS:
        return token
    return token[: _CDP_DIALOG_MESSAGE_MAX_CHARS - 3].rstrip() + "..."


def _send_browser_download_cdp(
    *,
    browser: Any,
    method: str,
    params: dict[str, Any],
    timeout_seconds: float,
    target_url: str = "",
) -> tuple[dict[str, Any], str, str]:
    if method in _TARGET_LEVEL_METHODS:
        client = _resolve_root_cdp_client(browser)
        result = _send_raw_cdp(
            client=client,
            method=method,
            params=params,
            session_id="",
            timeout_seconds=timeout_seconds,
        )
        return result, "", ""
    resolved_session = _resolve_browser_cdp_session(
        browser,
        timeout_seconds=timeout_seconds,
        target_url=target_url,
    )
    try:
        result = _send_raw_cdp(
            client=resolved_session.client,
            method=method,
            params=params,
            session_id=resolved_session.session_id,
            timeout_seconds=timeout_seconds,
        )
        return result, resolved_session.target_id, resolved_session.session_id
    finally:
        if resolved_session.transient:
            _detach_transient_cdp_session(
                client=resolved_session.client,
                session_id=resolved_session.session_id,
            )


def _resolve_browser_cdp_session(
    browser: Any,
    *,
    timeout_seconds: float,
    target_url: str = "",
) -> _ResolvedCdpSession:
    if str(target_url or "").strip():
        return _resolve_browser_cdp_session_for_target_url(
            browser,
            target_url=target_url,
            timeout_seconds=timeout_seconds,
        )
    get_session = getattr(browser, "get_or_create_cdp_session", None)
    if not callable(get_session):
        return _attach_transient_cdp_session(
            browser,
            timeout_seconds=timeout_seconds,
        )
    try:
        session = _await_with_timeout(
            get_session(target_id=None, focus=False),
            timeout_seconds=timeout_seconds,
        )
    except TypeError:
        session = _await_with_timeout(get_session(), timeout_seconds=timeout_seconds)
    except Exception:
        return _attach_transient_cdp_session(
            browser,
            timeout_seconds=timeout_seconds,
        )
    client = getattr(session, "cdp_client", None)
    session_id = str(getattr(session, "session_id", "") or "")
    target_id = str(getattr(session, "target_id", "") or "")
    if client is None or not session_id:
        return _attach_transient_cdp_session(
            browser,
            timeout_seconds=timeout_seconds,
        )
    return _ResolvedCdpSession(
        client=client,
        target_id=target_id,
        session_id=session_id,
        transient=False,
    )


def _resolve_browser_cdp_session_for_target_url(
    browser: Any,
    *,
    target_url: str,
    timeout_seconds: float,
) -> _ResolvedCdpSession:
    client = _resolve_root_cdp_client(browser)
    targets_result = _send_raw_cdp(
        client=client,
        method="Target.getTargets",
        params={},
        session_id="",
        timeout_seconds=timeout_seconds,
    )
    target_id = _select_real_page_target_id(
        targets_result,
        target_url=target_url,
        require_url_match=True,
    )
    if not target_id:
        raise RuntimeError("no real page target matched the requested CDP target URL")
    get_session = getattr(browser, "get_or_create_cdp_session", None)
    if callable(get_session):
        try:
            session = _await_with_timeout(
                get_session(target_id=target_id, focus=False),
                timeout_seconds=timeout_seconds,
            )
            client_from_session = getattr(session, "cdp_client", None)
            session_id = str(getattr(session, "session_id", "") or "")
            resolved_target_id = str(getattr(session, "target_id", "") or target_id)
            if client_from_session is not None and session_id:
                return _ResolvedCdpSession(
                    client=client_from_session,
                    target_id=resolved_target_id,
                    session_id=session_id,
                    transient=False,
                )
        except TypeError:
            pass
        except Exception:
            pass
    attach_result = _send_raw_cdp(
        client=client,
        method="Target.attachToTarget",
        params={"targetId": target_id, "flatten": True},
        session_id="",
        timeout_seconds=timeout_seconds,
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


def _resolve_browser_cdp_session_for_target_id(
    *,
    browser: Any,
    target_id: str,
    timeout_seconds: float,
) -> _ResolvedCdpSession:
    token = str(target_id or "").strip()
    if not token:
        raise RuntimeError("CDP target ID is required for target hygiene")
    get_session = getattr(browser, "get_or_create_cdp_session", None)
    if callable(get_session):
        try:
            session = _await_with_timeout(
                get_session(target_id=token, focus=False),
                timeout_seconds=timeout_seconds,
            )
            client_from_session = getattr(session, "cdp_client", None)
            session_id = str(getattr(session, "session_id", "") or "")
            resolved_target_id = str(getattr(session, "target_id", "") or token)
            if client_from_session is not None and session_id:
                return _ResolvedCdpSession(
                    client=client_from_session,
                    target_id=resolved_target_id,
                    session_id=session_id,
                    transient=False,
                )
        except TypeError:
            pass
        except Exception:
            pass
    client = _resolve_root_cdp_client(browser)
    attach_result = _send_raw_cdp(
        client=client,
        method="Target.attachToTarget",
        params={"targetId": token, "flatten": True},
        session_id="",
        timeout_seconds=timeout_seconds,
    )
    session_id = str(attach_result.get("sessionId") or "").strip()
    if not session_id:
        raise RuntimeError("CDP target attach returned no session ID")
    return _ResolvedCdpSession(
        client=client,
        target_id=token,
        session_id=session_id,
        transient=True,
    )


def _attach_transient_cdp_session(
    browser: Any,
    *,
    timeout_seconds: float = _CDP_OPERATION_TIMEOUT_SECONDS,
) -> _ResolvedCdpSession:
    client = _resolve_root_cdp_client(browser)
    targets_result = _send_raw_cdp(
        client=client,
        method="Target.getTargets",
        params={},
        session_id="",
        timeout_seconds=timeout_seconds,
    )
    target_id = _select_real_page_target_id(targets_result)
    if not target_id:
        raise RuntimeError("no real page target is available for CDP evidence capture")
    attach_result = _send_raw_cdp(
        client=client,
        method="Target.attachToTarget",
        params={"targetId": target_id, "flatten": True},
        session_id="",
        timeout_seconds=timeout_seconds,
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
            timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
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


def _select_real_page_target_id(
    targets_result: dict[str, Any],
    *,
    target_url: str = "",
    require_url_match: bool = False,
) -> str:
    target = _select_real_page_target_info(
        targets_result,
        target_url=target_url,
        require_url_match=require_url_match,
    )
    if target is None:
        return ""
    return str(target.get("targetId") or target.get("target_id") or "").strip()


def _select_real_page_target_info(
    targets_result: dict[str, Any],
    *,
    target_url: str = "",
    require_url_match: bool = False,
) -> dict[str, Any] | None:
    raw_targets = targets_result.get("targetInfos")
    if not isinstance(raw_targets, list):
        return None
    candidates: list[dict[str, Any]] = []
    url_candidates: list[dict[str, Any]] = []
    for raw_target in raw_targets:
        if not isinstance(raw_target, dict):
            continue
        if not _is_user_facing_page_target(raw_target):
            continue
        candidates.append(raw_target)
        url = str(raw_target.get("url") or "").strip()
        if _target_url_matches(url, target_url):
            url_candidates.append(raw_target)
    if target_url:
        return url_candidates[-1] if url_candidates else None
    if require_url_match:
        return None
    return candidates[-1] if candidates else None


def _is_user_facing_page_target(raw_target: dict[str, Any]) -> bool:
    target_type = str(raw_target.get("type") or raw_target.get("target_type") or "").strip()
    if target_type != "page":
        return False
    target_id = str(raw_target.get("targetId") or raw_target.get("target_id") or "").strip()
    if not target_id:
        return False
    url = str(raw_target.get("url") or "").strip()
    if not url:
        return False
    if any(url.startswith(prefix) for prefix in _INTERNAL_TARGET_URL_PREFIXES):
        return False
    return True


def _target_url_matches(candidate_url: str, expected_url: str) -> bool:
    candidate = str(candidate_url or "").strip()
    expected = str(expected_url or "").strip()
    if not candidate or not expected:
        return False
    return _without_url_fragment(candidate).rstrip("/") == _without_url_fragment(
        expected
    ).rstrip("/")


def _without_url_fragment(raw_url: str) -> str:
    return str(raw_url or "").split("#", 1)[0]


def _read_target_viewport_size(
    *,
    client: Any,
    session_id: str,
) -> tuple[int, int, str]:
    try:
        result = _send_raw_cdp(
            client=client,
            method="Page.getLayoutMetrics",
            params={},
            session_id=session_id,
            timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
        )
    except Exception:
        return 0, 0, "unknown"
    width = _coerce_viewport_dimension(result, "clientWidth", "width")
    height = _coerce_viewport_dimension(result, "clientHeight", "height")
    if width < 0 and height < 0:
        return width, height, "unknown"
    if width <= 0 or height <= 0:
        return width, height, "zero_size"
    return width, height, "ok"


def _coerce_viewport_dimension(
    result: dict[str, Any],
    primary_key: str,
    fallback_key: str,
) -> int:
    for container_key in ("visualViewport", "layoutViewport", "cssVisualViewport", "cssLayoutViewport"):
        container = result.get(container_key)
        if not isinstance(container, dict):
            continue
        raw_value = container.get(primary_key, container.get(fallback_key))
        try:
            value = int(float(str(raw_value)))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return -1


def _focus_browser_use_target(*, browser: Any, target_id: str) -> None:
    get_session = getattr(browser, "get_or_create_cdp_session", None)
    if not callable(get_session):
        return
    try:
        _await_with_timeout(
            get_session(target_id=target_id, focus=True),
            timeout_seconds=_CDP_OPERATION_TIMEOUT_SECONDS,
        )
    except Exception:
        return


def _send_raw_cdp(
    *,
    client: Any,
    method: str,
    params: dict[str, Any],
    session_id: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    send_raw = getattr(client, "send_raw", None)
    if callable(send_raw):
        result = _await_cdp_client_operation(
            client=client,
            value=send_raw(method, params, session_id=session_id or None),
            timeout_seconds=timeout_seconds,
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
        timeout_seconds=timeout_seconds,
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


def _await_with_timeout(
    value: Any,
    *,
    timeout_seconds: float = _CDP_OPERATION_TIMEOUT_SECONDS,
) -> Any:
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
        return asyncio.run(asyncio.wait_for(awaitable(), timeout=timeout_seconds))

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if thread.is_alive():
        raise TimeoutError("CDP operation timed out")
    if errors:
        raise errors[0]
    return payload.get("result")


def _await_cdp_client_operation(
    *,
    client: Any,
    value: Any,
    timeout_seconds: float = _CDP_OPERATION_TIMEOUT_SECONDS,
) -> Any:
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
                return future.result(timeout=timeout_seconds)
            except FutureTimeoutError as exc:
                future.cancel()
                raise TimeoutError("CDP operation timed out") from exc
    return _await_with_timeout(value, timeout_seconds=timeout_seconds)


def _cdp_timeout_seconds(method: str) -> float:
    if method == "Page.printToPDF":
        return _CDP_PRINT_TO_PDF_TIMEOUT_SECONDS
    return _CDP_OPERATION_TIMEOUT_SECONDS
