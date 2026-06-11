# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_run_publisher_inventory_discovery_reuses_idempotent_snapshot_and_source_steps(
    tmp_path,
    run_context,
) -> None:
    uploads = []
    source_records = []
    settings = _settings()
    settings = PublisherInventorySettings(
        **{**settings.__dict__, "reports_db": str(tmp_path / "reports.sqlite")}
    )

    deps = _dependencies(
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False
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

    first = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url="https://www.activate.com/insights",
            reports_db=settings.reports_db,
            settings=settings,
        ),
        ctx=run_context,
        dependencies=deps,
    )
    second = run_publisher_inventory_discovery(
        PublisherInventoryDiscoveryRequest(
            schema_version="1.0",
            insights_url="https://www.activate.com/insights",
            reports_db=settings.reports_db,
            settings=settings,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert first.snapshot_changed is True
    assert second.snapshot_changed is True
    assert len(uploads) == 1
    assert len(source_records) == 1
    assert (
        second.new_report_urls[0].canonical_url
        == first.new_report_urls[0].canonical_url
    )

def test_run_publisher_inventory_discovery_reuses_idempotent_auxiliary_writes(
    tmp_path,
    run_context,
    caplog,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    current_url = "https://www.activate.com/reports/new-report"
    run_quality_calls: list[object] = []
    recovery_cache_calls: list[object] = []
    state_calls: list[object] = []
    status_calls: list[object] = []

    replace_publishers(
        PublishersReplaceRequest(
            schema_version="1.0",
            db_path=reports_db,
            source_page_url="https://www.notion.so/source",
            publishers=[
                PublisherProfileRecord(
                    schema_version="1.0",
                    notion_page_id="page-1",
                    notion_page_url="https://www.notion.so/page-1",
                    name="Activate Consulting",
                    homepage="https://www.activate.com/",
                    self_presentation="Activate description",
                    insights_url="https://www.activate.com/insights",
                    icon_source="https://cdn.example.com/activate.png",
                )
            ],
        ),
        run_context,
    )

    def _record_run_quality(req, ctx):
        run_quality_calls.append(req)
        return record_publisher_inventory_run_quality(req, ctx)

    def _record_recovery_cache(req, ctx):
        recovery_cache_calls.append(req)
        return record_publisher_inventory_recovery_cache_record(req, ctx)

    def _record_state(req, ctx):
        state_calls.append(req)
        return record_publisher_inventory_state(req, ctx)

    def _record_status(req, ctx):
        status_calls.append(req)
        return record_publisher_inventory_test_status(req, ctx)

    def _quality_with_recovery(req, ctx):
        candidate = req.candidates[0]
        rejected = PublisherInventoryQualifiedCandidateItem(
            schema_version="1.0",
            canonical_url=candidate.canonical_url,
            title=candidate.title,
            discovered_on_page_number=candidate.discovered_on_page_number,
            source_page_url=candidate.source_page_url,
        )
        return PublisherInventoryCandidateQualityResponse(
            schema_version="1.0",
            approved_items=[],
            rejected_items=[rejected],
            decisions=[
                PublisherInventoryCandidateQualityDecision(
                    schema_version="1.0",
                    canonical_url=candidate.canonical_url,
                    accepted=False,
                    reason="protected_document_probe_required",
                    resolved_title=candidate.title,
                    source_surface_class="report_detail",
                    recovery_recipe=PublisherInventoryRecoveryRecipe(
                        schema_version="1.0",
                        verification_class="protected_document",
                        source_surface_class="report_detail",
                        recovery_action="protected_document_probe",
                        reason="retry with deferred protected-document probe",
                    ),
                )
            ],
        )

    settings = PublisherInventorySettings(
        **{**_settings().__dict__, "reports_db": reports_db}
    )
    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: _service_response(
            used_route_hint=False,
            new_url=current_url,
            title="Existing Report 1",
        ),
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False,
            with_snapshot=False,
            with_folder=True,
            snapshot_sha256="",
        ),
        get_publisher_inventory_recovery_cache_record=lambda req, ctx: None,
        qualify_publisher_inventory_candidates=_quality_with_recovery,
        record_publisher_inventory_run_quality=_record_run_quality,
        record_publisher_inventory_recovery_cache_record=_record_recovery_cache,
        record_publisher_inventory_state=_record_state,
        record_publisher_inventory_test_status=_record_status,
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("no qualified candidates should be recorded in this flow")
        ),
        upload_bytes=lambda req, ctx: DriveUploadBytesResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="drive-file-aux",
                name=req.file_name,
                modified_time=None,
                md5_checksum=None,
                mime_type="application/json",
            ),
            size=len(req.content),
            md5="abc123",
        ),
    )
    caplog.set_level(
        logging.INFO, logger="market_lense.publisher_inventory_orchestrator"
    )

    first = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )
    second = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert first.snapshot_changed is False
    assert second.snapshot_changed is False
    assert first.new_report_urls == []
    assert second.new_report_urls == []
    assert len(run_quality_calls) == 1
    assert len(recovery_cache_calls) == 1
    assert len(state_calls) == 1
    assert len(status_calls) == 1

    with sqlite3.connect(reports_db) as conn:
        run_quality_history = conn.execute(
            """
            SELECT COUNT(*)
            FROM publisher_inventory_route_history
            WHERE normalized_url=?
            """,
            ("https://www.activate.com/insights",),
        ).fetchone()
        recovery_cache_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM publisher_inventory_candidate_recovery_cache
            WHERE normalized_url=?
            """,
            ("https://www.activate.com/insights",),
        ).fetchone()
        publisher_row = conn.execute(
            """
            SELECT discovery_test_status, inventory_snapshot_sha256
            FROM publishers
            WHERE normalized_insights_url=?
            """,
            ("https://www.activate.com/insights",),
        ).fetchone()

    assert int(run_quality_history[0] if run_quality_history else 0) == 1
    assert int(recovery_cache_rows[0] if recovery_cache_rows else 0) == 1
    assert publisher_row is not None
    assert str(publisher_row[0] or "") == "passed:no_report_assets"
    assert len(str(publisher_row[1] or "")) == 64
    guardrail_events = [
        event
        for event in _events(caplog, "market_lense.publisher_inventory_orchestrator")
        if event["event"] == "publisher_inventory_rollout_guardrails_evaluated"
    ]
    assert guardrail_events
    guardrail_fields = guardrail_events[0]["fields"]
    assert guardrail_fields["rollout_flags"] == {
        "enable_deferred_candidate_recovery": True,
        "enable_structured_route_reuse": True,
        "enable_preflight_classifier_and_direct_detail": True,
    }
    assert guardrail_fields["deferred_recovery_scheduled_count"] == 1
    assert guardrail_fields["run_quality_requires_review"] is False
    assert guardrail_fields["kpi_guardrail_status"] == "pass"

def test_run_publisher_inventory_discovery_does_not_commit_raw_only_snapshot_drift(
    tmp_path,
    run_context,
):
    settings = PublisherInventorySettings(
        **{**_settings().__dict__, "reports_db": str(tmp_path / "reports.sqlite")}
    )
    uploads = []
    state_records = []
    snapshot_payload = _snapshot_json("https://www.activate.com/reports/report-one")
    snapshot_sha256 = _snapshot_sha256(
        "https://www.activate.com/reports/report-one", run_context
    )
    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: _service_response(
            used_route_hint=True,
            new_url="https://www.activate.com/reports/noisy-hub",
            title="Resources",
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
            with_route=True,
            with_snapshot=True,
            snapshot_sha256=snapshot_sha256,
        ),
        record_publisher_inventory_state=lambda req, ctx: state_records.append(req),
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
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record discovered sources")
        ),
    )

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.snapshot_changed is False
    assert result.new_report_urls == []
    assert uploads == []
    assert len(state_records) == 1
    assert state_records[0].snapshot_drive_file_id == "snapshot-1"
    assert state_records[0].snapshot_sha256 == snapshot_sha256
    assert state_records[0].route_kind == "browser_render"

def test_run_publisher_inventory_discovery_creates_missing_google_folder(
    run_context,
):
    settings = replace(_settings(), drive_parent_folder_id="parent-folder")
    ensured = []
    folder_updates = []
    deps = _dependencies(
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False, with_folder=False
        ),
        ensure_folder=lambda req, ctx: (
            ensured.append(req)
            or DriveFolderEnsureResponse(
                schema_version="1.0",
                folder=DriveFile(
                    schema_version="1.0",
                    file_id="created-publisher-folder",
                    name=req.folder_name,
                    modified_time=None,
                    md5_checksum=None,
                    mime_type="application/vnd.google-apps.folder",
                ),
                parent_folder_id=req.parent_folder_id,
                created=True,
            )
        ),
        update_publisher_google_folder=lambda req, ctx: (
            folder_updates.append(req)
            or PublisherGoogleFolderUpdateResponse(
                schema_version="1.0",
                publisher_name=req.publisher_name,
                google_folder=req.google_folder,
                updated_count=1,
                resolution_source="publisher_insights_url",
            )
        ),
    )

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.publisher_name == "Activate Consulting"
    assert ensured[0].parent_folder_id == "parent-folder"
    assert ensured[0].folder_name == "Activate Consulting"
    assert folder_updates[0].google_folder.endswith("/created-publisher-folder")

def test_run_publisher_inventory_discovery_requires_parent_for_missing_google_folder(
    run_context,
    assert_app_error,
):
    settings = _settings()
    deps = _dependencies(
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False, with_folder=False
        ),
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record discovered sources")
        ),
        upload_bytes=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not upload snapshot")
        ),
    )
    with pytest.raises(AppError) as err:
        run_publisher_inventory_discovery(
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )
    assert_app_error(
        err.value,
        code="publisher_inventory_google_folder_parent_missing",
        retryable=False,
    )

def test_run_publisher_inventory_discovery_rejects_non_meaningful_candidates_before_recording(
    run_context,
):
    settings = _settings()
    source_records = []
    uploads = []
    status_records = []
    deps = _dependencies(
        screen_publisher_inventory_candidates=lambda req, ctx: _screening_response(
            accepted_urls=set(),
            request=req,
        ),
        get_publisher_inventory_state=lambda req, ctx: _publisher_state(
            with_route=False, with_snapshot=False
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
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
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

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.new_report_urls == []
    assert source_records == []
    assert result.snapshot_changed is False
    assert uploads == []
    assert [record.status for record in status_records] == ["passed:no_report_assets"]

def test_run_publisher_inventory_discovery_quality_rejects_editorial_pages_before_recording(
    tmp_path,
    run_context,
):
    settings = PublisherInventorySettings(
        **{**_settings().__dict__, "reports_db": str(tmp_path / "reports.sqlite")}
    )
    source_records = []
    uploads = []
    status_records = []
    deps = _dependencies(
        qualify_publisher_inventory_candidates=lambda req, ctx: _quality_response(
            accepted_urls=set(),
            request=req,
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
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
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

    result = run_publisher_inventory_discovery(
        _request(settings),
        ctx=run_context,
        dependencies=deps,
    )

    assert result.new_report_urls == []
    assert source_records == []
    assert result.snapshot_changed is False
    assert uploads == []
    assert [record.status for record in status_records] == ["passed:no_report_assets"]

def test_run_publisher_inventory_discovery_rejects_material_shrinkage_without_new_assets(
    run_context,
    assert_app_error,
):
    settings = _settings()
    previous_urls = [
        f"https://www.activate.com/reports/report-{index}" for index in range(1, 11)
    ]
    current_urls = previous_urls[:5]
    snapshot_payload = _snapshot_json_for_urls(previous_urls)
    snapshot_sha256 = _snapshot_sha256_for_urls(previous_urls, run_context)
    uploads = []
    state_records = []
    status_records = []

    deps = _dependencies(
        discover_publisher_inventory=lambda req, ctx: PublisherInventoryServiceResponse(
            schema_version="1.0",
            source_url="https://www.activate.com/insights",
            normalized_url="https://www.activate.com/insights",
            route_kind="browser_render",
            route_summary="Open page 1, click next, extract cards.",
            final_page_url="https://www.activate.com/insights?page=2",
            used_route_hint=True,
            pages=[
                PublisherInventoryPage(
                    schema_version="1.0",
                    page_number=1,
                    page_url="https://www.activate.com/insights",
                ),
                PublisherInventoryPage(
                    schema_version="1.0",
                    page_number=2,
                    page_url="https://www.activate.com/insights?page=2",
                ),
            ],
            candidates=[
                PublisherInventoryRawCandidate(
                    schema_version="1.0",
                    url=item_url,
                    title=f"Existing Report {index}",
                    source_page_url=(
                        "https://www.activate.com/insights"
                        if index <= 3
                        else "https://www.activate.com/insights?page=2"
                    ),
                    discovered_on_page_number=1 if index <= 3 else 2,
                )
                for index, item_url in enumerate(current_urls, start=1)
            ],
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
            with_route=True,
            with_snapshot=True,
            snapshot_sha256=snapshot_sha256,
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
        record_publisher_inventory_state=lambda req, ctx: state_records.append(req),
        record_publisher_inventory_test_status=lambda req, ctx: status_records.append(
            req
        ),
        record_discovered_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("should not record discovered sources")
        ),
    )

    with pytest.raises(AppError) as err:
        run_publisher_inventory_discovery(
            _request(settings),
            ctx=run_context,
            dependencies=deps,
        )

    assert_app_error(
        err.value,
        code="publisher_inventory_browser_incomplete",
        retryable=False,
    )
    assert uploads == []
    assert state_records == []
    assert [record.status for record in status_records] == [
        "failed:publisher_inventory_browser_incomplete"
    ]

__all__ = [
    "test_run_publisher_inventory_discovery_reuses_idempotent_snapshot_and_source_steps",
    "test_run_publisher_inventory_discovery_reuses_idempotent_auxiliary_writes",
    "test_run_publisher_inventory_discovery_does_not_commit_raw_only_snapshot_drift",
    "test_run_publisher_inventory_discovery_creates_missing_google_folder",
    "test_run_publisher_inventory_discovery_requires_parent_for_missing_google_folder",
    "test_run_publisher_inventory_discovery_rejects_non_meaningful_candidates_before_recording",
    "test_run_publisher_inventory_discovery_quality_rejects_editorial_pages_before_recording",
    "test_run_publisher_inventory_discovery_rejects_material_shrinkage_without_new_assets",
]
