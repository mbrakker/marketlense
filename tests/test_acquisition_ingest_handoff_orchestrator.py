from __future__ import annotations

from dataclasses import replace
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pytest

from src.contracts.acquisition_handoff import VerifiedAcquisitionIngestHandoffRequest
from src.contracts.mailbox_acquisition import (
    MailboxAcquisitionSettings,
    MailboxAttachment,
    MailboxAttachmentMaterializeRequest,
)
from src.contracts.report_store import ReportMetadataGetRequest
from src.contracts.workflow_queue import WorkflowJob
from src.orchestrators.acquisition_ingest_handoff_orchestrator import (
    build_source_ingest_submission_from_verified_acquisition,
)
from src.services.mailbox_acquisition_service import materialize_mailbox_attachments
from src.services.report_store_service import get_metadata
from src.services.workflow_queue_service import enqueue_workflow_job
from src.utils.errors import AppError
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="acquisition-ingest-handoff-test")


def _parent_job() -> WorkflowJob:
    return WorkflowJob(
        schema_version="1.0",
        job_id="acquisition-job-1",
        queue_name="report_acquisition",
        job_type="report_acquisition.v1",
        job_schema_version="1.0",
        workflow_version="1.0",
        root_workflow_id="workflow-root-1",
        parent_job_id="",
        trigger_event_id="trigger-1",
        correlation_id="correlation-1",
        entity_type="report",
        entity_id="candidate-1",
        publisher_id="publisher-1",
        source_identity_id="",
        report_id="",
        input_reference="https://publisher.example/reports/market-outlook",
        input_content_hash="candidate-hash",
        required_artifact_references=[],
        output_reference="",
        output_content_hash="",
        idempotency_key="acquisition-job-1",
        deduplication_scope="test",
        priority=0,
        status="running",
        available_at_utc="2026-07-18T00:00:00+00:00",
        attempt_count=1,
        max_attempts=3,
        lease_owner="worker-1",
        lease_expires_at_utc="2026-07-18T00:01:00+00:00",
        heartbeat_at_utc="2026-07-18T00:00:00+00:00",
        budget_profile="report_acquisition",
        execution_plan_hash="plan-1",
        prompt_policy_version="",
        processing_version="acquisition-v1",
        created_at_utc="2026-07-18T00:00:00+00:00",
        updated_at_utc="2026-07-18T00:00:00+00:00",
        started_at_utc="2026-07-18T00:00:00+00:00",
        completed_at_utc="",
        error_code="",
        error_message_summary="",
        error_retryable=False,
        terminal_reason="",
        remediation_id="",
    )


def _fixture(name: str) -> str:
    path = Path("tests/fixtures/pdf_benchmark/golden") / name
    assert path.is_file(), f"retained benchmark PDF missing: {path}"
    return str(path.resolve())


def _request(
    reports_db: str,
    artifact: str,
    *,
    source_url: str,
    route: str,
    report_id: str = "",
    expected_content_hash: str = "",
) -> VerifiedAcquisitionIngestHandoffRequest:
    return VerifiedAcquisitionIngestHandoffRequest(
        schema_version="1.0",
        reports_db=reports_db,
        source_artifact_reference=artifact,
        expected_content_hash=expected_content_hash,
        source_url=source_url,
        report_title="2026 Market Outlook",
        publisher_name="Publisher Example",
        publisher_id="publisher-1",
        acquisition_route=route,
        processing_version="parser-ocr.v1",
        report_id=report_id,
    )


def _mailbox_settings(tmp_path: Path) -> MailboxAcquisitionSettings:
    return MailboxAcquisitionSettings(
        schema_version="1.0",
        provider="gmail",
        output_dir=str(tmp_path / "mailbox"),
        search_window_minutes=120,
        max_results=10,
        poll_timeout_seconds=120.0,
        poll_interval_seconds=30.0,
        gmail_oauth_client_path="client.json",
        gmail_oauth_token_path="token.json",
        gmail_user_id="me",
        imap_host="",
        imap_port=993,
        imap_user="",
        imap_password="",
        imap_mailbox="INBOX",
    )


