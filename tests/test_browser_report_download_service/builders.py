from __future__ import annotations

import json

import logging

import os

import subprocess

import tempfile

import time

from dataclasses import replace

from pathlib import Path

from types import SimpleNamespace

from typing import Any

import pytest

import requests

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadPublisherOverride,
    BrowserDownloadRouteStep,
    BrowserDownloadSettings,
    BrowserReportDownloadRequest,
)

from src.contracts.prompts import PromptLoadRequest, PromptRenderRequest

from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace

from src.services._browser_report_download import artifact as artifact_runtime

from src.services._browser_report_download import browser as browser_runtime

from src.services._browser_report_download import (
    browser_worker as browser_worker_runtime,
)

from src.services._browser_report_download import http as http_runtime

from src.services._browser_report_download import prompt as prompt_runtime

from src.services._browser_report_download import request as request_runtime

from src.services._browser_report_download.request import (
    resolve_effective_identity_fields,
)

from src.services import browser_report_download_service as service

from src.services import prompt_service

from src.utils.errors import AppError

def _settings(
    tmp_path: Path,
    *,
    work_email: str | None = "ops@example.com",
) -> BrowserDownloadSettings:
    return BrowserDownloadSettings(
        schema_version="1.0",
        openrouter_api_key="openrouter-key",
        model="openai/gpt-5-mini",
        temperature=0.0,
        timeout_seconds=30.0,
        max_steps=5,
        output_dir=str(tmp_path / "downloads"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        identity_config_path=str(tmp_path / "browser_download_identity.yaml"),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value=work_email,
                    aliases=["email", "email address"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="company",
                    label="Company",
                    value="Market Lense",
                    aliases=["company", "business", "organization"],
                ),
            ],
        ),
        openrouter_http_referer="https://marketlense.local",
        headed=False,
        retry_retries=1,
        retry_base_delay_seconds=0.1,
        retry_backoff_step_seconds=0.0,
        retry_jitter_seconds=0.0,
    )

def _runtime(
    tmp_path: Path,
    *,
    route_kind: str,
    route_summary: str,
    create_pdf: bool,
    email_submission_completed: bool | None,
):
    payload = {
        "route_kind": route_kind,
        "route_summary": route_summary,
        "final_page_url": "https://example.com/final",
        "email_submission_completed": email_submission_completed,
        "downloaded_file_path": None,
        "downloaded_file_name": None,
        "downloaded_mime_type": None,
        "encountered_form_fields": [],
        "post_submit_message": "",
    }
    history_attachments: list[str] = []

    class FakeHistory:
        def final_result(self) -> str:
            return json.dumps(payload)

        def action_results(self) -> list[Any]:
            return [
                SimpleNamespace(attachments=list(history_attachments)),
            ]

    class FakeBrowser:
        def __init__(
            self,
            downloads_path,
            headless,
            auto_download_pdfs,
            keep_alive=None,
            user_data_dir=None,
        ):
            self.downloads_path = str(downloads_path)
            self.user_data_dir = (
                str(user_data_dir) if user_data_dir is not None else None
            )
            self.headless = headless
            self.auto_download_pdfs = auto_download_pdfs
            self.keep_alive = keep_alive
            self.url = ""
            self.title = ""
            self.html = ""
            self.downloaded_files: list[str] = []
            self.network_resource_urls: list[str] = []
            self.network_events: list[dict[str, str]] = []
            self.dom_candidate_urls: list[str] = []
            self.current_page_factory = None

        async def kill(self) -> None:
            return None

        def get_current_page(self):
            if callable(self.current_page_factory):
                return self.current_page_factory()
            browser = self

            class FakePage:
                def evaluate(self, script):
                    if "navigationEntries" in str(script):
                        if browser.network_events:
                            return list(browser.network_events)
                        return list(browser.network_resource_urls)
                    if "document.querySelectorAll" in str(script):
                        return list(browser.dom_candidate_urls)
                    return list(browser.network_resource_urls)

            return FakePage()

        def take_screenshot(
            self, path=None, full_page=False, format="png", quality=None, clip=None
        ):
            if path:
                Path(path).write_bytes(b"fake-screenshot")
            return b"fake-screenshot"

    class FakeChatOpenRouter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeAgent:
        def __init__(
            self,
            *,
            task,
            llm,
            browser,
            output_model_schema,
            use_judge=False,
        ):
            self.task = task
            self.llm = llm
            self.browser = browser
            self.output_model_schema = output_model_schema
            self.use_judge = use_judge

        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/final"
            self.browser.title = "Example report terminal"
            self.browser.html = (
                "<html><body><h1>Example report terminal</h1></body></html>"
            )
            download_dir = Path(self.browser.downloads_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            if create_pdf:
                pdf_path = download_dir / "report.pdf"
                pdf_path.write_bytes(b"%PDF-1.7 test")
                self.browser.downloaded_files = [str(pdf_path)]
                payload["downloaded_file_path"] = str(pdf_path)
                payload["downloaded_file_name"] = pdf_path.name
                payload["downloaded_mime_type"] = "application/pdf"
                history_attachments[:] = [str(pdf_path)]
            return FakeHistory()

    return SimpleNamespace(
        Browser=FakeBrowser,
        ChatOpenRouter=FakeChatOpenRouter,
        Agent=FakeAgent,
    )

def _service_events(caplog) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != service.logger.name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events

class _FakeResponse:
    def __init__(
        self,
        *,
        content: bytes,
        status_code: int = 200,
        headers: dict[str, str] | None = None,
        url: str = "",
    ) -> None:
        self._content = content
        self.status_code = status_code
        self.headers = headers or {}
        self.url = url

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def iter_content(self, chunk_size: int = 65536):
        for start in range(0, len(self._content), chunk_size):
            yield self._content[start : start + chunk_size]

    @property
    def text(self) -> str:
        return self._content.decode("utf-8", errors="ignore")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")

__all__ = [name for name in globals() if name not in {'__name__', '__annotations__', '__doc__', '__spec__', '__file__', '__package__', '__loader__', '__cached__', '__builtins__'}]

