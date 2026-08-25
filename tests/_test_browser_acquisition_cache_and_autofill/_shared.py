# ruff: noqa: F401,F403,F405
from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

from src.contracts.browser_download import (
    BrowserReportDownloadRequest,
    BrowserRoutePlaybook,
    BrowserRoutePlaybookStep,
)
from src.contracts.run_context import RunContext
from src.contracts.state import StateArtifactAcquisitionCacheRecordRequest
from src.services._browser_report_download.artifact import (
    finalize_browser_report_download_result,
)
from src.services._browser_report_download.browser import (
    run_deterministic_browser_route_playbook,
)
from src.services._browser_report_download.helpers import (
    browser_helper_standard_form_submit,
)
from src.services._browser_report_download.models import BrowserAgentRunResult
from src.services._browser_report_download._artifact.classification import (
    _message_indicates_confirmed_email_delivery,
)
from src.services._browser_report_download.prompt import BrowserDownloadPromptBundle
from src.services.browser_report_download_service import (
    _artifact_cache_key,
    _deterministic_playbooks_require_isolated_worker,
    _deterministic_playbook_handoff_url,
    _normalized_report_title,
    _publisher_scope,
    _should_defer_browser_preflight_for_deterministic_playbooks,
    _try_deterministic_browser_route_playbooks,
    download_report_with_browser_use,
    try_deterministic_browser_route_playbooks,
)
from src.services.state_service import record_artifact_acquisition_cache
from tests.test_browser_report_download_service.builders import _settings


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _valid_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj <</Type/Catalog>> endobj\n%%EOF\n"


def _run_async_pre_llm_form_case(
    *,
    tmp_path: Path,
    external_boundary_mocks_only,
    form_payload: dict[str, object],
    terminal_html: str,
):
    from src.services._browser_report_download import browser as browser_runtime

    settings = _settings(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/gated-report",
        settings=settings,
        route_family_hint="browser_email_form",
        delivery_email="ops@example.com",
    )
    observed = {"agent_calls": 0, "agent_browser": None, "browser": None}

    class AsyncPage:
        def __init__(self, browser) -> None:
            self.browser = browser

        async def evaluate(self, expression: str):
            if "standardFormSubmit" in expression:
                self.browser.deterministic_submit_calls += 1
                return form_payload
            if "document.documentElement" in expression:
                return self.browser.html
            return {"status": "ok"}

    class AsyncBrowser:
        def __init__(self, **kwargs) -> None:
            observed["browser"] = self
            self.kwargs = kwargs
            self.url = request.url
            self.title = "Gated report"
            self.html = terminal_html
            self.storage_marker = "preflight-cookie-and-local-storage"
            self.page = AsyncPage(self)
            self.downloaded_files = []
            self.start_calls = 0
            self.kill_calls = 0
            self.deterministic_submit_calls = 0

        async def start(self) -> None:
            self.start_calls += 1

        async def get_current_page(self):
            return self.page

        async def get_current_page_url(self) -> str:
            return self.url

        async def get_current_page_title(self) -> str:
            return self.title

        async def kill(self) -> None:
            self.kill_calls += 1

    AsyncBrowser.__module__ = "browser_use.browser"

    class FakeChatOpenAI:
        def __init__(self, **kwargs) -> None:
            self.kwargs = kwargs

    class FakeChatOpenRouter(FakeChatOpenAI):
        pass

    class FakeHistory:
        def final_result(self) -> str:
            return json.dumps(
                {
                    "route_kind": "email_delivery",
                    "route_family": "browser_email_form",
                    "route_summary": "Agent received the existing form session.",
                    "final_page_url": "https://example.com/gated-report#agent",
                    "resolved_target_url": "https://example.com/gated-report#agent",
                    "email_submission_completed": False,
                    "encountered_form_fields": [],
                }
            )

        def action_results(self):
            return []

    class FakeAgent:
        def __init__(self, *, browser, **_kwargs) -> None:
            observed["agent_calls"] += 1
            observed["agent_browser"] = browser
            self.browser = browser

        def run_sync(self, max_steps):
            assert self.browser.storage_marker == "preflight-cookie-and-local-storage"
            self.browser.url = "https://example.com/gated-report#agent"
            self.browser.title = "Agent fallback"
            self.browser.html = "<html><body>Agent fallback</body></html>"
            return FakeHistory()

    fake_browser_use = SimpleNamespace(
        Browser=AsyncBrowser,
        ChatOpenAI=FakeChatOpenAI,
        ChatOpenRouter=FakeChatOpenRouter,
        Agent=FakeAgent,
    )
    external_boundary_mocks_only.setitem(sys.modules, "browser_use", fake_browser_use)
    prompt_bundle = BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route/browser_email_form",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user",
        task_prompt="task",
    )

    result = browser_runtime.run_browser_report_download_agent(
        request=request,
        ctx=_ctx(),
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path,
        prompt_bundle=prompt_bundle,
    )
    return result, observed, observed["browser"]


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
