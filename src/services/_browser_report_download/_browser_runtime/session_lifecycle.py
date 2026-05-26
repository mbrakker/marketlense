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
    _await_browser_task,
    _await_in_current_or_thread,
    _read_history_final_state,
    _run_awaitable,
)

logger = logging.getLogger("market_lense.browser_report_download_service")


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


def _default_session_reuse_base_dir(
    request: BrowserReportDownloadRequest,
    download_dir: Path,
) -> Path:
    output_dir = str(getattr(request.settings, "output_dir", "") or "").strip()
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    return download_dir.parent.resolve()


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
