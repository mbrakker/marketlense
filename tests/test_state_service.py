import sqlite3
from pathlib import Path

import pytest

from src.contracts.run_context import RunContext
from src.contracts.state import (
    MailboxCandidateRejectionListRequest,
    MailboxCandidateRejectionRecordRequest,
    StateBatchCheckItem,
    StateBatchCheckRequest,
    StateCheckRequest,
    StateDbAccessRequest,
    StateGetByMd5Request,
    StateGetRequest,
    StateIngestCursorGetRequest,
    StateIngestCursorSetRequest,
    MailDeliveryRequestListDueRequest,
    MailDeliveryRequestMarkAttemptRequest,
    MailDeliveryRequestUpsertRequest,
    StateProcessedListRequest,
    StatePublishedListRequest,
    StatePublishRecordRequest,
    StateRecordRequest,
    StateReportDownloadRouteGetRequest,
    StateReportDownloadRouteRecordRequest,
    WorkflowControlObservationListRequest,
    WorkflowControlObservationWriteRequest,
)
from src.services._state_service import common as state_common
from src.services.state_service import (
    already_processed_batch,
    already_processed,
    check_state_db_access,
    get,
    get_by_md5,
    get_ingest_cursor,
    get_report_download_route,
    list_mailbox_candidate_rejections,
    list_due_mail_delivery_requests,
    list_processed,
    list_published,
    record,
    record_mailbox_candidate_rejection,
    record_publish,
    record_report_download_route,
    list_workflow_control_observations,
    mark_mail_delivery_request_attempt,
    upsert_mail_delivery_request,
    write_workflow_control_observation,
    set_ingest_cursor,
)
from src.contracts.workflow_control import WorkflowControlObservation
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_migration_adds_vector_columns_and_preserves_data(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    # Simulate legacy schema without vector columns.
    conn = sqlite3.connect(db_path)
    conn.execute(
        """
        CREATE TABLE processed (
            file_id TEXT PRIMARY KEY,
            md5 TEXT NOT NULL,
            processed_at INTEGER NOT NULL,
            openai_file_id TEXT
        );
        """
    )
    conn.commit()
    conn.close()

    req = StateRecordRequest(
        schema_version="1.0",
        state_db=str(db_path),
        file_id="file-1",
        md5="md5",
        openai_file_id="of_123",
        vector_store_id="vs_123",
        vector_store_status="ready",
        indexed_at_utc="2026-01-07T00:00:00Z",
        last_error=None,
    )
    record(req, _ctx())

    # Columns should exist after migration.
    conn = sqlite3.connect(db_path)
    cols = {row[1] for row in conn.execute("PRAGMA table_info(processed)")}
    schema_version = conn.execute(
        "SELECT current_version FROM schema_version WHERE database_key='state_db'"
    ).fetchone()
    ledger_count = conn.execute(
        "SELECT COUNT(*) FROM schema_migration_ledger WHERE database_key='state_db'"
    ).fetchone()[0]
    conn.close()
    assert {
        "vector_store_id",
        "vector_store_status",
        "indexed_at_utc",
        "last_error",
        "doc_map_summary_json",
    }.issubset(cols)

    resp = get(
        StateGetRequest(schema_version="1.0", state_db=str(db_path), file_id="file-1"),
        _ctx(),
    )
    assert resp is not None
    assert resp.file_id == "file-1"
    assert resp.vector_store_id == "vs_123"
    assert resp.vector_store_status == "ready"
    assert resp.indexed_at_utc == "2026-01-07T00:00:00Z"
    assert resp.last_error is None
    assert resp.openai_file_id == "of_123"
    assert resp.doc_map_summary is None
    assert schema_version == (8,)
    assert ledger_count == 8


def test_record_and_get_with_defaults(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-2",
            md5="md5-2",
        ),
        _ctx(),
    )
    assert already_processed(
        StateCheckRequest(
            schema_version="1.0", state_db=str(db_path), file_id="file-2", md5="md5-2"
        ),
        _ctx(),
    )
    resp = get(
        StateGetRequest(schema_version="1.0", state_db=str(db_path), file_id="file-2"),
        _ctx(),
    )
    assert resp is not None
    assert resp.vector_store_id is None
    assert resp.vector_store_status is None
    assert resp.indexed_at_utc is None
    assert resp.last_error is None
    assert resp.doc_map_summary is None


