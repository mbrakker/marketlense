# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        (True, True),
        (False, False),
        ("true", True),
        ("yes", True),
        ("1", True),
        (1, True),
        ("false", False),
        ("no", False),
        ("0", False),
        (0, False),
        (None, None),
    ],
)
def test_browser_agent_result_normalizes_boolean_terminal_signals(
    raw_value,
    expected,
    run_context,
) -> None:
    result = artifact_runtime._parse_browser_result(
        raw_model_response=json.dumps(
            {
                "route_kind": "email_delivery",
                "email_submission_completed": raw_value,
                "confirmation_url_changed": raw_value,
                "form_disappeared": raw_value,
            }
        ),
        normalized_url="https://example.com/report",
        ctx=run_context,
    )

    assert result is not None
    assert result.email_submission_completed is expected
    assert result.confirmation_url_changed is expected
    assert result.form_disappeared is expected


def test_browser_agent_result_logs_ambiguous_boolean_terminal_signal(
    caplog,
    run_context,
) -> None:
    caplog.set_level(
        logging.INFO, logger="market_lense.browser_report_download_artifact"
    )
    result = artifact_runtime._parse_browser_result(
        raw_model_response=json.dumps(
            {
                "route_kind": "email_delivery",
                "email_submission_completed": "completed",
            }
        ),
        normalized_url="https://example.com/report",
        ctx=run_context,
    )

    assert result is not None
    assert result.email_submission_completed is None
    events = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "market_lense.browser_report_download_artifact"
    ]
    assert events[-1]["event"] == "browser_report_download_terminal_signal_ambiguous"
    assert (
        events[-1]["fields"]["raw_signals"]["email_submission_completed"] == "completed"
    )
    assert (
        events[-1]["fields"]["normalized_signals"]["email_submission_completed"] is None
    )


def test_browser_report_download_prompt_marks_unverified_memory_as_weak(
    tmp_path: Path,
    run_context,
) -> None:
    bundle = prompt_runtime.render_browser_report_download_prompt(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_hint=(
                "Filled the form but failed to select a valid Location and submit."
            ),
            route_kind_hint="email_delivery",
            route_family_hint="browser_email_form",
        ),
        ctx=run_context,
        normalized_url="https://example.com/report",
        execution_url="https://example.com/report",
        download_dir=tmp_path / "downloads",
        delivery_email="ops@example.com",
    )

    assert "Previously observed route kind: email_delivery." in bundle.task_prompt
    assert "Treat this as weak memory" in bundle.task_prompt
    assert "Previously successful route" not in bundle.task_prompt
    assert "do not click unrelated navigation links" in bundle.task_prompt
    assert "click the exact matching option text" in bundle.task_prompt
    assert "even when no configured value exists" in bundle.task_prompt
    assert (
        "every mandatory legal/report-delivery agreement checkbox is checked"
        in bundle.task_prompt
    )
    assert (
        "Click the mandatory checkbox, verify it is checked, and submit again"
        in bundle.task_prompt
    )
    assert (
        "separate `route_steps` item for each mandatory checkbox" in bundle.task_prompt
    )
    assert "dispatching `input` and `change`" in bundle.task_prompt
    assert (
        "optional marketing/newsletter opt-in checkboxes unchecked"
        in bundle.task_prompt
    )
    assert "Invisible reCAPTCHA badges" in bundle.task_prompt
    assert "not operator-solvable" in bundle.task_prompt
    assert "Never choose a first enabled option" in bundle.task_prompt
    assert (
        "Research for business type, industry, department, role, or priority"
        in bundle.task_prompt
    )
    assert (
        "open the iframe `src` or same-origin popup/form target directly"
        in bundle.task_prompt
    )
    assert "return `blocked_email_domain` immediately" in bundle.task_prompt


