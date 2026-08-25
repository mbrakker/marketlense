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
    external_boundary_mocks_only.setattr(
        browser_runtime, "import_module", fake_import_module
    )

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
    external_boundary_mocks_only.setattr(
        browser_runtime, "import_module", fake_import_module
    )

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
    assert (
        "remembered_interactive_captcha" in response.terminal_evidence.evidence_labels
    )
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


__all__ = [
    "test_download_report_with_browser_use_short_circuits_static_email_gate",
    "test_download_report_with_browser_use_detects_static_provider_email_gate",
    "test_download_report_with_browser_use_classifies_static_email_timeout",
    "test_download_report_with_browser_use_short_circuits_known_access_challenge",
    "test_download_report_with_browser_use_short_circuits_redirected_terminal_not_found",
]
