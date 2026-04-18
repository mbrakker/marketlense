from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import requests

from src.contracts.browser_download import (
    BrowserDownloadIdentity,
    BrowserDownloadIdentityField,
    BrowserDownloadPublisherOverride,
    BrowserDownloadSettings,
    BrowserReportDownloadRequest,
)
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.services._browser_report_download import artifact as artifact_runtime
from src.services._browser_report_download import browser as browser_runtime
from src.services._browser_report_download import http as http_runtime
from src.services._browser_report_download.request import resolve_effective_identity_fields
from src.services import browser_report_download_service as service
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
        ):
            self.downloads_path = str(downloads_path)
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

        def take_screenshot(self, path=None, full_page=False, format="png", quality=None, clip=None):
            if path:
                Path(path).write_bytes(b"fake-screenshot")
            return b"fake-screenshot"

    class FakeChatOpenRouter:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    class FakeAgent:
        def __init__(self, *, task, llm, browser, output_model_schema):
            self.task = task
            self.llm = llm
            self.browser = browser
            self.output_model_schema = output_model_schema

        def run_sync(self, max_steps: int):
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
    ) -> None:
        self._content = content
        self.status_code = status_code
        self.headers = headers or {}

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def iter_content(self, chunk_size: int = 65536):
        for start in range(0, len(self._content), chunk_size):
            yield self._content[start : start + chunk_size]

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"status={self.status_code}")


