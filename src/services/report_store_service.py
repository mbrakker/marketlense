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
  region TEXT,
  time_period TEXT,
  source_url TEXT,
  html_path TEXT,
  md5 TEXT,
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
    taxonomy = _clean_list(request.taxonomy)
    taxonomy_json = json.dumps(taxonomy, ensure_ascii=True)
    region = request.region.strip() if request.region and request.region.strip() else None
    time_period = request.time_period.strip() if request.time_period and request.time_period.strip() else None

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
        },
    ))
    with _metadata_conn(request.db_path) as conn:
        conn.execute(
            """
            INSERT INTO reports(file_id, title, publisher, taxonomy_json, region, time_period, source_url, html_path, md5, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
            ON CONFLICT(file_id) DO UPDATE SET
                title=excluded.title,
                publisher=excluded.publisher,
                taxonomy_json=excluded.taxonomy_json,
                region=excluded.region,
                time_period=excluded.time_period,
                source_url=excluded.source_url,
                html_path=excluded.html_path,
                md5=excluded.md5,
                updated_at=strftime('%s','now')
            """,
            (
                request.file_id,
                request.title,
                publisher,
                taxonomy_json,
                region,
                time_period,
                source_url,
                html_path,
                md5,
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
            SELECT file_id, title, publisher, taxonomy_json, region, time_period, source_url, html_path, md5, created_at, updated_at
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
    taxonomy: List[str] = []
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

    response = ReportMetadataGetResponse(
        schema_version="1.0",
        file_id=row[0],
        title=row[1],
        created_at=int(row[9]),
        updated_at=int(row[10]),
        publisher=row[2],
        taxonomy=taxonomy,
        region=row[4],
        time_period=row[5],
        source_url=row[6],
        html_path=row[7],
        md5=row[8],
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="report_metadata_get_complete",
        module=logger.name,
        fields={"file_id": request.file_id, "found": True},
    ))
    return response
