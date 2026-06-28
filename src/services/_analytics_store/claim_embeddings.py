from __future__ import annotations

"""Claim embedding persistence operations for the analytics store service."""

import hashlib
import json
import logging
import sqlite3
from dataclasses import asdict, replace
from typing import Any, cast

from src.contracts.analytics_projection import (
    ClaimEmbeddingStatus,
    ClaimEmbeddingPendingReadRequest,
    ClaimEmbeddingPendingReadResponse,
    ClaimEmbeddingPersistRequest,
    ClaimEmbeddingPersistResponse,
    ClaimEmbeddingQueueItem,
    ClaimEmbeddingReadRequest,
    ClaimEmbeddingReadResponse,
    ClaimEmbeddingRecord,
    ContentClass,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import EntityUid, ReportId
from src.services._analytics_store.common import _analytics_conn, _json
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.analytics_store_service")


def _embedding_uid(
    *,
    entity_uid: str,
    content_hash: str,
    embedding_version: str,
    provider: str,
    model: str,
) -> EntityUid:
    payload = _json(
        {
            "entity_uid": entity_uid,
            "content_hash": content_hash,
            "embedding_version": embedding_version,
            "provider": provider,
            "model": model,
        }
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return EntityUid(f"{entity_uid}:embedding:{digest[:24]}")


def claim_embedding_uid(
    *,
    entity_uid: str,
    content_hash: str,
    embedding_version: str,
    provider: str,
    model: str,
) -> EntityUid:
    return _embedding_uid(
        entity_uid=entity_uid,
        content_hash=content_hash,
        embedding_version=embedding_version,
        provider=provider,
        model=model,
    )


def _metadata_from_json(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _queue_item_from_row(row: sqlite3.Row) -> ClaimEmbeddingQueueItem:
    content_class = str(row["content_class"])
    if content_class not in {"evidence", "derived_evidence", "editorial"}:
        raise AppError(
            code="claim_embedding_content_class_invalid",
            message="Claim embedding queue row has invalid content_class",
            retryable=False,
            severity="error",
            context={
                "entity_uid": str(row["entity_uid"]),
                "content_class": content_class,
            },
        )
    return ClaimEmbeddingQueueItem(
        schema_version=PROJECTION_SCHEMA_VERSION,
        claim_uid=EntityUid(str(row["claim_uid"])),
        entity_uid=EntityUid(str(row["entity_uid"])),
        report_id=ReportId(str(row["report_id"])),
        text_payload=str(row["text_payload"]),
        content_hash=str(row["content_hash"]),
        metadata=_metadata_from_json(str(row["metadata_json"])),
        content_class=cast(ContentClass, content_class),
    )


def _record_from_row(row: sqlite3.Row) -> ClaimEmbeddingRecord:
    status = str(row["status"])
    if status not in {"embedded", "failed"}:
        raise AppError(
            code="claim_embedding_status_invalid",
            message="Claim embedding record has invalid status",
            retryable=False,
            severity="error",
            context={"embedding_uid": str(row["embedding_uid"]), "status": status},
        )
    vector_raw = row["vector_json"]
    vector: list[float] | None = None
    if vector_raw:
        parsed = _metadata_from_json(f'{{"vector":{vector_raw}}}').get("vector")
        if isinstance(parsed, list):
            vector = [float(value) for value in parsed]
    return ClaimEmbeddingRecord(
        schema_version=PROJECTION_SCHEMA_VERSION,
        embedding_uid=EntityUid(str(row["embedding_uid"])),
        claim_uid=EntityUid(str(row["claim_uid"])),
        entity_uid=EntityUid(str(row["entity_uid"])),
        report_id=ReportId(str(row["report_id"])),
        content_hash=str(row["content_hash"]),
        embedding_version=str(row["embedding_version"]),
        provider=str(row["provider"]),
        model=str(row["model"]),
        dimensions=int(row["dimensions"]) if row["dimensions"] is not None else None,
        vector=vector,
        external_vector_id=str(row["external_vector_id"] or ""),
        metadata=_metadata_from_json(str(row["metadata_json"])),
        status=cast(ClaimEmbeddingStatus, status),
        generated_at_utc=str(row["generated_at_utc"]),
        updated_at_utc=str(row["updated_at_utc"]),
        attempt_count=int(row["attempt_count"]),
        error_code=str(row["error_code"] or ""),
        error_message=str(row["error_message"] or ""),
        error_retryable=bool(row["error_retryable"]),
        error_severity=str(row["error_severity"] or ""),
    )


def read_pending_claim_embedding_rows(
    request: ClaimEmbeddingPendingReadRequest,
    ctx: RunContext,
) -> ClaimEmbeddingPendingReadResponse:
    limit = max(0, int(request.limit))
    logger.info(
        log_event(
            ctx,
            role="service",
            event="claim_embedding_pending_read_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "embedding_version": request.embedding_version,
                "provider": request.provider,
                "model": request.model,
                "limit": limit,
            },
        )
    )
    if limit <= 0:
        return ClaimEmbeddingPendingReadResponse(
            schema_version=PROJECTION_SCHEMA_VERSION, rows=[]
        )
    try:
        with _analytics_conn(request.db_path, ctx) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT
                  c.claim_uid,
                  q.entity_uid,
                  q.report_id,
                  q.text_payload,
                  q.content_hash,
                  q.metadata_json,
                  q.content_class
                FROM vector_projection_queue q
                JOIN report_claims c ON c.claim_uid = q.entity_uid
                WHERE q.entity_type = 'claim'
                  AND (
                    q.embedding_status IN ('pending', 'failed')
                    OR q.embedding_version <> ?
                    OR NOT EXISTS (
                      SELECT 1
                      FROM claim_embeddings e
                      WHERE e.entity_uid = q.entity_uid
                        AND e.content_hash = q.content_hash
                        AND e.embedding_version = ?
                        AND e.provider = ?
                        AND e.model = ?
                        AND e.status = 'embedded'
                    )
                  )
                ORDER BY q.updated_at_utc, q.entity_uid
                LIMIT ?
                """,
                (
                    request.embedding_version,
                    request.embedding_version,
                    request.provider,
                    request.model,
                    limit,
                ),
            ).fetchall()
    except sqlite3.Error as exc:
        raise AppError(
            code="claim_embedding_pending_read_failed",
            message="Failed to read pending claim embedding rows",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": request.db_path},
        ) from exc
    response = ClaimEmbeddingPendingReadResponse(
        schema_version=PROJECTION_SCHEMA_VERSION,
        rows=[_queue_item_from_row(row) for row in rows],
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="claim_embedding_pending_read_complete",
            module=logger.name,
            fields={"row_count": len(response.rows)},
        )
    )
    return response


def _validate_embedding_record(record: ClaimEmbeddingRecord) -> None:
    if record.status == "embedded":
        if not record.vector or not record.dimensions:
            raise AppError(
                code="claim_embedding_vector_missing",
                message="Embedded claim records require a non-empty vector",
                retryable=False,
                severity="error",
                context={"embedding_uid": str(record.embedding_uid)},
            )
        if int(record.dimensions) != len(record.vector):
            raise AppError(
                code="claim_embedding_dimensions_invalid",
                message="Claim embedding dimensions must match vector length",
                retryable=False,
                severity="error",
                context={"embedding_uid": str(record.embedding_uid)},
            )
        return
    if record.status == "failed":
        if not record.error_code.strip() or not record.error_message.strip():
            raise AppError(
                code="claim_embedding_error_taxonomy_missing",
                message="Failed claim embedding records require typed error details",
                retryable=False,
                severity="error",
                context={"embedding_uid": str(record.embedding_uid)},
            )
        return
    raise AppError(
        code="claim_embedding_status_invalid",
        message="Claim embedding status must be embedded or failed",
        retryable=False,
        severity="error",
        context={"embedding_uid": str(record.embedding_uid), "status": record.status},
    )


def persist_claim_embedding(
    request: ClaimEmbeddingPersistRequest,
    ctx: RunContext,
) -> ClaimEmbeddingPersistResponse:
    record = request.record
    _validate_embedding_record(record)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="claim_embedding_persist_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "embedding_uid": str(record.embedding_uid),
                "claim_uid": str(record.claim_uid),
                "entity_uid": str(record.entity_uid),
                "report_id": str(record.report_id),
                "status": record.status,
                "embedding_version": record.embedding_version,
                "provider": record.provider,
                "model": record.model,
                "content_hash": record.content_hash,
            },
        )
    )
    try:
        with _analytics_conn(request.db_path, ctx) as conn:
            conn.row_factory = sqlite3.Row
            claim = conn.execute(
                "SELECT claim_uid FROM report_claims WHERE claim_uid=?",
                (str(record.claim_uid),),
            ).fetchone()
            if claim is None:
                raise AppError(
                    code="claim_embedding_claim_missing",
                    message="Claim embedding record must link to report_claims.claim_uid",
                    retryable=False,
                    severity="error",
                    context={"claim_uid": str(record.claim_uid)},
                )
            existing = conn.execute(
                "SELECT attempt_count FROM claim_embeddings WHERE embedding_uid=?",
                (str(record.embedding_uid),),
            ).fetchone()
            attempt_count = int(existing["attempt_count"] or 0) + 1 if existing else 1
            stored_record = replace(record, attempt_count=attempt_count)
            conn.execute(
                """
                INSERT INTO claim_embeddings(
                  embedding_uid,
                  claim_uid,
                  entity_uid,
                  report_id,
                  content_hash,
                  embedding_version,
                  provider,
                  model,
                  dimensions,
                  vector_json,
                  external_vector_id,
                  metadata_json,
                  status,
                  generated_at_utc,
                  updated_at_utc,
                  attempt_count,
                  error_code,
                  error_message,
                  error_retryable,
                  error_severity
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(embedding_uid) DO UPDATE SET
                  dimensions=excluded.dimensions,
                  vector_json=excluded.vector_json,
                  external_vector_id=excluded.external_vector_id,
                  metadata_json=excluded.metadata_json,
                  status=excluded.status,
                  generated_at_utc=excluded.generated_at_utc,
                  updated_at_utc=excluded.updated_at_utc,
                  attempt_count=excluded.attempt_count,
                  error_code=excluded.error_code,
                  error_message=excluded.error_message,
                  error_retryable=excluded.error_retryable,
                  error_severity=excluded.error_severity
                """,
                (
                    str(stored_record.embedding_uid),
                    str(stored_record.claim_uid),
                    str(stored_record.entity_uid),
                    str(stored_record.report_id),
                    stored_record.content_hash,
                    stored_record.embedding_version,
                    stored_record.provider,
                    stored_record.model,
                    stored_record.dimensions,
                    _json(stored_record.vector)
                    if stored_record.vector is not None
                    else None,
                    stored_record.external_vector_id,
                    _json(stored_record.metadata),
                    stored_record.status,
                    stored_record.generated_at_utc,
                    stored_record.updated_at_utc,
                    stored_record.attempt_count,
                    stored_record.error_code,
                    stored_record.error_message,
                    1 if stored_record.error_retryable else 0,
                    stored_record.error_severity,
                ),
            )
            conn.execute(
                """
                UPDATE vector_projection_queue
                SET embedding_status=?,
                    embedding_version=?,
                    updated_at_utc=?
                WHERE entity_uid=?
                """,
                (
                    stored_record.status,
                    stored_record.embedding_version,
                    stored_record.updated_at_utc,
                    str(stored_record.entity_uid),
                ),
            )
    except AppError:
        raise
    except sqlite3.Error as exc:
        raise AppError(
            code="claim_embedding_persist_failed",
            message="Failed to persist claim embedding record",
            cause=exc,
            retryable=True,
            severity="error",
            context={
                "db_path": request.db_path,
                "embedding_uid": str(record.embedding_uid),
            },
        ) from exc
    response = ClaimEmbeddingPersistResponse(
        schema_version=PROJECTION_SCHEMA_VERSION,
        embedding_uid=record.embedding_uid,
        status=record.status,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="claim_embedding_persist_complete",
            module=logger.name,
            fields={**asdict(response), "embedding_uid": str(response.embedding_uid)},
        )
    )
    return response


def _matches_topics(metadata: dict[str, Any], topics: set[str]) -> bool:
    if not topics:
        return True
    candidates: set[str] = set()
    for key in ("taxonomy", "category_ids"):
        values = metadata.get(key)
        if isinstance(values, list):
            candidates.update(str(value).strip().casefold() for value in values)
    return bool(candidates.intersection(topics))


def read_claim_embeddings(
    request: ClaimEmbeddingReadRequest,
    ctx: RunContext,
) -> ClaimEmbeddingReadResponse:
    statuses = [
        str(status).strip() for status in request.statuses if str(status).strip()
    ]
    if not statuses:
        statuses = ["embedded"]
    if not set(statuses).issubset({"embedded", "failed"}):
        raise AppError(
            code="claim_embedding_read_status_invalid",
            message="Claim embedding read statuses must be embedded or failed",
            retryable=False,
            severity="error",
            context={"statuses": statuses},
        )
    limit = max(0, int(request.limit))
    topics = {
        str(topic).strip().casefold() for topic in request.topics if str(topic).strip()
    }
    clauses = ["status IN (" + ",".join("?" for _ in statuses) + ")"]
    params: list[Any] = list(statuses)
    if request.claim_uids:
        clauses.append(
            "claim_uid IN (" + ",".join("?" for _ in request.claim_uids) + ")"
        )
        params.extend(str(value) for value in request.claim_uids)
    if request.report_ids:
        clauses.append(
            "report_id IN (" + ",".join("?" for _ in request.report_ids) + ")"
        )
        params.extend(str(value) for value in request.report_ids)
    params.append(max(limit * 5, limit, 1))
    try:
        with _analytics_conn(request.db_path, ctx) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                f"""
                SELECT *
                FROM claim_embeddings
                WHERE {" AND ".join(clauses)}
                ORDER BY generated_at_utc DESC, embedding_uid DESC
                LIMIT ?
                """,
                tuple(params),
            ).fetchall()
    except sqlite3.Error as exc:
        raise AppError(
            code="claim_embedding_read_failed",
            message="Failed to read claim embedding records",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": request.db_path},
        ) from exc
    records = [
        record
        for record in (_record_from_row(row) for row in rows)
        if _matches_topics(record.metadata, topics)
    ][:limit]
    return ClaimEmbeddingReadResponse(
        schema_version=PROJECTION_SCHEMA_VERSION,
        embeddings=records,
    )
