# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_download_report_with_browser_use_fetches_relative_observed_pdf_candidate(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_calls: list[str] = []
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Opened the gated page and found a form.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class RelativePdfObservedAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["route_family"] = "browser_email_form"
            payload["encountered_form_fields"] = ["Business Email", "Country"]
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = "Country field could not be selected."
            self.browser.url = "https://example.com/resources/report"
            self.browser.title = "Example report"
            self.browser.html = (
                "<html><body><a href='/files/live/sites/www/files/ebooks/report.pdf'>"
                "PDF</a></body></html>"
            )

            class RelativePdfObservedHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return RelativePdfObservedHistory()

    def _download_pdf_from_url(**kwargs) -> None:
        external_calls.append("download_pdf")
        assert kwargs["pdf_url"] == (
            "https://example.com/files/live/sites/www/files/ebooks/report.pdf"
        )
        Path(kwargs["destination_path"]).write_bytes(b"%PDF-1.7 observed")

    runtime.Agent = RelativePdfObservedAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime,
        "download_pdf_from_url",
        _download_pdf_from_url,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/resources/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert response.downloaded_file_path.endswith("report.pdf")
    assert external_calls == ["download_pdf"]

def test_download_report_with_browser_use_fetches_pdf_after_terminal_html_recovery(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    external_calls: list[str] = []
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Opened the gated page and found a form.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent
    observed_relative_pdf = "/files/live/sites/www/files/ebooks/report.pdf"

    class EmptyHtmlPdfObservedAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/resources/report"
            self.browser.title = "Example report"
            self.browser.html = ""
            payload = {
                "route_kind": "email_delivery",
                "route_summary": "Opened the gated page and found a form.",
                "route_family": "browser_email_form",
                "resolved_target_url": "https://example.com/resources/report",
                "final_page_url": "https://example.com/resources/report",
                "email_submission_completed": False,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": ["Business Email", "Country"],
                "route_steps": [],
                "post_submit_message": None,
                "confirmation_url_changed": False,
                "submit_button_state": None,
                "form_disappeared": False,
                "blocked_reason": None,
                "blocked_reason_detail": None,
                "final_page_title": "Example report",
                "terminal_text_excerpt": "Unlock this asset",
                "traversed_page_urls": ["https://example.com/resources/report"],
                "onsite_capture_path": None,
                "onsite_capture_format": None,
                "onsite_page_count": None,
                "onsite_completeness_status": None,
            }

            class EmptyHtmlPdfObservedHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return EmptyHtmlPdfObservedHistory()

    def _fetch_html_from_url(**kwargs) -> str:
        external_calls.append("fetch_html")
        return (
            "<html><body><a href='/files/live/sites/www/files/ebooks/report.pdf'>"
            "PDF</a></body></html>"
        )

    def _download_pdf_from_url(**kwargs) -> None:
        external_calls.append("download_pdf")
        assert kwargs["pdf_url"] == (
            "https://example.com/files/live/sites/www/files/ebooks/report.pdf"
        )
        Path(kwargs["destination_path"]).write_bytes(b"%PDF-1.7 observed")

    runtime.Agent = EmptyHtmlPdfObservedAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime,
        "fetch_html_from_url",
        _fetch_html_from_url,
    )
    external_boundary_mocks_only.setattr(
        http_runtime,
        "download_pdf_from_url",
        _download_pdf_from_url,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/resources/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert observed_relative_pdf in response.terminal_evidence.observed_document_urls
    assert external_calls == ["fetch_html", "download_pdf"]

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
    assert (
        "network_confirmation_request" in response.confirmation_evidence.signal_labels
    )
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
            self.browser.take_screenshot = lambda *args, **kwargs: (
                _ for _ in ()
            ).throw(RuntimeError("browser screenshot failed"))

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
    assert (
        "https://cdn.example.com/reports/final-report.pdf"
        in response.terminal_evidence.observed_document_urls
    )

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
            self.browser.take_screenshot = lambda *args, **kwargs: (
                _ for _ in ()
            ).throw(RuntimeError("browser screenshot failed"))

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
    assert (
        response.terminal_evidence.final_page_title
        == "Thank you for downloading the report"
    )
    assert response.terminal_evidence.screenshot_path
    assert Path(response.terminal_evidence.screenshot_path).exists()

def test_download_report_with_browser_use_stabilizes_transient_submit_state(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
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
    assert (
        response.terminal_evidence.final_page_title
        == "Thank you for downloading the report"
    )
    assert "success_url" in response.confirmation_evidence.signal_labels
    terminal_events = [
        event
        for event in _service_events(caplog)
        if event.get("event") == "browser_report_download_terminal_state_assessed"
    ]
    assert len(terminal_events) == 1
    assert terminal_events[0]["fields"]["quorum_met"] is True
    assert "success_url" in terminal_events[0]["fields"]["quorum_signal_labels"]
    assert "success_text" in terminal_events[0]["fields"]["quorum_signal_labels"]
    assert (
        "page_text_transient"
        not in terminal_events[0]["fields"]["quorum_transient_labels"]
    )
    assert terminal_events[0]["fields"]["attempts"] >= 0

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


def test_download_report_with_browser_use_verifies_direct_thank_you_email_delivery(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary=(
            "Navigate to the remembered thank-you page, observe the terminal "
            "report email confirmation text, and wait for inbox delivery."
        ),
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class DirectThankYouAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["final_page_url"] = "https://example.com/report-ty/"
            payload["resolved_target_url"] = "https://example.com/report-ty/"
            payload["post_submit_message"] = (
                "Thank you for downloading the report. A copy of the report "
                "will be sent to your inbox shortly."
            )
            payload["final_page_title"] = "Thank you for downloading the report"
            payload["terminal_text_excerpt"] = payload["post_submit_message"]
            payload["encountered_form_fields"] = []

            class DirectThankYouHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return DirectThankYouHistory()

    runtime.Agent = DirectThankYouAgent
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
            attempt_url="https://example.com/report-ty/",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.route_status == "verified"
    assert "delivery_text" in response.confirmation_evidence.signal_labels

__all__ = [
    "test_download_report_with_browser_use_fetches_relative_observed_pdf_candidate",
    "test_download_report_with_browser_use_fetches_pdf_after_terminal_html_recovery",
    "test_download_report_with_browser_use_uses_network_confirmation_signal",
    "test_download_report_with_browser_use_falls_back_to_page_screenshot",
    "test_download_report_with_browser_use_parses_stringified_page_evaluate_payloads",
    "test_download_report_with_browser_use_falls_back_to_history_terminal_state",
    "test_download_report_with_browser_use_stabilizes_transient_submit_state",
    "test_download_report_with_browser_use_clears_phantom_pdf_metadata_without_file",
    "test_download_report_with_browser_use_verifies_direct_thank_you_email_delivery",
]
