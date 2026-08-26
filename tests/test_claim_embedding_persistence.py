from __future__ import annotations

import json
import logging
import sqlite3
from dataclasses import replace

import pytest

from src.contracts.analytics_projection import (
    AnalyticsProjectionUpsertRequest,
    ClaimEmbeddingPendingReadRequest,
    ClaimEmbeddingReadRequest,
    ClaimEmbeddingWorkflowRequest,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.openai import OpenAIEmbeddingResponse
from src.contracts.run_context import RunContext
from src.orchestrators.claim_embedding_orchestrator import (
    ClaimEmbeddingDependencies,
    run_claim_embedding_workflow,
)
from src.services.analytics_store_service import (
    read_pending_claim_embedding_rows,
    read_claim_embeddings,
    upsert_projection,
)
from src.utils.errors import AppError
from tests.test_analytics_projection_foundation import _batch


def _events(caplog) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for record in caplog.records:
        if record.name not in {
            "market_lense.claim_embedding_orchestrator",
            "market_lense.analytics_store_service",
        }:
            continue
        payload = json.loads(record.message)
        if isinstance(payload, dict):
            events.append(payload)
    return events


def _workflow_request(db_path: str, ctx: RunContext) -> ClaimEmbeddingWorkflowRequest:
    return ClaimEmbeddingWorkflowRequest(
        schema_version="1.0",
        db_path=db_path,
        api_key="key",
        provider="openai",
        model="text-embedding-3-large",
        embedding_version="claim-embedding.openai-large-1024.v1",
        limit=25,
        timeout_seconds=9.0,
        ctx=ctx,
    )


def _fetch_one(db_path: str, sql: str, params: tuple = ()) -> sqlite3.Row:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(sql, params).fetchone()
    assert row is not None
    return row


def test_claim_embedding_workflow_persists_vectors_and_skips_unchanged_reruns(
    ingest_settings,
    run_context,
    caplog,
    assert_logs_have_required_fields,
    assert_no_defaulted_required_fields,
) -> None:
    batch = _batch(ingest_settings, run_context)
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=ingest_settings.reports_db,
            batch=batch,
        ),
        run_context,
    )
    calls: list[list[str]] = []

    def _embed(request, ctx):
        calls.append(list(request.inputs))
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.11] * request.dimensions for _ in request.inputs],
            model=request.model,
            dimensions=request.dimensions,
            request_id="emb_claims_1",
            input_tokens=17,
            total_tokens=17,
        )

    caplog.set_level(logging.INFO)
    deps = ClaimEmbeddingDependencies(
        create_embeddings=_embed,
        utc_now=lambda: "2026-04-22T13:00:00Z",
    )

    first = run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context),
        dependencies=deps,
    )
    second = run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context),
        dependencies=deps,
    )

    assert first.embedded_count == 1
    assert first.failed_count == 0
    assert first.skipped_count == 0
    assert second.embedded_count == 0
    assert second.skipped_count == 0
    assert second.provider_calls_avoided == 1
    assert len(calls) == 1
    assert "Demand is expanding" in calls[0][0]

    readback = read_claim_embeddings(
        ClaimEmbeddingReadRequest(
            schema_version="1.0",
            db_path=ingest_settings.reports_db,
            report_ids=["drive-file-1"],
            topics=["AI"],
            statuses=["embedded"],
        ),
        run_context,
    )

    assert len(readback.embeddings) == 1
    record = readback.embeddings[0]
    assert record.claim_uid == batch.claims[0].claim_uid
    assert record.entity_uid == batch.claims[0].claim_uid
    assert record.report_id == "drive-file-1"
    assert record.embedding_version == "claim-embedding.openai-large-1024.v1"
    assert record.content_hash == next(
        row.content_hash for row in batch.vector_queue if row.entity_type == "claim"
    )
    assert record.provider == "openai"
    assert record.model == "text-embedding-3-large"
    assert record.dimensions == 1024
    assert record.vector == [0.11] * 1024
    assert record.status == "embedded"
    assert record.generated_at_utc == "2026-04-22T13:00:00Z"
    assert record.external_vector_id.startswith("local:claim_embeddings:")
    assert record.error_code == ""
    assert record.error_message == ""
    default_status_readback = read_claim_embeddings(
        ClaimEmbeddingReadRequest(
            schema_version="1.0",
            db_path=ingest_settings.reports_db,
            statuses=[""],
        ),
        run_context,
    )
    assert [item.embedding_uid for item in default_status_readback.embeddings] == [
        record.embedding_uid
    ]
    with sqlite3.connect(ingest_settings.reports_db) as conn:
        conn.execute(
            "UPDATE claim_embeddings SET metadata_json=? WHERE embedding_uid=?",
            ("{", str(record.embedding_uid)),
        )
    invalid_metadata_readback = read_claim_embeddings(
        ClaimEmbeddingReadRequest(
            schema_version="1.0",
            db_path=ingest_settings.reports_db,
            statuses=["embedded"],
        ),
        run_context,
    )
    assert invalid_metadata_readback.embeddings[0].metadata == {}

    queue = _fetch_one(
        ingest_settings.reports_db,
        "SELECT embedding_status, embedding_version FROM vector_projection_queue WHERE entity_uid=?",
        (str(batch.claims[0].claim_uid),),
    )
    assert dict(queue) == {
        "embedding_status": "embedded",
        "embedding_version": "claim-embedding.openai-large-1024.v1",
    }
    assert_logs_have_required_fields(_events(caplog))


