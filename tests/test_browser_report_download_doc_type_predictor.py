from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadSettings,
    BrowserReportDownloadRequest,
)
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.services import browser_report_download_service as service
from src.services._browser_report_download import browser as browser_runtime
from src.services._browser_report_download import http as http_runtime


def _settings(tmp_path: Path) -> BrowserDownloadSettings:
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
                    value="ops@example.com",
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
) -> SimpleNamespace:
    payload: dict[str, object] = {
        "route_kind": route_kind,
        "route_summary": route_summary,
        "final_page_url": "https://example.com/final",
        "email_submission_completed": None,
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
            return [SimpleNamespace(attachments=list(history_attachments))]

    class FakeBrowser:
        def __init__(
            self,
            downloads_path: str | Path,
            headless: bool,
            auto_download_pdfs: bool,
            keep_alive: bool | None = None,
            user_data_dir: str | Path | None = None,
        ) -> None:
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

        async def kill(self) -> None:
            return None

        def get_current_page(self) -> Any:
            browser = self

            class FakePage:
                def evaluate(self, script: object) -> list[object]:
                    script_text = str(script)
                    if "navigationEntries" in script_text:
                        if browser.network_events:
                            return list(browser.network_events)
                        return list(browser.network_resource_urls)
                    if "document.querySelectorAll" in script_text:
                        return list(browser.dom_candidate_urls)
                    return list(browser.network_resource_urls)

            return FakePage()

        def take_screenshot(
            self,
            path: str | None = None,
            full_page: bool = False,
            format: str = "png",
            quality: int | None = None,
            clip: object | None = None,
        ) -> bytes:
            _ = (full_page, format, quality, clip)
            if path:
                Path(path).write_bytes(b"fake-screenshot")
            return b"fake-screenshot"

    class FakeChatOpenRouter:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

    class FakeAgent:
        def __init__(
            self,
            *,
            task: str,
            llm: object,
            browser: FakeBrowser,
            output_model_schema: object,
            use_judge: bool = False,
        ) -> None:
            self.task = task
            self.llm = llm
            self.browser = browser
            self.output_model_schema = output_model_schema
            self.use_judge = use_judge

        def run_sync(self, max_steps: int) -> FakeHistory:
            _ = max_steps
            self.browser.url = "https://example.com/final"
            self.browser.title = "Example report terminal"
            self.browser.html = "<html><body><h1>Example report terminal</h1></body></html>"
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

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        _ = (exc_type, exc, tb)
        return None

    def iter_content(self, chunk_size: int = 65536) -> list[bytes]:
        return [
            self._content[start : start + chunk_size]
            for start in range(0, len(self._content), chunk_size)
        ]

    @property
    def text(self) -> str:
        return self._content.decode("utf-8", errors="ignore")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")


def _service_events(caplog: Any) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name != service.logger.name:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(cast(dict[str, object], payload))
    return events


def _prediction_fields(events: list[dict[str, object]]) -> dict[str, object]:
    for event in events:
        if event.get("event") == "browser_report_download_doc_type_prediction":
            fields = event.get("fields")
            if isinstance(fields, dict):
                return cast(dict[str, object], fields)
    raise AssertionError("Prediction event not found")


def test_download_report_predicts_query_embedded_pdf_before_browser(
    tmp_path: Path,
    caplog: Any,
    run_context: Any,
    external_boundary_mocks_only: Any,
    assert_logs_have_required_fields: Any,
    assert_no_defaulted_required_fields: Any,
) -> None:
    redirect_url = (
        "https://click.example.com/redirect?"
        "target=https%3A%2F%2Fcdn.example.com%2Freports%2Foutlook-2026.pdf"
    )
    pdf_url = "https://cdn.example.com/reports/outlook-2026.pdf"
    observed_urls: list[str] = []

    def fake_get(url: str, *args: object, **kwargs: object) -> _FakeResponse:
        _ = (args, kwargs)
        observed_urls.append(url)
        assert url == pdf_url
        return _FakeResponse(
            content=b"%PDF-1.7 predicted redirect pdf bytes",
            headers={"Content-Type": "application/pdf"},
            url=pdf_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError(
                f"browser runtime should not start for predicted query-target PDF: {module_name}"
            )
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=redirect_url,
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    events = _service_events(caplog)
    prediction_fields = _prediction_fields(events)
    assert prediction_fields["predicted_doc_type"] == "direct_pdf"
    assert prediction_fields["probe_url"] == pdf_url
    assert prediction_fields["evidence_labels"] == [
        "embedded_pdf_target",
        "query_redirect_pdf",
    ]
    assert observed_urls == [pdf_url]
    assert response.route_family == "direct_pdf_probe"
    assert response.final_page_url == pdf_url
    assert response.downloaded_file_name == "outlook-2026.pdf"
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(events)


def test_download_report_predicts_candidate_pdf_before_browser(
    tmp_path: Path,
    caplog: Any,
    run_context: Any,
    external_boundary_mocks_only: Any,
    assert_logs_have_required_fields: Any,
    assert_no_defaulted_required_fields: Any,
) -> None:
    landing_url = "https://example.com/resources/outlook-2026"
    candidate_pdf_url = "https://cdn.example.com/reports/outlook-2026.pdf"
    observed_urls: list[str] = []

    def fake_get(url: str, *args: object, **kwargs: object) -> _FakeResponse:
        _ = (args, kwargs)
        observed_urls.append(url)
        assert url == candidate_pdf_url
        return _FakeResponse(
            content=b"%PDF-1.7 candidate trace pdf bytes",
            headers={"Content-Type": "application/pdf"},
            url=candidate_pdf_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError(
                f"browser runtime should not start for predicted candidate PDF: {module_name}"
            )
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=landing_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url=landing_url,
                title="AI Outlook 2026",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/resources"],
                discovery_provenances=["browser_dom"],
                pdf_url=candidate_pdf_url,
                published_at_text=None,
                max_confidence=0.87,
            ),
        ),
        run_context,
    )

    events = _service_events(caplog)
    prediction_fields = _prediction_fields(events)
    assert prediction_fields["predicted_doc_type"] == "direct_pdf"
    assert prediction_fields["probe_url"] == candidate_pdf_url
    assert prediction_fields["evidence_labels"] == ["candidate_trace_pdf_url"]
    assert observed_urls == [candidate_pdf_url]
    assert response.used_candidate_pdf_url is True
    assert response.route_family == "direct_pdf_probe"
    assert response.downloaded_file_path is not None
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(events)


