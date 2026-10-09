from __future__ import annotations

import logging
import sqlite3

from src.contracts.mailbox_acquisition import MailReportAcquisitionResult
from src.contracts.state import MailDeliveryRequestUpsertRequest
from src.orchestrators import workflow_control_orchestrator as workflow
from src.services.state_service import upsert_mail_delivery_request
from tests.test_workflow_control_orchestrator import (
    _browser_settings,
    _ctx,
    _events,
    _mailbox_settings,
)


def test_workflow_control_dispatches_due_mail_delivery_requests(
    tmp_path,
    caplog,
) -> None:
    caplog.set_level(logging.INFO, logger="market_lense.workflow_control_orchestrator")
    state_db = tmp_path / "state.sqlite"
    reports_db = tmp_path / "reports.sqlite"
    upsert = upsert_mail_delivery_request(
        MailDeliveryRequestUpsertRequest(
            schema_version="1.0",
            state_db=str(state_db),
            idempotency_key="mail:https://example.com/report:reports@example.com",
            source_url="https://example.com/report",
            report_title="Retail Trends 2026",
            publisher_name="Example Publisher",
            delivery_email="reports@example.com",
            requested_after_utc="2026-07-04T11:08:00Z",
            route_family="browser_email_form",
            publisher_id="publisher-1",
            source_identity_id="source-1",
            submission_confirmed_at_utc="2026-07-04T11:08:00Z",
        ),
        _ctx(),
    )
    calls = []

    def acquire(req, ctx):
        calls.append(req)
        return MailReportAcquisitionResult(
            schema_version="1.0",
            source_url=req.source_url,
            outcome="downloaded_attachment",
            mailbox_poll_count=1,
            selected_report_url=None,
            selected_message_id="msg-1",
            downloaded_file_path=str(tmp_path / "report.pdf"),
            report_download_result=None,
            acquisition_result_taxonomy="mailbox_attachment_pdf",
            seen_provider_message_ids=["msg-1"],
        )

    result = workflow.run_due_mail_delivery_requests(
        workflow.MailDeliveryWorkflowRunRequest(
            schema_version="1.0",
            state_db=str(state_db),
            reports_db=str(reports_db),
            mailbox_settings=_mailbox_settings(tmp_path),
            browser_download_settings=_browser_settings(tmp_path),
            now_utc="2026-07-04T11:09:00Z",
            limit=10,
        ),
        ctx=_ctx(),
        run_mail_report_acquisition_fn=acquire,
    )

    assert result.processed_count == 1
    assert result.succeeded_count == 1
    assert result.deferred_count == 0
    assert result.failed_count == 0
    assert result.results[0].request_id == upsert.request.request_id
    assert result.results[0].status == "succeeded"
    assert calls[0].seen_provider_message_ids == []
    events = _events(caplog)
    assert events[-1]["event"] == "workflow_mail_delivery_run_complete"
    assert events[-1]["fields"]["succeeded_count"] == 1


def test_due_mail_workflow_holds_legacy_request_without_submission_proof(
    tmp_path,
) -> None:
    state_db = tmp_path / "state.sqlite"
    upsert = upsert_mail_delivery_request(
        MailDeliveryRequestUpsertRequest(
            schema_version="1.0",
            state_db=str(state_db),
            idempotency_key="legacy-mail-request",
            source_url="https://example.com/report",
            report_title="Retail Trends 2026",
            publisher_name="Example Publisher",
            delivery_email="reports@example.com",
            requested_after_utc="2026-07-04T11:08:00Z",
            route_family="browser_email_form",
            publisher_id="publisher-1",
            source_identity_id="source-1",
            submission_confirmed_at_utc="2026-07-04T11:08:00Z",
        ),
        _ctx(),
    )
    with sqlite3.connect(state_db) as conn:
        conn.execute(
            """
            UPDATE mail_delivery_requests
            SET publisher_id='', source_identity_id='', submission_confirmed_at_utc=''
            WHERE id=?
            """,
            (upsert.request.request_id,),
        )

    calls = []

    def unexpected_poll(request, ctx):
        calls.append(request)
        raise AssertionError("unverified legacy request must not poll the mailbox")

    result = workflow.run_due_mail_delivery_requests(
        workflow.MailDeliveryWorkflowRunRequest(
            schema_version="1.0",
            state_db=str(state_db),
            reports_db=str(tmp_path / "reports.sqlite"),
            mailbox_settings=_mailbox_settings(tmp_path),
            browser_download_settings=_browser_settings(tmp_path),
            now_utc="2026-07-04T11:09:00Z",
            limit=10,
        ),
        ctx=_ctx(),
        run_mail_report_acquisition_fn=unexpected_poll,
    )

    assert result.processed_count == 0
    assert calls == []
