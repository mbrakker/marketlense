import sqlite3
from pathlib import Path

from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateCheckRequest,
    StateDbAccessRequest,
    StateGetRequest,
    StateIngestCursorGetRequest,
    StateIngestCursorSetRequest,
    StateRecordRequest,
)
from src.services.state_service import (
    already_processed,
    check_state_db_access,
    get,
    get_ingest_cursor,
    record,
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
    assert {"vector_store_id", "vector_store_status", "indexed_at_utc", "last_error", "doc_map_summary_json"}.issubset(cols)

    resp = get(StateGetRequest(schema_version="1.0", state_db=str(db_path), file_id="file-1"), _ctx())
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
        StateCheckRequest(schema_version="1.0", state_db=str(db_path), file_id="file-2", md5="md5-2"),
        _ctx(),
    )
    resp = get(StateGetRequest(schema_version="1.0", state_db=str(db_path), file_id="file-2"), _ctx())
    assert resp is not None
    assert resp.vector_store_id is None
    assert resp.vector_store_status is None
    assert resp.indexed_at_utc is None
    assert resp.last_error is None
    assert resp.doc_map_summary is None


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
    resp = get(StateGetRequest(schema_version="1.0", state_db=str(db_path), file_id="file-3"), _ctx())
    assert resp is not None
    assert resp.doc_map_summary == summary


def test_state_db_access_detects_lock(tmp_path: Path) -> None:
    db_path = tmp_path / "state.sqlite"
    conn = sqlite3.connect(db_path)
    conn.execute("BEGIN EXCLUSIVE")
    try:
        resp = check_state_db_access(
            StateDbAccessRequest(schema_version="1.0", state_db=str(db_path), timeout_seconds=0.0),
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
        StateDbAccessRequest(schema_version="1.0", state_db=str(db_path), timeout_seconds=0.0),
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
