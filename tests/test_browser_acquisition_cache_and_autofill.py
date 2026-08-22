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


def test_deterministic_playbook_handoff_uses_only_a_new_same_publisher_url() -> None:
    assert _deterministic_playbook_handoff_url(
        execution_url="https://www.adjust.com/resources/ebooks/all",
        final_page_url="https://www.adjust.com/resources/ebooks/japan-app-trends/",
    ) == "https://www.adjust.com/resources/ebooks/japan-app-trends/"
    assert (
        _deterministic_playbook_handoff_url(
            execution_url="https://www.adjust.com/resources/ebooks/all",
            final_page_url="https://www.adjust.com/resources/ebooks/all",
        )
        == ""
    )


def test_publisher_playbooks_require_an_isolated_worker() -> None:
    publisher_playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="publisher-route",
        version="1.0.0",
        status="active",
        updated_at="2026-08-22T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="adjust.com",
        host_patterns=["www.adjust.com"],
        url_path_markers=["resources/ebooks/all"],
        route_family="browser_email_form",
        route_kind="email_form",
        summary="Publisher route.",
        steps=[],
    )
    generic_playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="generic-route",
        version="1.0.0",
        status="active",
        updated_at="2026-08-22T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="all publishers",
        host_patterns=["*"],
        url_path_markers=["resources/ebooks/all"],
        route_family="browser_email_form",
        route_kind="email_form",
        summary="Generic route.",
        steps=[],
    )

    assert _deterministic_playbooks_require_isolated_worker([publisher_playbook])
    assert not _deterministic_playbooks_require_isolated_worker([generic_playbook])
    assert _should_defer_browser_preflight_for_deterministic_playbooks(
        [publisher_playbook]
    )
    assert not _should_defer_browser_preflight_for_deterministic_playbooks(
        [generic_playbook]
    )


