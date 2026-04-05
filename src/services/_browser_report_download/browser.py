from __future__ import annotations

import asyncio
import inspect
import logging
import os
from dataclasses import dataclass
from importlib import import_module
from pathlib import Path
from threading import Thread
from typing import Any

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.contracts.run_context import RunContext
from src.services._browser_report_download.artifact import BrowserUseAgentResult
from src.services._browser_report_download.prompt import BrowserDownloadPromptBundle
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.browser_report_download_service")


@dataclass(frozen=True)
class BrowserAgentRunResult:
    schema_version: str
    raw_model_response: str
    final_page_url: str
    downloaded_files: list[str]


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
            },
        )
    )
    browser_use = _load_browser_use_runtime(normalized_url)
    browser: Any | None = None
    raw_model_response = ""
    final_page_url = ""
    downloaded_files: list[str] = []
    try:
        browser = browser_use.Browser(
            downloads_path=str(download_dir),
            headless=not request.settings.headed,
            auto_download_pdfs=True,
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
        )
        history = agent.run_sync(max_steps=request.settings.max_steps)
        raw_model_response = str(history.final_result() or "").strip()
        final_page_url = str(getattr(browser, "url", "") or "").strip()
        downloaded_files = [
            str(path) for path in getattr(browser, "downloaded_files", [])
        ]
    except Exception as exc:
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
            _kill_browser(browser, ctx=ctx, normalized_url=normalized_url)
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
                "browser_final_url": final_page_url,
            },
        )
    )
    return BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response=raw_model_response,
        final_page_url=final_page_url,
        downloaded_files=downloaded_files,
    )


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


def _kill_browser(browser: Any, *, ctx: RunContext, normalized_url: str) -> None:
    try:
        kill_result = browser.kill()
        if inspect.isawaitable(kill_result):
            _run_awaitable(kill_result)
    except Exception as exc:
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


def _run_awaitable(awaitable: Any) -> None:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(awaitable)
        return

    errors: list[Exception] = []

    def runner() -> None:
        try:
            asyncio.run(awaitable)
        except Exception as exc:  # pragma: no cover - defensive thread bridge
            errors.append(exc)

    thread = Thread(target=runner, daemon=True)
    thread.start()
    thread.join()
    if errors:
        raise errors[0]
