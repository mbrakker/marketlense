from __future__ import annotations

import asyncio
import base64
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from src.services._browser_report_download.cdp import (
    BrowserDownloadCdpCallResult,
    call_browser_download_cdp,
    capture_print_pdf_via_cdp_async,
    capture_print_pdf_via_cdp,
    capture_terminal_screenshot_via_cdp,
    collect_terminal_dialog_evidence_via_cdp,
    collect_terminal_network_entries_via_cdp,
    ensure_browser_download_target_hygiene_via_cdp,
    get_browser_download_cdp_allowlist,
    open_browser_download_target_async,
    wait_for_browser_document_text_async,
    wait_for_browser_download_target_async,
)
from src.utils.errors import AppError


class FakeCdpClient:
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []
        self.event_handlers: dict[str, Any] = {}
        self.dialog_events: list[dict[str, Any]] = []
        self.register = FakeCdpRegistration(self)
        self._event_registry = FakeEventRegistry(self)

    async def send_raw(
        self,
        method: str,
        params: dict[str, Any] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "method": method,
                "params": params or {},
                "session_id": session_id or "",
            }
        )
        if method not in self.responses:
            raise RuntimeError(f"unhandled CDP method: {method}")
        response = self.responses[method]
        if "raise" in response:
            raise RuntimeError(str(response["raise"]))
        if method == "Page.enable":
            for event in self.dialog_events:
                handler = self.event_handlers.get("Page.javascriptDialogOpening")
                if callable(handler):
                    result = handler(event, session_id)
                    if hasattr(result, "__await__"):
                        await result
        return response


class FakeEventRegistry:
    def __init__(self, client: FakeCdpClient) -> None:
        self.client = client

    def unregister(self, method: str) -> None:
        self.client.event_handlers.pop(method, None)


class FakePageRegistration:
    def __init__(self, client: FakeCdpClient) -> None:
        self.client = client

    def javascriptDialogOpening(self, callback: Any) -> None:
        self.client.event_handlers["Page.javascriptDialogOpening"] = callback


class FakeCdpRegistration:
    def __init__(self, client: FakeCdpClient) -> None:
        self.Page = FakePageRegistration(client)


class FakeCdpSession:
    def __init__(self, client: FakeCdpClient) -> None:
        self.cdp_client = client
        self.target_id = "target-123"
        self.session_id = "session-456"


class FakeBrowser:
    def __init__(self, client: FakeCdpClient) -> None:
        self._session = FakeCdpSession(client)

    async def get_or_create_cdp_session(
        self,
        target_id: str | None = None,
        focus: bool = False,
    ) -> FakeCdpSession:
        return self._session


def _log_payloads(caplog: pytest.LogCaptureFixture) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for record in caplog.records:
        try:
            payloads.append(json.loads(record.message))
        except json.JSONDecodeError:
            continue
    return payloads


def test_browser_download_cdp_allowlist_documents_supported_escape_hatch() -> None:
    allowlist = get_browser_download_cdp_allowlist()

    assert allowlist == {
        "Runtime.evaluate": "Read bounded terminal page state for evidence capture.",
        "Page.enable": "Subscribe to bounded terminal Page events such as JavaScript dialogs.",
        "Page.captureScreenshot": "Persist terminal screenshot evidence when browser-use screenshot hooks fail.",
        "Page.printToPDF": "Persist browser-rendered PDF captures for printable on-site reports.",
        "Page.getLayoutMetrics": "Reject zero-size or stale terminal targets before evidence capture.",
        "Page.handleJavaScriptDialog": "Handle terminal JavaScript dialogs according to browser-download policy.",
        "Target.getTargetInfo": "Inspect focused target identity for diagnostics and logging.",
        "Target.getTargets": "Find a real page target when browser-use session state is unavailable.",
        "Target.attachToTarget": "Create a transient evidence-only CDP session for an allowlisted read.",
        "Target.createTarget": "Open an exact public report target for a deterministic browser route.",
        "Target.detachFromTarget": "Clean up a transient evidence-only CDP session.",
        "Target.activateTarget": "Focus a verified user-facing target when headed evidence needs it.",
    }


