from __future__ import annotations

import asyncio
import inspect
import logging
from pathlib import Path
from threading import Thread
from typing import Any

from src.contracts.run_context import RunContext
from src.services._browser_report_download.artifact_materialization import (
    allocate_browser_artifact_stage,
    materialize_browser_artifact_bytes,
    materialize_external_browser_artifact,
)
from src.services._browser_report_download.artifact_paths import (
    resolve_browser_artifact_path,
)
from src.services._browser_report_download.helpers import (
    browser_helper_capture_screenshot,
)
from src.utils.errors import AppError

logger = logging.getLogger("market_lense.browser_report_download_service")


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
    target_path = resolve_browser_artifact_path(
        parent_dir=download_dir,
        source_name="terminal_screenshot.png",
        fixed_name="terminal_screenshot.png",
    )
    try:
        published_path = materialize_external_browser_artifact(
            source_path=source_path,
            download_dir=download_dir,
            preferred_filename=target_path.name,
            source_identity=str(source_path),
        )
    except (AppError, OSError):
        return ""
    return str(published_path or "")


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
    source_identity: str = "",
) -> str:
    token = str(final_page_html or "")
    if not token.strip():
        return ""
    try:
        published_path = materialize_browser_artifact_bytes(
            content=token.encode("utf-8"),
            download_dir=download_dir,
            preferred_filename="terminal_snapshot.html",
            source_identity=str(source_identity or "terminal_snapshot.html"),
        )
    except (AppError, OSError):
        return ""
    return str(published_path or "")


def _write_terminal_screenshot(
    *,
    browser: Any,
    page: Any,
    download_dir: Path,
    ctx: RunContext,
    normalized_url: str,
) -> str:
    screenshot_path = resolve_browser_artifact_path(
        parent_dir=download_dir,
        source_name="terminal_screenshot.png",
        fixed_name="terminal_screenshot.png",
    )
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
        stage_path = allocate_browser_artifact_stage(
            screenshot_path,
            stage_suffix=".png",
        )
    except (AppError, OSError):
        return False
    try:
        try:
            result = candidate(path=str(stage_path), full_page=True)
            if inspect.isawaitable(result):
                _run_awaitable(result)
        except TypeError:
            result = candidate(str(stage_path))
            if inspect.isawaitable(result):
                _run_awaitable(result)
        if not stage_path.exists() or stage_path.stat().st_size <= 0:
            return False
        published_path = materialize_external_browser_artifact(
            source_path=stage_path,
            download_dir=screenshot_path.parent,
            preferred_filename=screenshot_path.name,
            source_identity=str(screenshot_path),
        )
        return published_path is not None
    except (AppError, OSError):
        return False
    finally:
        stage_path.unlink(missing_ok=True)


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


__all__ = [
    "_resolve_current_page",
    "_read_history_final_page_url",
    "_read_history_final_page_title",
    "_copy_history_screenshot",
    "_read_history_final_state",
    "_read_history_attachment_paths",
    "_read_page_url",
    "_read_browser_current_page_url",
    "_read_page_title",
    "_read_browser_current_page_title",
    "_read_page_html",
    "_write_terminal_html_snapshot",
    "_write_terminal_screenshot",
    "_try_screenshot_call",
    "_maybe_await",
    "_await_browser_task",
    "_await_in_current_or_thread",
    "_run_awaitable",
]
