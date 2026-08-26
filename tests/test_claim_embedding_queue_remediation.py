from __future__ import annotations

import json
import sqlite3
import threading
import time

import pytest
from dataclasses import replace

from src.contracts.analytics_projection import (
    AnalyticsProjectionUpsertRequest,
    ClaimEmbeddingQueueHealthRequest,
    ClaimEmbeddingQueueReconcileRequest,
    ClaimEmbeddingWorkflowRequest,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.openai import OpenAIEmbeddingResponse
from src.contracts.remediation import RemediationListRequest
from src.orchestrators.claim_embedding_orchestrator import (
    ClaimEmbeddingDependencies,
    run_claim_embedding_workflow,
)
from src.generators._analytics_projection.common import _hash_payload
from src.services.analytics_store_service import (
    acquire_claim_embedding_execution_lease,
    read_claim_embedding_queue_health,
    reconcile_claim_embedding_queue,
    upsert_projection,
)
from src.services.state_service import list_remediation_records
from src.utils.errors import AppError
from tests.test_analytics_projection_foundation import _batch


def _workflow_request(db_path: str, ctx, **changes) -> ClaimEmbeddingWorkflowRequest:
    request = ClaimEmbeddingWorkflowRequest(
        schema_version="1.0",
        db_path=db_path,
        api_key="key",
        provider="openai",
        model="text-embedding-3-large",
        embedding_version="claim-embedding.openai-large-1024.v1",
        limit=10,
        timeout_seconds=2.0,
        ctx=ctx,
    )
    return replace(request, **changes)


def _health_request(db_path: str, **changes) -> ClaimEmbeddingQueueHealthRequest:
    request = ClaimEmbeddingQueueHealthRequest(
        schema_version="1.0",
        db_path=db_path,
        embedding_version="claim-embedding.openai-large-1024.v1",
        provider="openai",
        model="text-embedding-3-large",
        entity_types=["claim"],
    )
    return replace(request, **changes)


def _seed_projection(ingest_settings, run_context):
    batch = _batch(ingest_settings, run_context)
    upsert_projection(
        AnalyticsProjectionUpsertRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=ingest_settings.reports_db,
            batch=batch,
        ),
        run_context,
    )
    return batch


def _queue_state(db_path: str) -> sqlite3.Row:
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            """
            SELECT embedding_status,queue_reason_code,queue_error_retryable,
                   queue_attempt_count,next_eligible_at_utc
            FROM vector_projection_queue
            WHERE entity_type='claim'
            ORDER BY entity_uid
            LIMIT 1
            """
        ).fetchone()
    assert row is not None
    return row


def _add_current_claim(
    db_path: str,
    *,
    entity_uid: str,
    report_id: str,
    claim: str,
    evidence: str,
    publisher: str,
    created_at_utc: str,
) -> None:
    """Add a realistic projected claim row using the production queue hash contract."""
    with sqlite3.connect(db_path) as conn:
        metadata = {
            "schema_version": "1.0",
            "entity_type": "claim",
            "report_id": report_id,
            "publisher": publisher,
            "publisher_id": publisher.casefold(),
        }
        text_payload = f"Claim: {claim}\nEvidence: {evidence}"
        content_hash = _hash_payload(
            {
                "schema_version": "1.0",
                "entity_type": "claim",
                "text_payload": text_payload,
                "metadata": metadata,
                "content_class": "derived_evidence",
            }
        )
        conn.execute(
            """
            INSERT OR IGNORE INTO reports(
              file_id,title,taxonomy_json,categories_json,publisher,report_id,created_at,updated_at
            ) VALUES(?,?,?,?,?,?,?,?)
            """,
            (
                report_id,
                report_id,
                "[]",
                "[]",
                publisher,
                report_id,
                0,
                0,
            ),
        )
        conn.execute(
            """
            INSERT INTO report_claims(
              claim_uid,report_id,claim,evidence_id,evidence,pages_json,schema_version,
              projection_version,source_pack,source_ref,model,generated_at_utc,analysis_run_id
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                entity_uid,
                report_id,
                claim,
                entity_uid + ":evidence",
                evidence,
                "[]",
                "1.0",
                "analytics_projection.v1",
                "test",
                entity_uid,
                "",
                created_at_utc,
                "test-run",
            ),
        )
        conn.execute(
            """
            INSERT INTO vector_projection_queue(
              entity_uid,entity_type,report_id,text_payload,content_hash,metadata_json,
              content_class,embedding_status,embedding_version,created_at_utc,updated_at_utc,
              projection_schema_version
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                entity_uid,
                "claim",
                report_id,
                text_payload,
                content_hash,
                json.dumps(metadata, sort_keys=True),
                "derived_evidence",
                "pending",
                "",
                created_at_utc,
                created_at_utc,
                "1.0",
            ),
        )


