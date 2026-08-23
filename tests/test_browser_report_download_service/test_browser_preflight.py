from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from src.contracts.browser_download import (
    BrowserPreflightProbeResponse,
    BrowserPreflightProbeResult,
    BrowserReportDownloadRequest,
)
from src.services._browser_report_download import preflight as preflight_runtime
from src.services._browser_report_download import browser as browser_runtime
from src.utils.errors import AppError

from .builders import (
    _FakeResponse,
    _runtime,
    _settings,
    browser_runtime,
    http_runtime,
    service,
)


def test_preflight_thread_envelope_returns_when_async_cancellation_is_ignored() -> None:
    release = threading.Event()

    async def ignores_cancellation() -> None:
        while not release.is_set():
            try:
                await asyncio.sleep(0.001)
            except asyncio.CancelledError:
                continue

    coroutine = ignores_cancellation()
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="browser preflight session timed out"):
            try:
                preflight_runtime._run_coroutine_in_thread(
                    coroutine,
                    timeout_seconds=0.01,
                    grace_seconds=0.01,
                )
            except TypeError:
                coroutine.close()
                raise
    finally:
        release.set()
    assert time.monotonic() - started < 0.5


def test_preflight_runs_on_the_calling_thread_when_no_event_loop_is_active() -> None:
    caller_thread = threading.get_ident()

    async def record_thread() -> int:
        return threading.get_ident()

    assert (
        preflight_runtime._run_preflight_coroutine(
            record_thread(),
            timeout_seconds=0.1,
            grace_seconds=0.1,
        )
        == caller_thread
    )


def test_preflight_runner_preserves_the_browser_event_loop_for_handoff() -> None:
    async def record_loop_id() -> int:
        return id(asyncio.get_running_loop())

    with asyncio.Runner() as runner:
        first_loop_id = preflight_runtime._run_preflight_coroutine(
            record_loop_id(),
            timeout_seconds=0.1,
            grace_seconds=0.1,
            event_loop_runner=runner,
        )
        second_loop_id = preflight_runtime._run_preflight_coroutine(
            record_loop_id(),
            timeout_seconds=0.1,
            grace_seconds=0.1,
            event_loop_runner=runner,
        )

    assert first_loop_id == second_loop_id


def test_preflight_runner_shutdown_does_not_block_on_a_stubborn_agent_task() -> None:
    release = asyncio.Event()

    async def ignores_cancellation() -> None:
        while not release.is_set():
            try:
                await asyncio.sleep(0.001)
            except asyncio.CancelledError:
                continue

    async def start_task() -> asyncio.Task[None]:
        return asyncio.create_task(ignores_cancellation())

    runner = asyncio.Runner()
    session = SimpleNamespace(event_loop_runner=runner)
    task = runner.run(start_task())
    started = time.monotonic()
    browser_runtime._close_preflight_event_loop_runner(session)

    assert time.monotonic() - started < 3.0
    assert session.event_loop_runner is None

    async def release_task() -> None:
        release.set()
        await asyncio.wait_for(task, timeout=0.5)

    runner.run(release_task())
    runner.close()


def test_augmented_error_context_retains_scalar_preflight_diagnostics() -> None:
    probe = BrowserPreflightProbeResult(
        schema_version="1.0",
        status="failed",
        started_url="https://example.com/report",
        final_url="https://example.com/report",
        final_title="",
        html_size=0,
        event_drain_seconds=0.35,
        duration_seconds=24.0,
        candidate_pdf_urls=[],
        selected_pdf_url="",
        observed_event_urls=[],
        network_event_count=0,
        evidence_labels=["preflight_failed", "preflight_phase_browser_start"],
        escalation_reason="browser preflight session timed out",
        avoided_agent_call=False,
        false_negative_rate_sample=0.0,
    )

    error = service._with_augmented_error_context(
        AppError(
            code="browser_download_agent_timeout",
            message="Browser agent timed out",
            retryable=False,
        ),
        normalized_url="https://example.com/report",
        execution_url="https://example.com/report",
        download_dir="downloads",
        route_family_hint="browser_email_form",
        browser_preflight_probe=probe,
    )

    assert error.context["preflight_diagnostics"] == {
        "status": "failed",
        "phase": "browser_start",
        "duration_seconds": 24.0,
        "final_url": "https://example.com/report",
        "html_size": 0,
        "evidence_labels": [
            "preflight_failed",
            "preflight_phase_browser_start",
        ],
    }


