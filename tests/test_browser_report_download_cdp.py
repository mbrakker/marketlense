from __future__ import annotations

import base64
import json
import logging
from pathlib import Path
from typing import Any

import pytest

from src.services._browser_report_download.cdp import (
    BrowserDownloadCdpCallResult,
    call_browser_download_cdp,
    capture_terminal_screenshot_via_cdp,
    collect_terminal_network_entries_via_cdp,
    get_browser_download_cdp_allowlist,
)
from src.utils.errors import AppError


class FakeCdpClient:
    def __init__(self, responses: dict[str, dict[str, Any]] | None = None) -> None:
        self.responses = responses or {}
        self.calls: list[dict[str, Any]] = []

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
        return response


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
        "Page.captureScreenshot": "Persist terminal screenshot evidence when browser-use screenshot hooks fail.",
        "Target.getTargetInfo": "Inspect focused target identity for diagnostics and logging.",
        "Target.getTargets": "Find a real page target when browser-use session state is unavailable.",
        "Target.attachToTarget": "Create a transient evidence-only CDP session for an allowlisted read.",
        "Target.detachFromTarget": "Clean up a transient evidence-only CDP session.",
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
            method="Input.dispatchMouseEvent",
            params={"type": "mousePressed"},
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
