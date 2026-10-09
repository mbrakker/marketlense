# ruff: noqa: F401,F403,F405
from __future__ import annotations

from src.contracts.state import (
    MailDeliveryRequestByKeyGetRequest,
    MailDeliveryRequestUpsertRequest,
)
from src.services.state_service import (
    get_mail_delivery_request_by_key,
    upsert_mail_delivery_request,
)
from src.utils.idempotency import mail_delivery_request_idempotency_key

from ._shared import *  # noqa: F401,F403


def test_mail_submission_intent_precedes_browser_and_replay_does_not_resubmit(
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
        imap_user="ops@example.com",
        imap_password="secret",
        imap_mailbox="INBOX",
    )
    request = ReportDownloadOrchestratorRequest(
        schema_version="1.0",
        url="https://example.com/reports/download",
        settings=settings,
        state_db=settings.state_db,
        reports_db=settings.reports_db,
        delivery_email="ops@example.com",
        report_title="Retail Trends 2026",
        publisher_id="publisher-1",
        publisher_name="Example Publisher",
        source_identity_id="source-identity-1",
        mailbox_settings=mailbox_settings,
        mail_delivery_generation_id="workflow-generation-crash-window",
    )
    browser_result = replace(
        _result(url=request.url, used_route_hint=False, path=None),
        outcome="email_requested",
        route_status="verified",
        blocked_reason=None,
        blocked_reason_detail=None,
        confirmation_evidence=replace(
            _result(
                url=request.url, used_route_hint=False, path=None
            ).confirmation_evidence,
            submission_confirmed_at_utc="2026-07-04T10:59:00Z",
        ),
    )
    browser_calls: list[object] = []
    upsert_calls = 0

    def _download(req, ctx):
        browser_calls.append(req)
        return browser_result

    def _fail_confirmation(req, ctx):
        nonlocal upsert_calls
        upsert_calls += 1
        if upsert_calls == 2:
            raise AppError(
                code="test_confirmation_persistence_failed",
                message="Simulated durable confirmation write failure",
                retryable=False,
            )
        return upsert_mail_delivery_request(req, ctx)

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0", path=req.path, md5="unused"
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("email-requested flow must not persist a report source")
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
            searched_at_utc="2026-07-04T10:58:00Z",
            query="preflight",
            messages=[],
        ),
        upsert_mail_delivery_request=_fail_confirmation,
        sleep_fn=lambda seconds: None,
    )
    key = mail_delivery_request_idempotency_key(
        generation_id=request.mail_delivery_generation_id,
        source_url=request.url,
        delivery_email=request.delivery_email or "",
        source_identity_id=request.source_identity_id,
    )

    with pytest.raises(AppError) as first_error:
        run_report_download(request, ctx=run_context, dependencies=deps)
    intent = get_mail_delivery_request_by_key(
        MailDeliveryRequestByKeyGetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            idempotency_key=key,
        ),
        run_context,
    ).request
    assert first_error.value.code == "test_confirmation_persistence_failed"
    assert len(browser_calls) == 1
    assert intent.status == "submission_started"
    assert intent.requested_after_utc == ""
    assert intent.submission_confirmed_at_utc == ""

    with pytest.raises(AppError) as replay_error:
        run_report_download(request, ctx=run_context, dependencies=deps)

    assert replay_error.value.code == "mail_delivery_submission_in_progress"
    assert len(browser_calls) == 1