def test_download_report_with_browser_use_redacts_identity_values_from_prompt_logs(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and save the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    settings = replace(
        _settings(tmp_path, work_email="alice.private@example.com"),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="full_name",
                    label="Full name",
                    value="Alice Private",
                    aliases=["name"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value="alice.private@example.com",
                    aliases=["email"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="phone",
                    label="Phone",
                    value="555-123-9876",
                    aliases=["phone"],
                ),
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="company",
                    label="Company",
                    value="Private Company",
                    aliases=["company"],
                ),
            ],
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            delivery_email="alice.delivery@example.com",
        ),
        run_context,
    )

    assert response.outcome == "downloaded"
    events = _service_events(caplog)
    prompt_event = next(
        event
        for event in events
        if event["event"] == "browser_report_download_prompt_prepared"
    )
    request_event = next(
        event for event in events if event["event"] == "browser_report_download_request"
    )
    prompt_fields_json = json.dumps(prompt_event["fields"])
    request_fields_json = json.dumps(request_event["fields"])

    for forbidden in [
        "Alice Private",
        "alice.private@example.com",
        "alice.delivery@example.com",
        "555-123-9876",
        "Private Company",
    ]:
        assert forbidden not in prompt_fields_json
        assert forbidden not in request_fields_json

    assert prompt_event["fields"]["prompt_variables"]["identity_entries"] == [
        {
            "label": "Full name",
            "aliases": "name",
            "value": "***REDACTED***",
            "option_aliases": "",
        },
        {
            "label": "Work email",
            "aliases": "email",
            "value": "***REDACTED***",
            "option_aliases": "",
        },
        {
            "label": "Phone",
            "aliases": "phone",
            "value": "***REDACTED***",
            "option_aliases": "",
        },
        {
            "label": "Company",
            "aliases": "company",
            "value": "***REDACTED***",
            "option_aliases": "",
        },
    ]
    assert prompt_event["fields"]["prompt_variables"]["delivery_email"] == (
        "***REDACTED***"
    )
    assert "***REDACTED***" in prompt_event["fields"]["rendered_user_prompt"]
    assert "***REDACTED***" in request_event["fields"]["task_prompt"]
    assert (
        "Do not navigate to public search engines"
        in prompt_event["fields"]["rendered_system_prompt"]
    )


def test_browser_report_download_prompt_templates_fail_on_missing_variables(
    run_context,
    assert_app_error,
) -> None:
    prompt_set = prompt_service.load_prompt_set(
        PromptLoadRequest(
            schema_version="1.0",
            namespace="browser_report_download/browser_route",
            reload_if_changed=True,
        ),
        run_context,
    )

    with pytest.raises(AppError) as err:
        prompt_service.render_prompt(
            PromptRenderRequest(
                schema_version="1.0",
                template=prompt_set.user,
                variables={
                    "normalized_url": "https://example.com/report",
                    "execution_url": "https://example.com/report",
                    "download_dir": "/tmp/downloads",
                },
            ),
            run_context,
        )

    assert_app_error(
        err.value,
        code="prompt_render_missing_variable",
        retryable=False,
    )


