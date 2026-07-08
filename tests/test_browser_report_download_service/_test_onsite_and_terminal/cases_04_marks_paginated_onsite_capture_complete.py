# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

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

    def _fetch_html_from_url(**kwargs):
        assert kwargs["timeout_seconds"] == 15.0
        return (
            "<html><body><article><h1>Global innovation outlook report</h1>"
            "<h2>Executive summary</h2><p>" + ("Report section. " * 120) + "</p>"
            "<h2>Methodology</h2><p>" + ("More report content. " * 120) + "</p>"
            "</article></body></html>"
        )

    external_boundary_mocks_only.setattr(
        http_runtime,
        "fetch_html_from_url",
        _fetch_html_from_url,
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

    def _fetch_email_terminal_html(**kwargs):
        assert kwargs["timeout_seconds"] == 15.0
        return (
            "<html><head><title>Thank you for downloading the report</title></head>"
            "<body><main><h1>Thank you</h1>"
            "<p>A copy of the report will be sent to your inbox shortly.</p>"
            "</main></body></html>"
        )

    external_boundary_mocks_only.setattr(
        http_runtime,
        "fetch_html_from_url",
        _fetch_email_terminal_html,
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
            self.browser.html = ""
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


def test_download_report_with_browser_use_does_not_verify_email_from_generic_fetched_terminal_html(
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
            self.browser.html = ""
            payload = json.loads(history.final_result())
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Business Email",
                "Company Name",
                "Country",
                "Industry",
                "Privacy agreement",
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
            "<html><body><h1>Research report</h1>"
            "<p>Complete the form to receive the report.</p>"
            "</body></html>"
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/resources/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.route_status == "inferred"
    assert response.confirmation_evidence.form_disappeared is False
    assert "form_disappeared" not in response.confirmation_evidence.signal_labels

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

__all__ = [
    "test_download_report_with_browser_use_marks_paginated_onsite_capture_complete_after_final_page",
    "test_download_report_with_browser_use_prefers_onsite_capture_over_optional_form_submission",
    "test_download_report_with_browser_use_fetches_onsite_html_when_browser_html_is_missing",
    "test_download_report_with_browser_use_fetches_terminal_html_for_email_delivery_when_browser_html_is_missing",
    "test_download_report_with_browser_use_infers_form_disappeared_from_fetched_terminal_html",
    "test_download_report_with_browser_use_does_not_verify_email_from_generic_fetched_terminal_html",
    "test_download_report_with_browser_use_prefers_delivery_confirmation_over_conflicting_blocker",
    "test_download_report_with_browser_use_clears_conflicting_blocker_after_verified_pdf",
    "test_download_report_with_browser_use_normalizes_text_field_blocker_to_missing_identity",
]
