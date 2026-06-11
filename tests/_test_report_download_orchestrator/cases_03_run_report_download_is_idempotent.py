# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403

def test_run_report_download_is_idempotent_for_route_memory(
    tmp_path: Path,
    run_context,
    idempotency_guard,
) -> None:
    settings = _settings(tmp_path)
    file_path = Path(settings.output_dir)
    file_path.mkdir(parents=True, exist_ok=True)
    pdf_path = file_path / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.7 idempotent")

    def _download(req, ctx):
        return _result(
            url="https://example.com/report",
            used_route_hint=bool(req.route_hint),
            path=str(pdf_path),
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=get_publisher_download_route,
        record_publisher_download_route=record_publisher_download_route,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="idempotent-md5",
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
    )

    def _run_once():
        return run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    def _route_count() -> int:
        conn = sqlite3.connect(settings.reports_db)
        try:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM publishers
                WHERE insights_url=?
                  AND download_route_summary IS NOT NULL
                """,
                ("https://example.com/report",),
            ).fetchone()
        finally:
            conn.close()
        return int(row[0] if row else 0)

    first, second = idempotency_guard(_run_once, side_effect_count=_route_count)
    assert first.outcome == "downloaded"
    assert second.outcome == "downloaded"

def test_run_report_download_reuses_idempotent_source_record_and_drive_upload(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 idempotent upload")
    source_record_calls: list[object] = []
    upload_calls: list[object] = []

    def _record_source(req, ctx):
        source_record_calls.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=11,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    def _upload_local_file(req, ctx):
        upload_calls.append(req)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id="drive-file-1",
                name=req.file_name or Path(req.source_path).name,
                modified_time=None,
                md5_checksum="remote-md5",
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5="remote-md5",
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
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example",
                google_folder="folder123",
                resolution_source="publisher_insights_url",
            )
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[],
        ),
        upload_local_file=_upload_local_file,
        preflight_drive_write_access=_successful_drive_preflight,
    )

    first = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )
    second = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert first.outcome == "downloaded"
    assert second.outcome == "downloaded"
    assert len(source_record_calls) == 1
    assert len(upload_calls) == 1
    assert len(second.drive_uploads) == 1
    assert second.drive_uploads[0].status == "uploaded"
    assert second.drive_uploads[0].drive_file.file_id == "drive-file-1"

def test_run_report_download_drive_upload_idempotency_is_scoped_by_report_url(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    report_artifacts: dict[str, tuple[Path, Path, Path]] = {}
    for slug, payload in [("report-one", b"one"), ("report-two", b"two")]:
        artifact_dir = tmp_path / slug
        artifact_dir.mkdir(parents=True, exist_ok=True)
        onsite_path = artifact_dir / "onsite_capture.html"
        html_path = artifact_dir / "terminal_snapshot.html"
        screenshot_path = artifact_dir / "terminal_screenshot.png"
        onsite_path.write_bytes(b"<html>" + payload + b"</html>")
        html_path.write_bytes(b"<html>snapshot " + payload + b"</html>")
        screenshot_path.write_bytes(b"png-" + payload)
        report_artifacts[f"https://example.com/{slug}"] = (
            onsite_path,
            html_path,
            screenshot_path,
        )
    upload_calls: list[object] = []

    def _download(req, ctx):
        onsite_path, html_path, screenshot_path = report_artifacts[req.url]
        return _captured_result(
            url=req.url,
            onsite_path=str(onsite_path),
            html_snapshot_path=str(html_path),
            screenshot_path=str(screenshot_path),
        )

    def _upload_local_file(req, ctx):
        upload_calls.append(req)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=f"drive-file-{len(upload_calls)}",
                name=req.file_name or Path(req.source_path).name,
                modified_time=None,
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
                publisher_name="Example",
                google_folder="folder123",
                resolution_source="publisher_insights_url",
            )
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[],
        ),
        upload_local_file=_upload_local_file,
        preflight_drive_write_access=_successful_drive_preflight,
    )

    for url in report_artifacts:
        response = run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url=url,
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )
        assert response.outcome == "captured"

    assert len(upload_calls) == 6
    assert [call.file_name for call in upload_calls].count(
        "terminal_screenshot.png"
    ) == 2

def test_run_report_download_idempotency_allows_changed_artifact_for_same_url(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    source_record_calls: list[object] = []
    upload_calls: list[object] = []

    def _record_source(req, ctx):
        source_record_calls.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=len(source_record_calls),
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    def _upload_local_file(req, ctx):
        upload_calls.append(req)
        return DriveUploadLocalFileResponse(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=f"drive-file-{len(upload_calls)}",
                name=req.file_name or Path(req.source_path).name,
                modified_time=None,
                md5_checksum=_md5_for_path(Path(req.source_path)),
                mime_type=req.mime_type,
            ),
            source_path=req.source_path,
            size=Path(req.source_path).stat().st_size,
            md5=_md5_for_path(Path(req.source_path)),
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
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
        get_report_download_drive_folder=lambda req, ctx: (
            ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name="Example",
                google_folder="folder123",
                resolution_source="publisher_insights_url",
            )
        ),
        list_files_in_folder=lambda req, ctx: DriveFolderFileListResponse(
            schema_version="1.0",
            folder_id=req.folder_id,
            files=[],
        ),
        upload_local_file=_upload_local_file,
        preflight_drive_write_access=_successful_drive_preflight,
    )

    for content in [b"%PDF-1.7 first", b"%PDF-1.7 second"]:
        pdf_path.write_bytes(content)
        response = run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
            ),
            ctx=run_context,
            dependencies=deps,
        )
        assert response.outcome == "downloaded"

    assert len(source_record_calls) == 2
    assert len(upload_calls) == 2
    assert source_record_calls[0].md5 != source_record_calls[1].md5

def test_run_report_download_reuses_idempotent_route_record_and_identity_update(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    Path(settings.identity_config_path).write_text(
        "\n".join(
            [
                "schema_version: '1.0'",
                "fields:",
                "  - schema_version: '1.0'",
                "    key: work_email",
                "    label: Work email",
                "    value: ops@example.com",
                "    aliases:",
                "      - email",
                "delivery_emails: []",
                "publisher_overrides: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    route_record_calls: list[object] = []
    identity_update_calls: list[object] = []

    def _record_route(req, ctx):
        route_record_calls.append(req)
        return record_publisher_download_route(req, ctx)

    def _upsert_identity(req, ctx):
        identity_update_calls.append(req)
        return upsert_browser_download_identity_fields(req, ctx)

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=None,
        ),
        get_publisher_download_route=get_publisher_download_route,
        record_publisher_download_route=_record_route,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused-md5",
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("email-required flow should not persist a report source")
        ),
        upsert_browser_download_identity_fields=_upsert_identity,
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )

    first = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )
    second = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert first.outcome == "email_required"
    assert second.outcome == "email_required"
    assert len(route_record_calls) == 1
    assert len(identity_update_calls) == 1

    with sqlite3.connect(settings.reports_db) as conn:
        publisher_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM publishers
            WHERE normalized_insights_url=?
              AND download_route_summary IS NOT NULL
            """,
            ("https://example.com/report",),
        ).fetchone()
        history_rows = conn.execute(
            """
            SELECT COUNT(*)
            FROM publisher_download_route_history
            WHERE normalized_url=?
            """,
            ("https://example.com/report",),
        ).fetchone()

    assert int(publisher_rows[0] if publisher_rows else 0) == 1
    assert int(history_rows[0] if history_rows else 0) == 1

    identity_yaml = Path(settings.identity_config_path).read_text(encoding="utf-8")
    assert "key: name" in identity_yaml
    assert "key: business" in identity_yaml

