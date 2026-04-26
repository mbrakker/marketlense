from __future__ import annotations

import asyncio
import inspect
import json
import logging
import os
import psutil
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

from src.contracts.browser_download import (
    BrowserDownloadNetworkEvent,
    BrowserReportDownloadRequest,
)
from src.contracts.run_context import RunContext
from src.services._browser_report_download.artifact import BrowserUseAgentResult
from src.services._browser_report_download.http import (
    download_pdf_from_url,
    is_pdf_file,
)
from src.services._browser_report_download.prompt import BrowserDownloadPromptBundle
from src.utils.coercion import normalize_optional_bool_signal
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

_TERMINAL_TRANSIENT_MARKERS = (
    "please wait",
    "submitting",
    "processing",
    "loading",
    "one moment",
)
_TERMINAL_SUCCESS_URL_MARKERS = ("thank", "success", "confirm", "complete", "done")
_TERMINAL_SUCCESS_TEXT_MARKERS = (
    "thank you",
    "thanks for",
    "request received",
    "submission received",
    "download link",
    "check your email",
    "emailed",
    "sent to your email",
)
_TERMINAL_REPORT_TEXT_MARKERS = (
    "report",
    "research",
    "insight",
    "analysis",
    "survey",
    "outlook",
    "white paper",
    "whitepaper",
)
_TERMINAL_TEXT_EXCERPT_MAX_CHARS = 600
_TERMINAL_STABILIZATION_DEFAULT_POLL_SCHEDULE_SECONDS = (0.25, 0.5, 1.0)
_TERMINAL_STABILIZATION_EMAIL_POLL_SCHEDULE_SECONDS = (0.25, 0.5, 1.0, 1.5)
_AGENT_RUN_TIMEOUT_MIN_BUFFER_SECONDS = 1.0
_AGENT_RUN_TIMEOUT_STEP_BUFFER_SECONDS = 0.5
_AGENT_RUN_TIMEOUT_MAX_BUFFER_SECONDS = 30.0
_BROWSER_KILL_TIMEOUT_SECONDS = 15.0
_BROWSER_RESET_TIMEOUT_SECONDS = 10.0
_BROWSER_CLEANUP_GRACE_SECONDS = 5.0
_BROWSER_PROFILE_DIR_PREFIX = "browser-use-user-data-dir-profile"
_BROWSER_USE_TEMP_DIR_PATTERNS = (
    "browser-use-user-data-dir-*",
    "browser-use-downloads-*",
    "browseruse-tmp-*",
)
_STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS = 15 * 60.0
_TEMP_CLEANUP_LOG_SAMPLE_LIMIT = 5
_TIMED_OUT_COMPLETED_HISTORY_GRACE_SECONDS = 2.0
_TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS = 5.0
_AGENT_COMPLETED_HISTORY_POLL_SECONDS = 0.25
_BROWSER_AGENT_WORKER_ENV = "MARKET_LENSE_BROWSER_AGENT_WORKER"
# Let the worker finish its own timeout stop/cleanup path and write a typed
# response instead of being killed by the outer subprocess envelope mid-exit.
_BROWSER_AGENT_WORKER_TIMEOUT_BUFFER_SECONDS = 45.0
_BROWSER_AGENT_WORKER_OUTPUT_MAX_CHARS = 1200
_ANSI_ESCAPE_PATTERN = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_BROWSER_AGENT_USE_JUDGE = False
_LOOKUP_FIELD_MARKERS = (
    "location",
    "country",
    "state",
    "province",
    "region",
    "territory",
)
_LOOKUP_FAILURE_MARKERS = (
    "could not",
    "did not",
    "failed",
    "failure",
    "incorrect",
    "not correctly",
    "not processed",
    "not resolve",
    "not selected",
    "not work",
    "unsuccessful",
    "unverified",
)
_LOOKUP_SUBMIT_MARKERS = (
    "submit",
    "submitted",
    "submission",
)
_EMAIL_DOMAIN_BLOCK_MARKERS = (
    "business email",
    "work email",
    "corporate email",
    "company email",
    "professional email",
    "valid business email",
)
_EMAIL_DOMAIN_FAILURE_MARKERS = (
    "email error",
    "email address error",
    "invalid email",
    "not a business email",
    "not a work email",
    "not a corporate email",
    "not a professional email",
    "requires a business email",
    "require a business email",
    "please use a business email",
    "please enter a business email",
    "rejected",
)
_PARTIAL_HISTORY_TEXT_MAX_CHARS = 12000


@dataclass(frozen=True)
class BrowserAgentRunResult:
    schema_version: str
    raw_model_response: str
    final_page_url: str
    final_page_title: str
    final_page_html: str
    downloaded_files: list[str]
    attachment_paths: list[str]
    network_resource_urls: list[str]
    network_events: list[BrowserDownloadNetworkEvent]
    html_snapshot_path: str
    screenshot_path: str


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


@dataclass(frozen=True)
class BrowserAgentWorkerPayload:
    schema_version: str
    request: dict[str, Any]
    ctx: dict[str, Any]
    normalized_url: str
    execution_url: str
    download_dir: str
    prompt_bundle: dict[str, Any]


@dataclass(frozen=True)
class BrowserAgentWorkerResponse:
    schema_version: str
    status: str
    result: dict[str, Any] | None
    error: dict[str, Any] | None


@dataclass(frozen=True)
class BrowserAgentHistoryResult:
    history: Any
    salvaged_completed_history: bool


@dataclass(frozen=True)
class _SyntheticHistoryState:
    url: str
    title: str
    screenshot_path: str | None = None


@dataclass(frozen=True)
class _SyntheticHistoryEntry:
    state: _SyntheticHistoryState


@dataclass(frozen=True)
class _SyntheticActionResult:
    attachments: list[str]


class _SyntheticAgentHistory:
    def __init__(
        self,
        *,
        payload: dict[str, Any],
        state: _SyntheticHistoryState,
    ) -> None:
        self._payload = payload
        self.history = [_SyntheticHistoryEntry(state=state)]

    def is_done(self) -> bool:
        return True

    def final_result(self) -> str:
        return json.dumps(self._payload, ensure_ascii=True)

    def action_results(self) -> list[_SyntheticActionResult]:
        return [_SyntheticActionResult(attachments=[])]