def test_queue_health_and_reconciliation_classify_orphans_without_provider_calls(
    ingest_settings, run_context
) -> None:
    batch = _seed_projection(ingest_settings, run_context)
    with sqlite3.connect(ingest_settings.reports_db) as conn:
        conn.execute(
            "DELETE FROM reports WHERE file_id=?", (str(batch.report.report_id),)
        )

    health_request = _health_request(ingest_settings.reports_db)
    health = read_claim_embedding_queue_health(health_request, run_context)

    assert health.classification_counts == {"orphaned_report": 1}
    result = reconcile_claim_embedding_queue(
        ClaimEmbeddingQueueReconcileRequest(
            schema_version="1.0",
            health_request=health_request,
            run_id="queue-orphan-reconcile",
            actor="test_queue_operator",
            dry_run=False,
        ),
        run_context,
    )

    assert result.provider_calls_avoided == 1
    assert dict(_queue_state(ingest_settings.reports_db)) == {
        "embedding_status": "failed",
        "queue_reason_code": "orphaned_report",
        "queue_error_retryable": 0,
        "queue_attempt_count": 0,
        "next_eligible_at_utc": "",
    }


def test_stale_content_and_obsolete_versions_reconcile_without_provider_calls(
    ingest_settings, run_context
) -> None:
    batch = _seed_projection(ingest_settings, run_context)
    claim = batch.claims[0]
    with sqlite3.connect(ingest_settings.reports_db) as conn:
        conn.execute(
            "UPDATE report_claims SET claim=? WHERE claim_uid=?",
            ("Current content changed", str(claim.claim_uid)),
        )
    health_request = _health_request(ingest_settings.reports_db)

    stale = read_claim_embedding_queue_health(health_request, run_context)
    assert stale.classification_counts == {"stale_content": 1}
    reconcile_claim_embedding_queue(
        ClaimEmbeddingQueueReconcileRequest(
            schema_version="1.0",
            health_request=health_request,
            run_id="queue-stale-reconcile",
            actor="test_queue_operator",
            dry_run=False,
        ),
        run_context,
    )
    assert dict(_queue_state(ingest_settings.reports_db))["queue_reason_code"] == (
        "content_hash_stale_reprojection_required"
    )
    with sqlite3.connect(ingest_settings.reports_db) as conn:
        conn.execute(
            "UPDATE report_claims SET claim=? WHERE claim_uid=?",
            (claim.claim, str(claim.claim_uid)),
        )
        conn.execute(
            """
            UPDATE vector_projection_queue
            SET embedding_status='failed',embedding_version='claim-embedding.v0',
                queue_reason_code='embedding_version_obsolete'
            WHERE entity_uid=?
            """,
            (str(claim.claim_uid),),
        )
    obsolete = read_claim_embedding_queue_health(health_request, run_context)
    assert obsolete.classification_counts == {"obsolete_version": 1}
    reconciled = reconcile_claim_embedding_queue(
        ClaimEmbeddingQueueReconcileRequest(
            schema_version="1.0",
            health_request=health_request,
            run_id="queue-obsolete-reconcile",
            actor="test_queue_operator",
            dry_run=False,
        ),
        run_context,
    )
    assert reconciled.transitioned_entity_uids == [claim.claim_uid]


def test_budget_denial_and_dry_run_make_no_provider_calls_or_writes(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)
    calls: list[str] = []

    def _embed(request, _ctx):
        calls.extend(request.inputs)
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.1] * request.dimensions for _ in request.inputs],
            model=request.model,
            dimensions=request.dimensions,
            request_id="concurrent-test",
            input_tokens=2,
            total_tokens=2,
        )

    budget = run_claim_embedding_workflow(
        _workflow_request(
            ingest_settings.reports_db, run_context, max_estimated_tokens=1
        ),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_embed),
    )
    before = dict(_queue_state(ingest_settings.reports_db))
    dry_run = run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context, dry_run=True),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_embed),
    )

    assert budget.embedded_count == 0
    assert budget.provider_calls_avoided == 1
    assert dry_run.embedded_count == 0
    assert dry_run.provider_calls_avoided == 1
    assert calls == []
    assert dict(_queue_state(ingest_settings.reports_db)) == before


