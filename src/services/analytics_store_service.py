from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any, Iterable, Sequence

from src.contracts.analytics_projection import (
    AnalyticsProjectionFailureRequest,
    AnalyticsProjectionFailureResponse,
    AnalyticsProjectionUpsertRequest,
    AnalyticsProjectionUpsertResponse,
    PROJECTION_SCHEMA_VERSION,
)
from src.contracts.cross_report_analysis import (
    CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
    CrossReportEvidenceReference,
    CrossReportProjectedDataReadRequest,
    CrossReportProjectedDataReadResponse,
    CrossReportRawMetricReference,
    CrossReportSourceReportCandidate,
    validate_cross_report_contract,
)
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId
from src.contracts.sqlite_migration import SqliteMigrationApplyRequest
from src.services.sqlite_migration_service import apply_reports_db_migrations
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.analytics_store_service")

DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0
_CONN_LOCK = threading.Lock()
_EMBEDDING_STATUSES = {"pending", "embedded", "failed"}
_CROSS_REPORT_READ_CONTENT_CLASSES = {"claim", "finding", "quote", "metric"}

DDL = """
CREATE TABLE IF NOT EXISTS reports (
  file_id TEXT PRIMARY KEY,
  file_name TEXT,
  title TEXT NOT NULL,
  publisher TEXT,
  taxonomy_json TEXT NOT NULL DEFAULT '[]',
  categories_json TEXT NOT NULL DEFAULT '[]',
  region TEXT,
  time_period TEXT,
  source_url TEXT,
  html_path TEXT,
  md5 TEXT,
  page_count INTEGER,
  contents_page INTEGER,
  pdf_metadata_json TEXT,
  analysis_mode TEXT,
  vector_store_id TEXT,
  evidence_packs_json TEXT,
  report_id TEXT,
  publisher_id TEXT,
  source_md5 TEXT,
  ingest_run_id TEXT,
  analysis_run_id TEXT,
  validation_status TEXT,
  validation_severity TEXT,
  text_density REAL,
  text_not_available INTEGER,
  projection_schema_version TEXT,
  projection_version TEXT,
  projection_status TEXT NOT NULL DEFAULT 'not_projected' CHECK(projection_status IN ('not_projected','projected','failed')),
  projection_attempt_count INTEGER NOT NULL DEFAULT 0,
  projection_error_code TEXT,
  projection_error_message TEXT,
  projection_error_retryable INTEGER,
  projection_generated_at_utc TEXT,
  projection_updated_at_utc TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS report_sections (
  section_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  section_id TEXT NOT NULL,
  title TEXT NOT NULL,
  summary TEXT NOT NULL,
  key_points_json TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  order_index INTEGER NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_findings (
  finding_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  finding_id TEXT NOT NULL,
  text TEXT NOT NULL,
  evidence TEXT NOT NULL,
  confidence TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_metrics (
  metric_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  metric_id TEXT NOT NULL,
  metric TEXT NOT NULL,
  value TEXT NOT NULL,
  unit TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_quotes (
  quote_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  quote_id TEXT NOT NULL,
  text TEXT NOT NULL,
  speaker TEXT NOT NULL,
  citation TEXT NOT NULL,
  page INTEGER,
  evidence_id TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_claims (
  claim_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  claim TEXT NOT NULL,
  evidence_id TEXT NOT NULL,
  evidence TEXT NOT NULL,
  pages_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_tags (
  tag_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  tag TEXT NOT NULL,
  tag_type TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_categories (
  category_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  category_id TEXT NOT NULL,
  label TEXT NOT NULL,
  fit_score REAL NOT NULL,
  decision TEXT NOT NULL,
  selected INTEGER NOT NULL,
  evidence_sections_json TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS report_figures (
  figure_uid TEXT PRIMARY KEY,
  report_id TEXT NOT NULL,
  candidate_id TEXT NOT NULL,
  image_path TEXT NOT NULL,
  kind TEXT NOT NULL,
  page INTEGER NOT NULL,
  is_primary INTEGER NOT NULL,
  detected_caption TEXT NOT NULL,
  generated_caption TEXT NOT NULL,
  display_caption TEXT NOT NULL,
  caption_source TEXT NOT NULL,
  schema_version TEXT NOT NULL,
  projection_version TEXT NOT NULL,
  source_pack TEXT NOT NULL,
  source_ref TEXT NOT NULL,
  model TEXT,
  generated_at_utc TEXT NOT NULL,
  analysis_run_id TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS vector_projection_queue (
  entity_uid TEXT PRIMARY KEY,
  entity_type TEXT NOT NULL,
  report_id TEXT NOT NULL,
  text_payload TEXT NOT NULL,
  content_hash TEXT NOT NULL,
  metadata_json TEXT NOT NULL,
  content_class TEXT NOT NULL,
  embedding_status TEXT NOT NULL CHECK(embedding_status IN ('pending','embedded','failed')),
  embedding_version TEXT NOT NULL,
  created_at_utc TEXT NOT NULL,
  updated_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_report_sections_report_id ON report_sections(report_id);
CREATE INDEX IF NOT EXISTS idx_report_findings_report_id ON report_findings(report_id);
CREATE INDEX IF NOT EXISTS idx_report_metrics_report_id ON report_metrics(report_id);
CREATE INDEX IF NOT EXISTS idx_report_quotes_report_id ON report_quotes(report_id);
CREATE INDEX IF NOT EXISTS idx_report_claims_report_id ON report_claims(report_id);
CREATE INDEX IF NOT EXISTS idx_report_tags_report_id ON report_tags(report_id);
CREATE INDEX IF NOT EXISTS idx_report_categories_report_id ON report_categories(report_id);
CREATE INDEX IF NOT EXISTS idx_report_figures_report_id ON report_figures(report_id);
CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_report_id ON vector_projection_queue(report_id);
CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_status ON vector_projection_queue(embedding_status);
CREATE INDEX IF NOT EXISTS idx_vector_projection_queue_content_hash ON vector_projection_queue(content_hash);
CREATE INDEX IF NOT EXISTS idx_reports_projection_status ON reports(projection_status);
"""