def test_run_report_download_does_not_record_source_for_email_outcome(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    source_record_calls: list[object] = []

    def _record_source(req, ctx):
        source_record_calls.append(req)
        return ReportSourceRecordResponse(
            schema_version="1.0",
            record_id=1,
            source_domain=req.source_domain,
            report_name=req.report_name,
            landing_page_url=req.landing_page_url,
            downloaded_at_utc=req.downloaded_at_utc,
            md5=req.md5,
        )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url="https://example.com/report",
            used_route_hint=False,
            path=None,
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused",
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
        record_report_value_score=lambda req, ctx: None,
        sleep_fn=lambda seconds: None,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "email_required"
    assert source_record_calls == []

def test_run_report_download_uploads_downloaded_pdf_to_publisher_drive_folder(
    tmp_path: Path,
    caplog,
    run_context,
    assert_logs_have_required_fields,
) -> None:
    settings = _drive_enabled_settings(_settings(tmp_path))
    pdf_path = Path(settings.output_dir) / "report.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 acquired")
    uploaded_requests = []

    def _upload_file(req, ctx):
        uploaded_requests.append(req)
        return DriveUploadLocalFileResponse(
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
        upload_local_file=_upload_file,
        preflight_drive_write_access=_successful_drive_preflight,
    )
    caplog.set_level(logging.INFO, logger="market_lense.report_download_orchestrator")

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
    assert len(response.drive_uploads) == 1
    assert response.drive_uploads[0].folder_id == "folder123"
    assert response.drive_uploads[0].status == "uploaded"
    assert response.drive_uploads[0].drive_file.file_id == "drive-file-1"
    assert uploaded_requests[0].source_path == str(pdf_path)
    assert uploaded_requests[0].mime_type == "application/pdf"
    assert_logs_have_required_fields(
        _events(caplog, "market_lense.report_download_orchestrator")
    )

__all__ = [
    "test_run_report_download_is_idempotent_for_route_memory",
    "test_run_report_download_reuses_idempotent_source_record_and_drive_upload",
    "test_run_report_download_drive_upload_idempotency_is_scoped_by_report_url",
    "test_run_report_download_idempotency_allows_changed_artifact_for_same_url",
    "test_run_report_download_reuses_idempotent_route_record_and_identity_update",
    "test_run_report_download_does_not_record_source_for_email_outcome",
    "test_run_report_download_uploads_downloaded_pdf_to_publisher_drive_folder",
]
