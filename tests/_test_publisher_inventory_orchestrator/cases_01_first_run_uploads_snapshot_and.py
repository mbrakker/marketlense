# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_run_publisher_inventory_discovery_first_run_uploads_snapshot_and_returns_diff(
    run_context,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
):
    settings = _settings()
    uploads = []
    records = []
    status_records = []
    source_records = []

    deps = _dependencies(
        record_publisher_inventory_state=lambda req, ctx: records.append(req),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
        ),
        record_discovered_report_source=lambda req, ctx: (
            source_records.append(req)
            or ReportSourceDiscoveryRecordResponse(
                schema_version="1.0",
                record_id=1,
                publisher_name=req.publisher_name,
                source_domain=req.source_domain,
                report_name=req.report_name,
                landing_page_url=req.landing_page_url,
                source_page_url=req.source_page_url,
                discovered_at_utc=req.discovered_at_utc,
                discovered_on_page_number=req.discovered_on_page_number,
                created_new=True,
            )
        ),
        upload_bytes=lambda req, ctx: (
            uploads.append(req)
            or DriveUploadBytesResponse(
                schema_version="1.0",
                file=DriveFile(
                    schema_version="1.0",
                    file_id="drive-file-1",
                    name=req.file_name,
                    modified_time=None,
                    md5_checksum=None,
                    mime_type="application/json",
                ),
                size=len(req.content),
                md5="abc123",
            )
        ),
    )
    caplog.set_level(
        logging.INFO, logger="market_lense.publisher_inventory_orchestrator"
    )

    result = run_publisher_inventory_discovery(
        _request(settings), ctx=run_context, dependencies=deps
    )

    assert result.publisher_name == "Activate Consulting"
    assert result.snapshot_changed is True
    assert result.used_memory_route is False
    assert len(result.new_report_urls) == 1
    assert len(result.current_candidates) == 1
    assert (
        result.current_candidates[0].canonical_url
        == "https://www.activate.com/reports/new-report"
    )
    assert result.current_candidates[0].discovery_provenances == []
    assert result.new_report_urls[0].discovered_on_page_number == 2
    assert len(uploads) == 1
    assert len(records) == 1
    assert [record.status for record in status_records] == ["passed"]
    assert len(source_records) == 1
    assert (
        source_records[0].landing_page_url
        == "https://www.activate.com/reports/new-report"
    )
    assert source_records[0].report_name == "Resolved New Report"
    assert (
        source_records[0].source_page_url == "https://www.activate.com/insights?page=2"
    )
    assert_no_defaulted_required_fields(result)
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.publisher_inventory_orchestrator")
    )

def test_run_publisher_inventory_discovery_falls_back_after_memory_route_failure(
    run_context,
):
    settings = _settings()
    attempts = {"memory": 0, "fresh": 0}

    def _discover(req, ctx):
        if req.route_hint:
            attempts["memory"] += 1
            raise AppError(
                code="publisher_inventory_browser_failed",
                message="stale route",
                retryable=True,
            )
        attempts["fresh"] += 1
        return _service_response(
            used_route_hint=False,
            new_url="https://www.activate.com/reports/new-report",
        )

    deps = _dependencies(
        discover_publisher_inventory=_discover,
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=True, with_snapshot=False
        ),
    )

    result = run_publisher_inventory_discovery(
        _request(settings), ctx=run_context, dependencies=deps
    )

    assert attempts["memory"] >= 1
    assert attempts["fresh"] == 1
    assert result.used_memory_route is False

def test_run_publisher_inventory_discovery_falls_back_after_http_empty(
    run_context,
):
    settings = _settings()
    attempts: list[str] = []

    def _discover(req, ctx):
        attempts.append(req.route_kind_hint or "")
        if req.route_kind_hint == "http_parse":
            raise AppError(
                code="publisher_inventory_http_empty",
                message="Direct HTTP parsing found no valid report inventory items",
                retryable=False,
            )
        return _service_response(
            used_route_hint=False,
            new_url="https://www.activate.com/reports/new-report",
        )

    deps = _dependencies(discover_publisher_inventory=_discover)

    result = run_publisher_inventory_discovery(
        _request(settings), ctx=run_context, dependencies=deps
    )

    assert attempts == ["http_parse", "browser_render"]
    assert result.new_report_urls[0].canonical_url == (
        "https://www.activate.com/reports/new-report"
    )