def run_browser_report_download_agent(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    prompt_bundle: BrowserDownloadPromptBundle,
) -> BrowserAgentRunResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_request",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "execution_url": execution_url,
                "route_family_hint": request.route_family_hint or "",
                "prompt_namespace": prompt_bundle.namespace,
                "task_prompt": prompt_bundle.task_prompt,
                "agent_use_judge": _BROWSER_AGENT_USE_JUDGE,
            },
        )
    )
    browser_use = _load_browser_use_runtime(normalized_url)
    if _should_run_browser_agent_in_subprocess(browser_use):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_worker_dispatch",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "download_dir": str(download_dir),
                },
            )
        )
        return _run_browser_report_download_agent_subprocess(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            execution_url=execution_url,
            download_dir=download_dir,
            prompt_bundle=prompt_bundle,
        )
    browser: Any | None = None
    _cleanup_stale_browser_use_temp_dirs(ctx=ctx, normalized_url=normalized_url)
    preexisting_temp_dirs = {str(path) for path in _list_browser_use_temp_dirs()}
    _cleanup_managed_browser_profile_dirs(
        download_dir=download_dir,
        ctx=ctx,
        normalized_url=normalized_url,
    )
    profile_dir = _new_managed_browser_profile_dir(download_dir)
    profile_dir.mkdir(parents=True, exist_ok=True)
    raw_model_response = ""
    final_page_url = ""
    final_page_title = ""
    final_page_html = ""
    downloaded_files: list[str] = []
    attachment_paths: list[str] = []
    network_resource_urls: list[str] = []
    network_events: list[BrowserDownloadNetworkEvent] = []
    html_snapshot_path = ""
    screenshot_path = ""
    try:
        browser = browser_use.Browser(
            downloads_path=str(download_dir),
            user_data_dir=str(profile_dir),
            headless=not request.settings.headed,
            auto_download_pdfs=True,
            keep_alive=True,
        )
        llm = browser_use.ChatOpenRouter(
            model=request.settings.model,
            api_key=request.settings.openrouter_api_key,
            http_referer=request.settings.openrouter_http_referer,
            temperature=request.settings.temperature,
            timeout=request.settings.timeout_seconds,
        )
        agent = browser_use.Agent(
            task=prompt_bundle.task_prompt,
            llm=llm,
            browser=browser,
            output_model_schema=BrowserUseAgentResult,
            use_judge=_BROWSER_AGENT_USE_JUDGE,
        )
        history_result = _run_agent_history_with_timeout(
            agent=agent,
            browser=browser,
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        history = history_result.history
        raw_model_response = str(history.final_result() or "").strip()
        history_final_page_url = _read_history_final_page_url(history)
        history_final_page_title = _read_history_final_page_title(history)
        attachment_paths = _read_history_attachment_paths(history)
        history_screenshot_path = _copy_history_screenshot(
            history=history,
            download_dir=download_dir,
        )
        downloaded_files = [
            str(path) for path in getattr(browser, "downloaded_files", [])
        ]
        materialized_paths = _materialize_external_artifacts(
            raw_model_response=raw_model_response,
            attachment_paths=attachment_paths,
            downloaded_files=downloaded_files,
            download_dir=download_dir,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        for materialized_path in materialized_paths:
            if materialized_path not in attachment_paths:
                attachment_paths.append(materialized_path)
            if materialized_path not in downloaded_files:
                downloaded_files.append(materialized_path)
        prefetched_pdf_path = _prefetch_structured_pdf_artifact(
            request=request,
            ctx=ctx,
            normalized_url=normalized_url,
            download_dir=download_dir,
            raw_model_response=raw_model_response,
            history_final_page_url=history_final_page_url,
        )
        if prefetched_pdf_path and prefetched_pdf_path not in downloaded_files:
            downloaded_files.append(prefetched_pdf_path)
        lookup_submission_assisted = False
        if _should_attempt_lookup_submission_assist(
            request=request,
            raw_model_response=raw_model_response,
        ):
            lookup_submission_assisted = _attempt_lookup_submission_assist_with_timeout(
                browser=browser,
                ctx=ctx,
                normalized_url=normalized_url,
            )
        if history_result.salvaged_completed_history and not lookup_submission_assisted:
            final_page_url = history_final_page_url
            final_page_title = history_final_page_title
            screenshot_path = history_screenshot_path
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_completed_history_capture_skipped",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "history_final_page_url": history_final_page_url,
                        "history_final_page_title": history_final_page_title,
                        "downloaded_file_count": len(downloaded_files),
                        "attachment_count": len(attachment_paths),
                    },
                )
            )
        else:
            terminal_snapshot = _capture_terminal_snapshot(browser)
            terminal_snapshot = _stabilize_terminal_snapshot(
                browser=browser,
                raw_model_response=raw_model_response,
                route_family_hint=request.route_family_hint,
                snapshot=terminal_snapshot,
                ctx=ctx,
                normalized_url=normalized_url,
            )
            current_page = terminal_snapshot.page
            final_page_url = terminal_snapshot.url or history_final_page_url
            final_page_title = terminal_snapshot.title or history_final_page_title
            final_page_html = terminal_snapshot.html
            (
                network_resource_urls,
                network_events,
                html_snapshot_path,
                screenshot_path,
            ) = _capture_terminal_assets(
                browser=browser,
                page=current_page,
                download_dir=download_dir,
                final_page_html=final_page_html,
            )
            if not screenshot_path:
                screenshot_path = history_screenshot_path
    except AppError as exc:
        if exc.code == "browser_download_agent_timeout" and browser is not None:
            if _should_attempt_lookup_submission_assist(
                request=request,
                raw_model_response=raw_model_response,
            ):
                _attempt_lookup_submission_assist_with_timeout(
                    browser=browser,
                    ctx=ctx,
                    normalized_url=normalized_url,
                )
            salvaged_run = _salvage_timed_out_browser_run(
                request=request,
                browser=browser,
                ctx=ctx,
                normalized_url=normalized_url,
                download_dir=download_dir,
            )
            if salvaged_run is not None:
                return salvaged_run
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url, "error": exc.message},
            )
        )
        raise
    except Exception as exc:
        if _is_browser_start_timeout_error(exc):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_failed",
                    module=logger.name,
                    fields={"normalized_url": normalized_url, "error": str(exc)},
                )
            )
            raise AppError(
                code="browser_download_browser_start_timeout",
                message="browser-use timed out while starting the local browser session",
                cause=exc,
                retryable=True,
                context={"normalized_url": normalized_url},
            ) from exc
        if _is_no_space_error(exc):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_failed",
                    module=logger.name,
                    fields={"normalized_url": normalized_url, "error": str(exc)},
                )
            )
            raise AppError(
                code="browser_download_storage_full",
                message="The browser download runtime ran out of local disk space",
                cause=exc,
                retryable=True,
                context={"normalized_url": normalized_url},
            ) from exc
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url, "error": str(exc)},
            )
        )
        raise AppError(
            code="browser_download_agent_failed",
            message="browser-use failed to complete the report download task",
            cause=exc,
            retryable=True,
            context={"normalized_url": normalized_url},
        ) from exc
    finally:
        if browser is not None:
            _prepare_browser_for_shutdown(
                browser,
                ctx=ctx,
                normalized_url=normalized_url,
            )
            _kill_browser_with_timeout(
                browser,
                ctx=ctx,
                normalized_url=normalized_url,
            )
        _cleanup_browser_profile_dir(
            profile_dir,
            ctx=ctx,
            normalized_url=normalized_url,
        )
        _cleanup_new_browser_use_temp_dirs(
            ctx=ctx,
            normalized_url=normalized_url,
            preexisting_temp_dirs=preexisting_temp_dirs,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_response",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "raw_model_response": raw_model_response,
                "downloaded_files": downloaded_files,
                "attachment_paths": attachment_paths,
                "browser_final_url": final_page_url,
                "browser_final_title": final_page_title,
                "browser_final_html_size": len(final_page_html),
                "browser_network_resource_url_count": len(network_resource_urls),
                "browser_network_event_count": len(network_events),
                "browser_html_snapshot_path": html_snapshot_path,
                "browser_screenshot_path": screenshot_path,
            },
        )
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response=raw_model_response,
        final_page_url=final_page_url,
        final_page_title=final_page_title,
        final_page_html=final_page_html,
        downloaded_files=downloaded_files,
        attachment_paths=attachment_paths,
        network_resource_urls=network_resource_urls,
        network_events=network_events,
        html_snapshot_path=html_snapshot_path,
        screenshot_path=screenshot_path,
    )


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
    html_snapshot_path = ""
    screenshot_path = ""
    try:
        terminal_snapshot = _capture_terminal_snapshot(browser)
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
                final_page_html=final_page_html,
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


