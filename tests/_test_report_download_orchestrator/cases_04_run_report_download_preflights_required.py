# ruff: noqa: F401,F403,F405,I001
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_run_report_download_preflights_required_drive_archive_before_acquisition(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 acquired")
    calls: list[str] = []

    def _preflight(req, ctx):
        calls.append("preflight")
        assert req.folder_id == "folder123"
        assert req.service_account_path == "/tmp/fake-sa.json"
        assert req.auth_mode == "service_account"
        return DriveWritePreflightResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            auth_mode=req.auth_mode,
            credentials_refreshed=False,
            scopes_verified=True,
            folder_access_verified=True,
            write_access_verified=True,
        )

    def _download(req, ctx):
        calls.append("download")
        return _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(pdf_path),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        upload_local_file=lambda req, ctx: DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="drive-file-1",
                name=req.file_name,
                modified_time="2026-04-22T00:00:00Z",
                md5_checksum=_md5_for_path(Path(req.source_path)),
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=_md5_for_path(Path(req.source_path)),
        ),
        preflight_drive_write_access=_preflight,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            publisher_google_folder="https://drive.google.com/drive/folders/folder123",
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "downloaded"
    assert calls[:2] == ["preflight", "download"]

def test_run_report_download_creates_missing_publisher_drive_folder_before_upload(
    tmp_path: Path,
    run_context,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 acquired")
    calls: list[str] = []
    updated_folders: list[str] = []

    def _download(req, ctx):
        calls.append("download")
        return _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(pdf_path),
        )

    def _ensure_folder(req, ctx):
        calls.append("ensure_folder")
        assert req.parent_folder_id == "root-folder"
        assert req.folder_name == "Example Publisher"
        return DriveFolderEnsureResponse(
            schema_version="1.0",
            folder=DriveFile(
                schema_version="1.0",
                file_id="created-publisher-folder",
                name=req.folder_name,
                modified_time="2026-06-03T00:00:00Z",
                md5_checksum=None,
                mime_type="application/vnd.google-apps.folder",
            ),
            parent_folder_id=req.parent_folder_id,
            created=True,
        )

    def _update_folder(req, ctx):
        calls.append("update_folder")
        updated_folders.append(req.google_folder)
        assert req.publisher_name == "Example Publisher"
        assert req.publisher_insights_url == "https://example.com/insights"
        return PublisherGoogleFolderUpdateResponse(
            schema_version="1.0",
            publisher_name=req.publisher_name,
            google_folder=req.google_folder,
            updated_count=1,
            resolution_source="publisher_insights_url",
        )

    def _preflight(req, ctx):
        calls.append("preflight")
        assert req.folder_id == "created-publisher-folder"
        return _successful_drive_preflight(req, ctx)

    def _upload(req, ctx):
        calls.append("upload")
        assert req.folder_id == "created-publisher-folder"
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="drive-file-1",
                name=req.file_name,
                modified_time="2026-06-03T00:00:00Z",
                md5_checksum=_md5_for_path(Path(req.source_path)),
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=_md5_for_path(Path(req.source_path)),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example Publisher",
                google_folder="",
                resolution_source="publisher_insights_url",
            )
        ),
        ensure_folder=_ensure_folder,
        update_publisher_google_folder=_update_folder,
        preflight_drive_write_access=_preflight,
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        upload_local_file=_upload,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            publisher_insights_url="https://example.com/insights",
        ),
        ctx=run_context,
        dependencies=deps,
    )

    events = _events(caplog, "market_lense.report_download_orchestrator")
    assert response.outcome == "downloaded"
    assert response.drive_uploads[0].folder_id == "created-publisher-folder"
    assert calls[:4] == ["ensure_folder", "update_folder", "preflight", "download"]
    assert updated_folders == [
        "https://drive.google.com/drive/folders/created-publisher-folder"
    ]
    assert any(
        event.get("event") == "report_download_drive_folder_created"
        for event in events
    )
    assert_logs_have_required_fields(events)

