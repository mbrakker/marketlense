from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import asdict, dataclass
from hashlib import sha256
from importlib import import_module
from pathlib import Path
from threading import Thread
from typing import Any
from urllib.parse import urlsplit

import psutil

from src.contracts.browser_download import (
    BrowserDownloadDialogEvidence,
    BrowserDownloadNetworkEvent,
    BrowserReportDownloadRequest,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.cdp import (
    capture_print_pdf_via_cdp,
    collect_terminal_dialog_evidence_via_cdp,
    collect_terminal_network_entries_via_cdp,
    ensure_browser_download_target_hygiene_via_cdp,
)
from src.services._browser_report_download.helpers import (
    browser_helper_capture_screenshot,
    browser_helper_form_autocomplete,
    browser_helper_js,
    browser_helper_page_info,
)
from src.services._browser_report_download import http as http_runtime
from src.services._browser_report_download.http import is_pdf_file
from src.services._browser_report_download.models import (
    BrowserAgentRunResult,
    BrowserUseAgentResult,
)
from src.services._browser_report_download.prompt import (
    BrowserDownloadPromptBundle,
    redact_browser_report_download_prompt_for_log,
)
from src.services._browser_report_download.request import (
    resolve_delivery_email_value,
    resolve_effective_identity_fields,
)
from src.services._browser_report_download.session_reuse import (
    finalize_browser_session_reuse,
    resolve_browser_session_reuse,
)
from src.utils.coercion import normalize_optional_bool_signal
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.services._browser_report_download._browser_runtime import (
    _TERMINAL_TRANSIENT_MARKERS,
    _TERMINAL_SUCCESS_URL_MARKERS,
    _TERMINAL_SUCCESS_TEXT_MARKERS,
    _TERMINAL_REPORT_TEXT_MARKERS,
    _TERMINAL_TEXT_EXCERPT_MAX_CHARS,
    _TERMINAL_STABILIZATION_DEFAULT_POLL_SCHEDULE_SECONDS,
    _TERMINAL_STABILIZATION_EMAIL_POLL_SCHEDULE_SECONDS,
    _AGENT_RUN_TIMEOUT_MIN_BUFFER_SECONDS,
    _AGENT_RUN_TIMEOUT_STEP_BUFFER_SECONDS,
    _AGENT_RUN_TIMEOUT_MAX_BUFFER_SECONDS,
    _BROWSER_KILL_TIMEOUT_SECONDS,
    _BROWSER_RESET_TIMEOUT_SECONDS,
    _BROWSER_CLEANUP_GRACE_SECONDS,
    _BROWSER_PROFILE_DIR_PREFIX,
    _BROWSER_USE_TEMP_DIR_PATTERNS,
    _STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS,
    _TEMP_CLEANUP_LOG_SAMPLE_LIMIT,
    _TIMED_OUT_COMPLETED_HISTORY_GRACE_SECONDS,
    _TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS,
    _AGENT_COMPLETED_HISTORY_POLL_SECONDS,
    _BROWSER_AGENT_WORKER_ENV,
    _BROWSER_AGENT_WORKER_TIMEOUT_BUFFER_SECONDS,
    _BROWSER_AGENT_WORKER_OUTPUT_MAX_CHARS,
    _ANSI_ESCAPE_PATTERN,
    _BROWSER_AGENT_USE_JUDGE,
    _LOOKUP_FIELD_MARKERS,
    _LOOKUP_FAILURE_MARKERS,
    _LOOKUP_SUBMIT_MARKERS,
    _EMAIL_DOMAIN_BLOCK_MARKERS,
    _EMAIL_DOMAIN_FAILURE_MARKERS,
    _PARTIAL_HISTORY_TEXT_MAX_CHARS,
)

logger = logging.getLogger("market_lense.browser_report_download_service")


def _parse_raw_model_response(raw_model_response: str) -> dict[str, Any]:
    token = str(raw_model_response or "").strip()
    if not token:
        return {}
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _prefetch_structured_pdf_artifact(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
    raw_model_response: str,
    history_final_page_url: str,
) -> str:
    payload = _parse_raw_model_response(raw_model_response)
    if not payload:
        return ""
    route_kind = str(payload.get("route_kind") or "").strip()
    downloaded_name = str(payload.get("downloaded_file_name") or "").strip()
    downloaded_mime = str(payload.get("downloaded_mime_type") or "").strip().lower()
    if (
        route_kind != "pdf_download"
        and downloaded_mime != "application/pdf"
        and not downloaded_name.lower().endswith(".pdf")
    ):
        return ""
    for target_url in _structured_pdf_candidate_urls(
        payload=payload,
        history_final_page_url=history_final_page_url,
    ):
        destination_path = _pdf_prefetch_destination_path(
            download_dir=download_dir,
            target_url=target_url,
            downloaded_file_name=downloaded_name,
        )
        if destination_path.exists() and is_pdf_file(destination_path):
            return str(destination_path)
        try:
            http_runtime.download_pdf_from_url(
                pdf_url=target_url,
                destination_path=destination_path,
                timeout_seconds=request.settings.timeout_seconds,
                ctx=ctx,
                normalized_url=normalized_url,
            )
        except AppError as exc:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_pdf_prefetch_failed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "target_url": target_url,
                        "error_code": exc.code,
                        "error_message": exc.message,
                    },
                )
            )
            destination_path.unlink(missing_ok=True)
            continue
        if is_pdf_file(destination_path):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_pdf_prefetched",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "target_url": target_url,
                        "destination_path": str(destination_path),
                    },
                )
            )
            return str(destination_path)
        destination_path.unlink(missing_ok=True)
    return ""