_REPORT_PROJECTION_COLUMNS: tuple[tuple[str, str], ...] = (
    ("report_id", "TEXT"),
    ("publisher_id", "TEXT"),
    ("source_md5", "TEXT"),
    ("ingest_run_id", "TEXT"),
    ("analysis_run_id", "TEXT"),
    ("validation_status", "TEXT"),
    ("validation_severity", "TEXT"),
    ("text_density", "REAL"),
    ("text_not_available", "INTEGER"),
    ("projection_schema_version", "TEXT"),
    ("projection_version", "TEXT"),
    (
        "projection_status",
        "TEXT NOT NULL DEFAULT 'not_projected' CHECK(projection_status IN ('not_projected','projected','failed'))",
    ),
    ("projection_attempt_count", "INTEGER NOT NULL DEFAULT 0"),
    ("projection_error_code", "TEXT"),
    ("projection_error_message", "TEXT"),
    ("projection_error_retryable", "INTEGER"),
    ("projection_generated_at_utc", "TEXT"),
    ("projection_updated_at_utc", "TEXT"),
)


@contextmanager
def _analytics_conn(path: str, ctx: RunContext):
    db_path = str(path or "").strip()
    if not db_path:
        raise AppError(
            code="analytics_store_db_missing",
            message="Analytics projection DB path is required",
            retryable=False,
            severity="error",
        )
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    try:
        conn = sqlite3.connect(db_path, timeout=DEFAULT_BUSY_TIMEOUT_SECONDS)
    except sqlite3.Error as exc:
        raise AppError(
            code="analytics_store_db_unavailable",
            message="Failed to open analytics projection DB",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": db_path},
        ) from exc
    try:
        _configure(conn)
        with _CONN_LOCK:
            apply_reports_db_migrations(
                SqliteMigrationApplyRequest(
                    schema_version="1.0",
                    database_key="reports_db",
                    db_path=db_path,
                    target_version=11,
                    ctx=ctx,
                ),
                conn,
            )
            conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _configure(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA busy_timeout={int(DEFAULT_BUSY_TIMEOUT_SECONDS * 1000)}")
    conn.execute("PRAGMA synchronous=NORMAL")


def _ensure_reports_projection_columns(conn: sqlite3.Connection) -> None:
    cols = {
        str(row[1]) for row in conn.execute("PRAGMA table_info(reports)").fetchall()
    }
    for column_name, column_type in _REPORT_PROJECTION_COLUMNS:
        if column_name not in cols:
            conn.execute(f"ALTER TABLE reports ADD COLUMN {column_name} {column_type}")


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _lineage_values(lineage) -> tuple[str, str, str, str, str, str]:
    return (
        lineage.projection_version,
        lineage.source_pack,
        lineage.source_ref,
        lineage.model,
        lineage.generated_at_utc,
        lineage.analysis_run_id,
    )


def _uid_set(rows: Iterable[Any], attr_name: str) -> set[str]:
    return {str(getattr(row, attr_name)) for row in rows}


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
            taxonomy_json,
            categories_json,
            md5,
            report_id,
            publisher_id,
            source_md5,
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
        VALUES(?, ?, ?, '[]', '[]', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'projected', 1, NULL, NULL, NULL, ?, ?, strftime('%s','now'), strftime('%s','now'))
        ON CONFLICT(file_id) DO UPDATE SET
            title=excluded.title,
            publisher=excluded.publisher,
            md5=COALESCE(excluded.md5, reports.md5),
            report_id=excluded.report_id,
            publisher_id=excluded.publisher_id,
            source_md5=excluded.source_md5,
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
            report.publisher.strip() or None,
            report.source_md5,
            report_id,
            str(report.publisher_id) if report.publisher_id else None,
            report.source_md5,
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
    for row in rows:
        conn.execute(
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
            ),
        )