def test_run_report_download_missing_publisher_folder_requires_parent_folder(
    tmp_path: Path,
    run_context,
    assert_app_error,
) -> None:
    settings = replace(
        _drive_enabled_settings(_settings(tmp_path)),
        drive_upload_parent_folder_id="",
    )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("download should not start without archive folder")
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: (_ for _ in ()).throw(AssertionError("unused")),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("unused")
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("unused")
        ),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example Publisher",
                google_folder="",
                resolution_source="publisher_insights_url",
            )
        ),
    )

    with pytest.raises(AppError) as excinfo:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                publisher_insights_url="https://example.com/insights",
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert_app_error(
        excinfo.value,
        code="report_download_drive_folder_parent_missing",
        retryable=False,
    )

def test_run_report_download_required_drive_preflight_failure_blocks_acquisition(
    tmp_path: Path,
    run_context,
    assert_app_error,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))

    def _preflight(req, ctx):
        raise AppError(
            code="drive_preflight_no_write_access",
            message="Drive folder is not writable",
            retryable=False,
            severity="error",
            context={"folder_id": req.folder_id},
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("download should not start after preflight failure")
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: (_ for _ in ()).throw(AssertionError("unused")),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("unused")
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("unused")
        ),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        preflight_drive_write_access=_preflight,
    )

    with pytest.raises(AppError) as excinfo:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                publisher_google_folder=(
                    "https://drive.google.com/drive/folders/folder123"
                ),
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert_app_error(
        excinfo.value, code="drive_preflight_no_write_access", retryable=False
    )

def test_run_report_download_uploads_only_report_artifacts(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    artifact_dir = Path(settings.output_dir)
    onsite_path = artifact_dir / "onsite_capture.html"
    html_snapshot_path = artifact_dir / "terminal.html"
    screenshot_path = artifact_dir / "terminal.png"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    onsite_path.write_text("<html>onsite</html>", encoding="utf-8")
    html_snapshot_path.write_text("<html>terminal</html>", encoding="utf-8")
    screenshot_path.write_bytes(b"png-bytes")
    uploaded_paths: list[str] = []
    recorded_sources: list[object] = []
    recorded_identity_observations: list[object] = []

    def _upload_file(req, ctx):
        uploaded_paths.append(req.source_path)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=f"drive-{Path(req.source_path).stem}",
                name=req.file_name,
                modified_time="2026-04-22T00:00:00Z",
                md5_checksum=_md5_for_path(Path(req.source_path)),
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=_md5_for_path(Path(req.source_path)),
        )

    def _record_source(req, ctx):
        recorded_sources.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    def _record_source_identity_observation(req, ctx):
        recorded_identity_observations.append(req)
        return SimpleNamespace(
            created=True,
            resolution=SimpleNamespace(
                source_identity_id="source-identity-onsite",
                identity_status="resolved",
                publication_date_status="unknown",
                source_metadata_hash="source-metadata-hash",
            ),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _captured_result(
            url="https://example.com/report",
            onsite_path=str(onsite_path),
            html_snapshot_path=str(html_snapshot_path),
            screenshot_path=str(screenshot_path),
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=_record_source,
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_source_identity_observation=_record_source_identity_observation,
        score_report_value=lambda req, ctx: SimpleNamespace(
            overall_score=1.0,
            value_band="high",
            components=(),
            rationale="test score",
        ),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example Publisher",
                google_folder="folder456",
                resolution_source="publisher_insights_url",
            )
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        upload_local_file=_upload_file,
        preflight_drive_write_access=_successful_drive_preflight,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
                reports_db=settings.reports_db,
                publisher_insights_url="https://example.com/insights",
                report_title="On-site report title",
                publisher_name="Example Publisher",
            ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "captured"
    assert uploaded_paths == [str(onsite_path)]
    assert [item.status for item in response.drive_uploads] == ["uploaded"]
    assert response.drive_uploads[0].mime_type == "text/html"
    assert response.terminal_evidence.html_snapshot_path == str(html_snapshot_path)
    assert response.terminal_evidence.screenshot_path == str(screenshot_path)
    assert [item.md5 for item in recorded_sources] == [_md5_for_path(onsite_path)]
    assert [item.report_name for item in recorded_sources] == ["On-site report title"]
    assert [item.publisher_name for item in recorded_sources] == ["Example Publisher"]
    assert len(recorded_identity_observations) == 1
    assert (
        recorded_identity_observations[0].observation.publisher_name
        == "Example Publisher"
    )
    assert (
        recorded_identity_observations[0].observation.content_hash
        == f"md5:{_md5_for_path(onsite_path)}"
    )

def test_run_report_download_deduplicates_equivalent_drive_artifact_paths(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    redundant_dir = pdf_path.parent / "redundant"
    redundant_dir.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 rendered onsite report")
    equivalent_pdf_path = redundant_dir / ".." / pdf_path.name
    uploaded_paths: list[str] = []

    def _upload_file(req, ctx):
        uploaded_paths.append(req.source_path)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="drive-report",
                name=req.file_name,
                modified_time="2026-04-22T00:00:00Z",
                md5_checksum=_md5_for_path(Path(req.source_path)),
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=_md5_for_path(Path(req.source_path)),
        )

    def _download(req, ctx):
        return replace(
            _result(
                url="https://example.com/year-in-review",
                used_route_hint=False,
                path=str(pdf_path),
            ),
            onsite_capture_path=str(equivalent_pdf_path),
            onsite_capture_format="browser_rendered_pdf",
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5=_md5_for_path(Path(req.path)),
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example Publisher",
                google_folder="folder456",
                resolution_source="publisher_insights_url",
            )
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0", folder_id=req.folder_id, files=[]
        ),
        upload_local_file=_upload_file,
        preflight_drive_write_access=_successful_drive_preflight,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/year-in-review",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            publisher_insights_url="https://example.com/insights",
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert uploaded_paths == [str(pdf_path)]
    assert len(response.drive_uploads) == 1
    assert response.drive_uploads[0].file_name == "report.pdf"

