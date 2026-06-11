from __future__ import annotations

import asyncio
import inspect
import logging
import shutil
from pathlib import Path
from threading import Thread
from typing import Any

import psutil

from src.contracts.run_context import RunContext
from src.services._browser_report_download._browser_runtime import (
    _BROWSER_CLEANUP_GRACE_SECONDS,
    _BROWSER_KILL_TIMEOUT_SECONDS,
    _BROWSER_RESET_TIMEOUT_SECONDS,
)
from src.services._browser_report_download._browser_runtime._session_lifecycle.cleanup import (
    _log_browser_cleanup_failure,
)
from src.services._browser_report_download._browser_runtime.terminal_assets import (
    _await_browser_task,
    _run_awaitable,
)
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

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