def test_get_by_md5_returns_latest_processed_vector_store(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="older-file",
            md5="same-md5",
            openai_file_id="of_old",
            vector_store_id="vs_old",
            vector_store_status="completed",
            indexed_at_utc="2026-01-01T00:00:00Z",
        ),
        _ctx(),
    )
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="newer-file",
            md5="same-md5",
            openai_file_id="of_new",
            vector_store_id="vs_new",
            vector_store_status="completed",
            indexed_at_utc="2026-01-02T00:00:00Z",
        ),
        _ctx(),
    )
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE processed SET processed_at=1 WHERE file_id='older-file'")
        conn.execute("UPDATE processed SET processed_at=2 WHERE file_id='newer-file'")

    response = get_by_md5(
        StateGetByMd5Request(
            schema_version="1.0",
            state_db=str(db_path),
            md5="same-md5",
        ),
        _ctx(),
    )

    assert response is not None
    assert response.file_id == "newer-file"
    assert response.md5 == "same-md5"
    assert response.vector_store_id == "vs_new"
    assert response.openai_file_id == "of_new"


def test_already_processed_batch_returns_only_matched_pairs(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-1",
            md5="md5-1",
        ),
        _ctx(),
    )
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-2",
            md5="md5-2",
        ),
        _ctx(),
    )
    response = already_processed_batch(
        StateBatchCheckRequest(
            schema_version="1.0",
            state_db=str(db_path),
            items=[
                StateBatchCheckItem(
                    schema_version="1.0", file_id="file-1", md5="md5-1"
                ),
                StateBatchCheckItem(
                    schema_version="1.0", file_id="file-2", md5="no-match"
                ),
                StateBatchCheckItem(
                    schema_version="1.0", file_id="file-1", md5="md5-1"
                ),
                StateBatchCheckItem(schema_version="1.0", file_id=" ", md5=" "),
            ],
        ),
        _ctx(),
    )
    assert {(item.file_id, item.md5) for item in response.processed_items} == {
        ("file-1", "md5-1")
    }


def test_record_and_get_doc_map_summary(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    summary = {"sections_count": 0, "not_found_reason": "model_returned_no_json"}
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-3",
            md5="md5-3",
            doc_map_summary=summary,
        ),
        _ctx(),
    )
    resp = get(
        StateGetRequest(schema_version="1.0", state_db=str(db_path), file_id="file-3"),
        _ctx(),
    )
    assert resp is not None
    assert resp.doc_map_summary == summary


def test_record_and_get_ocr_fallback_fields(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-ocr",
            md5="md5-ocr",
            ocr_fallback_used=True,
            ocr_pdf_path="/tmp/generated-ocr.pdf",
        ),
        _ctx(),
    )
    resp = get(
        StateGetRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-ocr",
        ),
        _ctx(),
    )
    assert resp is not None
    assert resp.ocr_fallback_used is True
    assert resp.ocr_pdf_path == "/tmp/generated-ocr.pdf"


def test_state_db_access_detects_lock(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("BEGIN EXCLUSIVE")
    try:
        resp = check_state_db_access(
            StateDbAccessRequest(
                schema_version="1.0", state_db=str(db_path), timeout_seconds=0.0
            ),
            _ctx(),
        )
        assert resp.accessible is False
        assert resp.locked is True
    finally:
        conn.rollback()
        conn.close()


def test_state_db_access_allows_unlocked_db(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    resp = check_state_db_access(
        StateDbAccessRequest(
            schema_version="1.0", state_db=str(db_path), timeout_seconds=0.0
        ),
        _ctx(),
    )
    assert resp.accessible is True
    assert resp.locked is False


def test_state_db_uses_wal_mode(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-wal",
            md5="md5-wal",
        ),
        _ctx(),
    )

    conn = sqlite3.connect(db_path)
    try:
        journal_mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    finally:
        conn.close()

    assert journal_mode.lower() == "wal"


def test_state_db_access_allows_active_wal_writer(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-writer",
            md5="md5-writer",
        ),
        _ctx(),
    )

    conn = sqlite3.connect(db_path)
    conn.execute("BEGIN IMMEDIATE")
    try:
        resp = check_state_db_access(
            StateDbAccessRequest(
                schema_version="1.0",
                state_db=str(db_path),
                timeout_seconds=0.0,
            ),
            _ctx(),
        )
        assert resp.accessible is True
        assert resp.locked is False
    finally:
        conn.rollback()
        conn.close()


def test_ingest_cursor_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    initial = get_ingest_cursor(
        StateIngestCursorGetRequest(schema_version="1.0", state_db=str(db_path)),
        _ctx(),
    )
    assert initial.last_successful_ingest_utc is None

    ts = "2026-02-04T00:00:00Z"
    set_ingest_cursor(
        StateIngestCursorSetRequest(
            schema_version="1.0",
            state_db=str(db_path),
            last_successful_ingest_utc=ts,
        ),
        _ctx(),
    )
    updated = get_ingest_cursor(
        StateIngestCursorGetRequest(schema_version="1.0", state_db=str(db_path)),
        _ctx(),
    )
    assert updated.last_successful_ingest_utc == ts


