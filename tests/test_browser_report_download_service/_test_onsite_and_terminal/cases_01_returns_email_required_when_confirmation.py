# ruff: noqa: F401,F403,F405
from __future__ import annotations

import json

from src.contracts.http_acquisition import HttpAcquisitionResponse
from src.services._browser_report_download._http.adobe_indesign import (
    _adobe_indesign_pages,
    _extract_embedded_adobe_indesign_publication,
    _render_adobe_indesign_capture_html,
    try_embedded_adobe_indesign_capture,
)
from src.services._browser_report_download._http.onsite_capture import (
    _html_for_pdf_rendering,
    _should_try_direct_onsite_capture,
    try_direct_onsite_capture,
)

from ._shared import *  # noqa: F401,F403


def test_html_for_pdf_rendering_removes_external_assets_but_keeps_report_text() -> None:
    rendered = _html_for_pdf_rendering(
        "<html><head><link rel='stylesheet' href='https://cdn.example/style.css'>"
        "<style>@media print { body { color: black; } }</style></head>"
        "<body><article><h1>Report title</h1><p>Report findings.</p>"
        "<img src='https://cdn.example/chart.png'><iframe src='https://example.com/embed'></iframe>"
        "</article></body></html>"
    )

    assert "Report findings." in rendered
    assert "stylesheet" not in rendered
    assert "chart.png" not in rendered
    assert "iframe" not in rendered


def test_extract_embedded_adobe_indesign_publication_requires_public_view_url() -> None:
    publication = _extract_embedded_adobe_indesign_publication(
        """
        <iframe
          src="https://indd.adobe.com/view/9d9a68f6-38a9-4278-b61c-4506b24240b0?allowFullscreen=true"
        ></iframe>
        """
    )

    assert publication == "9d9a68f6-38a9-4278-b61c-4506b24240b0"
    assert _extract_embedded_adobe_indesign_publication(
        '<iframe src="https://example.com/view/9d9a68f6-38a9-4278-b61c-4506b24240b0"></iframe>'
    ) is None
    assert _extract_embedded_adobe_indesign_publication(
        '<a href="https://indd.adobe.com/view/9d9a68f6-38a9-4278-b61c-4506b24240b0">Report</a>'
    ) is None
    assert _extract_embedded_adobe_indesign_publication(
        '<script>"https://indd.adobe.com/view/9d9a68f6-38a9-4278-b61c-4506b24240b0"</script>'
    ) is None


def test_adobe_indesign_capture_html_preserves_published_page_text() -> None:
    pages = _adobe_indesign_pages(
        json.dumps(
            {
                "framesData": [
                    {
                        "pageNo": 1,
                        "frameData": [
                            {
                                "textBoundary": [
                                    [["DIGITAL 2025", [0, 12]]],
                                    [["GLOBAL OVERVIEW REPORT", [0, 24]]],
                                ]
                            }
                        ],
                    },
                    {
                        "pageNo": 2,
                        "frameData": [
                            {
                                "textBoundary": [
                                    [["Published report findings", [0, 12]]]
                                ]
                            }
                        ],
                    },
                ]
            }
        )
    )

    capture_html = _render_adobe_indesign_capture_html(pages)

    assert pages == [
        (1, ["DIGITAL 2025 GLOBAL OVERVIEW REPORT"]),
        (2, ["Published report findings"]),
    ]
    assert 'data-page-number="1"' in capture_html
    assert "Published report findings" in capture_html


def test_adobe_indesign_capture_counts_distinct_published_pages() -> None:
    pages = _adobe_indesign_pages(
        json.dumps(
            {
                "framesData": [
                    {
                        "pageNo": 1,
                        "frameData": [{"textBoundary": [["first frame"]]}],
                    },
                    {
                        "pageNo": 1,
                        "frameData": [{"textBoundary": [["second frame"]]}],
                    },
                ]
            }
        )
    )

    assert pages == [(1, ["first frame second frame"])]


def test_embedded_adobe_indesign_capture_requires_complete_public_content(
    tmp_path: Path,
    run_context,
) -> None:
    publication_id = "9d9a68f6-38a9-4278-b61c-4506b24240b0"
    content = json.dumps(
        {
            "framesData": [
                {
                    "pageNo": page_number,
                    "frameData": [
                        {"textBoundary": [["Verified report text " * 80]]}
                    ],
                }
                for page_number in (1, 2)
            ]
        }
    )

    def execute(*, request, ctx, requests_module):
        body = '"VERSION_PREFIX":"cukv"' if request.purpose.endswith("viewer") else content
        return HttpAcquisitionResponse(
            schema_version="1.0",
            purpose=request.purpose,
            method=request.method,
            request_url=request.url,
            final_url=request.url,
            status_code=200,
            headers={"content-type": "application/json"},
            content_type="application/json",
            text_body=body,
        )

    result = try_embedded_adobe_indesign_capture(
        request=BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://publisher.example/report",
            settings=_settings(tmp_path),
        ),
        ctx=run_context,
        normalized_url="https://publisher.example/report",
        download_dir=tmp_path,
        source_page_url="https://publisher.example/report",
        source_page_html=(
            f'<iframe src="https://indd.adobe.com/view/{publication_id}"></iframe>'
        ),
        http_acquisition_executor=execute,
    )

    assert result is not None
    assert result.outcome == "captured"
    assert result.onsite_page_count == 2
    assert (tmp_path / "adobe_indesign_capture.html").is_file()
    assert (tmp_path / "adobe_indesign_content.json").is_file()