def _materialize_external_artifacts(
    *,
    raw_model_response: str,
    attachment_paths: list[str],
    downloaded_files: list[str],
    download_dir: Path,
    ctx: RunContext,
    normalized_url: str,
) -> list[str]:
    payload = _parse_raw_model_response(raw_model_response)
    candidate_paths = _local_artifact_candidate_paths(
        payload=payload,
        attachment_paths=attachment_paths,
        downloaded_files=downloaded_files,
    )
    if not candidate_paths:
        return []
    download_dir.mkdir(parents=True, exist_ok=True)
    resolved_download_dir = _safe_resolve_path(download_dir)
    materialized_paths: list[str] = []
    seen_targets: set[str] = set()
    for source_path in candidate_paths:
        resolved_source = _safe_resolve_path(source_path)
        if resolved_source is None:
            continue
        if resolved_download_dir is not None and _is_within_directory(
            path=resolved_source,
            directory=resolved_download_dir,
        ):
            token = str(resolved_source)
            if token not in seen_targets:
                seen_targets.add(token)
                materialized_paths.append(token)
            continue
        target_path = _copy_external_artifact(
            source_path=resolved_source,
            download_dir=download_dir,
        )
        if target_path is None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_external_artifact_copy_failed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "source_path": str(resolved_source),
                    },
                )
            )
            continue
        token = str(target_path)
        if token in seen_targets:
            continue
        seen_targets.add(token)
        materialized_paths.append(token)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_external_artifact_materialized",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "source_path": str(resolved_source),
                    "destination_path": token,
                },
            )
        )
    return materialized_paths


def _local_artifact_candidate_paths(
    *,
    payload: dict[str, Any],
    attachment_paths: list[str],
    downloaded_files: list[str],
) -> list[Path]:
    candidates: list[Path] = []
    seen: set[str] = set()

    def add(raw_value: Any) -> None:
        token = str(raw_value or "").strip()
        if not token or token.startswith(("http://", "https://")):
            return
        marker = token.casefold()
        if marker in seen:
            return
        path = Path(token).expanduser()
        if not path.exists() or not path.is_file():
            return
        seen.add(marker)
        candidates.append(path)

    add(payload.get("downloaded_file_path"))
    add(payload.get("onsite_capture_path"))
    for raw_path in attachment_paths:
        add(raw_path)
    for raw_path in downloaded_files:
        add(raw_path)
    return candidates


