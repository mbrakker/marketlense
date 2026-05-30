from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from src.contracts.ingest import IngestSettings
from src.contracts.run_context import RunContext
from src.contracts.state import StateGetRequest, StateRecordRequest
from src.contracts.vector_store import VectorStorePruneResponse
from src.orchestrators.vector_store_retention_orchestrator import (
    run_vector_store_retention_cleanup,
)
from src.services.state_service import get as state_get
from src.services.state_service import list_processed, record as state_record


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _settings(tmp_path: Path) -> IngestSettings:
    return IngestSettings(
        schema_version="1.0",
        google_sa_path="sa.json",
        gdrive_folder_id="folder",
        openai_api_key="key",
        openai_model="gpt-4.1-mini",
        batch_limit=1,
        output_dir=str(tmp_path / "out"),
        cache_dir=str(tmp_path / "cache"),
        state_db=str(tmp_path / "state.sqlite"),
        reports_db=str(tmp_path / "reports.sqlite"),
        category_mapping_path="cats.yaml",
        cover_style_path="cover.yaml",
        ingest_lock_path=str(tmp_path / "lock"),
        ingest_lock_ttl_seconds=1.0,
        temperature=0.1,
        vector_store_keep=True,
        vector_store_retention_days=30,
        cost_ledger_path=str(tmp_path / "ledger.jsonl"),
        cost_daily_path=str(tmp_path / "daily.json"),
        model_pricing={},
    )


def _record_state(settings: IngestSettings, *, file_id: str, vector_store_id: str):
    state_record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id=file_id,
            md5=f"md5-{file_id}",
            openai_file_id=f"file-{file_id}",
            vector_store_id=vector_store_id,
            vector_store_status="completed",
            indexed_at_utc="2026-01-01T00:00:00Z",
            last_error=None,
        ),
        _ctx(),
    )


def _set_processed_at(settings: IngestSettings, *, file_id: str, processed_at: int):
    with sqlite3.connect(settings.state_db) as conn:
        conn.execute(
            "UPDATE processed SET processed_at=? WHERE file_id=?",
            (processed_at, file_id),
        )


def test_retention_cleanup_prunes_expired_state_rows_and_clears_deleted_ids(
    tmp_path,
) -> None:
    settings = _settings(tmp_path)
    now_epoch = 2_000_000
    _record_state(settings, file_id="old", vector_store_id="vs_old")
    _record_state(settings, file_id="recent", vector_store_id="vs_recent")
    _set_processed_at(settings, file_id="old", processed_at=now_epoch - 31 * 86400)
    _set_processed_at(settings, file_id="recent", processed_at=now_epoch - 10 * 86400)
    prune_requests = []

    def _prune(request, ctx):
        prune_requests.append(request)
        return VectorStorePruneResponse(
            schema_version="1.0",
            requested_count=len(request.items),
            deleted_vector_store_ids=["vs_old"],
            missing_vector_store_ids=[],
            skipped_duplicate_vector_store_ids=[],
        )

    response = run_vector_store_retention_cleanup(
        settings,
        _ctx(),
        now_epoch=now_epoch,
        state_list=list_processed,
        state_record=state_record,
        vector_store_prune=_prune,
    )

    assert response.pruned_vector_store_ids == ["vs_old"]
    assert response.scanned_count == 2
    assert prune_requests[0].items[0].reason == "retention_expired"
    assert prune_requests[0].items[0].file_id == "old"

    old = state_get(
        StateGetRequest(schema_version="1.0", state_db=settings.state_db, file_id="old"),
        _ctx(),
    )
    recent = state_get(
        StateGetRequest(
            schema_version="1.0", state_db=settings.state_db, file_id="recent"
        ),
        _ctx(),
    )
    assert old is not None
    assert old.vector_store_id is None
    assert old.vector_store_status == "deleted"
    assert old.last_error == "vector_store_deleted:retention_expired"
    assert recent is not None
    assert recent.vector_store_id == "vs_recent"


def test_retention_cleanup_skips_when_retention_days_is_zero(tmp_path) -> None:
    settings = replace(_settings(tmp_path), vector_store_retention_days=0)
    _record_state(settings, file_id="old", vector_store_id="vs_old")

    response = run_vector_store_retention_cleanup(
        settings,
        _ctx(),
        now_epoch=2_000_000,
        state_list=list_processed,
        state_record=state_record,
        vector_store_prune=lambda _request, _ctx: (_ for _ in ()).throw(
            AssertionError("cleanup should be disabled")
        ),
    )

    assert response.pruned_vector_store_ids == []
    assert response.scanned_count == 0