class _PreflightPage:
    def __init__(self, *, pdf_url: str | None, page_url: str) -> None:
        self.url = page_url
        self._pdf_url = pdf_url

    def title(self) -> str:
        return "Rendered publisher report"

    def content(self) -> str:
        if not self._pdf_url:
            return "<html><body><h1>Rendered publisher report</h1></body></html>"
        return (
            "<html><body><h1>Rendered publisher report</h1>"
            f'<a id="download" href="{self._pdf_url}">Download PDF</a>'
            "</body></html>"
        )

    def wait_for_load_state(self, state: str, timeout: int | None = None) -> None:
        return None

    def evaluate(self, script: str) -> object:
        if "getEntriesByType" in script:
            return [self._pdf_url] if self._pdf_url else []
        return {
            "pdf_candidates": [self._pdf_url] if self._pdf_url else [],
            "form_text": [],
            "location_href": self.url,
            "title": "Rendered publisher report",
            "html_size": len(self.content()),
            "cookie_names": ["session"],
            "local_storage_keys": ["publisherConsent"],
        }


class _PreflightBrowser:
    def __init__(
        self,
        *,
        downloads_path: str,
        headless: bool,
        auto_download_pdfs: bool,
        keep_alive: bool,
        pdf_url: str | None,
        user_data_dir: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.downloads_path = downloads_path
        self.headless = headless
        self.auto_download_pdfs = auto_download_pdfs
        self.keep_alive = keep_alive
        self.user_data_dir = user_data_dir
        self.user_agent = user_agent
        self.pdf_url = pdf_url
        self.url = ""
        self.title = ""
        self.html = ""
        self.downloaded_files: list[str] = []
        self.network_resource_urls: list[str] = []
        self.network_events: list[dict[str, str]] = []
        self.stopped = False

    def start(self) -> None:
        return None

    def navigate_to(self, url: str) -> None:
        self.url = url
        self.title = "Rendered publisher report"

    def get_current_page(self) -> _PreflightPage:
        return _PreflightPage(pdf_url=self.pdf_url, page_url=self.url)

    def kill(self) -> None:
        self.stopped = True

    def take_screenshot(self, path=None, **kwargs):
        if path:
            Path(path).write_bytes(b"fake-screenshot")
        return b"fake-screenshot"


def _preflight_runtime(*, pdf_url: str | None):
    class Browser(_PreflightBrowser):
        instances: list["Browser"] = []

        def __init__(self, *, user_agent: str | None = None, **kwargs):
            super().__init__(pdf_url=pdf_url, user_agent=user_agent, **kwargs)
            self.__class__.instances.append(self)

    return SimpleNamespace(Browser=Browser)


def _terminal_not_found_preflight_runtime():
    class TerminalNotFoundPage(_PreflightPage):
        def __init__(self, *, page_url: str) -> None:
            super().__init__(pdf_url=None, page_url=page_url)

        def title(self) -> str:
            return "404 Not Found"

        def content(self) -> str:
            return (
                "<html><body><h1>Not Found</h1>"
                "<p>The requested URL was not found on this server.</p>"
                "</body></html>"
            )

    class Browser(_PreflightBrowser):
        def __init__(self, **kwargs) -> None:
            super().__init__(pdf_url=None, **kwargs)

        def get_current_page(self) -> TerminalNotFoundPage:
            return TerminalNotFoundPage(page_url=self.url)

    return SimpleNamespace(Browser=Browser)


def _delayed_terminal_not_found_preflight_runtime():
    final_url = "https://www4.example.com/commerce-media-trends-report"

    class TerminalNotFoundPage(_PreflightPage):
        def __init__(self) -> None:
            super().__init__(pdf_url=None, page_url=final_url)

        def title(self) -> str:
            return "404 Not Found"

        def content(self) -> str:
            return (
                "<html><body><h1>Not Found</h1>"
                "<p>The requested URL was not found on this server.</p>"
                "</body></html>"
            )

    class Browser(_PreflightBrowser):
        def __init__(self, **kwargs) -> None:
            super().__init__(pdf_url=None, **kwargs)
            self.page_reads = 0

        def get_current_page(self) -> _PreflightPage:
            self.page_reads += 1
            if self.page_reads == 1:
                class LoadingPage(_PreflightPage):
                    def content(self) -> str:
                        return ""

                    def evaluate(self, script: str) -> object:
                        if "getEntriesByType" in script:
                            return []
                        if "documentElement" in script:
                            return ""
                        return {
                            "pdf_candidates": [],
                            "form_text": [],
                            "location_href": self.url,
                            "title": "",
                            "html_size": 0,
                            "cookie_names": [],
                            "local_storage_keys": [],
                        }

                return LoadingPage(pdf_url=None, page_url=self.url)
            self.url = final_url
            return TerminalNotFoundPage()

    return SimpleNamespace(Browser=Browser)


def _terminal_access_forbidden_preflight_runtime():
    class TerminalAccessForbiddenPage(_PreflightPage):
        def __init__(self, *, page_url: str) -> None:
            super().__init__(pdf_url=None, page_url=page_url)

        def title(self) -> str:
            return "403 Forbidden"

        def content(self) -> str:
            return (
                "<html><head><title>403 Forbidden</title></head>"
                "<body><h1>Error 403 Forbidden</h1><p>Forbidden</p></body></html>"
            )

    class Browser(_PreflightBrowser):
        def __init__(self, **kwargs) -> None:
            super().__init__(pdf_url=None, **kwargs)

        def get_current_page(self) -> TerminalAccessForbiddenPage:
            return TerminalAccessForbiddenPage(page_url=self.url)

    return SimpleNamespace(Browser=Browser)


def _preflight_agent_runtime(*, tmp_path: Path, pdf_url: str | None):
    runtime = _preflight_runtime(pdf_url=pdf_url)
    agent_runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and download the report.",
        create_pdf=True,
        email_submission_completed=None,
    )
    runtime.Agent = agent_runtime.Agent
    runtime.ChatOpenRouter = agent_runtime.ChatOpenRouter
    return runtime


