# ruff: noqa: F401,F403,F405
from __future__ import annotations

import asyncio

from src.contracts.browser_download import BrowserRoutePlaybook
from src.services._browser_report_download._browser_runtime import timeout_recovery
from src.services._browser_report_download._helpers.interaction import (
    browser_helper_form_autocomplete,
)

from ._shared import *  # noqa: F401,F403


def test_browser_worker_main_preserves_candidate_trace(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/report",
        title="Example Report",
        discovered_on_page_number=2,
        source_page_urls=[
            "https://example.com/insights",
            "https://example.com/resources",
        ],
        discovery_provenances=["http_parse", "browser_dom"],
        pdf_url="https://cdn.example.com/example-report.pdf",
        published_at_text="April 2026",
        max_confidence=0.92,
    )
    settings = replace(
        _settings(tmp_path),
        model_pricing={
            "gpt-5-mini": {
                "input_tokens_per_1k_usd": 0.00025,
                "output_tokens_per_1k_usd": 0.002,
            }
        },
    )
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url=candidate_trace.canonical_url,
        settings=settings,
        candidate_trace=candidate_trace,
        attempt_url="https://example.com/report?download=1",
        route_family_hint="browser_pdf_click",
    )
    download_dir = tmp_path / "worker-run"
    payload_path = tmp_path / "browser_agent_worker_request.json"
    response_path = tmp_path / "browser_agent_worker_response.json"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "request": {
                    **json.loads(
                        json.dumps(request, default=lambda value: value.__dict__)
                    ),
                },
                "ctx": run_context.__dict__,
                "normalized_url": request.url,
                "execution_url": request.attempt_url,
                "download_dir": str(download_dir),
                "prompt_bundle": {
                    "schema_version": "1.0",
                    "namespace": "browser_report_download/browser_route",
                    "system_prompt_path": "system.yaml",
                    "user_prompt_path": "user.yaml",
                    "system_prompt_sha256": "system",
                    "user_prompt_sha256": "user",
                    "rendered_system_prompt": "system",
                    "rendered_user_prompt": "user",
                    "task_prompt": "task",
                },
            }
        ),
        encoding="utf-8",
    )

    observed_requests: list[BrowserReportDownloadRequest] = []

    def fake_run_browser_report_download_agent(**kwargs):
        observed_requests.append(kwargs["request"])
        return browser_runtime.BrowserAgentRunResult(
            schema_version="1.0",
            raw_model_response="{}",
            final_page_url="https://example.com/final",
            final_page_title="Example",
            final_page_html="<html></html>",
            downloaded_files=[],
            attachment_paths=[],
            network_resource_urls=[],
            network_events=[],
            html_snapshot_path="",
            screenshot_path="",
        )

    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "run_browser_report_download_agent",
        fake_run_browser_report_download_agent,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "setup_logging",
        lambda *args, **kwargs: None,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime.sys,
        "argv",
        [
            "browser_worker.py",
            str(payload_path),
            str(response_path),
        ],
    )

    assert browser_worker_runtime.main() == 0
    assert response_path.exists()
    assert len(observed_requests) == 1
    observed_request = observed_requests[0]
    assert observed_request.candidate_trace is not None
    assert (
        observed_request.candidate_trace.canonical_url == candidate_trace.canonical_url
    )
    assert observed_request.candidate_trace.pdf_url == candidate_trace.pdf_url
    assert observed_request.candidate_trace.discovery_provenances == (
        candidate_trace.discovery_provenances
    )
    assert observed_request.settings.model_pricing == settings.model_pricing


