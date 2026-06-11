# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_browser_report_download_result_trusts_explicit_lookup_enum_blocker(
    tmp_path: Path,
    run_context,
) -> None:
    settings = replace(
        _settings(tmp_path),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value="ops@example.com",
                    aliases=["email", "email address"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="company",
                    label="Company",
                    value="Market Lense",
                    aliases=["company"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="location",
                    label="Location",
                    value="Austria",
                    aliases=["country", "location"],
                ),
            ],
        ),
    )
    payload = {
        "route_kind": "email_delivery",
        "route_summary": (
            "Opened the report page, filled the form, and failed to submit "
            "because the Location lookup could not be selected."
        ),
        "route_family": "browser_email_form",
        "resolved_target_url": "https://example.com/report#download",
        "final_page_url": "https://example.com/report#download",
        "email_submission_completed": False,
        "downloaded_file_path": None,
        "downloaded_file_name": None,
        "downloaded_mime_type": None,
        "encountered_form_fields": [
            "Business Email Address",
            "Company Name",
            "Location",
        ],
        "route_steps": [
            {
                "index": 0,
                "action": "click",
                "target_text": "Submit",
                "target_role": "button",
                "target_url": "https://example.com/report#download",
                "result": "Clicked Submit button.",
            }
        ],
        "post_submit_message": None,
        "confirmation_url_changed": False,
        "submit_button_state": None,
        "form_disappeared": False,
        "blocked_reason": "blocked_unknown_required_enum",
        "blocked_reason_detail": (
            "The Location field could not be properly selected, and the form "
            "submission failed."
        ),
        "final_page_title": "Example report",
        "terminal_text_excerpt": "",
        "traversed_page_urls": ["https://example.com/report#download"],
        "onsite_capture_path": None,
        "onsite_capture_format": None,
        "onsite_page_count": None,
        "onsite_completeness_status": None,
    }

    response = artifact_runtime.finalize_browser_report_download_result(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        ),
        ctx=run_context,
        normalized_url="https://example.com/report",
        delivery_email="ops@example.com",
        download_dir=tmp_path,
        browser_run=browser_runtime.BrowserAgentRunResult(
            schema_version="1.0",
            raw_model_response=json.dumps(payload),
            final_page_url="https://example.com/report#download",
            final_page_title="Example report",
            final_page_html="",
            downloaded_files=[],
            attachment_paths=[],
            network_resource_urls=[],
            network_events=[],
            html_snapshot_path="",
            screenshot_path="",
        ),
    )

    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_unknown_required_enum"
    assert "could not be properly selected" in str(response.blocked_reason_detail)

def test_download_report_with_browser_use_does_not_infer_static_archive_from_please_wait(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form and clicked submit.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class PendingSubmitAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Business Email",
                "Company Name",
                "Online Annual Revenue",
                "Country",
            ]
            payload["post_submit_message"] = "Please Wait"
            payload["submit_button_state"] = "disabled"
            payload["terminal_text_excerpt"] = (
                "Fill out the form below to have your copy sent directly to your inbox."
            )

            class PendingSubmitHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return PendingSubmitHistory()

    runtime.Agent = PendingSubmitAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://www.bigcommerce.com/resources/reports/global-b2b-buyer-report-cdl-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason != "blocked_static_archive"