def test_report_detail_without_route_hint_is_eligible_for_public_embed_capture(
    tmp_path: Path,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/reports/digital-overview-report",
        settings=_settings(tmp_path),
    )

    assert _should_try_direct_onsite_capture(request) is True


def test_unhinted_report_detail_falls_back_when_public_embed_is_unverified(
    tmp_path: Path,
    run_context,
) -> None:
    request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url="https://publisher.example/reports/digital-overview-report",
        settings=_settings(tmp_path),
    )

    def execute(*, request, ctx, requests_module):
        return HttpAcquisitionResponse(
            schema_version="1.0",
            purpose=request.purpose,
            method=request.method,
            request_url=request.url,
            final_url=request.url,
            status_code=200,
            headers={"content-type": "text/html"},
            content_type="text/html",
            text_body=(
                "<html><title>Report</title><article>"
                f"{'report findings ' * 100}</article></html>"
            ),
        )

    result = try_direct_onsite_capture(
        request=request,
        ctx=run_context,
        normalized_url=request.url,
        download_dir=tmp_path,
        http_acquisition_executor=execute,
    )

    assert result is None

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
    assert response.onsite_capture_format == "rendered_onsite_pdf"
    assert capture_path.read_bytes().startswith(b"%PDF-")
    assert response.terminal_evidence.html_snapshot_path
    assert "Long body text." in Path(
        response.terminal_evidence.html_snapshot_path
    ).read_text(encoding="utf-8")
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
    assert response.onsite_capture_format == "rendered_onsite_pdf"
    assert capture_path.read_bytes().startswith(b"%PDF-")
    assert "Operational insight." in Path(
        response.terminal_evidence.html_snapshot_path
    ).read_text(encoding="utf-8")
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
    assert response.onsite_capture_format == "rendered_onsite_pdf"
    assert Path(response.onsite_capture_path).read_bytes().startswith(b"%PDF-")
    assert "Population and connectivity insight." in Path(
        response.terminal_evidence.html_snapshot_path
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
    assert response.onsite_capture_format == "rendered_onsite_pdf"
    assert (
        Path(response.onsite_capture_path).read_bytes().startswith(b"%PDF-")
    )
    assert (
        Path(response.terminal_evidence.html_snapshot_path)
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
    assert response.onsite_capture_format == "rendered_onsite_pdf"
    assert capture_path.read_bytes().startswith(b"%PDF-")
    assert "Market adoption insight." in Path(
        response.terminal_evidence.html_snapshot_path
    ).read_text(encoding="utf-8")

def test_download_report_with_browser_use_recovers_email_form_report_detail_to_direct_onsite_capture(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        url = "https://data.example/reports/2026-threats-report"
        text = (
            "<html><head><title>2026 Threats Report</title></head>"
            "<body><form><input type='search' name='q' /></form>"
            "<main><h1>2026 Threats Report</h1>"
            "<h2>Executive summary</h2>"
            "<p>This page contains the complete report findings.</p>"
            "<h2>Threat analysis</h2>"
            "<p>" + ("Market security insight. " * 180) + "</p>"
            "</main></body></html>"
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
                "browser runtime should not start for report detail onsite capture"
            )
        ),
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://data.example/reports/2026-threats-report",
            settings=_settings(tmp_path),
            route_kind_hint="email_delivery",
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.route_family == "browser_onsite_report"
    assert response.outcome == "captured"
    assert response.browser_had_structured_result is False
    assert response.onsite_capture_path is not None
    assert response.onsite_capture_format == "rendered_onsite_pdf"
    assert Path(response.onsite_capture_path).read_bytes().startswith(b"%PDF-")
    assert "Market security insight." in Path(
        response.terminal_evidence.html_snapshot_path
    ).read_text(encoding="utf-8")

def test_download_report_with_browser_use_keeps_email_form_route_when_static_lead_form_exists(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "text/html; charset=utf-8"}
        url = "https://data.example/reports/2026-gated-report"
        text = (
            "<html><head><title>2026 Gated Report</title></head>"
            "<body><article><h1>2026 Gated Report</h1>"
            "<p>" + ("Report preview. " * 100) + "</p>"
            "</article><form><input name='email' />"
            "<input name='company' /><select name='country'></select>"
            "<button type='submit'>Download report</button></form></body></html>"
        )

    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary="Open the report form and submit the configured email.",
        create_pdf=False,
        email_submission_completed=False,
    )
    external_boundary_mocks_only.setattr(
        http_runtime.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://data.example/reports/2026-gated-report",
            settings=_settings(tmp_path),
            route_kind_hint="email_delivery",
            route_family_hint="browser_email_form",
        ),
        run_context,
    )

    assert response.route_kind == "email_delivery"
    assert response.route_family == "browser_email_form"
    assert response.outcome == "email_required"
    assert response.onsite_capture_path is None

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

