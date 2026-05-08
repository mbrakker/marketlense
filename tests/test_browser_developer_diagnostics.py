from __future__ import annotations

import json
import logging
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from src.contracts.browser_download import BrowserDeveloperDiagnosticsRequest
from src.services.browser_report_download_service import (
    run_browser_developer_diagnostics,
)


class FakeCdpClient:
    def __init__(self) -> None:
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
        if method == "Target.getTargets":
            return {
                "targetInfos": [
                    {
                        "targetId": "doctor-target",
                        "type": "page",
                        "url": "https://example.com/browser-doctor",
                        "title": "Browser Doctor",
                    }
                ]
            }
        if method == "Target.createTarget":
            return {"targetId": "doctor-target"}
        if method == "Page.getLayoutMetrics":
            return {"cssVisualViewport": {"clientWidth": 1280, "clientHeight": 720}}
        if method == "Target.activateTarget":
            return {}
        raise RuntimeError(f"unhandled CDP method: {method}")


class FakeCdpSession:
    def __init__(self, client: FakeCdpClient, target_id: str = "doctor-target") -> None:
        self.cdp_client = client
        self.target_id = target_id
        self.session_id = "doctor-session"


class FakeBrowserSession:
    instances: list["FakeBrowserSession"] = []

    def __init__(self, **kwargs: object) -> None:
        self.kwargs = kwargs
        self.browser_profile = SimpleNamespace(
            cdp_url=kwargs.get("cdp_url") or "http://127.0.0.1:9222",
            user_data_dir=kwargs.get("user_data_dir"),
            downloads_path=kwargs.get("downloads_path"),
        )
        self.cdp_url = "http://127.0.0.1:9222"
        self.cdp_client = FakeCdpClient()
        self.started = False
        self.killed = False
        self.navigations: list[dict[str, object]] = []
        self._reconnecting = True
        self._reconnect_task = None
        FakeBrowserSession.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def navigate_to(self, url: str, new_tab: bool = False) -> None:
        self.navigations.append({"url": url, "new_tab": new_tab})

    async def get_current_page_url(self) -> str:
        return "https://example.com/browser-doctor"

    async def get_current_page_title(self) -> str:
        return "Browser Doctor"

    async def get_or_create_cdp_session(
        self,
        target_id: str | None = None,
        focus: bool = False,
    ) -> FakeCdpSession:
        return FakeCdpSession(self.cdp_client, target_id or "doctor-target")

    async def kill(self) -> None:
        self.killed = True


def _log_payloads(caplog) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for record in caplog.records:
        try:
            payloads.append(json.loads(record.message))
        except json.JSONDecodeError:
            continue
    return payloads


def test_browser_developer_diagnostics_checks_paths_cdp_tab_and_cleanup(
    tmp_path: Path,
    run_context,
    assert_no_defaulted_required_fields,
    assert_logs_have_required_fields,
    caplog,
) -> None:
    caplog.set_level(
        logging.INFO,
        logger="market_lense.browser_report_download_service.dev_diagnostics",
    )
    FakeBrowserSession.instances.clear()

    result = run_browser_developer_diagnostics(
        BrowserDeveloperDiagnosticsRequest(
            schema_version="1.0",
            profile_path=str(tmp_path / "profile"),
            downloads_path=str(tmp_path / "downloads"),
            headed=False,
            verification_url="https://example.com/browser-doctor",
            cleanup_stale_once=True,
            activate_verification_tab=True,
        ),
        run_context,
        browser_session_class=FakeBrowserSession,
    )

    assert_no_defaulted_required_fields(result)
    assert result.status == "ok"
    assert result.browser_use_connected is True
    assert result.cdp_available is True
    assert result.real_tab_available is True
    assert result.cleanup_attempted is True
    assert result.cleanup_status == "ok"
    assert result.verification_tab_activated is True
    assert result.active_tab_url == "https://example.com/browser-doctor"
    assert {check.name for check in result.checks} == {
        "profile_path",
        "downloads_path",
        "stale_connection_cleanup",
        "browser_use_connectivity",
        "active_tab",
        "cdp_and_real_tab",
    }
    instance = FakeBrowserSession.instances[-1]
    assert instance.kwargs["headless"] is True
    assert "cdp_url" not in instance.kwargs
    assert "keep_alive" not in instance.kwargs
    assert instance.navigations == []
    assert instance.killed is True
    assert [call["method"] for call in instance.cdp_client.calls] == [
        "Target.createTarget",
        "Target.activateTarget",
        "Target.getTargets",
        "Page.getLayoutMetrics",
        "Target.activateTarget",
    ]
    assert_logs_have_required_fields(_log_payloads(caplog))


def test_browser_developer_diagnostics_reports_unusable_browser(
    tmp_path: Path,
    run_context,
) -> None:
    class FailingBrowserSession(FakeBrowserSession):
        async def start(self) -> None:
            raise RuntimeError("Chrome remote debugging unavailable")

    result = run_browser_developer_diagnostics(
        BrowserDeveloperDiagnosticsRequest(
            schema_version="1.0",
            profile_path=str(tmp_path / "profile"),
            downloads_path=str(tmp_path / "downloads"),
            headed=True,
            verification_url="https://example.com/browser-doctor",
        ),
        run_context,
        browser_session_class=FailingBrowserSession,
    )

    assert result.status == "failed"
    assert result.browser_use_connected is False
    assert "Chrome remote debugging unavailable" in result.error
    assert result.checks[-1].name == "diagnostic_runtime"
