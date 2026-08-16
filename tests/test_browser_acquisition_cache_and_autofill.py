from __future__ import annotations

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
from src.services._browser_report_download.prompt import BrowserDownloadPromptBundle
from src.services.browser_report_download_service import (
    _artifact_cache_key,
    _normalized_report_title,
    _publisher_scope,
    download_report_with_browser_use,
    try_deterministic_browser_route_playbooks,
)
from src.services.state_service import record_artifact_acquisition_cache
from tests.test_browser_report_download_service.builders import _settings


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _valid_pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj <</Type/Catalog>> endobj\n%%EOF\n"


def test_browser_download_reuses_valid_artifact_acquisition_cache(
    tmp_path: Path, external_boundary_mocks_only
):
    import src.services.browser_report_download_service as browser_download_service

    def fail_if_browser_is_called(**_kwargs):
        raise AssertionError("browser boundary must not run for a valid cache hit")

    external_boundary_mocks_only.setattr(
        browser_download_service,
        "run_browser_report_download_agent",
        fail_if_browser_is_called,
    )
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
            expires_at_utc=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
        ),
        _ctx(),
    )

    result = download_report_with_browser_use(request, _ctx())

    assert result.outcome == "downloaded"
    assert result.downloaded_file_path == str(pdf_path)
    assert result.terminal_evidence.artifact_validation_status == "verified"


def test_pre_llm_form_autofill_submits_without_model_client(
    tmp_path: Path,
    external_boundary_mocks_only,
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
            self.browser.html = (
                "<html><body>Thanks for requesting the report</body></html>"
            )

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
        normalized_url="https://example.com/gated-report",
        execution_url="https://example.com/gated-report",
        download_dir=tmp_path,
        prompt_bundle=prompt_bundle,
    )

    assert model_client_requested["value"] is False
    assert "deterministic pre-LLM form autofill" in result.raw_model_response
    assert (
        result.final_page_html
        == "<html><body>Thanks for requesting the report</body></html>"
    )
    raw_result = json.loads(result.raw_model_response)
    assert raw_result["confirmation_url_changed"] is False
    assert raw_result["form_disappeared"] is False


def test_deterministic_playbook_completes_without_constructing_browser_use_model(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/report",
        settings=settings,
        route_family_hint="browser_pdf_click",
    )
    model_constructed = {"value": False}

    class FakePage:
        def goto(self, url):
            self.url = url

        def evaluate(self, expression):
            if "document.body" in expression:
                return True
            return {"status": "ok"}

        url = "https://publisher.example/report"
        title = "Publisher report"
        html = "<html><body>PDF ready</body></html>"

    class FakeBrowser:
        def __init__(self):
            self.page = FakePage()

        def get_current_page(self):
            return self.page

        def get_current_page_url(self):
            return self.page.url

        def get_current_page_title(self):
            return self.page.title

    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="publisher-example-download",
        version="1.0.0",
        status="active",
        updated_at="2026-08-16T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="publisher.example",
        host_patterns=["publisher.example"],
        url_path_markers=["report"],
        route_family="browser_pdf_click",
        route_kind="pdf_download",
        summary="Use the report download control.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="navigate",
                target="Report page",
                verification="Report page is open.",
                selector_type="url",
                selector="https://publisher.example/report",
                expected_url_contains="/report",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Download report",
                verification="PDF-ready state is visible.",
                selector_type="css",
                selector="a.download",
                expected_text="PDF ready",
            ),
        ],
    )

    result = run_deterministic_browser_route_playbook(
        request=request,
        ctx=_ctx(),
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path,
        browser=FakeBrowser(),
        playbook=playbook,
    )

    assert result is not None
    assert model_constructed["value"] is False
    payload = json.loads(result.raw_model_response)
    assert payload["route_kind"] == "pdf_download"
    assert payload["route_steps"][0]["verification_status"] == "verified"


