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

    assert len(upload_calls) == 2
    assert [call.file_name for call in upload_calls] == [
        "onsite_capture.html",
        "onsite_capture.html",
    ]


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


def test_run_report_download_enqueues_mail_delivery_request_for_email_outcome(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    mailbox_settings = MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="imap",
        output_dir=str(tmp_path / "mailbox"),
        search_window_minutes=120,
        max_results=10,
        poll_timeout_seconds=900.0,
        poll_interval_seconds=60.0,
        gmail_oauth_client_path="",
        gmail_oauth_token_path="",
        gmail_user_id="me",
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="reports@example.com",
        imap_password="secret",
        imap_mailbox="INBOX",
    )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: replace(
            _result(url="https://example.com/report", used_route_hint=False, path=None),
            outcome="email_requested",
            route_status="verified",
            blocked_reason=None,
            blocked_reason_detail=None,
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused",
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("email-requested flow should not persist a report source")
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
        preflight_mailbox_search=lambda req, ctx: MailboxSearchResult(
            schema_version="1.0",
            provider="imap",
            searched_at_utc="2026-07-04T11:00:00Z",
            query="preflight",
            messages=[],
        ),
        sleep_fn=lambda seconds: None,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            delivery_email="ops@example.com",
            report_title="Retail Trends 2026",
            publisher_name="Example Publisher",
            mailbox_settings=mailbox_settings,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    due = list_due_mail_delivery_requests(
        MailDeliveryRequestListDueRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            now_utc="2099-01-01T00:00:00Z",
            limit=10,
        ),
        run_context,
    )
    observations = list_workflow_control_observations(
        WorkflowControlObservationListRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            workflow="mail_acquisition",
            publisher="Example Publisher",
            limit=10,
        ),
        run_context,
    )

    assert response.outcome == "email_requested"
    assert len(due.requests) == 1
    assert due.requests[0].source_url == "https://example.com/report"
    assert due.requests[0].report_title == "Retail Trends 2026"
    assert due.requests[0].delivery_email == "ops@example.com"
    assert due.requests[0].status == "pending"
    assert due.requests[0].route_family == "browser_email_form"
    assert len(observations.observations) == 1
    assert observations.observations[0].outcome == "deferred"
    assert observations.observations[0].route == "browser_email_form"
    with sqlite3.connect(settings.reports_db) as conn:
        resource_row = conn.execute(
            """
            SELECT source_identity_id, source_identity_status
            FROM acquisition_attempt_resources
            """
        ).fetchone()
    assert resource_row == ("", "provisional")


def test_run_report_download_does_not_enqueue_unconfirmed_email_required_outcome(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    mailbox_settings = MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="imap",
        output_dir=str(tmp_path / "mailbox"),
        search_window_minutes=120,
        max_results=10,
        poll_timeout_seconds=900.0,
        poll_interval_seconds=60.0,
        gmail_oauth_client_path="",
        gmail_oauth_token_path="",
        gmail_user_id="me",
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="reports@example.com",
        imap_password="secret",
        imap_mailbox="INBOX",
    )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: replace(
            _result(url="https://example.com/report", used_route_hint=False, path=None),
            outcome="email_required",
            route_status="inferred",
            route_summary="Form still shows Please Wait; no confirmation observed.",
            blocked_reason=None,
            blocked_reason_detail=None,
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused",
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("email-required flow should not persist a report source")
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
        preflight_mailbox_search=lambda req, ctx: MailboxSearchResult(
            schema_version="1.0",
            provider="imap",
            searched_at_utc="2026-07-04T11:00:00Z",
            query="preflight",
            messages=[],
        ),
        sleep_fn=lambda seconds: None,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            delivery_email="ops@example.com",
            report_title="Retail Trends 2026",
            publisher_name="Example Publisher",
            mailbox_settings=mailbox_settings,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    due = list_due_mail_delivery_requests(
        MailDeliveryRequestListDueRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            now_utc="2099-01-01T00:00:00Z",
            limit=10,
        ),
        run_context,
    )
    observations = list_workflow_control_observations(
        WorkflowControlObservationListRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            workflow="mail_acquisition",
            publisher="Example Publisher",
            limit=10,
        ),
        run_context,
    )

    assert response.outcome == "email_required"
    assert due.requests == []
    assert observations.observations == []


