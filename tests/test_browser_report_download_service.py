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
    BrowserDownloadSettings,
    BrowserReportDownloadRequest,
)
from src.contracts.publisher_inventory import PublisherInventoryCandidateTrace
from src.services._browser_report_download import browser as browser_runtime
from src.services._browser_report_download import http as http_runtime
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

    class FakeHistory:
        def final_result(self) -> str:
            return json.dumps(payload)

    class FakeBrowser:
        def __init__(self, downloads_path, headless, auto_download_pdfs):
            self.downloads_path = str(downloads_path)
            self.headless = headless
            self.auto_download_pdfs = auto_download_pdfs
            self.url = ""
            self.downloaded_files: list[str] = []

        async def kill(self) -> None:
            return None

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
            download_dir = Path(self.browser.downloads_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            if create_pdf:
                pdf_path = download_dir / "report.pdf"
                pdf_path.write_bytes(b"%PDF-1.7 test")
                self.browser.downloaded_files = [str(pdf_path)]
                payload["downloaded_file_path"] = str(pdf_path)
                payload["downloaded_file_name"] = pdf_path.name
                payload["downloaded_mime_type"] = "application/pdf"
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


def test_download_report_with_browser_use_requires_visible_email_confirmation(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
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

    with pytest.raises(AppError) as excinfo:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/form-report",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_email_confirmation_missing",
        retryable=True,
    )


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


def test_download_report_with_browser_use_raises_when_pdf_classification_has_no_file(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Click the report download CTA.",
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
        code="browser_download_missing_file",
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
        route_summary="Click the report download CTA.",
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
    assert "https://example.com/insights" in fields["rendered_user_prompt"]
