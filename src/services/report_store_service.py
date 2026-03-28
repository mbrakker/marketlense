from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import List, Optional
from urllib.parse import urlsplit

from src.contracts.report_store import (
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteRecordRequest,
    PublisherDownloadRouteResponse,
    PublishersReplaceRequest,
    PublishersReplaceResponse,
    ReportMetadataDbAccessRequest,
    ReportMetadataDbAccessResponse,
    ReportMetadataGetRequest,
    ReportMetadataGetResponse,
    ReportMetadataListRequest,
    ReportMetadataListResponse,
    ReportSourceRecordRequest,
    ReportSourceRecordResponse,
    ReportMetadataUpsertRequest,
)
from src.contracts.run_context import RunContext
from src.utils.coercion import clean_string_list
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.time_period import normalize_time_period
from src.utils.url_utils import normalize_url

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

CREATE TABLE IF NOT EXISTS report_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  source_domain TEXT NOT NULL,
  report_name TEXT NOT NULL,
  landing_page_url TEXT NOT NULL,
  downloaded_at_utc TEXT NOT NULL,
  md5 TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_report_sources_domain ON report_sources(source_domain);
CREATE INDEX IF NOT EXISTS idx_report_sources_md5 ON report_sources(md5);
CREATE INDEX IF NOT EXISTS idx_report_sources_downloaded_at ON report_sources(downloaded_at_utc);

CREATE TABLE IF NOT EXISTS publishers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  homepage TEXT NOT NULL,
  self_presentation TEXT NOT NULL,
  insights_url TEXT NOT NULL,
  google_folder TEXT,
  download_route_kind TEXT,
  download_route_summary TEXT,
  download_route_outcome TEXT,
  download_route_last_downloaded_file_path TEXT,
  download_route_last_final_page_url TEXT,
  download_route_updated_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_publishers_name ON publishers(name);
CREATE INDEX IF NOT EXISTS idx_publishers_homepage ON publishers(homepage);
CREATE INDEX IF NOT EXISTS idx_publishers_insights_url ON publishers(insights_url);
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
    _ensure_publishers_schema(conn)
    conn.commit()


def _ensure_publishers_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(publishers)")
    rows = cur.fetchall()
    expected = {
        "id",
        "name",
        "homepage",
        "self_presentation",
        "insights_url",
        "google_folder",
        "download_route_kind",
        "download_route_summary",
        "download_route_outcome",
        "download_route_last_downloaded_file_path",
        "download_route_last_final_page_url",
        "download_route_updated_at",
    }
    current = {str(row[1]) for row in rows}
    if current == expected:
        return

    conn.execute("DROP TABLE IF EXISTS publishers_new")
    conn.execute(
        """
        CREATE TABLE publishers_new (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          name TEXT NOT NULL,
          homepage TEXT NOT NULL,
          self_presentation TEXT NOT NULL,
          insights_url TEXT NOT NULL,
          google_folder TEXT,
          download_route_kind TEXT,
          download_route_summary TEXT,
          download_route_outcome TEXT,
          download_route_last_downloaded_file_path TEXT,
          download_route_last_final_page_url TEXT,
          download_route_updated_at INTEGER
        )
        """
    )
    if rows:
        selectable = [
            col
            for col in (
                "name",
                "homepage",
                "self_presentation",
                "insights_url",
                "google_folder",
                "download_route_kind",
                "download_route_summary",
                "download_route_outcome",
                "download_route_last_downloaded_file_path",
                "download_route_last_final_page_url",
                "download_route_updated_at",
            )
            if col in current
        ]
        if selectable:
            quoted = ", ".join(selectable)
            conn.execute(
                f"""
                INSERT INTO publishers_new({quoted})
                SELECT {quoted}
                FROM publishers
                """
            )
    conn.execute("DROP TABLE IF EXISTS publishers")
    conn.execute("ALTER TABLE publishers_new RENAME TO publishers")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_publishers_name ON publishers(name)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publishers_homepage ON publishers(homepage)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_publishers_insights_url ON publishers(insights_url)"
    )


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


