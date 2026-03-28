import sqlite3
from pathlib import Path

from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateBatchCheckItem,
    StateBatchCheckRequest,
    StateCheckRequest,
    StateDbAccessRequest,
    StateGetRequest,
    StateIngestCursorGetRequest,
    StateIngestCursorSetRequest,
    StateProcessedListRequest,
    StatePublishedListRequest,
    StatePublishRecordRequest,
    StateRecordRequest,
    StateReportDownloadRouteGetRequest,
    StateReportDownloadRouteRecordRequest,
)
from src.services.state_service import (
    already_processed_batch,
    already_processed,
    check_state_db_access,
    get,
    get_ingest_cursor,
    get_report_download_route,
    list_processed,
    list_published,
    record,
    record_publish,
    record_report_download_route,
    set_ingest_cursor,
)


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