def test_claim_embedding_read_rejects_invalid_status(
    ingest_settings,
    run_context,
    assert_app_error,
) -> None:
    with pytest.raises(AppError) as exc_info:
        read_claim_embeddings(
            ClaimEmbeddingReadRequest(
                schema_version="1.0",
                db_path=ingest_settings.reports_db,
                statuses=["pending"],
            ),
            run_context,
        )

    assert_app_error(
        exc_info.value,
        code="claim_embedding_read_status_invalid",
        retryable=False,
    )


def test_claim_embedding_pending_read_limit_zero_returns_empty_contract(
    ingest_settings,
    run_context,
) -> None:
    response = read_pending_claim_embedding_rows(
        ClaimEmbeddingPendingReadRequest(
            schema_version="1.0",
            db_path=ingest_settings.reports_db,
            embedding_version="claim-embedding.openai-large-1024.v1",
            provider="openai",
            model="text-embedding-3-large",
            limit=0,
        ),
        run_context,
    )

    assert response.schema_version == PROJECTION_SCHEMA_VERSION
    assert response.rows == []


def test_claim_embedding_workflow_records_failed_attempt_with_error_taxonomy(
    ingest_settings,
    run_context,
    assert_app_error,
) -> None:
    batch = _batch(ingest_settings, run_context)
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=ingest_settings.reports_db,
            batch=batch,
        ),
        run_context,
    )

    def _fail(_request, _ctx):
        raise AppError(
            code="openai_embedding_request_failed",
            message="provider unavailable",
            retryable=True,
            severity="error",
        )

    response = run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context),
        dependencies=ClaimEmbeddingDependencies(
            create_embeddings=_fail,
            utc_now=lambda: "2026-04-22T13:05:00Z",
        ),
    )

    assert response.embedded_count == 0
    assert response.failed_count == 1
    failed = read_claim_embeddings(
        ClaimEmbeddingReadRequest(
            schema_version="1.0",
            db_path=ingest_settings.reports_db,
            statuses=["failed"],
        ),
        run_context,
    ).embeddings[0]
    assert failed.status == "failed"
    assert failed.vector is None
    assert failed.dimensions is None
    assert failed.error_code == "openai_embedding_request_failed"
    assert failed.error_retryable is True
    assert failed.generated_at_utc == "2026-04-22T13:05:00Z"
    assert_app_error(
        AppError(
            code=failed.error_code,
            message=failed.error_message,
            retryable=failed.error_retryable,
            severity=failed.error_severity,
        ),
        code="openai_embedding_request_failed",
        retryable=True,
    )