def test_browser_preflight_contract_round_trip() -> None:
    probe = BrowserPreflightProbeResult(
        schema_version="1.0",
        status="confirmed_direct_pdf",
        started_url="https://example.com/report",
        final_url="https://example.com/report",
        final_title="Example report",
        html_size=250,
        event_drain_seconds=0.35,
        duration_seconds=1.25,
        candidate_pdf_urls=["https://example.com/report.pdf"],
        selected_pdf_url="https://example.com/report.pdf",
        observed_event_urls=["https://example.com/report.pdf"],
        network_event_count=1,
        evidence_labels=["page_info", "js_rendered_dom", "network_event"],
        escalation_reason="",
        avoided_agent_call=True,
        false_negative_rate_sample=0.0,
    )
    response = BrowserPreflightProbeResponse(schema_version="1.0", probe=probe)

    restored_probe = BrowserPreflightProbeResult(**asdict(probe))
    restored_response = BrowserPreflightProbeResponse(
        schema_version=response.schema_version,
        probe=BrowserPreflightProbeResult(**asdict(response.probe)),
    )

    assert restored_probe == probe
    assert restored_response == response
    assert restored_probe.status == "confirmed_direct_pdf"
    assert restored_probe.selected_pdf_url.endswith(".pdf")
    assert restored_probe.evidence_labels
    assert restored_response.probe.avoided_agent_call is True


