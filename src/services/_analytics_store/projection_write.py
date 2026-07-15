from __future__ import annotations

"""Projection Write operations for the analytics store service."""

import logging
import sqlite3
from dataclasses import asdict
from typing import Any, Sequence
from src.contracts.analytics_projection import (
    AnalyticsProjectionFailureRequest,
    AnalyticsProjectionFailureResponse,
    AnalyticsProjectionUpsertRequest,
    AnalyticsProjectionUpsertResponse,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId
from src.utils.errors import AppError
from src.utils.logging import log_event

from src.services._analytics_store.common import (
    _EMBEDDING_STATUSES,
    _analytics_conn,
    _json,
    _lineage_values,
    _table_exists,
    _uid_set,
)

logger = logging.getLogger("market_lense.analytics_store_service")


def _report_source_url_from_store(
    conn: sqlite3.Connection,
    *,
    report_title: str,
    publisher: str,
    source_md5: str,
) -> str:
    if not _table_exists(conn, "report_sources"):
        return ""
    if source_md5:
        row = conn.execute(
            """
            SELECT landing_page_url
            FROM report_sources
            WHERE md5=? AND COALESCE(landing_page_url, '') <> ''
            ORDER BY downloaded_at_utc DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            (source_md5,),
        ).fetchone()
        if row and str(row[0] or "").strip():
            return str(row[0]).strip()
    normalized_title = report_title.strip().casefold()
    normalized_publisher = publisher.strip().casefold()
    if not normalized_title:
        return ""
    row = conn.execute(
        """
        SELECT landing_page_url
        FROM report_sources
        WHERE lower(report_name)=?
          AND (?='' OR lower(COALESCE(publisher_name, ''))=?)
          AND COALESCE(landing_page_url, '') <> ''
        ORDER BY downloaded_at_utc DESC, updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_title, normalized_publisher, normalized_publisher),
    ).fetchone()
    return str(row[0]).strip() if row and str(row[0] or "").strip() else ""


def _delete_stale(
    conn: sqlite3.Connection,
    *,
    table: str,
    key_column: str,
    report_id: str,
    active_uids: set[str],
) -> None:
    if active_uids:
        placeholders = ",".join("?" for _ in active_uids)
        conn.execute(
            f"DELETE FROM {table} WHERE report_id=? AND {key_column} NOT IN ({placeholders})",
            (report_id, *sorted(active_uids)),
        )
        return
    conn.execute(f"DELETE FROM {table} WHERE report_id=?", (report_id,))