def test_production_playbook_success_finalizes_without_browser_use_agent(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/report",
        settings=settings,
        route_family_hint="browser_pdf_click",
    )
    download_dir = tmp_path / "downloads"
    download_dir.mkdir()
    downloaded_pdf = download_dir / "report.pdf"
    downloaded_pdf.write_bytes(_valid_pdf_bytes())

    class FakePage:
        url = "https://publisher.example/report"
        title = "Publisher report"
        html = "<html><body>PDF ready</body></html>"

        def goto(self, url):
            self.url = url

        def evaluate(self, expression):
            if "document.body" in expression:
                return True
            return {"status": "ok"}

    class FakeBrowser:
        def __init__(self):
            self.page = FakePage()

        def get_current_page(self):
            return self.page

        def get_current_page_url(self):
            return self.page.url

        def get_current_page_title(self):
            return self.page.title

    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="publisher-example-download",
        version="1.0.0",
        status="active",
        updated_at="2026-08-16T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="publisher.example",
        host_patterns=["publisher.example"],
        url_path_markers=["report"],
        route_family="browser_pdf_click",
        route_kind="pdf_download",
        summary="Use the report download control.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="navigate",
                target="Report page",
                verification="Report page is open.",
                selector_type="url",
                selector="https://publisher.example/report",
                expected_url_contains="/report",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Download report",
                verification="PDF-ready state is visible.",
                selector_type="css",
                selector="a.download",
                expected_text="PDF ready",
            ),
        ],
    )

    result = try_deterministic_browser_route_playbooks(
        request=request,
        ctx=_ctx(),
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=download_dir,
        browser=FakeBrowser(),
        playbooks=[playbook],
    )

    assert result is not None
    assert result.outcome == "downloaded"
    assert result.terminal_evidence.artifact_validation_status == "verified"


def test_drifted_publisher_playbook_returns_agent_fallback_signal(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/report",
        settings=settings,
        route_family_hint="browser_pdf_click",
    )

    class FakeBrowser:
        def get_current_page(self):
            return object()

    drifted_playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="publisher-example-drifted",
        version="1.0.0",
        status="active",
        updated_at="2026-08-16T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="publisher.example",
        host_patterns=["publisher.example"],
        url_path_markers=["report"],
        route_family="browser_pdf_click",
        route_kind="pdf_download",
        summary="Incomplete historical route.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Download report",
                verification="PDF-ready state is visible.",
                selector_type="css",
                selector="a.download",
            )
        ],
    )

    result = try_deterministic_browser_route_playbooks(
        request=request,
        ctx=_ctx(),
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path,
        browser=FakeBrowser(),
        playbooks=[drifted_playbook],
    )

    assert result is None


def test_generic_playbook_remains_browser_use_fallback(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/report",
        settings=settings,
        route_family_hint="browser_pdf_click",
    )
    generic_playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="generic-download",
        version="1.0.0",
        status="active",
        updated_at="2026-08-16T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="all publishers",
        host_patterns=["*"],
        url_path_markers=["report"],
        route_family="browser_pdf_click",
        route_kind="pdf_download",
        summary="Prompt-only generic route.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Download report",
                verification="PDF-ready state is visible.",
                selector_type="css",
                selector="a.download",
                expected_text="PDF ready",
            )
        ],
    )

    result = try_deterministic_browser_route_playbooks(
        request=request,
        ctx=_ctx(),
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path,
        browser=object(),
        playbooks=[generic_playbook],
    )

    assert result is None