def test_embedding_cost_is_accounted_when_the_rate_card_has_the_model(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)

    def _embed(request, _ctx):
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.1] * request.dimensions],
            model=request.model,
            dimensions=request.dimensions,
            request_id="priced-embedding-test",
            input_tokens=100,
            total_tokens=100,
        )

    response = run_claim_embedding_workflow(
        _workflow_request(
            ingest_settings.reports_db,
            run_context,
            model_pricing={
                "text-embedding-3-large": {
                    "input_tokens_per_1k_usd": 0.00002,
                    "output_tokens_per_1k_usd": 0.0,
                    "tool_call_usd": 0.0,
                }
            },
        ),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_embed),
    )

    assert response.embedded_count == 1
    assert response.actual_input_tokens == 100
    assert response.actual_cost_usd == 0.000002


def test_retry_metadata_terminal_escalation_and_idempotent_rerun(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)
    calls: list[int] = []

    def _fail(_request, _ctx):
        calls.append(1)
        raise AppError(
            code="openai_embedding_request_failed",
            message="provider unavailable",
            retryable=True,
            severity="error",
        )

    first = run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context, max_retries=2),
        dependencies=ClaimEmbeddingDependencies(
            create_embeddings=_fail,
            utc_now=lambda: "2030-04-22T13:00:00Z",
        ),
    )
    state = _queue_state(ingest_settings.reports_db)
    second = run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context, max_retries=2),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_fail),
    )

    assert first.failed_count == 1
    assert state["queue_error_retryable"] == 1
    assert state["next_eligible_at_utc"] > "2030-04-22T13:00:00Z"
    assert second.processed_entity_uids == []
    assert calls == [1]


def test_runtime_limit_stops_before_provider_call(ingest_settings, run_context) -> None:
    _seed_projection(ingest_settings, run_context)
    calls: list[str] = []

    def _embed(request, _ctx):
        calls.extend(request.inputs)
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.1] * request.dimensions],
            model=request.model,
            dimensions=request.dimensions,
            request_id="concurrent-test",
            input_tokens=2,
            total_tokens=2,
        )

    result = run_claim_embedding_workflow(
        _workflow_request(
            ingest_settings.reports_db, run_context, max_runtime_seconds=0.0000001
        ),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_embed),
    )

    assert result.embedded_count == 0
    assert result.processed_entity_uids == []
    assert calls == []


def test_batch_report_and_publisher_fairness_limits_are_respected(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)
    _add_current_claim(
        ingest_settings.reports_db,
        entity_uid="drive-file-1:claim:second",
        report_id="drive-file-1",
        claim="Second claim",
        evidence="Second evidence",
        publisher="Existing Publisher",
        created_at_utc="2026-04-02T00:00:00Z",
    )
    _add_current_claim(
        ingest_settings.reports_db,
        entity_uid="drive-file-2:claim:first",
        report_id="drive-file-2",
        claim="Other publisher claim",
        evidence="Other evidence",
        publisher="Other Publisher",
        created_at_utc="2026-04-03T00:00:00Z",
    )
    calls: list[str] = []

    def _embed(request, _ctx):
        calls.extend(request.inputs)
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.1] * request.dimensions for _ in request.inputs],
            model=request.model,
            dimensions=request.dimensions,
            request_id="fairness-test",
            input_tokens=2,
            total_tokens=2,
        )

    response = run_claim_embedding_workflow(
        _workflow_request(
            ingest_settings.reports_db,
            run_context,
            limit=2,
            max_reports=2,
            publisher_fairness_limit=1,
        ),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_embed),
    )

    assert response.embedded_count == 2
    assert len(calls) == 2
    assert any("Other publisher claim" in text for text in calls)


