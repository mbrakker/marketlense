from __future__ import annotations

"""Control-plane workflow for durable claim-level embeddings."""

import logging
import math
import time
import uuid
from dataclasses import dataclass
from datetime import timedelta
from typing import Callable, cast

from src.contracts.analytics_projection import (
    ClaimEmbeddingPersistRequest,
    ClaimEmbeddingQueueItem,
    ClaimEmbeddingQueueHealthItem,
    ClaimEmbeddingQueueHealthRequest,
    ClaimEmbeddingRecord,
    ClaimEmbeddingWorkflowRequest,
    ClaimEmbeddingWorkflowResponse,
    ContentClass,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.openai import OpenAIEmbeddingRequest, OpenAIEmbeddingResponse
from src.contracts.remediation import (
    RemediationArtifactReference,
    RemediationBudgetSummary,
    RemediationIdempotencyKey,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import EntityUid
from src.services import analytics_store_service, llm_service
from src.orchestrators.remediation_orchestrator import (
    record_workflow_failure,
    remediation_input_checksum,
)
from src.utils.costing import estimate_cost_usd
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
    read_queue_health: Callable = (
        analytics_store_service.read_claim_embedding_queue_health
    )
    acquire_execution_lease: Callable = (
        analytics_store_service.acquire_claim_embedding_execution_lease
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
    *,
    run_id: str,
    reason_code: str,
    next_eligible_at_utc: str = "",
    execution_lease_id: str = "",
) -> None:
    deps.persist_record(
        ClaimEmbeddingPersistRequest(
            schema_version=PROJECTION_SCHEMA_VERSION,
            db_path=request.db_path,
            record=record,
            queue_run_id=run_id,
            queue_reason_code=reason_code,
            next_eligible_at_utc=next_eligible_at_utc,
            execution_lease_id=execution_lease_id,
        ),
        ctx,
    )


def _queue_health_request(
    request: ClaimEmbeddingWorkflowRequest,
) -> ClaimEmbeddingQueueHealthRequest:
    return ClaimEmbeddingQueueHealthRequest(
        schema_version=PROJECTION_SCHEMA_VERSION,
        db_path=request.db_path,
        embedding_version=request.embedding_version,
        provider=request.provider,
        model=request.model,
        report_ids=request.report_ids,
        publishers=request.publishers,
        entity_types=["claim"],
        max_estimated_tokens=request.max_estimated_tokens,
        max_estimated_cost_usd=request.max_estimated_cost_usd,
        model_pricing=request.model_pricing,
    )


def _select_items(
    items: list[ClaimEmbeddingQueueHealthItem], request: ClaimEmbeddingWorkflowRequest
) -> tuple[list[ClaimEmbeddingQueueHealthItem], int, float]:
    """Select oldest-first rows under row, report, fairness and budget controls."""
    selected: list[ClaimEmbeddingQueueHealthItem] = []
    seen_reports: set[str] = set()
    publisher_counts: dict[str, int] = {}
    token_total = 0
    cost_total = 0.0
    avoided = 0
    avoided_cost = 0.0
    for item in items:
        if item.classification not in {"ready_to_embed", "retryable_failure"}:
            avoided += 1
            avoided_cost += item.estimated_cost_usd
            continue
        if (
            item.classification == "retryable_failure"
            and item.classification_reason == "retry_not_yet_eligible"
        ):
            avoided += 1
            avoided_cost += item.estimated_cost_usd
            continue
        publisher = item.publisher.casefold()
        prospective_reports = seen_reports | {str(item.report_id)}
        if request.limit > 0 and len(selected) >= request.limit:
            avoided += 1
            avoided_cost += item.estimated_cost_usd
            continue
        if request.max_reports > 0 and len(prospective_reports) > request.max_reports:
            avoided += 1
            avoided_cost += item.estimated_cost_usd
            continue
        if (
            request.publisher_fairness_limit > 0
            and publisher_counts.get(publisher, 0) >= request.publisher_fairness_limit
        ):
            avoided += 1
            avoided_cost += item.estimated_cost_usd
            continue
        if (
            request.max_estimated_tokens > 0
            and token_total + item.estimated_tokens > request.max_estimated_tokens
        ):
            avoided += 1
            avoided_cost += item.estimated_cost_usd
            continue
        if (
            request.max_estimated_cost_usd > 0
            and cost_total + item.estimated_cost_usd > request.max_estimated_cost_usd
        ):
            avoided += 1
            avoided_cost += item.estimated_cost_usd
            continue
        selected.append(item)
        seen_reports.add(str(item.report_id))
        publisher_counts[publisher] = publisher_counts.get(publisher, 0) + 1
        token_total += item.estimated_tokens
        cost_total += item.estimated_cost_usd
    return selected, avoided, avoided_cost


def _retry_timestamp(generated_at_utc: str, attempt_count: int) -> str:
    from datetime import datetime, timezone

    base = datetime.fromisoformat(generated_at_utc.replace("Z", "+00:00"))
    if base.tzinfo is None:
        base = base.replace(tzinfo=timezone.utc)
    seconds = min(3600, 60 * (2 ** max(0, attempt_count - 1)))
    return (base + timedelta(seconds=seconds)).isoformat()


def _run_claim_embedding_workflow(
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
    health = deps.read_queue_health(_queue_health_request(request), root_ctx)
    selected, avoided, avoided_cost = _select_items(list(health.items), request)
    queue_age_before_seconds = health.oldest_pending_age_seconds
    pending_before = health.total_pending
    if not selected:
        response = ClaimEmbeddingWorkflowResponse(
            schema_version=PROJECTION_SCHEMA_VERSION,
            embedded_count=0,
            failed_count=0,
            skipped_count=0,
            processed_entity_uids=[],
            provider_calls_avoided=avoided,
            estimated_cost_avoided_usd=avoided_cost,
            queue_age_before_seconds=queue_age_before_seconds,
            queue_age_after_seconds=queue_age_before_seconds,
        )
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="claim_embedding_workflow_complete",
                module=logger.name,
                fields={
                    "embedded_count": 0,
                    "failed_count": 0,
                    "skipped_count": response.skipped_count,
                    "provider_calls_avoided": response.provider_calls_avoided,
                },
            )
        )
        return response

    if request.dry_run:
        return ClaimEmbeddingWorkflowResponse(
            schema_version=PROJECTION_SCHEMA_VERSION,
            embedded_count=0,
            failed_count=0,
            skipped_count=len(selected) + avoided,
            processed_entity_uids=[],
            provider_calls_avoided=len(selected) + avoided,
            estimated_cost_avoided_usd=avoided_cost
            + sum(item.estimated_cost_usd for item in selected),
            queue_age_before_seconds=queue_age_before_seconds,
            queue_age_after_seconds=queue_age_before_seconds,
        )
    started = time.monotonic()
    run_id = str(request.ctx.run_id)
    processed: list[EntityUid] = []
    embedded_count = 0
    failed_count = 0
    actual_input_tokens = 0
    actual_cost = 0.0
    provider_latencies_ms: list[float] = []
    skipped_count = avoided
    for item in selected:
        if (
            request.max_runtime_seconds > 0
            and time.monotonic() - started >= request.max_runtime_seconds
        ):
            skipped_count += 1
            avoided += 1
            avoided_cost += item.estimated_cost_usd
            continue
        lease_id = uuid.uuid4().hex
        generated_at_utc = _timestamp(deps)
        lease_expires = _retry_timestamp(generated_at_utc, 7)
        acquired = deps.acquire_execution_lease(
            db_path=request.db_path,
            item=item,
            embedding_version=request.embedding_version,
            provider=request.provider,
            model=request.model,
            lease_id=lease_id,
            lease_expires_at_utc=lease_expires,
            ctx=root_ctx,
        )
        if not acquired:
            skipped_count += 1
            avoided += 1
            avoided_cost += item.estimated_cost_usd
            continue
        row = ClaimEmbeddingQueueItem(
            schema_version=PROJECTION_SCHEMA_VERSION,
            claim_uid=item.entity_uid,
            entity_uid=item.entity_uid,
            report_id=item.report_id,
            text_payload=item.text_payload,
            content_hash=item.content_hash,
            metadata=item.metadata,
            content_class=cast(ContentClass, item.content_class),
        )
        processed.append(row.entity_uid)
        try:
            provider_started = time.monotonic()
            provider_response = deps.create_embeddings(
                OpenAIEmbeddingRequest(
                    schema_version="1.0",
                    api_key=request.api_key,
                    model=request.model,
                    inputs=[row.text_payload],
                    timeout_seconds=request.timeout_seconds,
                    cost_ledger_path=request.cost_ledger_path,
                    cost_daily_path=request.cost_daily_path,
                    model_pricing=request.model_pricing,
                ),
                root_ctx,
            )
            provider_latencies_ms.append((time.monotonic() - provider_started) * 1000)
            if len(provider_response.embeddings) != 1:
                raise AppError(
                    code="claim_embedding_provider_count_mismatch",
                    message=(
                        "Embedding response count did not match one admitted claim row"
                    ),
                    retryable=True,
                    severity="error",
                    context={"actual": len(provider_response.embeddings)},
                )
        except AppError as exc:
            provider_latencies_ms.append((time.monotonic() - provider_started) * 1000)
            next_attempt = item.attempt_count + 1
            retryable = exc.retryable and next_attempt < max(1, request.max_retries)
            reason = exc.code if retryable else f"{exc.code}_retry_exhausted"
            _persist(
                deps,
                request,
                _failure_record(
                    row=row,
                    error=AppError(
                        code=reason,
                        message=exc.message,
                        cause=exc,
                        retryable=retryable,
                        severity=exc.severity,
                    ),
                    request=request,
                    generated_at_utc=generated_at_utc,
                    embedding_uid=_embedding_uid(deps, row, request),
                ),
                root_ctx,
                run_id=run_id,
                reason_code=reason,
                next_eligible_at_utc=(
                    _retry_timestamp(generated_at_utc, next_attempt)
                    if retryable
                    else ""
                ),
                execution_lease_id=lease_id,
            )
            if not retryable:
                record_workflow_failure(
                    state_db=request.state_db,
                    workflow="claim_embedding",
                    stage="provider_embedding",
                    operation="create_embeddings",
                    error=AppError(
                        code="claim_embedding_retry_budget_exhausted",
                        message="Claim embedding retry budget was exhausted",
                        cause=exc,
                        retryable=False,
                        severity=exc.severity,
                    ),
                    ctx=root_ctx,
                    input_checksum=row.content_hash,
                    report_id=str(row.report_id),
                    source_id=str(row.claim_uid),
                    publisher_id=str(row.metadata.get("publisher") or ""),
                    reusable_artifacts=[
                        RemediationArtifactReference(
                            schema_version="1.0",
                            name="claim_embedding_store",
                            reference=request.db_path,
                        )
                    ],
                    committed_side_effects=[
                        f"analytics_store:claim_embedding_failure:{_embedding_uid(deps, row, request)}"
                    ],
                    idempotency_keys=[
                        RemediationIdempotencyKey(
                            schema_version="1.0",
                            scope="claim_embedding.persist",
                            key=str(_embedding_uid(deps, row, request)),
                            input_checksum=row.content_hash,
                        )
                    ],
                    budget=RemediationBudgetSummary(
                        schema_version="1.0",
                        consumed={"attempts": next_attempt},
                        remaining={
                            "max_estimated_tokens": request.max_estimated_tokens,
                            "max_estimated_cost_usd": request.max_estimated_cost_usd,
                        },
                    ),
                )
            failed_count += 1
            continue
        actual_input_tokens += int(
            provider_response.input_tokens or item.estimated_tokens
        )
        actual_cost += estimate_cost_usd(
            request.model,
            int(provider_response.input_tokens or item.estimated_tokens),
            0,
            0,
            request.model_pricing,
        )
        _persist(
            deps,
            request,
            _success_record(
                row=row,
                vector=provider_response.embeddings[0],
                dimensions=provider_response.dimensions,
                response=provider_response,
                request=request,
                generated_at_utc=generated_at_utc,
                embedding_uid=_embedding_uid(deps, row, request),
            ),
            root_ctx,
            run_id=run_id,
            reason_code="embedding_completed",
            execution_lease_id=lease_id,
        )
        embedded_count += 1
    after_health = deps.read_queue_health(_queue_health_request(request), root_ctx)
    average_latency = (
        sum(provider_latencies_ms) / len(provider_latencies_ms)
        if provider_latencies_ms
        else 0.0
    )
    p95_latency = (
        sorted(provider_latencies_ms)[math.ceil(len(provider_latencies_ms) * 0.95) - 1]
        if provider_latencies_ms
        else 0.0
    )
    response = ClaimEmbeddingWorkflowResponse(
        schema_version=PROJECTION_SCHEMA_VERSION,
        embedded_count=embedded_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        processed_entity_uids=processed,
        provider_calls_avoided=avoided,
        estimated_cost_avoided_usd=avoided_cost,
        actual_input_tokens=actual_input_tokens,
        actual_cost_usd=actual_cost,
        queue_age_before_seconds=queue_age_before_seconds,
        queue_age_after_seconds=after_health.oldest_pending_age_seconds,
        backlog_burndown_count=max(0, pending_before - after_health.total_pending),
        average_provider_latency_ms=average_latency,
        p95_provider_latency_ms=p95_latency,
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
                "provider_calls_avoided": response.provider_calls_avoided,
                "actual_input_tokens": response.actual_input_tokens,
                "actual_cost_usd": response.actual_cost_usd,
            },
        )
    )
    return response