def test_deterministic_playbook_retains_same_publisher_page_for_agent_handoff(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://www.adjust.com/resources/ebooks/all",
        settings=_settings(tmp_path),
        route_family_hint="browser_email_form",
    )

    class FakePage:
        def __init__(self, browser) -> None:
            self.browser = browser
            self.url = request.url
            self.title = "Adjust ebooks"
            self.html = "<html><body>Report page</body></html>"

        def goto(self, url: str) -> None:
            self.url = url
            self.browser.url = url

        def evaluate(self, expression: str):
            if "document.body" in expression:
                return True
            return {"status": "ok"}

    class FakeBrowser:
        def __init__(self) -> None:
            self.url = request.url
            self.page = FakePage(self)

        def get_current_page(self):
            return self.page

        def get_current_page_url(self) -> str:
            return self.url

        def get_current_page_title(self) -> str:
            return self.page.title

    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="adjust-listing-route",
        version="1.0.0",
        status="active",
        updated_at="2026-08-22T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="adjust.com",
        host_patterns=["www.adjust.com"],
        url_path_markers=["resources/ebooks/all"],
        route_family="browser_email_form",
        route_kind="email_form",
        summary="Open the report detail page.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="navigate",
                target="Japan report",
                verification="The report page is open.",
                selector_type="url",
                selector="https://www.adjust.com/resources/ebooks/japan-app-trends/",
                expected_url_contains="/resources/ebooks/japan-app-trends/",
            )
        ],
    )

    attempt = _try_deterministic_browser_route_playbooks(
        request=request,
        ctx=_ctx(),
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path,
        browser=FakeBrowser(),
        playbooks=[playbook],
    )

    assert attempt.result is None
    assert attempt.handoff_execution_url == (
        "https://www.adjust.com/resources/ebooks/japan-app-trends/"
    )
    assert (
        _deterministic_playbook_handoff_url(
            execution_url="https://www.adjust.com/resources/ebooks/all",
            final_page_url="https://untrusted.example/resources/ebooks/japan-app-trends/",
        )
        == ""
    )


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
    browser_use_agent_requested = {"value": False}
    deterministic_submit_calls = {"value": 0}

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
                deterministic_submit_calls["value"] += 1
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

    class FailingAgent:
        def __init__(self, **kwargs):
            browser_use_agent_requested["value"] = True
            raise AssertionError("Browser Use agent should not be constructed")

    fake_browser_use = SimpleNamespace(
        Browser=FakeBrowser,
        ChatOpenRouter=FailingChatOpenRouter,
        Agent=FailingAgent,
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
    assert browser_use_agent_requested["value"] is False
    assert deterministic_submit_calls["value"] == 1
    assert "deterministic pre-LLM form autofill" in result.raw_model_response
    assert (
        result.final_page_html
        == "<html><body>Thanks for requesting the report</body></html>"
    )
    raw_result = json.loads(result.raw_model_response)
    assert raw_result["confirmation_url_changed"] is False
    assert raw_result["form_disappeared"] is True
    assert raw_result["route_steps"][0]["verification_status"] == "verified"


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


def test_async_pre_llm_form_verified_submit_avoids_agent_and_closes_once(
    tmp_path: Path, external_boundary_mocks_only
) -> None:
    result, observed, browser = _run_async_pre_llm_form_case(
        tmp_path=tmp_path,
        external_boundary_mocks_only=external_boundary_mocks_only,
        form_payload={
            "attempted_count": 2,
            "filled_count": 1,
            "selected_count": 0,
            "mandatory_agreement_checked_count": 1,
            "resolved_control_count": 2,
            "submitted": True,
            "final_url": "https://example.com/gated-report",
            "resolved_fields": ["Work email", "Privacy agreement"],
            "unresolved_fields": [],
        },
        terminal_html="<html><body>Thanks for requesting the report</body></html>",
    )

    assert observed["agent_calls"] == 0
    assert browser.deterministic_submit_calls == 1
    assert browser.start_calls == 1
    assert browser.kill_calls == 1
    assert "deterministic pre-LLM form autofill" in result.raw_model_response


def test_async_pre_llm_form_unknown_required_value_is_typed_blocker(
    tmp_path: Path, external_boundary_mocks_only
) -> None:
    result, observed, browser = _run_async_pre_llm_form_case(
        tmp_path=tmp_path,
        external_boundary_mocks_only=external_boundary_mocks_only,
        form_payload={
            "attempted_count": 1,
            "filled_count": 1,
            "selected_count": 0,
            "mandatory_agreement_checked_count": 0,
            "resolved_control_count": 1,
            "submitted": False,
            "final_url": "https://example.com/gated-report",
            "resolved_fields": ["Work email"],
            "unresolved_fields": ["Industry"],
        },
        terminal_html="<html><body><form>Required industry</form></body></html>",
    )

    assert observed["agent_calls"] == 0
    assert browser.deterministic_submit_calls == 1
    assert browser.start_calls == 1
    assert browser.kill_calls == 1
    assert json.loads(result.raw_model_response)["blocked_reason"] == (
        "blocked_unknown_required_enum"
    )


def test_async_pre_llm_unverified_submit_falls_through_on_same_browser(
    tmp_path: Path, external_boundary_mocks_only
) -> None:
    result, observed, browser = _run_async_pre_llm_form_case(
        tmp_path=tmp_path,
        external_boundary_mocks_only=external_boundary_mocks_only,
        form_payload={
            "attempted_count": 1,
            "filled_count": 1,
            "selected_count": 0,
            "mandatory_agreement_checked_count": 0,
            "resolved_control_count": 1,
            "submitted": True,
            "final_url": "https://example.com/gated-report",
            "resolved_fields": ["Work email"],
            "unresolved_fields": [],
        },
        terminal_html="<html><body><form>Work email</form></body></html>",
    )

    assert observed["agent_calls"] == 1
    assert observed["agent_browser"] is browser
    assert browser.deterministic_submit_calls == 1
    assert browser.start_calls == 1
    assert browser.kill_calls == 1
    assert result.final_page_url.endswith("#agent")


def test_async_pre_llm_unsupported_form_falls_through_on_same_browser(
    tmp_path: Path, external_boundary_mocks_only
) -> None:
    result, observed, browser = _run_async_pre_llm_form_case(
        tmp_path=tmp_path,
        external_boundary_mocks_only=external_boundary_mocks_only,
        form_payload={
            "attempted_count": 0,
            "filled_count": 0,
            "selected_count": 0,
            "mandatory_agreement_checked_count": 0,
            "resolved_control_count": 0,
            "submitted": False,
            "final_url": "https://example.com/gated-report",
            "resolved_fields": [],
            "unresolved_fields": [],
        },
        terminal_html="<html><body><custom-form></custom-form></body></html>",
    )

    assert observed["agent_calls"] == 1
    assert observed["agent_browser"] is browser
    assert browser.deterministic_submit_calls == 1
    assert browser.start_calls == 1
    assert browser.kill_calls == 1
    assert result.final_page_url.endswith("#agent")


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


def test_async_deterministic_playbook_executes_supported_actions_without_agent(
    tmp_path: Path,
) -> None:
    settings = _settings(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/report",
        settings=settings,
        route_family_hint="browser_email_form",
    )

    class AsyncPage:
        def __init__(self, browser) -> None:
            self.browser = browser
            self.evaluations: list[str] = []
            self.click_count = 0
            self.fill_values: list[str] = []
            self.select_values: list[str] = []
            self.submitted = False

        async def evaluate(self, expression: str):
            self.evaluations.append(expression)
            if "document.body?.innerText" in expression:
                return "Form ready" in expression
            if "document.documentElement.outerHTML" in expression:
                return self.browser.html
            if "element.tagName !== 'SELECT'" in expression:
                self.select_values.append("Market Lense")
                return "selected"
            if "element.value =" in expression:
                self.fill_values.append("ops@example.com")
                return "filled"
            if "element.click()" in expression:
                self.click_count += 1
                self.submitted = "button[type=submit]" in expression
                return "clicked"
            raise AssertionError(f"Unexpected deterministic expression: {expression}")

    class AsyncBrowser:
        def __init__(self) -> None:
            self.page = AsyncPage(self)
            self.url = "https://publisher.example/report"
            self.title = "Publisher form"
            self.html = "<html><body>Form ready</body></html>"
            self.start_calls = 0
            self.navigated_urls: list[str] = []
            self.agent_calls = 0

        async def start(self) -> None:
            self.start_calls += 1

        async def get_current_page(self) -> AsyncPage:
            return self.page

        async def navigate_to(self, url: str) -> None:
            self.url = url
            self.navigated_urls.append(url)

        async def get_current_page_url(self) -> str:
            return self.url

        async def get_current_page_title(self) -> str:
            return self.title

    AsyncBrowser.__module__ = "browser_use.browser"
    browser = AsyncBrowser()
    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="publisher-example-async-form",
        version="1.0.0",
        status="active",
        updated_at="2026-08-20T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="publisher.example",
        host_patterns=["publisher.example"],
        url_path_markers=["report"],
        route_family="browser_email_form",
        route_kind="email_delivery",
        summary="Complete the publisher form.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="open",
                target="Report form",
                verification="form loaded",
                selector_type="url",
                selector="https://publisher.example/report",
                expected_url_contains="/report",
                expected_text="Form ready",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="navigate",
                target="Report form",
                verification="form loaded",
                selector_type="url",
                selector="https://publisher.example/report",
                expected_url_contains="/report",
                expected_text="Form ready",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Open form",
                verification="form remains ready",
                selector_type="css",
                selector="a.download",
                expected_url_contains="/report",
                expected_text="Form ready",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Request report",
                verification="form remains ready",
                selector_type="role",
                selector="button:Request report",
                expected_url_contains="/report",
                expected_text="Form ready",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Continue",
                verification="form remains ready",
                selector_type="label",
                selector="Continue",
                expected_url_contains="/report",
                expected_text="Form ready",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Continue",
                verification="form remains ready",
                selector_type="name",
                selector="continue",
                expected_url_contains="/report",
                expected_text="Form ready",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Continue",
                verification="form remains ready",
                selector_type="data_attribute",
                selector="data-testid=continue",
                expected_url_contains="/report",
                expected_text="Form ready",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Download",
                verification="form remains ready",
                selector_type="text",
                selector="Download",
                expected_url_contains="/report",
                expected_text="Form ready",
            ),
            *[
                BrowserRoutePlaybookStep(
                    schema_version="1.0",
                    action=action,
                    target="Work email",
                    verification="email entered",
                    selector_type=selector_type,
                    selector=selector,
                    value_reference="${identity.work_email}",
                    expected_url_contains="/report",
                    expected_text="Form ready",
                )
                for action, selector_type, selector in (
                    ("fill", "css", "input.email"),
                    ("type", "label", "Work email"),
                    ("fill", "name", "email"),
                    ("fill", "data_attribute", "data-testid=email"),
                )
            ],
            *[
                BrowserRoutePlaybookStep(
                    schema_version="1.0",
                    action="select",
                    target="Company",
                    verification="company selected",
                    selector_type=selector_type,
                    selector=selector,
                    value_reference="${identity.company}",
                    expected_url_contains="/report",
                    expected_text="Form ready",
                )
                for selector_type, selector in (
                    ("css", "select.company"),
                    ("label", "Company"),
                    ("name", "company"),
                    ("data_attribute", "data-testid=company"),
                )
            ],
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="submit",
                target="Request report",
                verification="request submitted",
                selector_type="css",
                selector="button[type=submit]",
                expected_url_contains="/report",
                expected_text="Form ready",
            ),
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="verify",
                target="Confirmation",
                verification="form still ready",
                selector_type="css",
                selector="body",
                expected_url_contains="/report",
                expected_text="Form ready",
            ),
        ],
    )

    result = run_deterministic_browser_route_playbook(
        request=request,
        ctx=_ctx(),
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path,
        browser=browser,
        playbook=playbook,
    )

    assert result is not None
    assert browser.agent_calls == 0
    assert browser.start_calls == 1
    assert browser.navigated_urls == [request.url, request.url]
    assert json.loads(result.raw_model_response)["post_submit_message"] == "Form ready"
    assert browser.page.click_count == 7
    assert browser.page.submitted is True
    assert browser.page.fill_values == ["ops@example.com"] * 4
    assert browser.page.select_values == ["Market Lense"] * 4
    assert len(json.loads(result.raw_model_response)["route_steps"]) == len(
        playbook.steps
    )


