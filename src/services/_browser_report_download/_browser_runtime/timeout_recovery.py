from __future__ import annotations

import asyncio
import inspect
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
    browser_helper_standard_form_submit,
    browser_helper_js,
    browser_helper_page_info,
)
from src.services._browser_report_download.http import (
    download_pdf_from_url,
    is_pdf_file,
)
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
from src.services._browser_report_download._browser_runtime.terminal_assets import (
    _capture_terminal_assets,
    _capture_terminal_dialog_evidence,
    _materialize_external_artifacts,
    _parse_raw_model_response,
    _resolve_current_page,
    _write_terminal_html_snapshot,
)
from src.services._browser_report_download._browser_runtime.terminal_state import (
    _capture_terminal_snapshot,
)

logger = logging.getLogger("market_lense.browser_report_download_service")


def _salvage_timed_out_browser_run(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
) -> BrowserAgentRunResult | None:
    payload: dict[str, BrowserAgentRunResult | None] = {}
    cached_result = _build_cached_timed_out_browser_run(
        request=request,
        browser=browser,
        ctx=ctx,
        normalized_url=normalized_url,
        download_dir=download_dir,
    )

    def runner() -> None:
        payload["result"] = _salvage_timed_out_browser_run_unbounded(
            request=request,
            browser=browser,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
        )

    worker = Thread(target=runner, daemon=True)
    worker.start()
    worker.join(_TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS)
    if worker.is_alive():
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_timeout_recovery_timed_out",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "operation": "terminal_salvage",
                    "timeout_seconds": _TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS,
                },
            )
        )
        return cached_result
    return payload.get("result") or cached_result


def _build_cached_timed_out_browser_run(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
) -> BrowserAgentRunResult | None:
    downloaded_files = [str(path) for path in getattr(browser, "downloaded_files", [])]
    final_page_url = str(getattr(browser, "url", "") or "").strip()
    final_page_title = str(getattr(browser, "title", "") or "").strip()
    final_page_html = str(getattr(browser, "html", "") or "")
    if not (downloaded_files or final_page_title or final_page_html.strip()):
        return None
    route_family = str(request.route_family_hint or "").strip()
    if not downloaded_files and route_family not in {
        "browser_email_form",
        "browser_onsite_report",
        "browser_listing_hub",
        "browser_tracker_redirect",
    }:
        return None
    materialized_paths = _materialize_external_artifacts(
        raw_model_response="",
        attachment_paths=[],
        downloaded_files=downloaded_files,
        download_dir=download_dir,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    for materialized_path in materialized_paths:
        if materialized_path not in downloaded_files:
            downloaded_files.append(materialized_path)
    html_snapshot_path = _write_terminal_html_snapshot(
        download_dir=download_dir,
        final_page_html=final_page_html,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_timeout_cached_state_salvaged",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "downloaded_file_count": len(downloaded_files),
                "final_page_url": final_page_url,
                "final_page_title": final_page_title,
                "has_final_page_html": bool(final_page_html.strip()),
            },
        )
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response="",
        final_page_url=final_page_url,
        final_page_title=final_page_title,
        final_page_html=final_page_html,
        downloaded_files=downloaded_files,
        attachment_paths=[],
        network_resource_urls=[],
        network_events=[],
        html_snapshot_path=html_snapshot_path,
        screenshot_path="",
        print_pdf_capture_path="",
        print_pdf_capture_provenance="",
        dialog_evidence=[],
    )


