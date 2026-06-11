# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_download_report_with_browser_use_recovers_embedded_pdf_from_encoded_wrapper(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and click the wrapped PDF link.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class EncodedWrapperAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/report"
            self.browser.title = "Wrapped report"
            download_dir = Path(self.browser.downloads_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            wrapper_path = download_dir / "report.pdf"
            wrapper_path.write_text(
                (
                    "<html><body><iframe "
                    'src="/viewer?downloadData=https%3A%2F%2Fcdn.example.com%2Freal-report.pdf">'
                    "</iframe></body></html>"
                ),
                encoding="utf-8",
            )
            self.browser.downloaded_files = [str(wrapper_path)]
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["downloaded_file_path"] = str(wrapper_path)
            payload["downloaded_file_name"] = wrapper_path.name
            payload["downloaded_mime_type"] = "application/pdf"

            class EncodedWrapperHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return EncodedWrapperHistory()

    runtime.Agent = EncodedWrapperAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            content=b"%PDF-1.7 recovered bytes",
            headers={"Content-Type": "application/pdf"},
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).read_bytes().startswith(b"%PDF-")

def test_download_report_with_browser_use_salvages_empty_result_to_email_required(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the gated report page and inspect the form.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class EmptyEmailAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/gated-report"
            self.browser.title = "Download the report"
            self.browser.html = (
                "<html><body><form>"
                "<label>Email</label><input name='email' />"
                "<label>Industry</label><select name='industry'></select>"
                "<button type='submit'>Submit</button>"
                "</form></body></html>"
            )

            class EmptyHistory:
                def final_result(self_nonlocal) -> str:
                    return ""

            return EmptyHistory()

    runtime.Agent = EmptyEmailAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/gated-report",
            settings=_settings(tmp_path, work_email=None),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason in {
        "blocked_missing_identity_field",
        "blocked_unknown_required_enum",
    }
    assert "Email" in response.encountered_form_fields

def test_download_report_with_browser_use_normalizes_blocked_route_kind_to_email_delivery(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="blocked_unknown_required_enum",
        route_summary="",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class BlockedKindAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/gated-report"
            self.browser.title = "Download report"
            self.browser.html = (
                "<html><body><form>"
                "<label>Industry</label><select name='industry'></select>"
                "<button type='submit'>Download</button>"
                "</form></body></html>"
            )
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["route_kind"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = "Industry selection is required."
            payload["terminal_text_excerpt"] = "Industry selection is required."

            class BlockedKindHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return BlockedKindHistory()

    runtime.Agent = BlockedKindAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/gated-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_unknown_required_enum"
    assert response.blocked_reason_detail == "Industry selection is required."

def test_download_report_with_browser_use_prefetches_structured_pdf_url_before_cleanup(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and click Download.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent
    signed_pdf_url = (
        "https://cdn.example.com/assets/report.pdf?"
        "X-Amz-Expires=120&X-Amz-Signature=abc123"
    )

    class SignedPdfAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["resolved_target_url"] = signed_pdf_url
            payload["final_page_url"] = signed_pdf_url
            payload["downloaded_file_name"] = "report.pdf"
            payload["downloaded_mime_type"] = "application/pdf"
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "click",
                    "target_text": "Download",
                    "target_role": "button",
                    "target_url": signed_pdf_url,
                    "result": "Opened the signed PDF URL.",
                }
            ]
            self.browser.url = signed_pdf_url
            self.browser.title = "report.pdf"
            self.browser.html = ""

            class SignedPdfHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return SignedPdfHistory()

    def _download_pdf_from_url(**kwargs) -> None:
        assert kwargs["pdf_url"] == signed_pdf_url
        Path(kwargs["destination_path"]).write_bytes(b"%PDF-1.7 signed")

    runtime.Agent = SignedPdfAgent
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
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(response.downloaded_file_path).read_bytes().startswith(b"%PDF-")

def test_download_report_with_browser_use_rejects_report_not_found_listing(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Navigated to reports library, but the specific report was not found.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class NotFoundListingAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["route_kind"] = "onsite_report"
            payload["route_family"] = "browser_listing_hub"
            payload["final_page_url"] = (
                "https://datareportal.com/reports/?tag=Digital+2022"
            )
            payload["resolved_target_url"] = (
                "https://datareportal.com/reports/?tag=Digital+2022"
            )
            payload["terminal_text_excerpt"] = (
                "POSTS TAGGED DIGITAL 2022 Digital 2022: Tuvalu"
            )
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "search_page",
                    "target_text": "Digital 2022: Wallis and Futuna",
                    "target_role": "page",
                    "target_url": "https://datareportal.com/reports/?tag=Digital+2022",
                    "result": 'Searched page for "Digital 2022: Wallis and Futuna": 0 matches found.',
                }
            ]
            self.browser.url = "https://datareportal.com/reports/?tag=Digital+2022"
            self.browser.title = "Posts tagged Digital 2022"
            self.browser.html = "<html><body>POSTS TAGGED DIGITAL 2022</body></html>"

            class NotFoundHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return NotFoundHistory()

    runtime.Agent = NotFoundListingAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as exc_info:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://datareportal.com/reports/digital-2022-wallis-and-futuna",
                settings=_settings(tmp_path),
                route_family_hint="browser_listing_hub",
                candidate_trace=PublisherInventoryCandidateTrace(
                    schema_version="1.0",
                    canonical_url="https://datareportal.com/reports/digital-2022-wallis-and-futuna",
                    title="Digital 2022: Wallis and Futuna",
                    discovered_on_page_number=53,
                    source_page_urls=[
                        "https://datareportal.com/reports?offset=1658385029582"
                    ],
                    discovery_provenances=[],
                    pdf_url=None,
                    published_at_text=None,
                    max_confidence=0.8,
                ),
            ),
            run_context,
        )

    assert_app_error(
        exc_info.value,
        code="browser_download_report_not_found",
        retryable=False,
    )