def _attempt_lookup_submission_assist(
    *,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
) -> bool:
    page = _resolve_current_page(browser)
    if page is None:
        return False
    try:
        result = _maybe_await(
            page.evaluate(
                """
                () => {
                  const normalize = (value) => String(value || '').trim().toLowerCase();
                  const isVisible = (node) =>
                    Boolean(node) &&
                    !node.hidden &&
                    node.getClientRects &&
                    node.getClientRects().length > 0;
                  const collectVisibleOptions = (root) => [
                    ...(root || document).querySelectorAll(
                      '.ui-menu-item-wrapper, .ui-menu-item, [role="option"]'
                    ),
                  ].filter((node) => {
                    const text = normalize(node.innerText || node.textContent);
                    return text && isVisible(node);
                  });
                  const lookupBlocks = [...document.querySelectorAll('.lookupFormFieldBlock')];
                  const globalOptions = collectVisibleOptions(document);
                  let selectedCount = 0;
                  for (const block of lookupBlocks) {
                    const input = block.querySelector('input.lookup-behavior');
                    if (!input || !input.required || !normalize(input.value)) {
                      continue;
                    }
                    const options = [
                      ...collectVisibleOptions(block),
                      ...globalOptions,
                    ].filter((node, index, collection) => {
                      if (!node) {
                        return false;
                      }
                      return collection.indexOf(node) === index;
                    });
                    if (!options.length) {
                      continue;
                    }
                    const currentValue = normalize(input.value);
                    const exactMatch =
                      options.find(
                        (node) =>
                          normalize(node.innerText || node.textContent) === currentValue
                      )
                      || (options.length === 1 ? options[0] : null);
                    if (!exactMatch) {
                      continue;
                    }
                    exactMatch.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    exactMatch.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    exactMatch.click();
                    selectedCount += 1;
                  }
                  const submitButton = [
                    ...document.querySelectorAll(
                      'button[type="submit"], input[type="submit"], button'
                    ),
                  ].find((node) => {
                    const text = normalize(
                      node.innerText || node.textContent || node.value || ''
                    );
                    return text === 'submit' || text.includes('submit');
                  });
                  let submitted = false;
                  if (selectedCount > 0 && submitButton) {
                    submitButton.click();
                    submitted = true;
                  }
                  return {
                    acted: selectedCount > 0,
                    selected_count: selectedCount,
                    submitted,
                    final_url: window.location.href,
                  };
                }
                """
            )
        )
    except Exception:
        return False
    if not isinstance(result, dict) or result.get("acted") is not True:
        return False
    _stabilize_terminal_snapshot(
        browser=browser,
        raw_model_response=json.dumps(
            {
                "route_kind": "email_delivery",
                "route_family": "browser_email_form",
                "email_submission_completed": bool(result.get("submitted")),
                "confirmation_url_changed": True,
            },
            ensure_ascii=True,
        ),
        route_family_hint="browser_email_form",
        snapshot=_capture_terminal_snapshot(browser),
        ctx=ctx,
        normalized_url=normalized_url,
        trigger_reason="lookup_submission_assist",
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_lookup_submission_assist_applied",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "selected_count": int(result.get("selected_count") or 0),
                "submitted": bool(result.get("submitted")),
                "final_url": str(result.get("final_url") or "").strip(),
            },
        )
    )
    return True


def _attempt_lookup_submission_assist_with_timeout(
    *,
    browser: Any,
    ctx: RunContext,
    normalized_url: str,
) -> bool:
    payload: dict[str, bool] = {}

    def runner() -> None:
        payload["result"] = _attempt_lookup_submission_assist(
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
                    "operation": "lookup_submission_assist",
                    "timeout_seconds": _TIMED_OUT_RECOVERY_OPERATION_TIMEOUT_SECONDS,
                },
            )
        )
        return False
    return normalize_optional_bool_signal(payload.get("result")) is True


def _should_run_browser_agent_in_subprocess(browser_use: Any) -> bool:
    if os.environ.get(_BROWSER_AGENT_WORKER_ENV) == "1":
        return False
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return False
    return True


def _run_browser_report_download_agent_subprocess(
    *,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    execution_url: str,
    download_dir: Path,
    prompt_bundle: BrowserDownloadPromptBundle,
) -> BrowserAgentRunResult:
    download_dir.mkdir(parents=True, exist_ok=True)
    payload = BrowserAgentWorkerPayload(
        schema_version="1.0",
        request=asdict(request),
        ctx=asdict(ctx),
        normalized_url=normalized_url,
        execution_url=execution_url,
        download_dir=str(download_dir),
        prompt_bundle=asdict(prompt_bundle),
    )
    payload_path = download_dir / "browser_agent_worker_request.json"
    response_path = download_dir / "browser_agent_worker_response.json"
    payload_path.write_text(
        json.dumps(asdict(payload), ensure_ascii=True),
        encoding="utf-8",
    )
    response_path.unlink(missing_ok=True)
    env = dict(os.environ)
    env[_BROWSER_AGENT_WORKER_ENV] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    env.setdefault("NO_COLOR", "1")
    env.setdefault("RICH_DISABLE", "1")
    timeout_seconds = (
        _resolve_agent_run_timeout_seconds(request)
        + _BROWSER_AGENT_WORKER_TIMEOUT_BUFFER_SECONDS
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_worker_start",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "payload_path": str(payload_path),
                "response_path": str(response_path),
                "timeout_seconds": timeout_seconds,
            },
        )
    )
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "src.services._browser_report_download.browser_worker",
                str(payload_path),
                str(response_path),
            ],
            check=False,
            cwd=str(Path.cwd()),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        worker_output_excerpt = _normalize_browser_worker_output_excerpt(
            exc.stdout if isinstance(exc.stdout, str) else ""
        )
        raise AppError(
            code="browser_download_agent_timeout",
            message="browser-use did not return within the configured execution budget",
            cause=exc,
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "timeout_seconds": timeout_seconds,
                "max_steps": request.settings.max_steps,
                "worker_output_excerpt": worker_output_excerpt,
            },
        ) from exc
    worker_output_excerpt = _normalize_browser_worker_output_excerpt(completed.stdout)
    completion_fields: dict[str, Any] = {
        "normalized_url": normalized_url,
        "payload_path": str(payload_path),
        "response_path": str(response_path),
        "return_code": completed.returncode,
        "response_exists": response_path.exists(),
        "worker_output_captured": bool(completed.stdout),
    }
    if worker_output_excerpt:
        completion_fields["worker_output_excerpt"] = worker_output_excerpt
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_worker_complete",
            module=logger.name,
            fields=completion_fields,
        )
    )
    if not response_path.exists():
        raise AppError(
            code="browser_download_agent_missing_result",
            message="browser-use worker completed without writing a response payload",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "return_code": completed.returncode,
                "worker_output_excerpt": worker_output_excerpt,
            },
        )
    raw_response = json.loads(response_path.read_text(encoding="utf-8"))
    response = BrowserAgentWorkerResponse(
        schema_version=str(raw_response.get("schema_version", "1.0")),
        status=str(raw_response.get("status", "")).strip(),
        result=raw_response.get("result")
        if isinstance(raw_response.get("result"), dict)
        else None,
        error=raw_response.get("error")
        if isinstance(raw_response.get("error"), dict)
        else None,
    )
    if response.status == "ok" and response.result is not None:
        return _deserialize_browser_agent_run_result(response.result)
    if response.error is not None:
        raise AppError(
            code=str(response.error.get("code") or "browser_download_agent_failed"),
            message=str(
                response.error.get("message")
                or "browser-use worker failed to complete the report download task"
            ),
            retryable=bool(response.error.get("retryable", True)),
            severity=str(response.error.get("severity") or "error"),
            context=response.error.get("context")
            if isinstance(response.error.get("context"), dict)
            else {"normalized_url": normalized_url},
        )
    raise AppError(
        code="browser_download_agent_failed",
        message="browser-use worker failed to complete the report download task",
        retryable=True,
        context={"normalized_url": normalized_url},
    )


