from __future__ import annotations

"""Control-plane workflow for durable claim-level embeddings."""

import logging
from dataclasses import dataclass
from typing import Callable

from src.contracts.analytics_projection import (
    ClaimEmbeddingPendingReadRequest,
    ClaimEmbeddingPersistRequest,
    ClaimEmbeddingQueueItem,
    ClaimEmbeddingRecord,
    ClaimEmbeddingWorkflowRequest,
    ClaimEmbeddingWorkflowResponse,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.openai import OpenAIEmbeddingRequest, OpenAIEmbeddingResponse
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import EntityUid
from src.services import analytics_store_service, llm_service
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.claim_embedding_orchestrator")


@dataclass(frozen=True)
class ClaimEmbeddingDependencies:
    read_pending_rows: Callable = (
        analytics_store_service.read_pending_claim_embedding_rows
    )
    create_embeddings: Callable[
        [OpenAIEmbeddingRequest, RunContext], OpenAIEmbeddingResponse
    ] = llm_service.openai_create_embeddings
    persist_record: Callable = analytics_store_service.persist_claim_embedding
    embedding_uid: Callable[..., EntityUid] = (
        analytics_store_service.claim_embedding_uid
    )
    utc_now: Callable[[], str] = lambda: ""


def _timestamp(deps: ClaimEmbeddingDependencies) -> str:
    value = str(deps.utc_now() or "").strip()
    if value:
        return value
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


def _success_record(
    *,
    row: ClaimEmbeddingQueueItem,
    vector: list[float],
    dimensions: int,
    response: OpenAIEmbeddingResponse,
    request: ClaimEmbeddingWorkflowRequest,
    generated_at_utc: str,
    embedding_uid: EntityUid,
) -> ClaimEmbeddingRecord:
    return ClaimEmbeddingRecord(
        schema_version=PROJECTION_SCHEMA_VERSION,
        embedding_uid=embedding_uid,
        claim_uid=row.claim_uid,
        entity_uid=row.entity_uid,
        report_id=row.report_id,
        content_hash=row.content_hash,
        embedding_version=request.embedding_version,
        provider=request.provider,
        model=response.model or request.model,
        dimensions=dimensions,
        vector=vector,
        external_vector_id=f"local:claim_embeddings:{embedding_uid}",
        metadata={
            **row.metadata,
            "provider_request_id": response.request_id or "",
            "provider_input_tokens": response.input_tokens,
        },
        status="embedded",
        generated_at_utc=generated_at_utc,
        updated_at_utc=generated_at_utc,
        attempt_count=0,
        error_code="",
        error_message="",
        error_retryable=False,
        error_severity="",
    )


def _failure_record(
    *,
    row: ClaimEmbeddingQueueItem,
    error: AppError,
    request: ClaimEmbeddingWorkflowRequest,
    generated_at_utc: str,
    embedding_uid: EntityUid,
) -> ClaimEmbeddingRecord:
    return ClaimEmbeddingRecord(
        schema_version=PROJECTION_SCHEMA_VERSION,
        embedding_uid=embedding_uid,
        claim_uid=row.claim_uid,
        entity_uid=row.entity_uid,
        report_id=row.report_id,
        content_hash=row.content_hash,
        embedding_version=request.embedding_version,
        provider=request.provider,
        model=request.model,
        dimensions=None,
        vector=None,
        external_vector_id=f"local:claim_embeddings:{embedding_uid}",
        metadata=row.metadata,
        status="failed",
        generated_at_utc=generated_at_utc,
        updated_at_utc=generated_at_utc,
        attempt_count=0,
        error_code=error.code,
        error_message=error.message,
        error_retryable=error.retryable,
        error_severity=error.severity,
    )


def _embedding_uid(
    deps: ClaimEmbeddingDependencies,
    row: ClaimEmbeddingQueueItem,
    request: ClaimEmbeddingWorkflowRequest,
) -> EntityUid:
    return deps.embedding_uid(
        entity_uid=str(row.entity_uid),
        content_hash=row.content_hash,
        embedding_version=request.embedding_version,
        provider=request.provider,
        model=request.model,
    )


def _persist(
    deps: ClaimEmbeddingDependencies,
    request: ClaimEmbeddingWorkflowRequest,
    record: ClaimEmbeddingRecord,
    ctx: RunContext,
) -> None:
    deps.persist_record(
        ClaimEmbeddingPersistRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=request.db_path,
            record=record,
        ),
        ctx,
    )