def run_claim_embedding_workflow(
    request: ClaimEmbeddingWorkflowRequest,
    *,
    dependencies: ClaimEmbeddingDependencies | None = None,
) -> ClaimEmbeddingWorkflowResponse:
    """Run a bounded batch and record unexpected terminal workflow failures."""

    try:
        return _run_claim_embedding_workflow(request, dependencies=dependencies)
    except Exception as exc:
        record_workflow_failure(
            state_db=request.state_db,
            workflow="claim_embedding",
            stage="workflow",
            operation="run_claim_embedding_workflow",
            error=exc,
            ctx=request.ctx,
            input_checksum=remediation_input_checksum(
                {
                    "db_path": request.db_path,
                    "embedding_version": request.embedding_version,
                    "provider": request.provider,
                    "model": request.model,
                    "report_ids": sorted(request.report_ids),
                }
            ),
            source_id=request.db_path,
            reusable_artifacts=[
                RemediationArtifactReference(
                    schema_version="1.0",
                    name="claim_embedding_store",
                    reference=request.db_path,
                )
            ],
            budget=RemediationBudgetSummary(
                schema_version="1.0",
                remaining={
                    "max_estimated_tokens": request.max_estimated_tokens,
                    "max_estimated_cost_usd": request.max_estimated_cost_usd,
                },
            ),
        )
        raise
