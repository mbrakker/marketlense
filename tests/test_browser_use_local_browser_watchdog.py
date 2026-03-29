from __future__ import annotations

import http.server
import asyncio
import socket
import socketserver
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

VENDORED_BROWSER_USE_ROOT = Path(__file__).resolve().parents[1] / "tools" / "browser-use"
if str(VENDORED_BROWSER_USE_ROOT) not in sys.path:
    sys.path.insert(0, str(VENDORED_BROWSER_USE_ROOT))

from browser_use.browser.session import BrowserSession
from browser_use.browser.watchdogs import local_browser_watchdog as watchdog_module
from browser_use.browser.watchdogs.local_browser_watchdog import LocalBrowserWatchdog


class _CdpVersionHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/json/version":
            self.send_error(404)
            return
        payload = b'{"Browser":"Chrome","webSocketDebuggerUrl":"ws://127.0.0.1/devtools/browser/test"}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class _ReusableTcpServer(socketserver.TCPServer):
    allow_reuse_address = True


def _start_cdp_server(port: int) -> tuple[_ReusableTcpServer, threading.Thread]:
    server = _ReusableTcpServer(("127.0.0.1", port), _CdpVersionHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread


def test_local_browser_watchdog_launches_browser_with_devnull_stdio(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    captured: dict[str, object] = {}
    started_servers: list[tuple[_ReusableTcpServer, threading.Thread]] = []

    async def _fake_create_subprocess_exec(*cmd, stdout, stderr):
        captured["cmd"] = cmd
        captured["stdout"] = stdout
        captured["stderr"] = stderr
        debug_arg = next(arg for arg in cmd if str(arg).startswith("--remote-debugging-port="))
        debug_port = int(str(debug_arg).split("=", 1)[1])
        started_servers.append(_start_cdp_server(debug_port))
        return SimpleNamespace(pid=4242)

    external_boundary_mocks_only.setattr(
        watchdog_module.asyncio,
        "create_subprocess_exec",
        _fake_create_subprocess_exec,
    )
    external_boundary_mocks_only.setattr(
        watchdog_module.psutil,
        "Process",
        lambda pid: SimpleNamespace(pid=pid),
    )

    profile_dir = tmp_path / "browser-profile"
    profile_dir.mkdir()
    session = BrowserSession(
        headless=True,
        user_data_dir=profile_dir,
        executable_path="fake-browser",
    )
    watchdog = LocalBrowserWatchdog(event_bus=session.event_bus, browser_session=session)

    try:
        process, cdp_url = asyncio.run(watchdog._launch_browser(max_retries=1))
    finally:
        for server, thread in started_servers:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1.0)

    assert process.pid == 4242
    assert cdp_url.startswith("http://127.0.0.1:")
    assert captured["stdout"] == watchdog_module.asyncio.subprocess.DEVNULL
    assert captured["stderr"] == watchdog_module.asyncio.subprocess.DEVNULL


def test_local_browser_watchdog_wait_for_cdp_url_times_out() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.bind(("127.0.0.1", 0))
        unused_port = probe.getsockname()[1]

    with pytest.raises(TimeoutError, match="Browser did not start within"):
        asyncio.run(LocalBrowserWatchdog._wait_for_cdp_url(unused_port, timeout=0.2))
