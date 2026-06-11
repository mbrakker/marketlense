from __future__ import annotations
import asyncio
import inspect
import logging
import shutil
from pathlib import Path
from threading import Thread
from typing import Any
from src.contracts.run_context import RunContext
from src.services._browser_report_download.helpers import (
    browser_helper_capture_screenshot,
)

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