def test_pre_llm_form_autofill_returns_unknown_required_value_blocker(
    tmp_path: Path,
    external_boundary_mocks_only,
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
            self.browser.html = (
                "<html><body><form>Required industry</form></body></html>"
            )

        def evaluate(self, script):
            if "standardFormSubmit" in str(script):
                return {
                    "attempted_count": 1,
                    "filled_count": 1,
                    "selected_count": 0,
                    "mandatory_agreement_checked_count": 0,
                    "resolved_control_count": 1,
                    "submitted": False,
                    "final_url": self.browser.url,
                    "resolved_fields": ["Work email"],
                    "unresolved_fields": ["Industry"],
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
        normalized_url="https://example.com/gated-report",
        execution_url="https://example.com/gated-report",
        download_dir=tmp_path,
        prompt_bundle=prompt_bundle,
    )

    assert model_client_requested["value"] is False
    raw_result = json.loads(result.raw_model_response)
    assert raw_result["blocked_reason"] == "blocked_unknown_required_enum"
    assert raw_result["encountered_form_fields"] == ["Work email", "Industry"]


def test_pre_llm_form_autofill_opens_a_page_before_constructing_a_model_client(
    tmp_path: Path,
    external_boundary_mocks_only,
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
            self.browser.html = (
                "<html><body>Thanks for requesting the report</body></html>"
            )

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
            self.new_page_urls = []
            self.started = False

        def get_current_page(self):
            return None

        async def start(self):
            self.started = True

        async def new_page(self, url):
            if not self.started:
                raise RuntimeError("browser must start before opening a page")
            self.new_page_urls.append(url)
            self.url = url
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
        normalized_url="https://example.com/gated-report",
        execution_url="https://example.com/gated-report",
        download_dir=tmp_path,
        prompt_bundle=prompt_bundle,
    )

    assert model_client_requested["value"] is False
    assert result.final_page_url == "https://example.com/gated-report"


def test_pre_llm_submit_is_verified_only_from_terminal_confirmation_evidence(
    tmp_path: Path,
):
    settings = _settings(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/gated-report",
        settings=settings,
        route_family_hint="browser_email_form",
        delivery_email="ops@example.com",
    )
    browser_run = BrowserAgentRunResult(
        schema_version="1.0",
        raw_model_response=json.dumps(
            {
                "route_kind": "email_delivery",
                "route_family": "browser_email_form",
                "route_summary": (
                    "Filled configured identity fields and submitted "
                    "the report request form through deterministic "
                    "pre-LLM form autofill before invoking browser-use."
                ),
                "final_page_url": "https://example.com/gated-report",
                "resolved_target_url": "https://example.com/gated-report",
                "email_submission_completed": True,
                "post_submit_message": "",
                "confirmation_url_changed": False,
                "submit_button_state": "submitted",
                "form_disappeared": False,
                "encountered_form_fields": ["Work email", "Privacy agreement"],
            }
        ),
        final_page_url="https://example.com/gated-report",
        final_page_title="Gated report",
        final_page_html="<html><body><form>Work email</form></body></html>",
        downloaded_files=[],
        attachment_paths=[],
        network_resource_urls=[],
        network_events=[],
        html_snapshot_path="",
        screenshot_path="",
    )

    response = finalize_browser_report_download_result(
        request=request,
        ctx=_ctx(),
        normalized_url="https://example.com/gated-report",
        delivery_email="ops@example.com",
        download_dir=tmp_path,
        browser_run=browser_run,
    )

    assert response.outcome == "email_required"
    assert response.terminal_evidence.artifact_validation_status != "verified"


def test_standard_form_helper_retains_visible_options_for_required_blocker():
    class Page:
        def evaluate(self, _script):
            return {
                "attempted_count": 1,
                "filled_count": 1,
                "selected_count": 0,
                "mandatory_agreement_checked_count": 0,
                "resolved_control_count": 1,
                "submitted": False,
                "final_url": "https://example.com/gated-report",
                "resolved_fields": ["Work email"],
                "unresolved_fields": ["Industry"],
                "unresolved_options": {
                    "Industry": ["Financial services", "Technology"]
                },
            }

    result = browser_helper_standard_form_submit(
        page=Page(),
        field_values=[
            {
                "key": "work_email",
                "label": "Work email",
                "value": "ops@example.com",
                "aliases": ["email"],
                "option_aliases": [],
            }
        ],
        ctx=_ctx(),
        normalized_url="https://example.com/gated-report",
    )

    assert result.unresolved_options == {
        "Industry": ("Financial services", "Technology")
    }


def test_grounded_form_derivation_requires_visible_option_and_configured_evidence():
    from src.services._browser_report_download.browser import (
        _validated_grounded_form_option,
    )

    options = {"Industry": ("Financial services", "Technology")}
    configured = [
        {
            "key": "company_sector",
            "label": "Company sector",
            "value": "Technology",
            "aliases": ["Industry"],
            "option_aliases": ["Technology"],
        }
    ]
    valid_selection = {
        "field_label": "Industry",
        "option_value": "Technology",
        "evidence_key": "company_sector",
        "evidence_value": "Technology",
    }

    assert _validated_grounded_form_option(
        selection=valid_selection, options=options, configured=configured
    ) == {
        "key": "derived_company_sector",
        "label": "Industry",
        "value": "Technology",
        "aliases": ["Industry"],
        "option_aliases": ["Technology"],
    }
    assert (
        _validated_grounded_form_option(
            selection={**valid_selection, "option_value": "Healthcare"},
            options=options,
            configured=configured,
        )
        is None
    )
    assert (
        _validated_grounded_form_option(
            selection={**valid_selection, "evidence_value": "Finance"},
            options=options,
            configured=configured,
        )
        is None
    )
    assert (
        _validated_grounded_form_option(
            selection=dict.fromkeys(valid_selection, ""),
            options=options,
            configured=configured,
        )
        is None
    )


def test_grounded_form_derivation_unavailable_preserves_typed_blocker(
    tmp_path: Path, external_boundary_mocks_only
):
    from src.services import llm_service
    from src.services._browser_report_download import browser as browser_runtime
    from src.utils.errors import AppError

    def unavailable_model(*_args, **_kwargs):
        raise AppError(
            code="openai_chat_failed",
            message="provider unavailable",
            retryable=True,
        )

    external_boundary_mocks_only.setattr(
        llm_service, "openai_chat_json", unavailable_model
    )
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/gated-report",
        settings=_settings(tmp_path),
        route_family_hint="browser_email_form",
    )

    assert (
        browser_runtime._derive_grounded_form_option(
            request=request,
            helper_result=SimpleNamespace(
                unresolved_options={"Industry": ("Technology",)}
            ),
            ctx=_ctx(),
        )
        is None
    )


