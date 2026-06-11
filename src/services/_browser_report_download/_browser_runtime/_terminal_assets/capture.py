from __future__ import annotations
import logging
import re
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit
from src.contracts.browser_download import (
    BrowserDownloadDialogEvidence,
    BrowserDownloadNetworkEvent,
    BrowserReportDownloadRequest,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.cdp import (
    capture_print_pdf_via_cdp,
    collect_terminal_dialog_evidence_via_cdp,
    ensure_browser_download_target_hygiene_via_cdp,
)
from src.utils.logging import log_event
from src.services._browser_report_download._browser_runtime import (
    _TERMINAL_REPORT_TEXT_MARKERS,
)

from .artifacts import (
    _parse_raw_model_response,
)

from .network import (
    _collect_network_events,
    _collect_network_resource_urls,
)

from .page_state import (
    _write_terminal_html_snapshot,
    _write_terminal_screenshot,
)

logger = logging.getLogger("market_lense.browser_report_download_service")


def _capture_terminal_assets(
    *,
    browser: Any,
    page: Any,
    download_dir: Path,
    final_page_url: str,
    final_page_html: str,
    route_family: str,
    ctx: RunContext,
    normalized_url: str,
) -> tuple[list[str], list[BrowserDownloadNetworkEvent], str, str]:
    _ensure_terminal_target_hygiene(
        browser=browser,
        final_page_url=final_page_url,
        ctx=ctx,
        normalized_url=normalized_url,
        activate=True,
    )
    network_events = _collect_network_events(
        browser=browser,
        page=page,
        route_family=route_family,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    network_resource_urls = _collect_network_resource_urls(
        page=page,
        final_page_html=final_page_html,
        network_events=network_events,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    html_snapshot_path = _write_terminal_html_snapshot(
        download_dir=download_dir,
        final_page_html=final_page_html,
    )
    screenshot_path = _write_terminal_screenshot(
        browser=browser,
        page=page,
        download_dir=download_dir,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    return network_resource_urls, network_events, html_snapshot_path, screenshot_path


def _capture_terminal_dialog_evidence(
    *,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    allow_beforeunload: bool,
    target_url: str = "",
) -> list[BrowserDownloadDialogEvidence]:
    if browser is None:
        return []
    browser_use_evidence = _read_browser_closed_popup_dialog_evidence(browser)
    cdp_evidence = collect_terminal_dialog_evidence_via_cdp(
        browser=browser,
        ctx=ctx,
        normalized_url=normalized_url,
        allow_beforeunload=allow_beforeunload,
        target_url=target_url,
        required=False,
    )
    return _dedupe_browser_dialog_evidence(
        [
            *browser_use_evidence,
            *cdp_evidence,
            *_read_browser_closed_popup_dialog_evidence(browser),
        ]
    )


def _ensure_terminal_target_hygiene(
    *,
    browser: Any,
    final_page_url: str,
    ctx: RunContext,
    normalized_url: str,
    activate: bool,
) -> None:
    ensure_browser_download_target_hygiene_via_cdp(
        browser=browser,
        ctx=ctx,
        normalized_url=normalized_url,
        target_url=final_page_url,
        activate=activate,
        required=False,
    )


def _read_browser_closed_popup_dialog_evidence(
    browser: Any,
) -> list[BrowserDownloadDialogEvidence]:
    raw_messages = getattr(browser, "_closed_popup_messages", None)
    if raw_messages is None:
        raw_messages = getattr(
            getattr(browser, "browser_session", None),
            "_closed_popup_messages",
            None,
        )
    if not isinstance(raw_messages, list):
        return []
    evidence: list[BrowserDownloadDialogEvidence] = []
    for raw_message in raw_messages:
        dialog_type, message = _parse_closed_popup_message(raw_message)
        evidence.append(
            BrowserDownloadDialogEvidence(
                schema_version="1.0",
                dialog_type=dialog_type,
                message=message,
                page_url="",
                action_taken="auto_handled_by_browser_use",
                validation_status="handled",
                target_id="",
                session_id="",
            )
        )
    return evidence


def _parse_closed_popup_message(raw_message: Any) -> tuple[str, str]:
    token = " ".join(str(raw_message or "").replace("\x00", " ").split())
    match = re.match(r"^\[(?P<type>[A-Za-z]+)]\s*(?P<message>.*)$", token)
    if match is None:
        return "unknown", token
    dialog_type = match.group("type").strip().casefold()
    if dialog_type not in {"alert", "confirm", "prompt", "beforeunload"}:
        dialog_type = "unknown"
    return dialog_type, match.group("message").strip()


def _dedupe_browser_dialog_evidence(
    dialog_evidence: list[BrowserDownloadDialogEvidence],
) -> list[BrowserDownloadDialogEvidence]:
    normalized: list[BrowserDownloadDialogEvidence] = []
    seen: set[tuple[str, str, str, str]] = set()
    for item in dialog_evidence:
        marker = (
            str(item.dialog_type or "").casefold(),
            str(item.message or "").casefold(),
            str(item.page_url or "").casefold(),
            str(item.action_taken or "").casefold(),
        )
        if marker in seen:
            continue
        seen.add(marker)
        normalized.append(item)
    return normalized


def _maybe_capture_print_pdf_fallback(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    raw_model_response: str,
    final_page_url: str,
    final_page_title: str,
    final_page_html: str,
    download_dir: Path,
    ctx: RunContext,
    normalized_url: str,
    downloaded_files: list[str],
    attachment_paths: list[str],
) -> str:
    if downloaded_files or attachment_paths:
        return ""
    if not _should_capture_print_pdf_fallback(
        request=request,
        raw_model_response=raw_model_response,
        final_page_url=final_page_url,
        final_page_title=final_page_title,
        final_page_html=final_page_html,
    ):
        return ""
    pdf_path = _browser_rendered_pdf_capture_path(
        download_dir=download_dir,
        final_page_url=final_page_url or normalized_url,
    )
    if not capture_print_pdf_via_cdp(
        browser=browser,
        pdf_path=pdf_path,
        ctx=ctx,
        normalized_url=normalized_url,
        required=False,
        target_url=final_page_url or normalized_url,
    ):
        return ""
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_print_pdf_fallback_captured",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "final_page_url": final_page_url,
                "pdf_path": str(pdf_path),
                "provenance": "browser_rendered_print_to_pdf",
            },
        )
    )
    return str(pdf_path)


def _should_capture_print_pdf_fallback(
    *,
    request: BrowserReportDownloadRequest,
    raw_model_response: str,
    final_page_url: str,
    final_page_title: str,
    final_page_html: str,
) -> bool:
    if str(final_page_url or "").strip().casefold().endswith(".pdf"):
        return False
    payload = _parse_raw_model_response(raw_model_response)
    route_family = str(
        request.route_family_hint or payload.get("route_family") or ""
    ).strip()
    route_kind = str(payload.get("route_kind") or "").strip()
    if route_family != "browser_onsite_report" and route_kind != "onsite_report":
        return False
    html = str(final_page_html or "")
    if len(html.strip()) < 800:
        return False
    visible_text = _browser_visible_text_from_html(html)
    haystack = " ".join(
        [
            str(final_page_url or ""),
            str(final_page_title or ""),
            visible_text,
            str(request.candidate_trace.title or "") if request.candidate_trace else "",
        ]
    ).casefold()
    if not any(marker in haystack for marker in _TERMINAL_REPORT_TEXT_MARKERS):
        return False
    non_report_context = " ".join(
        [
            str(final_page_url or ""),
            str(final_page_title or ""),
            str(request.candidate_trace.title or "") if request.candidate_trace else "",
        ]
    ).casefold()
    if _browser_text_has_non_report_marker(non_report_context):
        return False
    has_print_signal = bool(
        re.search(
            r"(?is)(window\.print|@media\s+print|media=[\"']print[\"']|>\s*print\s*<|print this|print page|save as pdf)",
            html,
        )
    )
    if not has_print_signal:
        return False
    return len(visible_text) >= 500


def _browser_visible_text_from_html(html: str) -> str:
    token = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1\b[^>]*>", " ", str(html or ""))
    token = re.sub(r"(?is)<[^>]+>", " ", token)
    return " ".join(token.split())


def _browser_text_has_non_report_marker(text: str) -> bool:
    lowered = str(text or "").casefold()
    non_report_markers = ("case study", "customer story", "press release", "careers")
    return any(marker in lowered for marker in non_report_markers)


def _browser_rendered_pdf_capture_path(
    *,
    download_dir: Path,
    final_page_url: str,
) -> Path:
    stem = Path(urlsplit(str(final_page_url or "onsite-report")).path).stem
    if not stem:
        stem = "onsite-report"
    safe_stem = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip(".-")
    if not safe_stem:
        safe_stem = "onsite-report"
    return download_dir / f"{safe_stem}-browser-rendered.pdf"


def _capture_completed_history_terminal_assets(
    *,
    browser: Any,
    download_dir: Path,
    final_page_url: str,
    route_family: str,
    ctx: RunContext,
    normalized_url: str,
    fallback_screenshot_path: str,
) -> tuple[list[str], list[BrowserDownloadNetworkEvent], str]:
    _ensure_terminal_target_hygiene(
        browser=browser,
        final_page_url=final_page_url,
        ctx=ctx,
        normalized_url=normalized_url,
        activate=True,
    )
    network_events = _collect_network_events(
        browser=browser,
        page=None,
        route_family=route_family,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    network_resource_urls = _collect_network_resource_urls(
        page=None,
        final_page_html="",
        network_events=network_events,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    screenshot_path = str(fallback_screenshot_path or "").strip()
    if not screenshot_path:
        screenshot_path = _write_terminal_screenshot(
            browser=browser,
            page=None,
            download_dir=download_dir,
            ctx=ctx,
            normalized_url=normalized_url,
        )
    return network_resource_urls, network_events, screenshot_path


__all__ = [
    "_capture_terminal_assets",
    "_capture_terminal_dialog_evidence",
    "_ensure_terminal_target_hygiene",
    "_read_browser_closed_popup_dialog_evidence",
    "_parse_closed_popup_message",
    "_dedupe_browser_dialog_evidence",
    "_maybe_capture_print_pdf_fallback",
    "_should_capture_print_pdf_fallback",
    "_browser_visible_text_from_html",
    "_browser_text_has_non_report_marker",
    "_browser_rendered_pdf_capture_path",
    "_capture_completed_history_terminal_assets",
]