def test_run_report_download_skips_duplicate_drive_file_by_name_and_md5(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 duplicate")
    md5 = _md5_for_path(pdf_path)
    upload_calls: list[object] = []

    def _upload_file(req, ctx):
        upload_calls.append(req)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="unexpected-upload",
                name=req.file_name,
                modified_time="2026-04-22T00:00:00Z",
                md5_checksum=md5,
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=md5,
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=str(pdf_path),
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0", path=req.path, md5=md5
        ),
        record_report_source=lambda req, ctx: ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: type(
            "IdentityUpdate",
            (),
            {
                "path": settings.identity_config_path,
                "added_field_keys": [],
                "total_fields": len(settings.identity_profile.fields),
            },
        )(),
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[
                DriveFile(
                    schema_version="1.0",
                    file_id="existing-drive-file",
                    name="report.pdf",
                    modified_time="2026-04-22T00:00:00Z",
                    md5_checksum=md5,
                    mime_type="application/pdf",
                )
            ],
        ),
        upload_local_file=_upload_file,
        preflight_drive_write_access=_successful_drive_preflight,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            publisher_google_folder="folder123",
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert upload_calls == []
    assert response.drive_uploads[0].status == "skipped_duplicate"
    assert response.drive_uploads[0].drive_file.file_id == "existing-drive-file"

__all__ = [
    "test_run_report_download_preflights_required_drive_archive_before_acquisition",
    "test_run_report_download_creates_missing_publisher_drive_folder_before_upload",
    "test_run_report_download_missing_publisher_folder_requires_parent_folder",
    "test_run_report_download_required_drive_preflight_failure_blocks_acquisition",
    "test_run_report_download_uploads_only_report_artifacts",
    "test_run_report_download_deduplicates_equivalent_drive_artifact_paths",
    "test_run_report_download_skips_duplicate_drive_file_by_name_and_md5",
]
