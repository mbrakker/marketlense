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
    _collect_network_events,
    _collect_network_resource_urls,
    _looks_like_documentish_url,
    _parse_raw_model_response,
    _resolve_current_page,
)

logger = logging.getLogger("market_lense.browser_report_download_service")


@dataclass(frozen=True)
class TerminalSnapshot:
    page: Any
    url: str
    title: str
    html: str


@dataclass(frozen=True)
class TerminalStabilizationPolicy:
    route_family: str
    route_kind: str
    min_quorum_signals: int
    poll_schedule_seconds: tuple[float, ...]


@dataclass(frozen=True)
class TerminalQuorumAssessment:
    route_family: str
    route_kind: str
    signal_labels: list[str]
    transient_labels: list[str]
    signal_count: int
    network_event_count: int
    document_url_count: int
    terminal_key: str


def _capture_terminal_snapshot(
    browser: Any,
    *,
    ctx: RunContext,
    normalized_url: str,
) -> TerminalSnapshot:
    page = _resolve_current_page(browser)
    page_info = browser_helper_page_info(
        browser=browser,
        page=page,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    return TerminalSnapshot(
        page=page,
        url=page_info.url,
        title=page_info.title,
        html=page_info.html,
    )


def _stabilize_terminal_snapshot(
    *,
    browser: Any,
    raw_model_response: str,
    route_family_hint: str | None,
    snapshot: TerminalSnapshot,
    ctx: RunContext,
    normalized_url: str,
    trigger_reason: str | None = None,
) -> TerminalSnapshot:
    payload = _parse_raw_model_response(raw_model_response)
    policy = _resolve_terminal_stabilization_policy(
        payload=payload,
        route_family_hint=route_family_hint,
    )
    stabilized_snapshot = snapshot
    final_assessment = _assess_terminal_snapshot_quorum(
        browser=browser,
        snapshot=stabilized_snapshot,
        payload=payload,
        policy=policy,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    reason = trigger_reason or _terminal_stabilization_reason(
        raw_model_response=raw_model_response,
        snapshot=stabilized_snapshot,
    )
    previous_assessment: TerminalQuorumAssessment | None = None
    stable_repeat_observations = 1
    attempts = 0
    for poll_delay_seconds in policy.poll_schedule_seconds:
        if _assessment_meets_terminal_quorum(
            policy=policy,
            assessment=final_assessment,
            previous_assessment=previous_assessment,
        ):
            break
        attempts += 1
        time.sleep(poll_delay_seconds)
        candidate = _capture_terminal_snapshot(
            browser,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        stabilized_snapshot = _merge_terminal_snapshots(
            previous=stabilized_snapshot,
            candidate=candidate,
        )
        previous_assessment = final_assessment
        final_assessment = _assess_terminal_snapshot_quorum(
            browser=browser,
            snapshot=stabilized_snapshot,
            payload=payload,
            policy=policy,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        if (
            previous_assessment is not None
            and previous_assessment.terminal_key == final_assessment.terminal_key
        ):
            stable_repeat_observations += 1
        else:
            stable_repeat_observations = 1
        if not reason:
            reason = "quorum_not_met"
    quorum_met = _assessment_meets_terminal_quorum(
        policy=policy,
        assessment=final_assessment,
        previous_assessment=previous_assessment,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_terminal_state_assessed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "stabilization_reason": reason or "initial_quorum_met",
                "trigger_reason": trigger_reason or "",
                "route_family": policy.route_family,
                "route_kind": policy.route_kind,
                "attempts": attempts,
                "quorum_met": quorum_met,
                "quorum_signal_count": final_assessment.signal_count,
                "quorum_signal_labels": final_assessment.signal_labels,
                "quorum_transient_labels": final_assessment.transient_labels,
                "stable_repeat_observations": stable_repeat_observations,
                "quorum_network_event_count": final_assessment.network_event_count,
                "quorum_document_url_count": final_assessment.document_url_count,
                "poll_schedule_seconds": list(policy.poll_schedule_seconds),
                "wait_strategy": "bounded_browser_boundary_polling",
                "final_url": stabilized_snapshot.url,
                "final_title": stabilized_snapshot.title,
                "final_html_size": len(stabilized_snapshot.html),
            },
        )
    )
    return stabilized_snapshot


def _terminal_stabilization_reason(
    *,
    raw_model_response: str,
    snapshot: TerminalSnapshot,
) -> str:
    payload = _parse_raw_model_response(raw_model_response)
    email_submission_completed = (
        normalize_optional_bool_signal(payload.get("email_submission_completed"))
        is True
    )
    post_submit_message = str(payload.get("post_submit_message") or "").strip()
    submit_button_state = str(payload.get("submit_button_state") or "").strip().lower()
    snapshot_transient = _contains_transient_terminal_marker(
        " ".join([snapshot.title, snapshot.html])
    )
    if email_submission_completed and (
        _contains_transient_terminal_marker(post_submit_message)
        or submit_button_state == "disabled"
        or snapshot_transient
    ):
        return "transient_submit_state"
    if email_submission_completed and not snapshot.html.strip():
        return "empty_terminal_html_after_submit"
    return ""


def _resolve_terminal_stabilization_policy(
    *,
    payload: dict[str, Any],
    route_family_hint: str | None,
) -> TerminalStabilizationPolicy:
    route_kind = str(payload.get("route_kind") or "").strip()
    route_family = str(payload.get("route_family") or route_family_hint or "").strip()
    if route_kind == "email_delivery" or route_family == "browser_email_form":
        return TerminalStabilizationPolicy(
            route_family="browser_email_form",
            route_kind=route_kind or "email_delivery",
            min_quorum_signals=2,
            poll_schedule_seconds=_TERMINAL_STABILIZATION_EMAIL_POLL_SCHEDULE_SECONDS,
        )
    if route_kind == "onsite_report" or route_family in {
        "browser_onsite_report",
        "browser_listing_hub",
    }:
        return TerminalStabilizationPolicy(
            route_family=route_family or "browser_onsite_report",
            route_kind=route_kind or "onsite_report",
            min_quorum_signals=2,
            poll_schedule_seconds=_TERMINAL_STABILIZATION_DEFAULT_POLL_SCHEDULE_SECONDS,
        )
    return TerminalStabilizationPolicy(
        route_family=route_family or "browser_pdf_click",
        route_kind=route_kind or "pdf_download",
        min_quorum_signals=1,
        poll_schedule_seconds=_TERMINAL_STABILIZATION_DEFAULT_POLL_SCHEDULE_SECONDS,
    )


def _assess_terminal_snapshot_quorum(
    *,
    browser: Any,
    snapshot: TerminalSnapshot,
    payload: dict[str, Any],
    policy: TerminalStabilizationPolicy,
    ctx: RunContext,
    normalized_url: str,
) -> TerminalQuorumAssessment:
    signal_labels: list[str] = []
    transient_labels: list[str] = []
    route_text = _terminal_quorum_text(snapshot)
    lowered_route_text = route_text.casefold()
    lowered_url = str(snapshot.url or "").strip().casefold()
    network_events = _collect_network_events(
        browser=browser,
        page=snapshot.page,
        route_family=policy.route_family,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    document_urls = _collect_network_resource_urls(
        page=snapshot.page,
        final_page_html=snapshot.html,
        network_events=network_events,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    submit_button_state = (
        str(payload.get("submit_button_state") or "").strip().casefold()
    )
    post_submit_message = str(payload.get("post_submit_message") or "").strip()
    email_submission_completed = (
        normalize_optional_bool_signal(payload.get("email_submission_completed"))
        is True
    )
    confirmation_url_changed = (
        normalize_optional_bool_signal(payload.get("confirmation_url_changed")) is True
    )
    form_disappeared = (
        normalize_optional_bool_signal(payload.get("form_disappeared")) is True
    )
    downloaded_files = [
        str(path or "").strip()
        for path in getattr(browser, "downloaded_files", []) or []
        if str(path or "").strip()
    ]
    if _contains_transient_terminal_marker(post_submit_message):
        transient_labels.append("post_submit_message_transient")
    if submit_button_state == "disabled":
        transient_labels.append("submit_button_disabled")
    if _contains_transient_terminal_marker(lowered_route_text):
        transient_labels.append("page_text_transient")
    if policy.route_family == "browser_email_form":
        if confirmation_url_changed or any(
            marker in lowered_url for marker in _TERMINAL_SUCCESS_URL_MARKERS
        ):
            signal_labels.append("success_url")
        if any(
            marker in lowered_route_text for marker in _TERMINAL_SUCCESS_TEXT_MARKERS
        ):
            signal_labels.append("success_text")
        if any(event.signal_kind == "confirmation_request" for event in network_events):
            signal_labels.append("network_confirmation_request")
        if any(event.signal_kind == "submission_request" for event in network_events):
            signal_labels.append("network_submission_request")
        if form_disappeared or (
            email_submission_completed and "<form" not in snapshot.html.casefold()
        ):
            signal_labels.append("form_disappeared")
        if any(
            label in signal_labels
            for label in (
                "success_url",
                "success_text",
                "network_confirmation_request",
                "form_disappeared",
            )
        ):
            transient_labels = [
                label
                for label in transient_labels
                if label
                not in {"post_submit_message_transient", "submit_button_disabled"}
            ]
    elif policy.route_kind == "onsite_report" or policy.route_family in {
        "browser_onsite_report",
        "browser_listing_hub",
    }:
        if len(lowered_route_text) >= 400:
            signal_labels.append("onsite_html_body")
        if any(
            marker in lowered_route_text for marker in _TERMINAL_REPORT_TEXT_MARKERS
        ):
            signal_labels.append("onsite_report_text")
        if any(
            event.signal_kind in {"navigation_request", "document_request"}
            for event in network_events
        ):
            signal_labels.append("terminal_navigation")
    else:
        if downloaded_files:
            signal_labels.append("downloaded_file_present")
        if any(event.signal_kind == "document_request" for event in network_events):
            signal_labels.append("network_document_request")
        if any(_looks_like_documentish_url(url) for url in document_urls):
            signal_labels.append("document_url_observed")
        if lowered_url.endswith(".pdf") or ".pdf?" in lowered_url:
            signal_labels.append("final_pdf_url")
    terminal_key = sha256(
        json.dumps(
            {
                "url": str(snapshot.url or "").strip(),
                "title": str(snapshot.title or "").strip(),
                "text_excerpt": route_text[-_TERMINAL_TEXT_EXCERPT_MAX_CHARS:],
            },
            ensure_ascii=True,
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()[:16]
    return TerminalQuorumAssessment(
        route_family=policy.route_family,
        route_kind=policy.route_kind,
        signal_labels=_dedupe_labels(signal_labels),
        transient_labels=_dedupe_labels(transient_labels),
        signal_count=len(_dedupe_labels(signal_labels)),
        network_event_count=len(network_events),
        document_url_count=len(document_urls),
        terminal_key=terminal_key,
    )


def _assessment_meets_terminal_quorum(
    *,
    policy: TerminalStabilizationPolicy,
    assessment: TerminalQuorumAssessment,
    previous_assessment: TerminalQuorumAssessment | None,
) -> bool:
    if assessment.transient_labels:
        return False
    if assessment.signal_count >= policy.min_quorum_signals:
        return True
    if previous_assessment is None:
        return False
    return (
        assessment.terminal_key == previous_assessment.terminal_key
        and assessment.signal_count >= max(1, policy.min_quorum_signals - 1)
    )


def _terminal_quorum_text(snapshot: TerminalSnapshot) -> str:
    html = str(snapshot.html or "")
    sanitized = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    sanitized = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", sanitized)
    sanitized = re.sub(r"(?is)<[^>]+>", " ", sanitized)
    combined = " ".join([str(snapshot.title or "").strip(), sanitized])
    return re.sub(r"\s+", " ", combined).strip()


def _dedupe_labels(labels: list[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw_label in labels:
        label = str(raw_label or "").strip()
        if not label or label in seen:
            continue
        seen.add(label)
        normalized.append(label)
    return normalized


def _contains_transient_terminal_marker(text: str) -> bool:
    token = str(text or "").strip().casefold()
    if not token:
        return False
    for marker in _TERMINAL_TRANSIENT_MARKERS:
        escaped_marker = re.escape(marker)
        if " " in marker:
            pattern = rf"(?<![a-z0-9]){escaped_marker}(?![a-z0-9])"
        else:
            pattern = rf"\b{escaped_marker}\b"
        if re.search(pattern, token):
            return True
    return False


def _merge_terminal_snapshots(
    *,
    previous: TerminalSnapshot,
    candidate: TerminalSnapshot,
) -> TerminalSnapshot:
    html = previous.html
    candidate_html = str(candidate.html or "")
    if candidate_html.strip() and (
        not html.strip()
        or len(candidate_html) >= len(html)
        or (
            _contains_transient_terminal_marker(html)
            and not _contains_transient_terminal_marker(candidate_html)
        )
    ):
        html = candidate_html
    return TerminalSnapshot(
        page=candidate.page if candidate.page is not None else previous.page,
        url=str(candidate.url or "").strip() or previous.url,
        title=str(candidate.title or "").strip() or previous.title,
        html=html,
    )