def test_terminal_provider_failure_is_not_retried(ingest_settings, run_context) -> None:
    _seed_projection(ingest_settings, run_context)
    calls: list[int] = []

    def _fail(_request, _ctx):
        calls.append(1)
        raise AppError(
            code="openai_embedding_invalid_input",
            message="invalid payload",
            retryable=False,
            severity="error",
        )

    deps = ClaimEmbeddingDependencies(create_embeddings=_fail)
    first = run_claim_embedding_workflow(
        _workflow_request(
            ingest_settings.reports_db,
            run_context,
            state_db=ingest_settings.state_db,
        ),
        dependencies=deps,
    )
    second = run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context), dependencies=deps
    )

    assert first.failed_count == 1
    assert second.processed_entity_uids == []
    assert calls == [1]
    records = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0",
            state_db=ingest_settings.state_db,
            workflow="claim_embedding",
        ),
        run_context,
    ).records
    assert len(records) == 1
    assert records[0].error_code == "claim_embedding_retry_budget_exhausted"
    assert records[0].diagnostics["cause_code"] == "openai_embedding_invalid_input"
    assert records[0].status == "operator_action_required"


def test_provider_count_mismatch_is_retained_as_a_retryable_queue_failure(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)

    def _wrong_count(request, _ctx):
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[],
            model=request.model,
            dimensions=request.dimensions,
            request_id="wrong-count-test",
            input_tokens=0,
            total_tokens=0,
        )

    response = run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_wrong_count),
    )

    assert response.embedded_count == 0
    assert response.failed_count == 1
    assert _queue_state(ingest_settings.reports_db)["queue_error_retryable"] == 1


@pytest.mark.parametrize(
    ("request_overrides", "additional_claims"),
    [
        (
            {"max_reports": 1},
            [
                ("drive-file-2:claim:other", "drive-file-2", "Other Publisher"),
            ],
        ),
        (
            {"publisher_fairness_limit": 1},
            [
                ("drive-file-1:claim:second", "drive-file-1", "Existing Publisher"),
            ],
        ),
        ({"max_estimated_tokens": 1}, []),
        (
            {
                "max_estimated_cost_usd": 0.000000001,
                "model_pricing": {
                    "text-embedding-3-large": {
                        "input_tokens_per_1k_usd": 1.0,
                        "output_tokens_per_1k_usd": 0.0,
                        "tool_call_usd": 0.0,
                    }
                },
            },
            [],
        ),
    ],
)
def test_queue_admission_limits_avoid_provider_calls_before_embedding(
    ingest_settings,
    run_context,
    request_overrides,
    additional_claims,
) -> None:
    _seed_projection(ingest_settings, run_context)
    for entity_uid, report_id, publisher in additional_claims:
        _add_current_claim(
            ingest_settings.reports_db,
            entity_uid=entity_uid,
            report_id=report_id,
            claim="Additional claim",
            evidence="Additional evidence",
            publisher=publisher,
            created_at_utc="2026-04-02T00:00:00Z",
        )
    calls: list[str] = []

    def _embed(request, _ctx):
        calls.extend(request.inputs)
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.1] * request.dimensions],
            model=request.model,
            dimensions=request.dimensions,
            request_id="admission-limit-test",
            input_tokens=2,
            total_tokens=2,
        )

    response = run_claim_embedding_workflow(
        _workflow_request(
            ingest_settings.reports_db,
            run_context,
            limit=10,
            **request_overrides,
        ),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_embed),
    )

    assert response.provider_calls_avoided >= 1
    assert response.embedded_count == len(calls)


def test_retry_backoff_normalizes_a_naive_operator_clock(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)

    def _retryable_failure(_request, _ctx):
        raise AppError(
            code="openai_embedding_request_failed",
            message="provider unavailable",
            retryable=True,
            severity="error",
        )

    response = run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context),
        dependencies=ClaimEmbeddingDependencies(
            create_embeddings=_retryable_failure,
            utc_now=lambda: "2030-04-22T13:00:00",
        ),
    )

    assert response.failed_count == 1
    assert _queue_state(ingest_settings.reports_db)["next_eligible_at_utc"].endswith(
        "+00:00"
    )