def _copy_external_artifact(
    *,
    source_path: Path,
    download_dir: Path,
) -> Path | None:
    target_path = download_dir / source_path.name
    counter = 1
    while target_path.exists():
        try:
            if source_path.samefile(target_path):
                return _safe_resolve_path(target_path)
        except OSError:
            target_path = (
                download_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
            )
            counter += 1
            continue
        target_path = download_dir / f"{source_path.stem}_{counter}{source_path.suffix}"
        counter += 1
    try:
        shutil.copy2(source_path, target_path)
    except OSError:
        return None
    resolved_target = _safe_resolve_path(target_path)
    if (
        resolved_target is None
        or not resolved_target.exists()
        or not resolved_target.is_file()
    ):
        return None
    return resolved_target


def _safe_resolve_path(path: Path) -> Path | None:
    try:
        return path.expanduser().resolve()
    except OSError:
        return None


def _is_within_directory(*, path: Path, directory: Path) -> bool:
    try:
        path.relative_to(directory)
    except ValueError:
        return False
    return True


def _structured_pdf_candidate_urls(
    *,
    payload: dict[str, Any],
    history_final_page_url: str,
) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()

    def add(raw_value: Any) -> None:
        token = str(raw_value or "").strip()
        if not _looks_like_pdf_resource_url(token):
            return
        marker = token.casefold()
        if marker in seen:
            return
        seen.add(marker)
        candidates.append(token)

    add(payload.get("resolved_target_url"))
    add(payload.get("final_page_url"))
    add(history_final_page_url)
    for raw_step in payload.get("route_steps", []):
        if isinstance(raw_step, dict):
            add(raw_step.get("target_url"))
    for raw_url in payload.get("traversed_page_urls", []):
        add(raw_url)
    return candidates


def _looks_like_pdf_resource_url(raw_url: str) -> bool:
    token = str(raw_url or "").strip()
    if not token:
        return False
    lowered = token.casefold()
    return lowered.startswith(("http://", "https://")) and (
        lowered.endswith(".pdf") or ".pdf?" in lowered
    )


def _pdf_prefetch_destination_path(
    *,
    download_dir: Path,
    target_url: str,
    downloaded_file_name: str,
) -> Path:
    url_name = Path(urlsplit(target_url).path).name
    file_name = url_name or downloaded_file_name or "download.pdf"
    if not file_name.lower().endswith(".pdf"):
        file_name = f"{file_name}.pdf"
    return download_dir / file_name


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


def _collect_network_resource_urls(
    *,
    page: Any,
    final_page_html: str,
    network_events: list[BrowserDownloadNetworkEvent],
    ctx: RunContext,
    normalized_url: str,
) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()

    def add(raw_url: Any) -> None:
        token = str(raw_url or "").strip()
        if not _looks_like_documentish_url(token):
            return
        marker = token.casefold()
        if marker in seen:
            return
        seen.add(marker)
        normalized.append(token)

    if page is not None:
        for raw_url in _collect_page_resource_urls(
            page,
            ctx=ctx,
            normalized_url=normalized_url,
        ):
            add(raw_url)
        for raw_url in _collect_dom_candidate_urls(
            page,
            ctx=ctx,
            normalized_url=normalized_url,
        ):
            add(raw_url)
    for event in network_events:
        add(event.url)
    for raw_url in _extract_documentish_urls_from_html(final_page_html):
        add(raw_url)
    return normalized