def test_browser_preflight_recognizes_terminal_not_found_page() -> None:
    assert preflight_runtime._is_terminal_not_found_page(
        title="404 Not Found",
        html=(
            "<html><body><h1>Not Found</h1><p>The requested URL was not found "
            "on this server.</p></body></html>"
        ),
    )


def test_browser_preflight_waits_for_redirected_terminal_not_found_page(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    original_url = "https://go.example.com/commerce-media-trends-report"
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: _delayed_terminal_not_found_preflight_runtime(),
    )

    response = preflight_runtime.try_browser_preflight_probe(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url=original_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        ctx=run_context,
        normalized_url=original_url,
        execution_url=original_url,
        download_dir=tmp_path / "downloads",
        force_for_http_access_status=True,
    )

    assert response.probe.status == "terminal_static_archive"
    assert response.probe.final_url == "https://www4.example.com/commerce-media-trends-report"
    assert response.probe.avoided_agent_call is True
    assert not preflight_runtime._is_terminal_not_found_page(
        title="Commerce media trends report",
        html=(
            "<html><body><p>404 brands contributed data to this report.</p>"
            "</body></html>"
        ),
    )


def test_browser_preflight_recognizes_terminal_access_forbidden_page() -> None:
    assert preflight_runtime._is_terminal_access_forbidden_page(
        title="403 Forbidden",
        html=(
            "<html><body><h1>Error 403 Forbidden</h1><p>Forbidden</p>"
            "</body></html>"
        ),
    )
    assert not preflight_runtime._is_terminal_access_forbidden_page(
        title="Marketing report",
        html="<html><body><p>403 brands contributed data.</p></body></html>",
    )


def test_browser_preflight_skips_email_route_without_positive_evidence(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: _preflight_runtime(pdf_url=None),
    )
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
        route_family_hint="browser_email_form",
    )

    response = preflight_runtime.try_browser_preflight_probe(
        request=request,
        ctx=run_context,
        normalized_url="https://example.com/report",
        execution_url="https://example.com/report",
        download_dir=tmp_path / "downloads",
    )

    assert response.probe.status == "escalated"
    assert response.probe.escalation_reason == (
        "preflight_evidence_insufficient_for_route_family"
    )
    assert response.probe.reuse_state is not None
    assert response.probe.reuse_state.status == "skipped"


def test_browser_preflight_runs_for_email_route_when_http_access_signal_requires_it(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: _preflight_runtime(pdf_url=None),
    )
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://example.com/report",
        settings=_settings(tmp_path),
        route_family_hint="browser_email_form",
    )

    response = preflight_runtime.try_browser_preflight_probe(
        request=request,
        ctx=run_context,
        normalized_url="https://example.com/report",
        execution_url="https://example.com/report",
        download_dir=tmp_path / "downloads",
        force_for_http_access_status=True,
    )

    assert response.probe.status == "escalated"
    assert response.probe.escalation_reason == "no_rendered_pdf_candidate"
    assert response.probe.reuse_state is not None
    assert response.probe.reuse_state.status == "available"