def _salvage_timed_out_browser_run_unbounded(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    download_dir: Path,
) -> BrowserAgentRunResult | None:
    downloaded_files = [str(path) for path in getattr(browser, "downloaded_files", [])]
    final_page_url = ""
    final_page_title = ""
    final_page_html = ""
    network_resource_urls: list[str] = []
    network_events: list[BrowserDownloadNetworkEvent] = []
    dialog_evidence: list[BrowserDownloadDialogEvidence] = []
    html_snapshot_path = ""
    screenshot_path = ""
    try:
        dialog_evidence.extend(
            _capture_terminal_dialog_evidence(
                browser=browser,
                ctx=ctx,
                normalized_url=normalized_url,
                allow_beforeunload=False,
            )
        )
        terminal_snapshot = _capture_terminal_snapshot(
            browser,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        final_page_url = terminal_snapshot.url
        final_page_title = terminal_snapshot.title
        final_page_html = terminal_snapshot.html
        current_page = terminal_snapshot.page
        if current_page is not None:
            (
                network_resource_urls,
                network_events,
                html_snapshot_path,
                screenshot_path,
            ) = _capture_terminal_assets(
                browser=browser,
                page=current_page,
                download_dir=download_dir,
                final_page_url=final_page_url,
                final_page_html=final_page_html,
                route_family=request.route_family_hint or "",
                ctx=ctx,
                normalized_url=normalized_url,
            )
    except Exception:
        if not downloaded_files:
            return None
    if not (downloaded_files or final_page_title or final_page_html.strip()):
        return None
    route_family = str(request.route_family_hint or "").strip()
    if not downloaded_files and route_family not in {
        "browser_email_form",
        "browser_onsite_report",
        "browser_listing_hub",
        "browser_tracker_redirect",
    }:
        return None
    materialized_paths = _materialize_external_artifacts(
        raw_model_response="",
        attachment_paths=[],
        downloaded_files=downloaded_files,
        download_dir=download_dir,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    for materialized_path in materialized_paths:
        if materialized_path not in downloaded_files:
            downloaded_files.append(materialized_path)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_timeout_terminal_state_salvaged",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "downloaded_file_count": len(downloaded_files),
                "final_page_url": final_page_url,
                "final_page_title": final_page_title,
                "has_final_page_html": bool(final_page_html.strip()),
            },
        )
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response="",
        final_page_url=final_page_url,
        final_page_title=final_page_title,
        final_page_html=final_page_html,
        downloaded_files=downloaded_files,
        attachment_paths=[],
        network_resource_urls=network_resource_urls,
        network_events=network_events,
        html_snapshot_path=html_snapshot_path,
        screenshot_path=screenshot_path,
        print_pdf_capture_path="",
        print_pdf_capture_provenance="",
        dialog_evidence=dialog_evidence,
    )


def _should_attempt_lookup_submission_assist(
    *,
    request: BrowserReportDownloadRequest,
    raw_model_response: str,
) -> bool:
    if str(request.route_family_hint or "").strip() != "browser_email_form":
        return False
    payload = _parse_raw_model_response(raw_model_response)
    if str(payload.get("route_kind") or "").strip() != "email_delivery":
        return False
    if (
        normalize_optional_bool_signal(payload.get("email_submission_completed"))
        is True
    ):
        return True
    if normalize_optional_bool_signal(payload.get("confirmation_url_changed")) is True:
        return False
    if normalize_optional_bool_signal(payload.get("form_disappeared")) is True:
        return False
    return _payload_has_lookup_submission_recovery_signal(payload)


def _payload_has_lookup_submission_recovery_signal(payload: dict[str, Any]) -> bool:
    lookup_fields = {
        "location",
        "country",
        "state",
        "province",
        "region",
        "territory",
    }
    encountered_fields = {
        str(item or "").strip().lower()
        for item in payload.get("encountered_form_fields", [])
        if str(item or "").strip()
    }
    if not any(
        any(marker in field for marker in lookup_fields) for field in encountered_fields
    ):
        return False
    for step in payload.get("route_steps", []):
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").strip().lower()
        target_text = str(step.get("target_text") or "").strip().lower()
        result = str(step.get("result") or "").strip().lower()
        if action == "click" and "submit" in " ".join([target_text, result]):
            return True
    blocked_reason = str(payload.get("blocked_reason") or "").strip().lower()
    blocked_reason_detail = (
        str(payload.get("blocked_reason_detail") or "").strip().lower()
    )
    blocked_text = " ".join([blocked_reason, blocked_reason_detail])
    return any(marker in blocked_text for marker in lookup_fields)


def _should_attempt_standard_form_submit_assist(
    *,
    request: BrowserReportDownloadRequest,
    raw_model_response: str,
) -> bool:
    if str(request.route_family_hint or "").strip() != "browser_email_form":
        return False
    payload = _parse_raw_model_response(raw_model_response)
    if str(payload.get("route_kind") or "").strip() != "email_delivery":
        return False
    if normalize_optional_bool_signal(payload.get("confirmation_url_changed")) is True:
        return False
    if normalize_optional_bool_signal(payload.get("form_disappeared")) is True:
        return False
    return _payload_has_standard_form_submit_recovery_signal(payload)


def _should_attempt_timeout_standard_form_submit_assist(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    raw_model_response: str,
) -> bool:
    if _should_attempt_standard_form_submit_assist(
        request=request,
        raw_model_response=raw_model_response,
    ):
        return True
    if str(request.route_family_hint or "").strip() != "browser_email_form":
        return False
    html = str(getattr(browser, "html", "") or "").casefold()
    if not html:
        return False
    if any(marker in html for marker in _EMAIL_DOMAIN_FAILURE_MARKERS):
        return False
    has_form_control = any(
        marker in html
        for marker in ("<form", "<input", "<select", "<textarea", "checkbox")
    )
    has_submit_control = any(
        marker in html
        for marker in ("type=\"submit\"", "type='submit'", ">submit<", "submit")
    )
    return has_form_control and has_submit_control