@pytest.mark.parametrize("mailbox_settings_enabled", [True, False])
def test_direct_email_submission_has_durable_identity_before_browser(
    tmp_path: Path,
    run_context,
    mailbox_settings_enabled: bool,
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
        imap_user="ops@example.com",
        imap_password="secret",
        imap_mailbox="INBOX",
    )
    request = ReportDownloadOrchestratorRequest(
        schema_version="1.0",
        url="https://example.com/reports/download",
        settings=settings,
        state_db=settings.state_db,
        reports_db=settings.reports_db,
        delivery_email="ops@example.com",
        report_title="Retail Trends 2026",
        publisher_name="Example Publisher",
        mailbox_settings=mailbox_settings if mailbox_settings_enabled else None,
        mail_delivery_generation_id="workflow-generation-direct-caller",
    )
    source_identity_id = hashlib.sha256(request.url.encode()).hexdigest()
    key = mail_delivery_request_idempotency_key(
        generation_id=request.mail_delivery_generation_id,
        source_url=request.url,
        delivery_email=request.delivery_email or "",
        source_identity_id=source_identity_id,
    )
    browser_result = replace(
        _result(url=request.url, used_route_hint=False, path=None),
        outcome="email_requested",
        route_status="verified",
        blocked_reason=None,
        blocked_reason_detail=None,
        confirmation_evidence=replace(
            _result(
                url=request.url, used_route_hint=False, path=None
            ).confirmation_evidence,
            submission_confirmed_at_utc="2026-07-04T10:59:00Z",
        ),
    )
    intents_seen_at_browser: list[object] = []

    def _download(req, ctx):
        intent = get_mail_delivery_request_by_key(
            MailDeliveryRequestByKeyGetRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                idempotency_key=key,
            ),
            ctx,
        ).request
        intents_seen_at_browser.append(intent)
        return browser_result

    deps = ReportDownloadDependencies(
        download_report_with_browser_use=_download,
        get_publisher_download_route=lambda req, ctx: None,
        record_publisher_download_route=lambda req, ctx: None,
        file_md5=lambda req, ctx: FileHashResponse(
            schema_version="1.0", path=req.path, md5="unused"
        ),
        record_report_source=lambda req, ctx: (_ for _ in ()).throw(
            AssertionError("email-requested flow must not persist a report source")
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
            searched_at_utc="2026-07-04T10:58:00Z",
            query="preflight",
            messages=[],
        ),
        sleep_fn=lambda seconds: None,
    )

    response = run_report_download(request, ctx=run_context, dependencies=deps)
    persisted = get_mail_delivery_request_by_key(
        MailDeliveryRequestByKeyGetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            idempotency_key=key,
        ),
        run_context,
    ).request

    assert response.outcome == "email_requested"
    assert len(intents_seen_at_browser) == 1
    assert intents_seen_at_browser[0].status == "submission_started"
    assert intents_seen_at_browser[0].requested_after_utc == ""
    assert intents_seen_at_browser[0].delivery_email == "ops@example.com"
    assert intents_seen_at_browser[0].report_title == "Retail Trends 2026"
    assert intents_seen_at_browser[0].publisher_name == "Example Publisher"
    assert intents_seen_at_browser[0].publisher_id == "host:example.com"
    assert intents_seen_at_browser[0].source_identity_id == source_identity_id
    assert persisted.status == "pending"
    assert persisted.requested_after_utc == "2026-07-04T10:59:00Z"
    assert persisted.submission_confirmed_at_utc == persisted.requested_after_utc


__all__ = [
    "test_mail_submission_intent_precedes_browser_and_replay_does_not_resubmit",
    "test_direct_email_submission_has_durable_identity_before_browser",
    "test_mail_submission_confirmation_cannot_rewrite_intent_identity",
]


def test_mail_submission_confirmation_cannot_rewrite_intent_identity(
    tmp_path: Path,
    run_context,
) -> None:
    settings = _settings(tmp_path)
    intent = MailDeliveryRequestUpsertRequest(
        schema_version="1.0",
        state_db=settings.state_db,
        idempotency_key="mail-delivery:immutable-intent",
        source_url="https://example.com/reports/download",
        report_title="Retail Trends 2026",
        publisher_name="Example Publisher",
        delivery_email="ops@example.com",
        requested_after_utc="",
        route_family="browser_email_form",
        publisher_id="publisher-1",
        source_identity_id="source-identity-1",
        status="submission_started",
    )
    upsert_mail_delivery_request(intent, run_context)

    with pytest.raises(AppError) as error:
        upsert_mail_delivery_request(
            replace(
                intent,
                report_title="Changed report title",
                publisher_name="Changed publisher",
                requested_after_utc="2026-07-04T10:59:00Z",
                submission_confirmed_at_utc="2026-07-04T10:59:00Z",
                status="pending",
            ),
            run_context,
        )

    persisted = get_mail_delivery_request_by_key(
        MailDeliveryRequestByKeyGetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            idempotency_key=intent.idempotency_key,
        ),
        run_context,
    ).request
    assert error.value.code == "mail_delivery_submission_identity_mismatch"
    assert persisted.status == "submission_started"
    assert persisted.report_title == "Retail Trends 2026"
    assert persisted.publisher_name == "Example Publisher"