def test_browser_worker_main_preserves_identity_option_aliases(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = _settings(tmp_path)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=replace(
            settings,
            identity_profile=BrowserDownloadIdentity(
                schema_version="1.0",
                fields=[
                    BrowserDownloadIdentityField(
                        schema_version="1.0",
                        key="state_region",
                        label="State",
                        value="AT-9",
                        aliases=["state", "region"],
                        option_aliases=["Vienna", "Wien"],
                    )
                ],
            ),
        ),
        route_family_hint="browser_email_form",
    )
    payload_path = tmp_path / "browser_agent_worker_request.json"
    response_path = tmp_path / "browser_agent_worker_response.json"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "request": json.loads(
                    json.dumps(request, default=lambda value: value.__dict__)
                ),
                "ctx": run_context.__dict__,
                "normalized_url": request.url,
                "execution_url": request.url,
                "download_dir": str(tmp_path / "worker-download"),
                "prompt_bundle": {
                    "schema_version": "1.0",
                    "namespace": "browser_report_download/browser_route",
                    "system_prompt_path": "system.yaml",
                    "user_prompt_path": "user.yaml",
                    "system_prompt_sha256": "system",
                    "user_prompt_sha256": "user",
                    "rendered_system_prompt": "system",
                    "rendered_user_prompt": "user",
                    "task_prompt": "task",
                },
            }
        ),
        encoding="utf-8",
    )

    observed_requests: list[BrowserReportDownloadRequest] = []

    def fake_run_browser_report_download_agent(**kwargs):
        observed_requests.append(kwargs["request"])
        return browser_runtime.BrowserAgentRunResult(
            schema_version="1.0",
            raw_model_response="{}",
            final_page_url="https://example.com/final",
            final_page_title="Final",
            final_page_html="<html></html>",
            downloaded_files=[],
            attachment_paths=[],
            network_resource_urls=[],
            network_events=[],
            html_snapshot_path="",
            screenshot_path="",
        )

    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "run_browser_report_download_agent",
        fake_run_browser_report_download_agent,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "setup_logging",
        lambda *args, **kwargs: None,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime.sys,
        "argv",
        [
            "browser_worker.py",
            str(payload_path),
            str(response_path),
        ],
    )

    assert browser_worker_runtime.main() == 0
    assert len(observed_requests) == 1
    observed_field = observed_requests[0].settings.identity_profile.fields[0]
    assert observed_field.option_aliases == ["Vienna", "Wien"]


def test_deterministic_worker_navigates_before_executing_playbook(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
        route_family_hint="browser_email_form",
    )
    playbook = BrowserRoutePlaybook(
        schema_version="1.0",
        playbook_id="publisher-route",
        version="1.0.0",
        status="active",
        updated_at="2026-08-22T00:00:00+00:00",
        stale_after_days=180,
        publisher_pattern="example.com",
        host_patterns=["example.com"],
        url_path_markers=["report"],
        route_family="browser_email_form",
        route_kind="email_delivery",
        summary="Publisher form route.",
        steps=[],
    )
    payload_path = tmp_path / "browser_agent_worker_request.json"
    response_path = tmp_path / "browser_agent_worker_response.json"
    execution_url = "https://example.com/report?source=validation"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "request": json.loads(
                    json.dumps(request, default=lambda value: value.__dict__)
                ),
                "ctx": run_context.__dict__,
                "normalized_url": request.url,
                "execution_url": execution_url,
                "download_dir": str(tmp_path / "worker-download"),
                "prompt_bundle": {},
                "execution_mode": "deterministic_playbook",
                "deterministic_playbook": json.loads(
                    json.dumps(playbook, default=lambda value: value.__dict__)
                ),
            }
        ),
        encoding="utf-8",
    )

    class FakeBrowser:
        def __init__(self) -> None:
            self.navigated_urls: list[str] = []

        async def start(self) -> None:
            return None

        async def navigate_to(self, url: str) -> None:
            self.navigated_urls.append(url)

        async def get_current_page(self):
            assert self.navigated_urls == [execution_url]
            return None

        async def kill(self) -> None:
            return None

    browser = FakeBrowser()
    session = SimpleNamespace(browser=browser)

    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "load_browser_use_runtime",
        lambda **kwargs: object(),
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "start_browser_preflight_session",
        lambda **kwargs: session,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "close_browser_preflight_session",
        lambda **kwargs: None,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "setup_logging",
        lambda *args, **kwargs: None,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime.sys,
        "argv",
        ["browser_worker.py", str(payload_path), str(response_path)],
    )

    assert browser_worker_runtime.main() == 0
    response = json.loads(response_path.read_text(encoding="utf-8"))
    assert response["status"] == "drifted"