def _normalize_browser_worker_output_excerpt(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return ""
    without_ansi = _ANSI_ESCAPE_PATTERN.sub("", value)
    normalized = without_ansi.replace("\r\n", "\n").replace("\r", "\n")
    ascii_only = "".join(
        character
        if character == "\n" or character == "\t" or 32 <= ord(character) <= 126
        else " "
        for character in normalized
    )
    collapsed_lines = [
        re.sub(r"\s+", " ", line).strip()
        for line in ascii_only.splitlines()
        if line.strip()
    ]
    excerpt = "\n".join(collapsed_lines).strip()
    if len(excerpt) <= _BROWSER_AGENT_WORKER_OUTPUT_MAX_CHARS:
        return excerpt
    return excerpt[: _BROWSER_AGENT_WORKER_OUTPUT_MAX_CHARS - 3].rstrip() + "..."


def _deserialize_browser_agent_run_result(
    payload: dict[str, Any],
) -> BrowserAgentRunResult:
    network_events_payload = payload.get("network_events")
    network_events: list[BrowserDownloadNetworkEvent] = []
    if isinstance(network_events_payload, list):
        for item in network_events_payload:
            if not isinstance(item, dict):
                continue
            network_events.append(
                BrowserDownloadNetworkEvent(
                    schema_version=str(item.get("schema_version", "1.0")),
                    url=str(item.get("url") or "").strip(),
                    initiator_type=str(item.get("initiator_type") or "other").strip()
                    or "other",
                    signal_kind=str(item.get("signal_kind") or "other").strip()
                    or "other",
                )
            )
    return BrowserAgentRunResult(
        schema_version=str(payload.get("schema_version", "1.0")),
        raw_model_response=str(payload.get("raw_model_response") or ""),
        final_page_url=str(payload.get("final_page_url") or ""),
        final_page_title=str(payload.get("final_page_title") or ""),
        final_page_html=str(payload.get("final_page_html") or ""),
        downloaded_files=[
            str(item)
            for item in payload.get("downloaded_files", [])
            if str(item or "").strip()
        ],
        attachment_paths=[
            str(item)
            for item in payload.get("attachment_paths", [])
            if str(item or "").strip()
        ],
        network_resource_urls=[
            str(item)
            for item in payload.get("network_resource_urls", [])
            if str(item or "").strip()
        ],
        network_events=network_events,
        html_snapshot_path=str(payload.get("html_snapshot_path") or ""),
        screenshot_path=str(payload.get("screenshot_path") or ""),
    )


def _capture_terminal_snapshot(browser: Any) -> TerminalSnapshot:
    page = _resolve_current_page(browser)
    return TerminalSnapshot(
        page=page,
        url=(
            str(getattr(browser, "url", "") or "").strip()
            or _read_browser_current_page_url(browser)
            or _read_page_url(page)
        ),
        title=(
            str(getattr(browser, "title", "") or "").strip()
            or _read_browser_current_page_title(browser)
            or _read_page_title(page)
        ),
        html=str(getattr(browser, "html", "") or "") or _read_page_html(page),
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
        candidate = _capture_terminal_snapshot(browser)
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
) -> TerminalQuorumAssessment:
    signal_labels: list[str] = []
    transient_labels: list[str] = []
    route_text = _terminal_quorum_text(snapshot)
    lowered_route_text = route_text.casefold()
    lowered_url = str(snapshot.url or "").strip().casefold()
    network_events = _collect_network_events(snapshot.page)
    document_urls = _collect_network_resource_urls(
        page=snapshot.page,
        final_page_html=snapshot.html,
        network_events=network_events,
    )
    submit_button_state = str(payload.get("submit_button_state") or "").strip().casefold()
    post_submit_message = str(payload.get("post_submit_message") or "").strip()
    email_submission_completed = (
        normalize_optional_bool_signal(payload.get("email_submission_completed")) is True
    )
    confirmation_url_changed = (
        normalize_optional_bool_signal(payload.get("confirmation_url_changed")) is True
    )
    form_disappeared = normalize_optional_bool_signal(payload.get("form_disappeared")) is True
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
        if any(
            event.signal_kind == "confirmation_request" for event in network_events
        ):
            signal_labels.append("network_confirmation_request")
        if any(
            event.signal_kind == "submission_request" for event in network_events
        ):
            signal_labels.append("network_submission_request")
        if form_disappeared or (email_submission_completed and "<form" not in snapshot.html.casefold()):
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
                if label not in {"post_submit_message_transient", "submit_button_disabled"}
            ]
    elif policy.route_kind == "onsite_report" or policy.route_family in {
        "browser_onsite_report",
        "browser_listing_hub",
    }:
        if len(lowered_route_text) >= 400:
            signal_labels.append("onsite_html_body")
        if any(marker in lowered_route_text for marker in _TERMINAL_REPORT_TEXT_MARKERS):
            signal_labels.append("onsite_report_text")
        if any(
            event.signal_kind in {"navigation_request", "document_request"}
            for event in network_events
        ):
            signal_labels.append("terminal_navigation")
    else:
        if downloaded_files:
            signal_labels.append("downloaded_file_present")
        if any(
            event.signal_kind == "document_request" for event in network_events
        ):
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
            download_pdf_from_url(
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


def _capture_terminal_assets(
    *,
    browser: Any,
    page: Any,
    download_dir: Path,
    final_page_html: str,
) -> tuple[list[str], list[BrowserDownloadNetworkEvent], str, str]:
    network_events = _collect_network_events(page=page)
    network_resource_urls = _collect_network_resource_urls(
        page=page,
        final_page_html=final_page_html,
        network_events=network_events,
    )
    html_snapshot_path = _write_terminal_html_snapshot(
        download_dir=download_dir,
        final_page_html=final_page_html,
    )
    screenshot_path = _write_terminal_screenshot(
        browser=browser,
        page=page,
        download_dir=download_dir,
    )
    return network_resource_urls, network_events, html_snapshot_path, screenshot_path


def _collect_network_resource_urls(
    *,
    page: Any,
    final_page_html: str,
    network_events: list[BrowserDownloadNetworkEvent],
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
        for raw_url in _collect_page_resource_urls(page):
            add(raw_url)
        for raw_url in _collect_dom_candidate_urls(page):
            add(raw_url)
    for event in network_events:
        add(event.url)
    for raw_url in _extract_documentish_urls_from_html(final_page_html):
        add(raw_url)
    return normalized


def _collect_network_events(page: Any) -> list[BrowserDownloadNetworkEvent]:
    if page is None:
        return []
    try:
        raw_events = _maybe_await(
            page.evaluate(
                """
                () => {
                  const build = (entry, initiatorFallback = 'other') => ({
                    url: String(entry?.name || '').trim(),
                    initiator_type: String(entry?.initiatorType || initiatorFallback || 'other').trim(),
                  });
                  const navigationEntries = (globalThis.performance?.getEntriesByType?.('navigation') || [])
                    .map((entry) => build(entry, 'navigation'));
                  const resourceEntries = (globalThis.performance?.getEntriesByType?.('resource') || [])
                    .map((entry) => build(entry, 'other'));
                  return [...navigationEntries, ...resourceEntries];
                }
                """
            )
        )
    except Exception:
        return []
    raw_events = _coerce_evaluate_list(raw_events)
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


def _collect_page_resource_urls(page: Any) -> list[str]:
    try:
        resource_urls = _maybe_await(
            page.evaluate(
                """
                () => {
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
                }
                """
            )
        )
    except Exception:
        return []
    resource_urls = _coerce_evaluate_list(resource_urls)
    return [
        str(raw_url or "").strip()
        for raw_url in resource_urls
        if str(raw_url or "").strip()
    ]


def _collect_dom_candidate_urls(page: Any) -> list[str]:
    try:
        candidate_urls = _maybe_await(
            page.evaluate(
                """
                () => {
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
                }
                """
            )
        )
    except Exception:
        return []
    candidate_urls = _coerce_evaluate_list(candidate_urls)
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
    evaluate = getattr(page, "evaluate", None)
    if callable(evaluate):
        try:
            value = _maybe_await(
                evaluate("() => document.documentElement?.outerHTML || ''")
            )
        except Exception:
            return ""
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
) -> str:
    screenshot_path = download_dir / "terminal_screenshot.png"
    if _try_screenshot_call(
        candidate=getattr(browser, "take_screenshot", None),
        screenshot_path=screenshot_path,
    ):
        return str(screenshot_path)
    if _try_screenshot_call(
        candidate=getattr(page, "screenshot", None) if page is not None else None,
        screenshot_path=screenshot_path,
    ):
        return str(screenshot_path)
    if _try_screenshot_call(
        candidate=getattr(page, "take_screenshot", None) if page is not None else None,
        screenshot_path=screenshot_path,
    ):
        return str(screenshot_path)
    return ""


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


def _load_browser_use_runtime(normalized_url: str) -> Any:
    os.environ.setdefault("BROWSER_USE_SETUP_LOGGING", "false")
    try:
        return import_module("browser_use")
    except Exception as exc:
        raise AppError(
            code="browser_use_unavailable",
            message="The local browser_use runtime is not installed in this environment",
            cause=exc,
            retryable=False,
            context={"normalized_url": normalized_url},
        ) from exc


def _run_agent_history_with_timeout(
    *,
    agent: Any,
    browser: Any,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
) -> Any:
    payload: dict[str, Any] = {}
    errors: list[BaseException] = []

    def runner() -> None:
        try:
            payload["history"] = agent.run_sync(max_steps=request.settings.max_steps)
        except BaseException as exc:  # pragma: no cover - defensive thread bridge
            errors.append(exc)

    worker = Thread(target=runner, daemon=True)
    worker.start()
    timeout_seconds = _resolve_agent_run_timeout_seconds(request)
    deadline = time.monotonic() + timeout_seconds
    while worker.is_alive():
        remaining_seconds = deadline - time.monotonic()
        if remaining_seconds <= 0:
            break
        worker.join(min(_AGENT_COMPLETED_HISTORY_POLL_SECONDS, remaining_seconds))
        if not worker.is_alive():
            break
        completed_history = _read_completed_agent_history(agent)
        if completed_history is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_completed_history_observed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "timeout_seconds": timeout_seconds,
                        "max_steps": request.settings.max_steps,
                    },
                )
            )
            return BrowserAgentHistoryResult(
                history=completed_history,
                salvaged_completed_history=True,
            )
        email_blocker_history = _read_email_domain_blocker_partial_history(
            agent=agent,
            request=request,
            normalized_url=normalized_url,
        )
        if email_blocker_history is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_partial_email_blocker_observed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "timeout_seconds": timeout_seconds,
                        "max_steps": request.settings.max_steps,
                    },
                )
            )
            return BrowserAgentHistoryResult(
                history=email_blocker_history,
                salvaged_completed_history=True,
            )
    if worker.is_alive():
        completed_history = _read_completed_agent_history(agent)
        if completed_history is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_timeout_salvaged_completed_history",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "timeout_seconds": timeout_seconds,
                        "max_steps": request.settings.max_steps,
                    },
                )
            )
            return BrowserAgentHistoryResult(
                history=completed_history,
                salvaged_completed_history=True,
            )
        partial_blocker_history = _read_terminal_blocker_partial_history(
            agent=agent,
            request=request,
            normalized_url=normalized_url,
        )
        if partial_blocker_history is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_timeout_salvaged_partial_history_blocker",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "timeout_seconds": timeout_seconds,
                        "max_steps": request.settings.max_steps,
                    },
                )
            )
            return BrowserAgentHistoryResult(
                history=partial_blocker_history,
                salvaged_completed_history=True,
            )
        _signal_agent_stop(agent)
        worker.join(_AGENT_COMPLETED_HISTORY_POLL_SECONDS)
        completed_history = _read_completed_agent_history(agent)
        if completed_history is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_timeout_salvaged_completed_history",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "timeout_seconds": timeout_seconds,
                        "max_steps": request.settings.max_steps,
                    },
                )
            )
            return BrowserAgentHistoryResult(
                history=completed_history,
                salvaged_completed_history=True,
            )
        partial_blocker_history = _read_terminal_blocker_partial_history(
            agent=agent,
            request=request,
            normalized_url=normalized_url,
        )
        if partial_blocker_history is not None:
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="browser_report_download_timeout_salvaged_partial_history_blocker",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "timeout_seconds": timeout_seconds,
                        "max_steps": request.settings.max_steps,
                    },
                )
            )
            return BrowserAgentHistoryResult(
                history=partial_blocker_history,
                salvaged_completed_history=True,
            )
        raise AppError(
            code="browser_download_agent_timeout",
            message="browser-use did not return within the configured execution budget",
            retryable=True,
            context={
                "normalized_url": normalized_url,
                "timeout_seconds": timeout_seconds,
                "max_steps": request.settings.max_steps,
            },
        )
    if errors:
        raise errors[0]
    history = payload.get("history")
    if history is None:
        raise AppError(
            code="browser_download_agent_missing_history",
            message="browser-use completed without returning agent history",
            retryable=True,
            context={"normalized_url": normalized_url},
        )
    return BrowserAgentHistoryResult(
        history=history,
        salvaged_completed_history=False,
    )