def test_browser_preflight_uses_standard_browser_user_agent(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _preflight_runtime(pdf_url=None)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    preflight_runtime.try_browser_preflight_probe(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        ctx=run_context,
        normalized_url="https://example.com/report",
        execution_url="https://example.com/report",
        download_dir=tmp_path / "downloads",
        force_for_http_access_status=True,
    )

    assert runtime.Browser.instances[0].user_agent == (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    )


def test_download_report_with_browser_use_uses_forced_preflight_for_http_access_status(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    page_url = "https://go.example.com/commerce-media-trends-report"

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=(
                b"<html><head><title>403 Forbidden</title></head>"
                b"<body><h1>Error 403 Forbidden</h1><p>Forbidden</p></body></html>"
            ),
            status_code=403,
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        service,
        "try_rendered_terminal_preflight",
        lambda **kwargs: None,
    )
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: _terminal_not_found_preflight_runtime(),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("full browser-use Agent should not load after terminal preflight")
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_family == "browser_preflight_terminal_static_archive"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_static_archive"
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_blocks_terminal_access_forbidden_preflight(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    page_url = "https://go.example.com/commerce-media-trends-report"

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=(
                b"<html><head><title>403 Forbidden</title></head>"
                b"<body><h1>Error 403 Forbidden</h1><p>Forbidden</p></body></html>"
            ),
            status_code=403,
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        service,
        "try_rendered_terminal_preflight",
        lambda **kwargs: None,
    )
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: _terminal_access_forbidden_preflight_runtime(),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("full browser-use Agent should not load after 403 preflight")
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_family == "browser_preflight_terminal_access_forbidden"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_static_archive"
    assert "preflight_terminal_access_forbidden" in response.terminal_evidence.evidence_labels
    assert_no_defaulted_required_fields(response)


def test_browser_preflight_confirms_js_rendered_pdf_without_full_agent(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    page_url = "https://example.com/rendered-report"
    pdf_url = "https://example.com/assets/rendered-report.pdf"

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url == pdf_url:
            return _FakeResponse(
                content=b"%PDF-1.7 rendered pdf",
                headers={"Content-Type": "application/pdf"},
                url=pdf_url,
            )
        return _FakeResponse(
            content=b"<html><body><h1>Rendered publisher report</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: _preflight_runtime(pdf_url=pdf_url),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("full browser-use agent should not load after preflight")
        ),
    )
    caplog.set_level(logging.INFO, logger=preflight_runtime.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.route_family == "browser_preflight_js_pdf_probe"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(response.downloaded_file_path).read_bytes().startswith(b"%PDF-")
    assert response.route_steps[1].target_url == pdf_url
    assert response.route_steps[1].verification_status == "verified"
    assert (
        "browser_preflight_js_pdf_probe" in response.terminal_evidence.evidence_labels
    )
    assert "preflight_reuse_state_available" in response.terminal_evidence.evidence_labels
    assert_no_defaulted_required_fields(response)
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == preflight_runtime.logger.name
    ]
    complete_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_browser_preflight_complete"
    ]
    assert complete_events
    fields = complete_events[-1]["fields"]
    assert fields["status"] == "confirmed_direct_pdf"
    assert fields["avoided_agent_call"] is True
    assert fields["preflight_duration_seconds"] >= 0


def test_browser_preflight_escalates_cleanly_when_evidence_is_insufficient(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_url = "https://example.com/report-with-hidden-route"
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page, click Download report, and wait for the PDF save to finish.",
        create_pdf=True,
        email_submission_completed=None,
    )
    shared_runtime = _preflight_agent_runtime(tmp_path=tmp_path, pdf_url=None)
    full_agent_loaded = {"value": False}

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"<html><body><h1>Report with hidden route</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    def load_agent_runtime(module_name: str) -> Any:
        full_agent_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: shared_runtime,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (load_agent_runtime(module_name), shared_runtime)[1],
    )
    caplog.set_level(logging.INFO)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    events = [json.loads(record.message) for record in caplog.records]
    escalation_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_browser_preflight_escalation"
    ]
    outcome_events = [
        event
        for event in events
        if event.get("event")
        == "browser_report_download_browser_preflight_agent_outcome"
    ]
    assert escalation_events
    assert escalation_events[-1]["fields"]["escalation_reason"] == (
        "no_rendered_pdf_candidate"
    )
    assert outcome_events
    assert outcome_events[-1]["fields"]["false_negative_rate_sample"] == 1.0