def test_deterministic_worker_navigation_timeout_keeps_loaded_page_available() -> None:
    """A page that rendered before navigation settles must still reach the route runner."""

    class Browser:
        def __init__(self) -> None:
            self.navigation_started = False

        async def navigate_to(self, url: str) -> None:
            self.navigation_started = True
            await asyncio.Event().wait()

    browser = Browser()

    settled = asyncio.run(
        browser_worker_runtime.navigate_deterministic_playbook_page(
            browser=browser,
            execution_url="https://publisher.example/report",
            timeout_seconds=0.01,
        )
    )

    assert settled is False
    assert browser.navigation_started is True


def test_deterministic_worker_start_timeout_keeps_started_browser_available() -> None:
    """The deterministic CDP route can attach after Browser Use startup settles."""

    class Browser:
        def __init__(self) -> None:
            self.start_started = False
            self.start_cancelled = False

        async def start(self) -> None:
            self.start_started = True
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                self.start_cancelled = True
                raise

    browser = Browser()

    async def exercise() -> tuple[bool, bool]:
        settled = await browser_worker_runtime.start_deterministic_playbook_browser(
            browser=browser,
            timeout_seconds=0.01,
        )
        return settled, browser.start_cancelled

    settled, cancelled_before_loop_teardown = asyncio.run(exercise())

    assert settled is False
    assert browser.start_started is True
    assert cancelled_before_loop_teardown is False


def test_browser_worker_main_redacts_identity_values_from_persisted_response(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    delivery_email = "submitted@example.com"
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path, work_email="ops@example.com"),
        delivery_email=delivery_email,
    )
    payload_path = tmp_path / "browser_agent_worker_request.json"
    response_path = tmp_path / "browser_agent_worker_response.json"
    payload_path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "request": json.loads(
                    json.dumps(request, default=lambda value: value.__dict__)
                ),
                "ctx": run_context.__dict__,
                "normalized_url": request.url,
                "execution_url": request.url,
                "download_dir": str(tmp_path / "worker-download"),
                "prompt_bundle": {
                    "schema_version": "1.0",
                    "namespace": "browser_report_download/browser_route",
                    "system_prompt_path": "system.yaml",
                    "user_prompt_path": "user.yaml",
                    "system_prompt_sha256": "system",
                    "user_prompt_sha256": "user",
                    "rendered_system_prompt": "system",
                    "rendered_user_prompt": "user",
                    "task_prompt": "task",
                },
            }
        ),
        encoding="utf-8",
    )

    def fake_run_browser_report_download_agent(**kwargs):
        return browser_runtime.BrowserAgentRunResult(
            schema_version="1.0",
            raw_model_response=json.dumps(
                {
                    "route_kind": "email_delivery",
                    "target_text": f"Work email -> {delivery_email}",
                    "observed_evidence": [
                        f"typed ops@example.com and {delivery_email}"
                    ],
                }
            ),
            final_page_url="https://example.com/thanks",
            final_page_title="Thanks",
            final_page_html=(
                f'<html><input value="ops@example.com">'
                f'<a href="https://example.com/download?email={delivery_email}">'
                "download</a></html>"
            ),
            downloaded_files=[],
            attachment_paths=[],
            network_resource_urls=[
                f"https://example.com/pixel?email={delivery_email}",
            ],
            network_events=[],
            html_snapshot_path="",
            screenshot_path="",
        )

    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "run_browser_report_download_agent",
        fake_run_browser_report_download_agent,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime,
        "setup_logging",
        lambda *args, **kwargs: None,
    )
    external_boundary_mocks_only.setattr(
        browser_worker_runtime.sys,
        "argv",
        [
            "browser_worker.py",
            str(payload_path),
            str(response_path),
        ],
    )

    assert browser_worker_runtime.main() == 0

    persisted = response_path.read_text(encoding="utf-8")
    assert "ops@example.com" not in persisted
    assert delivery_email not in persisted
    assert "***REDACTED***" in persisted


