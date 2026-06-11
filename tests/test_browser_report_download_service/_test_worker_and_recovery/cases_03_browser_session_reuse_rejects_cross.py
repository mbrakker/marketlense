# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_browser_session_reuse_rejects_cross_publisher_key_without_override(
    tmp_path: Path,
    run_context,
) -> None:
    policy = BrowserDownloadSessionReusePolicy(
        schema_version="1.0",
        enabled=True,
        mode="same_publisher_batch",
        session_key="shared-key",
        publisher_scope="example.com",
        ttl_seconds=120.0,
        base_dir=str(tmp_path / "session-reuse"),
    )
    first = browser_runtime.resolve_browser_session_reuse(
        policy=policy,
        default_base_dir=tmp_path,
        normalized_url="https://example.com/report",
        ctx=run_context,
    )
    second = browser_runtime.resolve_browser_session_reuse(
        policy=replace(policy, publisher_scope="other.example"),
        default_base_dir=tmp_path,
        normalized_url="https://other.example/report",
        ctx=run_context,
    )

    assert first.accepted is True
    assert second.accepted is False
    assert second.rejection_reason == "cross_publisher_scope_mismatch"

def test_prepare_download_dir_tolerates_locked_managed_browser_profile_dir(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    normalized_url = (
        "https://www.brightlocal.com/research/local-rankings-investigation-dentist"
    )
    download_dir = request_runtime.prepare_download_dir(
        root_dir=str(tmp_path),
        normalized_url=normalized_url,
    )
    locked_profile_dir = download_dir / "browser-use-user-data-dir-profile-locked"
    locked_profile_dir.mkdir(parents=True, exist_ok=True)
    (locked_profile_dir / "journal.baj").write_text("locked", encoding="utf-8")
    stale_artifact = download_dir / "stale.txt"
    stale_artifact.write_text("stale", encoding="utf-8")
    original_rmtree = request_runtime.rmtree

    def fake_rmtree(path: str | Path, *args: Any, **kwargs: Any) -> None:
        candidate = Path(path)
        if candidate == locked_profile_dir:
            raise PermissionError(13, "locked", str(candidate))
        return original_rmtree(path, *args, **kwargs)

    external_boundary_mocks_only.setattr(request_runtime, "rmtree", fake_rmtree)

    prepared_dir = request_runtime.prepare_download_dir(
        root_dir=str(tmp_path),
        normalized_url=normalized_url,
    )

    assert prepared_dir == download_dir
    assert locked_profile_dir.exists()
    assert not stale_artifact.exists()

def test_kill_browser_force_stops_local_watchdog_process_tree(
    run_context,
    external_boundary_mocks_only,
) -> None:
    class _FakeProcess:
        def __init__(
            self, pid: int, children: list["_FakeProcess"] | None = None
        ) -> None:
            self.pid = pid
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

        def kill(self) -> None:
            self.kill_calls += 1

    grandchild = _FakeProcess(pid=3003)
    child = _FakeProcess(pid=3002, children=[grandchild])
    root = _FakeProcess(pid=3001, children=[child])

    def _fake_psutil_process(pid: int) -> _FakeProcess:
        assert pid == 3001
        return root

    def _fake_wait_procs(processes: list[_FakeProcess], timeout: float):
        assert timeout > 0.0
        return list(processes), []

    fake_browser = SimpleNamespace(
        browser_profile=SimpleNamespace(user_data_dir="active-profile"),
        _local_browser_watchdog=SimpleNamespace(
            _subprocess=SimpleNamespace(pid=3001),
            _temp_dirs_to_cleanup=[],
            _original_user_data_dir=None,
        ),
        kill=lambda: (_ for _ in ()).throw(
            AssertionError("browser.kill should not run")
        ),
    )

    external_boundary_mocks_only.setattr(
        browser_runtime.psutil,
        "Process",
        _fake_psutil_process,
    )
    external_boundary_mocks_only.setattr(
        browser_runtime.psutil,
        "wait_procs",
        _fake_wait_procs,
    )

    browser_runtime._kill_browser(
        fake_browser,
        ctx=run_context,
        normalized_url="https://example.com/report",
    )

    assert root.terminate_calls == 1
    assert child.terminate_calls == 1
    assert grandchild.terminate_calls == 1
    assert root.kill_calls == 0
    assert child.kill_calls == 0
    assert grandchild.kill_calls == 0
    assert fake_browser._local_browser_watchdog._subprocess is None

def test_prepare_browser_for_shutdown_awaits_cancelled_reconnect_task(
    run_context,
) -> None:
    event_calls: list[str] = []

    class FakeReconnectTask:
        def __init__(self) -> None:
            self.cancelled = False
            self.awaited = False

        def done(self) -> bool:
            return False

        def cancel(self) -> None:
            self.cancelled = True

        def __await__(self):
            self.awaited = True
            if False:
                yield None
            return None

    reconnect_task = FakeReconnectTask()
    fake_browser = SimpleNamespace(
        browser_profile=SimpleNamespace(cdp_url="ws://example"),
        _reconnect_task=reconnect_task,
        _reconnect_event=SimpleNamespace(set=lambda: event_calls.append("set")),
        _reconnecting=True,
    )

    browser_runtime._prepare_browser_for_shutdown(
        fake_browser,
        ctx=run_context,
        normalized_url="https://example.com/report",
    )

    assert reconnect_task.cancelled is True
    assert reconnect_task.awaited is True
    assert fake_browser._reconnect_task is None
    assert fake_browser._reconnecting is False
    assert fake_browser.browser_profile.cdp_url is None
    assert event_calls == ["set"]

def test_download_report_with_browser_use_maps_browser_start_timeout_to_typed_error(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent

    class BrowserStartTimeoutAgent(original_runtime):
        def run_sync(self, max_steps: int):
            raise TimeoutError(
                "Event handler browser_use.browser.watchdog_base.BrowserSession.on_BrowserStartEvent "
                "timed out after 30.0s and interrupted any processing of 1 child events"
            )

    runtime.Agent = BrowserStartTimeoutAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as exc_info:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://datareportal.com/reports/digital-2026-mozambique",
                settings=_settings(tmp_path),
            ),
            run_context,
        )

    assert_app_error(
        exc_info.value,
        code="browser_download_browser_start_timeout",
        retryable=True,
    )