def test_claim_embedding_workflow_reembeds_when_content_hash_or_version_changes(
    ingest_settings,
    run_context,
) -> None:
    batch = _batch(ingest_settings, run_context)
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=ingest_settings.reports_db,
            batch=batch,
        ),
        run_context,
    )
    calls: list[str] = []

    def _embed(request, _ctx):
        calls.append(request.model + ":" + request.inputs[0])
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[float(len(calls))] * request.dimensions],
            model=request.model,
            dimensions=request.dimensions,
            request_id=f"emb_{len(calls)}",
            input_tokens=5,
            total_tokens=5,
        )

    deps = ClaimEmbeddingDependencies(
        create_embeddings=_embed,
        utc_now=lambda: f"2026-04-22T13:0{len(calls)}:00Z",
    )
    run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context),
        dependencies=deps,
    )
    version_two = replace(
        _workflow_request(ingest_settings.reports_db, run_context),
        embedding_version="claim-embedding.openai-large-1024.v2",
    )
    run_claim_embedding_workflow(version_two, dependencies=deps)

    claim_queue = next(row for row in batch.vector_queue if row.entity_type == "claim")
    changed_queue = replace(
        claim_queue,
        text_payload=claim_queue.text_payload + "\nNew adoption signal.",
        content_hash="f" * 64,
        embedding_status="pending",
        embedding_version="",
        updated_at_utc="2026-04-22T14:00:00Z",
    )
    changed_batch = replace(batch, vector_queue=[changed_queue])
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=ingest_settings.reports_db,
            batch=changed_batch,
        ),
        run_context,
    )
    run_claim_embedding_workflow(version_two, dependencies=deps)

    assert len(calls) == 2
    embedded = read_claim_embeddings(
        ClaimEmbeddingReadRequest(
            schema_version="1.0",
            db_path=ingest_settings.reports_db,
            claim_uids=[str(claim_queue.entity_uid)],
            statuses=["embedded"],
        ),
        run_context,
    ).embeddings
    assert [record.embedding_version for record in embedded] == [
        "claim-embedding.openai-large-1024.v2",
        "claim-embedding.openai-large-1024.v1",
    ]
    queue = _fetch_one(
        ingest_settings.reports_db,
        """
        SELECT embedding_status, queue_reason_code
        FROM vector_projection_queue
        WHERE entity_uid=?
        """,
        (str(claim_queue.entity_uid),),
    )
    assert dict(queue) == {
        "embedding_status": "pending",
        "queue_reason_code": "",
    }


def test_claim_embedding_workflow_reembeds_when_stored_model_identity_differs(
    ingest_settings, run_context
) -> None:
    batch = _batch(ingest_settings, run_context)
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=ingest_settings.reports_db,
            batch=batch,
        ),
        run_context,
    )
    calls: list[list[str]] = []

    def _embed(request, _ctx):
        calls.append(list(request.inputs))
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.2] * request.dimensions for _ in request.inputs],
            model=request.model,
            dimensions=request.dimensions,
            request_id=f"model-migration-{len(calls)}",
            input_tokens=4,
            total_tokens=4,
        )

    request = _workflow_request(ingest_settings.reports_db, run_context)
    deps = ClaimEmbeddingDependencies(create_embeddings=_embed)
    first = run_claim_embedding_workflow(request, dependencies=deps)
    with sqlite3.connect(ingest_settings.reports_db) as connection:
        connection.execute("UPDATE claim_embeddings SET model='text-embedding-3-small'")
    second = run_claim_embedding_workflow(request, dependencies=deps)

    assert first.embedded_count == 1
    assert second.embedded_count == 1
    assert len(calls) == 2