def record_report_source(
    request: ReportSourceRecordRequest, ctx: RunContext
) -> ReportSourceRecordResponse:
    db_path = request.db_path.strip()
    source_domain = request.source_domain.strip()
    report_name = request.report_name.strip()
    landing_page_url = request.landing_page_url.strip()
    downloaded_at_utc = request.downloaded_at_utc.strip()
    md5 = request.md5.strip().lower()

    if not db_path:
        raise AppError(
            code="report_source_db_missing",
            message="Report metadata DB path is required for source recording",
            retryable=False,
            severity="error",
        )
    if not source_domain:
        raise AppError(
            code="report_source_domain_missing",
            message="source_domain is required for report source recording",
            retryable=False,
            severity="error",
        )
    if not report_name:
        raise AppError(
            code="report_source_name_missing",
            message="report_name is required for report source recording",
            retryable=False,
            severity="error",
        )
    if not landing_page_url:
        raise AppError(
            code="report_source_url_missing",
            message="landing_page_url is required for report source recording",
            retryable=False,
            severity="error",
        )
    if not downloaded_at_utc:
        raise AppError(
            code="report_source_downloaded_at_missing",
            message="downloaded_at_utc is required for report source recording",
            retryable=False,
            severity="error",
        )
    if not md5:
        raise AppError(
            code="report_source_md5_missing",
            message="md5 is required for report source recording",
            retryable=False,
            severity="error",
        )

    logger.info(log_event(
        ctx,
        role="service",
        event="report_source_record_start",
        module=logger.name,
        fields={
            "db_path": db_path,
            "source_domain": source_domain,
            "report_name": report_name,
            "landing_page_url": landing_page_url,
            "downloaded_at_utc": downloaded_at_utc,
            "md5": md5,
        },
    ))
    try:
        with _metadata_conn(db_path) as conn:
            cur = conn.execute(
                """
                INSERT INTO report_sources(source_domain, report_name, landing_page_url, downloaded_at_utc, md5)
                VALUES(?, ?, ?, ?, ?)
                """,
                (
                    source_domain,
                    report_name,
                    landing_page_url,
                    downloaded_at_utc,
                    md5,
                ),
            )
            record_id = int(cur.lastrowid or 0)
    except sqlite3.Error as exc:
        raise AppError(
            code="report_source_record_failed",
            message="Failed to record downloaded report source",
            cause=exc,
            retryable=True,
            context={
                "db_path": db_path,
                "source_domain": source_domain,
                "landing_page_url": landing_page_url,
                "md5": md5,
            },
        ) from exc

    response = ReportSourceRecordResponse(
        schema_version="1.0",
        record_id=record_id,
        source_domain=source_domain,
        report_name=report_name,
        landing_page_url=landing_page_url,
        downloaded_at_utc=downloaded_at_utc,
        md5=md5,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="report_source_record_complete",
        module=logger.name,
        fields={
            "record_id": response.record_id,
            "source_domain": response.source_domain,
            "report_name": response.report_name,
            "landing_page_url": response.landing_page_url,
            "downloaded_at_utc": response.downloaded_at_utc,
            "md5": response.md5,
        },
    ))
    return response