def test_browser_agent_uses_openai_primary_with_openrouter_fallback(
    tmp_path: Path,
    external_boundary_mocks_only,
):
    from src.services._browser_report_download import browser as browser_runtime

    settings = _settings(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=settings,
        route_family_hint="browser_pdf_click",
    )
    captured_agent: dict[str, object] = {}

    class FakeBrowser:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.url = ""
            self.title = ""
            self.html = ""
            self.downloaded_files = []
            self.network_resource_urls = []
            self.network_events = []
            self.dom_candidate_urls = []

        def get_current_page(self):
            browser = self

            class FakePage:
                def evaluate(self, script):
                    if "navigationEntries" in str(script):
                        return list(browser.network_events)
                    if "document.querySelectorAll" in str(script):
                        return list(browser.dom_candidate_urls)
                    return list(browser.network_resource_urls)

            return FakePage()

        def take_screenshot(self, path=None, **_kwargs):
            if path:
                Path(path).write_bytes(b"fake-screenshot")
            return b"fake-screenshot"

        async def kill(self):
            return None

    class FakeChatOpenAI:
        def __init__(self, **kwargs):
            self.provider = "openai"
            self.kwargs = kwargs

    class FakeChatOpenRouter:
        def __init__(self, **kwargs):
            self.provider = "openrouter"
            self.kwargs = kwargs

    class FakeHistory:
        def final_result(self):
            return (
                '{"route_kind":"email_delivery","route_family":"browser_pdf_click",'
                '"route_summary":"Reached the report page.",'
                '"final_page_url":"https://example.com/final",'
                '"resolved_target_url":"https://example.com/final",'
                '"email_submission_completed":false,'
                '"post_submit_message":"",'
                '"downloaded_file_path":null,'
                '"downloaded_file_name":null,'
                '"downloaded_mime_type":null,'
                '"encountered_form_fields":[]}'
            )

        def action_results(self):
            return []

    class FakeAgent:
        def __init__(
            self,
            *,
            task,
            llm,
            browser,
            output_model_schema,
            use_judge=False,
            fallback_llm=None,
            calculate_cost=False,
        ):
            captured_agent.update(
                {
                    "task": task,
                    "llm": llm,
                    "fallback_llm": fallback_llm,
                    "output_model_schema": output_model_schema,
                    "use_judge": use_judge,
                    "calculate_cost": calculate_cost,
                }
            )
            self.browser = browser

        def run_sync(self, max_steps):
            self.browser.url = "https://example.com/final"
            self.browser.title = "Example final"
            self.browser.html = "<html><body>Example final</body></html>"
            return FakeHistory()

    fake_browser_use = SimpleNamespace(
        Browser=FakeBrowser,
        ChatOpenAI=FakeChatOpenAI,
        ChatOpenRouter=FakeChatOpenRouter,
        Agent=FakeAgent,
    )
    external_boundary_mocks_only.setitem(sys.modules, "browser_use", fake_browser_use)
    prompt_bundle = BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route/browser_pdf_click",
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
        normalized_url="https://example.com/report",
        execution_url="https://example.com/report",
        download_dir=tmp_path,
        prompt_bundle=prompt_bundle,
    )

    assert captured_agent["llm"].provider == "openai"
    assert captured_agent["fallback_llm"].provider == "openrouter"
    assert captured_agent["llm"].kwargs["model"] == "gpt-5-mini"
    assert captured_agent["fallback_llm"].kwargs["model"] == "openai/gpt-5-mini"
    assert captured_agent["calculate_cost"] is True
    assert result.final_page_url == "https://example.com/final"