def test_state_read_connect_failure_is_typed_app_error(
    external_boundary_mocks_only,
    assert_app_error,
) -> None:
    def _raise_connect(*args, **kwargs):
        raise sqlite3.OperationalError("connect boom")

    external_boundary_mocks_only.setattr(
        state_common.sqlite3, "connect", _raise_connect
    )

    with pytest.raises(AppError) as exc_info:
        get_ingest_cursor(
            StateIngestCursorGetRequest(
                schema_version="1.0",
                state_db="C:/tmp/state.sqlite",
            ),
            _ctx(),
        )

    assert_app_error(
        exc_info.value,
        code="state_db_unavailable",
        retryable=True,
    )


def test_list_processed_and_published_rows(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-1",
            md5="md5-1",
            vector_store_status="completed",
        ),
        _ctx(),
    )
    record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-2",
            md5="md5-2",
            text_validation_status="pass",
            text_validation_pages=[1, 3, 5],
        ),
        _ctx(),
    )
    processed = list_processed(
        StateProcessedListRequest(
            schema_version="1.0", state_db=str(db_path), limit=10
        ),
        _ctx(),
    )
    assert len(processed.rows) == 2
    assert {row.file_id for row in processed.rows} == {"file-1", "file-2"}

    record_publish(
        StatePublishRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            file_id="file-1",
            md5="md5-1",
            wp_post_id=123,
            wp_post_url="https://example.com/post/123",
            post_type="ml_report",
        ),
        _ctx(),
    )
    published = list_published(
        StatePublishedListRequest(
            schema_version="1.0", state_db=str(db_path), limit=10
        ),
        _ctx(),
    )
    assert len(published.rows) == 1
    assert published.rows[0].file_id == "file-1"
    assert published.rows[0].wp_post_id == 123
    assert published.rows[0].post_type == "ml_report"


def test_report_download_route_roundtrip(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    record_report_download_route(
        StateReportDownloadRouteRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            normalized_url="https://example.com/report",
            source_url="https://example.com/report",
            route_kind="pdf_download",
            route_summary="Click the top download button.",
            outcome="downloaded",
            last_downloaded_file_path=str(tmp_path / "report.pdf"),
            last_final_page_url="https://example.com/report/final",
        ),
        _ctx(),
    )

    response = get_report_download_route(
        StateReportDownloadRouteGetRequest(
            schema_version="1.0",
            state_db=str(db_path),
            normalized_url="https://example.com/report",
        ),
        _ctx(),
    )

    assert response is not None
    assert response.route_kind == "pdf_download"
    assert response.route_summary == "Click the top download button."
    assert response.outcome == "downloaded"
    assert response.last_final_page_url == "https://example.com/report/final"