def replace_publishers(
    request: PublishersReplaceRequest,
    ctx: RunContext,
) -> PublishersReplaceResponse:
    db_path = request.db_path.strip()
    source_page_url = request.source_page_url.strip()
    publishers = request.publishers

    if not db_path:
        raise AppError(
            code="publishers_db_missing",
            message="Report metadata DB path is required for publisher sync",
            retryable=False,
            severity="error",
        )
    if not source_page_url:
        raise AppError(
            code="publishers_source_page_missing",
            message="source_page_url is required for publisher sync",
            retryable=False,
            severity="error",
        )

    seen_ids: set[str] = set()
    rows: list[tuple[str, str, str, str]] = []
    for publisher in publishers:
        notion_page_id = publisher.notion_page_id.strip()
        name = publisher.name.strip()
        homepage = publisher.homepage.strip()
        self_presentation = publisher.self_presentation.strip()
        insights_url = publisher.insights_url.strip()

        if not notion_page_id:
            raise AppError(
                code="publisher_notion_page_id_missing",
                message="Each publisher row requires notion_page_id",
                retryable=False,
                severity="error",
            )
        if notion_page_id in seen_ids:
            raise AppError(
                code="publisher_notion_page_id_duplicate",
                message=f"Duplicate notion_page_id in publisher sync payload: {notion_page_id}",
                retryable=False,
                severity="error",
            )
        if not name:
            raise AppError(
                code="publisher_name_missing",
                message=f"Publisher '{notion_page_id}' requires name",
                retryable=False,
                severity="error",
            )

        seen_ids.add(notion_page_id)
        rows.append(
            (
                name,
                homepage,
                self_presentation,
                insights_url,
            )
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="publishers_replace_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "source_page_url": source_page_url,
                "publisher_count": len(rows),
            },
        )
    )
    try:
        with _metadata_conn(db_path) as conn:
            existing_row = conn.execute("SELECT COUNT(*) FROM publishers").fetchone()
            previous_count = int(existing_row[0] if existing_row else 0)
            preserved_rows = conn.execute(
                """
                SELECT
                    name,
                    insights_url,
                    google_folder,
                    download_route_kind,
                    download_route_summary,
                    download_route_outcome,
                    download_route_last_downloaded_file_path,
                    download_route_last_final_page_url,
                    download_route_updated_at
                FROM publishers
                """
            ).fetchall()
            preserved_by_insights_url: dict[str, tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[int]]] = {}
            preserved_by_name: dict[str, tuple[Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[str], Optional[int]]] = {}
            for row in preserved_rows:
                name_key = _normalize_publisher_key(str(row[0] or ""))
                insights_url_key = _normalize_optional_url_key(str(row[1] or ""))
                preserved_payload = (
                    str(row[2] or "").strip() or None,
                    str(row[3] or "").strip() or None,
                    str(row[4] or "").strip() or None,
                    str(row[5] or "").strip() or None,
                    str(row[6] or "").strip() or None,
                    str(row[7] or "").strip() or None,
                    int(row[8]) if row[8] is not None else None,
                )
                if insights_url_key and insights_url_key not in preserved_by_insights_url:
                    preserved_by_insights_url[insights_url_key] = preserved_payload
                if name_key and name_key not in preserved_by_name:
                    preserved_by_name[name_key] = preserved_payload
            conn.execute("DELETE FROM publishers")
            if rows:
                rows_with_routes = []
                for row in rows:
                    insights_url_key = _normalize_optional_url_key(row[3])
                    name_key = _normalize_publisher_key(row[0])
                    preserved = (
                        preserved_by_insights_url.get(insights_url_key)
                        if insights_url_key
                        else None
                    )
                    if preserved is None and name_key:
                        preserved = preserved_by_name.get(name_key)
                    if preserved is None:
                        preserved = (None, None, None, None, None, None, None)
                    rows_with_routes.append((*row, *preserved))
                conn.executemany(
                    """
                    INSERT INTO publishers(
                        name,
                        homepage,
                        self_presentation,
                        insights_url,
                        google_folder,
                        download_route_kind,
                        download_route_summary,
                        download_route_outcome,
                        download_route_last_downloaded_file_path,
                        download_route_last_final_page_url,
                        download_route_updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    rows_with_routes,
                )
    except sqlite3.Error as exc:
        raise AppError(
            code="publishers_replace_failed",
            message="Failed to replace publishers in the reports database",
            cause=exc,
            retryable=True,
            context={
                "db_path": db_path,
                "source_page_url": source_page_url,
                "publisher_count": len(rows),
            },
        ) from exc

    response = PublishersReplaceResponse(
        schema_version="1.0",
        db_path=db_path,
        source_page_url=source_page_url,
        previous_count=previous_count,
        replaced_count=len(rows),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publishers_replace_complete",
            module=logger.name,
            fields={
                "db_path": response.db_path,
                "source_page_url": response.source_page_url,
                "previous_count": response.previous_count,
                "replaced_count": response.replaced_count,
            },
        )
    )
    return response


def _normalize_publisher_key(name: str) -> str:
    token = str(name).strip().lower()
    if not token:
        return ""
    token = token.replace("&", " and ")
    token = re.sub(r"[^a-z0-9]+", "", token)
    return token


def _normalize_optional_url_key(url: str) -> str:
    token = str(url).strip()
    if not token:
        return ""
    return normalize_url(token)


def get_publisher_download_route(
    request: PublisherDownloadRouteGetRequest,
    ctx: RunContext,
) -> Optional[PublisherDownloadRouteResponse]:
    db_path = request.db_path.strip()
    normalized_url = request.normalized_url.strip()
    if not db_path:
        raise AppError(
            code="publisher_route_db_missing",
            message="Report metadata DB path is required for publisher route lookup",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_route_normalized_url_missing",
            message="normalized_url is required for publisher route lookup",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_route_get_start",
            module=logger.name,
            fields={"db_path": db_path, "normalized_url": normalized_url},
        )
    )
    with _metadata_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                insights_url,
                download_route_kind,
                download_route_summary,
                download_route_outcome,
                download_route_last_downloaded_file_path,
                download_route_last_final_page_url,
                download_route_updated_at
            FROM publishers
            WHERE insights_url <> ''
              AND download_route_summary IS NOT NULL
            ORDER BY id ASC
            """
        ).fetchall()
    for row in rows:
        insights_url = str(row[0] or "").strip()
        if not insights_url:
            continue
        if normalize_url(insights_url) != normalized_url:
            continue
        response = PublisherDownloadRouteResponse(
            schema_version="1.0",
            normalized_url=normalized_url,
            source_url=insights_url,
            route_kind=str(row[1] or "").strip(),
            route_summary=str(row[2] or "").strip(),
            outcome=str(row[3] or "").strip(),
            updated_at=int(row[6] or 0),
            last_downloaded_file_path=str(row[4] or "").strip() or None,
            last_final_page_url=str(row[5] or "").strip() or None,
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_route_get_complete",
                module=logger.name,
                fields={
                    "db_path": db_path,
                    "normalized_url": normalized_url,
                    "found": True,
                    "source_url": response.source_url,
                    "route_kind": response.route_kind,
                    "outcome": response.outcome,
                },
            )
        )
        return response
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_route_get_complete",
            module=logger.name,
            fields={"db_path": db_path, "normalized_url": normalized_url, "found": False},
        )
    )
    return None