def test_browser_worker_subprocess_forces_utf8_without_capturing_child_output(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )
    prompt_bundle = prompt_runtime.BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user",
        task_prompt="task",
    )

    def fake_run(*args, **kwargs):
        assert kwargs["stdout"] == subprocess.DEVNULL
        assert kwargs["stderr"] == subprocess.DEVNULL
        assert kwargs["env"][browser_runtime._BROWSER_AGENT_WORKER_ENV] == "1"
        assert kwargs["env"]["PYTHONIOENCODING"] == "utf-8"
        assert kwargs["env"]["PYTHONUTF8"] == "1"
        assert kwargs["env"]["NO_COLOR"] == "1"
        assert kwargs["env"]["RICH_DISABLE"] == "1"
        assert kwargs["env"]["TIMEOUT_AgentEventBusStop"] == "0"
        response_path = Path(args[0][-1])
        response_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "ok",
                    "result": {
                        "schema_version": "1.0",
                        "raw_model_response": "{}",
                        "final_page_url": "https://example.com/final",
                        "final_page_title": "Final",
                        "final_page_html": "<html></html>",
                        "downloaded_files": [],
                        "attachment_paths": [],
                        "network_resource_urls": [],
                        "network_events": [],
                        "html_snapshot_path": "",
                        "screenshot_path": "",
                    },
                    "error": None,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=None,
        )

    external_boundary_mocks_only.setattr(browser_runtime.subprocess, "run", fake_run)

    result = browser_runtime._run_browser_report_download_agent_subprocess(
        request=request,
        ctx=run_context,
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=tmp_path / "worker-download",
        prompt_bundle=prompt_bundle,
    )

    assert result.final_page_url == "https://example.com/final"
    completion_events = [
        event
        for event in _service_events(caplog)
        if event.get("event") == "browser_report_download_worker_complete"
    ]
    assert len(completion_events) == 1
    completion_fields = completion_events[0]["fields"]
    assert completion_fields["worker_output_captured"] is False
    assert "worker_output_excerpt" not in completion_fields
    assert_logs_have_required_fields(_service_events(caplog))


def test_headed_browser_run_stays_in_process(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=replace(_settings(tmp_path), headed=True),
    )

    assert (
        browser_runtime._should_run_browser_agent_in_subprocess(
            object(),
            request=request,
        )
        is False
    )