def _read_lookup_blocker_partial_history(
    *,
    agent: Any,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
) -> Any | None:
    if str(request.route_family_hint or "").strip() != "browser_email_form":
        return None
    history = getattr(agent, "history", None)
    entries = getattr(history, "history", None)
    if not isinstance(entries, list) or not entries:
        return None
    history_text = _collect_agent_history_text(history)
    lowered = history_text.casefold()
    if not (
        any(marker in lowered for marker in _LOOKUP_FIELD_MARKERS)
        and any(marker in lowered for marker in _LOOKUP_FAILURE_MARKERS)
        and any(marker in lowered for marker in _LOOKUP_SUBMIT_MARKERS)
    ):
        return None
    state = _read_history_final_state(history)
    final_page_url = (
        str(getattr(state, "url", "") or "").strip()
        or str(request.attempt_url or request.url).strip()
        or normalized_url
    )
    final_page_title = str(getattr(state, "title", "") or "").strip()
    screenshot_path = str(getattr(state, "screenshot_path", "") or "").strip() or None
    lookup_label = _resolve_lookup_blocker_label(lowered)
    encountered_form_fields = _infer_encountered_form_fields(lowered, lookup_label)
    payload = {
        "route_kind": "email_delivery",
        "route_summary": (
            "Opened the report page, filled the email form, but could not verify "
            f"the required {lookup_label} lookup selection before submission."
        ),
        "route_family": "browser_email_form",
        "resolved_target_url": final_page_url,
        "final_page_url": final_page_url,
        "email_submission_completed": False,
        "downloaded_file_path": None,
        "downloaded_file_name": None,
        "downloaded_mime_type": None,
        "encountered_form_fields": encountered_form_fields,
        "route_steps": [
            {
                "index": None,
                "action": "submit",
                "target_text": "Submit",
                "target_role": "button",
                "target_url": final_page_url,
                "result": (
                    f"Submission was not verified because the required {lookup_label} "
                    "lookup field did not resolve to a valid option."
                ),
            }
        ],
        "post_submit_message": None,
        "confirmation_url_changed": False,
        "submit_button_state": None,
        "form_disappeared": False,
        "blocked_reason": "blocked_unknown_required_enum",
        "blocked_reason_detail": (
            f"The {lookup_label} field did not resolve to a valid lookup selection "
            "before submission."
        ),
        "final_page_title": final_page_title,
        "terminal_text_excerpt": _truncate_partial_history_excerpt(history_text),
        "traversed_page_urls": _read_distinct_history_urls(history, final_page_url),
        "onsite_capture_path": None,
        "onsite_capture_format": None,
        "onsite_page_count": None,
        "onsite_completeness_status": None,
    }
    return _SyntheticAgentHistory(
        payload=payload,
        state=_SyntheticHistoryState(
            url=final_page_url,
            title=final_page_title,
            screenshot_path=screenshot_path,
        ),
    )