def _payload_has_standard_form_submit_recovery_signal(payload: dict[str, Any]) -> bool:
    text_parts: list[str] = [
        str(payload.get("route_summary") or ""),
        str(payload.get("blocked_reason") or ""),
        str(payload.get("blocked_reason_detail") or ""),
    ]
    for item in payload.get("encountered_form_fields", []):
        text_parts.append(str(item or ""))
    submitted = False
    for step in payload.get("route_steps", []):
        if not isinstance(step, dict):
            continue
        action = str(step.get("action") or "").strip().casefold()
        target_text = str(step.get("target_text") or "")
        result = str(step.get("result") or "")
        text_parts.extend([target_text, result])
        if action == "click" and "submit" in " ".join([target_text, result]).casefold():
            submitted = True
    joined = " ".join(text_parts).casefold()
    relevant_markers = (
        "country",
        "industry",
        "department",
        "role",
        "job title",
        "company",
        "email",
        "privacy",
        "terms",
        "policy",
        "agree",
        "agreement",
        "checkbox",
        "select",
        "required",
        "unchecked",
        "unselected",
    )
    blocked_reason = str(payload.get("blocked_reason") or "").strip().casefold()
    return any(marker in joined for marker in relevant_markers) and (
        submitted
        or blocked_reason
        in {"blocked_unknown_required_enum", "blocked_missing_identity_field"}
    )


def _attempt_standard_form_submit_assist(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
) -> bool:
    page = _resolve_current_page(browser)
    if page is None:
        return False
    field_values = _browser_standard_form_identity_field_values(request)
    if not field_values:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_standard_form_assist_skipped",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "reason": "no_identity_fields",
                },
            )
        )
        return False
    helper_result = browser_helper_standard_form_submit(
        page=page,
        field_values=field_values,
        ctx=ctx,
        normalized_url=normalized_url,
        browser=browser,
    )
    if helper_result.status == "blocked":
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_standard_form_assist_blocked",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "blocker_code": helper_result.blocker_code or "",
                    "unresolved_fields": list(helper_result.unresolved_fields),
                    "attempted_count": helper_result.attempted_count,
                },
            )
        )
        return False
    if helper_result.status != "ok" or not helper_result.submitted:
        return False
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_standard_form_assist_applied",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "filled_count": helper_result.filled_count,
                "selected_count": helper_result.selected_count,
                "mandatory_agreement_checked_count": (
                    helper_result.mandatory_agreement_checked_count
                ),
                "submitted": helper_result.submitted,
                "final_url": helper_result.final_url,
                "resolved_fields": list(helper_result.resolved_fields),
            },
        )
    )
    return True


def _browser_standard_form_identity_field_values(
    request: BrowserReportDownloadRequest,
) -> list[dict[str, object]]:
    delivery_email = str(resolve_delivery_email_value(request) or "").strip()
    values: list[dict[str, object]] = []
    for field in resolve_effective_identity_fields(request):
        token = str(field.value or "").strip()
        if field.key == "work_email" and delivery_email:
            token = delivery_email
        if not token:
            continue
        values.append(
            {
                "key": field.key,
                "label": field.label,
                "value": token,
                "aliases": list(field.aliases),
                "option_aliases": list(field.option_aliases),
            }
        )
    if delivery_email and not any(
        str(item.get("key") or "") == "work_email" for item in values
    ):
        values.append(
            {
                "key": "work_email",
                "label": "Work email",
                "value": delivery_email,
                "aliases": ["email", "email address", "business email", "work email"],
                "option_aliases": [],
            }
        )
    return values[:40]


def _attempt_lookup_submission_assist(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    raw_model_response: str = "",
) -> bool:
    page = _resolve_current_page(browser)
    if page is None:
        return False
    lookup_labels = _lookup_submission_assist_target_labels(
        _parse_raw_model_response(raw_model_response)
    )
    field_values = _browser_form_identity_field_values(
        request,
        lookup_labels=lookup_labels,
    )
    if (
        not field_values
        and normalize_optional_bool_signal(
            _parse_raw_model_response(raw_model_response).get(
                "email_submission_completed"
            )
        )
        is True
    ):
        field_values = _browser_standard_form_identity_field_values(request)
    if not field_values:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_lookup_submission_assist_skipped",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "reason": "no_matching_identity_fields",
                    "lookup_labels": list(lookup_labels),
                },
            )
        )
        return False
    autocomplete_result = browser_helper_form_autocomplete(
        page=page,
        field_values=field_values,
        ctx=ctx,
        normalized_url=normalized_url,
        submit=True,
        browser=browser,
    )
    if autocomplete_result.status == "blocked":
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_lookup_autocomplete_blocked",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "blocker_code": autocomplete_result.blocker_code or "",
                    "unresolved_fields": list(autocomplete_result.unresolved_fields),
                    "attempted_count": autocomplete_result.attempted_count,
                },
            )
        )
        return False
    if autocomplete_result.status != "ok" or autocomplete_result.selected_count <= 0:
        return False
    if not autocomplete_result.submitted:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_lookup_submission_assist_incomplete",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "selected_count": autocomplete_result.selected_count,
                    "submitted": autocomplete_result.submitted,
                    "final_url": autocomplete_result.final_url,
                },
            )
        )
        return False
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_lookup_submission_assist_applied",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "selected_count": autocomplete_result.selected_count,
                "selected_fields": list(autocomplete_result.selected_fields),
                "submitted": autocomplete_result.submitted,
                "final_url": autocomplete_result.final_url,
            },
        )
    )
    return True


