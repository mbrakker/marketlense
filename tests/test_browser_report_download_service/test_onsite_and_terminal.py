from __future__ import annotations

from .builders import *  # noqa: F401,F403


def test_download_report_with_browser_use_returns_email_required_when_confirmation_is_missing(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the form, enter the configured email, submit it, and wait for the confirmation message.",
        create_pdf=False,
        email_submission_completed=True,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/form-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.route_status == "inferred"


def test_download_report_with_browser_use_short_circuits_remembered_onsite_extract_to_direct_html_capture(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        url = "https://example.com/research/report"
        text = (
            "<html><head><title>Example Report</title></head>"
            "<body><article><h1>Example Report</h1>"
            "<p>Market research findings.</p>"
            "<p>" + ("Long body text. " * 120) + "</p>"
            "</article></body></html>"
        )

    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError(
                "browser runtime should not start for remembered onsite HTML capture"
            )
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/report",
            settings=_settings(tmp_path),
            route_hint="Accept cookies and extract the report body.",
            route_step_hints=[
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=0,
                    action="click",
                    target_text="Allow all",
                    target_role="button",
                    target_url="https://example.com/research/report",
                    result="Accepted cookies",
                ),
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=1,
                    action="extract",
                    target_text="report article",
                    target_role="extract",
                    target_url="https://example.com/research/report",
                    result="Captured the on-site report body",
                ),
            ],
            route_kind_hint="onsite_report",
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.browser_had_structured_result is False
    assert response.onsite_capture_path is not None
    capture_path = Path(str(response.onsite_capture_path))
    assert capture_path.exists()
    assert "Long body text." in capture_path.read_text(encoding="utf-8")
    service_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == service.logger.name
    ]
    assert any(
        event.get("event") == "browser_report_download_direct_onsite_attempt_complete"
        for event in service_events
    )


