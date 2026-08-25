# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_browser_acquisition_cache_and_autofill.py"
)

from ._shared import *  # noqa: F401,F403


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


def test_semantic_terminal_message_confirms_email_delivery() -> None:
    """A terminal thank-you page can confirm delivery without a URL change."""

    assert _message_indicates_confirmed_email_delivery(
        "Good news: the report link is on its way to the inbox for the email "
        "address you provided."
    )
    assert _message_indicates_confirmed_email_delivery(
        "An email with a link should be in your inbox. Or maybe your spam folder. "
        "Either way your download is just seconds away."
    )
    assert not _message_indicates_confirmed_email_delivery(
        "Enter your email to get a link to download the report."
    )


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


__all__ = [
    "test_production_playbook_success_finalizes_without_browser_use_agent",
    "test_drifted_publisher_playbook_returns_agent_fallback_signal",
    "test_generic_playbook_remains_browser_use_fallback",
    "test_pre_llm_form_autofill_returns_unknown_required_value_blocker",
    "test_pre_llm_form_autofill_opens_a_page_before_constructing_a_model_client",
    "test_pre_llm_submit_is_verified_only_from_terminal_confirmation_evidence",
    "test_semantic_terminal_message_confirms_email_delivery",
    "test_standard_form_helper_retains_visible_options_for_required_blocker",
    "test_standard_form_helper_activates_same_page_report_cta_before_submit",
    "test_standard_form_helper_traverses_shadow_hosted_cta_and_form_frame",
    "test_grounded_form_derivation_requires_visible_option_and_configured_evidence",
]
