# ruff: noqa: F401,F403,F405
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.contracts.browser_download import (
    BrowserPreflightProbeResponse,
    BrowserPreflightProbeResult,
    BrowserReportDownloadRequest,
)
from src.services._browser_report_download import preflight as preflight_runtime
from src.utils.errors import AppError

from ..builders import (
    _FakeResponse,
    _runtime,
    _settings,
    browser_runtime,
    http_runtime,
    service,
)


class _PreflightPage:
    def __init__(self, *, pdf_url: str | None, page_url: str) -> None:
        self.url = page_url
        self._pdf_url = pdf_url

    def title(self) -> str:
        return "Rendered publisher report"

    def content(self) -> str:
        if not self._pdf_url:
            return "<html><body><h1>Rendered publisher report</h1></body></html>"
        return (
            "<html><body><h1>Rendered publisher report</h1>"
            f'<a id="download" href="{self._pdf_url}">Download PDF</a>'
            "</body></html>"
        )

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        return None

    def evaluate(self, script: str) -> object:
        if "getEntriesByType" in script:
            return [self._pdf_url] if self._pdf_url else []
        return {
            "pdf_candidates": [self._pdf_url] if self._pdf_url else [],
            "form_text": [],
            "location_href": self.url,
            "title": "Rendered publisher report",
            "html_size": len(self.content()),
            "cookie_names": ["session"],
            "local_storage_keys": ["publisherConsent"],
        }


class _PreflightBrowser:
    def __init__(
        self,
        *,
        downloads_path: str,
        headless: bool,
        auto_download_pdfs: bool,
        keep_alive: bool,
        pdf_url: str | None,
        user_data_dir: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.downloads_path = downloads_path
        self.headless = headless
        self.auto_download_pdfs = auto_download_pdfs
        self.keep_alive = keep_alive
        self.user_data_dir = user_data_dir
        self.user_agent = user_agent
        self.pdf_url = pdf_url
        self.url = ""
        self.title = ""
        self.html = ""
        self.downloaded_files: list[str] = []
        self.network_resource_urls: list[str] = []
        self.network_events: list[dict[str, str]] = []
        self.stopped = False

    def start(self) -> None:
        return None

    def navigate_to(self, url: str) -> None:
        self.url = url
        self.title = "Rendered publisher report"

    def get_current_page(self) -> _PreflightPage:
        return _PreflightPage(pdf_url=self.pdf_url, page_url=self.url)

    def kill(self) -> None:
        self.stopped = True

    def take_screenshot(self, path=None, **kwargs):
        if path:
            Path(path).write_bytes(b"fake-screenshot")
        return b"fake-screenshot"


def _preflight_runtime(*, pdf_url: str | None):
    class Browser(_PreflightBrowser):
        instances: list["Browser"] = []

        def __init__(self, *, user_agent: str | None = None, **kwargs):
            super().__init__(pdf_url=pdf_url, user_agent=user_agent, **kwargs)
            self.__class__.instances.append(self)

    return SimpleNamespace(Browser=Browser)


def _terminal_not_found_preflight_runtime():
    class TerminalNotFoundPage(_PreflightPage):
        def __init__(self, *, page_url: str) -> None:
            super().__init__(pdf_url=None, page_url=page_url)

        def title(self) -> str:
            return "404 Not Found"

        def content(self) -> str:
            return (
                "<html><body><h1>Not Found</h1>"
                "<p>The requested URL was not found on this server.</p>"
                "</body></html>"
            )

    class Browser(_PreflightBrowser):
        def __init__(self, **kwargs) -> None:
            super().__init__(pdf_url=None, **kwargs)

        def get_current_page(self) -> TerminalNotFoundPage:
            return TerminalNotFoundPage(page_url=self.url)

    return SimpleNamespace(Browser=Browser)


def _delayed_terminal_not_found_preflight_runtime():
    final_url = "https://www4.example.com/commerce-media-trends-report"

    class TerminalNotFoundPage(_PreflightPage):
        def __init__(self) -> None:
            super().__init__(pdf_url=None, page_url=final_url)

        def title(self) -> str:
            return "404 Not Found"

        def content(self) -> str:
            return (
                "<html><body><h1>Not Found</h1>"
                "<p>The requested URL was not found on this server.</p>"
                "</body></html>"
            )

    class Browser(_PreflightBrowser):
        def __init__(self, **kwargs) -> None:
            super().__init__(pdf_url=None, **kwargs)
            self.page_reads = 0

        def get_current_page(self) -> _PreflightPage:
            self.page_reads += 1
            if self.page_reads == 1:

                class LoadingPage(_PreflightPage):
                    def content(self) -> str:
                        return ""

                    def evaluate(self, script: str) -> object:
                        if "getEntriesByType" in script:
                            return []
                        if "documentElement" in script:
                            return ""
                        return {
                            "pdf_candidates": [],
                            "form_text": [],
                            "location_href": self.url,
                            "title": "",
                            "html_size": 0,
                            "cookie_names": [],
                            "local_storage_keys": [],
                        }

                return LoadingPage(pdf_url=None, page_url=self.url)
            self.url = final_url
            return TerminalNotFoundPage()

    return SimpleNamespace(Browser=Browser)


def _terminal_access_forbidden_preflight_runtime():
    class TerminalAccessForbiddenPage(_PreflightPage):
        def __init__(self, *, page_url: str) -> None:
            super().__init__(pdf_url=None, page_url=page_url)

        def title(self) -> str:
            return "403 Forbidden"

        def content(self) -> str:
            return (
                "<html><head><title>403 Forbidden</title></head>"
                "<body><h1>Error 403 Forbidden</h1><p>Forbidden</p></body></html>"
            )

    class Browser(_PreflightBrowser):
        def __init__(self, **kwargs) -> None:
            super().__init__(pdf_url=None, **kwargs)

        def get_current_page(self) -> TerminalAccessForbiddenPage:
            return TerminalAccessForbiddenPage(page_url=self.url)

    return SimpleNamespace(Browser=Browser)


def _preflight_agent_runtime(*, tmp_path: Path, pdf_url: str | None):
    runtime = _preflight_runtime(pdf_url=pdf_url)
    agent_runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and download the report.",
        create_pdf=True,
        email_submission_completed=None,
    )
    runtime.Agent = agent_runtime.Agent
    runtime.ChatOpenRouter = agent_runtime.ChatOpenRouter
    return runtime


__all__ = [
    name
    for name in globals()
    if name
    not in {
        "__name__",
        "__annotations__",
        "__doc__",
        "__spec__",
        "__file__",
        "__package__",
        "__loader__",
        "__cached__",
        "__builtins__",
        "_SplitPath",
    }
]