def _upsert_report(
    conn: sqlite3.Connection, request: AnalyticsProjectionUpsertRequest
) -> int:
    report = request.batch.report
    report_id = str(report.report_id)
    title = report.title.strip()
    publisher = report.publisher.strip()
    source_md5 = str(report.source_md5 or "").strip()
    source_url = report.source_url.strip() or _report_source_url_from_store(
        conn,
        report_title=title,
        publisher=publisher,
        source_md5=source_md5,
    )
    if not title:
        raise AppError(
            code="analytics_projection_title_missing",
            message="Projected report title is required",
            retryable=False,
            severity="error",
            context={"report_id": report_id},
        )
    conn.execute(
        """
        INSERT INTO reports(
            file_id,
            title,
            publisher,
            time_period,
            taxonomy_json,
            categories_json,
            md5,
            report_id,
            publisher_id,
            source_md5,
            source_url,
            ingest_run_id,
            analysis_run_id,
            validation_status,
            validation_severity,
            text_density,
            text_not_available,
            projection_schema_version,
            projection_version,
            projection_status,
            projection_attempt_count,
            projection_error_code,
            projection_error_message,
            projection_error_retryable,
            projection_generated_at_utc,
            projection_updated_at_utc,
            created_at,
            updated_at
        )
        VALUES(?, ?, ?, ?, '[]', '[]', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'projected', 1, NULL, NULL, NULL, ?, ?, strftime('%s','now'), strftime('%s','now'))
        ON CONFLICT(file_id) DO UPDATE SET
            title=excluded.title,
            publisher=excluded.publisher,
            time_period=excluded.time_period,
            md5=COALESCE(excluded.md5, reports.md5),
            report_id=excluded.report_id,
            publisher_id=excluded.publisher_id,
            source_md5=excluded.source_md5,
            source_url=excluded.source_url,
            ingest_run_id=excluded.ingest_run_id,
            analysis_run_id=excluded.analysis_run_id,
            validation_status=excluded.validation_status,
            validation_severity=excluded.validation_severity,
            text_density=excluded.text_density,
            text_not_available=excluded.text_not_available,
            projection_schema_version=excluded.projection_schema_version,
            projection_version=excluded.projection_version,
            projection_status='projected',
            projection_attempt_count=COALESCE(reports.projection_attempt_count, 0) + 1,
            projection_error_code=NULL,
            projection_error_message=NULL,
            projection_error_retryable=NULL,
            projection_generated_at_utc=excluded.projection_generated_at_utc,
            projection_updated_at_utc=excluded.projection_updated_at_utc,
            updated_at=strftime('%s','now')
        """,
        (
            report_id,
            title,
            publisher or None,
            report.time_period.strip() or None,
            source_md5 or None,
            report_id,
            str(report.publisher_id) if report.publisher_id else None,
            source_md5 or None,
            source_url or None,
            report.ingest_run_id,
            report.analysis_run_id,
            report.validation_status,
            report.validation_severity,
            float(report.text_density),
            1 if report.text_not_available else 0,
            report.schema_version,
            report.projection_version,
            report.projection_generated_at_utc,
            report.projection_generated_at_utc,
        ),
    )
    row = conn.execute(
        "SELECT projection_attempt_count FROM reports WHERE file_id=?", (report_id,)
    ).fetchone()
    return int(row[0] or 0) if row else 0