def _upsert_findings(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    for row in rows:
        conn.execute(
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
                str(row.finding_uid),
                str(row.report_id),
                row.finding_id,
                row.text,
                row.evidence,
                row.confidence,
                _json(row.pages),
                row.schema_version,
                *_lineage_values(row.lineage),
            ),
        )


def _upsert_metrics(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    for row in rows:
        conn.execute(
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
            ),
        )


def _upsert_quotes(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    for row in rows:
        conn.execute(
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
            ),
        )


def _upsert_claims(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    for row in rows:
        conn.execute(
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
                str(row.claim_uid),
                str(row.report_id),
                row.claim,
                row.evidence_id,
                row.evidence,
                _json(row.pages),
                row.schema_version,
                *_lineage_values(row.lineage),
            ),
        )


def _upsert_tags(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    for row in rows:
        conn.execute(
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
                str(row.tag_uid),
                str(row.report_id),
                row.tag,
                row.tag_type,
                row.schema_version,
                *_lineage_values(row.lineage),
            ),
        )


def _upsert_categories(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    for row in rows:
        conn.execute(
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
            ),
        )


def _upsert_figures(conn: sqlite3.Connection, rows: Sequence[Any]) -> None:
    for row in rows:
        conn.execute(
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
        conn.execute(
            """
            INSERT INTO vector_projection_queue(entity_uid, entity_type, report_id, text_payload, content_hash, metadata_json, content_class, embedding_status, embedding_version, created_at_utc, updated_at_utc)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                updated_at_utc=excluded.updated_at_utc
            """,
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
            ),
        )


def _normalized_filter_values(values: Sequence[str]) -> set[str]:
    return {str(value).strip().casefold() for value in values if str(value).strip()}


def _status_floor_values(status: str) -> set[str]:
    if status == "projected":
        return {"projected"}
    if status == "failed":
        return {"failed", "projected"}
    if status == "not_projected":
        return {"not_projected", "failed", "projected"}
    raise AppError(
        code="cross_report_projection_status_invalid",
        message="Cross-report projected data read received an invalid status floor",
        retryable=False,
        severity="error",
        context={"minimum_projection_status": status},
    )


def _json_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    try:
        decoded = json.loads(str(value))
    except (TypeError, ValueError):
        return []
    return decoded if isinstance(decoded, list) else []


def _fetch_grouped_rows(
    conn: sqlite3.Connection,
    *,
    table: str,
    report_ids: Sequence[str],
) -> dict[str, list[sqlite3.Row]]:
    if not report_ids:
        return {}
    placeholders = ",".join("?" for _ in report_ids)
    rows = conn.execute(
        f"SELECT * FROM {table} WHERE report_id IN ({placeholders}) ORDER BY report_id",
        tuple(report_ids),
    ).fetchall()
    grouped: dict[str, list[sqlite3.Row]] = {}
    for row in rows:
        grouped.setdefault(str(row["report_id"]), []).append(row)
    return grouped


