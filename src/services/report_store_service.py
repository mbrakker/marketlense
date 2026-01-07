from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional

from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportMetadataGetResponse,
    ReportMetadataListRequest,
    ReportMetadataListResponse,
    ReportMetadataUpsertRequest,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.report_store_service")

DDL = """
CREATE TABLE IF NOT EXISTS reports (
  file_id TEXT PRIMARY KEY,
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
  created_at INTEGER NOT NULL,
  updated_at INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_title ON reports(title);
CREATE INDEX IF NOT EXISTS idx_reports_publisher ON reports(publisher);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(reports)")
    cols = {row[1] for row in cur.fetchall()}
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
    conn = sqlite3.connect(path)
    try:
        conn.executescript(DDL)
        _ensure_schema(conn)
        conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _clean_list(values: List[str]) -> List[str]:
    return [v.strip() for v in values if isinstance(v, str) and v.strip()]


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

    publisher = request.publisher.strip() if request.publisher and request.publisher.strip() else None
    source_url = request.source_url.strip() if request.source_url and request.source_url.strip() else None
    html_path = request.html_path.strip() if request.html_path and request.html_path.strip() else None
    md5 = request.md5.strip() if request.md5 and request.md5.strip() else None
    page_count = request.page_count if isinstance(request.page_count, int) and request.page_count >= 0 else None
    contents_page = request.contents_page_number if isinstance(request.contents_page_number, int) and request.contents_page_number >= 0 else 0
    taxonomy = _clean_list(request.taxonomy)
    taxonomy_json = json.dumps(taxonomy, ensure_ascii=True)
    categories = _clean_list(request.categories)
    categories_json = json.dumps(categories, ensure_ascii=True)
    region = request.region.strip() if request.region and request.region.strip() else None
    time_period = request.time_period.strip() if request.time_period and request.time_period.strip() else None
    metadata_clean = _clean_metadata(request.pdf_metadata)
    metadata_json = json.dumps(metadata_clean, ensure_ascii=True)

    logger.info(log_event(
        ctx,
        role="service",
        event="report_metadata_upsert_start",
        module=logger.name,
        fields={
            "file_id": request.file_id,
            "db_path": request.db_path,
            "title": request.title,
            "publisher": publisher,
            "taxonomy_count": len(taxonomy),
            "region": region,
            "time_period": time_period,
            "categories_count": len(categories),
            "page_count": page_count,
            "contents_page": contents_page,
            "metadata_keys": list(metadata_clean.keys()),
        },
    ))
    with _metadata_conn(request.db_path) as conn:
        conn.execute(
            """
            INSERT INTO reports(file_id, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
            ON CONFLICT(file_id) DO UPDATE SET
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
                updated_at=strftime('%s','now')
            """,
            (
                request.file_id,
                request.title,
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
            SELECT file_id, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, created_at, updated_at
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

    taxonomy_json = row[3] or "[]"
    categories_json = row[4] or "[]"
    page_count_raw = row[10]
    contents_page_raw = row[11]
    metadata_json = row[12] or "{}"
    created_at = int(row[13])
    updated_at = int(row[14])
    taxonomy: List[str] = []
    categories: List[str] = []
    pdf_metadata: dict[str, str] = {}
    page_count: Optional[int] = None
    try:
        parsed = json.loads(taxonomy_json)
        if isinstance(parsed, list):
            taxonomy = _clean_list([str(item) for item in parsed])
    except json.JSONDecodeError:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_taxonomy_parse_failed",
            module=logger.name,
            fields={"file_id": request.file_id},
        ))
    try:
        parsed_cats = json.loads(categories_json)
        if isinstance(parsed_cats, list):
            categories = _clean_list([str(item) for item in parsed_cats])
    except json.JSONDecodeError:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_categories_parse_failed",
            module=logger.name,
            fields={"file_id": request.file_id},
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
            fields={"file_id": request.file_id},
        ))
    try:
        if page_count_raw is not None:
            page_int = int(page_count_raw)
            if page_int >= 0:
                page_count = page_int
    except Exception:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_page_count_invalid",
            module=logger.name,
            fields={"file_id": request.file_id, "raw": page_count_raw},
        ))

    contents_page_number = 0
    try:
        if contents_page_raw is not None:
            page_int = int(contents_page_raw)
            if page_int >= 0:
                contents_page_number = page_int
    except Exception:
        logger.info(log_event(
            ctx,
            role="service",
            event="report_metadata_contents_page_invalid",
            module=logger.name,
            fields={"file_id": request.file_id, "raw": contents_page_raw},
        ))

    response = ReportMetadataGetResponse(
        schema_version="1.1",
        file_id=row[0],
        title=row[1],
        created_at=created_at,
        updated_at=updated_at,
        publisher=row[2],
        taxonomy=taxonomy,
        categories=categories,
        region=row[5],
        time_period=row[6],
        source_url=row[7],
        html_path=row[8],
        md5=row[9],
        page_count=page_count,
        contents_page_number=contents_page_number,
        pdf_metadata=pdf_metadata,
    )
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
            SELECT file_id, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, created_at, updated_at
            FROM reports
            ORDER BY created_at ASC
            """
        )
        for row in cur.fetchall():
            taxonomy_json = row[3] or "[]"
            categories_json = row[4] or "[]"
            page_count_raw = row[10]
            contents_page_raw = row[11]
            metadata_json = row[12] or "{}"
            taxonomy: List[str] = []
            categories: List[str] = []
            pdf_metadata: dict[str, str] = {}
            page_count: Optional[int] = None
            contents_page_number = 0
            try:
                parsed = json.loads(taxonomy_json)
                if isinstance(parsed, list):
                    taxonomy = _clean_list([str(item) for item in parsed])
            except json.JSONDecodeError:
                logger.info(log_event(
                    ctx,
                    role="service",
                    event="report_metadata_taxonomy_parse_failed",
                    module=logger.name,
                    fields={"file_id": row[0]},
                ))
            try:
                parsed_cats = json.loads(categories_json)
                if isinstance(parsed_cats, list):
                    categories = _clean_list([str(item) for item in parsed_cats])
            except json.JSONDecodeError:
                logger.info(log_event(
                    ctx,
                    role="service",
                    event="report_metadata_categories_parse_failed",
                    module=logger.name,
                    fields={"file_id": row[0]},
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
                    fields={"file_id": row[0]},
                ))
            try:
                if page_count_raw is not None:
                    page_int = int(page_count_raw)
                    if page_int >= 0:
                        page_count = page_int
            except Exception:
                logger.info(log_event(
                    ctx,
                    role="service",
                    event="report_metadata_page_count_invalid",
                    module=logger.name,
                    fields={"file_id": row[0], "raw": page_count_raw},
                ))
            try:
                if contents_page_raw is not None:
                    page_int = int(contents_page_raw)
                    if page_int >= 0:
                        contents_page_number = page_int
            except Exception:
                logger.info(log_event(
                    ctx,
                    role="service",
                    event="report_metadata_contents_page_invalid",
                    module=logger.name,
                    fields={"file_id": row[0], "raw": contents_page_raw},
                ))
            rows.append(ReportMetadataGetResponse(
                schema_version="1.1",
                file_id=row[0],
                title=row[1],
                created_at=int(row[13]),
                updated_at=int(row[14]),
                publisher=row[2],
                taxonomy=taxonomy,
                categories=categories,
                region=row[5],
                time_period=row[6],
                source_url=row[7],
                html_path=row[8],
                md5=row[9],
                page_count=page_count,
                contents_page_number=contents_page_number,
                pdf_metadata=pdf_metadata,
            ))
    logger.info(log_event(
        ctx,
        role="service",
        event="report_metadata_list_complete",
        module=logger.name,
        fields={"db_path": request.db_path, "count": len(rows)},
    ))
    return ReportMetadataListResponse(schema_version="1.1", records=rows)
