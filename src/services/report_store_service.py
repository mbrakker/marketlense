from __future__ import annotations

import json
import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

from src.contracts.report_store import (
    ReportMetadataDbAccessRequest,
    ReportMetadataDbAccessResponse,
    ReportMetadataGetRequest,
    ReportMetadataGetResponse,
    ReportMetadataListRequest,
    ReportMetadataListResponse,
    ReportMetadataUpsertRequest,
)
from src.contracts.run_context import RunContext
from src.utils.coercion import clean_string_list
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.time_period import normalize_time_period

logger = logging.getLogger("market_lense.report_store_service")

ACCESS_TIMEOUT_SECONDS = 0.0
LOCK_ERROR_MARKERS = ("database is locked", "database is busy")
_REPORT_CONN_LOCK = threading.Lock()

DDL = """
CREATE TABLE IF NOT EXISTS reports (
  file_id TEXT PRIMARY KEY,
  file_name TEXT,
  title TEXT NOT NULL,
  publisher TEXT,
  taxonomy_json TEXT NOT NULL,
  categories_json TEXT NOT NULL,
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
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_title ON reports(title);
CREATE INDEX IF NOT EXISTS idx_reports_publisher ON reports(publisher);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(reports)")
    cols = {row[1] for row in cur.fetchall()}
    if "file_name" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN file_name TEXT")
    if "region" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN region TEXT")
    if "time_period" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN time_period TEXT")
    if "categories_json" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN categories_json TEXT DEFAULT '[]'")
    if "page_count" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN page_count INTEGER")
    if "contents_page" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN contents_page INTEGER")
    if "pdf_metadata_json" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN pdf_metadata_json TEXT")
    if "analysis_mode" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN analysis_mode TEXT")
    if "vector_store_id" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN vector_store_id TEXT")
    if "evidence_packs_json" not in cols:
        conn.execute("ALTER TABLE reports ADD COLUMN evidence_packs_json TEXT")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_file_name ON reports(file_name)")
    conn.commit()


@contextmanager
def _metadata_conn(path: str):
    if not path:
        raise AppError(
            code="metadata_db_missing",
            message="Report metadata DB path is required",
            retryable=False,
            severity="error",
        )
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with _REPORT_CONN_LOCK:
        conn = sqlite3.connect(path)
        try:
            conn.executescript(DDL)
            _ensure_schema(conn)
            conn.commit()
            yield conn
            conn.commit()
        finally:
            conn.close()


def _clean_metadata(metadata: dict[str, str]) -> dict[str, str]:
    if not metadata:
        return {}
    cleaned: dict[str, str] = {}
    for key, value in metadata.items():
        key_str = str(key).strip()
        if not key_str:
            continue
        val_str = str(value).strip() if value is not None else ""
        if not val_str:
            continue
        cleaned[key_str] = val_str
    return cleaned


def _is_lock_error(exc: Exception) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in LOCK_ERROR_MARKERS)


def _row_to_metadata_response(row: tuple, ctx: RunContext) -> ReportMetadataGetResponse:
    file_id = row[0]
    taxonomy_json = row[4] or "[]"
    categories_json = row[5] or "[]"
    page_count_raw = row[11]
    contents_page_raw = row[12]
    metadata_json = row[13] or "{}"
    analysis_mode = row[14] or "vector_store"
    vector_store_id = row[15]
    evidence_packs_json = row[16] or "{}"
    taxonomy: List[str] = []
    categories: List[str] = []
    pdf_metadata: dict[str, str] = {}
    page_count: Optional[int] = None
    contents_page_number = 0
    evidence_pack_paths: dict[str, str] = {}
    raw_time_period = row[7] if isinstance(row[7], str) else None
    time_period = normalize_time_period(raw_time_period)

    try:
        parsed = json.loads(taxonomy_json)
        if isinstance(parsed, list):
            taxonomy = clean_string_list([str(item) for item in parsed])
    except json.JSONDecodeError:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_taxonomy_parse_failed",
            module=logger.name,
            fields={"file_id": file_id},
        ))
    try:
        parsed_cats = json.loads(categories_json)
        if isinstance(parsed_cats, list):
            categories = clean_string_list([str(item) for item in parsed_cats])
    except json.JSONDecodeError:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_categories_parse_failed",
            module=logger.name,
            fields={"file_id": file_id},
        ))
    try:
        parsed_meta = json.loads(metadata_json)
        if isinstance(parsed_meta, dict):
            pdf_metadata = _clean_metadata({str(k): v for k, v in parsed_meta.items()})
    except json.JSONDecodeError:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_pdf_metadata_parse_failed",
            module=logger.name,
            fields={"file_id": file_id},
        ))
    try:
        if page_count_raw is not None:
            page_int = int(page_count_raw)
            if page_int >= 0:
                page_count = page_int
    except (TypeError, ValueError):
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_page_count_invalid",
            module=logger.name,
            fields={"file_id": file_id, "raw": page_count_raw},
        ))
    try:
        if contents_page_raw is not None:
            page_int = int(contents_page_raw)
            if page_int >= 0:
                contents_page_number = page_int
    except (TypeError, ValueError):
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_contents_page_invalid",
            module=logger.name,
            fields={"file_id": file_id, "raw": contents_page_raw},
        ))
    try:
        parsed_packs = json.loads(evidence_packs_json)
        if isinstance(parsed_packs, dict):
            evidence_pack_paths = {str(k): str(v) for k, v in parsed_packs.items()}
    except json.JSONDecodeError:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_evidence_packs_parse_failed",
            module=logger.name,
            fields={"file_id": file_id},
        ))

    return ReportMetadataGetResponse(
        schema_version="1.1",
        file_id=file_id,
        title=row[2],
        created_at=int(row[17]),
        updated_at=int(row[18]),
        file_name=row[1],
        publisher=row[3],
        taxonomy=taxonomy,
        categories=categories,
        region=row[6],
        time_period=time_period,
        source_url=row[8],
        html_path=row[9],
        md5=row[10],
        page_count=page_count,
        contents_page_number=contents_page_number,
        pdf_metadata=pdf_metadata,
        analysis_mode=str(analysis_mode),
        vector_store_id=vector_store_id,
        evidence_pack_paths=evidence_pack_paths,
    )


def check_report_db_access(request: ReportMetadataDbAccessRequest, ctx: RunContext) -> ReportMetadataDbAccessResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="report_db_access_start",
        module=logger.name,
        fields={"db_path": request.db_path, "timeout_seconds": request.timeout_seconds},
    ))
    if not request.db_path or not request.db_path.strip():
        raise AppError(
            code="metadata_db_missing",
            message="Report metadata DB path is required",
            retryable=False,
            severity="error",
        )
    timeout = request.timeout_seconds if request.timeout_seconds >= 0 else ACCESS_TIMEOUT_SECONDS
    logger.info(log_event(
        ctx,
        role="service",
        event="report_db_access_config",
        module=logger.name,
        fields={"timeout_seconds": timeout},
    ))
    try:
        conn = sqlite3.connect(request.db_path, timeout=timeout)
    except sqlite3.Error as exc:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_db_access_connect_failed",
            module=logger.name,
            fields={"db_path": request.db_path, "error": str(exc)},
        ))
        raise AppError(
            code="metadata_db_unavailable",
            message="Failed to open report metadata DB",
            cause=exc,
            retryable=True,
            context={"db_path": request.db_path},
        ) from exc
    try:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_db_access_probe",
            module=logger.name,
            fields={"db_path": request.db_path},
        ))
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("ROLLBACK")
    except sqlite3.OperationalError as exc:
        if _is_lock_error(exc):
            message = str(exc)
            logger.info(log_event(
                ctx,
                role="service",
                event="report_db_access_locked",
                module=logger.name,
                fields={"db_path": request.db_path, "error": message},
            ))
            response = ReportMetadataDbAccessResponse(
                schema_version="1.0",
                db_path=request.db_path,
                accessible=False,
                locked=True,
                message=message,
            )
            logger.info(log_event(
                ctx,
                role="service",
                event="report_db_access_complete",
                module=logger.name,
                fields={
                    "db_path": response.db_path,
                    "accessible": response.accessible,
                    "locked": response.locked,
                    "message": response.message,
                },
            ))
            return response
        logger.info(log_event(
            ctx,
            role="service",
            event="report_db_access_failed",
            module=logger.name,
            fields={"db_path": request.db_path, "error": str(exc)},
        ))
        raise AppError(
            code="metadata_db_unavailable",
            message="Report metadata DB is not accessible",
            cause=exc,
            retryable=True,
            context={"db_path": request.db_path},
        ) from exc
    finally:
        conn.close()
    response = ReportMetadataDbAccessResponse(
        schema_version="1.0",
        db_path=request.db_path,
        accessible=True,
        locked=False,
        message="",
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="report_db_access_complete",
        module=logger.name,
        fields={
            "db_path": response.db_path,
            "accessible": response.accessible,
            "locked": response.locked,
            "message": response.message,
        },
    ))
    return response


def upsert_metadata(request: ReportMetadataUpsertRequest, ctx: RunContext) -> None:
    if not request.file_id.strip():
        raise AppError(
            code="metadata_file_id_missing",
            message="file_id is required for metadata upsert",
            retryable=False,
            severity="error",
        )
    if not request.title.strip():
        raise AppError(
            code="metadata_title_missing",
            message="title is required for metadata upsert",
            retryable=False,
            severity="error",
        )

    title = request.title.strip()
    file_name = request.file_name.strip() if request.file_name and request.file_name.strip() else None
    publisher = request.publisher.strip() if request.publisher and request.publisher.strip() else None
    source_url = request.source_url.strip() if request.source_url and request.source_url.strip() else None
    html_path = request.html_path.strip() if request.html_path and request.html_path.strip() else None
    md5 = request.md5.strip() if request.md5 and request.md5.strip() else None
    page_count = request.page_count if isinstance(request.page_count, int) and request.page_count >= 0 else None
    contents_page = request.contents_page_number if isinstance(request.contents_page_number, int) and request.contents_page_number >= 0 else 0
    taxonomy = clean_string_list(request.taxonomy)
    taxonomy_json = json.dumps(taxonomy, ensure_ascii=True)
    categories = clean_string_list(request.categories)
    categories_json = json.dumps(categories, ensure_ascii=True)
    region = request.region.strip() if request.region and request.region.strip() else None
    raw_time_period = request.time_period.strip() if request.time_period and request.time_period.strip() else None
    time_period = normalize_time_period(raw_time_period)
    metadata_clean = _clean_metadata(request.pdf_metadata)
    metadata_json = json.dumps(metadata_clean, ensure_ascii=True)
    analysis_mode = request.analysis_mode.strip() if request.analysis_mode else "vector_store"
    vector_store_id = request.vector_store_id.strip() if request.vector_store_id else None
    evidence_packs = request.evidence_pack_paths or {}
    evidence_packs_json = json.dumps(evidence_packs, ensure_ascii=False)

    logger.info(log_event(
        ctx,
        role="service",
        event="report_metadata_upsert_start",
        module=logger.name,
        fields={
            "file_id": request.file_id,
            "db_path": request.db_path,
            "file_name": file_name,
            "title": title,
            "publisher": publisher,
            "taxonomy_count": len(taxonomy),
            "region": region,
            "time_period": time_period,
            "raw_time_period": raw_time_period,
            "categories_count": len(categories),
            "page_count": page_count,
            "contents_page": contents_page,
            "metadata_keys": list(metadata_clean.keys()),
        },
    ))
    with _metadata_conn(request.db_path) as conn:
        conn.execute(
            """
            INSERT INTO reports(file_id, file_name, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, analysis_mode, vector_store_id, evidence_packs_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
            ON CONFLICT(file_id) DO UPDATE SET
                file_name=COALESCE(excluded.file_name, reports.file_name),
                title=excluded.title,
                publisher=excluded.publisher,
                taxonomy_json=excluded.taxonomy_json,
                categories_json=excluded.categories_json,
                region=excluded.region,
                time_period=excluded.time_period,
                source_url=excluded.source_url,
                html_path=excluded.html_path,
                md5=excluded.md5,
                page_count=excluded.page_count,
                contents_page=excluded.contents_page,
                pdf_metadata_json=excluded.pdf_metadata_json,
                analysis_mode=excluded.analysis_mode,
                vector_store_id=excluded.vector_store_id,
                evidence_packs_json=excluded.evidence_packs_json,
                updated_at=strftime('%s','now')
            """,
            (
                request.file_id,
                file_name,
                title,
                publisher,
                taxonomy_json,
                categories_json,
                region,
                time_period,
                source_url,
                html_path,
                md5,
                page_count,
                contents_page,
                metadata_json,
                analysis_mode,
                vector_store_id,
                evidence_packs_json,
            ),
        )
    logger.info(log_event(
        ctx,
        role="service",
        event="report_metadata_upsert_complete",
        module=logger.name,
        fields={"file_id": request.file_id},
    ))


def get_metadata(request: ReportMetadataGetRequest, ctx: RunContext) -> Optional[ReportMetadataGetResponse]:
    logger.info(log_event(
        ctx,
        role="service",
        event="report_metadata_get_start",
        module=logger.name,
        fields={"file_id": request.file_id, "db_path": request.db_path},
    ))
    with _metadata_conn(request.db_path) as conn:
        cur = conn.execute(
            """
            SELECT file_id, file_name, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, analysis_mode, vector_store_id, evidence_packs_json, created_at, updated_at
            FROM reports
            WHERE file_id=?
            """,
            (request.file_id,),
        )
        row = cur.fetchone()

    if not row:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_get_complete",
            module=logger.name,
            fields={"file_id": request.file_id, "found": False},
        ))
        return None

    response = _row_to_metadata_response(row, ctx)
    logger.info(log_event(
        ctx,
        role="service",
        event="report_metadata_get_complete",
        module=logger.name,
        fields={"file_id": request.file_id, "found": True},
    ))
    return response


def list_metadata(request: ReportMetadataListRequest, ctx: RunContext) -> ReportMetadataListResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="report_metadata_list_start",
        module=logger.name,
        fields={"db_path": request.db_path},
    ))
    rows: List[ReportMetadataGetResponse] = []
    with _metadata_conn(request.db_path) as conn:
        cur = conn.execute(
            """
            SELECT file_id, file_name, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, analysis_mode, vector_store_id, evidence_packs_json, created_at, updated_at
            FROM reports
            ORDER BY created_at ASC
            """
        )
        for row in cur.fetchall():
            rows.append(_row_to_metadata_response(row, ctx))
    logger.info(log_event(
        ctx,
        role="service",
        event="report_metadata_list_complete",
        module=logger.name,
        fields={"db_path": request.db_path, "count": len(rows)},
    ))
    return ReportMetadataListResponse(schema_version="1.1", records=rows)
