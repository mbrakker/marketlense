from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.contracts.browser_download import BrowserDownloadDialogEvidence

logger = logging.getLogger("market_lense.browser_report_download_service.cdp")

from .models import (
    _CDP_OPERATION_TIMEOUT_SECONDS,
    _CDP_DIALOG_DRAIN_SECONDS,
    _CDP_DIALOG_MESSAGE_MAX_CHARS,
)

from .transport import (
    _send_raw_cdp,
    _await_with_timeout,
)

from .session import (
    _resolve_browser_cdp_session,
    _detach_transient_cdp_session,
)


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

    async def on_dialog_opening(
        params: Any, event_session_id: str | None = None
    ) -> None:
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
            "accepted_without_opening_event"
            if accept
            else "dismissed_without_opening_event"
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
