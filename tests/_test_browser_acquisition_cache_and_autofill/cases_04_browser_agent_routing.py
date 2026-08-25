# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent
    / "test_browser_acquisition_cache_and_autofill.py"
)

from ._shared import *  # noqa: F401,F403


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


__all__ = [
    "test_browser_agent_uses_openai_primary_with_openrouter_fallback",
]