def run_claim_embedding_workflow(
    request: ClaimEmbeddingWorkflowRequest,
    *,
    dependencies: ClaimEmbeddingDependencies | None = None,
) -> ClaimEmbeddingWorkflowResponse:
    deps = dependencies or ClaimEmbeddingDependencies()
    root_ctx = child_context(
        request.ctx, task_id=f"{request.ctx.task_id}:claim_embeddings"
    )
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="claim_embedding_workflow_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "provider": request.provider,
                "model": request.model,
                "embedding_version": request.embedding_version,
                "limit": request.limit,
            },
        )
    )
    pending = deps.read_pending_rows(
        ClaimEmbeddingPendingReadRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=request.db_path,
            embedding_version=request.embedding_version,
            provider=request.provider,
            model=request.model,
            limit=request.limit,
        ),
        root_ctx,
    )
    rows = list(pending.rows)
    if not rows:
        response = ClaimEmbeddingWorkflowResponse(
            schema_version=PROJECTION_SCHEMA_VERSION,
            embedded_count=0,
            failed_count=0,
            skipped_count=0,
            processed_entity_uids=[],
        )
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="claim_embedding_workflow_complete",
                module=logger.name,
                fields={"embedded_count": 0, "failed_count": 0, "skipped_count": 0},
            )
        )
        return response

    processed: list[EntityUid] = [row.entity_uid for row in rows]
    generated_at_utc = _timestamp(deps)
    try:
        provider_response = deps.create_embeddings(
            OpenAIEmbeddingRequest(
                schema_version="1.0",
                api_key=request.api_key,
                model=request.model,
                inputs=[row.text_payload for row in rows],
                timeout_seconds=request.timeout_seconds,
                cost_ledger_path=request.cost_ledger_path,
                cost_daily_path=request.cost_daily_path,
                model_pricing=request.model_pricing,
            ),
            root_ctx,
        )
    except AppError as exc:
        for row in rows:
            _persist(
                deps,
                request,
                _failure_record(
                    row=row,
                    error=exc,
                    request=request,
                    generated_at_utc=generated_at_utc,
                    embedding_uid=_embedding_uid(deps, row, request),
                ),
                root_ctx,
            )
        response = ClaimEmbeddingWorkflowResponse(
            schema_version=PROJECTION_SCHEMA_VERSION,
            embedded_count=0,
            failed_count=len(rows),
            skipped_count=0,
            processed_entity_uids=processed,
        )
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="claim_embedding_workflow_complete",
                module=logger.name,
                fields={
                    "embedded_count": response.embedded_count,
                    "failed_count": response.failed_count,
                    "skipped_count": response.skipped_count,
                },
            )
        )
        return response

    if len(provider_response.embeddings) != len(rows):
        raise AppError(
            code="claim_embedding_provider_count_mismatch",
            message="Embedding response count did not match pending claim rows",
            retryable=True,
            severity="error",
            context={
                "expected": len(rows),
                "actual": len(provider_response.embeddings),
            },
        )
    for row, vector in zip(rows, provider_response.embeddings):
        _persist(
            deps,
            request,
            _success_record(
                row=row,
                vector=vector,
                dimensions=provider_response.dimensions,
                response=provider_response,
                request=request,
                generated_at_utc=generated_at_utc,
                embedding_uid=_embedding_uid(deps, row, request),
            ),
            root_ctx,
        )
    response = ClaimEmbeddingWorkflowResponse(
        schema_version=PROJECTION_SCHEMA_VERSION,
        embedded_count=len(rows),
        failed_count=0,
        skipped_count=0,
        processed_entity_uids=processed,
    )
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="claim_embedding_workflow_complete",
            module=logger.name,
            fields={
                "embedded_count": response.embedded_count,
                "failed_count": response.failed_count,
                "skipped_count": response.skipped_count,
            },
        )
    )
    return response
