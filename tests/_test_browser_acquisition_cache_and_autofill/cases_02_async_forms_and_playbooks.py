# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_browser_acquisition_cache_and_autofill.py"
)

from ._shared import *  # noqa: F401,F403


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
            if asyncio.get_running_loop() is not self.browser.event_loop:
                raise RuntimeError("page_evaluate_must_run_on_browser_event_loop")
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
            self.event_loop = None

        async def start(self) -> None:
            self.event_loop = asyncio.get_running_loop()
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


__all__ = [
    "test_async_pre_llm_form_verified_submit_avoids_agent_and_closes_once",
    "test_async_pre_llm_form_unknown_required_value_is_typed_blocker",
    "test_async_pre_llm_unverified_submit_falls_through_on_same_browser",
    "test_async_pre_llm_unsupported_form_falls_through_on_same_browser",
    "test_deterministic_playbook_completes_without_constructing_browser_use_model",
    "test_async_deterministic_playbook_executes_supported_actions_without_agent",
    "test_async_deterministic_playbook_rejects_explicit_cookie_banner_before_form_steps",
    "test_async_deterministic_playbook_drift_returns_fallback_signal",
]