def test_run_publisher_inventory_discovery_skips_invalid_drive_snapshot(
    run_context,
    caplog,
):
    settings = _settings()
    source_records = []
    downloads = []

    def _download_snapshot(req, ctx):
        downloads.append(req.file.file_id)
        return DriveDownloadResponse(
            schema_version="1.0",
            file=req.file,
            content=b'{"schema_version":"1.0","publisher_name":"Integration Publisher"}',
            md5="bad-md5",
            size=65,
        )

    deps = _dependencies(
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[
                DriveFile(
                    schema_version="1.0",
                    file_id="invalid-snapshot",
                    name="publisher_inventory_snapshot__20260422T202421Z.json",
                    modified_time="2026-04-22T20:24:21Z",
                    md5_checksum="bad-md5",
                    mime_type="application/json",
                )
            ],
        ),
        download_pdf=_download_snapshot,
        record_discovered_report_source=lambda req, ctx: (
            source_records.append(req)
            or ReportSourceDiscoveryRecordResponse(
                schema_version="1.0",
                record_id=1,
                publisher_name=req.publisher_name,
                source_domain=req.source_domain,
                report_name=req.report_name,
                landing_page_url=req.landing_page_url,
                source_page_url=req.source_page_url,
                discovered_at_utc=req.discovered_at_utc,
                discovered_on_page_number=req.discovered_on_page_number,
                created_new=True,
            )
        ),
    )
    caplog.set_level(
        logging.INFO, logger="market_lense.publisher_inventory_orchestrator"
    )

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert downloads == ["invalid-snapshot"]
    assert result.snapshot_changed is True
    assert [item.landing_page_url for item in source_records] == [
        "https://www.activate.com/reports/new-report"
    ]
    events = _events(caplog, "market_lense.publisher_inventory_orchestrator")
    assert any(
        event["event"] == "publisher_inventory_previous_snapshot_skipped"
        and event["fields"]["snapshot_drive_file_id"] == "invalid-snapshot"
        for event in events
    )

def test_run_publisher_inventory_discovery_skips_mismatched_drive_snapshot(
    run_context,
    caplog,
):
    settings = _settings()
    source_records = []

    deps = _dependencies(
        get_publisher_inventory_state=lambda req, ctx: PublisherInventoryStateResponse(
            schema_version="1.0",
            publisher_name="Algolia",
            insights_url="https://resources.algolia.com/reports",
            normalized_url="https://resources.algolia.com/reports",
            google_folder="https://drive.google.com/drive/folders/folder123",
            discovery_test_status=None,
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[
                DriveFile(
                    schema_version="1.0",
                    file_id="activate-snapshot",
                    name="publisher_inventory_snapshot__20260501T195807Z.json",
                    modified_time="2026-05-01T19:58:07Z",
                    md5_checksum="activate-md5",
                    mime_type="application/json",
                )
            ],
        ),
        download_pdf=lambda req, ctx: DriveDownloadResponse(
            schema_version="1.0",
            file=req.file,
            content=_snapshot_json(
                "https://www.activate.com/reports/old-report"
            ).encode("utf-8"),
            md5="activate-md5",
            size=100,
        ),
        record_discovered_report_source=lambda req, ctx: (
            source_records.append(req)
            or ReportSourceDiscoveryRecordResponse(
                schema_version="1.0",
                record_id=1,
                publisher_name=req.publisher_name,
                source_domain=req.source_domain,
                report_name=req.report_name,
                landing_page_url=req.landing_page_url,
                source_page_url=req.source_page_url,
                discovered_at_utc=req.discovered_at_utc,
                discovered_on_page_number=req.discovered_on_page_number,
                created_new=True,
            )
        ),
    )
    caplog.set_level(
        logging.INFO, logger="market_lense.publisher_inventory_orchestrator"
    )

    result = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url="https://resources.algolia.com/reports",
            reports_db=settings.reports_db,
            settings=settings,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.previous_report_count == 0
    assert [item.landing_page_url for item in source_records] == [
        "https://www.activate.com/reports/new-report"
    ]
    events = _events(caplog, "market_lense.publisher_inventory_orchestrator")
    assert any(
        event["event"] == "publisher_inventory_previous_snapshot_skipped"
        and event["fields"]["code"] == "publisher_inventory_snapshot_publisher_mismatch"
        for event in events
    )

def test_run_publisher_inventory_discovery_does_not_fallback_after_non_retryable_memory_failure(
    run_context,
    assert_app_error,
):
    settings = _settings()
    attempts = {"memory": 0, "fresh": 0}

    def _discover(req, ctx):
        if req.route_hint:
            attempts["memory"] += 1
            raise AppError(
                code="publisher_inventory_route_summary_invalid",
                message="stored route is structurally invalid",
                retryable=False,
            )
        attempts["fresh"] += 1
        return _service_response(
            used_route_hint=False,
            new_url="https://www.activate.com/reports/new-report",
        )

    deps = _dependencies(
        discover_publisher_inventory=_discover,
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=True, with_snapshot=False
        ),
    )

    with pytest.raises(AppError) as err:
        run_publisher_inventory_discovery(
            _request(settings), ctx=run_context, dependencies=deps
        )

    assert attempts["memory"] == 1
    assert attempts["fresh"] == 0
    assert_app_error(
        err.value,
        code="publisher_inventory_route_summary_invalid",
        retryable=False,
    )

