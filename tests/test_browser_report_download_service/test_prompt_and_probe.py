from __future__ import annotations

from .builders import *  # noqa: F401,F403


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
        {"label": "Full name", "aliases": "name", "value": "***REDACTED***"},
        {"label": "Work email", "aliases": "email", "value": "***REDACTED***"},
        {"label": "Phone", "aliases": "phone", "value": "***REDACTED***"},
        {"label": "Company", "aliases": "company", "value": "***REDACTED***"},
    ]
    assert prompt_event["fields"]["prompt_variables"]["delivery_email"] == (
        "***REDACTED***"
    )
    assert "***REDACTED***" in prompt_event["fields"]["rendered_user_prompt"]
    assert "***REDACTED***" in request_event["fields"]["task_prompt"]


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


def test_download_report_with_browser_use_short_circuits_static_email_gate(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=(
                b"<html><head><title>Annual Marketing Report</title></head>"
                b"<body><h1>Annual Marketing Report</h1>"
                b"<a>Download the report</a>"
                b"<form><label>Business email address</label>"
                b'<input name="email"><button>Submit</button></form></body></html>'
            ),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("browser runtime should not start for static email gate")
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/insights/annual-marketing-report",
            settings=_settings(tmp_path),
            route_kind_hint="email_delivery",
            route_family_hint="browser_pdf_click",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.route_family == "browser_email_form"
    assert response.outcome == "email_required"
    assert response.browser_had_structured_result is False
    assert response.terminal_evidence.artifact_validation_status == "blocked"
    assert "static_email_gate" in response.terminal_evidence.evidence_labels
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_detects_static_provider_email_gate(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=(
                b"<html><head><title>Whitepaper Download</title></head>"
                b'<body><script src="/pardot/forms.js"></script>'
                b"<a>Download eBook</a><section>Whitepaper report asset</section>"
                b"</body></html>"
            ),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("browser runtime should not start for provider email gate")
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/whitepapers/product-lifecycle-management",
            settings=_settings(tmp_path),
            route_kind_hint="email_delivery",
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.outcome == "email_required"
    assert response.route_family == "browser_email_form"
    assert response.browser_had_structured_result is False
    assert "static_email_gate" in response.terminal_evidence.evidence_labels
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_classifies_static_email_timeout(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    observed_urls: list[str] = []

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        observed_urls.append(url)
        raise requests.Timeout("static preflight timeout")

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError("browser runtime should not start after static timeout gate")
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/resources/reports/annual-marketing-report",
            settings=_settings(tmp_path),
            route_kind_hint="email_delivery",
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert observed_urls == [
        "https://example.com/resources/reports/annual-marketing-report",
        "https://example.com/resources/reports/annual-marketing-report",
    ]
    assert response.outcome == "email_required"
    assert response.route_status == "inferred"
    assert "static_fetch_timeout" in response.terminal_evidence.evidence_labels
    assert response.terminal_evidence.terminal_text_excerpt
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_short_circuits_known_access_challenge(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=(
                b"<html><title>Just a moment</title>"
                b"Cloudflare security check. Verify you are human.</html>"
            ),
            status_code=403,
            headers={"Content-Type": "text/html"},
        )

    def fail_if_browser_loaded(module_name: str) -> Any:
        raise AssertionError(
            f"browser runtime should not load for access challenge: {module_name}"
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
            url="https://example.com/whitepapers/report",
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_captcha"
    assert response.terminal_evidence.artifact_validation_status == "blocked"
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_extracts_email_route_embedded_pdf_link(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    page_url = "https://example.com/resources/asset/ebook-transforming-search-ai"
    pdf_url = (
        "https://cdn.example.com/files/Ebook_transforming-search-ai_compressed.pdf"
    )
    observed_urls: list[str] = []

    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        observed_urls.append(url)
        if url == pdf_url:
            return _FakeResponse(
                content=b"%PDF-1.7 embedded ebook",
                status_code=200,
                headers={"Content-Type": "application/pdf"},
            )
        assert url == page_url
        return _FakeResponse(
            content=(
                b'<html><body><a href="https://cdn.example.com/files/'
                b'Ebook_transforming-search-ai_compressed.pdf">'
                b"Download ebook</a></body></html>"
            ),
            status_code=200,
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    def fail_if_browser_loaded(module_name: str) -> Any:
        raise AssertionError(
            f"browser runtime should not load for embedded PDF link: {module_name}"
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
            url=page_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "pdf_download"
    assert response.outcome == "downloaded"
    assert response.route_family == "report_page_pdf_link_probe"
    assert observed_urls == [page_url, pdf_url]
    assert response.downloaded_file_path is not None
    assert_no_defaulted_required_fields(response)
    assert_logs_have_required_fields(_service_events(caplog))


def test_download_report_with_browser_use_fetches_real_pdf_from_wrapper(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page and click the PDF link.",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class WrapperAgent(original_runtime):
        def run_sync(self, max_steps: int):
            self.browser.url = "https://example.com/pdf-wrapper"
            download_dir = Path(self.browser.downloads_path)
            download_dir.mkdir(parents=True, exist_ok=True)
            wrapper_path = download_dir / "report.pdf"
            wrapper_path.write_text(
                (
                    "<head><script>window.location.replace("
                    "'https://cdn.example.com/report.pdf');</script></head>"
                    "<body><embed type='application/pdf' "
                    "src='https://cdn.example.com/report.pdf' /></body>"
                ),
                encoding="utf-8",
            )
            self.browser.downloaded_files = [str(wrapper_path)]
            payload = json.loads(super().run_sync(max_steps).final_result())
            payload["downloaded_file_path"] = str(wrapper_path)
            payload["downloaded_file_name"] = wrapper_path.name
            payload["downloaded_mime_type"] = "application/pdf"

            class WrapperHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return WrapperHistory()

    runtime.Agent = WrapperAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=b"%PDF-1.7 actual pdf bytes",
            headers={"Content-Type": "application/pdf"},
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)

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
    assert Path(str(response.downloaded_file_path)).read_bytes().startswith(b"%PDF-")
    assert response.downloaded_size_bytes == len(b"%PDF-1.7 actual pdf bytes")
    assert response.downloaded_mime_type == "application/pdf"
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_returns_email_required_without_address(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the gated page and enter an email in the submit form.",
        create_pdf=False,
        email_submission_completed=False,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/email-gated-report",
            settings=_settings(tmp_path, work_email=None),
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_required"
    assert response.downloaded_file_path is None
    assert response.encountered_form_fields == []
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_returns_encountered_form_fields(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the gated page and inspect the registration form.",
        create_pdf=False,
        email_submission_completed=False,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    original_runtime = runtime.Agent

    class EncounterAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["encountered_form_fields"] = [
                "Name",
                "Business",
                "Email",
                "Email",
            ]

            class EncounterHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return EncounterHistory()

    runtime.Agent = EncounterAgent

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/form-report",
            settings=_settings(tmp_path, work_email=None),
        ),
        run_context,
    )

    assert response.encountered_form_fields == ["Name", "Business", "Email"]


def test_download_report_with_browser_use_reclassifies_email_message(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Fill the form and submit the download request.",
        create_pdf=False,
        email_submission_completed=True,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    original_runtime = runtime.Agent

    class ReclassifyAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["post_submit_message"] = (
                "Thanks. We sent the download link to your email inbox."
            )
            payload["encountered_form_fields"] = [
                "Name",
                "Title / Role",
                "Business / Organization",
                "Email",
            ]

            class ReclassifyHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return ReclassifyHistory()

    runtime.Agent = ReclassifyAgent

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/form-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.downloaded_file_path is None
    assert response.encountered_form_fields == [
        "Name",
        "Title / Role",
        "Business / Organization",
        "Email",
    ]
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_treats_generic_success_text_as_email_requested(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary=(
            "Filled the form fields and submitted the gated report request."
        ),
        create_pdf=False,
        email_submission_completed=True,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    original_runtime = runtime.Agent

    class SuccessTextAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["post_submit_message"] = "Thank you for submitting the form."
            payload["encountered_form_fields"] = [
                "First Name",
                "Last Name",
                "Company Name",
                "Professional Email",
                "Business Phone",
            ]

            class SuccessTextHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return SuccessTextHistory()

    runtime.Agent = SuccessTextAgent

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/form-report",
            settings=_settings(tmp_path),
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.outcome == "email_requested"
    assert response.blocked_reason is None


def test_download_report_with_browser_use_requires_semantic_route_summary(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Clicked button.",
        create_pdf=True,
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
                url="https://example.com/report",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_route_summary_too_weak",
        retryable=True,
    )


def test_download_report_with_browser_use_maps_empty_page_to_retryable_load_error(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="blocked_unknown_required_enum",
        route_summary=(
            "The target page failed to load after multiple attempts, preventing further interaction."
        ),
        create_pdf=False,
        email_submission_completed=False,
    )
    original_runtime = runtime.Agent

    class EmptyPageAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = (
                "The page at the provided URL did not load any content after multiple waits."
            )
            payload["encountered_form_fields"] = []

            class EmptyPageHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return EmptyPageHistory()

    runtime.Agent = EmptyPageAgent
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
                route_family_hint="browser_email_form",
            ),
            run_context,
        )

    assert_app_error(
        excinfo.value,
        code="browser_download_page_not_loaded",
        retryable=True,
    )


def test_download_report_with_browser_use_rejects_conflicting_pdf_metadata(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the landing page, click Download report, and wait for the file save to finish.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class ConflictingMimeAgent(original_runtime):
        def run_sync(self, max_steps: int):
            history = super().run_sync(max_steps)
            payload = json.loads(history.final_result())
            payload["downloaded_mime_type"] = "text/html"

            class ConflictingMimeHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return ConflictingMimeHistory()

    runtime.Agent = ConflictingMimeAgent
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
        code="browser_download_invalid_pdf_metadata",
        retryable=True,
    )


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
        browser_runtime,
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
