# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_download_report_with_browser_use_raises_when_pdf_classification_has_no_verifiable_artifact(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page, click the main download CTA, and wait for the PDF save to finish.",
        create_pdf=False,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as excinfo:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/broken-report",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_unverified_pdf_claim",
        retryable=True,
    )
    assert excinfo.value.context["download_dir"]
    assert excinfo.value.context["execution_url"] == "https://example.com/broken-report"
    assert excinfo.value.context["route_family_hint"] == ""
    assert excinfo.value.context["html_snapshot_path"]
    assert Path(str(excinfo.value.context["html_snapshot_path"])).exists()
    assert excinfo.value.context["screenshot_path"]
    assert Path(str(excinfo.value.context["screenshot_path"])).exists()
    assert excinfo.value.context["network_event_count"] == 0

def test_download_report_with_browser_use_adopts_external_pdf_attachment(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the current page as a PDF.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class ExternalAttachmentAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/report"
            self.browser.title = "External attachment report"
            external_dir = tmp_path / "browseruse_agent_data"
            external_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = external_dir / "external-report.pdf"
            pdf_path.write_bytes(b"%PDF-1.7 external attachment")
            payload = {
                "route_kind": "pdf_download",
                "route_summary": "Open the report page and save the current page as a PDF artifact.",
                "final_page_url": "https://example.com/report",
                "resolved_target_url": "https://example.com/report",
                "email_submission_completed": None,
                "downloaded_file_path": None,
                "downloaded_file_name": None,
                "downloaded_mime_type": None,
                "encountered_form_fields": [],
                "post_submit_message": "",
                "route_steps": [
                    {
                        "index": 0,
                        "action": "navigate",
                        "target_text": "",
                        "target_role": "url",
                        "target_url": "https://example.com/report",
                        "result": "Opened the report landing page",
                    },
                    {
                        "index": 1,
                        "action": "save_as_pdf",
                        "target_text": "external-report.pdf",
                        "target_role": "page",
                        "target_url": "https://example.com/report",
                        "result": "Saved the current page as PDF",
                    },
                ],
            }

            class ExternalAttachmentHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

                def action_results(self_nonlocal) -> list[Any]:
                    return [SimpleNamespace(attachments=[str(pdf_path)])]

            return ExternalAttachmentHistory()

    runtime.Agent = ExternalAttachmentAgent
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
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    downloaded_path = Path(str(response.downloaded_file_path))
    assert downloaded_path.exists()
    assert downloaded_path.parent != (tmp_path / "browseruse_agent_data")
    assert str(tmp_path / "downloads") in str(downloaded_path)
    assert downloaded_path.read_bytes().startswith(b"%PDF-")

def test_download_report_with_browser_use_materializes_browser_use_temp_pdf_before_cleanup(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the report PDF.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class TempAttachmentAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/temp-report"
            self.browser.title = "Temp attachment report"
            temp_dir = (
                Path(tempfile.gettempdir())
                / f"browseruse-tmp-market-lense-test-{tmp_path.name}"
            )
            temp_dir.mkdir(parents=True, exist_ok=True)
            pdf_path = temp_dir / "temp-report.pdf"
            pdf_path.write_bytes(b"%PDF-1.7 temp attachment")
            payload = {
                "route_kind": "pdf_download",
                "route_summary": "Saved the report PDF through browser-use.",
                "final_page_url": "https://example.com/temp-report",
                "resolved_target_url": "https://example.com/temp-report",
                "email_submission_completed": None,
                "downloaded_file_path": str(pdf_path),
                "downloaded_file_name": "temp-report.pdf",
                "downloaded_mime_type": "application/pdf",
                "encountered_form_fields": [],
                "post_submit_message": "",
                "route_steps": [
                    {
                        "index": 1,
                        "action": "download",
                        "target_text": "Download PDF",
                        "target_role": "link",
                        "target_url": "https://example.com/temp-report",
                        "result": "Saved temp-report.pdf",
                    },
                ],
            }

            class TempAttachmentHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

                def action_results(self_nonlocal) -> list[Any]:
                    return [SimpleNamespace(attachments=[str(pdf_path)])]

            return TempAttachmentHistory()

    runtime.Agent = TempAttachmentAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/temp-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    downloaded_path = Path(str(response.downloaded_file_path))
    assert downloaded_path.exists()
    assert str(tmp_path / "downloads") in str(downloaded_path)
    assert downloaded_path.name == "temp-report.pdf"
    assert downloaded_path.read_bytes().startswith(b"%PDF-")

def test_download_report_with_browser_use_raises_for_unverified_pdf_claim_with_spurious_blocker(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Attempted to follow the report links but did not acquire an artifact.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class SpuriousBlockerAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/2026-report"
            self.browser.title = "2026 Report"
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = (
                "The agent could not find the correct report link after multiple attempts."
            )
            payload["terminal_text_excerpt"] = "The 2026 report page is available here."

            class SpuriousBlockerHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

                def action_results(self_nonlocal) -> list[Any]:
                    return []

            return SpuriousBlockerHistory()

    runtime.Agent = SpuriousBlockerAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as excinfo:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/2026-report",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_unverified_pdf_claim",
        retryable=True,
    )

def test_download_report_with_browser_use_raises_for_invalid_pdf_stub(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page, click the main download CTA, and wait for the PDF save to finish.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class InvalidPdfAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/pdf-wrapper"
            download_dir = Path(self.browser.downloads_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            wrapper_path = download_dir / "report.pdf"
            wrapper_path.write_text(
                "<html><body>not a pdf</body></html>", encoding="utf-8"
            )
            self.browser.downloaded_files = [str(wrapper_path)]
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["downloaded_file_path"] = str(wrapper_path)
            payload["downloaded_file_name"] = wrapper_path.name
            payload["downloaded_mime_type"] = "application/pdf"

            class InvalidPdfHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return InvalidPdfHistory()

    runtime.Agent = InvalidPdfAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as excinfo:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_invalid_pdf",
        retryable=True,
    )

def test_download_report_with_browser_use_direct_pdf_skips_browser_config_requirements(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"%PDF-1.7 direct pdf bytes",
            headers={"Content-Type": "application/pdf"},
        )

    def fail_if_browser_loaded(module_name: str) -> Any:
        raise AssertionError(
            f"browser runtime should not load for direct pdf URL: {module_name}"
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        fail_if_browser_loaded,
    )
    settings = _settings(tmp_path)
    settings = BrowserDownloadSettings(
        schema_version=settings.schema_version,
        openrouter_api_key="",
        model="",
        temperature=settings.temperature,
        timeout_seconds=settings.timeout_seconds,
        max_steps=settings.max_steps,
        output_dir=settings.output_dir,
        state_db=settings.state_db,
        reports_db=settings.reports_db,
        identity_config_path=settings.identity_config_path,
        identity_profile=settings.identity_profile,
        openrouter_http_referer=settings.openrouter_http_referer,
        headed=settings.headed,
        retry_retries=settings.retry_retries,
        retry_base_delay_seconds=settings.retry_base_delay_seconds,
        retry_backoff_step_seconds=settings.retry_backoff_step_seconds,
        retry_jitter_seconds=settings.retry_jitter_seconds,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://cdn.example.com/reports/outlook-2026.pdf",
            settings=settings,
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None

def test_download_report_with_browser_use_prefers_candidate_pdf_probe(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/report",
        title="Discovery PDF",
        discovered_on_page_number=1,
        source_page_urls=["https://example.com/insights"],
        discovery_provenances=["direct_pdf_source"],
        pdf_url="https://cdn.example.com/discovery-report.pdf",
        published_at_text=None,
        max_confidence=0.98,
    )

    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"%PDF-1.7 discovery bytes",
            headers={"Content-Type": "application/pdf"},
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("browser runtime should not load for candidate pdf probe")
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            candidate_trace=candidate_trace,
            attempt_url=candidate_trace.pdf_url,
            route_family_hint="direct_pdf_probe",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.used_candidate_pdf_url is True
    assert response.route_family == "direct_pdf_probe"

def test_download_report_with_browser_use_respects_planned_browser_email_form_after_candidate_pdf_probe_fails(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/gated-report",
        title="Gated Report",
        discovered_on_page_number=1,
        source_page_urls=["https://example.com/reports"],
        discovery_provenances=["direct_pdf_source"],
        pdf_url="https://cdn.example.com/gated-report.pdf",
        published_at_text=None,
        max_confidence=0.96,
    )
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the lead form and received confirmation that the report will be emailed.",
        create_pdf=False,
        email_submission_completed=True,
    )

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        if str(url).casefold().endswith(".pdf"):
            raise AssertionError(
                "browser email fallback must not retry candidate PDF fetch"
            )
        return _FakeResponse(
            content=b"<html><body><form><input name='email'></form></body></html>",
            headers={"Content-Type": "text/html"},
            url=str(url),
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=candidate_trace.canonical_url,
            settings=_settings(tmp_path),
            candidate_trace=candidate_trace,
            attempt_url=candidate_trace.canonical_url,
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.outcome == "email_required"
    assert response.route_kind == "email_delivery"
    assert response.route_family == "browser_email_form"
    assert response.used_candidate_pdf_url is False

def test_download_report_with_browser_use_salvages_empty_browser_result_from_candidate_pdf(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/report",
        title="Discovery PDF",
        discovered_on_page_number=1,
        source_page_urls=["https://example.com/insights"],
        discovery_provenances=["browser_dom"],
        pdf_url="https://cdn.example.com/discovery-report.pdf",
        published_at_text=None,
        max_confidence=0.91,
    )
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the page and click the report CTA.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class EmptyAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/report/final"

            class EmptyHistory:
                def final_result(self_nonlocal) -> str:
                    return ""

            return EmptyHistory()

    runtime.Agent = EmptyAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: _FakeResponse(
            content=b"%PDF-1.7 discovery salvage",
            headers={"Content-Type": "application/pdf"},
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            candidate_trace=candidate_trace,
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    assert response.browser_had_structured_result is False
    assert response.used_candidate_pdf_url is True

def test_download_report_with_browser_use_logs_discovery_prompt_context(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://trk.example.com/campaign?id=123",
        title="Tracker Candidate",
        discovered_on_page_number=2,
        source_page_urls=["https://example.com/insights"],
        discovery_provenances=["browser_dom"],
        pdf_url=None,
        published_at_text=None,
        max_confidence=0.73,
    )
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the source page, click the report link, and download the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=candidate_trace.canonical_url,
            settings=_settings(tmp_path),
            candidate_trace=candidate_trace,
            attempt_url="https://example.com/insights",
            route_family_hint="browser_tracker_redirect",
            source_page_url_hint="https://example.com/insights",
            publisher_discovery_route_kind="browser_render",
            publisher_recommended_discovery_route_kind="browser_render",
        ),
        run_context,
    )

    prompt_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == service.logger.name
        and json.loads(record.message).get("event")
        == "browser_report_download_prompt_prepared"
    ]
    assert len(prompt_events) == 1
    fields = prompt_events[0]["fields"]
    assert fields["candidate_canonical_url"] == candidate_trace.canonical_url
    assert fields["candidate_source_page_urls"] == ["https://example.com/insights"]
    assert fields["publisher_recommended_discovery_route_kind"] == "browser_render"
    assert "redirect" in fields["rendered_user_prompt"].casefold()
    assert "https://example.com/insights" in fields["rendered_user_prompt"]
    assert fields["prompt_variables"]["route_family_hint"] == "browser_tracker_redirect"

def test_download_report_with_browser_use_logs_onsite_prompt_guidance(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    candidate_trace = PublisherInventoryCandidateTrace(
        schema_version="1.0",
        canonical_url="https://example.com/research/market-outlook-2026",
        title="Market Outlook 2026",
        discovered_on_page_number=1,
        source_page_urls=["https://example.com/research"],
        discovery_provenances=["browser_dom"],
        pdf_url=None,
        published_at_text=None,
        max_confidence=0.82,
    )
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Open the report page, capture the article locally, and verify completeness.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class OnsiteAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            onsite_path = Path(self.browser.downloads_path) / "onsite-report.html"
            onsite_path.write_text(
                "<article><h1>Market Outlook</h1><p>Longread body.</p></article>",
                encoding="utf-8",
            )
            payload["onsite_capture_path"] = str(onsite_path)
            payload["onsite_capture_format"] = "html"
            payload["onsite_page_count"] = 1
            payload["onsite_completeness_status"] = "complete"

            class OnsiteHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return OnsiteHistory()

    runtime.Agent = OnsiteAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=candidate_trace.canonical_url,
            settings=_settings(tmp_path),
            candidate_trace=candidate_trace,
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    prompt_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == service.logger.name
        and json.loads(record.message).get("event")
        == "browser_report_download_prompt_prepared"
    ]
    assert len(prompt_events) == 1
    fields = prompt_events[0]["fields"]
    assert "on-site content" in fields["rendered_user_prompt"].casefold()
    assert fields["prompt_variables"]["route_family_hint"] == "browser_onsite_report"
    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"

def test_download_report_with_browser_use_logs_remembered_route_step_hints(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="onsite_report",
        route_summary="Accept cookies and extract the report body.",
        create_pdf=False,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    service.download_report_with_browser_use(
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

    prompt_events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == service.logger.name
        and json.loads(record.message).get("event")
        == "browser_report_download_prompt_prepared"
    ]
    assert len(prompt_events) == 1
    rendered_user_prompt = prompt_events[0]["fields"]["rendered_user_prompt"]
    assert (
        "Replay these remembered structured route steps before broader exploration:"
        in rendered_user_prompt
    )
    assert "1. click Allow all -> Accepted cookies" in rendered_user_prompt
    assert (
        "2. extract report article -> Captured the on-site report body"
        in rendered_user_prompt
    )

__all__ = [
    "test_download_report_with_browser_use_raises_when_pdf_classification_has_no_verifiable_artifact",
    "test_download_report_with_browser_use_adopts_external_pdf_attachment",
    "test_download_report_with_browser_use_materializes_browser_use_temp_pdf_before_cleanup",
    "test_download_report_with_browser_use_raises_for_unverified_pdf_claim_with_spurious_blocker",
    "test_download_report_with_browser_use_raises_for_invalid_pdf_stub",
    "test_download_report_with_browser_use_direct_pdf_skips_browser_config_requirements",
    "test_download_report_with_browser_use_prefers_candidate_pdf_probe",
    "test_download_report_with_browser_use_salvages_empty_browser_result_from_candidate_pdf",
    "test_download_report_with_browser_use_logs_discovery_prompt_context",
    "test_download_report_with_browser_use_logs_onsite_prompt_guidance",
    "test_download_report_with_browser_use_logs_remembered_route_step_hints",
]