def record_publisher_download_route(
    request: PublisherDownloadRouteRecordRequest,
    ctx: RunContext,
) -> None:
    db_path = request.db_path.strip()
    normalized_url = request.normalized_url.strip()
    source_url = request.source_url.strip()
    route_kind = request.route_kind.strip()
    route_summary = request.route_summary.strip()
    outcome = request.outcome.strip()
    last_downloaded_file_path = (
        request.last_downloaded_file_path.strip()
        if request.last_downloaded_file_path and request.last_downloaded_file_path.strip()
        else None
    )
    last_final_page_url = (
        request.last_final_page_url.strip()
        if request.last_final_page_url and request.last_final_page_url.strip()
        else None
    )
    if not db_path:
        raise AppError(
            code="publisher_route_db_missing",
            message="Report metadata DB path is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_route_normalized_url_missing",
            message="normalized_url is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not source_url:
        raise AppError(
            code="publisher_route_source_url_missing",
            message="source_url is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not route_kind:
        raise AppError(
            code="publisher_route_kind_missing",
            message="route_kind is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not route_summary:
        raise AppError(
            code="publisher_route_summary_missing",
            message="route_summary is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    if not outcome:
        raise AppError(
            code="publisher_route_outcome_missing",
            message="outcome is required for publisher route recording",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_route_record_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "source_url": source_url,
                "route_kind": route_kind,
                "outcome": outcome,
            },
        )
    )
    try:
        with _metadata_conn(db_path) as conn:
            matched_id: Optional[int] = None
            rows = conn.execute(
                "SELECT id, insights_url FROM publishers WHERE insights_url <> '' ORDER BY id ASC"
            ).fetchall()
            for row in rows:
                if normalize_url(str(row[1] or "").strip()) == normalized_url:
                    matched_id = int(row[0])
                    source_url = str(row[1] or "").strip() or source_url
                    break
            if matched_id is None:
                parsed = urlsplit(source_url)
                placeholder_name = parsed.netloc or source_url
                homepage = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme and parsed.netloc else ""
                cur = conn.execute(
                    """
                    INSERT INTO publishers(
                        name,
                        homepage,
                        self_presentation,
                        insights_url,
                        download_route_kind,
                        download_route_summary,
                        download_route_outcome,
                        download_route_last_downloaded_file_path,
                        download_route_last_final_page_url,
                        download_route_updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))
                    """,
                    (
                        placeholder_name,
                        homepage,
                        "",
                        source_url,
                        route_kind,
                        route_summary,
                        outcome,
                        last_downloaded_file_path,
                        last_final_page_url,
                    ),
                )
                matched_id = int(cur.lastrowid or 0)
            else:
                conn.execute(
                    """
                    UPDATE publishers
                    SET
                        download_route_kind=?,
                        download_route_summary=?,
                        download_route_outcome=?,
                        download_route_last_downloaded_file_path=?,
                        download_route_last_final_page_url=?,
                        download_route_updated_at=strftime('%s','now')
                    WHERE id=?
                    """,
                    (
                        route_kind,
                        route_summary,
                        outcome,
                        last_downloaded_file_path,
                        last_final_page_url,
                        matched_id,
                    ),
                )
    except sqlite3.Error as exc:
        raise AppError(
            code="publisher_route_record_failed",
            message="Failed to record publisher route memory",
            cause=exc,
            retryable=True,
            context={"db_path": db_path, "source_url": source_url},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_route_record_complete",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "source_url": source_url,
                "route_kind": route_kind,
                "outcome": outcome,
            },
        )
    )
