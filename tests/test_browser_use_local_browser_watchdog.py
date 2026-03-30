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
from browser_use.browser.events import BrowserKillEvent, BrowserStopEvent
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


class _FakeLogger:
    def debug(self, _message: str) -> None:
        return


class _FakeProcess:
    def __init__(self, pid: int, children: list["_FakeProcess"] | None = None) -> None:
        self.pid = pid
        self._running = True
        self._children = children or []
        self.terminate_calls = 0
        self.kill_calls = 0

    def children(self, recursive: bool = False) -> list["_FakeProcess"]:
        if not recursive:
            return list(self._children)
        descendants: list[_FakeProcess] = []
        for child in self._children:
            descendants.append(child)
            descendants.extend(child.children(recursive=True))
        return descendants

    def terminate(self) -> None:
        self.terminate_calls += 1
        self._running = False

    def kill(self) -> None:
        self.kill_calls += 1
        self._running = False

    def is_running(self) -> bool:
        return self._running


def test_local_browser_watchdog_force_stop_awaits_kill_completion() -> None:
    state = {"dispatched_types": [], "awaited": False, "event_result_awaited": False}

    class _DispatchedEvent:
        def __await__(self):
            async def _wait() -> None:
                state["awaited"] = True

            return _wait().__await__()

        async def event_result(self, **_kwargs) -> None:
            state["event_result_awaited"] = True
            return None

    class _EventBus:
        def dispatch(self, event):
            state["dispatched_types"].append(type(event).__name__)
            return _DispatchedEvent()

    watchdog = LocalBrowserWatchdog.model_construct(
        event_bus=_EventBus(),
        browser_session=SimpleNamespace(
            is_local=True,
            logger=_FakeLogger(),
            browser_profile=SimpleNamespace(user_data_dir="profile"),
        ),
    )
    watchdog._subprocess = _FakeProcess(pid=1001)

    asyncio.run(watchdog.on_BrowserStopEvent(BrowserStopEvent(force=True)))

    assert state == {
        "dispatched_types": [BrowserKillEvent.__name__],
        "awaited": True,
        "event_result_awaited": True,
    }


def test_local_browser_watchdog_stop_without_force_keeps_browser_alive() -> None:
    dispatched_types: list[str] = []

    class _EventBus:
        def dispatch(self, event):
            dispatched_types.append(type(event).__name__)
            return event

    watchdog = LocalBrowserWatchdog.model_construct(
        event_bus=_EventBus(),
        browser_session=SimpleNamespace(
            is_local=True,
            logger=_FakeLogger(),
            browser_profile=SimpleNamespace(user_data_dir="profile"),
        ),
    )
    watchdog._subprocess = _FakeProcess(pid=1002)

    asyncio.run(watchdog.on_BrowserStopEvent(BrowserStopEvent(force=False)))

    assert dispatched_types == []
    assert watchdog._subprocess is not None


def test_local_browser_watchdog_kill_cleans_browser_process_tree() -> None:
    grandchild = _FakeProcess(pid=2003)
    child = _FakeProcess(pid=2002, children=[grandchild])
    root = _FakeProcess(pid=2001, children=[child])
    watchdog = LocalBrowserWatchdog.model_construct(
        event_bus=SimpleNamespace(dispatch=lambda event: event),
        browser_session=SimpleNamespace(
            is_local=True,
            logger=_FakeLogger(),
            browser_profile=SimpleNamespace(user_data_dir="profile"),
        ),
    )
    watchdog._subprocess = root

    asyncio.run(watchdog.on_BrowserKillEvent(BrowserKillEvent()))

    assert root.terminate_calls == 1
    assert child.terminate_calls == 1
    assert grandchild.terminate_calls == 1
    assert root.kill_calls == 0
    assert child.kill_calls == 0
    assert grandchild.kill_calls == 0
    assert root.is_running() is False
    assert child.is_running() is False
    assert grandchild.is_running() is False
    assert watchdog._subprocess is None