def _fetch_vector_hashes(
    conn: sqlite3.Connection, report_ids: Sequence[str]
) -> dict[str, dict[str, str]]:
    if not report_ids:
        return {}
    placeholders = ",".join("?" for _ in report_ids)
    rows = conn.execute(
        """
        SELECT report_id, entity_uid, content_hash
        FROM vector_projection_queue
        WHERE report_id IN ({placeholders})
        ORDER BY report_id, entity_uid
        """.format(placeholders=placeholders),
        tuple(report_ids),
    ).fetchall()
    hashes: dict[str, dict[str, str]] = {}
    for row in rows:
        content_hash = str(row["content_hash"] or "").strip()
        entity_uid = str(row["entity_uid"] or "").strip()
        report_id = str(row["report_id"] or "").strip()
        if content_hash and entity_uid and report_id:
            hashes.setdefault(report_id, {})[entity_uid] = content_hash
    return hashes


def _aggregate_content_hash(report_row: sqlite3.Row, hashes: dict[str, str]) -> str:
    if hashes:
        payload = "|".join(f"{key}={hashes[key]}" for key in sorted(hashes))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
    fallback = "|".join(
        str(report_row[key] or "")
        for key in (
            "report_id",
            "source_md5",
            "md5",
            "projection_generated_at_utc",
        )
    )
    return hashlib.sha256(fallback.encode("utf-8")).hexdigest()


def _report_date(report_row: sqlite3.Row) -> str:
    generated_at = str(report_row["projection_generated_at_utc"] or "").strip()
    if generated_at:
        return generated_at[:10]
    return str(report_row["time_period"] or "").strip()


def _row_text(row: sqlite3.Row, column: str) -> str:
    return str(row[column] or "").strip()


def _report_passes_filters(
    report_row: sqlite3.Row,
    *,
    request: CrossReportProjectedDataReadRequest,
    tags: list[sqlite3.Row],
    categories: list[sqlite3.Row],
) -> bool:
    publisher_filters = _normalized_filter_values(request.publisher_filters)
    if publisher_filters:
        publisher_values = {
            _row_text(report_row, "publisher").casefold(),
            _row_text(report_row, "publisher_id").casefold(),
        }
        if not publisher_filters.intersection(publisher_values):
            return False

    report_date = _report_date(report_row)
    if request.date_range_start and (
        not report_date or report_date < request.date_range_start
    ):
        return False
    if request.date_range_end and (
        not report_date or report_date > request.date_range_end
    ):
        return False

    tag_filters = _normalized_filter_values(request.tag_filters)
    if tag_filters:
        report_tags = {_row_text(row, "tag").casefold() for row in tags}
        if not tag_filters.intersection(report_tags):
            return False

    category_filters = _normalized_filter_values(request.category_filters)
    if category_filters:
        category_values = set()
        for row in categories:
            category_values.add(_row_text(row, "category_id").casefold())
            category_values.add(_row_text(row, "label").casefold())
        if not category_filters.intersection(category_values):
            return False

    return True


def _source_candidate(
    report_row: sqlite3.Row,
    *,
    tags: list[sqlite3.Row],
    categories: list[sqlite3.Row],
    claims: list[sqlite3.Row],
    findings: list[sqlite3.Row],
    quotes: list[sqlite3.Row],
    metrics: list[sqlite3.Row],
    content_hashes: dict[str, str],
) -> CrossReportSourceReportCandidate:
    claim_count = len(claims)
    finding_count = len(findings)
    quote_count = len(quotes)
    metric_count = len(metrics)
    evidence_count = claim_count + finding_count + quote_count
    report_id = _row_text(report_row, "report_id")
    publisher = _row_text(report_row, "publisher") or _row_text(
        report_row, "publisher_id"
    )
    if not publisher and _row_text(report_row, "projection_status") != "projected":
        publisher = report_id
    publisher_id = _row_text(report_row, "publisher_id") or publisher
    return CrossReportSourceReportCandidate(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        report_id=report_id,
        title=_row_text(report_row, "title"),
        publisher=publisher,
        publisher_id=publisher_id,
        report_date=_report_date(report_row),
        projection_status=_row_text(report_row, "projection_status"),
        content_hash=_aggregate_content_hash(report_row, content_hashes),
        category_labels=sorted(
            {_row_text(row, "label") for row in categories if _row_text(row, "label")}
        ),
        tags=sorted({_row_text(row, "tag") for row in tags if _row_text(row, "tag")}),
        evidence_count=evidence_count,
        claim_count=claim_count,
        finding_count=finding_count,
        quote_count=quote_count,
        metric_count=metric_count,
        recency_score=0.0,
        relevance_score=0.0,
        diversity_score=0.0,
        density_score=float(evidence_count),
        total_score=0.0,
        selection_reasons=["projection_status:projected"],
        rejection_reasons=[],
    )