def _upsert_sections(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    conn.executemany(
        """
        INSERT INTO report_sections(section_uid, report_id, section_id, title, summary, key_points_json, pages_json, order_index, schema_version, projection_version, source_pack, source_ref, model, generated_at_utc, analysis_run_id)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(section_uid) DO UPDATE SET
            title=excluded.title,
            summary=excluded.summary,
            key_points_json=excluded.key_points_json,
            pages_json=excluded.pages_json,
            order_index=excluded.order_index,
            schema_version=excluded.schema_version,
            projection_version=excluded.projection_version,
            source_pack=excluded.source_pack,
            source_ref=excluded.source_ref,
            model=excluded.model,
            generated_at_utc=excluded.generated_at_utc,
            analysis_run_id=excluded.analysis_run_id
        """,
        (
            (
                str(row.section_uid),
                str(row.report_id),
                row.section_id,
                row.title,
                row.summary,
                _json(row.key_points),
                _json(row.pages),
                row.order_index,
                row.schema_version,
                *_lineage_values(row.lineage),
            )
            for row in rows
        ),
    )


def _upsert_findings(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    conn.executemany(
        """
        INSERT INTO report_findings(finding_uid, report_id, finding_id, text, evidence, confidence, pages_json, schema_version, projection_version, source_pack, source_ref, model, generated_at_utc, analysis_run_id)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(finding_uid) DO UPDATE SET
            text=excluded.text,
            evidence=excluded.evidence,
            confidence=excluded.confidence,
            pages_json=excluded.pages_json,
            schema_version=excluded.schema_version,
            projection_version=excluded.projection_version,
            source_pack=excluded.source_pack,
            source_ref=excluded.source_ref,
            model=excluded.model,
            generated_at_utc=excluded.generated_at_utc,
            analysis_run_id=excluded.analysis_run_id
        """,
        (
            (
                str(row.finding_uid),
                str(row.report_id),
                row.finding_id,
                row.text,
                row.evidence,
                row.confidence,
                _json(row.pages),
                row.schema_version,
                *_lineage_values(row.lineage),
            )
            for row in rows
        ),
    )


def _upsert_metrics(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    conn.executemany(
        """
        INSERT INTO report_metrics(metric_uid, report_id, metric_id, metric, value, unit, evidence_id, pages_json, schema_version, projection_version, source_pack, source_ref, model, generated_at_utc, analysis_run_id)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(metric_uid) DO UPDATE SET
            metric=excluded.metric,
            value=excluded.value,
            unit=excluded.unit,
            evidence_id=excluded.evidence_id,
            pages_json=excluded.pages_json,
            schema_version=excluded.schema_version,
            projection_version=excluded.projection_version,
            source_pack=excluded.source_pack,
            source_ref=excluded.source_ref,
            model=excluded.model,
            generated_at_utc=excluded.generated_at_utc,
            analysis_run_id=excluded.analysis_run_id
        """,
        (
            (
                str(row.metric_uid),
                str(row.report_id),
                row.metric_id,
                row.metric,
                row.value,
                row.unit,
                row.evidence_id,
                _json(row.pages),
                row.schema_version,
                *_lineage_values(row.lineage),
            )
            for row in rows
        ),
    )


def _upsert_quotes(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    conn.executemany(
        """
        INSERT INTO report_quotes(quote_uid, report_id, quote_id, text, speaker, citation, page, evidence_id, schema_version, projection_version, source_pack, source_ref, model, generated_at_utc, analysis_run_id)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(quote_uid) DO UPDATE SET
            text=excluded.text,
            speaker=excluded.speaker,
            citation=excluded.citation,
            page=excluded.page,
            evidence_id=excluded.evidence_id,
            schema_version=excluded.schema_version,
            projection_version=excluded.projection_version,
            source_pack=excluded.source_pack,
            source_ref=excluded.source_ref,
            model=excluded.model,
            generated_at_utc=excluded.generated_at_utc,
            analysis_run_id=excluded.analysis_run_id
        """,
        (
            (
                str(row.quote_uid),
                str(row.report_id),
                row.quote_id,
                row.text,
                row.speaker,
                row.citation,
                row.page,
                row.evidence_id,
                row.schema_version,
                *_lineage_values(row.lineage),
            )
            for row in rows
        ),
    )


def _upsert_claims(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    conn.executemany(
        """
        INSERT INTO report_claims(claim_uid, report_id, claim, evidence_id, evidence, pages_json, schema_version, projection_version, source_pack, source_ref, model, generated_at_utc, analysis_run_id)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(claim_uid) DO UPDATE SET
            claim=excluded.claim,
            evidence_id=excluded.evidence_id,
            evidence=excluded.evidence,
            pages_json=excluded.pages_json,
            schema_version=excluded.schema_version,
            projection_version=excluded.projection_version,
            source_pack=excluded.source_pack,
            source_ref=excluded.source_ref,
            model=excluded.model,
            generated_at_utc=excluded.generated_at_utc,
            analysis_run_id=excluded.analysis_run_id
        """,
        (
            (
                str(row.claim_uid),
                str(row.report_id),
                row.claim,
                row.evidence_id,
                row.evidence,
                _json(row.pages),
                row.schema_version,
                *_lineage_values(row.lineage),
            )
            for row in rows
        ),
    )


def _upsert_tags(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    conn.executemany(
        """
        INSERT INTO report_tags(tag_uid, report_id, tag, tag_type, schema_version, projection_version, source_pack, source_ref, model, generated_at_utc, analysis_run_id)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(tag_uid) DO UPDATE SET
            tag=excluded.tag,
            tag_type=excluded.tag_type,
            schema_version=excluded.schema_version,
            projection_version=excluded.projection_version,
            source_pack=excluded.source_pack,
            source_ref=excluded.source_ref,
            model=excluded.model,
            generated_at_utc=excluded.generated_at_utc,
            analysis_run_id=excluded.analysis_run_id
        """,
        (
            (
                str(row.tag_uid),
                str(row.report_id),
                row.tag,
                row.tag_type,
                row.schema_version,
                *_lineage_values(row.lineage),
            )
            for row in rows
        ),
    )


def _upsert_categories(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    conn.executemany(
        """
        INSERT INTO report_categories(category_uid, report_id, category_id, label, fit_score, decision, selected, evidence_sections_json, schema_version, projection_version, source_pack, source_ref, model, generated_at_utc, analysis_run_id)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(category_uid) DO UPDATE SET
            label=excluded.label,
            fit_score=excluded.fit_score,
            decision=excluded.decision,
            selected=excluded.selected,
            evidence_sections_json=excluded.evidence_sections_json,
            schema_version=excluded.schema_version,
            projection_version=excluded.projection_version,
            source_pack=excluded.source_pack,
            source_ref=excluded.source_ref,
            model=excluded.model,
            generated_at_utc=excluded.generated_at_utc,
            analysis_run_id=excluded.analysis_run_id
        """,
        (
            (
                str(row.category_uid),
                str(row.report_id),
                row.category_id,
                row.label,
                float(row.fit_score),
                row.decision,
                1 if row.selected else 0,
                _json(row.evidence_sections),
                row.schema_version,
                *_lineage_values(row.lineage),
            )
            for row in rows
        ),
    )


def _upsert_figures(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    conn.executemany(
        """
        INSERT INTO report_figures(figure_uid, report_id, candidate_id, image_path, kind, page, is_primary, detected_caption, generated_caption, display_caption, caption_source, schema_version, projection_version, source_pack, source_ref, model, generated_at_utc, analysis_run_id)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(figure_uid) DO UPDATE SET
            candidate_id=excluded.candidate_id,
            image_path=excluded.image_path,
            kind=excluded.kind,
            page=excluded.page,
            is_primary=excluded.is_primary,
            detected_caption=excluded.detected_caption,
            generated_caption=excluded.generated_caption,
            display_caption=excluded.display_caption,
            caption_source=excluded.caption_source,
            schema_version=excluded.schema_version,
            projection_version=excluded.projection_version,
            source_pack=excluded.source_pack,
            source_ref=excluded.source_ref,
            model=excluded.model,
            generated_at_utc=excluded.generated_at_utc,
            analysis_run_id=excluded.analysis_run_id
        """,
        (
            (
                str(row.figure_uid),
                str(row.report_id),
                row.candidate_id,
                row.image_path,
                row.kind,
                int(row.page),
                1 if row.is_primary else 0,
                row.detected_caption,
                row.generated_caption,
                row.display_caption,
                row.caption_source,
                row.schema_version,
                *_lineage_values(row.lineage),
            )
            for row in rows
        ),
    )


def _validate_queue_row(row) -> None:
    if row.embedding_status not in _EMBEDDING_STATUSES:
        raise AppError(
            code="analytics_projection_embedding_status_invalid",
            message="Embedding status must be pending, embedded, or failed",
            retryable=False,
            severity="error",
            context={
                "entity_uid": str(row.entity_uid),
                "embedding_status": row.embedding_status,
            },
        )
    if not row.content_hash.strip():
        raise AppError(
            code="analytics_projection_content_hash_missing",
            message="Vector queue content_hash is required",
            retryable=False,
            severity="error",
            context={"entity_uid": str(row.entity_uid)},
        )


def _upsert_vector_queue(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    for row in rows:
        _validate_queue_row(row)
    conn.executemany(
        """
        INSERT INTO vector_projection_queue(entity_uid, entity_type, report_id, text_payload, content_hash, metadata_json, content_class, embedding_status, embedding_version, created_at_utc, updated_at_utc, projection_schema_version)
        VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_uid) DO UPDATE SET
            entity_type=excluded.entity_type,
            report_id=excluded.report_id,
            text_payload=excluded.text_payload,
            content_hash=excluded.content_hash,
            metadata_json=excluded.metadata_json,
            content_class=excluded.content_class,
            embedding_status=CASE
                WHEN vector_projection_queue.content_hash = excluded.content_hash
                THEN vector_projection_queue.embedding_status
                ELSE 'pending'
            END,
            embedding_version=CASE
                WHEN vector_projection_queue.content_hash = excluded.content_hash
                THEN vector_projection_queue.embedding_version
                ELSE ''
            END,
            queue_reason_code=CASE
                WHEN vector_projection_queue.content_hash = excluded.content_hash
                THEN vector_projection_queue.queue_reason_code
                ELSE ''
            END,
            queue_error_retryable=CASE
                WHEN vector_projection_queue.content_hash = excluded.content_hash
                THEN vector_projection_queue.queue_error_retryable
                ELSE 0
            END,
            queue_attempt_count=CASE
                WHEN vector_projection_queue.content_hash = excluded.content_hash
                THEN vector_projection_queue.queue_attempt_count
                ELSE 0
            END,
            next_eligible_at_utc=CASE
                WHEN vector_projection_queue.content_hash = excluded.content_hash
                THEN vector_projection_queue.next_eligible_at_utc
                ELSE ''
            END,
            queue_actor=CASE
                WHEN vector_projection_queue.content_hash = excluded.content_hash
                THEN vector_projection_queue.queue_actor
                ELSE ''
            END,
            execution_lease_id=CASE
                WHEN vector_projection_queue.content_hash = excluded.content_hash
                THEN vector_projection_queue.execution_lease_id
                ELSE ''
            END,
            execution_lease_expires_at_utc=CASE
                WHEN vector_projection_queue.content_hash = excluded.content_hash
                THEN vector_projection_queue.execution_lease_expires_at_utc
                ELSE ''
            END,
            projection_schema_version=excluded.projection_schema_version,
            updated_at_utc=excluded.updated_at_utc
        """,
        (
            (
                str(row.entity_uid),
                row.entity_type,
                str(row.report_id),
                row.text_payload,
                row.content_hash,
                _json(row.metadata),
                row.content_class,
                row.embedding_status,
                row.embedding_version,
                row.created_at_utc,
                row.updated_at_utc,
                row.schema_version,
            )
            for row in rows
        ),
    )


def upsert_projection(
    request: AnalyticsProjectionUpsertRequest,
    ctx: RunContext,
) -> AnalyticsProjectionUpsertResponse:
    report_id = str(request.batch.report.report_id)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analytics_projection_upsert_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "report_id": report_id,
                "projection_version": request.batch.projection_version,
                "section_count": len(request.batch.sections),
                "vector_queue_count": len(request.batch.vector_queue),
            },
        )
    )
    try:
        with _analytics_conn(request.db_path, ctx) as conn:
            attempt_count = _upsert_report(conn, request)
            _upsert_sections(conn, request.batch.sections)
            _upsert_findings(conn, request.batch.findings)
            _upsert_metrics(conn, request.batch.metrics)
            _upsert_quotes(conn, request.batch.quotes)
            _upsert_claims(conn, request.batch.claims)
            _upsert_tags(conn, request.batch.tags)
            _upsert_categories(conn, request.batch.categories)
            _upsert_figures(conn, request.batch.figures)
            _upsert_vector_queue(conn, request.batch.vector_queue)
            _delete_stale(
                conn,
                table="report_sections",
                key_column="section_uid",
                report_id=report_id,
                active_uids=_uid_set(request.batch.sections, "section_uid"),
            )
            _delete_stale(
                conn,
                table="report_findings",
                key_column="finding_uid",
                report_id=report_id,
                active_uids=_uid_set(request.batch.findings, "finding_uid"),
            )
            _delete_stale(
                conn,
                table="report_metrics",
                key_column="metric_uid",
                report_id=report_id,
                active_uids=_uid_set(request.batch.metrics, "metric_uid"),
            )
            _delete_stale(
                conn,
                table="report_quotes",
                key_column="quote_uid",
                report_id=report_id,
                active_uids=_uid_set(request.batch.quotes, "quote_uid"),
            )
            _delete_stale(
                conn,
                table="report_claims",
                key_column="claim_uid",
                report_id=report_id,
                active_uids=_uid_set(request.batch.claims, "claim_uid"),
            )
            _delete_stale(
                conn,
                table="report_tags",
                key_column="tag_uid",
                report_id=report_id,
                active_uids=_uid_set(request.batch.tags, "tag_uid"),
            )
            _delete_stale(
                conn,
                table="report_categories",
                key_column="category_uid",
                report_id=report_id,
                active_uids=_uid_set(request.batch.categories, "category_uid"),
            )
            _delete_stale(
                conn,
                table="report_figures",
                key_column="figure_uid",
                report_id=report_id,
                active_uids=_uid_set(request.batch.figures, "figure_uid"),
            )
            _delete_stale(
                conn,
                table="vector_projection_queue",
                key_column="entity_uid",
                report_id=report_id,
                active_uids=_uid_set(request.batch.vector_queue, "entity_uid"),
            )
    except AppError:
        raise
    except sqlite3.Error as exc:
        raise AppError(
            code="analytics_projection_upsert_failed",
            message="Failed to upsert analytics projection rows",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": request.db_path, "report_id": report_id},
        ) from exc

    rows_upserted = (
        1
        + len(request.batch.sections)
        + len(request.batch.findings)
        + len(request.batch.metrics)
        + len(request.batch.quotes)
        + len(request.batch.claims)
        + len(request.batch.tags)
        + len(request.batch.categories)
        + len(request.batch.figures)
    )
    response = AnalyticsProjectionUpsertResponse(
        schema_version=PROJECTION_SCHEMA_VERSION,
        report_id=ReportId(report_id),
        projection_status="projected",
        projection_attempt_count=attempt_count,
        rows_upserted=rows_upserted,
        vector_queue_count=len(request.batch.vector_queue),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analytics_projection_upsert_complete",
            module=logger.name,
            fields={**asdict(response), "report_id": str(response.report_id)},
        )
    )
    return response


def record_projection_failure(
    request: AnalyticsProjectionFailureRequest,
    ctx: RunContext,
) -> AnalyticsProjectionFailureResponse:
    report_id = str(request.report_id)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analytics_projection_failure_record_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "report_id": report_id,
                "error_code": request.error_code,
                "error_retryable": request.error_retryable,
            },
        )
    )
    try:
        with _analytics_conn(request.db_path, ctx) as conn:
            conn.execute(
                """
                INSERT INTO reports(
                    file_id,
                    title,
                    taxonomy_json,
                    categories_json,
                    report_id,
                    projection_schema_version,
                    projection_version,
                    projection_status,
                    projection_attempt_count,
                    projection_error_code,
                    projection_error_message,
                    projection_error_retryable,
                    projection_generated_at_utc,
                    projection_updated_at_utc,
                    created_at,
                    updated_at
                )
                VALUES(?, ?, '[]', '[]', ?, ?, ?, 'failed', 1, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
                ON CONFLICT(file_id) DO UPDATE SET
                    report_id=excluded.report_id,
                    projection_schema_version=excluded.projection_schema_version,
                    projection_version=excluded.projection_version,
                    projection_status='failed',
                    projection_attempt_count=COALESCE(reports.projection_attempt_count, 0) + 1,
                    projection_error_code=excluded.projection_error_code,
                    projection_error_message=excluded.projection_error_message,
                    projection_error_retryable=excluded.projection_error_retryable,
                    projection_generated_at_utc=excluded.projection_generated_at_utc,
                    projection_updated_at_utc=excluded.projection_updated_at_utc,
                    updated_at=strftime('%s','now')
                """,
                (
                    report_id,
                    report_id,
                    report_id,
                    request.projection_schema_version,
                    request.projection_version,
                    request.error_code,
                    request.error_message,
                    1 if request.error_retryable else 0,
                    request.generated_at_utc,
                    request.generated_at_utc,
                ),
            )
            row = conn.execute(
                "SELECT projection_attempt_count FROM reports WHERE file_id=?",
                (report_id,),
            ).fetchone()
            attempt_count = int(row[0] or 0) if row else 0
    except sqlite3.Error as exc:
        raise AppError(
            code="analytics_projection_failure_record_failed",
            message="Failed to record analytics projection failure",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": request.db_path, "report_id": report_id},
        ) from exc

    response = AnalyticsProjectionFailureResponse(
        schema_version=PROJECTION_SCHEMA_VERSION,
        report_id=ReportId(report_id),
        projection_status="failed",
        projection_attempt_count=attempt_count,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="analytics_projection_failure_record_complete",
            module=logger.name,
            fields={**asdict(response), "report_id": str(response.report_id)},
        )
    )
    return response
