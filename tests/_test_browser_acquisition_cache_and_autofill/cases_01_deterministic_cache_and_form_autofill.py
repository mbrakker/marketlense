# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_browser_acquisition_cache_and_autofill.py"
)

from ._shared import *  # noqa: F401,F403


def test_deterministic_playbook_handoff_uses_only_a_new_same_publisher_url() -> None:
    assert (
        _deterministic_playbook_handoff_url(
            execution_url="https://www.adjust.com/resources/ebooks/all",
            final_page_url="https://www.adjust.com/resources/ebooks/japan-app-trends/",
        )
        == "https://www.adjust.com/resources/ebooks/japan-app-trends/"
    )
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


__all__ = [
    "test_deterministic_playbook_handoff_uses_only_a_new_same_publisher_url",
    "test_publisher_playbooks_require_an_isolated_worker",
    "test_deterministic_playbook_retains_same_publisher_page_for_agent_handoff",
    "test_browser_download_reuses_valid_artifact_acquisition_cache",
    "test_pre_llm_form_autofill_submits_without_model_client",
]