def _claim_evidence(
    row: sqlite3.Row, *, report_row: sqlite3.Row
) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=_row_text(row, "evidence_id"),
        report_id=_row_text(row, "report_id"),
        publisher=_row_text(report_row, "publisher"),
        title=_row_text(report_row, "title"),
        source_table="report_claims",
        entity_uid=_row_text(row, "claim_uid"),
        content_class="claim",
        text=_row_text(row, "claim"),
        source_metadata={
            "evidence": _row_text(row, "evidence"),
            "pages": _json_list(row["pages_json"]),
        },
    )


def _finding_evidence(
    row: sqlite3.Row, *, report_row: sqlite3.Row
) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=_row_text(row, "finding_uid"),
        report_id=_row_text(row, "report_id"),
        publisher=_row_text(report_row, "publisher"),
        title=_row_text(report_row, "title"),
        source_table="report_findings",
        entity_uid=_row_text(row, "finding_uid"),
        content_class="finding",
        text=_row_text(row, "text"),
        source_metadata={
            "evidence": _row_text(row, "evidence"),
            "confidence": _row_text(row, "confidence"),
            "pages": _json_list(row["pages_json"]),
        },
    )


def _quote_evidence(
    row: sqlite3.Row, *, report_row: sqlite3.Row
) -> CrossReportEvidenceReference:
    return CrossReportEvidenceReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        evidence_id=_row_text(row, "evidence_id"),
        report_id=_row_text(row, "report_id"),
        publisher=_row_text(report_row, "publisher"),
        title=_row_text(report_row, "title"),
        source_table="report_quotes",
        entity_uid=_row_text(row, "quote_uid"),
        content_class="quote",
        text=_row_text(row, "text"),
        source_metadata={
            "speaker": _row_text(row, "speaker"),
            "citation": _row_text(row, "citation"),
            "page": row["page"],
            "quote_id": _row_text(row, "quote_id"),
        },
    )


def _raw_metric(
    row: sqlite3.Row, *, report_row: sqlite3.Row
) -> CrossReportRawMetricReference:
    return CrossReportRawMetricReference(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        metric_id=_row_text(row, "metric_id"),
        report_id=_row_text(row, "report_id"),
        publisher=_row_text(report_row, "publisher"),
        label=_row_text(row, "metric"),
        raw_value=_row_text(row, "value"),
        unit=_row_text(row, "unit"),
        context=f"pages={_json_list(row['pages_json'])}",
        evidence_id=_row_text(row, "evidence_id"),
        source_metadata={
            "source_table": "report_metrics",
            "entity_uid": _row_text(row, "metric_uid"),
            "pages": _json_list(row["pages_json"]),
        },
    )


def _requested_content_classes(
    request: CrossReportProjectedDataReadRequest,
) -> set[str]:
    requested = (
        set(request.content_classes)
        if request.content_classes
        else set(_CROSS_REPORT_READ_CONTENT_CLASSES)
    )
    invalid = requested - _CROSS_REPORT_READ_CONTENT_CLASSES
    if invalid:
        raise AppError(
            code="cross_report_content_class_invalid",
            message="Cross-report projected data read received invalid content classes",
            retryable=False,
            severity="error",
            context={"content_classes": sorted(invalid)},
        )
    return requested