def test_async_deterministic_playbook_rejects_explicit_cookie_banner_before_form_steps(
    tmp_path: Path,
) -> None:
    """A consent overlay must not turn a known deterministic route into Agent work."""
    settings = _settings(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/report",
        settings=settings,
        route_family_hint="browser_email_form",
    )

    class ConsentGatedPage:
        def __init__(self, browser) -> None:
            self.browser = browser
            self.cookie_banner_rejected = False
            self.calls: list[str] = []

        async def evaluate(self, expression: str):
            self.calls.append(expression)
            if "document.documentElement.outerHTML" in expression:
                return "<html><body>Request confirmed</body></html>"
            if "document.body?.innerText" in expression:
                return "Request confirmed" in expression
            if "normalizedText" in expression and "reject all" in expression:
                self.cookie_banner_rejected = True
                return "rejected"
            if "element.click()" in expression:
                if not self.cookie_banner_rejected:
                    raise RuntimeError("cookie_banner_blocks_interaction")
                return "clicked"
            raise AssertionError(f"Unexpected deterministic expression: {expression}")

    class ConsentGatedBrowser:
        def __init__(self) -> None:
            self.page = ConsentGatedPage(self)
            self.url = "https://publisher.example/report"
            self.title = "Publisher form"

        async def start(self) -> None:
            return None

        async def get_current_page(self) -> ConsentGatedPage:
            return self.page

        async def navigate_to(self, url: str) -> None:
            self.url = url

        async def get_current_page_url(self) -> str:
            return self.url

        async def get_current_page_title(self) -> str:
            return self.title

    ConsentGatedBrowser.__module__ = "browser_use.browser"
    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="publisher-cookie-gated-form",
        version="1.0.0",
        status="active",
        updated_at="2026-08-22T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="publisher.example",
        host_patterns=["publisher.example"],
        url_path_markers=["report"],
        route_family="browser_email_form",
        route_kind="email_delivery",
        summary="Submit the publisher form after rejecting its consent banner.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="submit",
                target="Request report",
                verification="request submitted",
                selector_type="css",
                selector="button[type=submit]",
                expected_text="Request confirmed",
            )
        ],
    )

    browser = ConsentGatedBrowser()
    result = run_deterministic_browser_route_playbook(
        request=request,
        ctx=_ctx(),
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path,
        browser=browser,
        playbook=playbook,
    )

    assert result is not None
    assert browser.page.cookie_banner_rejected is True