def test_download_report_with_browser_use_short_circuits_planned_onsite_candidate_to_direct_html_capture(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        url = "https://example.com/commerce-content/report-guide"
        text = (
            "<html><head><title>High Performance Content Operations Guide</title></head>"
            "<body><article><h1>High Performance Content Operations Guide</h1>"
            "<p>Content operations workflow research and benchmark findings.</p>"
            "<p>" + ("Operational insight. " * 140) + "</p>"
            "</article></body></html>"
        )

    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError(
                "browser runtime should not start for planned onsite HTML capture"
            )
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/commerce-content/report-guide",
            settings=_settings(tmp_path),
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://example.com/commerce-content/report-guide",
                title="High Performance Content Operations Guide",
                discovered_on_page_number=18,
                source_page_urls=["https://example.com/search?ft%5B0%5D=report&pg=18"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            route_kind_hint="onsite_report",
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.browser_had_structured_result is False
    assert response.used_candidate_source_page is False
    assert response.onsite_capture_path is not None
    capture_path = Path(str(response.onsite_capture_path))
    assert capture_path.exists()
    assert "Operational insight." in capture_path.read_text(encoding="utf-8")
    service_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == service.logger.name
    ]
    assert any(
        event.get("event") == "browser_report_download_direct_onsite_attempt_complete"
        for event in service_events
    )


def test_download_report_with_browser_use_short_circuits_planned_extract_step_without_candidate_trace(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        url = "https://data.example/reports/digital-2023-norfolk-island"
        text = (
            "<html><head><title>Digital 2023: Norfolk Island</title></head>"
            "<body><article><h1>Digital 2023: Norfolk Island</h1>"
            "<p>This page contains the complete report findings.</p>"
            "<p>" + ("Population and connectivity insight. " * 160) + "</p>"
            "</article></body></html>"
        )

    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("browser runtime should not start for planned extract step")
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://data.example/reports/digital-2023-norfolk-island",
            settings=_settings(tmp_path),
            route_kind_hint="onsite_report",
            route_family_hint="browser_onsite_report",
            route_step_hints=[
                BrowserDownloadRouteStep(
                    schema_version="1.0",
                    index=0,
                    action="extract",
                    target_text="https://data.example/reports/digital-2023-norfolk-island",
                    target_role="html",
                    target_url="https://data.example/reports/digital-2023-norfolk-island",
                    result="Capture the on-site report HTML.",
                )
            ],
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.route_family == "browser_onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    assert "Population and connectivity insight." in Path(
        response.onsite_capture_path
    ).read_text(encoding="utf-8")


def test_download_report_with_browser_use_directly_captures_route_confirmed_non_article_longread(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        url = "https://example.com/guides/personalization/"
        text = (
            "<html><head><title>What is Personalization and How to Get Started</title></head>"
            "<body><main><h1>Personalization Guide</h1>"
            "<section><p>This guide explains research-backed personalization practices.</p>"
            "<p>" + ("Customer insight and implementation detail. " * 140) + "</p>"
            "</section></main></body></html>"
        )

    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError(
                "browser runtime should not start for route-confirmed longread"
            )
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/guides/personalization",
            settings=_settings(tmp_path),
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://example.com/guides/personalization",
                title="What is Personalization and How to Get Started?",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/guides"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.82,
            ),
            route_kind_hint="onsite_report",
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.browser_had_structured_result is False
    assert response.onsite_capture_path is not None
    assert (
        Path(response.onsite_capture_path)
        .read_text(encoding="utf-8")
        .startswith("<html>")
    )


def test_download_report_with_browser_use_probes_report_detail_candidate_for_direct_onsite_capture(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        url = "https://data.example/reports/digital-2022-example"
        text = (
            "<html><head><title>Digital 2022 Example</title>"
            "<script>window.grecaptcha = { execute: function() {} };</script>"
            "</head><body><article><h1>Digital 2022 Example</h1>"
            "<p>This page contains the complete report findings.</p>"
            "<p>" + ("Market adoption insight. " * 160) + "</p>"
            "</article></body></html>"
        )

    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError(
                "browser runtime should not start for direct article capture"
            )
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://data.example/reports/digital-2022-example",
            settings=_settings(tmp_path),
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://data.example/reports/digital-2022-example",
                title="Digital 2022 Example Report",
                discovered_on_page_number=53,
                source_page_urls=["https://data.example/reports?offset=123"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            route_kind_hint=None,
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.route_family == "browser_onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    capture_path = Path(str(response.onsite_capture_path))
    assert capture_path.exists()
    assert "Market adoption insight." in capture_path.read_text(encoding="utf-8")


def test_download_report_with_browser_use_blocks_mixed_hub_direct_onsite_recovery(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the candidate and click the visible PDF download.",
        create_pdf=True,
        email_submission_completed=False,
    )

    class FakeHtmlResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        url = "https://data.example/reports"
        text = "<html><head><title>Reports</title></head><body>Reports</body></html>"

    http_calls: list[str] = []

    def _http_get(url, **kwargs):
        http_calls.append(str(url))
        return FakeHtmlResponse()

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", _http_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://data.example/reports",
            settings=_settings(tmp_path),
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://data.example/reports",
                title="Reports and insights",
                discovered_on_page_number=1,
                source_page_urls=["https://data.example/reports"],
                discovery_provenances=["browser_dom"],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.95,
            ),
            route_kind_hint=None,
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert http_calls == ["https://data.example/reports"]
    decision_events = [
        event
        for event in _service_events(caplog)
        if event.get("event")
        == "browser_report_download_direct_onsite_recovery_decision"
    ]
    assert decision_events
    assert decision_events[-1]["fields"]["recovery_class"] == (
        "mixed_content_hub_http_capture"
    )
    assert decision_events[-1]["fields"]["recovery_decision"] == "blocked"


def test_download_report_with_browser_use_prefers_form_evidence_over_onsite_hint(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary=(
            "Accepted cookies, filled form fields, and clicked submit on the gated page."
        ),
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class OnsiteHintEmailAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/research/report"
            self.browser.title = "Request the report"
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["route_kind"] = "onsite_report"
            payload["encountered_form_fields"] = ["Company", "Work email"]
            payload["submit_button_state"] = "disabled"
            payload["post_submit_message"] = "Please use a business email address."
            payload["blocked_reason"] = "blocked_email_domain"

            class OnsiteHintEmailHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return OnsiteHintEmailHistory()

    runtime.Agent = OnsiteHintEmailAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_email_domain"


def test_download_report_with_browser_use_keeps_explicit_onsite_classification_when_optional_form_fields_were_seen(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Accepted cookies, opened the optional form, and captured the article content.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class ExplicitOnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/research/report"
            self.browser.title = "Research report"
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["route_kind"] = "onsite_report"
            payload["route_family"] = "browser_onsite_report"
            payload["encountered_form_fields"] = ["Company", "Work email"]
            payload["post_submit_message"] = ""
            payload["terminal_text_excerpt"] = (
                "Research report executive summary and methodology."
            )
            payload["onsite_capture_path"] = str(
                tmp_path / "downloads" / "captured-report.md"
            )
            payload["onsite_capture_format"] = "md"
            payload["onsite_completeness_status"] = "complete"

            class ExplicitOnsiteHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return ExplicitOnsiteHistory()

    runtime.Agent = ExplicitOnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.route_status == "verified"


def test_download_report_with_browser_use_salvages_empty_result_to_onsite_capture(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the longread report page and capture the article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class EmptyOnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/research/market-outlook-2026"
            self.browser.title = "Market Outlook 2026 report"
            self.browser.html = (
                "<html><body><article><h1>Market Outlook 2026 report</h1>"
                "<h2>Executive summary</h2><p>" + ("Longread body. " * 300) + "</p>"
                "<h2>Methodology</h2><p>" + ("More body. " * 120) + "</p>"
                "</article></body></html>"
            )

            class EmptyHistory:
                def final_result(self_nonlocal) -> str:
                    return ""

            return EmptyHistory()

    runtime.Agent = EmptyOnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/market-outlook-2026",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    assert Path(str(response.onsite_capture_path)).exists()


def test_download_report_with_browser_use_records_terminal_snapshot_and_document_urls(
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

    class EvidenceRichAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.network_resource_urls = [
                "https://cdn.example.com/reports/final-report.pdf",
                "https://cdn.example.com/reports/final-report.pdf",
            ]
            self.browser.html = (
                "<html><head><meta property='og:url' content='https://cdn.example.com/reports/final-report.pdf' /></head>"
                "<body><h1>Example report terminal</h1></body></html>"
            )
            return super().run_sync(max_steps)

    runtime.Agent = EvidenceRichAgent
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

    assert response.terminal_evidence.html_snapshot_path
    assert Path(response.terminal_evidence.html_snapshot_path).exists()
    assert response.terminal_evidence.screenshot_path
    assert Path(response.terminal_evidence.screenshot_path).exists()
    assert (
        "https://cdn.example.com/reports/final-report.pdf"
        in response.terminal_evidence.observed_document_urls
    )
    assert response.terminal_evidence.network_events
    assert (
        response.terminal_evidence.network_events[0].signal_kind == "document_request"
    )
    assert response.terminal_evidence.visited_url_timeline


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


def test_download_report_with_browser_use_infers_bounded_incomplete_for_weak_onsite_capture(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report page and capture the article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class WeakOnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/research/report-2026"
            self.browser.title = "Research report 2026"
            self.browser.html = (
                "<html><body><article><h1>Research report 2026</h1>"
                "<p>Short introduction only.</p></article></body></html>"
            )
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["route_kind"] = "onsite_report"
            payload["onsite_capture_path"] = str(
                Path(self.browser.downloads_path) / "onsite-report.html"
            )
            Path(payload["onsite_capture_path"]).write_text(
                self.browser.html,
                encoding="utf-8",
            )
            payload["onsite_capture_format"] = "html"
            payload["onsite_page_count"] = 1
            payload["onsite_completeness_status"] = ""
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "navigate",
                    "target_text": "report",
                    "target_role": "page",
                    "target_url": "https://example.com/research/report-2026",
                    "result": "opened",
                }
            ]
            payload["traversed_page_urls"] = [
                "https://example.com/research/report-2026"
            ]

            class WeakOnsiteHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return WeakOnsiteHistory()

    runtime.Agent = WeakOnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/report-2026",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_completeness_status == "bounded_incomplete"
    assert response.route_status == "inferred"


def test_download_report_with_browser_use_auto_captures_onsite_html_when_agent_omits_capture_path(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report page and capture the article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class MissingCaptureAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/research/report-2026"
            self.browser.title = "Research report 2026"
            self.browser.html = (
                "<html><body><article><h1>Research report 2026</h1>"
                "<h2>Executive summary</h2><p>" + ("Longread body. " * 180) + "</p>"
                "<h2>Methodology</h2><p>" + ("More report detail. " * 120) + "</p>"
                "</article></body></html>"
            )
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["route_kind"] = "onsite_report"
            payload["onsite_capture_path"] = None
            payload["onsite_capture_format"] = None
            payload["onsite_page_count"] = None
            payload["onsite_completeness_status"] = ""
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/research/report-2026",
                    "result": "Scrolled down 950px",
                },
                {
                    "index": 1,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/research/report-2026",
                    "result": "Scrolled down 950px",
                },
                {
                    "index": 2,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/research/report-2026",
                    "result": "Scrolled down 950px",
                },
            ]
            payload["traversed_page_urls"] = [
                "https://example.com/research/report-2026"
            ]

            class MissingCaptureHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return MissingCaptureHistory()

    runtime.Agent = MissingCaptureAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/report-2026",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    assert Path(str(response.onsite_capture_path)).exists()
    assert response.onsite_capture_format == "html"


def test_download_report_with_browser_use_prints_printable_onsite_report_to_pdf(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    import base64

    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the printable report page, inspect the article, and capture the on-site report content.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_browser = runtime.Browser
    original_agent = runtime.Agent
    cdp_calls: list[dict[str, object]] = []

    class PrintPdfCdpClient:
        async def send_raw(
            self,
            method: str,
            params: dict[str, object] | None = None,
            session_id: str | None = None,
        ) -> dict[str, object]:
            cdp_calls.append(
                {
                    "method": method,
                    "params": params or {},
                    "session_id": session_id or "",
                }
            )
            if method == "Target.getTargets":
                return {
                    "targetInfos": [
                        {
                            "targetId": "printable-target",
                            "type": "page",
                            "url": "https://example.com/research/printable-report",
                        }
                    ]
                }
            if method == "Target.attachToTarget":
                return {"sessionId": "printable-session"}
            if method == "Page.printToPDF":
                return {
                    "data": base64.b64encode(
                        b"%PDF-1.7 browser-rendered onsite report"
                    ).decode("ascii")
                }
            if method == "Target.detachFromTarget":
                return {}
            raise RuntimeError(method)

    class PrintableBrowser(original_browser):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cdp_client = PrintPdfCdpClient()

    class PrintableOnsiteAgent(original_agent):
        def run_sync(self, max_steps: int):
            payload = json.loads(super().run_sync(max_steps).final_result())
            self.browser.url = "https://example.com/research/printable-report"
            self.browser.title = "Printable research report 2026"
            self.browser.html = (
                "<html><head><title>Printable research report 2026</title>"
                "<style>@media print { article { color: black; } }</style></head>"
                "<body><article><h1>Printable research report 2026</h1>"
                "<button>Print this report</button>"
                "<h2>Executive summary</h2><p>"
                + ("Market analysis report detail. " * 120)
                + "</p><h2>Methodology</h2><p>"
                + ("Survey insight and research evidence. " * 90)
                + "</p></article></body></html>"
            )
            payload["route_kind"] = "onsite_report"
            payload["route_family"] = "browser_onsite_report"
            payload["final_page_url"] = self.browser.url
            payload["final_page_title"] = self.browser.title
            payload["terminal_text_excerpt"] = "Printable research report 2026"
            payload["onsite_capture_path"] = None
            payload["onsite_capture_format"] = None
            payload["onsite_page_count"] = 1
            payload["onsite_completeness_status"] = "complete"
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "capture",
                    "target_text": "printable report page",
                    "target_role": "article",
                    "target_url": self.browser.url,
                    "result": "Captured the longread report content.",
                }
            ]

            class PrintableHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return PrintableHistory()

    runtime.Browser = PrintableBrowser
    runtime.Agent = PrintableOnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/printable-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.downloaded_file_path is None
    assert response.onsite_capture_format == "browser_rendered_pdf"
    assert response.onsite_capture_path is not None
    assert Path(response.onsite_capture_path).read_bytes().startswith(b"%PDF")
    assert "browser_rendered_pdf_capture" in response.terminal_evidence.evidence_labels
    assert (
        "not a publisher-supplied PDF"
        in response.terminal_evidence.artifact_validation_detail
    )
    assert "Page.printToPDF" in [str(call["method"]) for call in cdp_calls]


def test_download_report_with_browser_use_rejects_print_pdf_for_generic_printable_page(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    import base64

    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the printable page and inspect the content.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_browser = runtime.Browser
    original_agent = runtime.Agent
    cdp_calls: list[str] = []

    class PrintPdfCdpClient:
        async def send_raw(
            self,
            method: str,
            params: dict[str, object] | None = None,
            session_id: str | None = None,
        ) -> dict[str, object]:
            cdp_calls.append(method)
            if method == "Page.printToPDF":
                return {"data": base64.b64encode(b"%PDF-1.7 generic").decode("ascii")}
            return {
                "targetInfos": [
                    {
                        "targetId": "generic-target",
                        "type": "page",
                        "url": "https://example.com/company/print",
                    }
                ],
                "sessionId": "generic-session",
            }

    class GenericPrintableBrowser(original_browser):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cdp_client = PrintPdfCdpClient()

    class GenericPrintableAgent(original_agent):
        def run_sync(self, max_steps: int):
            payload = json.loads(super().run_sync(max_steps).final_result())
            self.browser.url = "https://example.com/company/print"
            self.browser.title = "Company overview"
            self.browser.html = (
                "<html><head><style>@media print { body { color: black; } }</style>"
                "</head><body><main><h1>Company overview</h1><button>Print</button>"
                "<p>"
                + ("Product platform and services detail. " * 120)
                + "</p></main></body></html>"
            )
            payload["route_kind"] = "onsite_report"
            payload["route_family"] = "browser_onsite_report"
            payload["final_page_url"] = self.browser.url
            payload["final_page_title"] = self.browser.title
            payload["onsite_capture_path"] = None
            payload["onsite_capture_format"] = None
            payload["onsite_page_count"] = 1
            payload["onsite_completeness_status"] = "bounded_incomplete"
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "capture",
                    "target_text": "company overview page",
                    "target_role": "page",
                    "target_url": self.browser.url,
                    "result": "Captured page content.",
                }
            ]

            class GenericHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return GenericHistory()

    runtime.Browser = GenericPrintableBrowser
    runtime.Agent = GenericPrintableAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/company/print",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_format == "html"
    assert "Page.printToPDF" not in cdp_calls


def test_download_report_with_browser_use_records_terminal_dialog_evidence(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report page and capture the on-site article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_browser = runtime.Browser
    original_agent = runtime.Agent
    cdp_calls: list[dict[str, object]] = []

    class DialogRegistry:
        def __init__(self) -> None:
            self.handlers: dict[str, object] = {}

        def unregister(self, method: str) -> None:
            self.handlers.pop(method, None)

    class DialogPageRegister:
        def __init__(self, registry: DialogRegistry) -> None:
            self.registry = registry

        def javascriptDialogOpening(self, callback: object) -> None:
            self.registry.handlers["Page.javascriptDialogOpening"] = callback

    class DialogCdpClient:
        def __init__(self) -> None:
            self._event_registry = DialogRegistry()
            self.register = SimpleNamespace(
                Page=DialogPageRegister(self._event_registry)
            )
            self.dialog_events = [
                {
                    "url": "https://example.com/research/dialog-report",
                    "type": "alert",
                    "message": "Report capture is ready.",
                }
            ]
            self.active_dialog = False

        async def send_raw(
            self,
            method: str,
            params: dict[str, object] | None = None,
            session_id: str | None = None,
        ) -> dict[str, object]:
            cdp_calls.append(
                {
                    "method": method,
                    "params": params or {},
                    "session_id": session_id or "",
                }
            )
            if method == "Page.enable":
                events = list(self.dialog_events)
                self.dialog_events.clear()
                for event in events:
                    handler = self._event_registry.handlers.get(
                        "Page.javascriptDialogOpening"
                    )
                    if callable(handler):
                        self.active_dialog = True
                        result = handler(event, session_id)
                        if hasattr(result, "__await__"):
                            await result
                return {}
            if method == "Page.handleJavaScriptDialog":
                if not self.active_dialog:
                    raise RuntimeError("No dialog is showing")
                self.active_dialog = False
                return {}
            if method == "Runtime.evaluate":
                return {"result": {"type": "object", "value": []}}
            raise RuntimeError(method)

    class DialogSession:
        def __init__(self, client: DialogCdpClient) -> None:
            self.cdp_client = client
            self.target_id = "dialog-target"
            self.session_id = "dialog-session"

    class DialogBrowser(original_browser):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.cdp_client = DialogCdpClient()
            self._dialog_session = DialogSession(self.cdp_client)

        async def get_or_create_cdp_session(
            self,
            target_id: str | None = None,
            focus: bool = False,
        ) -> DialogSession:
            return self._dialog_session

    class DialogAgent(original_agent):
        def run_sync(self, max_steps: int):
            payload = json.loads(super().run_sync(max_steps).final_result())
            self.browser.url = "https://example.com/research/dialog-report"
            self.browser.title = "Dialog report"
            self.browser.html = (
                "<html><body><article><h1>Dialog report</h1><p>"
                + ("Market analysis report detail. " * 80)
                + "</p></article></body></html>"
            )
            payload["route_kind"] = "onsite_report"
            payload["route_family"] = "browser_onsite_report"
            payload["final_page_url"] = self.browser.url
            payload["final_page_title"] = self.browser.title
            payload["terminal_text_excerpt"] = "Dialog report"
            payload["onsite_capture_path"] = None
            payload["onsite_capture_format"] = None

            class DialogHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

                def action_results(self_nonlocal) -> list[object]:
                    return []

            return DialogHistory()

    runtime.Browser = DialogBrowser
    runtime.Agent = DialogAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/dialog-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.terminal_evidence.dialog_evidence
    assert response.terminal_evidence.dialog_evidence[0].dialog_type == "alert"
    assert response.terminal_evidence.dialog_evidence[0].message == (
        "Report capture is ready."
    )
    assert response.terminal_evidence.dialog_evidence[0].action_taken == "accepted"
    assert "javascript_dialog" in response.terminal_evidence.evidence_labels
    assert "dialog_handled" in response.terminal_evidence.evidence_labels
    assert {
        "method": "Page.handleJavaScriptDialog",
        "params": {"accept": True},
        "session_id": "dialog-session",
    } in cdp_calls


def test_download_report_with_browser_use_marks_paginated_onsite_capture_partial_without_full_traversal(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report pages and capture the article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class PartialPaginationAgent(original_runtime):
        def run_sync(self, max_steps: int):
            combined_html = (
                "<html><body><article><h1>Global industry report</h1>"
                "<h2>Executive summary</h2><p>" + ("Page one content. " * 140) + "</p>"
                "<h2>Market outlook</h2><p>" + ("Page two content. " * 140) + "</p>"
                "</article></body></html>"
            )
            payload = json.loads(super().run_sync(max_steps).final_result())
            self.browser.url = "https://example.com/report?page=2"
            self.browser.title = "Global industry report"
            self.browser.html = combined_html
            payload["route_kind"] = "onsite_report"
            payload["final_page_url"] = "https://example.com/report?page=2"
            payload["onsite_capture_path"] = str(
                Path(self.browser.downloads_path) / "onsite-report.html"
            )
            Path(payload["onsite_capture_path"]).write_text(
                combined_html,
                encoding="utf-8",
            )
            payload["onsite_capture_format"] = "html"
            payload["onsite_page_count"] = 3
            payload["onsite_completeness_status"] = ""
            payload["traversed_page_urls"] = [
                "https://example.com/report?page=1",
                "https://example.com/report?page=2",
            ]
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "navigate",
                    "target_text": "Page 1",
                    "target_role": "page",
                    "target_url": "https://example.com/report?page=1",
                    "result": "opened",
                },
                {
                    "index": 1,
                    "action": "click",
                    "target_text": "Next page",
                    "target_role": "button",
                    "target_url": "https://example.com/report?page=2",
                    "result": "Opened page 2",
                },
            ]

            class PartialPaginationHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return PartialPaginationHistory()

    runtime.Agent = PartialPaginationAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report?page=1",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_completeness_status == "partial"
    assert response.route_status == "inferred"


def test_download_report_with_browser_use_marks_paginated_onsite_capture_complete_after_final_page(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report pages and capture the article.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class CompletePaginationAgent(original_runtime):
        def run_sync(self, max_steps: int):
            combined_html = (
                "<html><body><article><h1>Global industry report</h1>"
                "<h2>Executive summary</h2><p>" + ("Page one content. " * 140) + "</p>"
                "<h2>Market outlook</h2><p>" + ("Page two content. " * 140) + "</p>"
                "<h2>Recommendations</h2><p>" + ("Page three content. " * 140) + "</p>"
                "</article></body></html>"
            )
            payload = json.loads(super().run_sync(max_steps).final_result())
            self.browser.url = "https://example.com/report?page=3"
            self.browser.title = "Global industry report"
            self.browser.html = combined_html
            payload["route_kind"] = "onsite_report"
            payload["final_page_url"] = "https://example.com/report?page=3"
            payload["onsite_capture_path"] = str(
                Path(self.browser.downloads_path) / "onsite-report.html"
            )
            Path(payload["onsite_capture_path"]).write_text(
                combined_html,
                encoding="utf-8",
            )
            payload["onsite_capture_format"] = "html"
            payload["onsite_page_count"] = 3
            payload["onsite_completeness_status"] = ""
            payload["traversed_page_urls"] = [
                "https://example.com/report?page=1",
                "https://example.com/report?page=2",
                "https://example.com/report?page=3",
            ]
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "navigate",
                    "target_text": "Page 1",
                    "target_role": "page",
                    "target_url": "https://example.com/report?page=1",
                    "result": "opened",
                },
                {
                    "index": 1,
                    "action": "click",
                    "target_text": "Next page",
                    "target_role": "button",
                    "target_url": "https://example.com/report?page=2",
                    "result": "Opened page 2",
                },
                {
                    "index": 2,
                    "action": "click",
                    "target_text": "Next page",
                    "target_role": "button",
                    "target_url": "https://example.com/report?page=3",
                    "result": "Reached page 3 of 3",
                },
            ]

            class CompletePaginationHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return CompletePaginationHistory()

    runtime.Agent = CompletePaginationAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report?page=1",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_completeness_status == "complete"
    assert response.route_status == "verified"


def test_download_report_with_browser_use_prefers_onsite_capture_over_optional_form_submission(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the optional form on the longread page and clicked submit.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class OnsiteLongreadAgent(original_runtime):
        def run_sync(self, max_steps: int):
            longread_html = (
                "<html><body><article>"
                "<h1>Global innovation outlook report</h1>"
                "<h2>Executive summary</h2>"
                "<p>" + ("Report analysis section. " * 120) + "</p>"
                "<h2>Methodology</h2>"
                "<p>" + ("Detailed report findings. " * 120) + "</p>"
                "</article></body></html>"
            )

            class AsyncPage:
                url = "https://example.com/insights/global-innovation-outlook"

                async def title(self_nonlocal):
                    return "Global innovation outlook report"

                async def content(self_nonlocal):
                    return longread_html

                async def evaluate(self_nonlocal, script):
                    if "getEntriesByType" in script:
                        return [
                            "https://example.com/insights/global-innovation-outlook",
                        ]
                    return longread_html

            async def get_current_page():
                return AsyncPage()

            history = super().run_sync(max_steps)
            self.browser.url = "https://example.com/insights/global-innovation-outlook"
            self.browser.title = ""
            self.browser.html = ""
            self.browser.get_current_page = get_current_page
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["route_family"] = "browser_onsite_report"
            payload["final_page_url"] = (
                "https://example.com/insights/global-innovation-outlook"
            )
            payload["final_page_title"] = "Global innovation outlook report"
            payload["encountered_form_fields"] = ["Full name", "Work email"]
            payload["post_submit_message"] = "Thank you for submitting the form."
            payload["traversed_page_urls"] = [
                "https://example.com/insights/global-innovation-outlook"
            ]
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Scrolled down 950px",
                },
                {
                    "index": 1,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Scrolled down 950px",
                },
                {
                    "index": 2,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Scrolled down 950px",
                },
                {
                    "index": 3,
                    "action": "click",
                    "target_text": "Submit",
                    "target_role": "button",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": 'Clicked button "Submit"',
                },
            ]

            class OnsiteHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return OnsiteHistory()

    runtime.Agent = OnsiteLongreadAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/insights/global-innovation-outlook",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.onsite_capture_path is not None
    assert Path(str(response.onsite_capture_path)).exists()
    assert response.terminal_evidence.html_snapshot_path
    assert response.terminal_evidence.dom_snapshot_sha256