def read_cross_report_projected_data(
    request: CrossReportProjectedDataReadRequest,
    ctx: RunContext,
) -> CrossReportProjectedDataReadResponse:
    validate_cross_report_contract(request)
    requested_content_classes = _requested_content_classes(request)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="cross_report_projected_data_read_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "publisher_filters": request.publisher_filters,
                "category_filters": request.category_filters,
                "tag_filters": request.tag_filters,
                "date_range_start": request.date_range_start,
                "date_range_end": request.date_range_end,
                "content_classes": sorted(requested_content_classes),
                "minimum_projection_status": request.minimum_projection_status,
            },
        )
    )
    try:
        with _analytics_conn(request.db_path, ctx) as conn:
            conn.row_factory = sqlite3.Row
            status_floor = _status_floor_values(request.minimum_projection_status)
            all_rows = conn.execute(
                """
                SELECT file_id, report_id, title, publisher, publisher_id, source_md5,
                       md5, time_period, projection_status,
                       projection_generated_at_utc
                FROM reports
                ORDER BY report_id
                """
            ).fetchall()
            status_rows = [
                row
                for row in all_rows
                if _row_text(row, "projection_status") in status_floor
            ]
            status_report_ids = [_row_text(row, "report_id") for row in status_rows]
            tags_by_report = _fetch_grouped_rows(
                conn, table="report_tags", report_ids=status_report_ids
            )
            categories_by_report = _fetch_grouped_rows(
                conn, table="report_categories", report_ids=status_report_ids
            )
            claims_by_report = _fetch_grouped_rows(
                conn, table="report_claims", report_ids=status_report_ids
            )
            findings_by_report = _fetch_grouped_rows(
                conn, table="report_findings", report_ids=status_report_ids
            )
            quotes_by_report = _fetch_grouped_rows(
                conn, table="report_quotes", report_ids=status_report_ids
            )
            metrics_by_report = _fetch_grouped_rows(
                conn, table="report_metrics", report_ids=status_report_ids
            )
            content_hashes = _fetch_vector_hashes(conn, status_report_ids)

            filtered_rows = [
                row
                for row in status_rows
                if _report_passes_filters(
                    row,
                    request=request,
                    tags=tags_by_report.get(_row_text(row, "report_id"), []),
                    categories=categories_by_report.get(
                        _row_text(row, "report_id"), []
                    ),
                )
            ]
            report_rows = {_row_text(row, "report_id"): row for row in filtered_rows}
            source_candidates = []
            evidence = []
            raw_metrics = []
            for report_id in sorted(report_rows):
                report_row = report_rows[report_id]
                source_candidates.append(
                    _source_candidate(
                        report_row,
                        tags=tags_by_report.get(report_id, []),
                        categories=categories_by_report.get(report_id, []),
                        claims=claims_by_report.get(report_id, []),
                        findings=findings_by_report.get(report_id, []),
                        quotes=quotes_by_report.get(report_id, []),
                        metrics=metrics_by_report.get(report_id, []),
                        content_hashes=content_hashes.get(report_id, {}),
                    )
                )
                if "claim" in requested_content_classes:
                    evidence.extend(
                        _claim_evidence(row, report_row=report_row)
                        for row in claims_by_report.get(report_id, [])
                    )
                if "finding" in requested_content_classes:
                    evidence.extend(
                        _finding_evidence(row, report_row=report_row)
                        for row in findings_by_report.get(report_id, [])
                    )
                if "quote" in requested_content_classes:
                    evidence.extend(
                        _quote_evidence(row, report_row=report_row)
                        for row in quotes_by_report.get(report_id, [])
                    )
                if "metric" in requested_content_classes:
                    raw_metrics.extend(
                        _raw_metric(row, report_row=report_row)
                        for row in metrics_by_report.get(report_id, [])
                    )
    except AppError:
        raise
    except sqlite3.Error as exc:
        raise AppError(
            code="cross_report_projected_data_read_failed",
            message="Failed to read cross-report projected data",
            cause=exc,
            retryable=True,
            severity="error",
            context={"db_path": request.db_path},
        ) from exc

    response = CrossReportProjectedDataReadResponse(
        schema_version=CROSS_REPORT_ANALYSIS_SCHEMA_VERSION,
        source_candidates=source_candidates,
        evidence=evidence,
        raw_metrics=raw_metrics,
        content_hashes={
            report_id: content_hashes.get(report_id, {})
            for report_id in sorted(report_rows)
        },
        excluded_report_counts={
            "filtered": max(len(status_rows) - len(source_candidates), 0),
        },
    )
    validate_cross_report_contract(response)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="cross_report_projected_data_read_complete",
            module=logger.name,
            fields={
                "source_candidate_count": len(response.source_candidates),
                "evidence_count": len(response.evidence),
                "raw_metric_count": len(response.raw_metrics),
                "excluded_report_counts": response.excluded_report_counts,
                "selected_report_ids": [
                    candidate.report_id for candidate in response.source_candidates
                ],
            },
        )
    )
    return response


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