def test_download_report_with_browser_use_returns_downloaded_pdf(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page, click Download report, and wait for the PDF save to finish.",
        create_pdf=True,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_hint="Click the main download CTA.",
            route_kind_hint="pdf_download",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.used_route_hint is True
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).exists()
    assert response.downloaded_mime_type == "application/pdf"
    assert response.encountered_form_fields == []
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_short_circuits_direct_pdf_url(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"%PDF-1.7 direct pdf bytes",
            headers={"Content-Type": "application/pdf"},
        )

    def fail_if_browser_loaded(module_name: str) -> Any:
        raise AssertionError(f"browser runtime should not load for direct pdf URL: {module_name}")

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        fail_if_browser_loaded,
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://cdn.example.com/reports/outlook-2026.pdf?download=1",
            settings=_settings(tmp_path),
            route_hint="Click the download CTA.",
            route_kind_hint="pdf_download",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.used_route_hint is False
    assert response.final_page_url == "https://cdn.example.com/reports/outlook-2026.pdf?download=1"
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).read_bytes().startswith(b"%PDF-")
    assert response.downloaded_file_name == "outlook-2026.pdf"
    assert response.downloaded_mime_type == "application/pdf"
    assert response.route_summary == "Open the direct PDF URL and save the returned PDF file locally."
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_falls_back_from_invalid_direct_pdf(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page, click Download report, and wait for the PDF save to finish.",
        create_pdf=True,
        email_submission_completed=None,
    )
    browser_loaded = {"value": False}

    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"<html><body>login required</body></html>",
            headers={"Content-Type": "text/html"},
        )

    def load_runtime(module_name: str) -> Any:
        browser_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        load_runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://cdn.example.com/reports/outlook-2026.pdf",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert browser_loaded["value"] is True
    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).exists()
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_fetches_real_pdf_from_wrapper(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and click the PDF link.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class WrapperAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/pdf-wrapper"
            download_dir = Path(self.browser.downloads_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            wrapper_path = download_dir / "report.pdf"
            wrapper_path.write_text(
                (
                    "<head><script>window.location.replace("
                    "'https://cdn.example.com/report.pdf');</script></head>"
                    "<body><embed type='application/pdf' "
                    "src='https://cdn.example.com/report.pdf' /></body>"
                ),
                encoding="utf-8",
            )
            self.browser.downloaded_files = [str(wrapper_path)]
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["downloaded_file_path"] = str(wrapper_path)
            payload["downloaded_file_name"] = wrapper_path.name
            payload["downloaded_mime_type"] = "application/pdf"

            class WrapperHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return WrapperHistory()

    runtime.Agent = WrapperAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"%PDF-1.7 actual pdf bytes",
            headers={"Content-Type": "application/pdf"},
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).read_bytes().startswith(b"%PDF-")
    assert response.downloaded_size_bytes == len(b"%PDF-1.7 actual pdf bytes")
    assert response.downloaded_mime_type == "application/pdf"
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_returns_email_required_without_address(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the gated page and enter an email in the submit form.",
        create_pdf=False,
        email_submission_completed=False,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/email-gated-report",
            settings=_settings(tmp_path, work_email=None),
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.downloaded_file_path is None
    assert response.encountered_form_fields == []
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_returns_encountered_form_fields(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the gated page and inspect the registration form.",
        create_pdf=False,
        email_submission_completed=False,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    original_runtime = runtime.Agent

    class EncounterAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["encountered_form_fields"] = [
                "Name",
                "Business",
                "Email",
                "Email",
            ]

            class EncounterHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return EncounterHistory()

    runtime.Agent = EncounterAgent

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/form-report",
            settings=_settings(tmp_path, work_email=None),
        ),
        run_context,
    )

    assert response.encountered_form_fields == ["Name", "Business", "Email"]


def test_download_report_with_browser_use_reclassifies_email_message(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Fill the form and submit the download request.",
        create_pdf=False,
        email_submission_completed=True,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    original_runtime = runtime.Agent

    class ReclassifyAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["post_submit_message"] = (
                "Thanks. We sent the download link to your email inbox."
            )
            payload["encountered_form_fields"] = [
                "Name",
                "Title / Role",
                "Business / Organization",
                "Email",
            ]

            class ReclassifyHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return ReclassifyHistory()

    runtime.Agent = ReclassifyAgent

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/form-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.downloaded_file_path is None
    assert response.encountered_form_fields == [
        "Name",
        "Title / Role",
        "Business / Organization",
        "Email",
    ]
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_treats_generic_success_text_as_email_requested(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary=(
            "Filled the form fields and submitted the gated report request."
        ),
        create_pdf=False,
        email_submission_completed=True,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    original_runtime = runtime.Agent

    class SuccessTextAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["post_submit_message"] = "Thank you for submitting the form."
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Company Name",
                "Professional Email",
                "Business Phone",
            ]

            class SuccessTextHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return SuccessTextHistory()

    runtime.Agent = SuccessTextAgent

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/form-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.blocked_reason is None


def test_download_report_with_browser_use_requires_semantic_route_summary(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Clicked button.",
        create_pdf=True,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as excinfo:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_route_summary_too_weak",
        retryable=True,
    )


def test_download_report_with_browser_use_returns_email_required_when_confirmation_is_missing(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the form, enter the configured email, submit it, and wait for the confirmation message.",
        create_pdf=False,
        email_submission_completed=True,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/form-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.route_status == "inferred"


def test_download_report_with_browser_use_rejects_conflicting_pdf_metadata(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page, click Download report, and wait for the file save to finish.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class ConflictingMimeAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["downloaded_mime_type"] = "text/html"

            class ConflictingMimeHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return ConflictingMimeHistory()

    runtime.Agent = ConflictingMimeAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as excinfo:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_invalid_pdf_metadata",
        retryable=True,
    )


def test_download_report_with_browser_use_raises_when_pdf_classification_has_no_verifiable_artifact(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page, click the main download CTA, and wait for the PDF save to finish.",
        create_pdf=False,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as excinfo:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/broken-report",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_unverified_pdf_claim",
        retryable=True,
    )


def test_download_report_with_browser_use_adopts_external_pdf_attachment(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the current page as a PDF.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class ExternalAttachmentAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/report"
            self.browser.title = "External attachment report"
            external_dir = tmp_path / "browseruse_agent_data"
            external_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = external_dir / "external-report.pdf"
            pdf_path.write_bytes(b"%PDF-1.7 external attachment")
            payload = {
                "route_kind": "pdf_download",
                "route_summary": "Open the report page and save the current page as a PDF artifact.",
                "final_page_url": "https://example.com/report",
                "resolved_target_url": "https://example.com/report",
                "email_submission_completed": None,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": [],
                "post_submit_message": "",
                "route_steps": [
                    {
                        "index": 0,
                        "action": "navigate",
                        "target_text": "",
                        "target_role": "url",
                        "target_url": "https://example.com/report",
                        "result": "Opened the report landing page",
                    },
                    {
                        "index": 1,
                        "action": "save_as_pdf",
                        "target_text": "external-report.pdf",
                        "target_role": "page",
                        "target_url": "https://example.com/report",
                        "result": "Saved the current page as PDF",
                    },
                ],
            }

            class ExternalAttachmentHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

                def action_results(self_nonlocal) -> list[Any]:
                    return [SimpleNamespace(attachments=[str(pdf_path)])]

            return ExternalAttachmentHistory()

    runtime.Agent = ExternalAttachmentAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    downloaded_path = Path(str(response.downloaded_file_path))
    assert downloaded_path.exists()
    assert downloaded_path.parent != (tmp_path / "browseruse_agent_data")
    assert str(tmp_path / "downloads") in str(downloaded_path)
    assert downloaded_path.read_bytes().startswith(b"%PDF-")


def test_download_report_with_browser_use_raises_for_unverified_pdf_claim_with_spurious_blocker(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Attempted to follow the report links but did not acquire an artifact.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class SpuriousBlockerAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/2026-report"
            self.browser.title = "2026 Report"
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = (
                "The agent could not find the correct report link after multiple attempts."
            )
            payload["terminal_text_excerpt"] = "The 2026 report page is available here."

            class SpuriousBlockerHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

                def action_results(self_nonlocal) -> list[Any]:
                    return []

            return SpuriousBlockerHistory()

    runtime.Agent = SpuriousBlockerAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as excinfo:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/2026-report",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_unverified_pdf_claim",
        retryable=True,
    )


def test_download_report_with_browser_use_raises_for_invalid_pdf_stub(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page, click the main download CTA, and wait for the PDF save to finish.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class InvalidPdfAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/pdf-wrapper"
            download_dir = Path(self.browser.downloads_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            wrapper_path = download_dir / "report.pdf"
            wrapper_path.write_text("<html><body>not a pdf</body></html>", encoding="utf-8")
            self.browser.downloaded_files = [str(wrapper_path)]
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["downloaded_file_path"] = str(wrapper_path)
            payload["downloaded_file_name"] = wrapper_path.name
            payload["downloaded_mime_type"] = "application/pdf"

            class InvalidPdfHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return InvalidPdfHistory()

    runtime.Agent = InvalidPdfAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as excinfo:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_invalid_pdf",
        retryable=True,
    )


def test_download_report_with_browser_use_direct_pdf_skips_browser_config_requirements(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"%PDF-1.7 direct pdf bytes",
            headers={"Content-Type": "application/pdf"},
        )

    def fail_if_browser_loaded(module_name: str) -> Any:
        raise AssertionError(
            f"browser runtime should not load for direct pdf URL: {module_name}"
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        fail_if_browser_loaded,
    )
    settings = _settings(tmp_path)
    settings = BrowserDownloadSettings(
        schema_version=settings.schema_version,
        openrouter_api_key="",
        model="",
        temperature=settings.temperature,
        timeout_seconds=settings.timeout_seconds,
        max_steps=settings.max_steps,
        output_dir=settings.output_dir,
        state_db=settings.state_db,
        reports_db=settings.reports_db,
        identity_config_path=settings.identity_config_path,
        identity_profile=settings.identity_profile,
        openrouter_http_referer=settings.openrouter_http_referer,
        headed=settings.headed,
        retry_retries=settings.retry_retries,
        retry_base_delay_seconds=settings.retry_base_delay_seconds,
        retry_backoff_step_seconds=settings.retry_backoff_step_seconds,
        retry_jitter_seconds=settings.retry_jitter_seconds,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://cdn.example.com/reports/outlook-2026.pdf",
            settings=settings,
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None


def test_download_report_with_browser_use_prefers_candidate_pdf_probe(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/report",
        title="Discovery PDF",
        discovered_on_page_number=1,
        source_page_urls=["https://example.com/insights"],
        discovery_provenances=["direct_pdf_source"],
        pdf_url="https://cdn.example.com/discovery-report.pdf",
        published_at_text=None,
        max_confidence=0.98,
    )

    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"%PDF-1.7 discovery bytes",
            headers={"Content-Type": "application/pdf"},
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("browser runtime should not load for candidate pdf probe")
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            candidate_trace=candidate_trace,
            attempt_url=candidate_trace.pdf_url,
            route_family_hint="direct_pdf_probe",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.used_candidate_pdf_url is True
    assert response.route_family == "direct_pdf_probe"


def test_download_report_with_browser_use_salvages_empty_browser_result_from_candidate_pdf(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/report",
        title="Discovery PDF",
        discovered_on_page_number=1,
        source_page_urls=["https://example.com/insights"],
        discovery_provenances=["browser_dom"],
        pdf_url="https://cdn.example.com/discovery-report.pdf",
        published_at_text=None,
        max_confidence=0.91,
    )
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the page and click the report CTA.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class EmptyAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/report/final"

            class EmptyHistory:
                def final_result(self_nonlocal) -> str:
                    return ""

            return EmptyHistory()

    runtime.Agent = EmptyAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            content=b"%PDF-1.7 discovery salvage",
            headers={"Content-Type": "application/pdf"},
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            candidate_trace=candidate_trace,
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.browser_had_structured_result is False
    assert response.used_candidate_pdf_url is True


def test_download_report_with_browser_use_logs_discovery_prompt_context(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://trk.example.com/campaign?id=123",
        title="Tracker Candidate",
        discovered_on_page_number=2,
        source_page_urls=["https://example.com/insights"],
        discovery_provenances=["browser_dom"],
        pdf_url=None,
        published_at_text=None,
        max_confidence=0.73,
    )
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the source page, click the report link, and download the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=candidate_trace.canonical_url,
            settings=_settings(tmp_path),
            candidate_trace=candidate_trace,
            attempt_url="https://example.com/insights",
            route_family_hint="browser_tracker_redirect",
            source_page_url_hint="https://example.com/insights",
            publisher_discovery_route_kind="browser_render",
            publisher_recommended_discovery_route_kind="browser_render",
        ),
        run_context,
    )

    prompt_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == service.logger.name
        and json.loads(record.message).get("event")
        == "browser_report_download_prompt_prepared"
    ]
    assert len(prompt_events) == 1
    fields = prompt_events[0]["fields"]
    assert fields["candidate_canonical_url"] == candidate_trace.canonical_url
    assert fields["candidate_source_page_urls"] == ["https://example.com/insights"]
    assert fields["publisher_recommended_discovery_route_kind"] == "browser_render"
    assert "redirect" in fields["route_family_guidance"].casefold()
    assert "https://example.com/insights" in fields["rendered_user_prompt"]


def test_download_report_with_browser_use_logs_onsite_prompt_guidance(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/research/market-outlook-2026",
        title="Market Outlook 2026",
        discovered_on_page_number=1,
        source_page_urls=["https://example.com/research"],
        discovery_provenances=["browser_dom"],
        pdf_url=None,
        published_at_text=None,
        max_confidence=0.82,
    )
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report page, capture the article locally, and verify completeness.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class OnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            onsite_path = Path(self.browser.downloads_path) / "onsite-report.html"
            onsite_path.write_text("<article><h1>Market Outlook</h1><p>Longread body.</p></article>", encoding="utf-8")
            payload["onsite_capture_path"] = str(onsite_path)
            payload["onsite_capture_format"] = "html"
            payload["onsite_page_count"] = 1
            payload["onsite_completeness_status"] = "complete"

            class OnsiteHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return OnsiteHistory()

    runtime.Agent = OnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=candidate_trace.canonical_url,
            settings=_settings(tmp_path),
            candidate_trace=candidate_trace,
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    prompt_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == service.logger.name
        and json.loads(record.message).get("event")
        == "browser_report_download_prompt_prepared"
    ]
    assert len(prompt_events) == 1
    fields = prompt_events[0]["fields"]
    assert "on-site content" in fields["route_family_guidance"].casefold()
    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"


def test_download_report_with_browser_use_recovers_embedded_pdf_from_encoded_wrapper(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and click the wrapped PDF link.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class EncodedWrapperAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/report"
            self.browser.title = "Wrapped report"
            download_dir = Path(self.browser.downloads_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            wrapper_path = download_dir / "report.pdf"
            wrapper_path.write_text(
                (
                    "<html><body><iframe "
                    "src=\"/viewer?downloadData=https%3A%2F%2Fcdn.example.com%2Freal-report.pdf\">"
                    "</iframe></body></html>"
                ),
                encoding="utf-8",
            )
            self.browser.downloaded_files = [str(wrapper_path)]
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["downloaded_file_path"] = str(wrapper_path)
            payload["downloaded_file_name"] = wrapper_path.name
            payload["downloaded_mime_type"] = "application/pdf"

            class EncodedWrapperHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return EncodedWrapperHistory()

    runtime.Agent = EncodedWrapperAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            content=b"%PDF-1.7 recovered bytes",
            headers={"Content-Type": "application/pdf"},
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).read_bytes().startswith(b"%PDF-")


def test_download_report_with_browser_use_salvages_empty_result_to_email_required(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the gated report page and inspect the form.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class EmptyEmailAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/gated-report"
            self.browser.title = "Download the report"
            self.browser.html = (
                "<html><body><form>"
                "<label>Email</label><input name='email' />"
                "<label>Industry</label><select name='industry'></select>"
                "<button type='submit'>Submit</button>"
                "</form></body></html>"
            )

            class EmptyHistory:
                def final_result(self_nonlocal) -> str:
                    return ""

            return EmptyHistory()

    runtime.Agent = EmptyEmailAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/gated-report",
            settings=_settings(tmp_path, work_email=None),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason in {
        "blocked_missing_identity_field",
        "blocked_unknown_required_enum",
    }
    assert "Email" in response.encountered_form_fields


def test_download_report_with_browser_use_normalizes_blocked_route_kind_to_email_delivery(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="blocked_unknown_required_enum",
        route_summary="",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class BlockedKindAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/gated-report"
            self.browser.title = "Download report"
            self.browser.html = (
                "<html><body><form>"
                "<label>Industry</label><select name='industry'></select>"
                "<button type='submit'>Download</button>"
                "</form></body></html>"
            )
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["route_kind"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = "Industry selection is required."
            payload["terminal_text_excerpt"] = "Industry selection is required."

            class BlockedKindHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return BlockedKindHistory()

    runtime.Agent = BlockedKindAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/gated-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_unknown_required_enum"
    assert response.blocked_reason_detail == "Industry selection is required."


def test_download_report_with_browser_use_prefers_form_evidence_over_onsite_hint(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary=(
            "Accepted cookies, filled form fields, and clicked submit on the gated page."
        ),
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class OnsiteHintEmailAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/research/report"
            self.browser.title = "Request the report"
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["route_kind"] = "onsite_report"
            payload["encountered_form_fields"] = ["Business Email", "Industry"]
            payload["submit_button_state"] = "disabled"
            payload["post_submit_message"] = "Please use a business email address."
            payload["blocked_reason"] = "blocked_email_domain"

            class OnsiteHintEmailHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return OnsiteHintEmailHistory()

    runtime.Agent = OnsiteHintEmailAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_email_domain"


def test_download_report_with_browser_use_maps_company_name_and_professional_email_without_false_blocker(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form and submitted it successfully.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class AliasAwareAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["post_submit_message"] = "Thank you for submitting the form."
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Company Name",
                "Professional Email",
                "Business Phone",
                "Country",
            ]

            class AliasAwareHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return AliasAwareHistory()

    runtime.Agent = AliasAwareAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/gated-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.blocked_reason is None


def test_download_report_with_browser_use_salvages_empty_result_to_onsite_capture(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the longread report page and capture the article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class EmptyOnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/research/market-outlook-2026"
            self.browser.title = "Market Outlook 2026 report"
            self.browser.html = (
                "<html><body><article><h1>Market Outlook 2026 report</h1>"
                "<h2>Executive summary</h2><p>" + ("Longread body. " * 300) + "</p>"
                "<h2>Methodology</h2><p>" + ("More body. " * 120) + "</p>"
                "</article></body></html>"
            )

            class EmptyHistory:
                def final_result(self_nonlocal) -> str:
                    return ""

            return EmptyHistory()

    runtime.Agent = EmptyOnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/market-outlook-2026",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    assert Path(str(response.onsite_capture_path)).exists()


def test_download_report_with_browser_use_records_terminal_snapshot_and_document_urls(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report and download the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class EvidenceRichAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.network_resource_urls = [
                "https://cdn.example.com/reports/final-report.pdf",
                "https://cdn.example.com/reports/final-report.pdf",
            ]
            self.browser.html = (
                "<html><head><meta property='og:url' content='https://cdn.example.com/reports/final-report.pdf' /></head>"
                "<body><h1>Example report terminal</h1></body></html>"
            )
            return super().run_sync(max_steps)

    runtime.Agent = EvidenceRichAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.terminal_evidence.html_snapshot_path
    assert Path(response.terminal_evidence.html_snapshot_path).exists()
    assert response.terminal_evidence.screenshot_path
    assert Path(response.terminal_evidence.screenshot_path).exists()
    assert "https://cdn.example.com/reports/final-report.pdf" in response.terminal_evidence.observed_document_urls
    assert response.terminal_evidence.network_events
    assert response.terminal_evidence.network_events[0].signal_kind == "document_request"
    assert response.terminal_evidence.visited_url_timeline


def test_download_report_with_browser_use_uses_network_confirmation_signal(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Fill the form, submit it, and verify the terminal state.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class NetworkConfirmedAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            self.browser.network_events = [
                {
                    "url": "https://example.com/forms/submit",
                    "initiator_type": "fetch",
                },
                {
                    "url": "https://example.com/report/thank-you",
                    "initiator_type": "navigation",
                },
            ]
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["route_family"] = "browser_email_form"
            payload["final_page_url"] = "https://example.com/report"
            payload["resolved_target_url"] = "https://example.com/report"
            payload["post_submit_message"] = ""
            payload["confirmation_url_changed"] = False
            payload["submit_button_state"] = ""
            payload["form_disappeared"] = False

            class NetworkConfirmedHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return NetworkConfirmedHistory()

    runtime.Agent = NetworkConfirmedAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert "network_confirmation_request" in response.confirmation_evidence.signal_labels
    assert any(
        event.signal_kind == "confirmation_request"
        for event in response.terminal_evidence.network_events
    )


def test_download_report_with_browser_use_falls_back_to_page_screenshot(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report and download the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class PageScreenshotAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            self.browser.take_screenshot = lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("browser screenshot failed")
            )

            class AsyncPage:
                url = "https://example.com/final"

                async def title(self_nonlocal):
                    return "Example report terminal"

                async def content(self_nonlocal):
                    return "<html><body><h1>Example report terminal</h1></body></html>"

                async def evaluate(self_nonlocal, script):
                    return []

                async def screenshot(self_nonlocal, path=None, full_page=False):
                    if path:
                        Path(path).write_bytes(b"page-screenshot")
                    return b"page-screenshot"

            async def get_current_page():
                return AsyncPage()

            self.browser.get_current_page = get_current_page
            return history

    runtime.Agent = PageScreenshotAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.terminal_evidence.screenshot_path
    assert Path(response.terminal_evidence.screenshot_path).exists()


def test_download_report_with_browser_use_parses_stringified_page_evaluate_payloads(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report and download the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class JsonStringEvaluateAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            self.browser.url = ""
            self.browser.title = ""
            self.browser.html = ""

            class AsyncPage:
                async def title(self_nonlocal):
                    return "Example report terminal"

                async def content(self_nonlocal):
                    return (
                        "<html><head><meta property='og:url' "
                        "content='https://cdn.example.com/reports/final-report.pdf' /></head>"
                        "<body><h1>Example report terminal</h1></body></html>"
                    )

                async def evaluate(self_nonlocal, script):
                    source = str(script)
                    if "navigationEntries" in source:
                        return json.dumps(
                            [
                                {
                                    "url": "https://example.com/report/thank-you",
                                    "initiator_type": "navigation",
                                },
                                {
                                    "url": "https://cdn.example.com/reports/final-report.pdf",
                                    "initiator_type": "fetch",
                                },
                            ]
                        )
                    if "document.querySelectorAll" in source:
                        return json.dumps(
                            [
                                "https://cdn.example.com/reports/final-report.pdf",
                            ]
                        )
                    return json.dumps(
                        [
                            "https://cdn.example.com/reports/final-report.pdf",
                        ]
                    )

                async def screenshot(self_nonlocal, path=None, full_page=False):
                    if path:
                        Path(path).write_bytes(b"page-screenshot")
                    return b"page-screenshot"

            async def get_current_page():
                return AsyncPage()

            async def get_current_page_url():
                return "https://example.com/report/thank-you"

            async def get_current_page_title():
                return "Example report terminal"

            self.browser.get_current_page = get_current_page
            self.browser.get_current_page_url = get_current_page_url
            self.browser.get_current_page_title = get_current_page_title
            return history

    runtime.Agent = JsonStringEvaluateAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.final_page_url == "https://example.com/report/thank-you"
    assert response.terminal_evidence.final_page_title == "Example report terminal"
    assert response.terminal_evidence.network_events
    assert any(
        event.signal_kind == "confirmation_request"
        for event in response.terminal_evidence.network_events
    )
    assert "https://cdn.example.com/reports/final-report.pdf" in response.terminal_evidence.observed_document_urls


def test_download_report_with_browser_use_falls_back_to_history_terminal_state(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form and submitted it successfully.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class HistoryStateAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            self.browser.url = ""
            self.browser.title = ""
            self.browser.html = ""
            self.browser.take_screenshot = lambda *args, **kwargs: (_ for _ in ()).throw(
                RuntimeError("browser screenshot failed")
            )

            def raise_current_page():
                raise RuntimeError("browser session already reset")

            self.browser.get_current_page = raise_current_page
            screenshot_source = Path(self.browser.downloads_path) / "history-step.png"
            screenshot_source.write_bytes(b"history-screenshot")
            payload = json.loads(history.final_result())
            payload["post_submit_message"] = (
                "A copy of the report will be sent to your inbox shortly."
            )
            payload["final_page_title"] = ""
            payload["terminal_text_excerpt"] = ""

            class HistoryWithState:
                history = [
                    SimpleNamespace(
                        state=SimpleNamespace(
                            url="https://example.com/report/thank-you",
                            title="Thank you for downloading the report",
                            screenshot_path=str(screenshot_source),
                        )
                    )
                ]

                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return HistoryWithState()

    runtime.Agent = HistoryStateAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.final_page_url == "https://example.com/report/thank-you"
    assert response.terminal_evidence.final_page_title == "Thank you for downloading the report"
    assert response.terminal_evidence.screenshot_path
    assert Path(response.terminal_evidence.screenshot_path).exists()


def test_download_report_with_browser_use_stabilizes_transient_submit_state(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Fill the form, submit it, and wait for the email-delivery terminal state.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class StabilizingAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["route_family"] = "browser_email_form"
            payload["post_submit_message"] = "Please Wait"
            payload["submit_button_state"] = "disabled"
            payload["encountered_form_fields"] = [
                "First Name",
                "Company",
                "Professional Email",
            ]
            snapshots = [
                {
                    "url": "https://example.com/report",
                    "title": "Example report",
                    "html": (
                        "<html><body><form><button disabled>Please Wait</button></form></body></html>"
                    ),
                },
                {
                    "url": "https://example.com/report/thank-you",
                    "title": "Thank you for downloading the report",
                    "html": (
                        "<html><body><h1>Thank you for downloading the report</h1>"
                        "<p>Check your email inbox for the download link.</p></body></html>"
                    ),
                },
            ]
            state = {"index": 0}

            class AsyncPage:
                def __init__(self, snapshot: dict[str, str]):
                    self.url = snapshot["url"]
                    self._title = snapshot["title"]
                    self._html = snapshot["html"]

                async def get_title(self_nonlocal):
                    return self_nonlocal._title

                async def content(self_nonlocal):
                    return self_nonlocal._html

                async def evaluate(self_nonlocal, script):
                    source = str(script)
                    if "navigationEntries" in source:
                        return []
                    if "document.querySelectorAll" in source:
                        return []
                    return []

                async def screenshot(self_nonlocal, path=None, full_page=False):
                    if path:
                        Path(path).write_bytes(b"page-screenshot")
                    return b"page-screenshot"

            def current_page_factory():
                snapshot = snapshots[min(state["index"], len(snapshots) - 1)]
                state["index"] += 1
                return AsyncPage(snapshot)

            self.browser.url = ""
            self.browser.title = ""
            self.browser.html = ""
            self.browser.current_page_factory = current_page_factory

            class StabilizingHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return StabilizingHistory()

    runtime.Agent = StabilizingAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(browser_runtime.time, "sleep", lambda _: None)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.final_page_url == "https://example.com/report/thank-you"
    assert response.terminal_evidence.final_page_title == "Thank you for downloading the report"
    assert "success_url" in response.confirmation_evidence.signal_labels


def test_download_report_with_browser_use_clears_phantom_pdf_metadata_without_file(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Fill the form, submit it, and wait for the email-delivery terminal state.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class PhantomPdfAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["route_family"] = "browser_email_form"
            payload["downloaded_file_path"] = str(
                Path(self.browser.downloads_path) / "missing.pdf"
            )
            payload["downloaded_file_name"] = "missing.pdf"
            payload["downloaded_mime_type"] = "application/pdf"
            payload["post_submit_message"] = (
                "A copy of the report will be sent to your email inbox shortly."
            )

            class PhantomHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return PhantomHistory()

    runtime.Agent = PhantomPdfAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.outcome == "email_requested"
    assert response.downloaded_file_path is None
    assert response.downloaded_mime_type is None


def test_resolve_effective_identity_fields_hydrates_semantic_alias_values(tmp_path: Path) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/form",
        settings=BrowserDownloadSettings(
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
                        aliases=["email", "business email"],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="company",
                        label="Company",
                        value="Market Lense",
                        aliases=["organization"],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="professional_email",
                        label="Professional Email",
                        value=None,
                        aliases=[],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="company_name",
                        label="Company Name",
                        value=None,
                        aliases=[],
                    ),
                ],
            ),
            headed=False,
        ),
    )

    effective = resolve_effective_identity_fields(request)
    by_key = {field.key: field for field in effective}

    assert by_key["professional_email"].value == "ops@example.com"
    assert by_key["company_name"].value == "Market Lense"


def test_resolve_effective_identity_fields_applies_publisher_override_values(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
        settings=BrowserDownloadSettings(
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
                        key="online_annual_revenue",
                        label="Online Annual Revenue",
                        value=None,
                        aliases=["projected annual revenue"],
                    ),
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="country",
                        label="Country",
                        value="Austria",
                        aliases=["country"],
                    ),
                ],
                publisher_overrides=[
                    BrowserDownloadPublisherOverride(
                        schema_version="1.0",
                        host_pattern="bigcommerce.com",
                        field_values=[
                            BrowserDownloadIdentityField(
                                schema_version="1.0",
                                key="online_annual_revenue",
                                label="Online Annual Revenue",
                                value="Building a business: $50K to $250K",
                                aliases=[
                                    "projected annual revenue",
                                    "projected annual online revenue",
                                ],
                            )
                        ],
                    )
                ],
            ),
            headed=False,
        ),
    )

    effective = resolve_effective_identity_fields(request)
    by_key = {field.key: field for field in effective}

    assert by_key["online_annual_revenue"].value == "Building a business: $50K to $250K"
    assert by_key["country"].value == "Austria"


def test_download_report_with_browser_use_infers_bounded_incomplete_for_weak_onsite_capture(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report page and capture the article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class WeakOnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/research/report-2026"
            self.browser.title = "Research report 2026"
            self.browser.html = (
                "<html><body><article><h1>Research report 2026</h1>"
                "<p>Short introduction only.</p></article></body></html>"
            )
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["route_kind"] = "onsite_report"
            payload["onsite_capture_path"] = str(
                Path(self.browser.downloads_path) / "onsite-report.html"
            )
            Path(payload["onsite_capture_path"]).write_text(
                self.browser.html,
                encoding="utf-8",
            )
            payload["onsite_capture_format"] = "html"
            payload["onsite_page_count"] = 1
            payload["onsite_completeness_status"] = ""
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "navigate",
                    "target_text": "report",
                    "target_role": "page",
                    "target_url": "https://example.com/research/report-2026",
                    "result": "opened",
                }
            ]
            payload["traversed_page_urls"] = [
                "https://example.com/research/report-2026"
            ]

            class WeakOnsiteHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return WeakOnsiteHistory()

    runtime.Agent = WeakOnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/report-2026",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_completeness_status == "bounded_incomplete"
    assert response.route_status == "inferred"


def test_download_report_with_browser_use_auto_captures_onsite_html_when_agent_omits_capture_path(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report page and capture the article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class MissingCaptureAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/research/report-2026"
            self.browser.title = "Research report 2026"
            self.browser.html = (
                "<html><body><article><h1>Research report 2026</h1>"
                "<h2>Executive summary</h2><p>" + ("Longread body. " * 180) + "</p>"
                "<h2>Methodology</h2><p>" + ("More report detail. " * 120) + "</p>"
                "</article></body></html>"
            )
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["route_kind"] = "onsite_report"
            payload["onsite_capture_path"] = None
            payload["onsite_capture_format"] = None
            payload["onsite_page_count"] = None
            payload["onsite_completeness_status"] = ""
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/research/report-2026",
                    "result": "Scrolled down 950px",
                },
                {
                    "index": 1,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/research/report-2026",
                    "result": "Scrolled down 950px",
                },
                {
                    "index": 2,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/research/report-2026",
                    "result": "Scrolled down 950px",
                },
            ]
            payload["traversed_page_urls"] = [
                "https://example.com/research/report-2026"
            ]

            class MissingCaptureHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return MissingCaptureHistory()

    runtime.Agent = MissingCaptureAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/report-2026",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    assert Path(str(response.onsite_capture_path)).exists()
    assert response.onsite_capture_format == "html"


def test_download_report_with_browser_use_marks_paginated_onsite_capture_partial_without_full_traversal(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report pages and capture the article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class PartialPaginationAgent(original_runtime):
        def run_sync(self, max_steps: int):
            combined_html = (
                "<html><body><article><h1>Global industry report</h1>"
                "<h2>Executive summary</h2><p>" + ("Page one content. " * 140) + "</p>"
                "<h2>Market outlook</h2><p>" + ("Page two content. " * 140) + "</p>"
                "</article></body></html>"
            )
            payload = json.loads(super().run_sync(max_steps).final_result())
            self.browser.url = "https://example.com/report?page=2"
            self.browser.title = "Global industry report"
            self.browser.html = combined_html
            payload["route_kind"] = "onsite_report"
            payload["final_page_url"] = "https://example.com/report?page=2"
            payload["onsite_capture_path"] = str(
                Path(self.browser.downloads_path) / "onsite-report.html"
            )
            Path(payload["onsite_capture_path"]).write_text(
                combined_html,
                encoding="utf-8",
            )
            payload["onsite_capture_format"] = "html"
            payload["onsite_page_count"] = 3
            payload["onsite_completeness_status"] = ""
            payload["traversed_page_urls"] = [
                "https://example.com/report?page=1",
                "https://example.com/report?page=2",
            ]
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "navigate",
                    "target_text": "Page 1",
                    "target_role": "page",
                    "target_url": "https://example.com/report?page=1",
                    "result": "opened",
                },
                {
                    "index": 1,
                    "action": "click",
                    "target_text": "Next page",
                    "target_role": "button",
                    "target_url": "https://example.com/report?page=2",
                    "result": "Opened page 2",
                },
            ]

            class PartialPaginationHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return PartialPaginationHistory()

    runtime.Agent = PartialPaginationAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report?page=1",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_completeness_status == "partial"
    assert response.route_status == "inferred"


def test_download_report_with_browser_use_marks_paginated_onsite_capture_complete_after_final_page(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report pages and capture the article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class CompletePaginationAgent(original_runtime):
        def run_sync(self, max_steps: int):
            combined_html = (
                "<html><body><article><h1>Global industry report</h1>"
                "<h2>Executive summary</h2><p>" + ("Page one content. " * 140) + "</p>"
                "<h2>Market outlook</h2><p>" + ("Page two content. " * 140) + "</p>"
                "<h2>Recommendations</h2><p>" + ("Page three content. " * 140) + "</p>"
                "</article></body></html>"
            )
            payload = json.loads(super().run_sync(max_steps).final_result())
            self.browser.url = "https://example.com/report?page=3"
            self.browser.title = "Global industry report"
            self.browser.html = combined_html
            payload["route_kind"] = "onsite_report"
            payload["final_page_url"] = "https://example.com/report?page=3"
            payload["onsite_capture_path"] = str(
                Path(self.browser.downloads_path) / "onsite-report.html"
            )
            Path(payload["onsite_capture_path"]).write_text(
                combined_html,
                encoding="utf-8",
            )
            payload["onsite_capture_format"] = "html"
            payload["onsite_page_count"] = 3
            payload["onsite_completeness_status"] = ""
            payload["traversed_page_urls"] = [
                "https://example.com/report?page=1",
                "https://example.com/report?page=2",
                "https://example.com/report?page=3",
            ]
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "navigate",
                    "target_text": "Page 1",
                    "target_role": "page",
                    "target_url": "https://example.com/report?page=1",
                    "result": "opened",
                },
                {
                    "index": 1,
                    "action": "click",
                    "target_text": "Next page",
                    "target_role": "button",
                    "target_url": "https://example.com/report?page=2",
                    "result": "Opened page 2",
                },
                {
                    "index": 2,
                    "action": "click",
                    "target_text": "Next page",
                    "target_role": "button",
                    "target_url": "https://example.com/report?page=3",
                    "result": "Reached page 3 of 3",
                },
            ]

            class CompletePaginationHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return CompletePaginationHistory()

    runtime.Agent = CompletePaginationAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report?page=1",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_completeness_status == "complete"
    assert response.route_status == "verified"


def test_download_report_with_browser_use_prefers_onsite_capture_over_optional_form_submission(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the optional form on the longread page and clicked submit.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class OnsiteLongreadAgent(original_runtime):
        def run_sync(self, max_steps: int):
            longread_html = (
                "<html><body><article>"
                "<h1>Global innovation outlook report</h1>"
                "<h2>Executive summary</h2>"
                "<p>" + ("Report analysis section. " * 120) + "</p>"
                "<h2>Methodology</h2>"
                "<p>" + ("Detailed report findings. " * 120) + "</p>"
                "</article></body></html>"
            )

            class AsyncPage:
                url = "https://example.com/insights/global-innovation-outlook"

                async def title(self_nonlocal):
                    return "Global innovation outlook report"

                async def content(self_nonlocal):
                    return longread_html

                async def evaluate(self_nonlocal, script):
                    if "getEntriesByType" in script:
                        return [
                            "https://example.com/insights/global-innovation-outlook",
                        ]
                    return longread_html

            async def get_current_page():
                return AsyncPage()

            history = super().run_sync(max_steps)
            self.browser.url = "https://example.com/insights/global-innovation-outlook"
            self.browser.title = ""
            self.browser.html = ""
            self.browser.get_current_page = get_current_page
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["route_family"] = "browser_onsite_report"
            payload["final_page_url"] = "https://example.com/insights/global-innovation-outlook"
            payload["final_page_title"] = "Global innovation outlook report"
            payload["encountered_form_fields"] = ["Full name", "Work email"]
            payload["post_submit_message"] = "Thank you for submitting the form."
            payload["traversed_page_urls"] = [
                "https://example.com/insights/global-innovation-outlook"
            ]
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Scrolled down 950px",
                },
                {
                    "index": 1,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Scrolled down 950px",
                },
                {
                    "index": 2,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Scrolled down 950px",
                },
                {
                    "index": 3,
                    "action": "click",
                    "target_text": "Submit",
                    "target_role": "button",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Clicked button \"Submit\"",
                },
            ]

            class OnsiteHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return OnsiteHistory()

    runtime.Agent = OnsiteLongreadAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/insights/global-innovation-outlook",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    assert Path(str(response.onsite_capture_path)).exists()
    assert response.terminal_evidence.html_snapshot_path
    assert response.terminal_evidence.dom_snapshot_sha256


def test_download_report_with_browser_use_fetches_onsite_html_when_browser_html_is_missing(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Scrolled through the article and submitted the optional form.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class HtmlMissingOnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            self.browser.url = "https://example.com/insights/global-innovation-outlook"
            self.browser.title = ""
            self.browser.html = ""
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["route_family"] = "browser_onsite_report"
            payload["final_page_url"] = "https://example.com/insights/global-innovation-outlook"
            payload["final_page_title"] = "Global innovation outlook report"
            payload["post_submit_message"] = "Thank you for submitting the form."
            payload["encountered_form_fields"] = ["Full name", "Work email"]
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Scrolled down 900px",
                },
                {
                    "index": 1,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Scrolled down 900px",
                },
                {
                    "index": 2,
                    "action": "click",
                    "target_text": "Submit",
                    "target_role": "button",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Clicked button",
                },
            ]

            class HtmlMissingOnsiteHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return HtmlMissingOnsiteHistory()

    runtime.Agent = HtmlMissingOnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        artifact_runtime,
        "fetch_html_from_url",
        lambda **kwargs: (
            "<html><body><article><h1>Global innovation outlook report</h1>"
            "<h2>Executive summary</h2><p>" + ("Report section. " * 120) + "</p>"
            "<h2>Methodology</h2><p>" + ("More report content. " * 120) + "</p>"
            "</article></body></html>"
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/insights/global-innovation-outlook",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.blocked_reason is None
    assert response.onsite_capture_path is not None


def test_download_report_with_browser_use_fetches_terminal_html_for_email_delivery_when_browser_html_is_missing(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form and submitted it successfully.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class HtmlMissingEmailAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            self.browser.url = "https://example.com/report/thank-you"
            self.browser.title = ""
            self.browser.html = ""
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["final_page_url"] = "https://example.com/report/thank-you"
            payload["resolved_target_url"] = "https://example.com/report/thank-you"
            payload["final_page_title"] = ""
            payload["post_submit_message"] = (
                "Thank you. A copy of the report will be sent to your inbox shortly."
            )
            payload["terminal_text_excerpt"] = ""
            payload["encountered_form_fields"] = ["Business Email", "Country"]

            class HtmlMissingEmailHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return HtmlMissingEmailHistory()

    runtime.Agent = HtmlMissingEmailAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        artifact_runtime,
        "fetch_html_from_url",
        lambda **kwargs: (
            "<html><head><title>Thank you for downloading the report</title></head>"
            "<body><main><h1>Thank you</h1>"
            "<p>A copy of the report will be sent to your inbox shortly.</p>"
            "</main></body></html>"
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.terminal_evidence.html_snapshot_path
    assert Path(response.terminal_evidence.html_snapshot_path).exists()
    assert response.terminal_evidence.dom_snapshot_sha256
    assert response.final_page_url == "https://example.com/report/thank-you"
    assert response.terminal_evidence.final_page_title == "Thank you for downloading the report"


def test_download_report_with_browser_use_infers_form_disappeared_from_fetched_terminal_html(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form and clicked submit.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class SparseTerminalAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Business Email",
                "Company Name",
                "Online Annual Revenue",
                "Country",
            ]
            payload["post_submit_message"] = ""
            payload["submit_button_state"] = ""
            payload["form_disappeared"] = None
            payload["confirmation_url_changed"] = None
            payload["final_page_title"] = ""
            payload["terminal_text_excerpt"] = ""

            class SparseTerminalHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return SparseTerminalHistory()

    runtime.Agent = SparseTerminalAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        artifact_runtime,
        "fetch_html_from_url",
        lambda **kwargs: (
            "<html><body><h1>Thanks</h1>"
            "<p>A copy of the report will be sent directly to your inbox shortly.</p>"
            "</body></html>"
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.confirmation_evidence.form_disappeared is True
    assert response.confirmation_evidence.confirmation_score >= 2
    assert "form_disappeared" in response.confirmation_evidence.signal_labels


def test_download_report_with_browser_use_prefers_delivery_confirmation_over_conflicting_blocker(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form and submitted it successfully.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class ConflictingBlockerAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Business Email",
                "Company Name",
                "Online Annual Revenue",
                "Country",
            ]
            payload["post_submit_message"] = (
                "A copy of the report will be sent directly to your inbox shortly."
            )
            payload["submit_button_state"] = "disabled"
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = "Online Annual Revenue is required."

            class ConflictingBlockerHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return ConflictingBlockerHistory()

    runtime.Agent = ConflictingBlockerAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.blocked_reason is None
    assert response.blocked_reason_detail is None
    assert response.confirmation_evidence.confirmation_score >= 2


def test_download_report_with_browser_use_normalizes_text_field_blocker_to_missing_identity(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Opened the report page, attempted the form, and stopped at the blocker.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class TextFieldBlockerAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["route_kind"] = "pdf_download"
            payload["route_family"] = "browser_pdf_click"
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Business Email",
                "Company Name",
                "Phone",
                "Company Website",
            ]
            payload["post_submit_message"] = (
                "Form submission failed because the company website field is required."
            )
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = (
                "Company Website is required before submission."
            )
            payload["terminal_text_excerpt"] = (
                "Fill out the form below to have your copy sent directly to your inbox."
            )

            class TextFieldBlockerHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return TextFieldBlockerHistory()

    runtime.Agent = TextFieldBlockerAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.route_family == "browser_email_form"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_missing_identity_field"
    assert "Company Website is required" in str(response.blocked_reason_detail)


def test_download_report_with_browser_use_does_not_infer_static_archive_from_please_wait(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form and clicked submit.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class PendingSubmitAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Business Email",
                "Company Name",
                "Online Annual Revenue",
                "Country",
            ]
            payload["post_submit_message"] = "Please Wait"
            payload["submit_button_state"] = "disabled"
            payload["terminal_text_excerpt"] = (
                "Fill out the form below to have your copy sent directly to your inbox."
            )

            class PendingSubmitHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return PendingSubmitHistory()

    runtime.Agent = PendingSubmitAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason != "blocked_static_archive"


def test_download_report_with_browser_use_does_not_infer_blocker_from_onsite_article_text(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Captured the on-site report article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class OnsiteBodyAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            onsite_path = Path(self.browser.downloads_path) / "onsite-report.md"
            onsite_path.write_text("# Report\n\nBody", encoding="utf-8")
            payload["route_kind"] = "onsite_report"
            payload["onsite_capture_path"] = str(onsite_path)
            payload["onsite_capture_format"] = "markdown"
            payload["onsite_page_count"] = 1
            payload["onsite_completeness_status"] = "complete"
            payload["final_page_title"] = "Global Soft Power Index"
            payload["terminal_text_excerpt"] = (
                "Among member states, innovation perceptions remain strong. "
                "See Legal Archives in the footer for historical notices."
            )

            class OnsiteBodyHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return OnsiteBodyHistory()

    runtime.Agent = OnsiteBodyAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://brandfinance.com/insights/global-soft-power-index-which-nations-lead-global-perceptions-of-innovation-in-2026",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.blocked_reason is None
    assert response.blocked_reason_detail is None