def test_async_deterministic_playbook_drift_returns_fallback_signal(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/report",
        settings=_settings(tmp_path),
        route_family_hint="browser_pdf_click",
    )

    class AsyncPage:
        def __init__(self) -> None:
            self.evaluations = 0

        async def evaluate(self, expression: str):
            self.evaluations += 1
            if "element.click()" in expression:
                return "clicked"
            if "document.body?.innerText" in expression:
                return False
            raise AssertionError(f"Unexpected deterministic expression: {expression}")

    class AsyncBrowser:
        def __init__(self) -> None:
            self.page = AsyncPage()
            self.url = request.url
            self.start_calls = 0

        async def start(self) -> None:
            self.start_calls += 1

        async def get_current_page(self) -> AsyncPage:
            return self.page

        async def get_current_page_url(self) -> str:
            return self.url

    AsyncBrowser.__module__ = "browser_use.browser"
    browser = AsyncBrowser()
    drifted_playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="publisher-example-async-drift",
        version="1.0.0",
        status="active",
        updated_at="2026-08-20T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="publisher.example",
        host_patterns=["publisher.example"],
        url_path_markers=["report"],
        route_family="browser_pdf_click",
        route_kind="pdf_download",
        summary="Click the report download.",
        steps=[
            BrowserRoutePlaybookStep(
                schema_version="1.0",
                action="click",
                target="Download report",
                verification="PDF-ready state is visible.",
                selector_type="css",
                selector="a.download",
                expected_url_contains="/report",
                expected_text="PDF ready",
            )
        ],
    )

    result = run_deterministic_browser_route_playbook(
        request=request,
        ctx=_ctx(),
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path,
        browser=browser,
        playbook=drifted_playbook,
    )

    assert result is None
    assert browser.start_calls == 1
    assert browser.page.evaluations >= 2


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
    browser_use_agent_requested = {"value": False}
    deterministic_submit_calls = {"value": 0}

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
                deterministic_submit_calls["value"] += 1
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

    class FailingAgent:
        def __init__(self, **kwargs):
            browser_use_agent_requested["value"] = True
            raise AssertionError("Browser Use agent should not be constructed")

    fake_browser_use = SimpleNamespace(
        Browser=FakeBrowser,
        ChatOpenRouter=FailingChatOpenRouter,
        Agent=FailingAgent,
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
    assert browser_use_agent_requested["value"] is False
    assert deterministic_submit_calls["value"] == 1
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
            if "document.documentElement" in str(script):
                return self.browser.html
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
            self.title = "Gated report"
            self.html = "<html><body>Thanks for requesting the report</body></html>"
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


def test_standard_form_helper_activates_same_page_report_cta_before_submit():
    class Page:
        def __init__(self) -> None:
            self.cta_activated = False

        def evaluate(self, script):
            if "standardFormActivate" in script:
                self.cta_activated = True
                return {
                    "activated": True,
                    "activation_text": "Download report",
                    "final_url": "https://example.com/gated-report#form",
                }
            if "standardFormSubmit" in script:
                assert self.cta_activated is True
                return {
                    "attempted_count": 2,
                    "filled_count": 1,
                    "selected_count": 0,
                    "mandatory_agreement_checked_count": 1,
                    "resolved_control_count": 2,
                    "submitted": True,
                    "final_url": "https://example.com/gated-report#form",
                    "resolved_fields": ["Work email", "Privacy agreement"],
                    "unresolved_fields": [],
                }
            raise AssertionError("unexpected browser helper expression")

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

    assert result.status == "ok"
    assert result.submitted is True
    assert result.final_url == "https://example.com/gated-report#form"


def test_standard_form_helper_traverses_shadow_hosted_cta_and_form_frame():
    """A shadow-hosted CTA must be activated before the form helper gives up."""

    class ShadowHostedFormPage:
        def evaluate(self, script):
            if "standardFormActivate" in script:
                if "shadowRoot" not in script:
                    raise AssertionError("shadow-hosted CTA was not searched")
                return {
                    "activated": True,
                    "activation_text": "Download report",
                    "final_url": "https://example.com/gated-report#form",
                }
            if "standardFormSubmit" in script:
                if "shadowRoot" not in script:
                    raise AssertionError("shadow-hosted form frame was not searched")
                return {
                    "attempted_count": 1,
                    "filled_count": 1,
                    "selected_count": 0,
                    "mandatory_agreement_checked_count": 0,
                    "resolved_control_count": 1,
                    "submitted": True,
                    "final_url": "https://example.com/gated-report#form",
                    "resolved_fields": ["Work email"],
                    "unresolved_fields": [],
                }
            raise AssertionError("unexpected browser helper expression")

    result = browser_helper_standard_form_submit(
        page=ShadowHostedFormPage(),
        field_values=[
            {
                "key": "work_email",
                "label": "Work email",
                "value": "ops@example.com",
                "aliases": ["email"],
            }
        ],
        ctx=_ctx(),
        normalized_url="https://example.com/gated-report",
    )

    assert result.status == "ok"
    assert result.submitted is True


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