def test_download_report_with_browser_use_does_not_infer_blocker_from_onsite_article_text(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Captured the on-site report article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class OnsiteBodyAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            onsite_path = Path(self.browser.downloads_path) / "onsite-report.md"
            onsite_path.write_text("# Report\n\nBody", encoding="utf-8")
            payload["route_kind"] = "onsite_report"
            payload["onsite_capture_path"] = str(onsite_path)
            payload["onsite_capture_format"] = "markdown"
            payload["onsite_page_count"] = 1
            payload["onsite_completeness_status"] = "complete"
            payload["final_page_title"] = "Global Soft Power Index"
            payload["terminal_text_excerpt"] = (
                "Among member states, innovation perceptions remain strong. "
                "See Legal Archives in the footer for historical notices."
            )

            class OnsiteBodyHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return OnsiteBodyHistory()

    runtime.Agent = OnsiteBodyAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://brandfinance.com/insights/global-soft-power-index-which-nations-lead-global-perceptions-of-innovation-in-2026",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.blocked_reason is None
    assert response.blocked_reason_detail is None

def test_download_report_with_browser_use_salvages_empty_result_via_terminal_html_fetch(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class EmptyResultAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "chrome://newtab/"
            self.browser.title = "New Tab"
            self.browser.html = ""

            class EmptyHistory:
                def final_result(self_nonlocal) -> str:
                    return ""

                def action_results(self_nonlocal) -> list[Any]:
                    return []

            return EmptyHistory()

    runtime.Agent = EmptyResultAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime,
        "fetch_html_from_url",
        lambda **kwargs: (
            "<html><head><title>Digital 2021: Bosnia and Herzegovina</title></head>"
            "<body><article><h1>Digital 2021: Bosnia and Herzegovina</h1>"
            "<p>Report overview, audience, and internet usage analysis.</p>"
            "</article></body></html>"
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://datareportal.com/reports/digital-2021-bosnia-and-herzegovina",
            settings=_settings(tmp_path),
            route_family_hint="browser_tracker_redirect",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert (
        response.final_page_url
        == "https://datareportal.com/reports/digital-2021-bosnia-and-herzegovina"
    )
    assert response.onsite_capture_path is not None
    assert Path(str(response.onsite_capture_path)).exists()

def test_download_report_with_browser_use_salvages_cached_terminal_state_when_timeout_recovery_hangs(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    settings = replace(_settings(tmp_path), timeout_seconds=0.05, max_steps=1)
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Opened the report form.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent
    original_browser = runtime.Browser

    class HangingTerminalBrowser(original_browser):
        def get_current_page(self):
            time.sleep(7.0)
            return super().get_current_page()

    class TimedOutFormAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/report#download"
            self.browser.title = "Download report"
            self.browser.html = (
                "<html><body><form>"
                "<label>Business Email</label><input name='email'>"
                "<p>Please enter a valid business email address.</p>"
                "<button>Submit</button>"
                "</form></body></html>"
            )
            time.sleep(2.0)
            return super().run_sync(max_steps)

    runtime.Browser = HangingTerminalBrowser
    runtime.Agent = TimedOutFormAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_email_domain"
    assert any(
        event.get("event") == "browser_report_download_timeout_cached_state_salvaged"
        for event in _service_events(caplog)
    )

def test_download_report_with_browser_use_salvages_terminal_state_on_timeout(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = replace(_settings(tmp_path), timeout_seconds=0.05, max_steps=1)
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and click Download.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class TimeoutSalvageAgent(original_runtime):
        def run_sync(self, max_steps: int):
            download_dir = Path(self.browser.downloads_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = download_dir / "timed-out-report.pdf"
            pdf_path.write_bytes(b"%PDF-1.7 timeout salvage")
            self.browser.downloaded_files = [str(pdf_path)]
            self.browser.url = "https://example.com/report"
            self.browser.title = "Example report"
            self.browser.html = "<html><body><h1>Example report</h1></body></html>"
            time.sleep(2.0)
            return super().run_sync(max_steps)

    runtime.Agent = TimeoutSalvageAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path.endswith("timed-out-report.pdf")

def test_download_report_with_browser_use_materializes_claimed_onsite_capture(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Navigated to the report URL and captured the on-site content.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent
    long_report_excerpt = (
        "Local RankFlux research report analysis. "
        "This report studies ranking volatility across industries. " * 30
    )

    class ClaimedOnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            claimed_path = Path(self.browser.downloads_path) / "onsite_report.md"
            payload["route_kind"] = "onsite_report"
            payload["route_family"] = "browser_tracker_redirect"
            payload["final_page_url"] = "https://example.com/research/local-rankflux"
            payload["resolved_target_url"] = (
                "https://example.com/research/local-rankflux"
            )
            payload["terminal_text_excerpt"] = long_report_excerpt
            payload["onsite_capture_path"] = str(claimed_path)
            payload["onsite_capture_format"] = "markdown"
            payload["onsite_page_count"] = 1
            payload["onsite_completeness_status"] = "complete"
            self.browser.url = "https://example.com/research/local-rankflux"
            self.browser.title = "Local RankFlux Research Report"
            self.browser.html = ""

            class ClaimedOnsiteHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return ClaimedOnsiteHistory()

    runtime.Agent = ClaimedOnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/local-rankflux",
            settings=_settings(tmp_path),
            route_family_hint="browser_tracker_redirect",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    assert (
        Path(response.onsite_capture_path)
        .read_text(encoding="utf-8")
        .startswith("Local RankFlux research report analysis.")
    )

def test_download_report_with_browser_use_fetches_terminal_html_for_missing_onsite_capture(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Opened the report page and extracted the on-site report body.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent
    report_html = (
        "<html><head><title>Consumer Search Behavior Research Report</title></head>"
        "<body><article><h1>Consumer Search Behavior Research Report</h1>"
        "<p>This research report analyzes how consumers discover local businesses.</p>"
        "<p>"
        + ("Local search behavior survey findings and analysis. " * 80)
        + "</p></article></body></html>"
    )

    class MissingCaptureAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["route_kind"] = "onsite_report"
            payload["route_family"] = "browser_onsite_report"
            payload["final_page_url"] = (
                "https://example.com/research/consumer-search-behavior/"
            )
            payload["resolved_target_url"] = payload["final_page_url"]
            payload["terminal_text_excerpt"] = "Consumer search behavior research."
            payload["onsite_capture_path"] = "extracted_content_0.md"
            payload["onsite_capture_format"] = "markdown"
            payload["onsite_page_count"] = 1
            payload["onsite_completeness_status"] = "complete"
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "extract",
                    "target_text": "Capture full on-site report content",
                    "target_role": "page",
                    "target_url": payload["final_page_url"],
                    "result": "Content extracted to extracted_content_0.md",
                }
            ]
            self.browser.url = payload["final_page_url"]
            self.browser.title = "Consumer Search Behavior Research Report"
            self.browser.html = ""

            class MissingCaptureHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return MissingCaptureHistory()

    runtime.Agent = MissingCaptureAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            content=report_html.encode("utf-8"),
            headers={"content-type": "text/html; charset=utf-8"},
            url="https://example.com/research/consumer-search-behavior/",
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/consumer-search-behavior",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    capture_path = Path(response.onsite_capture_path)
    assert capture_path.exists()
    assert capture_path.name == "consumer-search-behavior.html"
    assert "Local search behavior survey findings" in capture_path.read_text(
        encoding="utf-8"
    )

def test_download_report_with_browser_use_ignores_worker_metadata_when_materializing_onsite_extract(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Opened the report page and extracted on-site report content.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent
    extracted_report = (
        "# The Single Age\n"
        "The Single Age report explores a global multi-generational cohort. "
        "The report discusses self-expression, independence, and authenticity. "
        "This report includes original infographics, case studies, trends, "
        "and implications for brands and marketers. " * 20
    )

    class ExtractedOnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            claimed_path = Path(self.browser.downloads_path) / "The Single Age.md"
            (
                Path(self.browser.downloads_path) / "browser_agent_worker_response.json"
            ).write_text(
                "{}",
                encoding="utf-8",
            )
            payload["route_kind"] = "onsite_report"
            payload["route_family"] = "browser_pdf_click"
            payload["final_page_url"] = "https://www.vml.com/insight/the-single-age"
            payload["resolved_target_url"] = (
                "https://www.vml.com/insight/the-single-age"
            )
            payload["terminal_text_excerpt"] = "The Single Age"
            payload["onsite_capture_path"] = str(claimed_path)
            payload["onsite_capture_format"] = "md"
            payload["onsite_page_count"] = 167
            payload["onsite_completeness_status"] = "complete"
            payload["route_steps"] = [
                {
                    "index": 13,
                    "action": "extract",
                    "target_text": "Extract the full content of the report.",
                    "target_role": "page",
                    "target_url": "https://www.vml.com/insight/the-single-age",
                    "result": extracted_report,
                }
            ]
            self.browser.url = "https://www.vml.com/insight/the-single-age"
            self.browser.title = "The Single Age"
            self.browser.html = ""

            class ExtractedOnsiteHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return ExtractedOnsiteHistory()

    runtime.Agent = ExtractedOnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://www.vml.com/insight/new-trend-report-the-single-age",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    capture_path = Path(response.onsite_capture_path)
    assert capture_path.exists()
    assert capture_path.name == "The Single Age.md"
    assert "self-expression" in capture_path.read_text(encoding="utf-8")
    assert "original infographics" in capture_path.read_text(encoding="utf-8")
    assert response.downloaded_file_path is None

__all__ = [
    "test_browser_report_download_result_trusts_explicit_lookup_enum_blocker",
    "test_download_report_with_browser_use_does_not_infer_static_archive_from_please_wait",
    "test_download_report_with_browser_use_does_not_infer_blocker_from_onsite_article_text",
    "test_download_report_with_browser_use_salvages_empty_result_via_terminal_html_fetch",
    "test_download_report_with_browser_use_salvages_cached_terminal_state_when_timeout_recovery_hangs",
    "test_download_report_with_browser_use_salvages_terminal_state_on_timeout",
    "test_download_report_with_browser_use_materializes_claimed_onsite_capture",
    "test_download_report_with_browser_use_fetches_terminal_html_for_missing_onsite_capture",
    "test_download_report_with_browser_use_ignores_worker_metadata_when_materializing_onsite_extract",
]