def test_download_report_with_browser_use_accepts_nullable_structured_result_fields(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Submit the form.",
        create_pdf=False,
        email_submission_completed=True,
    )
    original_runtime = runtime.Agent

    class NullableResultAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "open",
                    "target_text": None,
                    "target_role": None,
                    "target_url": "https://example.com/report",
                    "result": "opened",
                }
            ]
            payload["post_submit_message"] = None
            payload["submit_button_state"] = None
            payload["blocked_reason"] = None
            payload["blocked_reason_detail"] = None
            payload["final_page_title"] = "Thank you"
            payload["terminal_text_excerpt"] = "Thanks for your interest."
            payload["final_page_url"] = "https://example.com/thank-you"
            payload["resolved_target_url"] = "https://example.com/thank-you"
            payload["confirmation_url_changed"] = True
            payload["form_disappeared"] = True
            self.browser.url = "https://example.com/thank-you"
            self.browser.title = "Thank you"
            self.browser.html = "<html><body><h1>Thank you</h1></body></html>"

            class NullableHistory:
                def final_result(self) -> str:
                    return json.dumps(payload)

                def action_results(self) -> list[Any]:
                    return []

            return NullableHistory()

    runtime.Agent = NullableResultAgent
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
    assert response.route_steps[0].target_text == ""
    assert response.route_steps[0].target_role == "page"

__all__ = [
    "test_download_report_with_browser_use_recovers_embedded_pdf_from_encoded_wrapper",
    "test_download_report_with_browser_use_salvages_empty_result_to_email_required",
    "test_download_report_with_browser_use_normalizes_blocked_route_kind_to_email_delivery",
    "test_download_report_with_browser_use_prefetches_structured_pdf_url_before_cleanup",
    "test_download_report_with_browser_use_rejects_report_not_found_listing",
    "test_download_report_with_browser_use_accepts_nullable_structured_result_fields",
]
