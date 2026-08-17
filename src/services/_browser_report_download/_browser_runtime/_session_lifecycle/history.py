from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from threading import Thread
from typing import Any

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.contracts.run_context import RunContext
from src.services._browser_report_download._browser_runtime import (
    _AGENT_COMPLETED_HISTORY_POLL_SECONDS,
    _AGENT_RUN_TIMEOUT_MAX_BUFFER_SECONDS,
    _AGENT_RUN_TIMEOUT_MIN_BUFFER_SECONDS,
    _AGENT_RUN_TIMEOUT_STEP_BUFFER_SECONDS,
)
from src.services._browser_report_download._browser_runtime._session_lifecycle.partial_history import (
    _read_email_domain_blocker_partial_history,
    _read_terminal_blocker_partial_history,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

@dataclass(frozen=True)
class BrowserAgentHistoryResult:
    history: Any
    salvaged_completed_history: bool
    no_progress_observation: Any | None = None


def _run_agent_history_with_timeout(
    *,
    agent: Any,
    browser: Any,
    request: BrowserReportDownloadRequest,
    ctx: RunContext,
    normalized_url: str,
    no_progress_detector: Any | None = None,
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
    no_progress_observation = (
        getattr(no_progress_detector, "observation", None)
        if bool(getattr(no_progress_detector, "should_stop", False))
        else None
    )
    return BrowserAgentHistoryResult(
        history=history,
        salvaged_completed_history=False,
        no_progress_observation=no_progress_observation,
    )


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