def test_verified_acquisition_handoff_preserves_identity_and_deduplicates_content(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    state_db = str(tmp_path / "state.sqlite")
    parent = _parent_job()
    capgemini = _fixture("CAPGEMINI - 2026-Retail-Trends_ACIG.pdf")
    ias = _fixture("IAS - Industry_Pulse_Report_2026_ACIG.pdf")

    direct = build_source_ingest_submission_from_verified_acquisition(
        _request(
            reports_db,
            capgemini,
            source_url="https://publisher.example/reports/market-outlook-direct",
            route="direct_pdf",
        ),
        parent_job=parent,
        ctx=_ctx(),
    )
    browser_same_content = build_source_ingest_submission_from_verified_acquisition(
        _request(
            reports_db,
            capgemini,
            source_url="https://mirror.publisher.example/reports/market-outlook-browser",
            route="browser_capture",
        ),
        parent_job=parent,
        ctx=_ctx(),
    )
    mailbox_different_content = (
        build_source_ingest_submission_from_verified_acquisition(
            _request(
                reports_db,
                ias,
                source_url="https://publisher.example/reports/market-outlook-mailbox",
                route="mailbox_delivery",
            ),
            parent_job=parent,
            ctx=_ctx(),
        )
    )

    assert direct.payload.source_content_hash
    assert (
        direct.payload.source_content_hash
        == browser_same_content.payload.source_content_hash
    )
    assert direct.source_identity_id == browser_same_content.source_identity_id
    assert direct.report_id == browser_same_content.report_id
    assert direct.report_id.startswith("acquired-")
    assert ":" not in direct.report_id
    assert direct.source_identity_id != direct.report_id
    assert direct.idempotency_key == browser_same_content.idempotency_key
    assert (
        mailbox_different_content.payload.source_content_hash
        != direct.payload.source_content_hash
    )
    assert mailbox_different_content.source_identity_id != direct.source_identity_id
    assert mailbox_different_content.report_id != direct.report_id

    first_job, first_created = enqueue_workflow_job(state_db, direct, _ctx())
    duplicate_job, duplicate_created = enqueue_workflow_job(
        state_db, browser_same_content, _ctx()
    )
    mailbox_job, mailbox_created = enqueue_workflow_job(
        state_db, mailbox_different_content, _ctx()
    )
    assert first_created is True
    assert duplicate_created is False
    assert duplicate_job.job_id == first_job.job_id
    changed_compatibility = replace(
        browser_same_content,
        payload=replace(
            browser_same_content.payload,
            parser_ocr_compatibility_version="parser-ocr.v2",
        ),
    )
    with pytest.raises(AppError) as conflict:
        enqueue_workflow_job(state_db, changed_compatibility, _ctx())
    assert conflict.value.code == "workflow_queue_idempotency_conflict"
    assert mailbox_created is True
    assert mailbox_job.job_id != first_job.job_id

    direct_metadata = get_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0", db_path=reports_db, file_id=direct.report_id
        ),
        _ctx(),
    )
    mailbox_metadata = get_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0",
            db_path=reports_db,
            file_id=mailbox_different_content.report_id,
        ),
        _ctx(),
    )
    assert direct_metadata is not None
    assert direct_metadata.source_identity_id == direct.source_identity_id
    assert mailbox_metadata is not None
    assert (
        mailbox_metadata.source_identity_id
        == mailbox_different_content.source_identity_id
    )


