# ruff: noqa: F401,F403,F405
from __future__ import annotations

from ._shared import *  # noqa: F401,F403


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
        record_acquisition_attempt_resource=lambda req, ctx: (
            resource_records.append(req.summary) or SimpleNamespace()
        ),
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
    "test_run_report_download_does_not_record_source_for_email_outcome",
    "test_run_report_download_enqueues_mail_delivery_request_for_email_outcome",
    "test_run_report_download_does_not_enqueue_unconfirmed_email_required_outcome",
    "test_run_report_download_uses_mailbox_account_for_unattended_email_submission",
    "test_run_report_download_preflights_mailbox_before_email_form_submission",
    "test_fresh_hard_blocker_suppresses_before_browser_preflight",
]
