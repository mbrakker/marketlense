# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

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

__all__ = [
    "test_download_report_with_browser_use_infers_bounded_incomplete_for_weak_onsite_capture",
    "test_download_report_with_browser_use_auto_captures_onsite_html_when_agent_omits_capture_path",
    "test_download_report_with_browser_use_prints_printable_onsite_report_to_pdf",
    "test_download_report_with_browser_use_rejects_print_pdf_for_generic_printable_page",
    "test_download_report_with_browser_use_records_terminal_dialog_evidence",
    "test_download_report_with_browser_use_marks_paginated_onsite_capture_partial_without_full_traversal",
]