def test_concurrent_runs_have_one_successful_embedding_and_one_provider_call(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)
    calls: list[str] = []
    lock = threading.Lock()

    def _embed(request, _ctx):
        with lock:
            calls.extend(request.inputs)
        time.sleep(0.05)
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.1] * request.dimensions],
            model=request.model,
            dimensions=request.dimensions,
            request_id="concurrent-test",
            input_tokens=2,
            total_tokens=2,
        )

    request = _workflow_request(ingest_settings.reports_db, run_context)
    deps = ClaimEmbeddingDependencies(create_embeddings=_embed)
    threads = [
        threading.Thread(
            target=run_claim_embedding_workflow,
            args=(request,),
            kwargs={"dependencies": deps},
        )
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    with sqlite3.connect(ingest_settings.reports_db) as conn:
        successful = conn.execute(
            "SELECT COUNT(*) FROM claim_embeddings WHERE status='embedded'"
        ).fetchone()[0]

    assert len(calls) == 1
    assert successful == 1


def test_claim_embedding_workflow_batches_individually_leased_claims(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)
    _add_current_claim(
        ingest_settings.reports_db,
        entity_uid="drive-file-1:claim:second",
        report_id="drive-file-1",
        claim="A second representative claim",
        evidence="The report contains a second evidence statement.",
        publisher="Existing Publisher",
        created_at_utc="2026-04-02T00:00:00Z",
    )
    calls: list[list[str]] = []

    def _embed(request, _ctx):
        calls.append(list(request.inputs))
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.1] * request.dimensions for _ in request.inputs],
            model=request.model,
            dimensions=request.dimensions,
            request_id="batch-test",
            input_tokens=8,
            total_tokens=8,
        )

    response = run_claim_embedding_workflow(
        _workflow_request(
            ingest_settings.reports_db,
            run_context,
            model="text-embedding-3-large",
            embedding_version="claim-embedding.openai-large-1024.v1",
            dimensions=1024,
            batch_size=2,
        ),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_embed),
    )

    assert response.embedded_count == 2
    assert response.provider_call_count == 1
    assert len(calls) == 1
    assert len(calls[0]) == 2


def test_claim_embedding_workflow_rejects_wrong_sized_provider_vectors(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)

    def _embed(request, _ctx):
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.1] * (request.dimensions - 1)],
            model=request.model,
            dimensions=request.dimensions - 1,
            request_id="wrong-dimensions-test",
            input_tokens=4,
            total_tokens=4,
        )

    response = run_claim_embedding_workflow(
        _workflow_request(
            ingest_settings.reports_db,
            run_context,
            model="text-embedding-3-large",
            embedding_version="claim-embedding.openai-large-1024.v1",
            dimensions=1024,
        ),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_embed),
    )

    assert response.embedded_count == 0
    assert response.failed_count == 1
    assert _queue_state(ingest_settings.reports_db)["queue_reason_code"] == (
        "claim_embedding_dimensions_mismatch"
    )


def test_active_lease_is_observable_and_excluded_from_new_admission(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)
    request = _health_request(ingest_settings.reports_db)
    item = read_claim_embedding_queue_health(request, run_context).items[0]

    assert acquire_claim_embedding_execution_lease(
        db_path=ingest_settings.reports_db,
        item=item,
        embedding_version=request.embedding_version,
        provider=request.provider,
        model=request.model,
        lease_id="observability-lease",
        lease_expires_at_utc="2030-04-22T13:00:00+00:00",
        ctx=run_context,
    )
    health = read_claim_embedding_queue_health(request, run_context)

    assert health.classification_counts == {"leased": 1}
    assert health.oldest_pending_age_seconds == 0
    assert health.age_percentiles_seconds == {"p50": 0, "p95": 0, "p99": 0}
    assert health.estimated_drain_seconds is None


def test_queue_transitions_reconcile_with_detailed_audit_rows(
    ingest_settings, run_context
) -> None:
    _seed_projection(ingest_settings, run_context)

    def _embed(request, _ctx):
        return OpenAIEmbeddingResponse(
            schema_version="1.0",
            embeddings=[[0.1] * request.dimensions],
            model=request.model,
            dimensions=request.dimensions,
            request_id="transition-test",
            input_tokens=4,
            total_tokens=4,
        )

    response = run_claim_embedding_workflow(
        _workflow_request(ingest_settings.reports_db, run_context),
        dependencies=ClaimEmbeddingDependencies(create_embeddings=_embed),
    )
    with sqlite3.connect(ingest_settings.reports_db) as conn:
        rows = conn.execute(
            "SELECT prior_status,new_status,reason_code FROM claim_embedding_queue_transitions"
        ).fetchall()

    assert response.embedded_count == 1
    assert rows == [("pending", "embedded", "embedding_completed")]
