# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


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
                settings=_settings(tmp_path, work_email=None),
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
                settings=_settings(tmp_path, work_email=None),
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


def test_download_report_with_browser_use_does_not_static_gate_when_delivery_email_is_available(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
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

    browser_started = {"value": False}

    def fake_import_module(module_name: str) -> Any:
        browser_started["value"] = True
        raise AppError(
            code="browser_runtime_started",
            message="Browser runtime started after static email gate was bypassed",
            retryable=False,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(browser_runtime, "import_module", fake_import_module)

    with pytest.raises(AppError) as exc_info:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/insights/annual-marketing-report",
                settings=_settings(tmp_path),
                delivery_email="reports@example.com",
                route_kind_hint="email_delivery",
                route_family_hint="browser_email_form",
            ),
            run_context,
        )

    assert exc_info.value.code == "browser_use_unavailable"
    assert browser_started["value"] is True


def test_download_report_with_browser_use_does_not_static_gate_when_configured_email_is_available(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
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

    browser_started = {"value": False}

    def fake_import_module(module_name: str) -> Any:
        browser_started["value"] = True
        raise AppError(
            code="browser_runtime_started",
            message="Browser runtime started after static email gate was bypassed",
            retryable=False,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(browser_runtime, "import_module", fake_import_module)

    with pytest.raises(AppError) as exc_info:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/insights/annual-marketing-report",
                settings=_settings(tmp_path),
                route_kind_hint="email_delivery",
                route_family_hint="browser_email_form",
            ),
            run_context,
        )

    assert exc_info.value.code == "browser_use_unavailable"
    assert browser_started["value"] is True


