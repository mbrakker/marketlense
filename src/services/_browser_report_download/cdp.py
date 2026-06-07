"""Allowlisted raw-CDP helpers for the browser report-download service."""

from __future__ import annotations

# ruff: noqa: F401

from ._cdp.models import (
    _CDP_ALLOWLIST,
    _TARGET_LEVEL_METHODS,
    _INTERNAL_TARGET_URL_PREFIXES,
    _CDP_OPERATION_TIMEOUT_SECONDS,
    _CDP_PRINT_TO_PDF_TIMEOUT_SECONDS,
    _CDP_DIALOG_DRAIN_SECONDS,
    _CDP_DIALOG_MESSAGE_MAX_CHARS,
    BrowserDownloadCdpCallResult,
    BrowserDownloadTargetHygieneResult,
    _ResolvedCdpSession,
)
from ._cdp.transport import (
    _send_raw_cdp,
    _extract_runtime_value,
    _await_with_timeout,
    _await_cdp_client_operation,
    _cdp_timeout_seconds,
)
from ._cdp.session import (
    _send_browser_download_cdp,
    _resolve_browser_cdp_session,
    _resolve_browser_cdp_session_for_target_url,
    _resolve_browser_cdp_session_for_target_id,
    _attach_transient_cdp_session,
    _detach_transient_cdp_session,
    _resolve_root_cdp_client,
    _select_real_page_target_id,
    _select_real_page_target_info,
    _is_user_facing_page_target,
    _target_url_matches,
    _without_url_fragment,
    _read_target_viewport_size,
    _coerce_viewport_dimension,
    _focus_browser_use_target,
)
from ._cdp.dialogs import (
    _collect_terminal_dialog_evidence_via_cdp,
    _register_page_dialog_opening_handler,
    _unregister_cdp_event_handler,
    _try_handle_unknown_terminal_dialog,
    _dialog_policy_action,
    _normalize_dialog_type,
    _sanitize_dialog_message,
)
from ._cdp.operations import (
    logger,
    get_browser_download_cdp_allowlist,
    select_browser_download_real_page_target_info,
    call_browser_download_cdp,
    collect_terminal_network_entries_via_cdp,
    ensure_browser_download_target_hygiene_via_cdp,
    capture_terminal_screenshot_via_cdp,
    collect_terminal_dialog_evidence_via_cdp,
    capture_print_pdf_via_cdp,
    _ensure_browser_download_target_hygiene_via_cdp,
)