def _read_terminal_blocker_partial_history(
    *,
    agent: Any,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
) -> Any | None:
    email_blocker_history = _read_email_domain_blocker_partial_history(
        agent=agent,
        request=request,
        normalized_url=normalized_url,
    )
    if email_blocker_history is not None:
        return email_blocker_history
    return _read_lookup_blocker_partial_history(
        agent=agent,
        request=request,
        normalized_url=normalized_url,
    )


def _read_email_domain_blocker_partial_history(
    *,
    agent: Any,
    request: BrowserReportDownloadRequest,
    normalized_url: str,
) -> Any | None:
    history = getattr(agent, "history", None)
    entries = getattr(history, "history", None)
    if not isinstance(entries, list) or not entries:
        return None
    history_text = _collect_agent_history_text(history)
    lowered = history_text.casefold()
    if not (
        any(marker in lowered for marker in _EMAIL_DOMAIN_BLOCK_MARKERS)
        and any(marker in lowered for marker in _EMAIL_DOMAIN_FAILURE_MARKERS)
    ):
        return None
    state = _read_history_final_state(history)
    final_page_url = (
        str(getattr(state, "url", "") or "").strip()
        or str(request.attempt_url or request.url).strip()
        or normalized_url
    )
    final_page_title = str(getattr(state, "title", "") or "").strip()
    screenshot_path = str(getattr(state, "screenshot_path", "") or "").strip() or None
    encountered_form_fields = _infer_encountered_form_fields(lowered, "")
    if "Business Email Address" not in encountered_form_fields:
        encountered_form_fields.insert(0, "Business Email Address")
    payload = {
        "route_kind": "email_delivery",
        "route_summary": (
            "Opened the report page and reached an email form, but the configured "
            "email address was rejected because the site requires a business email."
        ),
        "route_family": "browser_email_form",
        "resolved_target_url": final_page_url,
        "final_page_url": final_page_url,
        "email_submission_completed": False,
        "downloaded_file_path": None,
        "downloaded_file_name": None,
        "downloaded_mime_type": None,
        "encountered_form_fields": encountered_form_fields,
        "route_steps": [
            {
                "index": None,
                "action": "submit",
                "target_text": "Download report",
                "target_role": "button",
                "target_url": final_page_url,
                "result": (
                    "Submission was blocked because the configured email address "
                    "was rejected as not being a business email."
                ),
            }
        ],
        "post_submit_message": "The form requires a business email address.",
        "confirmation_url_changed": False,
        "submit_button_state": None,
        "form_disappeared": False,
        "blocked_reason": "blocked_email_domain",
        "blocked_reason_detail": (
            "The form rejected the configured email address as not being a "
            "business or professional email."
        ),
        "final_page_title": final_page_title,
        "terminal_text_excerpt": _truncate_partial_history_excerpt(history_text),
        "traversed_page_urls": _read_distinct_history_urls(history, final_page_url),
        "onsite_capture_path": None,
        "onsite_capture_format": None,
        "onsite_page_count": None,
        "onsite_completeness_status": None,
    }
    return _SyntheticAgentHistory(
        payload=payload,
        state=_SyntheticHistoryState(
            url=final_page_url,
            title=final_page_title,
            screenshot_path=screenshot_path,
        ),
    )


def _collect_agent_history_text(history: Any) -> str:
    pieces: list[str] = []
    entries = getattr(history, "history", None)
    if not isinstance(entries, list):
        return ""
    for entry in entries:
        model_output = getattr(entry, "model_output", None)
        if model_output is not None:
            for attribute in (
                "thinking",
                "evaluation_previous_goal",
                "memory",
                "next_goal",
            ):
                pieces.append(str(getattr(model_output, attribute, "") or ""))
            current_state = getattr(model_output, "current_state", None)
            if current_state is not None:
                for attribute in (
                    "thinking",
                    "evaluation_previous_goal",
                    "memory",
                    "next_goal",
                ):
                    pieces.append(str(getattr(current_state, attribute, "") or ""))
            for action in getattr(model_output, "action", []) or []:
                pieces.append(_serialize_history_fragment(action))
        for result in getattr(entry, "result", []) or []:
            for attribute in (
                "error",
                "long_term_memory",
                "extracted_content",
            ):
                pieces.append(str(getattr(result, attribute, "") or ""))
        state = getattr(entry, "state", None)
        if state is not None:
            pieces.append(str(getattr(state, "url", "") or ""))
            pieces.append(str(getattr(state, "title", "") or ""))
    text = "\n".join(piece for piece in pieces if piece)
    return text[-_PARTIAL_HISTORY_TEXT_MAX_CHARS:]


