from __future__ import annotations

import logging
import os
import shutil
import tempfile
import time
from pathlib import Path

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.contracts.run_context import RunContext
from src.services._browser_report_download._browser_runtime import (
    _BROWSER_PROFILE_DIR_PREFIX,
    _BROWSER_USE_TEMP_DIR_PATTERNS,
    _STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS,
    _TEMP_CLEANUP_LOG_SAMPLE_LIMIT,
)
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")

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