def test_run_report_download_uses_mailbox_account_for_unattended_email_submission(
    tmp_path: Path,
    run_context,
) -> None:
    settings = replace(
        _settings(tmp_path),
        identity_profile=BrowserDownloadIdentity(
            schema_version="1.0",
            fields=[
                BrowserDownloadIdentityField(
                    schema_version="1.0",
                    key="work_email",
                    label="Work email",
                    value="personal@proton.me",
                    aliases=["email", "business email"],
                )
            ],
            delivery_emails=["personal@proton.me"],
        ),
    )
    mailbox_settings = MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="imap",
        output_dir=str(tmp_path / "mailbox"),
        search_window_minutes=120,
        max_results=10,
        poll_timeout_seconds=900.0,
        poll_interval_seconds=60.0,
        gmail_oauth_client_path="",
        gmail_oauth_token_path="",
        gmail_user_id="me",
        imap_host="imap.example.com",
        imap_port=993,
        imap_user="reports@marketbearing.eu",
        imap_password="secret",
        imap_mailbox="INBOX",
    )
    browser_requests = []

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: (
            browser_requests.append(req)
            or replace(
                _result(
                    url="https://example.com/report", used_route_hint=False, path=None
                ),
                outcome="email_requested",
                route_status="verified",
                blocked_reason=None,
                blocked_reason_detail=None,
            )
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused",
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("email-requested flow should not persist a report source")
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
        preflight_mailbox_search=lambda req, ctx: MailboxSearchResult(
            schema_version="1.0",
            provider="imap",
            searched_at_utc="2026-07-04T11:00:00Z",
            query="preflight",
            messages=[],
        ),
        sleep_fn=lambda seconds: None,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            report_title="Retail Trends 2026",
            publisher_name="Example Publisher",
            mailbox_settings=mailbox_settings,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    due = list_due_mail_delivery_requests(
        MailDeliveryRequestListDueRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            now_utc="2099-01-01T00:00:00Z",
            limit=10,
        ),
        run_context,
    )

    assert response.outcome == "email_requested"
    assert len(browser_requests) == 1
    assert browser_requests[0].delivery_email == "reports@marketbearing.eu"
    assert len(due.requests) == 1
    assert due.requests[0].delivery_email == "reports@marketbearing.eu"


def test_run_report_download_preflights_mailbox_before_email_form_submission(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    mailbox_settings = MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="imap",
        output_dir=str(tmp_path / "mailbox"),
        search_window_minutes=120,
        max_results=10,
        poll_timeout_seconds=900.0,
        poll_interval_seconds=60.0,
        gmail_oauth_client_path="",
        gmail_oauth_token_path="",
        gmail_user_id="me",
        imap_host="",
        imap_port=993,
        imap_user="",
        imap_password="",
        imap_mailbox="INBOX",
    )

    def _preflight_mailbox(req, ctx):
        raise AppError(
            code="mailbox_imap_credentials_missing",
            message="Mailbox credentials are incomplete",
            retryable=False,
            severity="error",
        )

    remembered_email_route = PublisherDownloadRouteResponse(
        schema_version="1.0",
        normalized_url="https://example.com/report",
        source_url="https://example.com/report",
        route_kind="email_delivery",
        route_summary="Submit the verified email form.",
        outcome="email_requested",
        route_family="browser_email_form",
        route_status="verified",
        resolved_target_url="https://example.com/report",
        route_steps=[],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url="https://example.com/report",
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url="https://example.com/report",
            final_page_title="Report",
            terminal_text_excerpt="Email delivery required.",
            artifact_url="https://example.com/report",
            artifact_kind="email_delivery",
            artifact_validation_status="blocked",
            artifact_validation_detail="Verified form requires a matching mailbox.",
            confirmation_signal_count=1,
            traversed_page_urls=["https://example.com/report"],
        ),
        browser_had_structured_result=True,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        updated_at=_fresh_route_memory_updated_at(),
        attempts=2,
        verified_successes=1,
        last_n_outcomes=["email_requested"],
        confidence_score=0.9,
    )

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: pytest.fail(
            "browser should not run when mailbox preflight fails"
        ),
        get_publisher_download_route=lambda req, ctx: remembered_email_route,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0",
            path=req.path,
            md5="unused",
        ),
        record_report_source=lambda req, ctx: pytest.fail("source should not record"),
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
        preflight_mailbox_search=_preflight_mailbox,
        sleep_fn=lambda seconds: None,
    )

    with pytest.raises(AppError) as exc_info:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                delivery_email="ops@example.com",
                mailbox_settings=mailbox_settings,
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "mailbox_imap_credentials_missing"


