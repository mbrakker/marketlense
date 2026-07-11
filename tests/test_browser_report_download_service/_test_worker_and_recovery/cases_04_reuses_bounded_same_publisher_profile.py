# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_download_report_with_browser_use_reuses_bounded_same_publisher_profile(
    tmp_path: Path,
    run_context,
    external_boundary_mocks_only,
    caplog,
) -> None:
    caplog.set_level(
        logging.INFO,
        logger="market_lense.browser_report_download_service.session_reuse",
    )
    reuse_base_dir = tmp_path / "session-reuse"
    settings = replace(
        _settings(tmp_path),
        session_reuse_policy=BrowserDownloadSessionReusePolicy(
            schema_version="1.0",
            enabled=True,
            mode="same_publisher_batch",
            session_key="batch-key",
            publisher_scope="example.com",
            ttl_seconds=120.0,
            base_dir=str(reuse_base_dir),
        ),
    )
    runtime = _runtime(
        tmp_path,
        route_kind="pdf_download",
        route_summary="Open the report page and save the PDF.",
        create_pdf=True,
        email_submission_completed=None,
    )
    original_browser = runtime.Browser
    browser_profile_paths: list[str] = []

    class ReuseTrackingBrowser(original_browser):
        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            browser_profile_paths.append(str(kwargs.get("user_data_dir") or ""))

    runtime.Browser = ReuseTrackingBrowser
    external_boundary_mocks_only.setattr(
        browser_runtime,
        "import_module",
        lambda module_name: runtime,
    )

    first = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/reuse-report",
            settings=settings,
        ),
        run_context,
    )
    second = service.download_report_with_browser_use(
        BrowserReportDownloadRequest(
            schema_version="1.0",
            url="https://example.com/reuse-report",
            settings=settings,
        ),
        run_context,
    )

    assert first.outcome == "downloaded"
    assert second.outcome == "downloaded"
    assert len(browser_profile_paths) == 2
    assert browser_profile_paths[0] == browser_profile_paths[1]
    profile_path = Path(browser_profile_paths[0])
    assert profile_path.exists()
    assert (profile_path / "session_reuse_ledger.json").exists()
    reuse_events = []
    for record in caplog.records:
        payload = json.loads(record.message)
        if payload.get("event") == "browser_report_download_session_reuse_resolved":
            reuse_events.append(payload)
    assert [event["fields"]["profile_reused"] for event in reuse_events[-2:]] == [
        False,
        True,
    ]


__all__ = ["test_download_report_with_browser_use_reuses_bounded_same_publisher_profile"]
