from __future__ import annotations

import hashlib
import sys
from pathlib import Path
from types import SimpleNamespace

from src.contracts.browser_download import BrowserReportDownloadRequest
from src.contracts.run_context import RunContext
from src.contracts.state import StateArtifactAcquisitionCacheRecordRequest
from src.services._browser_report_download.prompt import BrowserDownloadPromptBundle
from src.services.browser_report_download_service import (
    _artifact_cache_key,
    _normalized_report_title,
    _publisher_scope,
    download_report_with_browser_use,
)
from src.services.state_service import record_artifact_acquisition_cache

from tests.test_browser_report_download_service.builders import _settings


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _valid_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj <</Type/Catalog>> endobj\n%%EOF\n"


def test_browser_download_reuses_valid_artifact_acquisition_cache(tmp_path: Path):
    settings = _settings(tmp_path)
    pdf_path = tmp_path / "cached-report.pdf"
    payload = _valid_pdf_bytes()
    pdf_path.write_bytes(payload)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=settings,
        report_title="Market Report",
        route_family_hint="browser_pdf_click",
    )
    normalized_url = "https://example.com/report"
    md5 = hashlib.md5(payload).hexdigest()
    sha256 = hashlib.sha256(payload).hexdigest()
    publisher_scope = _publisher_scope(normalized_url)
    report_title = _normalized_report_title(request)
    cache_key = _artifact_cache_key(
        normalized_url=normalized_url,
        publisher_scope=publisher_scope,
        report_title=report_title,
    )
    record_artifact_acquisition_cache(
        StateArtifactAcquisitionCacheRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            cache_key=cache_key,
            normalized_url=normalized_url,
            publisher_scope=publisher_scope,
            report_title=report_title,
            final_artifact_url="https://example.com/report.pdf",
            artifact_path=str(pdf_path),
            artifact_md5=md5,
            artifact_sha256=sha256,
            route_kind="pdf_download",
            route_family="browser_pdf_click",
            outcome="downloaded",
            downloaded_mime_type="application/pdf",
            size_bytes=len(payload),
            cache_version="browser_artifact_cache_v1",
            expires_at_utc="2026-08-01T00:00:00Z",
        ),
        _ctx(),
    )

    result = download_report_with_browser_use(request, _ctx())

    assert result.outcome == "downloaded"
    assert result.downloaded_file_path == str(pdf_path)
    assert result.terminal_evidence.artifact_validation_status == "verified"


def test_pre_llm_form_autofill_submits_without_model_client(
    tmp_path: Path,
    monkeypatch,
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
    model_client_requested = {"value": False}

    class FakePage:
        def __init__(self, browser):
            self.browser = browser

        def goto(self, url):
            self.browser.url = url
            self.browser.title = "Gated report"
            self.browser.html = "<html><body>Thanks for requesting the report</body></html>"

        def evaluate(self, script):
            if "standardFormSubmit" in str(script):
                return {
                    "attempted_count": 2,
                    "filled_count": 1,
                    "selected_count": 0,
                    "mandatory_agreement_checked_count": 1,
                    "resolved_control_count": 2,
                    "submitted": True,
                    "final_url": self.browser.url,
                    "resolved_fields": ["Work email", "Privacy agreement"],
                    "unresolved_fields": [],
                }
            return {"status": "ok"}

    class FakeBrowser:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.url = ""
            self.title = ""
            self.html = ""
            self.downloaded_files = []

        def get_current_page(self):
            return FakePage(self)

        async def kill(self):
            return None

    class FailingChatOpenRouter:
        def __init__(self, **kwargs):
            model_client_requested["value"] = True
            raise AssertionError("model client should not be constructed")

    fake_browser_use = SimpleNamespace(
        Browser=FakeBrowser,
        ChatOpenRouter=FailingChatOpenRouter,
        Agent=object,
    )
    monkeypatch.setitem(sys.modules, "browser_use", fake_browser_use)
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
        normalized_url="https://example.com/gated-report",
        execution_url="https://example.com/gated-report",
        download_dir=tmp_path,
        prompt_bundle=prompt_bundle,
    )

    assert model_client_requested["value"] is False
    assert "deterministic pre-LLM form autofill" in result.raw_model_response