def test_fresh_hard_blocker_suppresses_before_browser_preflight(
    tmp_path: Path,
    run_context,
) -> None:
    settings = replace(
        _settings(tmp_path), usage_db_path=str(tmp_path / "usage.sqlite")
    )
    browser_requests = []
    suppression_requests = []
    resource_records = []
    remembered_blocker = PublisherDownloadRouteResponse(
        schema_version="1.0",
        normalized_url="https://example.com/report",
        source_url="https://example.com/report",
        route_kind="email_delivery",
        route_summary="The verified form rejected the configured business email.",
        outcome="email_required",
        route_family="browser_email_form",
        route_status="verified",
        resolved_target_url="https://example.com/report",
        route_steps=[],
        confirmation_evidence=BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="",
            submit_button_state="unchanged",
            form_disappeared=False,
            final_page_url="https://example.com/report",
        ),
        terminal_evidence=DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url="https://example.com/report",
            final_page_title="Report",
            terminal_text_excerpt="Business email required.",
            artifact_url="https://example.com/report",
            artifact_kind="email_delivery",
            artifact_validation_status="blocked",
            artifact_validation_detail="The form rejected the configured email.",
            confirmation_signal_count=1,
            traversed_page_urls=["https://example.com/report"],
            evidence_labels=["blocked", "blocked_email_domain"],
        ),
        browser_had_structured_result=True,
        used_candidate_pdf_url=False,
        used_candidate_source_page=False,
        blocked_reason="blocked_email_domain",
        blocked_reason_detail="Business email required.",
        updated_at=_fresh_route_memory_updated_at(),
        attempts=1,
        verified_successes=0,
        last_n_outcomes=["email_required"],
        confidence_score=1.0,
    )
    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: browser_requests.append(req),
        get_publisher_download_route=lambda req, ctx: remembered_blocker,
        record_publisher_download_route=lambda req, ctx: pytest.fail(
            "route recording must not run after suppression"
        ),
        file_md5=lambda req, ctx: pytest.fail("file hashing must not run"),
        record_report_source=lambda req, ctx: pytest.fail(
            "source recording must not run"
        ),
        upsert_browser_download_identity_fields=lambda req, ctx: pytest.fail(
            "identity update must not run"
        ),
        record_report_value_score=lambda req, ctx: pytest.fail(
            "value scoring must not run"
        ),
        evaluate_acquisition_route_suppression=lambda req, ctx: (
            suppression_requests.append(req)
            or pytest.fail("historical suppression must not run before exact blocker")
        ),
        record_acquisition_attempt_resource=lambda req, ctx: resource_records.append(
            req.summary
        )
        or SimpleNamespace(),
        sleep_fn=lambda seconds: None,
    )

    with pytest.raises(AppError) as exc_info:
        run_report_download(
            ReportDownloadOrchestratorRequest(
                schema_version="1.0",
                url="https://example.com/report",
                settings=settings,
                state_db=settings.state_db,
                reports_db=settings.reports_db,
                publisher_name="Example Publisher",
            ),
            ctx=run_context,
            dependencies=deps,
        )

    assert exc_info.value.code == "report_download_route_suppressed"
    assert browser_requests == []
    assert suppression_requests == []
    assert len(resource_records) == 1
    assert resource_records[0].browser_launches == 0
    assert resource_records[0].browser_model_calls == 0
    assert resource_records[0].avoided_operations == (
        "browser_launch",
        "browser_model_call",
    )


__all__ = [
    "test_run_report_download_is_idempotent_for_route_memory",
    "test_run_report_download_reuses_idempotent_source_record_and_drive_upload",
    "test_run_report_download_drive_upload_idempotency_is_scoped_by_report_url",
    "test_run_report_download_idempotency_allows_changed_artifact_for_same_url",
    "test_run_report_download_reuses_idempotent_route_record_and_identity_update",
    "test_run_report_download_does_not_record_source_for_email_outcome",
    "test_run_report_download_enqueues_mail_delivery_request_for_email_outcome",
    "test_run_report_download_does_not_enqueue_unconfirmed_email_required_outcome",
    "test_run_report_download_uses_mailbox_account_for_unattended_email_submission",
    "test_run_report_download_preflights_mailbox_before_email_form_submission",
    "test_fresh_hard_blocker_suppresses_before_browser_preflight",
]