def test_download_report_with_browser_use_uses_remembered_interactive_captcha_blocker(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=(
                b"<html><head><title>Guide Download</title></head>"
                b"<body><h1>Guide Download</h1>"
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
            AssertionError("browser runtime should not start for remembered CAPTCHA")
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/guides/product-guide",
            settings=_settings(tmp_path),
            delivery_email="reports@example.com",
            route_hint=(
                "Filled the form, then the flow was blocked by an interactive "
                "reCAPTCHA challenge displayed in the modal."
            ),
            route_kind_hint="email_delivery",
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.route_family == "browser_email_form"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_captcha"
    assert response.used_route_hint is True
    assert response.browser_had_structured_result is False
    assert "remembered_interactive_captcha" in response.terminal_evidence.evidence_labels
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_reruns_remembered_captcha_in_headed_agent(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=(
                b"<html><head><title>Guide Download</title></head>"
                b"<body><h1>Guide Download</h1>"
                b"<form><label>Business email address</label>"
                b'<input name="email"><button>Submit</button></form></body></html>'
            ),
            headers={"Content-Type": "text/html; charset=utf-8"},
        )

    captured: dict[str, Any] = {}
    fake_runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Operator completed CAPTCHA and submitted the form.",
        create_pdf=False,
        email_submission_completed=True,
        post_submit_message=(
            "Thank you. Your report has been sent to your business email."
        ),
    )
    original_browser = fake_runtime.Browser
    original_agent = fake_runtime.Agent

    class CapturingBrowser(original_browser):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            captured["headless"] = self.headless

        def start(self) -> None:
            raise AssertionError("service must not pre-start CAPTCHA handoff browser")

        def new_page(self, url: str) -> None:
            raise AssertionError(f"service must not pre-open CAPTCHA URL: {url}")

        def get_current_page(self):
            return None

    class CapturingAgent(original_agent):
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            super().__init__(*args, **kwargs)
            captured["task"] = self.task

    fake_runtime.Browser = CapturingBrowser
    fake_runtime.Agent = CapturingAgent

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: fake_runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/guides/product-guide",
            settings=replace(
                _settings(tmp_path),
                captcha_handoff_policy=BrowserDownloadCaptchaHandoffPolicy(
                    schema_version="1.0",
                    enabled=True,
                    timeout_seconds=120.0,
                ),
            ),
            delivery_email="reports@example.com",
            route_hint=(
                "Filled the form, then the flow was blocked by an interactive "
                "reCAPTCHA challenge displayed in the modal."
            ),
            route_kind_hint="email_delivery",
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert captured["headless"] is False
    assert "CAPTCHA manual handoff is enabled" in captured["task"]
    assert "Do not wait on the initial landing page" in captured["task"]
    assert "Do not solve or bypass CAPTCHA automatically" in captured["task"]
    assert "Do not finish the task" in captured["task"]
    assert "full handoff window expires" in captured["task"]
    assert response.route_kind == "email_delivery"
    assert response.route_family == "browser_email_form"
    assert response.outcome == "email_requested"
    assert response.blocked_reason is None
    assert_no_defaulted_required_fields(response)


def test_download_report_with_browser_use_uses_remembered_access_forbidden_blocker(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    def fake_get(url: str, *args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=(
                b"<html><head><title>Report Download</title></head>"
                b"<body><h1>Report Download</h1>"
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
            AssertionError("browser runtime should not start for remembered HTTP 403")
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/resources/security-report",
            settings=_settings(tmp_path),
            delivery_email="reports@example.com",
            route_hint=(
                "Browser route reached the form, but HTTP 403 Forbidden access "
                "control prevented loading the archive page."
            ),
            route_kind_hint="email_delivery",
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.route_family == "browser_email_form"
    assert response.outcome == "email_required"
    assert response.blocked_reason == "blocked_static_archive"
    assert response.used_route_hint is True
    assert response.browser_had_structured_result is False
    assert "remembered_access_forbidden" in response.terminal_evidence.evidence_labels
    assert_no_defaulted_required_fields(response)


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
                settings=_settings(tmp_path, work_email=None),
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


def test_download_report_with_browser_use_short_circuits_redirected_terminal_not_found(
    tmp_path: Path,
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    original_url = "https://go.example.com/commerce-media-trends-report"
    final_url = "https://www4.example.com/commerce-media-trends-report"

    def fake_get(*args: Any, **kwargs: Any) -> _FakeResponse:
        return _FakeResponse(
            content=(
                b"<html><head><title>404 Not Found</title></head>"
                b"<body>The requested URL was not found on this server.</body></html>"
            ),
            status_code=404,
            headers={"Content-Type": "text/html; charset=utf-8"},
            url=final_url,
        )

    external_boundary_mocks_only.setattr(http_runtime.requests, "get", fake_get)
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: (_ for _ in ()).throw(
            AssertionError(
                "browser runtime should not load for terminal HTTP not-found page"
            )
        ),
    )
    caplog.set_level(logging.INFO, logger=service.logger.name)

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url=original_url,
            settings=_settings(tmp_path),
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.route_family == "http_terminal_static_archive_preflight"
    assert response.outcome == "email_required"
    assert response.final_page_url == final_url
    assert response.blocked_reason == "blocked_static_archive"
    assert response.terminal_evidence.artifact_validation_status == "blocked"
    assert "http_terminal_not_found" in response.terminal_evidence.evidence_labels
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
    caplog,
    run_context,
    external_boundary_mocks_only,
    assert_no_defaulted_required_fields,
) -> None:
    caplog.set_level(logging.INFO, logger=service.logger.name)
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
    terminal_event = next(
        event
        for event in _service_events(caplog)
        if event.get("event") == "browser_report_download_terminal_state_assessed"
    )
    assert terminal_event["fields"]["stabilization_reason"] == "email_submission_not_completed"
    assert terminal_event["fields"]["attempts"] == 0

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

__all__ = [
    "test_download_report_with_browser_use_short_circuits_static_email_gate",
    "test_download_report_with_browser_use_detects_static_provider_email_gate",
    "test_download_report_with_browser_use_classifies_static_email_timeout",
    "test_download_report_with_browser_use_short_circuits_known_access_challenge",
    "test_download_report_with_browser_use_short_circuits_redirected_terminal_not_found",
    "test_download_report_with_browser_use_extracts_email_route_embedded_pdf_link",
    "test_download_report_with_browser_use_fetches_real_pdf_from_wrapper",
    "test_download_report_with_browser_use_returns_email_required_without_address",
    "test_download_report_with_browser_use_returns_encountered_form_fields",
    "test_download_report_with_browser_use_reclassifies_email_message",
    "test_download_report_with_browser_use_treats_generic_success_text_as_email_requested",
    "test_download_report_with_browser_use_requires_semantic_route_summary",
    "test_download_report_with_browser_use_maps_empty_page_to_retryable_load_error",
    "test_download_report_with_browser_use_rejects_conflicting_pdf_metadata",
]