def test_browser_worker_subprocess_discards_sensitive_request_payload_after_run(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )
    prompt_bundle = prompt_runtime.BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user with Market Lense",
        task_prompt="task with openrouter-key and Market Lense",
    )
    download_dir = tmp_path / "worker-download"
    protocol_dir = download_dir / "_browser_worker_protocol"
    payload_path = protocol_dir / "browser_agent_worker_request.json"
    response_path = protocol_dir / "browser_agent_worker_response.json"

    def fake_run(*args, **kwargs):
        assert payload_path.exists()
        payload_text = payload_path.read_text(encoding="utf-8")
        assert "openrouter-key" in payload_text
        assert "Market Lense" in payload_text
        response_path = Path(args[0][-1])
        response_path.write_text(
            json.dumps(
                {
                    "schema_version": "1.0",
                    "status": "ok",
                    "result": {
                        "schema_version": "1.0",
                        "raw_model_response": "{}",
                        "final_page_url": "https://example.com/final",
                        "final_page_title": "Final",
                        "final_page_html": "<html></html>",
                        "downloaded_files": [],
                        "attachment_paths": [],
                        "network_resource_urls": [],
                        "network_events": [],
                        "html_snapshot_path": "",
                        "screenshot_path": "",
                    },
                    "error": None,
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(args=args[0], returncode=0, stdout="")

    external_boundary_mocks_only.setattr(browser_runtime.subprocess, "run", fake_run)

    result = browser_runtime._run_browser_report_download_agent_subprocess(
        request=request,
        ctx=run_context,
        normalized_url=request.url,
        execution_url=request.url,
        download_dir=download_dir,
        prompt_bundle=prompt_bundle,
    )

    assert result.final_page_url == "https://example.com/final"
    assert response_path.exists()
    assert not payload_path.exists()


def test_browser_worker_subprocess_discards_sensitive_request_payload_after_timeout(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )
    prompt_bundle = prompt_runtime.BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user with Market Lense",
        task_prompt="task with openrouter-key and Market Lense",
    )
    download_dir = tmp_path / "worker-download"
    payload_path = (
        download_dir / "_browser_worker_protocol" / "browser_agent_worker_request.json"
    )

    def fake_run(*args, **kwargs):
        assert payload_path.exists()
        raise subprocess.TimeoutExpired(
            cmd=args[0],
            timeout=kwargs["timeout"],
            output="INFO browser_use.Agent still running",
        )

    external_boundary_mocks_only.setattr(browser_runtime.subprocess, "run", fake_run)

    with pytest.raises(AppError) as exc_info:
        browser_runtime._run_browser_report_download_agent_subprocess(
            request=request,
            ctx=run_context,
            normalized_url=request.url,
            execution_url=request.url,
            download_dir=download_dir,
            prompt_bundle=prompt_bundle,
        )

    assert exc_info.value.code == "browser_download_agent_timeout"
    assert not payload_path.exists()


def test_pre_llm_autofill_runs_on_async_browser_session(
    tmp_path: Path,
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    """The standard helper runs before Agent on the BrowserSession event loop."""

    class AsyncBrowser:
        def __init__(self) -> None:
            self.start_calls = 0
            self.url = "https://example.com/report"
            self.title = "Report form"
            self.html = "<html><body>Thanks for requesting the report</body></html>"

            class Page:
                async def evaluate(_self, expression: str):
                    if "standardFormSubmit" in expression:
                        return {
                            "attempted_count": 1,
                            "filled_count": 1,
                            "selected_count": 0,
                            "mandatory_agreement_checked_count": 0,
                            "resolved_control_count": 1,
                            "submitted": True,
                            "final_url": self.url,
                            "resolved_fields": ["Work email"],
                            "unresolved_fields": [],
                        }
                    if "document.documentElement" in expression:
                        return self.html
                    return {"status": "ok"}

            self.page = Page()

        async def start(self) -> None:
            self.start_calls += 1

        async def get_current_page(self):
            return self.page

        async def get_current_page_url(self) -> str:
            return self.url

        async def get_current_page_title(self) -> str:
            return self.title

    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        route_family_hint="browser_email_form",
        settings=_settings(tmp_path),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)
    browser = AsyncBrowser()

    result = browser_runtime._try_pre_llm_standard_form_submit(
        request=request,
        browser=browser,
        ctx=run_context,
        normalized_url=request.url,
        execution_url=request.url,
    )

    assert result is not None
    assert browser.start_calls == 1
    assert "deterministic pre-LLM form autofill" in result.raw_model_response
    assert_logs_have_required_fields(caplog.records)


def test_browser_worker_execution_never_dispatches_a_nested_worker(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )

    assert (
        browser_runtime._should_run_browser_agent_in_subprocess(
            object(),
            request=request,
            inside_worker=True,
        )
        is False
    )


def test_browser_worker_subprocess_reports_missing_result_without_child_output(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
    )
    prompt_bundle = prompt_runtime.BrowserDownloadPromptBundle(
        schema_version="1.0",
        namespace="browser_report_download/browser_route",
        system_prompt_path="system.yaml",
        user_prompt_path="user.yaml",
        system_prompt_sha256="system",
        user_prompt_sha256="user",
        rendered_system_prompt="system",
        rendered_user_prompt="user",
        task_prompt="task",
    )

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout=None,
        )

    external_boundary_mocks_only.setattr(browser_runtime.subprocess, "run", fake_run)

    with pytest.raises(AppError) as exc_info:
        browser_runtime._run_browser_report_download_agent_subprocess(
            request=request,
            ctx=run_context,
            normalized_url=request.url,
            execution_url=request.url,
            download_dir=tmp_path / "worker-download",
            prompt_bundle=prompt_bundle,
        )

    assert exc_info.value.code == "browser_download_agent_missing_result"
    assert exc_info.value.context == {
        "normalized_url": "https://example.com/report",
        "return_code": 1,
        "worker_output_excerpt": "",
    }
    completion_events = [
        event
        for event in _service_events(caplog)
        if event.get("event") == "browser_report_download_worker_complete"
    ]
    assert len(completion_events) == 1
    completion_fields = completion_events[0]["fields"]
    assert completion_fields["worker_output_captured"] is False
    assert "worker_output_excerpt" not in completion_fields
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_cleans_stale_browser_use_temp_dirs_before_launch(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    stale_profile_dir = tmp_path / "browser-use-user-data-dir-stale"
    stale_profile_dir.mkdir(parents=True, exist_ok=True)
    (stale_profile_dir / "SingletonLock").write_text("lock", encoding="utf-8")
    stale_download_dir = tmp_path / "browser-use-downloads-stale"
    stale_download_dir.mkdir(parents=True, exist_ok=True)
    (stale_download_dir / "artifact.tmp").write_text("x", encoding="utf-8")
    old_timestamp = time.time() - (
        browser_runtime._STALE_BROWSER_USE_TEMP_DIR_MIN_AGE_SECONDS + 60.0
    )
    os.utime(stale_profile_dir, (old_timestamp, old_timestamp))
    os.utime(stale_download_dir, (old_timestamp, old_timestamp))

    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime.tempfile,
        "gettempdir",
        lambda: str(tmp_path),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/stale-temp-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert not stale_profile_dir.exists()
    assert not stale_download_dir.exists()


def test_download_report_with_browser_use_cleans_new_browser_use_temp_dirs_after_run(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class TempLeakAgent(original_runtime):
        def run_sync(self, max_steps: int):
            leaked_profile_dir = tmp_path / "browseruse-tmp-created-during-run"
            leaked_profile_dir.mkdir(parents=True, exist_ok=True)
            (leaked_profile_dir / "cache.tmp").write_text("temp", encoding="utf-8")
            return super().run_sync(max_steps)

    runtime.Agent = TempLeakAgent
    external_boundary_mocks_only.setattr(
        browser_runtime.tempfile,
        "gettempdir",
        lambda: str(tmp_path),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/temp-leak-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert not (tmp_path / "browseruse-tmp-created-during-run").exists()


__all__ = [
    "test_browser_worker_main_preserves_candidate_trace",
    "test_browser_worker_main_preserves_identity_option_aliases",
    "test_browser_worker_main_redacts_identity_values_from_persisted_response",
    "test_browser_worker_subprocess_forces_utf8_without_capturing_child_output",
    "test_headed_browser_run_stays_in_process",
    "test_browser_worker_subprocess_discards_sensitive_request_payload_after_run",
    "test_browser_worker_subprocess_discards_sensitive_request_payload_after_timeout",
    "test_browser_worker_execution_never_dispatches_a_nested_worker",
    "test_pre_llm_autofill_runs_on_async_browser_session",
    "test_browser_worker_subprocess_reports_missing_result_without_child_output",
    "test_download_report_with_browser_use_cleans_stale_browser_use_temp_dirs_before_launch",
    "test_download_report_with_browser_use_cleans_new_browser_use_temp_dirs_after_run",
]