def test_download_report_with_browser_use_times_out_stalled_agent(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = _settings(tmp_path)
    settings = replace(settings, timeout_seconds=0.05, max_steps=1)

    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="",
        create_pdf=False,
        email_submission_completed=None,
    )
    original_runtime = runtime.Agent
    original_browser = runtime.Browser
    kill_calls: list[str] = []
    stop_observations: list[bool] = []

    class TrackingBrowser(original_browser):
        async def kill(self) -> None:
            kill_calls.append("kill")
            await super().kill()

    class StalledAgent(original_runtime):
        def stop(self) -> None:
            stop_observations.append(hasattr(self, "_task_start_time"))
            super().stop()

        def run_sync(self, max_steps: int):
            time.sleep(2.0)
            return super().run_sync(max_steps)

    runtime.Browser = TrackingBrowser
    runtime.Agent = StalledAgent
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    with pytest.raises(AppError) as exc_info:
        service.download_report_with_browser_use(
            BrowserReportDownloadRequest(
                schema_version="1.0",
                url="https://example.com/whitepapers/eu-cosmetics-regulations-foundations-plm",
                settings=settings,
                route_family_hint="browser_pdf_click",
            ),
            run_context,
        )

    assert exc_info.value.code == "browser_download_agent_timeout"
    assert kill_calls
    assert stop_observations == [True]

__all__ = [
    "test_browser_session_reuse_rejects_cross_publisher_key_without_override",
    "test_prepare_download_dir_tolerates_locked_managed_browser_profile_dir",
    "test_kill_browser_force_stops_local_watchdog_process_tree",
    "test_prepare_browser_for_shutdown_awaits_cancelled_reconnect_task",
    "test_download_report_with_browser_use_maps_browser_start_timeout_to_typed_error",
    "test_download_report_with_browser_use_times_out_stalled_agent",
]