def test_download_report_falls_back_after_invalid_predicted_candidate_pdf(
    tmp_path: Path,
    caplog: Any,
    run_context: Any,
    external_boundary_mocks_only: Any,
    assert_logs_have_required_fields: Any,
    assert_no_defaulted_required_fields: Any,
) -> None:
    landing_url = "https://example.com/resources/outlook-2026"
    candidate_pdf_url = "https://cdn.example.com/reports/outlook-2026.pdf"
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and save the real PDF after browser fallback.",
        create_pdf=True,
    )
    browser_loaded = {"value": False}

    def fake_get(url: str, *args: object, **kwargs: object) -> _FakeResponse:
        _ = (args, kwargs)
        if url == candidate_pdf_url:
            return _FakeResponse(
                content=b"<html><body>temporary login wall</body></html>",
                headers={"Content-Type": "text/html; charset=utf-8"},
                url=candidate_pdf_url,
            )
        assert url == landing_url
        return _FakeResponse(
            content=b"<html><body><h1>AI Outlook 2026</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=landing_url,
        )

    def load_runtime(module_name: str) -> SimpleNamespace:
        _ = module_name
        browser_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(browser_runtime, "import_module", load_runtime)
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=landing_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url=landing_url,
                title="AI Outlook 2026",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/resources"],
                discovery_provenances=["browser_dom"],
                pdf_url=candidate_pdf_url,
                published_at_text=None,
                max_confidence=0.87,
            ),
        ),
        run_context,
    )

    events = _service_events(caplog)
    prediction_fields = _prediction_fields(events)
    assert prediction_fields["predicted_doc_type"] == "direct_pdf"
    assert browser_loaded["value"] is True
    assert response.route_family == "browser_pdf_click"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(events)


def test_download_report_predicts_report_page_pdf_link_without_route_hint(
    tmp_path: Path,
    caplog: Any,
    run_context: Any,
    external_boundary_mocks_only: Any,
    assert_logs_have_required_fields: Any,
    assert_no_defaulted_required_fields: Any,
) -> None:
    page_url = "https://example.com/research/ai-outlook-2026"
    pdf_url = "https://cdn.example.com/reports/ai-outlook-2026.pdf"
    observed_urls: list[str] = []

    def fake_get(url: str, *args: object, **kwargs: object) -> _FakeResponse:
        _ = (args, kwargs)
        observed_urls.append(url)
        if url == pdf_url:
            return _FakeResponse(
                content=b"%PDF-1.7 predicted report page pdf bytes",
                headers={"Content-Type": "application/pdf"},
                url=pdf_url,
            )
        assert url == page_url
        return _FakeResponse(
            content=(
                b"<html><head><title>AI Outlook 2026 Report</title></head>"
                b"<body><a href=\"https://cdn.example.com/reports/ai-outlook-2026.pdf\">"
                b"Download report PDF</a></body></html>"
            ),
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError(
                f"browser runtime should not start for predicted report-page PDF link: {module_name}"
            )
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    events = _service_events(caplog)
    prediction_fields = _prediction_fields(events)
    assert prediction_fields["predicted_doc_type"] == "report_page_pdf_link"
    assert prediction_fields["predicted_route_family"] == "report_page_pdf_link_probe"
    assert observed_urls == [page_url, pdf_url]
    assert response.route_family == "report_page_pdf_link_probe"
    assert response.outcome == "downloaded"
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(events)