def test_run_publisher_inventory_discovery_applies_remaining_time_budget_to_step_settings(
    run_context,
):
    captured_discovery_timeouts = []
    captured_screening_timeouts = []
    captured_quality_timeouts = []
    settings = PublisherInventorySettings(
        **{
            **_settings().__dict__,
            "timeout_seconds": 30.0,
            "candidate_screening_timeout_seconds": 30.0,
            "candidate_quality_check_timeout_seconds": 15.0,
            "command_time_budget_seconds": 4.0,
        }
    )
    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: (
            captured_discovery_timeouts.append(req.settings.timeout_seconds)
            or _service_response(
                used_route_hint=False,
                new_url="https://www.activate.com/reports/new-report",
            )
        ),
        screen_publisher_inventory_candidates=lambda req, ctx: (
            captured_screening_timeouts.append(
                req.settings.candidate_screening_timeout_seconds
            )
            or _screening_response(
                accepted_urls={"https://www.activate.com/reports/new-report"},
                request=req,
            )
        ),
        qualify_publisher_inventory_candidates=lambda req, ctx: (
            captured_quality_timeouts.append(
                req.settings.candidate_quality_check_timeout_seconds
            )
            or _quality_response(
                accepted_urls={"https://www.activate.com/reports/new-report"},
                request=req,
            )
        ),
    )

    with patch(
        "time.monotonic",
        side_effect=[
            100.0,
            100.5,
            100.75,
            101.0,
            101.25,
            101.5,
            101.75,
            102.0,
            102.25,
            102.5,
            102.75,
            103.0,
        ],
    ):
        run_publisher_inventory_discovery(
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )

    assert len(captured_discovery_timeouts) == 1
    assert len(captured_screening_timeouts) == 1
    assert len(captured_quality_timeouts) == 1
    assert 1.0 <= captured_discovery_timeouts[0] < settings.timeout_seconds
    assert (
        1.0
        <= captured_screening_timeouts[0]
        < settings.candidate_screening_timeout_seconds
    )
    assert (
        1.0
        <= captured_quality_timeouts[0]
        <= settings.candidate_quality_check_timeout_seconds
    )
    assert captured_discovery_timeouts[0] >= captured_screening_timeouts[0]
    assert captured_screening_timeouts[0] >= captured_quality_timeouts[0]

def test_run_publisher_inventory_discovery_records_failed_test_status(
    run_context,
):
    settings = _settings()
    status_records = []

    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: (_ for _ in ()).throw(
            AppError(
                code="publisher_inventory_browser_pagination_limit",
                message="deep archive limit reached",
                retryable=False,
            )
        ),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
        ),
    )

    with pytest.raises(AppError) as exc_info:
        run_publisher_inventory_discovery(
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "publisher_inventory_browser_pagination_limit"
    assert [record.status for record in status_records] == [
        "bounded:publisher_inventory_browser_pagination_limit"
    ]

def test_run_publisher_inventory_discovery_records_time_budget_failure_before_discovery(
    run_context,
):
    status_records = []
    discover_calls = []
    settings = PublisherInventorySettings(
        **{**_settings().__dict__, "command_time_budget_seconds": 1.0}
    )
    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: (
            discover_calls.append(req)
            or _service_response(
                used_route_hint=False,
                new_url="https://www.activate.com/reports/new-report",
            )
        ),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
        ),
    )

    with patch(
        "time.monotonic",
        side_effect=[100.0, 101.5],
    ):
        with pytest.raises(AppError) as exc_info:
            run_publisher_inventory_discovery(
                _request(settings),
                ctx=run_context,
                dependencies=deps,
            )

    assert exc_info.value.code == "publisher_inventory_time_budget_exceeded"
    assert discover_calls == []
    assert [record.status for record in status_records] == [
        "failed:publisher_inventory_time_budget_exceeded"
    ]

def test_run_publisher_inventory_discovery_does_not_retry_or_fallback_on_pagination_limit(
    run_context,
):
    settings = _settings()
    attempts = {"memory": 0, "fresh": 0}

    def _discover(req, ctx):
        if req.route_hint:
            attempts["memory"] += 1
        else:
            attempts["fresh"] += 1
        raise AppError(
            code="publisher_inventory_browser_pagination_limit",
            message="deep archive limit reached",
            retryable=False,
        )

    deps = _dependencies(
        discover_publisher_inventory=_discover,
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=True,
            with_snapshot=False,
        ),
    )

    with pytest.raises(AppError) as exc_info:
        run_publisher_inventory_discovery(
            _request(settings), ctx=run_context, dependencies=deps
        )

    assert exc_info.value.code == "publisher_inventory_browser_pagination_limit"
    assert attempts == {"memory": 1, "fresh": 0}