def _serialize_history_fragment(value: Any) -> str:
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            return json.dumps(
                model_dump(exclude_none=True, mode="json"),
                ensure_ascii=True,
                sort_keys=True,
            )
        except Exception:
            return str(value)
    if isinstance(value, dict):
        try:
            return json.dumps(value, ensure_ascii=True, sort_keys=True)
        except Exception:
            return str(value)
    return str(value)


def _resolve_lookup_blocker_label(history_text: str) -> str:
    for label, markers in (
        ("Location", ("location",)),
        ("Country", ("country",)),
        ("State", ("state", "province", "territory")),
        ("Region", ("region",)),
    ):
        if any(marker in history_text for marker in markers):
            return label
    return "Location"


def _infer_encountered_form_fields(history_text: str, lookup_label: str) -> list[str]:
    field_markers = [
        ("First Name", ("first name", "firstname")),
        ("Last Name", ("last name", "lastname")),
        ("Business Email Address", ("business email", "work email", "email")),
        ("Phone", ("phone", "telephone")),
        ("Company Name", ("company", "organization", "organisation")),
        ("Role", ("role", "job level", "seniority")),
        ("Department", ("department",)),
        ("Industry", ("industry",)),
    ]
    lookup_token = str(lookup_label or "").strip()
    if lookup_token:
        field_markers.append((lookup_token, (lookup_token.casefold(),)))
    fields: list[str] = []
    seen: set[str] = set()
    for label, markers in field_markers:
        if label in seen:
            continue
        if any(marker in history_text for marker in markers):
            seen.add(label)
            fields.append(label)
    if lookup_token and lookup_token not in seen:
        fields.append(lookup_token)
    return fields


def _truncate_partial_history_excerpt(history_text: str) -> str:
    excerpt = re.sub(r"\s+", " ", history_text).strip()
    if len(excerpt) <= 500:
        return excerpt
    return excerpt[-500:]


def _read_distinct_history_urls(history: Any, fallback_url: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    entries = getattr(history, "history", None)
    if isinstance(entries, list):
        for entry in entries:
            state = getattr(entry, "state", None)
            token = str(getattr(state, "url", "") or "").strip()
            if token and token not in seen:
                seen.add(token)
                urls.append(token)
    if fallback_url and fallback_url not in seen:
        urls.append(fallback_url)
    return urls


def _read_completed_agent_history(agent: Any) -> Any | None:
    history = getattr(agent, "history", None)
    if history is None:
        return None
    is_done = getattr(history, "is_done", None)
    final_result = getattr(history, "final_result", None)
    if not callable(is_done) or not callable(final_result):
        return None
    try:
        history_done = bool(is_done())
        rendered_result = str(final_result() or "").strip()
    except Exception:
        return None
    if not history_done or not rendered_result:
        return None
    return history


def _resolve_agent_run_timeout_seconds(
    request: BrowserReportDownloadRequest,
) -> float:
    buffer_seconds = min(
        _AGENT_RUN_TIMEOUT_MAX_BUFFER_SECONDS,
        max(
            _AGENT_RUN_TIMEOUT_MIN_BUFFER_SECONDS,
            float(request.settings.max_steps) * _AGENT_RUN_TIMEOUT_STEP_BUFFER_SECONDS,
        ),
    )
    return float(request.settings.timeout_seconds) + buffer_seconds


def _signal_agent_stop(agent: Any) -> None:
    _prime_agent_timing_fields(agent)
    stop_method = getattr(agent, "stop", None)
    if not callable(stop_method):
        return
    try:
        stop_method()
    except Exception:
        return


def _prime_agent_timing_fields(agent: Any) -> None:
    now = time.time()
    for attribute_name in ("_session_start_time", "_task_start_time"):
        if hasattr(agent, attribute_name):
            continue
        try:
            setattr(agent, attribute_name, now)
        except Exception:
            continue


def _log_browser_cleanup_failure(
    *,
    ctx: RunContext,
    normalized_url: str,
    operation: str,
    error: Exception,
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="browser_report_download_cleanup_failed",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "operation": operation,
                "error": str(error),
            },
        )
    )


def _prepare_browser_for_shutdown(
    browser: Any,
    *,
    ctx: RunContext,
    normalized_url: str,
) -> None:
    try:
        setattr(browser, "_intentional_stop", True)
    except Exception as exc:
        _log_browser_cleanup_failure(
            ctx=ctx,
            normalized_url=normalized_url,
            operation="set_intentional_stop",
            error=exc,
        )
    browser_profile = getattr(browser, "browser_profile", None)
    if browser_profile is not None:
        try:
            setattr(browser_profile, "cdp_url", None)
        except Exception as exc:
            _log_browser_cleanup_failure(
                ctx=ctx,
                normalized_url=normalized_url,
                operation="clear_browser_profile_cdp_url",
                error=exc,
            )
    reconnect_task = getattr(browser, "_reconnect_task", None)
    if reconnect_task is not None:
        try:
            if not reconnect_task.done():
                reconnect_task.cancel()
                try:
                    _run_awaitable(
                        _await_browser_task(reconnect_task),
                        timeout_seconds=_BROWSER_RESET_TIMEOUT_SECONDS,
                    )
                except (asyncio.CancelledError, TimeoutError):
                    pass
            setattr(browser, "_reconnect_task", None)
        except Exception as exc:
            _log_browser_cleanup_failure(
                ctx=ctx,
                normalized_url=normalized_url,
                operation="cancel_reconnect_task",
                error=exc,
            )
    try:
        setattr(browser, "_reconnecting", False)
    except Exception as exc:
        _log_browser_cleanup_failure(
            ctx=ctx,
            normalized_url=normalized_url,
            operation="clear_reconnecting_flag",
            error=exc,
        )
    reconnect_event = getattr(browser, "_reconnect_event", None)
    if reconnect_event is not None:
        try:
            reconnect_event.set()
        except Exception as exc:
            _log_browser_cleanup_failure(
                ctx=ctx,
                normalized_url=normalized_url,
                operation="set_reconnect_event",
                error=exc,
            )


def _cleanup_browser_profile_dir(
    profile_dir: Path,
    *,
    ctx: RunContext | None = None,
    normalized_url: str = "",
) -> None:
    try:
        if profile_dir.exists():
            shutil.rmtree(profile_dir, ignore_errors=True)
    except OSError as exc:
        if ctx is not None:
            _log_browser_cleanup_failure(
                ctx=ctx,
                normalized_url=normalized_url,
                operation="remove_browser_profile_dir",
                error=exc,
            )


def _new_managed_browser_profile_dir(download_dir: Path) -> Path:
    return download_dir / (
        f"{_BROWSER_PROFILE_DIR_PREFIX}-{os.getpid()}-{int(time.time() * 1000)}"
    )