def test_browser_download_cdp_call_logs_context_and_returns_contract(
    caplog: pytest.LogCaptureFixture,
    run_context,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    client = FakeCdpClient(
        {
            "Runtime.evaluate": {
                "result": {"type": "string", "value": "ready"},
            }
        }
    )
    browser = FakeBrowser(client)

    with caplog.at_level(
        logging.INFO,
        logger="market_lense.browser_report_download_service.cdp",
    ):
        result = call_browser_download_cdp(
            browser=browser,
            method="Runtime.evaluate",
            params={"expression": "document.title", "returnByValue": True},
            ctx=run_context,
            normalized_url="https://example.com/report",
            required=True,
        )

    assert isinstance(result, BrowserDownloadCdpCallResult)
    assert_no_defaulted_required_fields(result)
    assert result.status == "ok"
    assert result.target_id == "target-123"
    assert result.session_id == "session-456"
    assert client.calls == [
        {
            "method": "Runtime.evaluate",
            "params": {"expression": "document.title", "returnByValue": True},
            "session_id": "session-456",
        }
    ]
    payloads = _log_payloads(caplog)
    assert_logs_have_required_fields(payloads)
    completed = [
        payload
        for payload in payloads
        if payload.get("event") == "browser_report_download_cdp_call_completed"
    ][-1]
    assert completed["fields"]["method"] == "Runtime.evaluate"
    assert completed["fields"]["result_status"] == "ok"
    assert completed["fields"]["target_id"] == "target-123"
    assert completed["fields"]["session_id"] == "session-456"


def test_browser_download_cdp_required_failure_surfaces_app_error(
    caplog: pytest.LogCaptureFixture,
    run_context,
    assert_app_error,
    assert_logs_have_required_fields,
) -> None:
    browser = FakeBrowser(
        FakeCdpClient({"Runtime.evaluate": {"raise": "cdp target detached"}})
    )

    with caplog.at_level(
        logging.INFO,
        logger="market_lense.browser_report_download_service.cdp",
    ):
        with pytest.raises(AppError) as exc_info:
            call_browser_download_cdp(
                browser=browser,
                method="Runtime.evaluate",
                params={"expression": "document.title", "returnByValue": True},
                ctx=run_context,
                normalized_url="https://example.com/report",
                required=True,
            )

    assert_app_error(
        exc_info.value,
        code="browser_download_cdp_call_failed",
        retryable=True,
    )
    payloads = _log_payloads(caplog)
    assert_logs_have_required_fields(payloads)
    failed = [
        payload
        for payload in payloads
        if payload.get("event") == "browser_report_download_cdp_call_failed"
    ][-1]
    assert failed["fields"]["method"] == "Runtime.evaluate"
    assert failed["fields"]["result_status"] == "failed"


def test_browser_download_cdp_rejects_unapproved_methods(
    run_context,
    assert_app_error,
) -> None:
    browser = FakeBrowser(FakeCdpClient())

    with pytest.raises(AppError) as exc_info:
        call_browser_download_cdp(
            browser=browser,
            method="Browser.close",
            params={},
            ctx=run_context,
            normalized_url="https://example.com/report",
            required=True,
        )

    assert_app_error(
        exc_info.value,
        code="browser_download_cdp_method_not_allowed",
        retryable=False,
    )


def test_browser_download_cdp_attaches_transient_session_when_browser_session_missing(
    run_context,
) -> None:
    client = FakeCdpClient(
        {
            "Target.getTargets": {
                "targetInfos": [
                    {
                        "targetId": "internal-target",
                        "type": "page",
                        "url": "chrome://new-tab-page",
                    },
                    {
                        "targetId": "real-target",
                        "type": "page",
                        "url": "https://example.com/report",
                    },
                ]
            },
            "Target.attachToTarget": {"sessionId": "transient-session"},
            "Runtime.evaluate": {
                "result": {"type": "string", "value": "ready"},
            },
            "Target.detachFromTarget": {},
        }
    )

    class RootOnlyBrowser:
        cdp_client = client

    result = call_browser_download_cdp(
        browser=RootOnlyBrowser(),
        method="Runtime.evaluate",
        params={"expression": "document.title", "returnByValue": True},
        ctx=run_context,
        normalized_url="https://example.com/report",
        required=True,
    )

    assert result.status == "ok"
    assert result.target_id == "real-target"
    assert result.session_id == "transient-session"
    assert [call["method"] for call in client.calls] == [
        "Target.getTargets",
        "Target.attachToTarget",
        "Runtime.evaluate",
        "Target.detachFromTarget",
    ]
    assert client.calls[2]["session_id"] == "transient-session"


def test_browser_download_cdp_collects_terminal_network_entries(run_context) -> None:
    client = FakeCdpClient(
        {
            "Runtime.evaluate": {
                "result": {
                    "type": "object",
                    "value": [
                        {
                            "url": "https://example.com/report.pdf",
                            "initiator_type": "navigation",
                        }
                    ],
                }
            }
        }
    )

    entries = collect_terminal_network_entries_via_cdp(
        browser=FakeBrowser(client),
        ctx=run_context,
        normalized_url="https://example.com/report",
        required=True,
    )

    assert entries == [
        {
            "url": "https://example.com/report.pdf",
            "initiator_type": "navigation",
        }
    ]


def test_browser_download_target_hygiene_filters_internal_targets_and_activates_real_page(
    run_context,
) -> None:
    client = FakeCdpClient(
        {
            "Target.getTargets": {
                "targetInfos": [
                    {
                        "targetId": "omnibox-target",
                        "type": "page",
                        "url": "chrome://omnibox-popup",
                    },
                    {
                        "targetId": "blank-target",
                        "type": "page",
                        "url": "about:blank",
                    },
                    {
                        "targetId": "real-target",
                        "type": "page",
                        "url": "https://example.com/report",
                        "title": "Example report",
                    },
                ]
            },
            "Target.attachToTarget": {"sessionId": "real-session"},
            "Page.getLayoutMetrics": {
                "cssVisualViewport": {"clientWidth": 1280, "clientHeight": 720}
            },
            "Target.activateTarget": {},
            "Target.detachFromTarget": {},
        }
    )

    class RootOnlyBrowser:
        cdp_client = client

    result = ensure_browser_download_target_hygiene_via_cdp(
        browser=RootOnlyBrowser(),
        ctx=run_context,
        normalized_url="https://example.com/report",
        activate=True,
    )

    assert result.status == "ok"
    assert result.selected_target_id == "real-target"
    assert result.selected_url == "https://example.com/report"
    assert result.selected_title == "Example report"
    assert result.viewport_width == 1280
    assert result.viewport_height == 720
    assert result.activated is True
    assert [call["method"] for call in client.calls] == [
        "Target.getTargets",
        "Target.attachToTarget",
        "Page.getLayoutMetrics",
        "Target.activateTarget",
        "Target.detachFromTarget",
    ]


def test_browser_download_target_hygiene_rejects_zero_size_target(
    run_context,
) -> None:
    client = FakeCdpClient(
        {
            "Target.getTargets": {
                "targetInfos": [
                    {
                        "targetId": "zero-target",
                        "type": "page",
                        "url": "https://example.com/report",
                        "title": "Example report",
                    },
                ]
            },
            "Target.attachToTarget": {"sessionId": "zero-session"},
            "Page.getLayoutMetrics": {
                "cssVisualViewport": {"clientWidth": 0, "clientHeight": 0}
            },
            "Target.detachFromTarget": {},
        }
    )

    class RootOnlyBrowser:
        cdp_client = client

    result = ensure_browser_download_target_hygiene_via_cdp(
        browser=RootOnlyBrowser(),
        ctx=run_context,
        normalized_url="https://example.com/report",
        target_url="https://example.com/report",
        activate=False,
    )

    assert result.status == "rejected"
    assert result.selected_target_id == "zero-target"
    assert result.reason == "selected page target has zero-size viewport"
    assert result.viewport_width == 0
    assert result.viewport_height == 0


def test_browser_download_target_hygiene_reports_reattached_focus(
    run_context,
) -> None:
    client = FakeCdpClient(
        {
            "Target.getTargets": {
                "targetInfos": [
                    {
                        "targetId": "real-target",
                        "type": "page",
                        "url": "https://example.com/report",
                        "title": "Example report",
                    },
                ]
            },
            "Page.getLayoutMetrics": {
                "cssVisualViewport": {"clientWidth": 1024, "clientHeight": 768}
            },
        }
    )

    class FocusedBrowser(FakeBrowser):
        agent_focus_target_id = "stale-target"

        def __init__(self, target_client: FakeCdpClient) -> None:
            super().__init__(target_client)
            self.cdp_client = target_client

    result = ensure_browser_download_target_hygiene_via_cdp(
        browser=FocusedBrowser(client),
        ctx=run_context,
        normalized_url="https://example.com/report",
        target_url="https://example.com/report",
        activate=False,
    )

    assert result.status == "reattached"
    assert result.selected_target_id == "real-target"
    assert "differs from previous browser-use focus" in result.reason


def test_browser_download_cdp_collects_and_accepts_alert_dialog(
    run_context,
) -> None:
    client = FakeCdpClient(
        {
            "Page.enable": {},
            "Page.handleJavaScriptDialog": {},
        }
    )
    client.dialog_events = [
        {
            "url": "https://example.com/report",
            "type": "alert",
            "message": "Report export is ready.",
        }
    ]

    evidence = collect_terminal_dialog_evidence_via_cdp(
        browser=FakeBrowser(client),
        ctx=run_context,
        normalized_url="https://example.com/report",
    )

    assert len(evidence) == 1
    assert evidence[0].dialog_type == "alert"
    assert evidence[0].message == "Report export is ready."
    assert evidence[0].action_taken == "accepted"
    assert evidence[0].validation_status == "handled"
    assert client.calls[-1]["method"] == "Page.handleJavaScriptDialog"
    assert client.calls[-1]["params"] == {"accept": True}


def test_browser_download_cdp_dismisses_confirm_dialog_by_policy(
    run_context,
) -> None:
    client = FakeCdpClient(
        {
            "Page.enable": {},
            "Page.handleJavaScriptDialog": {},
        }
    )
    client.dialog_events = [
        {
            "url": "https://example.com/report",
            "type": "confirm",
            "message": "Leave this report page?",
        }
    ]

    evidence = collect_terminal_dialog_evidence_via_cdp(
        browser=FakeBrowser(client),
        ctx=run_context,
        normalized_url="https://example.com/report",
    )

    assert evidence[0].dialog_type == "confirm"
    assert evidence[0].action_taken == "dismissed_confirm_by_policy"
    assert evidence[0].validation_status == "policy_rejected"
    assert client.calls[-1]["params"] == {"accept": False}


def test_browser_download_cdp_accepts_beforeunload_only_for_teardown(
    run_context,
) -> None:
    client = FakeCdpClient(
        {
            "Page.enable": {},
            "Page.handleJavaScriptDialog": {},
        }
    )
    client.dialog_events = [
        {
            "url": "https://example.com/report",
            "type": "beforeunload",
            "message": "Changes you made may not be saved.",
        }
    ]

    evidence = collect_terminal_dialog_evidence_via_cdp(
        browser=FakeBrowser(client),
        ctx=run_context,
        normalized_url="https://example.com/report",
        allow_beforeunload=True,
    )

    assert evidence[0].dialog_type == "beforeunload"
    assert evidence[0].action_taken == "accepted_beforeunload_for_teardown"
    assert evidence[0].validation_status == "handled"
    assert client.calls[-1]["params"] == {"accept": True}


def test_browser_download_cdp_writes_terminal_screenshot(
    tmp_path: Path,
    run_context,
) -> None:
    image_bytes = b"\x89PNG\r\n\x1a\n"
    client = FakeCdpClient(
        {
            "Page.captureScreenshot": {
                "data": base64.b64encode(image_bytes).decode("ascii")
            }
        }
    )
    screenshot_path = tmp_path / "terminal_screenshot.png"

    captured = capture_terminal_screenshot_via_cdp(
        browser=FakeBrowser(client),
        screenshot_path=screenshot_path,
        ctx=run_context,
        normalized_url="https://example.com/report",
        required=True,
    )

    assert captured is True
    assert screenshot_path.read_bytes() == image_bytes


def test_browser_download_cdp_writes_print_pdf_capture(
    tmp_path: Path,
    run_context,
) -> None:
    pdf_bytes = b"%PDF-1.7 browser-rendered"
    client = FakeCdpClient(
        {
            "Page.printToPDF": {
                "data": base64.b64encode(pdf_bytes).decode("ascii")
            }
        }
    )
    pdf_path = tmp_path / "rendered.pdf"

    captured = capture_print_pdf_via_cdp(
        browser=FakeBrowser(client),
        pdf_path=pdf_path,
        ctx=run_context,
        normalized_url="https://example.com/report",
        required=True,
    )

    assert captured is True
    assert pdf_path.read_bytes() == pdf_bytes
    assert client.calls[0]["method"] == "Page.printToPDF"
    assert client.calls[0]["params"]["printBackground"] is True


def test_browser_download_cdp_print_pdf_bridges_from_browser_event_loop(
    tmp_path: Path,
    run_context,
) -> None:
    """A deterministic route must not block the CDP receive loop it depends on."""

    async def run_capture() -> tuple[bool, bytes]:
        pdf_bytes = b"%PDF-1.7 browser-event-loop"
        client = FakeCdpClient(
            {
                "Page.printToPDF": {
                    "data": base64.b64encode(pdf_bytes).decode("ascii")
                }
            }
        )
        client._message_handler_task = asyncio.current_task()
        pdf_path = tmp_path / "event-loop-rendered.pdf"
        captured = await asyncio.to_thread(
            capture_print_pdf_via_cdp,
            browser=FakeBrowser(client),
            pdf_path=pdf_path,
            ctx=run_context,
            normalized_url="https://example.com/report",
            required=True,
        )
        return captured, pdf_path.read_bytes()

    captured, written = asyncio.run(run_capture())

    assert captured is True
    assert written == b"%PDF-1.7 browser-event-loop"


def test_browser_download_cdp_async_print_pdf_uses_the_active_browser_loop(
    tmp_path: Path,
    run_context,
) -> None:
    pdf_bytes = b"%PDF-1.7 browser-active-loop"
    client = FakeCdpClient(
        {
            "Target.getTargets": {
                "targetInfos": [
                    {
                        "targetId": "report-target",
                        "type": "page",
                        "url": "https://example.com/report",
                    }
                ]
            },
            "Target.attachToTarget": {"sessionId": "report-session"},
            "Page.printToPDF": {
                "data": base64.b64encode(pdf_bytes).decode("ascii")
            },
            "Target.detachFromTarget": {},
        }
    )

    class RootOnlyBrowser:
        cdp_client = client

    pdf_path = tmp_path / "active-loop-rendered.pdf"
    captured = asyncio.run(
        capture_print_pdf_via_cdp_async(
            browser=RootOnlyBrowser(),
            pdf_path=pdf_path,
            ctx=run_context,
            normalized_url="https://example.com/report",
            target_url="https://example.com/report",
        )
    )

    assert captured is True
    assert pdf_path.read_bytes() == pdf_bytes
    assert [call["method"] for call in client.calls] == [
        "Target.getTargets",
        "Target.attachToTarget",
        "Page.printToPDF",
        "Target.detachFromTarget",
    ]


def test_browser_download_cdp_async_waits_for_the_exact_page_target() -> None:
    client = FakeCdpClient(
        {
            "Target.getTargets": {
                "targetInfos": [
                    {
                        "targetId": "report-target",
                        "type": "page",
                        "url": "https://example.com/report",
                    }
                ]
            }
        }
    )

    class RootOnlyBrowser:
        cdp_client = client

    ready = asyncio.run(
        wait_for_browser_download_target_async(
            browser=RootOnlyBrowser(),
            target_url="https://example.com/report",
            timeout_seconds=0.01,
        )
    )

    assert ready is True
    assert [call["method"] for call in client.calls] == ["Target.getTargets"]


def test_browser_download_cdp_async_opens_the_exact_page_target() -> None:
    client = FakeCdpClient(
        {
            "Target.createTarget": {"targetId": "report-target"},
            "Target.getTargets": {
                "targetInfos": [
                    {
                        "targetId": "report-target",
                        "type": "page",
                        "url": "https://example.com/report",
                    }
                ]
            },
        }
    )

    class RootOnlyBrowser:
        cdp_client = client

    opened = asyncio.run(
        open_browser_download_target_async(
            browser=RootOnlyBrowser(),
            target_url="https://example.com/report",
            timeout_seconds=0.01,
        )
    )

    assert opened is True
    assert [call["method"] for call in client.calls] == [
        "Target.createTarget",
        "Target.getTargets",
    ]


def test_browser_download_cdp_async_waits_for_expected_document_text() -> None:
    client = FakeCdpClient(
        {
            "Target.getTargets": {
                "targetInfos": [
                    {
                        "targetId": "report-target",
                        "type": "page",
                        "url": "https://example.com/report",
                    }
                ]
            },
            "Target.attachToTarget": {"sessionId": "report-session"},
            "Runtime.evaluate": {
                "result": {
                    "value": {
                        "readyState": "complete",
                        "title": "Example report",
                        "bodyText": "Expected report heading",
                    }
                }
            },
            "Target.detachFromTarget": {},
        }
    )

    class RootOnlyBrowser:
        cdp_client = client

    ready = asyncio.run(
        wait_for_browser_document_text_async(
            browser=RootOnlyBrowser(),
            target_url="https://example.com/report",
            expected_text="Expected report heading",
            timeout_seconds=0.01,
        )
    )

    assert ready is True
    assert [call["method"] for call in client.calls] == [
        "Target.getTargets",
        "Target.attachToTarget",
        "Runtime.evaluate",
        "Target.detachFromTarget",
    ]


def test_browser_download_cdp_print_pdf_uses_matching_target_url(
    tmp_path: Path,
    run_context,
) -> None:
    pdf_bytes = b"%PDF-1.7 report page"
    client = FakeCdpClient(
        {
            "Target.getTargets": {
                "targetInfos": [
                    {
                        "targetId": "report-target",
                        "type": "page",
                        "url": "https://example.com/report",
                    },
                    {
                        "targetId": "startup-target",
                        "type": "page",
                        "url": "https://example.com/browser-use/start",
                    },
                ]
            },
            "Target.attachToTarget": {"sessionId": "report-session"},
            "Page.printToPDF": {
                "data": base64.b64encode(pdf_bytes).decode("ascii")
            },
            "Target.detachFromTarget": {},
        }
    )

    class RootOnlyBrowser:
        cdp_client = client

    pdf_path = tmp_path / "rendered.pdf"

    captured = capture_print_pdf_via_cdp(
        browser=RootOnlyBrowser(),
        pdf_path=pdf_path,
        ctx=run_context,
        normalized_url="https://example.com/report",
        required=True,
        target_url="https://example.com/report#section",
    )

    assert captured is True
    assert pdf_path.read_bytes() == pdf_bytes
    assert [call["method"] for call in client.calls] == [
        "Target.getTargets",
        "Target.attachToTarget",
        "Page.printToPDF",
        "Target.detachFromTarget",
    ]
    assert client.calls[1]["params"]["targetId"] == "report-target"
    assert client.calls[2]["session_id"] == "report-session"


def test_browser_download_cdp_print_pdf_rejects_unmatched_target_url(
    tmp_path: Path,
    run_context,
) -> None:
    client = FakeCdpClient(
        {
            "Target.getTargets": {
                "targetInfos": [
                    {
                        "targetId": "startup-target",
                        "type": "page",
                        "url": "https://example.com/browser-use/start",
                    },
                ]
            },
        }
    )

    class RootOnlyBrowser:
        cdp_client = client

    pdf_path = tmp_path / "rendered.pdf"

    captured = capture_print_pdf_via_cdp(
        browser=RootOnlyBrowser(),
        pdf_path=pdf_path,
        ctx=run_context,
        normalized_url="https://example.com/report",
        required=False,
        target_url="https://example.com/report",
    )

    assert captured is False
    assert not pdf_path.exists()
    assert [call["method"] for call in client.calls] == ["Target.getTargets"]