def _collect_network_events(
    *,
    browser: Any,
    page: Any,
    route_family: str,
    ctx: RunContext,
    normalized_url: str,
) -> list[BrowserDownloadNetworkEvent]:
    cdp_events = _collect_network_events_via_cdp(
        browser=browser,
        route_family=route_family,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if page is None:
        return cdp_events
    js_result = browser_helper_js(
        page=page,
        expression="""
                return (() => {
                  const build = (entry, initiatorFallback = 'other') => ({
                    url: String(entry?.name || '').trim(),
                    initiator_type: String(entry?.initiatorType || initiatorFallback || 'other').trim(),
                  });
                  const navigationEntries = (globalThis.performance?.getEntriesByType?.('navigation') || [])
                    .map((entry) => build(entry, 'navigation'));
                  const resourceEntries = (globalThis.performance?.getEntriesByType?.('resource') || [])
                    .map((entry) => build(entry, 'other'));
                  return [...navigationEntries, ...resourceEntries];
                })();
                """,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if js_result.status != "ok":
        return cdp_events
    raw_events = js_result.result
    raw_events = _coerce_evaluate_list(raw_events)
    page_events = _network_events_from_raw_events(raw_events)
    if not cdp_events:
        return page_events
    return _merge_network_events(cdp_events, page_events)


def _collect_network_events_via_cdp(
    *,
    browser: Any,
    route_family: str,
    ctx: RunContext,
    normalized_url: str,
) -> list[BrowserDownloadNetworkEvent]:
    if str(route_family or "").strip() not in {
        "browser_email_form",
        "browser_pdf_click",
        "browser_tracker_redirect",
        "browser_onsite_report",
    }:
        return []
    raw_events = collect_terminal_network_entries_via_cdp(
        browser=browser,
        ctx=ctx,
        normalized_url=normalized_url,
        required=False,
    )
    return _network_events_from_raw_events(raw_events)


def _network_events_from_raw_events(
    raw_events: list[Any],
) -> list[BrowserDownloadNetworkEvent]:
    events: list[BrowserDownloadNetworkEvent] = []
    seen: set[tuple[str, str]] = set()
    for raw_event in raw_events:
        if isinstance(raw_event, dict):
            url = str(raw_event.get("url") or raw_event.get("name") or "").strip()
            initiator_type = (
                str(
                    raw_event.get("initiator_type")
                    or raw_event.get("initiatorType")
                    or "other"
                ).strip()
                or "other"
            )
        else:
            url = str(raw_event or "").strip()
            initiator_type = "other"
        if not url or not url.casefold().startswith("http"):
            continue
        key = (url.casefold(), initiator_type.casefold())
        if key in seen:
            continue
        seen.add(key)
        events.append(
            BrowserDownloadNetworkEvent(
                schema_version="1.0",
                url=url,
                initiator_type=initiator_type,
                signal_kind=_classify_network_signal_kind(
                    url=url,
                    initiator_type=initiator_type,
                ),
            )
        )
    return events[-25:]


def _merge_network_events(
    first: list[BrowserDownloadNetworkEvent],
    second: list[BrowserDownloadNetworkEvent],
) -> list[BrowserDownloadNetworkEvent]:
    merged: list[BrowserDownloadNetworkEvent] = []
    seen: set[tuple[str, str]] = set()
    for event in [*first, *second]:
        key = (event.url.casefold(), event.initiator_type.casefold())
        if key in seen:
            continue
        seen.add(key)
        merged.append(event)
    return merged[-25:]


def _classify_network_signal_kind(*, url: str, initiator_type: str) -> str:
    lowered_url = str(url or "").strip().casefold()
    lowered_initiator = str(initiator_type or "").strip().casefold()
    if not lowered_url:
        return "other"
    if lowered_url.endswith(".pdf") or ".pdf?" in lowered_url:
        return "document_request"
    if any(
        marker in lowered_url
        for marker in ("thank", "success", "confirm", "complete", "done")
    ):
        return "confirmation_request"
    if any(
        marker in lowered_url
        for marker in (
            "download",
            "document",
            "whitepaper",
            "research",
            "study",
            "ebook",
            "report",
        )
    ):
        return "document_request"
    if lowered_initiator in {"fetch", "xmlhttprequest", "beacon"} and any(
        marker in lowered_url
        for marker in (
            "form",
            "submit",
            "lead",
            "register",
            "request",
            "contact",
            "marketo",
            "pardot",
            "hubspot",
            "eloqua",
        )
    ):
        return "submission_request"
    if lowered_initiator == "navigation":
        return "navigation_request"
    return "other"


def _collect_page_resource_urls(
    page: Any,
    *,
    ctx: RunContext,
    normalized_url: str,
) -> list[str]:
    js_result = browser_helper_js(
        page=page,
        expression="""
                return (() => {
                  const entries = globalThis.performance?.getEntriesByType?.('resource') || [];
                  return entries
                    .map((entry) => String(entry?.name || '').trim())
                    .filter(Boolean)
                    .filter((url) => {
                      const lowered = url.toLowerCase();
                      return lowered.endsWith('.pdf')
                        || lowered.includes('.pdf?')
                        || lowered.includes('download')
                        || lowered.includes('document')
                        || lowered.includes('report');
                    });
                })();
                """,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if js_result.status != "ok":
        return []
    resource_urls = _coerce_evaluate_list(js_result.result)
    return [
        str(raw_url or "").strip()
        for raw_url in resource_urls
        if str(raw_url or "").strip()
    ]


def _collect_dom_candidate_urls(
    page: Any,
    *,
    ctx: RunContext,
    normalized_url: str,
) -> list[str]:
    js_result = browser_helper_js(
        page=page,
        expression="""
                return (() => {
                  const selectors = [
                    'a[href]',
                    'iframe[src]',
                    'embed[src]',
                    'object[data]',
                    'source[src]',
                    'link[href]',
                    'meta[content]',
                  ];
                  const values = [];
                  for (const selector of selectors) {
                    for (const node of document.querySelectorAll(selector)) {
                      const value =
                        node.getAttribute('href')
                        || node.getAttribute('src')
                        || node.getAttribute('data')
                        || node.getAttribute('content')
                        || '';
                      if (value) {
                        values.push(String(value).trim());
                      }
                    }
                  }
                  return values;
                })();
                """,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    if js_result.status != "ok":
        return []
    candidate_urls = _coerce_evaluate_list(js_result.result)
    return [
        str(raw_url or "").strip()
        for raw_url in candidate_urls
        if str(raw_url or "").strip()
    ]


def _coerce_evaluate_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    token = str(value or "").strip()
    if not token:
        return []
    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def _extract_documentish_urls_from_html(html: str) -> list[str]:
    token = str(html or "")
    if not token.strip():
        return []
    urls: list[str] = []
    for match in re.finditer(
        r"""(?is)(?:href|src|data|content)\s*=\s*['"]([^'"]+)['"]""",
        token,
    ):
        candidate = str(match.group(1) or "").strip()
        if candidate:
            urls.append(candidate)
    return urls


def _looks_like_documentish_url(raw_url: str) -> bool:
    token = str(raw_url or "").strip()
    if not token:
        return False
    lowered = token.casefold()
    if lowered.startswith(("/", "./", "../")) and (
        lowered.endswith(".pdf") or ".pdf?" in lowered
    ):
        return True
    if not lowered.startswith("http"):
        return False
    if lowered.endswith(".pdf") or ".pdf?" in lowered:
        return True
    return any(
        marker in lowered
        for marker in (
            "download",
            "document",
            "report",
            "whitepaper",
            "research",
            "study",
            "ebook",
            "insight",
        )
    )


def _resolve_current_page(browser: Any) -> Any:
    try:
        return _maybe_await(browser.get_current_page())
    except Exception:
        return None


def _read_history_final_page_url(history: Any) -> str:
    state = _read_history_final_state(history)
    token = str(getattr(state, "url", "") or "").strip()
    if token in {"", "about:blank"}:
        return ""
    return token


def _read_history_final_page_title(history: Any) -> str:
    state = _read_history_final_state(history)
    return str(getattr(state, "title", "") or "").strip()


def _copy_history_screenshot(*, history: Any, download_dir: Path) -> str:
    state = _read_history_final_state(history)
    source_path = Path(str(getattr(state, "screenshot_path", "") or "").strip())
    if not str(source_path):
        return ""
    if not source_path.exists() or not source_path.is_file():
        return ""
    target_path = download_dir / "terminal_screenshot.png"
    try:
        if source_path.resolve() != target_path.resolve():
            shutil.copy2(source_path, target_path)
        else:
            target_path = source_path
    except OSError:
        return str(source_path)
    return str(target_path)


def _read_history_final_state(history: Any) -> Any:
    entries = getattr(history, "history", None)
    if not isinstance(entries, list) or not entries:
        return None
    last_entry = entries[-1]
    return getattr(last_entry, "state", None)


def _read_history_attachment_paths(history: Any) -> list[str]:
    action_results = getattr(history, "action_results", None)
    if not callable(action_results):
        return []
    attachments: list[str] = []
    seen: set[str] = set()
    try:
        results = action_results()
    except Exception:
        return []
    if not isinstance(results, list):
        return []
    for result in results:
        for raw_path in getattr(result, "attachments", None) or []:
            token = str(raw_path or "").strip()
            if not token or token in seen:
                continue
            seen.add(token)
            attachments.append(token)
    return attachments


def _read_page_url(page: Any) -> str:
    if page is None:
        return ""
    try:
        candidate = getattr(page, "url", "")
        if callable(candidate):
            candidate = _maybe_await(candidate())
    except Exception:
        return ""
    return str(candidate or "").strip()


def _read_browser_current_page_url(browser: Any) -> str:
    candidate = getattr(browser, "get_current_page_url", None)
    if not callable(candidate):
        return ""
    try:
        value = _maybe_await(candidate())
    except Exception:
        return ""
    token = str(value or "").strip()
    if token in {"about:blank", ""}:
        return ""
    return token


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


def _read_browser_current_page_title(browser: Any) -> str:
    candidate = getattr(browser, "get_current_page_title", None)
    if not callable(candidate):
        return ""
    try:
        value = _maybe_await(candidate())
    except Exception:
        return ""
    token = str(value or "").strip()
    if token in {"Unknown page title", ""}:
        return ""
    return token


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
    return str(getattr(page, "html", "") or "")


def _write_terminal_html_snapshot(
    *,
    download_dir: Path,
    final_page_html: str,
) -> str:
    token = str(final_page_html or "")
    if not token.strip():
        return ""
    snapshot_path = download_dir / "terminal_snapshot.html"
    try:
        snapshot_path.write_text(token, encoding="utf-8")
    except OSError:
        return ""
    return str(snapshot_path)


def _write_terminal_screenshot(
    *,
    browser: Any,
    page: Any,
    download_dir: Path,
    ctx: RunContext,
    normalized_url: str,
) -> str:
    screenshot_path = download_dir / "terminal_screenshot.png"
    result = browser_helper_capture_screenshot(
        browser=browser,
        page=page,
        screenshot_path=screenshot_path,
        ctx=ctx,
        normalized_url=normalized_url,
        required=False,
    )
    return result.path if result.status == "ok" else ""


def _try_screenshot_call(*, candidate: Any, screenshot_path: Path) -> bool:
    if not callable(candidate):
        return False
    try:
        result = candidate(path=str(screenshot_path), full_page=True)
        if inspect.isawaitable(result):
            _run_awaitable(result)
    except TypeError:
        try:
            result = candidate(str(screenshot_path))
            if inspect.isawaitable(result):
                _run_awaitable(result)
        except Exception:
            return False
    except Exception:
        return False
    return screenshot_path.exists()


def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return _await_in_current_or_thread(value)
    return value


async def _await_browser_task(awaitable: Any) -> Any:
    return await awaitable


def _await_in_current_or_thread(
    awaitable: Any,
    *,
    timeout_seconds: float | None = None,
) -> Any:
    payload: dict[str, Any] = {}
    errors: list[Exception] = []

    def runner() -> None:
        try:
            payload["result"] = asyncio.run(_await_browser_task(awaitable))
        except Exception as exc:  # pragma: no cover - defensive thread bridge
            errors.append(exc)

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        if timeout_seconds is None:
            return asyncio.run(_await_browser_task(awaitable))
        thread = Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout_seconds)
        if thread.is_alive():
            raise TimeoutError("awaitable execution timed out")
        if errors:
            raise errors[0]
        return payload.get("result")

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join(timeout_seconds)
    if timeout_seconds is not None and thread.is_alive():
        raise TimeoutError("awaitable execution timed out")
    if errors:
        raise errors[0]
    return payload.get("result")


def _run_awaitable(awaitable: Any, *, timeout_seconds: float | None = None) -> None:
    _await_in_current_or_thread(awaitable, timeout_seconds=timeout_seconds)