def _cleanup_managed_browser_profile_dirs(
    *,
    download_dir: Path,
    active_profile_dir: Path | None = None,
    ctx: RunContext | None = None,
    normalized_url: str = "",
) -> None:
    if not download_dir.exists() or not download_dir.is_dir():
        return
    for candidate in download_dir.glob(f"{_BROWSER_PROFILE_DIR_PREFIX}*"):
        if active_profile_dir is not None and candidate == active_profile_dir:
            continue
        _cleanup_browser_profile_dir(
            candidate,
            ctx=ctx,
            normalized_url=normalized_url,
        )


def _cleanup_stale_browser_use_temp_dirs(
    *,
    ctx: RunContext,
    normalized_url: str,
) -> None:
    now = time.time()
    stale_dirs: list[Path] = []
    for path in _list_browser_use_temp_dirs():
        try:
            age_seconds = now - path.stat().st_mtime
        except OSError:
            continue
        if age_seconds < _STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS:
            continue
        stale_dirs.append(path)
    removed = _remove_browser_use_temp_dirs(stale_dirs)
    if removed:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_stale_temp_cleanup",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "removed_count": len(removed),
                    "removed_sample": removed[:_TEMP_CLEANUP_LOG_SAMPLE_LIMIT],
                },
            )
        )


def _cleanup_new_browser_use_temp_dirs(
    *,
    ctx: RunContext,
    normalized_url: str,
    preexisting_temp_dirs: set[str],
) -> None:
    new_dirs = [
        path
        for path in _list_browser_use_temp_dirs()
        if str(path) not in preexisting_temp_dirs
    ]
    removed = _remove_browser_use_temp_dirs(new_dirs)
    if removed:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_run_temp_cleanup",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "removed_count": len(removed),
                    "removed_sample": removed[:_TEMP_CLEANUP_LOG_SAMPLE_LIMIT],
                },
            )
        )


def _list_browser_use_temp_dirs() -> list[Path]:
    try:
        temp_root = Path(tempfile.gettempdir()).expanduser().resolve()
    except OSError:
        return []
    if not temp_root.exists() or not temp_root.is_dir():
        return []
    discovered: list[Path] = []
    seen: set[str] = set()
    for pattern in _BROWSER_USE_TEMP_DIR_PATTERNS:
        for candidate in temp_root.glob(pattern):
            try:
                resolved = candidate.resolve()
            except OSError:
                continue
            if not resolved.is_dir() or resolved.parent != temp_root:
                continue
            marker = str(resolved)
            if marker in seen:
                continue
            seen.add(marker)
            discovered.append(resolved)
    return discovered


def _remove_browser_use_temp_dirs(paths: list[Path]) -> list[str]:
    removed: list[str] = []
    for path in paths:
        try:
            if path.exists():
                shutil.rmtree(path)
        except OSError:
            continue
        if not path.exists():
            removed.append(path.name)
    return removed


def _kill_browser(browser: Any, *, ctx: RunContext, normalized_url: str) -> None:
    if _force_stop_local_browser_process(
        browser,
        ctx=ctx,
        normalized_url=normalized_url,
    ):
        return
    try:
        kill_result = browser.kill()
        if inspect.isawaitable(kill_result):
            _run_awaitable(kill_result, timeout_seconds=_BROWSER_KILL_TIMEOUT_SECONDS)
        return
    except Exception as exc:
        reset_method = getattr(browser, "reset", None)
        if callable(reset_method):
            try:
                reset_result = reset_method()
                if inspect.isawaitable(reset_result):
                    _run_awaitable(
                        reset_result,
                        timeout_seconds=_BROWSER_RESET_TIMEOUT_SECONDS,
                    )
                return
            except Exception as reset_exc:
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="browser_report_download_browser_kill_failed",
                        module=logger.name,
                        fields={
                            "normalized_url": normalized_url,
                            "error": str(reset_exc),
                        },
                    )
                )
                return
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_browser_kill_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "error": str(exc),
                },
            )
        )


def _kill_browser_with_timeout(
    browser: Any,
    *,
    ctx: RunContext,
    normalized_url: str,
) -> None:
    worker = Thread(
        target=_kill_browser,
        kwargs={
            "browser": browser,
            "ctx": ctx,
            "normalized_url": normalized_url,
        },
        daemon=True,
    )
    worker.start()
    worker.join(_BROWSER_CLEANUP_GRACE_SECONDS)
    if worker.is_alive():
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_browser_cleanup_timed_out",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "timeout_seconds": _BROWSER_CLEANUP_GRACE_SECONDS,
                },
            )
        )


def _force_stop_local_browser_process(
    browser: Any,
    *,
    ctx: RunContext,
    normalized_url: str,
) -> bool:
    watchdog = getattr(browser, "_local_browser_watchdog", None)
    process = getattr(watchdog, "_subprocess", None) if watchdog is not None else None
    pid = getattr(process, "pid", None)
    if pid is None:
        return False
    try:
        root_process = psutil.Process(int(pid))
        process_tree = [*root_process.children(recursive=True), root_process]
        for candidate in reversed(process_tree):
            try:
                candidate.terminate()
            except psutil.Error:
                continue
        _, alive = psutil.wait_procs(
            process_tree,
            timeout=_BROWSER_KILL_TIMEOUT_SECONDS / 2.0,
        )
        for candidate in alive:
            try:
                candidate.kill()
            except psutil.Error:
                continue
        if alive:
            psutil.wait_procs(
                alive,
                timeout=_BROWSER_KILL_TIMEOUT_SECONDS / 2.0,
            )
        setattr(watchdog, "_subprocess", None)
        temp_dirs = list(getattr(watchdog, "_temp_dirs_to_cleanup", []) or [])
        for temp_dir in temp_dirs:
            try:
                shutil.rmtree(Path(temp_dir), ignore_errors=True)
            except OSError:
                continue
        setattr(watchdog, "_temp_dirs_to_cleanup", [])
        original_user_data_dir = getattr(watchdog, "_original_user_data_dir", None)
        browser_profile = getattr(browser, "browser_profile", None)
        if original_user_data_dir is not None and browser_profile is not None:
            try:
                setattr(browser_profile, "user_data_dir", original_user_data_dir)
            except Exception as exc:
                _log_browser_cleanup_failure(
                    ctx=ctx,
                    normalized_url=normalized_url,
                    operation="restore_browser_profile_user_data_dir",
                    error=exc,
                )
        setattr(watchdog, "_original_user_data_dir", None)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_browser_process_force_stopped",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "browser_pid": int(pid),
                    "terminated_process_count": len(process_tree),
                },
            )
        )
        return True
    except (psutil.Error, OSError, ValueError) as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="browser_report_download_browser_process_force_stop_failed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "browser_pid": pid,
                    "error": str(exc),
                },
            )
        )
        return False


def _run_awaitable(awaitable: Any, *, timeout_seconds: float | None = None) -> None:
    _await_in_current_or_thread(awaitable, timeout_seconds=timeout_seconds)


def _is_no_space_error(exc: BaseException) -> bool:
    if isinstance(exc, OSError) and getattr(exc, "errno", None) == 28:
        return True
    return "no space left on device" in str(exc).casefold()


def _is_browser_start_timeout_error(exc: BaseException) -> bool:
    token = str(exc).casefold()
    return "browserstartevent" in token and "timed out" in token
