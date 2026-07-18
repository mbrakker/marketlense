from __future__ import annotations

"""Deterministic, no-provider health and reconciliation for claim embeddings."""

import hashlib
import json
import logging
import sqlite3
from collections import Counter
from datetime import UTC, datetime, timedelta
from typing import Any

from src.contracts.analytics_projection import (
    PROJECTION_SCHEMA_VERSION,
    ClaimEmbeddingQueueHealthItem,
    ClaimEmbeddingQueueHealthRequest,
    ClaimEmbeddingQueueHealthResponse,
    ClaimEmbeddingQueueReconcileRequest,
    ClaimEmbeddingQueueReconcileResponse,
    QueueClassification,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import EntityUid, ReportId
from src.services._analytics_store.claim_embeddings import _metadata_from_json
from src.services._analytics_store.common import _analytics_conn, _json
from src.utils.costing import estimate_cost_usd, estimate_text_tokens
from src.utils.errors import AppError
from src.utils.logging import log_event


logger = logging.getLogger("market_lense.analytics_store_service")

_VALID_CONTENT_CLASSES = {"evidence", "derived_evidence", "editorial"}
_READY = {"ready_to_embed", "retryable_failure"}


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _parse_utc(value: object, now: datetime) -> datetime:
    rendered = str(value or "").strip()
    if not rendered:
        return now
    try:
        parsed = datetime.fromisoformat(rendered.replace("Z", "+00:00"))
    except ValueError:
        return now
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _age_bucket(created_at_utc: object, now: datetime) -> str:
    seconds = max(0, int((now - _parse_utc(created_at_utc, now)).total_seconds()))
    if seconds < 24 * 60 * 60:
        return "under_1_day"
    if seconds <= 7 * 24 * 60 * 60:
        return "1_to_7_days"
    if seconds <= 30 * 24 * 60 * 60:
        return "8_to_30_days"
    if seconds <= 60 * 24 * 60 * 60:
        return "31_to_60_days"
    return "over_60_days"


def _canonical_content_hash(
    *, text_payload: str, metadata: dict[str, Any], entity_type: str, content_class: str
) -> str:
    payload = {
        "schema_version": PROJECTION_SCHEMA_VERSION,
        "entity_type": entity_type,
        "text_payload": text_payload,
        "metadata": metadata,
        "content_class": content_class,
    }
    rendered = json.dumps(payload, ensure_ascii=True, sort_keys=True, default=str)
    return hashlib.sha256(rendered.encode("utf-8")).hexdigest()


def _current_claim_text(row: sqlite3.Row) -> str | None:
    if str(row["entity_type"]) != "claim":
        return None
    if row["current_claim_uid"] is None:
        return ""
    parts = [f"Claim: {str(row['current_claim'] or '')}"]
    evidence = str(row["current_evidence"] or "")
    if evidence:
        parts.append(f"Evidence: {evidence}")
    return "\n".join(parts)


def _classification(
    row: sqlite3.Row,
    request: ClaimEmbeddingQueueHealthRequest,
    now: datetime,
) -> tuple[QueueClassification, str, int, float, dict[str, Any]]:
    metadata = _metadata_from_json(str(row["metadata_json"] or "{}"))
    text_payload = str(row["text_payload"] or "")
    content_hash = str(row["content_hash"] or "")
    content_class = str(row["content_class"] or "")
    estimated_tokens = estimate_text_tokens(text_payload)
    estimated_cost = estimate_cost_usd(
        request.model, estimated_tokens, 0, 0, request.model_pricing
    )
    if (
        not text_payload
        or len(content_hash) != 64
        or content_class not in _VALID_CONTENT_CLASSES
    ):
        return (
            "invalid_payload",
            "invalid_queue_payload",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    if row["report_file_id"] is None:
        return (
            "orphaned_report",
            "report_missing",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    if str(row["entity_type"]) != "claim":
        return (
            "unknown_requires_review",
            "claim_embedding_workflow_supports_claim_rows_only",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    current_claim_text = _current_claim_text(row)
    if current_claim_text == "":
        return (
            "orphaned_report",
            "projected_claim_missing",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    if current_claim_text is not None:
        current_hash = _canonical_content_hash(
            text_payload=current_claim_text,
            metadata=metadata,
            entity_type="claim",
            content_class=content_class,
        )
        if current_hash != content_hash or current_claim_text != text_payload:
            return (
                "stale_content",
                "current_claim_hash_changed",
                estimated_tokens,
                estimated_cost,
                metadata,
            )
    if int(row["matching_embedding_count"] or 0) > 0:
        return (
            "already_satisfied",
            "durable_embedding_exists",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    if (
        str(row["execution_lease_id"] or "")
        and _parse_utc(row["execution_lease_expires_at_utc"], now) > now
    ):
        return (
            "leased",
            "active_execution_lease",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    status = str(row["embedding_status"] or "")
    reason = str(row["queue_reason_code"] or "")
    if reason == "embedding_version_obsolete":
        return "obsolete_version", reason, estimated_tokens, estimated_cost, metadata
    if status == "failed" and not bool(row["queue_error_retryable"]):
        return (
            "terminal_failure",
            reason or "terminal_failure",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    if status == "failed":
        eligible = _parse_utc(row["next_eligible_at_utc"], now)
        if eligible > now:
            return (
                "retryable_failure",
                "retry_not_yet_eligible",
                estimated_tokens,
                estimated_cost,
                metadata,
            )
        return (
            "retryable_failure",
            reason or "retryable_failure",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    if (
        str(row["embedding_version"] or "")
        and str(row["embedding_version"]) != request.embedding_version
    ):
        return (
            "ready_to_embed",
            "configured_version_requires_embedding",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    if request.max_estimated_tokens and estimated_tokens > request.max_estimated_tokens:
        return (
            "blocked_by_budget",
            "token_budget_exceeded",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    if (
        request.max_estimated_cost_usd
        and estimated_cost > request.max_estimated_cost_usd
    ):
        return (
            "blocked_by_budget",
            "cost_budget_exceeded",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    if status == "pending":
        return (
            "ready_to_embed",
            "pending_current_projection",
            estimated_tokens,
            estimated_cost,
            metadata,
        )
    return (
        "unknown_requires_review",
        "unrecognized_queue_state",
        estimated_tokens,
        estimated_cost,
        metadata,
    )


def _rows(
    conn: sqlite3.Connection, request: ClaimEmbeddingQueueHealthRequest
) -> list[sqlite3.Row]:
    clauses = ["1=1"]
    params: list[object] = [
        request.embedding_version,
        request.provider,
        request.model,
    ]
    if request.report_ids:
        clauses.append(
            "q.report_id IN (" + ",".join("?" for _ in request.report_ids) + ")"
        )
        params.extend(str(value) for value in request.report_ids)
    if request.entity_types:
        clauses.append(
            "q.entity_type IN (" + ",".join("?" for _ in request.entity_types) + ")"
        )
        params.extend(str(value) for value in request.entity_types)
    if request.publishers:
        clauses.append(
            "lower(COALESCE(r.publisher, '')) IN ("
            + ",".join("?" for _ in request.publishers)
            + ")"
        )
        params.extend(str(value).strip().lower() for value in request.publishers)
    conn.row_factory = sqlite3.Row
    return conn.execute(
        f"""
        SELECT
          q.*,
          c.claim_uid AS current_claim_uid,
          c.claim AS current_claim,
          c.evidence AS current_evidence,
          c.schema_version AS current_projection_schema_version,
          r.file_id AS report_file_id,
          r.publisher AS report_publisher,
          EXISTS(
            SELECT 1 FROM claim_embeddings e
            WHERE e.entity_uid=q.entity_uid
              AND e.content_hash=q.content_hash
              AND e.embedding_version=?
              AND e.provider=?
              AND e.model=?
              AND e.status='embedded'
          ) AS matching_embedding_count
        FROM vector_projection_queue q
        LEFT JOIN report_claims c ON c.claim_uid=q.entity_uid
        LEFT JOIN reports r ON r.file_id=q.report_id OR r.report_id=q.report_id
        WHERE {" AND ".join(clauses)}
        ORDER BY q.created_at_utc ASC, q.entity_uid ASC
        """,
        tuple(params),
    ).fetchall()


def _item(
    row: sqlite3.Row,
    request: ClaimEmbeddingQueueHealthRequest,
    now: datetime,
) -> ClaimEmbeddingQueueHealthItem:
    classification, reason, tokens, cost, metadata = _classification(row, request, now)
    return ClaimEmbeddingQueueHealthItem(
        schema_version=PROJECTION_SCHEMA_VERSION,
        entity_uid=EntityUid(str(row["entity_uid"])),
        report_id=ReportId(str(row["report_id"])),
        entity_type=str(row["entity_type"]),
        publisher=str(row["report_publisher"] or metadata.get("publisher") or ""),
        content_class=str(row["content_class"]),
        content_hash=str(row["content_hash"]),
        projection_schema_version=str(
            row["projection_schema_version"]
            or row["current_projection_schema_version"]
            or metadata.get("schema_version")
            or ""
        ),
        embedding_status=str(row["embedding_status"]),
        embedding_version=str(row["embedding_version"]),
        provider=request.provider,
        model=request.model,
        error_code=str(row["queue_reason_code"] or ""),
        error_retryable=bool(row["queue_error_retryable"]),
        attempt_count=int(row["queue_attempt_count"] or 0),
        next_eligible_at_utc=str(row["next_eligible_at_utc"] or ""),
        created_at_utc=str(row["created_at_utc"]),
        updated_at_utc=str(row["updated_at_utc"]),
        age_bucket=_age_bucket(row["created_at_utc"], now),
        classification=classification,
        classification_reason=reason,
        estimated_tokens=tokens,
        estimated_cost_usd=cost,
        text_payload=str(row["text_payload"]),
        metadata=metadata,
    )


def read_claim_embedding_queue_health(
    request: ClaimEmbeddingQueueHealthRequest,
    ctx: RunContext,
) -> ClaimEmbeddingQueueHealthResponse:
    """Read and classify the queue without provider calls or database writes."""
    logger.info(
        log_event(
            ctx,
            role="service",
            event="claim_embedding_queue_health_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "provider": request.provider,
                "model": request.model,
            },
        )
    )
    now = _utc_now()
    try:
        with _analytics_conn(request.db_path, ctx) as conn:
            items = [_item(row, request, now) for row in _rows(conn, request)]
            transition_rows = conn.execute(
                """SELECT new_status,timestamp_utc FROM claim_embedding_queue_transitions
                WHERE timestamp_utc >= ?""",
                ((now - timedelta(hours=24)).isoformat(),),
            ).fetchall()
    except sqlite3.Error as exc:
        raise AppError(
            code="claim_embedding_queue_health_failed",
            message="Failed to assess the claim embedding queue",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": request.db_path},
        ) from exc
    classification_counts = Counter(item.classification for item in items)
    status_counts = Counter(item.embedding_status for item in items)
    pending_ages = [
        max(0, int((now - _parse_utc(item.created_at_utc, now)).total_seconds()))
        for item in items
        if item.classification in _READY
    ]
    sorted_ages = sorted(pending_ages)

    def _percentile(percent: float) -> int:
        if not sorted_ages:
            return 0
        index = max(0, min(len(sorted_ages) - 1, int((len(sorted_ages) - 1) * percent)))
        return sorted_ages[index]

    completed_last_day = sum(str(row[0] or "") == "embedded" for row in transition_rows)
    throughput = round(completed_last_day / 24.0, 6)
    terminal = sum(
        1
        for item in items
        if item.classification in {"already_satisfied", "terminal_failure"}
        or item.embedding_status == "embedded"
    )
    retry_reasons = Counter(
        item.classification_reason
        for item in items
        if item.classification == "retryable_failure"
    )
    terminal_reasons = Counter(
        item.classification_reason
        for item in items
        if item.classification
        in {"terminal_failure", "invalid_payload", "orphaned_report"}
    )
    response = ClaimEmbeddingQueueHealthResponse(
        schema_version=PROJECTION_SCHEMA_VERSION,
        items=items,
        classification_counts=dict(sorted(classification_counts.items())),
        status_counts=dict(sorted(status_counts.items())),
        total_pending=sum(1 for item in items if item.embedding_status == "pending"),
        oldest_pending_age_seconds=max(pending_ages, default=0),
        age_percentiles_seconds={
            "p50": _percentile(0.50),
            "p95": _percentile(0.95),
            "p99": _percentile(0.99),
        },
        observed_throughput_per_hour=throughput,
        completion_rate=(round(terminal / len(items), 6) if items else None),
        estimated_drain_seconds=(
            round(len(pending_ages) / throughput * 3600.0, 3) if throughput else None
        ),
        retry_reason_counts=dict(sorted(retry_reasons.items())),
        terminal_reason_counts=dict(sorted(terminal_reasons.items())),
        content_hash_skip_count=sum(
            1 for item in items if item.classification == "already_satisfied"
        ),
        model_version_mismatch_count=sum(
            1 for item in items if item.classification == "obsolete_version"
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="claim_embedding_queue_health_complete",
            module=logger.name,
            fields={
                "row_count": len(items),
                "classification_counts": response.classification_counts,
                "oldest_pending_age_seconds": response.oldest_pending_age_seconds,
                "observed_throughput_per_hour": response.observed_throughput_per_hour,
            },
        )
    )
    return response


def _record_transition(
    conn: sqlite3.Connection,
    *,
    item: ClaimEmbeddingQueueHealthItem,
    prior_status: str,
    new_status: str,
    reason_code: str,
    actor: str,
    run_id: str,
    timestamp_utc: str,
) -> None:
    conn.execute(
        """
        INSERT INTO claim_embedding_queue_transitions(
          entity_uid,report_id,prior_status,new_status,reason_code,actor,run_id,
          timestamp_utc,content_hash,embedding_version,provider,model,details_json
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            str(item.entity_uid),
            str(item.report_id),
            prior_status,
            new_status,
            reason_code,
            actor,
            run_id,
            timestamp_utc,
            item.content_hash,
            item.embedding_version,
            item.provider,
            item.model,
            _json(
                {"classification": item.classification, "age_bucket": item.age_bucket}
            ),
        ),
    )


def reconcile_claim_embedding_queue(
    request: ClaimEmbeddingQueueReconcileRequest,
    ctx: RunContext,
) -> ClaimEmbeddingQueueReconcileResponse:
    """Apply only deterministic, no-provider queue transitions with audit history."""
    health = read_claim_embedding_queue_health(request.health_request, ctx)
    changed: list[EntityUid] = []
    now = _utc_now().isoformat()
    actions = {
        "already_satisfied": (
            "embedded",
            "durable_embedding_already_satisfied",
            False,
            request.health_request.embedding_version,
        ),
        "obsolete_version": ("failed", "embedding_version_obsolete", False, ""),
        "stale_content": (
            "pending",
            "content_hash_stale_reprojection_required",
            False,
            "",
        ),
        "orphaned_report": ("failed", "orphaned_report", False, ""),
    }
    if not request.dry_run:
        try:
            with _analytics_conn(request.health_request.db_path, ctx) as conn:
                for item in health.items:
                    action = actions.get(item.classification)
                    if action is None:
                        continue
                    new_status, reason, retryable, version = action
                    if (
                        item.embedding_status == new_status
                        and item.error_code == reason
                        and item.embedding_version == version
                    ):
                        continue
                    cursor = conn.execute(
                        """
                        UPDATE vector_projection_queue
                        SET embedding_status=?, embedding_version=?, queue_reason_code=?,
                            queue_error_retryable=?, next_eligible_at_utc='',
                            queue_actor=?, execution_lease_id='',
                            execution_lease_expires_at_utc='', updated_at_utc=?
                        WHERE entity_uid=? AND content_hash=?
                        """,
                        (
                            new_status,
                            version,
                            reason,
                            1 if retryable else 0,
                            request.actor,
                            now,
                            str(item.entity_uid),
                            item.content_hash,
                        ),
                    )
                    if cursor.rowcount != 1:
                        continue
                    _record_transition(
                        conn,
                        item=item,
                        prior_status=item.embedding_status,
                        new_status=new_status,
                        reason_code=reason,
                        actor=request.actor,
                        run_id=request.run_id,
                        timestamp_utc=now,
                    )
                    changed.append(item.entity_uid)
        except sqlite3.Error as exc:
            raise AppError(
                code="claim_embedding_queue_reconcile_failed",
                message="Failed to reconcile the claim embedding queue",
                cause=exc,
                retryable=True,
                severity="error",
                context={"db_path": request.health_request.db_path},
            ) from exc
    response = ClaimEmbeddingQueueReconcileResponse(
        schema_version=PROJECTION_SCHEMA_VERSION,
        run_id=request.run_id,
        transitioned_entity_uids=changed,
        classification_counts=health.classification_counts,
        provider_calls_avoided=sum(
            count
            for name, count in health.classification_counts.items()
            if name not in _READY
        ),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="claim_embedding_queue_reconcile_complete",
            module=logger.name,
            fields={
                "schema_version": response.schema_version,
                "run_id": response.run_id,
                "transition_count": len(changed),
                "classification_count": len(response.classification_counts),
                "provider_calls_avoided": response.provider_calls_avoided,
                "dry_run": request.dry_run,
            },
        )
    )
    return response


def acquire_claim_embedding_execution_lease(
    *,
    db_path: str,
    item: ClaimEmbeddingQueueHealthItem,
    embedding_version: str,
    provider: str,
    model: str,
    lease_id: str,
    lease_expires_at_utc: str,
    ctx: RunContext,
) -> bool:
    """Atomically admit one still-current row so concurrent runs cannot call twice."""
    now = _utc_now().isoformat()
    try:
        with _analytics_conn(db_path, ctx) as conn:
            conn.execute("BEGIN IMMEDIATE")
            current_request = ClaimEmbeddingQueueHealthRequest(
                schema_version=PROJECTION_SCHEMA_VERSION,
                db_path=db_path,
                embedding_version=embedding_version,
                provider=provider,
                model=model,
                entity_types=["claim"],
            )
            current = next(
                (
                    _item(row, current_request, _utc_now())
                    for row in _rows(conn, current_request)
                    if str(row["entity_uid"]) == str(item.entity_uid)
                ),
                None,
            )
            if (
                current is None
                or current.content_hash != item.content_hash
                or current.classification not in _READY
            ):
                return False
            cursor = conn.execute(
                """
                UPDATE vector_projection_queue
                SET execution_lease_id=?, execution_lease_expires_at_utc=?, queue_actor='claim_embedding_workflow'
                WHERE entity_uid=? AND content_hash=?
                  AND (execution_lease_id='' OR execution_lease_expires_at_utc<?)
                  AND NOT EXISTS (
                    SELECT 1 FROM claim_embeddings e
                    WHERE e.entity_uid=vector_projection_queue.entity_uid
                      AND e.content_hash=vector_projection_queue.content_hash
                      AND e.embedding_version=? AND e.provider=? AND e.model=?
                      AND e.status='embedded'
                  )
                """,
                (
                    lease_id,
                    lease_expires_at_utc,
                    str(item.entity_uid),
                    item.content_hash,
                    now,
                    embedding_version,
                    provider,
                    model,
                ),
            )
            return cursor.rowcount == 1
    except sqlite3.Error as exc:
        raise AppError(
            code="claim_embedding_queue_lease_failed",
            message="Failed to reserve a claim embedding queue row",
            cause=exc,
            retryable=True,
            severity="error",
            context={"entity_uid": str(item.entity_uid)},
        ) from exc
