# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


def test_run_report_download_defers_mailbox_preflight_until_an_email_route(
    tmp_path: Path,
    run_context,
) -> None:
    """A direct PDF probe must not be blocked by irrelevant mailbox credentials."""
    settings = _settings(tmp_path)
    pdf_path = Path(settings.output_dir) / "direct.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-1.7 direct")
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
        raise AssertionError("direct PDF acquisition must not preflight the mailbox")

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=lambda req, ctx: _result(
            url=req.url,
            used_route_hint=bool(req.route_hint),
            path=str(pdf_path),
        ),
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0", path=req.path, md5=_md5_for_path(Path(req.path))
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
        preflight_mailbox_search=_preflight_mailbox,
        sleep_fn=lambda seconds: None,
    )

    response = run_report_download(
        ReportDownloadOrchestratorRequest(
            schema_version="1.0",
            url="https://example.com/report.pdf",
            settings=settings,
            state_db=settings.state_db,
            reports_db=settings.reports_db,
            mailbox_settings=mailbox_settings,
        ),
        ctx=run_context,
        dependencies=deps,
    )

    assert response.outcome == "downloaded"


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