def test_download_report_with_browser_use_fetches_onsite_html_when_browser_html_is_missing(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Scrolled through the article and submitted the optional form.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class HtmlMissingOnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            self.browser.url = "https://example.com/insights/global-innovation-outlook"
            self.browser.title = ""
            self.browser.html = ""
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["route_family"] = "browser_onsite_report"
            payload["final_page_url"] = (
                "https://example.com/insights/global-innovation-outlook"
            )
            payload["final_page_title"] = "Global innovation outlook report"
            payload["post_submit_message"] = "Thank you for submitting the form."
            payload["encountered_form_fields"] = ["Full name", "Work email"]
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Scrolled down 900px",
                },
                {
                    "index": 1,
                    "action": "scroll",
                    "target_text": "",
                    "target_role": "page",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Scrolled down 900px",
                },
                {
                    "index": 2,
                    "action": "click",
                    "target_text": "Submit",
                    "target_role": "button",
                    "target_url": "https://example.com/insights/global-innovation-outlook",
                    "result": "Clicked button",
                },
            ]

            class HtmlMissingOnsiteHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return HtmlMissingOnsiteHistory()

    runtime.Agent = HtmlMissingOnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime,
        "fetch_html_from_url",
        lambda **kwargs: (
            "<html><body><article><h1>Global innovation outlook report</h1>"
            "<h2>Executive summary</h2><p>" + ("Report section. " * 120) + "</p>"
            "<h2>Methodology</h2><p>" + ("More report content. " * 120) + "</p>"
            "</article></body></html>"
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/insights/global-innovation-outlook",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.blocked_reason is None
    assert response.onsite_capture_path is not None


def test_download_report_with_browser_use_fetches_terminal_html_for_email_delivery_when_browser_html_is_missing(
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

    class HtmlMissingEmailAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            self.browser.url = "https://example.com/report/thank-you"
            self.browser.title = ""
            self.browser.html = ""
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["final_page_url"] = "https://example.com/report/thank-you"
            payload["resolved_target_url"] = "https://example.com/report/thank-you"
            payload["final_page_title"] = ""
            payload["post_submit_message"] = (
                "Thank you. A copy of the report will be sent to your inbox shortly."
            )
            payload["terminal_text_excerpt"] = ""
            payload["encountered_form_fields"] = ["Business Email", "Country"]

            class HtmlMissingEmailHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return HtmlMissingEmailHistory()

    runtime.Agent = HtmlMissingEmailAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime,
        "fetch_html_from_url",
        lambda **kwargs: (
            "<html><head><title>Thank you for downloading the report</title></head>"
            "<body><main><h1>Thank you</h1>"
            "<p>A copy of the report will be sent to your inbox shortly.</p>"
            "</main></body></html>"
        ),
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
    assert response.terminal_evidence.html_snapshot_path
    assert Path(response.terminal_evidence.html_snapshot_path).exists()
    assert response.terminal_evidence.dom_snapshot_sha256
    assert response.final_page_url == "https://example.com/report/thank-you"
    assert (
        response.terminal_evidence.final_page_title
        == "Thank you for downloading the report"
    )


def test_download_report_with_browser_use_infers_form_disappeared_from_fetched_terminal_html(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form and clicked submit.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class SparseTerminalAgent(original_runtime):
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
            payload["post_submit_message"] = ""
            payload["submit_button_state"] = ""
            payload["form_disappeared"] = None
            payload["confirmation_url_changed"] = None
            payload["final_page_title"] = ""
            payload["terminal_text_excerpt"] = ""

            class SparseTerminalHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return SparseTerminalHistory()

    runtime.Agent = SparseTerminalAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime,
        "fetch_html_from_url",
        lambda **kwargs: (
            "<html><body><h1>Thanks</h1>"
            "<p>A copy of the report will be sent directly to your inbox shortly.</p>"
            "</body></html>"
        ),
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
    assert response.outcome == "email_requested"
    assert response.confirmation_evidence.form_disappeared is True
    assert response.confirmation_evidence.confirmation_score >= 2
    assert "form_disappeared" in response.confirmation_evidence.signal_labels


def test_download_report_with_browser_use_prefers_delivery_confirmation_over_conflicting_blocker(
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

    class ConflictingBlockerAgent(original_runtime):
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
            payload["post_submit_message"] = (
                "A copy of the report will be sent directly to your inbox shortly."
            )
            payload["submit_button_state"] = "disabled"
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = "Online Annual Revenue is required."

            class ConflictingBlockerHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return ConflictingBlockerHistory()

    runtime.Agent = ConflictingBlockerAgent
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
    assert response.outcome == "email_requested"
    assert response.blocked_reason is None
    assert response.blocked_reason_detail is None
    assert response.confirmation_evidence.confirmation_score >= 2


def test_download_report_with_browser_use_clears_conflicting_blocker_after_verified_pdf(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Clicked the download CTA and saved the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class ConflictingPdfBlockerAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = "Industry selection is required."

            class ConflictingPdfBlockerHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

                def action_results(self_nonlocal) -> list[Any]:
                    return history.action_results()

            return ConflictingPdfBlockerHistory()

    runtime.Agent = ConflictingPdfBlockerAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://impact.com/partnerships/5-dos-and-dont-for-influencer-recruiting",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.blocked_reason is None
    assert response.blocked_reason_detail is None
    assert response.downloaded_file_path is not None


def test_download_report_with_browser_use_normalizes_text_field_blocker_to_missing_identity(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Opened the report page, attempted the form, and stopped at the blocker.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class TextFieldBlockerAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["route_kind"] = "pdf_download"
            payload["route_family"] = "browser_pdf_click"
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Business Email",
                "Company Name",
                "Phone",
                "Company Website",
            ]
            payload["post_submit_message"] = (
                "Form submission failed because the company website field is required."
            )
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = (
                "Company Website is required before submission."
            )
            payload["terminal_text_excerpt"] = (
                "Fill out the form below to have your copy sent directly to your inbox."
            )

            class TextFieldBlockerHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return TextFieldBlockerHistory()

    runtime.Agent = TextFieldBlockerAgent
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
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.route_family == "browser_email_form"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_missing_identity_field"
    assert "Company Website is required" in str(response.blocked_reason_detail)


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


def test_download_report_with_browser_use_lookup_submission_assist_upgrades_email_requested(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the report page, complete the form, and submit it.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class LookupAssistAgent(original_runtime):
        def run_sync(self, max_steps: int):
            browser = self.browser
            browser.url = "https://example.com/report#download"
            browser.title = "Example report"
            browser.html = ""

            class LookupAssistPage:
                def evaluate(self, script):
                    script_text = str(script or "")
                    if (
                        "selected_count" in script_text
                        and ".lookupFormFieldBlock" in script_text
                    ):
                        browser.url = "https://example.com/report#success"
                        browser.title = "Thank you"
                        browser.html = (
                            "<html><body>"
                            "Thank you for your interest. You will be emailed a "
                            "downloadable copy of this insight shortly."
                            "</body></html>"
                        )
                        return {
                            "acted": True,
                            "selected_count": 1,
                            "submitted": True,
                            "final_url": browser.url,
                        }
                    if "navigationEntries" in script_text:
                        return []
                    if "document.querySelectorAll" in script_text:
                        return []
                    return []

            browser.current_page_factory = LookupAssistPage
            payload = {
                "route_kind": "email_delivery",
                "route_summary": (
                    "Opened the form, filled the required fields, and clicked submit."
                ),
                "route_family": "browser_email_form",
                "resolved_target_url": "https://example.com/report#download",
                "final_page_url": "https://example.com/report#download",
                "email_submission_completed": True,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": [
                    "First Name",
                    "Last Name",
                    "Business Email Address",
                    "Business Phone",
                    "Company Name",
                    "Role",
                    "Department",
                    "Industry",
                    "Location",
                ],
                "route_steps": [],
                "post_submit_message": None,
                "confirmation_url_changed": False,
                "submit_button_state": None,
                "form_disappeared": False,
                "blocked_reason": None,
                "blocked_reason_detail": None,
                "final_page_title": "Example report",
                "terminal_text_excerpt": None,
                "traversed_page_urls": [
                    "https://example.com/report",
                    "https://example.com/report#download",
                ],
                "onsite_capture_path": None,
                "onsite_capture_format": None,
                "onsite_page_count": None,
                "onsite_completeness_status": None,
            }

            class LookupAssistHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return LookupAssistHistory()

    runtime.Agent = LookupAssistAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime.time,
        "sleep",
        lambda seconds: (_ for _ in ()).throw(
            AssertionError(f"unexpected blind sleep: {seconds}")
        ),
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
    assert response.route_status == "verified"
    assert response.final_page_url == "https://example.com/report#success"
    assert response.confirmation_evidence is not None
    assert response.confirmation_evidence.visible_confirmation_text.startswith(
        "Thank you for your interest."
    )
    terminal_events = [
        event
        for event in _service_events(caplog)
        if event.get("event") == "browser_report_download_terminal_state_assessed"
    ]
    assert any(
        event["fields"]["trigger_reason"] == "lookup_submission_assist"
        and event["fields"]["quorum_met"] is True
        and "success_text" in event["fields"]["quorum_signal_labels"]
        for event in terminal_events
    )