def test_browser_preflight_escalation_reuses_the_open_browser_session(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_url = "https://example.com/report-with-hidden-route"
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and download the report.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_browser = runtime.Browser
    original_agent = runtime.Agent
    browser_instances: list[object] = []
    agent_browser_ids: list[int] = []
    agent_cookie_headers: list[str] = []
    agent_page_urls: list[str] = []

    class SharedPage:
        def __init__(self, browser) -> None:
            self._browser = browser

        @property
        def url(self) -> str:
            return self._browser.url

        def title(self) -> str:
            return self._browser.title

        def content(self) -> str:
            return self._browser.html

        def evaluate(self, script: str) -> object:
            if "getEntriesByType" in script:
                return []
            if "const values" in script:
                return {
                    "pdf_candidates": [],
                    "form_text": [],
                    "location_href": self._browser.url,
                    "title": self._browser.title,
                    "html_size": len(self._browser.html),
                    "cookie_names": ["session"],
                    "local_storage_keys": ["publisherConsent"],
                }
            return []

    class SharedBrowser(original_browser):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.cookie_header = "session=retained"
            browser_instances.append(self)

        def start(self) -> None:
            return None

        def navigate_to(self, url: str) -> None:
            self.url = url
            self.title = "Rendered publisher report"
            self.html = "<html><body><h1>Rendered publisher report</h1></body></html>"

        def get_current_page(self) -> SharedPage:
            return SharedPage(self)

    class SessionObservingAgent(original_agent):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            agent_browser_ids.append(id(self.browser))
            agent_cookie_headers.append(self.browser.cookie_header)
            agent_page_urls.append(self.browser.url)

    runtime.Browser = SharedBrowser
    runtime.Agent = SessionObservingAgent

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"<html><body><h1>Report with hidden route</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert len(browser_instances) == 1
    assert agent_browser_ids == [id(browser_instances[0])]
    assert agent_cookie_headers == ["session=retained"]
    assert agent_page_urls == [page_url]


def test_async_unverified_deterministic_submit_preserves_preflight_browser_for_agent(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_url = "https://example.com/gated-report"
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Recover from the form helper and download the report.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_browser = runtime.Browser
    original_agent = runtime.Agent
    browser_instances: list[object] = []
    agent_browser_ids: list[int] = []
    agent_cookies: list[str] = []
    agent_page_urls: list[str] = []
    agent_storage_markers: list[str] = []
    agent_page_html: list[str] = []

    class AsyncPage:
        def __init__(self, browser) -> None:
            self._browser = browser

        @property
        def url(self) -> str:
            return self._browser.url

        def title(self) -> str:
            return self._browser.title

        def content(self) -> str:
            return self._browser.html

        def evaluate(self, script: str) -> object:
            if "standardFormSubmit" in script:
                self._browser.form_submit_count += 1
                self._browser.html = (
                    "<html><body><form>Work email</form>"
                    "<p>Submitting your request...</p></body></html>"
                )
                return {
                    "attempted_count": 1,
                    "filled_count": 1,
                    "selected_count": 0,
                    "mandatory_agreement_checked_count": 0,
                    "resolved_control_count": 1,
                    "submitted": True,
                    "final_url": self._browser.url,
                    "resolved_fields": ["Work email"],
                    "unresolved_fields": [],
                }
            if "getEntriesByType" in script:
                return []
            if "const values" in script:
                return {
                    "pdf_candidates": [],
                    "form_text": ["Work email"],
                    "location_href": self._browser.url,
                    "title": self._browser.title,
                    "html_size": len(self._browser.html),
                    "cookie_names": ["session"],
                    "local_storage_keys": [self._browser.storage_marker],
                }
            return []

    class AsyncBrowser(original_browser):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            self.cookie_header = "session=retained"
            self.storage_marker = "preflight-storage"
            self.start_calls = 0
            self.kill_calls = 0
            self.form_submit_count = 0
            browser_instances.append(self)

        async def start(self) -> None:
            self.start_calls += 1

        async def kill(self) -> None:
            self.kill_calls += 1

        def navigate_to(self, url: str) -> None:
            self.url = url
            self.title = "Gated report"
            self.html = "<html><body><form>Work email</form></body></html>"

        def get_current_page(self) -> AsyncPage:
            return AsyncPage(self)

    class SessionObservingAgent(original_agent):
        def __init__(self, **kwargs) -> None:
            super().__init__(**kwargs)
            agent_browser_ids.append(id(self.browser))
            agent_cookies.append(self.browser.cookie_header)
            agent_page_urls.append(self.browser.url)
            agent_storage_markers.append(self.browser.storage_marker)
            agent_page_html.append(self.browser.html)

    runtime.Browser = AsyncBrowser
    runtime.Agent = SessionObservingAgent

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"<html><body><form>Work email</form></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            source_page_url_hint=page_url,
            delivery_email="ops@example.com",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert len(browser_instances) == 1
    assert agent_browser_ids == [id(browser_instances[0])]
    assert agent_cookies == ["session=retained"]
    assert agent_page_urls == [page_url]
    assert agent_storage_markers == ["preflight-storage"]
    assert agent_page_html == [
        "<html><body><form>Work email</form>"
        "<p>Submitting your request...</p></body></html>"
    ]
    assert browser_instances[0].form_submit_count == 1
    assert browser_instances[0].kill_calls == 1


def test_browser_preflight_rejects_rendered_legal_pdf_candidate(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_url = "https://example.com/guides-whitepapers/marketing-success-metrics"
    legal_pdf_url = "https://example.com/legal/MARMIND_Online_Terms_and_DPA.pdf"
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Escalated past unrelated legal PDF and used the full route.",
        create_pdf=True,
        email_submission_completed=None,
    )
    shared_runtime = _preflight_agent_runtime(
        tmp_path=tmp_path,
        pdf_url=legal_pdf_url,
    )
    full_agent_loaded = {"value": False}

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url == legal_pdf_url:
            return _FakeResponse(
                content=b"%PDF-1.7 legal terms dpa",
                headers={"Content-Type": "application/pdf"},
                url=legal_pdf_url,
            )
        return _FakeResponse(
            content=b"<html><body><h1>Marketing Success Metrics</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    def load_agent_runtime(module_name: str) -> Any:
        full_agent_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: shared_runtime,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (load_agent_runtime(module_name), shared_runtime)[1],
    )
    caplog.set_level(logging.INFO)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.route_family != "browser_preflight_js_pdf_probe"
    events = [json.loads(record.message) for record in caplog.records]
    escalation_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_browser_preflight_escalation"
    ]
    assert escalation_events
    assert escalation_events[-1]["fields"]["escalation_reason"] == (
        "no_rendered_pdf_candidate"
    )


def test_browser_preflight_rejects_title_mismatched_pdf_candidate(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    page_url = "https://example.com/insights/food-and-drink/global-food-and-drink-trends"
    unrelated_pdf_url = "https://assets.example.com/Mintel_Gender_Pay_Gap_Report_2025.pdf"
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Escalated past unrelated rendered PDF and used the full route.",
        create_pdf=True,
        email_submission_completed=None,
    )
    shared_runtime = _preflight_agent_runtime(
        tmp_path=tmp_path,
        pdf_url=unrelated_pdf_url,
    )
    full_agent_loaded = {"value": False}

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if url == unrelated_pdf_url:
            raise AssertionError("title-mismatched PDF must not be downloaded")
        return _FakeResponse(
            content=(
                b"<html><body><h1>2026 Global Food & Drink Predictions</h1></body></html>"
            ),
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=page_url,
        )

    def load_agent_runtime(module_name: str) -> Any:
        full_agent_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        preflight_runtime,
        "import_module",
        lambda module_name: shared_runtime,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (load_agent_runtime(module_name), shared_runtime)[1],
    )
    caplog.set_level(logging.INFO)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
            report_title="2026 Global Food & Drink Predictions",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.route_family != "browser_preflight_js_pdf_probe"
    events = [json.loads(record.message) for record in caplog.records]
    escalation_events = [
        event
        for event in events
        if event.get("event") == "browser_report_download_browser_preflight_escalation"
    ]
    assert escalation_events
    assert escalation_events[-1]["fields"]["candidate_pdf_url_count"] == 0