def test_download_report_with_browser_use_prefers_complete_onsite_capture_over_optional_enum_blocker(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="email_delivery",
        route_summary=(
            "Captured the report body, then saw an optional download form with a "
            "company-size dropdown blocker."
        ),
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class OnsiteWithOptionalEnumBlockerAgent(original_runtime):
        def run_sync(self, max_steps: int):
            payload = json.loads(super().run_sync(max_steps).final_result())
            self.browser.url = "https://example.com/research/workforce-report"
            self.browser.title = "Workforce Report"
            self.browser.html = (
                "<html><body><article><h1>Workforce Report</h1>"
                "<p>This page contains the complete report findings.</p>"
                "<p>" + ("Benchmark research detail. " * 180) + "</p>"
                "</article><form><select name='company_size'></select></form>"
                "</body></html>"
            )
            payload["route_kind"] = "email_delivery"
            payload["route_family"] = "browser_onsite_report"
            payload["encountered_form_fields"] = [
                "Work Email",
                "Company size",
            ]
            payload["blocked_reason"] = "blocked_unknown_required_enum"
            payload["blocked_reason_detail"] = (
                "The optional Company size select had no matching configured value."
            )
            payload["terminal_text_excerpt"] = (
                "Workforce Report. This page contains the complete report findings. "
                + ("Benchmark research detail. " * 80)
            )
            payload["route_steps"] = [
                {
                    "index": 0,
                    "action": "capture",
                    "target_text": "report article",
                    "target_role": "onsite report body",
                    "target_url": "https://example.com/research/workforce-report",
                    "result": "Captured the complete on-page report body.",
                    "expected_evidence": ["artifact", "dom_hash", "screenshot"],
                    "observed_evidence": ["artifact", "dom_hash", "screenshot"],
                    "verification_status": "verified",
                }
            ]

            class OnsiteWithOptionalEnumBlockerHistory:
                def final_result(self_nonlocal) -> str:
                    return json.dumps(payload)

            return OnsiteWithOptionalEnumBlockerHistory()

    runtime.Agent = OnsiteWithOptionalEnumBlockerAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    response = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/research/workforce-report",
            settings=_settings(tmp_path),
            route_family_hint="browser_onsite_report",
        ),
        run_context,
    )

    assert response.route_kind == "onsite_report"
    assert response.outcome == "captured"
    assert response.blocked_reason is None
    assert response.onsite_capture_path is not None
    assert Path(str(response.onsite_capture_path)).exists()

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

__all__ = [
    "test_html_for_pdf_rendering_removes_external_assets_but_keeps_report_text",
    "test_adobe_indesign_capture_counts_distinct_published_pages",
    "test_embedded_adobe_indesign_capture_requires_complete_public_content",
    "test_extract_embedded_adobe_indesign_publication_requires_public_view_url",
    "test_report_detail_without_route_hint_is_eligible_for_public_embed_capture",
    "test_unhinted_report_detail_falls_back_when_public_embed_is_unverified",
    "test_adobe_indesign_capture_html_preserves_published_page_text",
    "test_download_report_with_browser_use_returns_email_required_when_confirmation_is_missing",
    "test_download_report_with_browser_use_short_circuits_remembered_onsite_extract_to_direct_html_capture",
    "test_download_report_with_browser_use_short_circuits_planned_onsite_candidate_to_direct_html_capture",
    "test_download_report_with_browser_use_short_circuits_planned_extract_step_without_candidate_trace",
    "test_download_report_with_browser_use_directly_captures_route_confirmed_non_article_longread",
    "test_download_report_with_browser_use_probes_report_detail_candidate_for_direct_onsite_capture",
    "test_download_report_with_browser_use_recovers_email_form_report_detail_to_direct_onsite_capture",
    "test_download_report_with_browser_use_keeps_email_form_route_when_static_lead_form_exists",
    "test_download_report_with_browser_use_blocks_mixed_hub_direct_onsite_recovery",
    "test_download_report_with_browser_use_prefers_form_evidence_over_onsite_hint",
    "test_download_report_with_browser_use_keeps_explicit_onsite_classification_when_optional_form_fields_were_seen",
    "test_download_report_with_browser_use_prefers_complete_onsite_capture_over_optional_enum_blocker",
    "test_download_report_with_browser_use_salvages_empty_result_to_onsite_capture",
    "test_download_report_with_browser_use_records_terminal_snapshot_and_document_urls",
]