def test_run_publisher_inventory_discovery_unchanged_rerun_skips_upload(
    run_context,
    idempotency_guard,
):
    settings = _settings()
    uploads = []
    snapshot_payload = _snapshot_json("https://www.activate.com/reports/report-one")
    snapshot_sha256 = _snapshot_sha256(
        "https://www.activate.com/reports/report-one",
        run_context,
    )

    def _run_once():
        deps = _dependencies(
            discover_publisher_inventory=lambda req, ctx: (
                PublisherInventoryServiceResponse(
                    schema_version="1.0",
                    source_url="https://www.activate.com/insights",
                    normalized_url="https://www.activate.com/insights",
                    route_kind="browser_render",
                    route_summary="Open page 1, click next, extract cards.",
                    final_page_url="https://www.activate.com/insights?page=2",
                    used_route_hint=False,
                    pages=[
                        PublisherInventoryPage(
                            schema_version="1.0",
                            page_number=1,
                            page_url="https://www.activate.com/insights",
                        )
                    ],
                    candidates=[
                        PublisherInventoryRawCandidate(
                            schema_version="1.0",
                            url="https://www.activate.com/reports/report-one",
                            title="Existing Report",
                            source_page_url="https://www.activate.com/insights",
                            discovered_on_page_number=1,
                        )
                    ],
                )
            ),
            screen_publisher_inventory_candidates=lambda req, ctx: _screening_response(
                accepted_urls=set(),
                request=req,
            ),
            qualify_publisher_inventory_candidates=lambda req, ctx: _quality_response(
                accepted_urls=set(),
                request=req,
            ),
            get_publisher_inventory_state=lambda req, ctx: _publisher_state(
                with_route=False, with_snapshot=True, snapshot_sha256=snapshot_sha256
            ),
            record_discovered_report_source=lambda req, ctx: (
                ReportSourceDiscoveryRecordResponse(
                    schema_version="1.0",
                    record_id=1,
                    publisher_name=req.publisher_name,
                    source_domain=req.source_domain,
                    report_name=req.report_name,
                    landing_page_url=req.landing_page_url,
                    source_page_url=req.source_page_url,
                    discovered_at_utc=req.discovered_at_utc,
                    discovered_on_page_number=req.discovered_on_page_number,
                    created_new=False,
                )
            ),
            download_pdf=lambda req, ctx: DriveDownloadResponse(
                schema_version="1.0",
                file=req.file,
                content=snapshot_payload.encode("utf-8"),
                md5="md5",
                size=len(snapshot_payload),
            ),
            upload_bytes=lambda req, ctx: (
                uploads.append(req)
                or DriveUploadBytesResponse(
                    schema_version="1.0",
                    file=DriveFile(
                        schema_version="1.0",
                        file_id="drive-file-new",
                        name=req.file_name,
                        modified_time=None,
                        md5_checksum=None,
                        mime_type="application/json",
                    ),
                    size=len(req.content),
                    md5="abc123",
                )
            ),
        )
        return run_publisher_inventory_discovery(
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )

    first, second = idempotency_guard(_run_once, side_effect_count=lambda: len(uploads))
    assert first.snapshot_changed is False
    assert second.snapshot_changed is False
    assert first.new_report_urls == []
    assert second.new_report_urls == []
    assert uploads == []

__all__ = [
    "test_run_publisher_inventory_discovery_first_run_uploads_snapshot_and_returns_diff",
    "test_run_publisher_inventory_discovery_falls_back_after_memory_route_failure",
    "test_run_publisher_inventory_discovery_falls_back_after_http_empty",
    "test_run_publisher_inventory_discovery_skips_invalid_drive_snapshot",
    "test_run_publisher_inventory_discovery_skips_mismatched_drive_snapshot",
    "test_run_publisher_inventory_discovery_does_not_fallback_after_non_retryable_memory_failure",
    "test_run_publisher_inventory_discovery_applies_remaining_time_budget_to_step_settings",
    "test_run_publisher_inventory_discovery_records_failed_test_status",
    "test_run_publisher_inventory_discovery_records_time_budget_failure_before_discovery",
    "test_run_publisher_inventory_discovery_does_not_retry_or_fallback_on_pagination_limit",
    "test_run_publisher_inventory_discovery_unchanged_rerun_skips_upload",
]