def test_verified_acquisition_handoff_fails_closed_on_hash_or_report_conflict(
    tmp_path,
) -> None:
    reports_db = str(tmp_path / "reports.sqlite")
    parent = _parent_job()
    capgemini = _fixture("CAPGEMINI - 2026-Retail-Trends_ACIG.pdf")
    ias = _fixture("IAS - Industry_Pulse_Report_2026_ACIG.pdf")

    with pytest.raises(AppError, match="no longer matches") as mismatch:
        build_source_ingest_submission_from_verified_acquisition(
            _request(
                reports_db,
                capgemini,
                source_url="https://publisher.example/reports/market-outlook",
                route="direct_pdf",
                expected_content_hash="0" * 32,
            ),
            parent_job=parent,
            ctx=_ctx(),
        )
    assert mismatch.value.code == "acquisition_ingest_hash_mismatch"

    build_source_ingest_submission_from_verified_acquisition(
        _request(
            reports_db,
            capgemini,
            source_url="https://publisher.example/reports/market-outlook",
            route="direct_pdf",
            report_id="retained-drive-file-1",
        ),
        parent_job=parent,
        ctx=_ctx(),
    )
    with pytest.raises(
        AppError, match="conflicts with the persisted report ID"
    ) as conflict:
        build_source_ingest_submission_from_verified_acquisition(
            _request(
                reports_db,
                ias,
                source_url="https://publisher.example/reports/market-outlook-revision",
                route="mailbox_delivery",
                report_id="retained-drive-file-1",
            ),
            parent_job=parent,
            ctx=_ctx(),
        )
    assert conflict.value.code == "acquisition_ingest_report_content_conflict"


def test_mailbox_zip_candidate_failure_keeps_valid_pdf_eligible_for_ingest(
    tmp_path,
) -> None:
    source_pdf = Path(_fixture("CAPGEMINI - 2026-Retail-Trends_ACIG.pdf"))
    source_pdf_bytes = source_pdf.read_bytes()
    archive_buffer = BytesIO()
    with ZipFile(archive_buffer, "w") as archive:
        archive.writestr("nested/retail-trends-2026.pdf", source_pdf_bytes)

    response = materialize_mailbox_attachments(
        MailboxAttachmentMaterializeRequest(
            schema_version="1.0",
            settings=_mailbox_settings(tmp_path),
            provider_message_id="mailbox-zip-handoff",
            attachments=[
                MailboxAttachment(
                    schema_version="1.0",
                    file_name="broken.zip",
                    content_type="application/zip",
                    payload=b"malformed zip",
                ),
                MailboxAttachment(
                    schema_version="1.0",
                    file_name="delivery.zip",
                    content_type="application/zip",
                    payload=archive_buffer.getvalue(),
                ),
            ],
        ),
        _ctx(),
    )

    assert response.schema_version == "2.0"
    assert [failure.error_code for failure in response.failures] == [
        "mailbox_zip_invalid"
    ]
    assert response.failures[0].schema_version == "1.0"
    assert response.failures[0].attachment_index == 0
    assert len(response.artifacts) == 1
    artifact = response.artifacts[0]
    assert Path(artifact.path).read_bytes() == source_pdf_bytes

    submission = build_source_ingest_submission_from_verified_acquisition(
        _request(
            str(tmp_path / "reports.sqlite"),
            artifact.path,
            source_url="https://publisher.example/reports/market-outlook-mailbox",
            route="mailbox_delivery",
        ),
        parent_job=_parent_job(),
        ctx=_ctx(),
    )
    assert submission.payload.source_content_hash

    rejected_only = materialize_mailbox_attachments(
        MailboxAttachmentMaterializeRequest(
            schema_version="1.0",
            settings=_mailbox_settings(tmp_path),
            provider_message_id="mailbox-zip-rejected-only",
            attachments=[
                MailboxAttachment(
                    schema_version="1.0",
                    file_name="broken.zip",
                    content_type="application/zip",
                    payload=b"malformed zip",
                )
            ],
        ),
        _ctx(),
    )
    assert rejected_only.artifacts == []
    assert [failure.error_code for failure in rejected_only.failures] == [
        "mailbox_zip_invalid"
    ]
    assert (
        list((tmp_path / "mailbox" / "mailbox-zip-rejected-only").glob("*.pdf")) == []
    )