def test_workflow_control_observation_roundtrip_and_ttl(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    fresh = WorkflowControlObservation(
        schema_version="1.0",
        observed_at_utc="2026-07-04T10:00:00Z",
        run_id="run-fresh",
        workflow="report_download",
        step_name="http_pdf",
        route="http_pdf",
        publisher="Example Publisher",
        report_key="https://example.com/report",
        outcome="succeeded",
        error_code="",
        error_retryable=False,
        error_severity="",
        latency_ms=1200,
        cost_usd=0.01,
        retry_count=0,
        resource_pressure={"model": 0.0},
    )
    stale = WorkflowControlObservation(
        schema_version="1.0",
        observed_at_utc="2026-06-01T10:00:00Z",
        run_id="run-stale",
        workflow="report_download",
        step_name="browser_acquisition",
        route="browser_render",
        publisher="Example Publisher",
        report_key="https://example.com/report-old",
        outcome="failed",
        error_code="browser_timeout",
        error_retryable=True,
        error_severity="warning",
        latency_ms=9000,
        cost_usd=0.25,
        retry_count=1,
        resource_pressure={"browser_failure_rate": 0.5},
    )

    write_workflow_control_observation(
        WorkflowControlObservationWriteRequest(
            schema_version="1.0",
            state_db=str(db_path),
            observation=stale,
        ),
        _ctx(),
    )
    write_workflow_control_observation(
        WorkflowControlObservationWriteRequest(
            schema_version="1.0",
            state_db=str(db_path),
            observation=fresh,
        ),
        _ctx(),
    )

    response = list_workflow_control_observations(
        WorkflowControlObservationListRequest(
            schema_version="1.0",
            state_db=str(db_path),
            workflow="report_download",
            publisher="Example Publisher",
            observed_after_utc="2026-07-01T00:00:00Z",
            limit=20,
        ),
        _ctx(),
    )

    assert [item.run_id for item in response.observations] == ["run-fresh"]
    assert response.observations[0].resource_pressure == {"model": 0.0}


def test_mail_delivery_request_roundtrip_is_idempotent_and_tracks_incremental_state(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state.sqlite"
    upsert = MailDeliveryRequestUpsertRequest(
        schema_version="1.0",
        state_db=str(db_path),
        idempotency_key="mail:https://example.com/report:ops@example.com",
        source_url="https://example.com/report",
        report_title="Retail Trends 2026",
        publisher_name="Example Publisher",
        delivery_email="ops@example.com",
        requested_after_utc="2026-07-04T11:08:00Z",
        route_family="browser_email_form",
        route_history_id="history-1",
    )

    first = upsert_mail_delivery_request(upsert, _ctx())
    second = upsert_mail_delivery_request(upsert, _ctx())

    assert first.request.request_id == second.request.request_id
    assert first.created is True
    assert second.created is False

    due = list_due_mail_delivery_requests(
        MailDeliveryRequestListDueRequest(
            schema_version="1.0",
            state_db=str(db_path),
            now_utc="2026-07-04T11:09:00Z",
            limit=10,
        ),
        _ctx(),
    )
    assert [item.idempotency_key for item in due.requests] == [
        "mail:https://example.com/report:ops@example.com"
    ]

    updated = mark_mail_delivery_request_attempt(
        MailDeliveryRequestMarkAttemptRequest(
            schema_version="1.0",
            state_db=str(db_path),
            request_id=first.request.request_id,
            status="pending",
            next_attempt_after_utc="2026-07-04T11:12:00Z",
            provider_cursor="imap:105",
            seen_provider_message_ids=["100", "101"],
            outcome="not_arrived_yet",
            selected_message_id="",
            downloaded_file_path="",
            error_code="mail_report_not_arrived_yet",
        ),
        _ctx(),
    )

    assert updated.request.attempt_count == 1
    assert updated.request.provider_cursor == "imap:105"
    assert updated.request.seen_provider_message_ids == ["100", "101"]
    assert (
        list_due_mail_delivery_requests(
            MailDeliveryRequestListDueRequest(
                schema_version="1.0",
                state_db=str(db_path),
                now_utc="2026-07-04T11:10:00Z",
                limit=10,
            ),
            _ctx(),
        ).requests
        == []
    )


def test_mailbox_candidate_rejection_persists_sanitized_request_scoped_evidence(
    tmp_path: Path,
) -> None:
    db_path = tmp_path / "state.sqlite"

    record_mailbox_candidate_rejection(
        MailboxCandidateRejectionRecordRequest(
            schema_version="1.0",
            state_db=str(db_path),
            request_id=7,
            provider_message_id="msg-cross-publisher",
            sender="Reports Team <reports@example.com>",
            source_host="gwi.com",
            link_host="about.bigcommerce.com",
            publisher_affinity="mismatch",
            title_token_overlap=0.125,
            reason_code="cross_publisher",
            expires_at_utc="2026-07-11T00:00:00Z",
        ),
        _ctx(),
    )

    response = list_mailbox_candidate_rejections(
        MailboxCandidateRejectionListRequest(
            schema_version="1.0",
            state_db=str(db_path),
            request_id=7,
            now_utc="2026-07-08T00:00:00Z",
            limit=20,
        ),
        _ctx(),
    )

    assert len(response.rejections) == 1
    rejection = response.rejections[0]
    assert rejection.provider_message_id == "msg-cross-publisher"
    assert rejection.sender == "Reports Team <redacted>"
    assert rejection.source_host == "gwi.com"
    assert rejection.link_host == "about.bigcommerce.com"
    assert rejection.reason_code == "cross_publisher"
    assert rejection.title_token_overlap == 0.125

    expired = list_mailbox_candidate_rejections(
        MailboxCandidateRejectionListRequest(
            schema_version="1.0",
            state_db=str(db_path),
            request_id=7,
            now_utc="2026-07-12T00:00:00Z",
            limit=20,
        ),
        _ctx(),
    )
    other_request = list_mailbox_candidate_rejections(
        MailboxCandidateRejectionListRequest(
            schema_version="1.0",
            state_db=str(db_path),
            request_id=8,
            now_utc="2026-07-08T00:00:00Z",
            limit=20,
        ),
        _ctx(),
    )

    assert expired.rejections == []
    assert other_request.rejections == []