def test_download_report_with_browser_use_returns_downloaded_pdf(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    unexpected_recovery_calls: list[str] = []
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page, click Download report, and wait for the PDF save to finish.",
        create_pdf=True,
        email_submission_completed=None,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )
    external_boundary_mocks_only.setattr(
        http_runtime,
        "download_pdf_from_url",
        lambda **kwargs: unexpected_recovery_calls.append("download_pdf"),
    )
    external_boundary_mocks_only.setattr(
        http_runtime,
        "fetch_html_from_url",
        lambda **kwargs: unexpected_recovery_calls.append("fetch_html") or "",
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=_settings(tmp_path),
            route_hint="Click the main download CTA.",
            route_kind_hint="pdf_download",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.used_route_hint is True
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).exists()
    assert response.downloaded_mime_type == "application/pdf"
    assert response.encountered_form_fields == []
    assert unexpected_recovery_calls == []
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_disables_browser_use_judge(
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
    observed_use_judge: list[bool] = []
    original_runtime = runtime.Agent

    class TrackingAgent(original_runtime):
        def __init__(self, **kwargs):
            observed_use_judge.append(bool(kwargs.get("use_judge", True)))
            super().__init__(**kwargs)

    runtime.Agent = TrackingAgent
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

    assert response.outcome == "downloaded"
    assert observed_use_judge == [False]


def test_download_report_with_browser_use_short_circuits_direct_pdf_url(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
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
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://cdn.example.com/reports/outlook-2026.pdf?download=1",
            settings=_settings(tmp_path),
            route_hint="Click the download CTA.",
            route_kind_hint="pdf_download",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.used_route_hint is False
    assert (
        response.final_page_url
        == "https://cdn.example.com/reports/outlook-2026.pdf?download=1"
    )
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).read_bytes().startswith(b"%PDF-")
    assert response.downloaded_file_name == "outlook-2026.pdf"
    assert response.downloaded_mime_type == "application/pdf"
    assert (
        response.route_summary
        == "Open the direct PDF URL and save the returned PDF file locally."
    )
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_falls_back_from_invalid_direct_pdf(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page, click Download report, and wait for the PDF save to finish.",
        create_pdf=True,
        email_submission_completed=None,
    )
    browser_loaded = {"value": False}

    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"<html><body>login required</body></html>",
            headers={"Content-Type": "text/html"},
        )

    def load_runtime(module_name: str) -> Any:
        browser_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        load_runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://cdn.example.com/reports/outlook-2026.pdf",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert browser_loaded["value"] is True
    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).exists()
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_short_circuits_report_page_pdf_link(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    page_url = "https://example.com/2024-stanford-ai-index-report"
    pdf_url = "https://example.com/hubfs/Stanford_HAI_2024_AI-Index-Report.pdf"
    calls: list[str] = []

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        calls.append(url)
        if url == pdf_url:
            return _FakeResponse(
                content=b"%PDF-1.7 report page pdf bytes",
                headers={"Content-Type": "application/pdf"},
            )
        assert url == page_url
        return _FakeResponse(
            content=(
                b"<html><head><title>Stanford AI Index Report</title></head>"
                b'<body><a href="/hubfs/Stanford_HAI_2024_AI-Index-Report.pdf">'
                b"Download the Report</a></body></html>"
            ),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("browser runtime should not start for HTML PDF-link probe")
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=page_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
            route_kind_hint="pdf_download",
        ),
        run_context,
    )

    assert calls == [page_url, pdf_url]
    assert response.route_kind == "pdf_download"
    assert response.route_family == "report_page_pdf_link_probe"
    assert response.outcome == "downloaded"
    assert response.route_steps[0].action == "open"
    assert response.route_steps[1].action == "extract"
    assert response.route_steps[1].target_url == pdf_url
    assert response.terminal_evidence.traversed_page_urls == [page_url, pdf_url]
    assert response.downloaded_file_path is not None
    assert Path(response.downloaded_file_path).read_bytes().startswith(b"%PDF-")
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_ignores_unrelated_report_page_pdf_link(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page, click Download report, and wait for the PDF save to finish.",
        create_pdf=True,
        email_submission_completed=None,
    )
    browser_loaded = {"value": False}

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=(
                b"<html><head><title>Ultimate Guide to SaaS Affiliate Marketing</title></head>"
                b'<body><a href="https://impact.example.com/legal/'
                b'impact-modern-slavery-statement.pdf">'
                b"Modern slavery statement</a></body></html>"
            ),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    def load_runtime(module_name: str) -> Any:
        browser_loaded["value"] = True
        return runtime

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(browser_runtime, "import_module", load_runtime)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://impact.example.com/partnerships/ultimate-guide-to-saas-affiliate-marketing",
            settings=_settings(tmp_path),
            route_family_hint="browser_pdf_click",
            route_kind_hint="pdf_download",
        ),
        run_context,
    )

    assert browser_loaded["value"] is True
    assert response.route_family == "browser_pdf_click"
    assert response.outcome == "downloaded"
    assert response.downloaded_file_path is not None
    assert Path(str(response.downloaded_file_path)).exists()
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_rejects_unrelated_downloaded_pdf_artifact(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Filled the form but could not verify a required location lookup.",
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class WrongPdfAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            wrong_pdf = (
                Path(self.browser.downloads_path) / "Gender_Pay_Gap_Report_2024.pdf"
            )
            wrong_pdf.write_bytes(b"%PDF-1.7 unrelated")
            self.browser.downloaded_files = [str(wrong_pdf)]
            payload = json.loads(history.final_result())
            payload["route_kind"] = "email_delivery"
            payload["route_family"] = "browser_email_form"
            payload["downloaded_file_path"] = str(wrong_pdf)
            payload["downloaded_file_name"] = wrong_pdf.name
            payload["downloaded_mime_type"] = "application/pdf"
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = (
                "Location did not resolve to a valid option."
            )

            class WrongPdfHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

                def action_results(self_nonlocal) -> list[Any]:
                    return []

            return WrongPdfHistory()

    runtime.Agent = WrongPdfAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/insights/global-food-and-drink-trends",
            settings=_settings(tmp_path),
            candidate_trace=PublisherInventoryCandidateTrace(
                schema_version="1.0",
                canonical_url="https://example.com/insights/global-food-and-drink-trends",
                title="Global Food & Drink Predictions 2026",
                discovered_on_page_number=1,
                source_page_urls=["https://example.com/insights"],
                discovery_provenances=[],
                pdf_url=None,
                published_at_text=None,
                max_confidence=0.8,
            ),
            route_family_hint="browser_email_form",
            route_kind_hint="email_delivery",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_unknown_required_enum"
    assert response.downloaded_file_path is None
    assert response.terminal_evidence.artifact_kind == "email_delivery"
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_http_probe_skips_direct_pdf_fetch_for_html_page(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    observed_urls: list[str] = []

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        observed_urls.append(url)
        return _FakeResponse(
            content=b"<html><body><h1>Report landing page</h1></body></html>",
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("browser runtime should not start for an HTTP probe step")
        ),
    )

    with pytest.raises(AppError) as exc_info:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/reports/slow-html-report",
                settings=_settings(tmp_path),
                route_family_hint="http_pdf_probe",
                route_kind_hint="pdf_download",
            ),
            run_context,
        )

    assert observed_urls == ["https://example.com/reports/slow-html-report"]
    assert_app_error(
        exc_info.value,
        code="browser_download_http_probe_failed",
        retryable=True,
        severity="error",
    )


__all__ = [
    "test_browser_agent_result_normalizes_boolean_terminal_signals",
    "test_browser_agent_result_logs_ambiguous_boolean_terminal_signal",
    "test_browser_report_download_prompt_marks_unverified_memory_as_weak",
    "test_download_report_with_browser_use_redacts_identity_values_from_prompt_logs",
    "test_browser_report_download_prompt_templates_fail_on_missing_variables",
    "test_download_report_with_browser_use_returns_downloaded_pdf",
    "test_download_report_with_browser_use_disables_browser_use_judge",
    "test_download_report_with_browser_use_short_circuits_direct_pdf_url",
    "test_download_report_with_browser_use_falls_back_from_invalid_direct_pdf",
    "test_download_report_with_browser_use_short_circuits_report_page_pdf_link",
    "test_download_report_with_browser_use_ignores_unrelated_report_page_pdf_link",
    "test_download_report_with_browser_use_rejects_unrelated_downloaded_pdf_artifact",
    "test_download_report_with_browser_use_http_probe_skips_direct_pdf_fetch_for_html_page",
]