def _lookup_submission_assist_target_labels(payload: dict[str, Any]) -> tuple[str, ...]:
    labels: list[str] = []
    marker_pattern = re.compile(
        r"\b(country|location|state|province|region|territory)\b",
        re.IGNORECASE,
    )
    for item in payload.get("encountered_form_fields", []):
        label = str(item or "").strip()
        if label and marker_pattern.search(label):
            labels.append(label)
    blocked_detail = str(payload.get("blocked_reason_detail") or "").strip()
    if blocked_detail:
        for match in re.finditer(
            r"\b(country|location|state|province|region|territory)\b",
            blocked_detail,
            re.IGNORECASE,
        ):
            labels.append(match.group(1))
    normalized: list[str] = []
    seen: set[str] = set()
    for label in labels:
        token = re.sub(r"\s+", " ", label).strip().casefold()
        if not token or token in seen:
            continue
        seen.add(token)
        normalized.append(label)
    return tuple(normalized)


def _browser_form_identity_field_values(
    request: BrowserReportDownloadRequest,
    *,
    lookup_labels: tuple[str, ...] = (),
) -> list[dict[str, object]]:
    values: list[dict[str, object]] = []
    lookup_markers = (
        "country",
        "location",
        "state",
        "province",
        "region",
        "territory",
    )
    lookup_label_markers = tuple(
        marker
        for raw_label in lookup_labels
        for marker in lookup_markers
        if marker in str(raw_label or "").strip().casefold()
    )
    for field in resolve_effective_identity_fields(request):
        token = str(field.value or "").strip()
        if not token:
            continue
        searchable_tokens = " ".join(
            [
                str(field.key or ""),
                str(field.label or ""),
                *(str(alias or "") for alias in field.aliases),
            ]
        ).casefold()
        if not any(
            marker in searchable_tokens
            for marker in lookup_markers
        ):
            continue
        if (
            lookup_label_markers
            and "location" not in lookup_label_markers
            and not any(marker in searchable_tokens for marker in lookup_label_markers)
        ):
            continue
        values.append(
            {
                "key": field.key,
                "label": field.label,
                "value": token,
                "aliases": list(field.aliases),
                "option_aliases": list(field.option_aliases),
            }
        )
    if not values and lookup_labels:
        values.append(
            {
                "key": "country",
                "label": "Country",
                "value": "Austria",
                "aliases": ["country", "location", "region"],
                "option_aliases": ["Austria"],
            }
        )
    return values[:12]


def _attempt_lookup_submission_assist_with_timeout(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
    raw_model_response: str = "",
) -> bool:
    payload: dict[str, bool] = {}

    def runner() -> None:
        payload["result"] = _attempt_lookup_submission_assist(
            request=request,
            browser=browser,
            ctx=ctx,
            normalized_url=normalized_url,
            raw_model_response=raw_model_response,
        )

    worker = Thread(target=runner, daemon=True)
    worker.start()
    worker.join(_TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS)
    if worker.is_alive():
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_timeout_recovery_timed_out",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "operation": "lookup_submission_assist",
                    "timeout_seconds": _TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS,
                },
            )
        )
        return False
    return normalize_optional_bool_signal(payload.get("result")) is True


def _attempt_standard_form_submit_assist_with_timeout(
    *,
    request: BrowserReportDownloadRequest,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
) -> bool:
    payload: dict[str, bool] = {}

    def runner() -> None:
        payload["result"] = _attempt_standard_form_submit_assist(
            request=request,
            browser=browser,
            ctx=ctx,
            normalized_url=normalized_url,
        )

    worker = Thread(target=runner, daemon=True)
    worker.start()
    worker.join(_TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS)
    if worker.is_alive():
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_timeout_recovery_timed_out",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "operation": "standard_form_submit_assist",
                    "timeout_seconds": _TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS,
                },
            )
        )
        return False
    return normalize_optional_bool_signal(payload.get("result")) is True
