from __future__ import annotations

from dataclasses import asdict
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
    PublisherInventoryStateGetRequest,
    PublisherInventoryRunQualityRecordRequest,
    PublisherInventoryStateRecordRequest,
    PublisherInventoryStateResponse,
    PublisherInventoryTestStatusRecordRequest,
    PublishersReplaceRequest,
    PublishersReplaceResponse,
    ReportMetadataDbAccessRequest,
    ReportMetadataDbAccessResponse,
    ReportMetadataGetRequest,
    ReportMetadataGetResponse,
    ReportMetadataListRequest,
    ReportMetadataListResponse,
    ReportSourceDiscoveryRecordRequest,
    ReportSourceDiscoveryRecordResponse,
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
DEFAULT_BUSY_TIMEOUT_SECONDS = 5.0
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
  normalized_landing_page_url TEXT NOT NULL,
  source_status TEXT NOT NULL,
  source_page_url TEXT,
  publisher_name TEXT,
  discovered_at_utc TEXT,
  discovered_on_page_number INTEGER,
  downloaded_at_utc TEXT,
  md5 TEXT,
  created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
  updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
);

CREATE TABLE IF NOT EXISTS publishers (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  homepage TEXT NOT NULL,
  self_presentation TEXT NOT NULL,
  insights_url TEXT NOT NULL,
  google_folder TEXT,
  discovery_test_status TEXT,
  download_route_kind TEXT,
  download_route_summary TEXT,
  download_route_outcome TEXT,
  download_route_last_downloaded_file_path TEXT,
  download_route_last_final_page_url TEXT,
  download_route_updated_at INTEGER,
  inventory_route_kind TEXT,
  inventory_route_summary TEXT,
  inventory_route_last_final_page_url TEXT,
  inventory_route_updated_at INTEGER,
  inventory_snapshot_drive_file_id TEXT,
  inventory_snapshot_drive_file_name TEXT,
  inventory_snapshot_sha256 TEXT,
  inventory_snapshot_updated_at INTEGER,
  inventory_run_quality_json TEXT,
  inventory_run_quality_updated_at INTEGER
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
    _ensure_report_sources_schema(conn)
    _ensure_publishers_schema(conn)
    conn.commit()


def _ensure_report_sources_schema(conn: sqlite3.Connection) -> None:
    cur = conn.execute("PRAGMA table_info(report_sources)")
    rows = cur.fetchall()
    expected = {
        "id",
        "source_domain",
        "report_name",
        "landing_page_url",
        "normalized_landing_page_url",
        "source_status",
        "source_page_url",
        "publisher_name",
        "discovered_at_utc",
        "discovered_on_page_number",
        "downloaded_at_utc",
        "md5",
        "created_at",
        "updated_at",
    }
    current = {str(row[1]) for row in rows}
    if current == expected:
        _ensure_report_sources_indexes(conn)
        return

    conn.execute("DROP TABLE IF EXISTS report_sources_new")
    conn.execute(
        """
        CREATE TABLE report_sources_new (
          id INTEGER PRIMARY KEY AUTOINCREMENT,
          source_domain TEXT NOT NULL,
          report_name TEXT NOT NULL,
          landing_page_url TEXT NOT NULL,
          normalized_landing_page_url TEXT NOT NULL,
          source_status TEXT NOT NULL,
          source_page_url TEXT,
          publisher_name TEXT,
          discovered_at_utc TEXT,
          discovered_on_page_number INTEGER,
          downloaded_at_utc TEXT,
          md5 TEXT,
          created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
          updated_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))
        )
        """
    )
    if rows:
        fetched_rows = conn.execute(
            "SELECT * FROM report_sources ORDER BY id ASC"
        ).fetchall()
        column_order = [str(row[1]) for row in rows]
        current_epoch = int(conn.execute("SELECT strftime('%s','now')").fetchone()[0])
        for fetched in fetched_rows:
            source = dict(zip(column_order, fetched))
            landing_page_url = str(source.get("landing_page_url") or "").strip()
            normalized_landing_page_url = _normalize_optional_url_key(landing_page_url)
            if not landing_page_url or not normalized_landing_page_url:
                continue
            downloaded_at_utc = str(source.get("downloaded_at_utc") or "").strip() or None
            md5 = str(source.get("md5") or "").strip().lower() or None
            source_status = str(source.get("source_status") or "").strip() or "downloaded"
            source_page_url = (
                str(source.get("source_page_url") or "").strip() or landing_page_url
            )
            discovered_at_utc = (
                str(source.get("discovered_at_utc") or "").strip() or downloaded_at_utc
            )
            discovered_on_page_number = source.get("discovered_on_page_number")
            created_at = int(source.get("created_at") or 0) or current_epoch
            updated_at = int(source.get("updated_at") or 0) or created_at
            conn.execute(
                """
                INSERT OR REPLACE INTO report_sources_new(
                    id,
                    source_domain,
                    report_name,
                    landing_page_url,
                    normalized_landing_page_url,
                    source_status,
                    source_page_url,
                    publisher_name,
                    discovered_at_utc,
                    discovered_on_page_number,
                    downloaded_at_utc,
                    md5,
                    created_at,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    int(source.get("id") or 0) or None,
                    str(source.get("source_domain") or "").strip(),
                    str(source.get("report_name") or "").strip(),
                    landing_page_url,
                    normalized_landing_page_url,
                    source_status,
                    source_page_url,
                    str(source.get("publisher_name") or "").strip() or None,
                    discovered_at_utc,
                    int(discovered_on_page_number)
                    if discovered_on_page_number is not None
                    else None,
                    downloaded_at_utc,
                    md5,
                    created_at,
                    updated_at,
                ),
            )
    conn.execute("DROP TABLE IF EXISTS report_sources")
    conn.execute("ALTER TABLE report_sources_new RENAME TO report_sources")
    _ensure_report_sources_indexes(conn)


def _ensure_report_sources_indexes(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_domain ON report_sources(source_domain)"
    )
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_report_sources_normalized_url ON report_sources(normalized_landing_page_url)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_status ON report_sources(source_status)"
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_report_sources_md5 ON report_sources(md5)")
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_discovered_at ON report_sources(discovered_at_utc)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_report_sources_downloaded_at ON report_sources(downloaded_at_utc)"
    )


def _optional_int(value: object) -> Optional[int]:
    if value is None:
        return None
    value_str = str(value).strip()
    if not value_str:
        return None
    return int(value_str)


def _serialize_inventory_run_quality_summary(summary) -> Optional[str]:
    if summary is None:
        return None
    return json.dumps(
        asdict(summary),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _parse_inventory_run_quality_summary(payload: Optional[str]):
    token = str(payload or "").strip()
    if not token:
        return None
    from src.contracts.publisher_inventory import PublisherInventoryRunQualitySummary

    try:
        parsed = json.loads(token)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    try:
        return PublisherInventoryRunQualitySummary(
            schema_version=str(parsed.get("schema_version") or "1.0"),
            outcome=str(parsed["outcome"]).strip(),
            status=str(parsed["status"]).strip(),
            quality_band=str(parsed["quality_band"]).strip(),
            route_kind=str(parsed["route_kind"]).strip(),
            recommended_route_kind=str(parsed["recommended_route_kind"]).strip(),
            used_memory_route=bool(parsed["used_memory_route"]),
            page_count=int(parsed["page_count"]),
            raw_candidate_count=int(parsed["raw_candidate_count"]),
            current_report_count=int(parsed["current_report_count"]),
            previous_report_count=int(parsed["previous_report_count"]),
            raw_new_report_count=int(parsed["raw_new_report_count"]),
            screened_new_report_count=int(parsed["screened_new_report_count"]),
            qualified_new_report_count=int(parsed["qualified_new_report_count"]),
            snapshot_changed=bool(parsed["snapshot_changed"]),
            requires_review=bool(parsed["requires_review"]),
            recommended_route_reason=str(parsed["recommended_route_reason"]).strip(),
            summary=str(parsed["summary"]).strip(),
            candidate_provenance_counts={
                str(key).strip(): int(value)
                for key, value in dict(
                    parsed.get("candidate_provenance_counts") or {}
                ).items()
                if str(key).strip()
            },
        )
    except (KeyError, TypeError, ValueError):
        return None


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
        "discovery_test_status",
        "download_route_kind",
        "download_route_summary",
        "download_route_outcome",
        "download_route_last_downloaded_file_path",
        "download_route_last_final_page_url",
        "download_route_updated_at",
        "inventory_route_kind",
        "inventory_route_summary",
        "inventory_route_last_final_page_url",
        "inventory_route_updated_at",
        "inventory_snapshot_drive_file_id",
        "inventory_snapshot_drive_file_name",
        "inventory_snapshot_sha256",
        "inventory_snapshot_updated_at",
        "inventory_run_quality_json",
        "inventory_run_quality_updated_at",
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
          discovery_test_status TEXT,
          download_route_kind TEXT,
          download_route_summary TEXT,
          download_route_outcome TEXT,
          download_route_last_downloaded_file_path TEXT,
          download_route_last_final_page_url TEXT,
          download_route_updated_at INTEGER,
          inventory_route_kind TEXT,
          inventory_route_summary TEXT,
          inventory_route_last_final_page_url TEXT,
          inventory_route_updated_at INTEGER,
          inventory_snapshot_drive_file_id TEXT,
          inventory_snapshot_drive_file_name TEXT,
          inventory_snapshot_sha256 TEXT,
          inventory_snapshot_updated_at INTEGER,
          inventory_run_quality_json TEXT,
          inventory_run_quality_updated_at INTEGER
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
                "discovery_test_status",
                "download_route_kind",
                "download_route_summary",
                "download_route_outcome",
                "download_route_last_downloaded_file_path",
                "download_route_last_final_page_url",
                "download_route_updated_at",
                "inventory_route_kind",
                "inventory_route_summary",
                "inventory_route_last_final_page_url",
                "inventory_route_updated_at",
                "inventory_snapshot_drive_file_id",
                "inventory_snapshot_drive_file_name",
                "inventory_snapshot_sha256",
                "inventory_snapshot_updated_at",
                "inventory_run_quality_json",
                "inventory_run_quality_updated_at",
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
    conn = sqlite3.connect(path, timeout=DEFAULT_BUSY_TIMEOUT_SECONDS)
    try:
        _configure_sqlite_connection(
            conn,
            busy_timeout_seconds=DEFAULT_BUSY_TIMEOUT_SECONDS,
        )
        with _REPORT_CONN_LOCK:
            conn.executescript(DDL)
            _ensure_schema(conn)
            conn.commit()
        yield conn
        conn.commit()
    finally:
        conn.close()


def _configure_sqlite_connection(
    conn: sqlite3.Connection,
    *,
    busy_timeout_seconds: float,
) -> None:
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        f"PRAGMA busy_timeout={max(0, int(busy_timeout_seconds * 1000))}"
    )
    conn.execute("PRAGMA synchronous=NORMAL")


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
        _configure_sqlite_connection(conn, busy_timeout_seconds=timeout)
        logger.info(log_event(
            ctx,
            role="service",
            event="report_db_access_probe",
            module=logger.name,
            fields={"db_path": request.db_path},
        ))
        conn.execute("PRAGMA schema_version")
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
    normalized_landing_page_url = _normalize_optional_url_key(landing_page_url)

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
    if not normalized_landing_page_url:
        raise AppError(
            code="report_source_url_invalid",
            message="landing_page_url must be a valid absolute URL for report source recording",
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
            existing_row = conn.execute(
                """
                SELECT id, discovered_at_utc
                FROM report_sources
                WHERE normalized_landing_page_url=?
                """,
                (normalized_landing_page_url,),
            ).fetchone()
            if existing_row:
                record_id = int(existing_row[0])
                discovered_at_utc_value = (
                    str(existing_row[1] or "").strip() or downloaded_at_utc
                )
                conn.execute(
                    """
                    UPDATE report_sources
                    SET
                        source_domain=?,
                        report_name=?,
                        landing_page_url=?,
                        source_status='downloaded',
                        source_page_url=COALESCE(NULLIF(source_page_url, ''), ?),
                        discovered_at_utc=COALESCE(NULLIF(discovered_at_utc, ''), ?),
                        downloaded_at_utc=?,
                        md5=?,
                        updated_at=strftime('%s','now')
                    WHERE id=?
                    """,
                    (
                        source_domain,
                        report_name,
                        landing_page_url,
                        landing_page_url,
                        discovered_at_utc_value,
                        downloaded_at_utc,
                        md5,
                        record_id,
                    ),
                )
            else:
                cur = conn.execute(
                    """
                    INSERT INTO report_sources(
                        source_domain,
                        report_name,
                        landing_page_url,
                        normalized_landing_page_url,
                        source_status,
                        source_page_url,
                        publisher_name,
                        discovered_at_utc,
                        discovered_on_page_number,
                        downloaded_at_utc,
                        md5
                    )
                    VALUES(?, ?, ?, ?, 'downloaded', ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        source_domain,
                        report_name,
                        landing_page_url,
                        normalized_landing_page_url,
                        landing_page_url,
                        None,
                        downloaded_at_utc,
                        None,
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


def record_discovered_report_source(
    request: ReportSourceDiscoveryRecordRequest,
    ctx: RunContext,
) -> ReportSourceDiscoveryRecordResponse:
    db_path = request.db_path.strip()
    publisher_name = request.publisher_name.strip()
    source_domain = request.source_domain.strip().lower()
    report_name = request.report_name.strip()
    landing_page_url = request.landing_page_url.strip()
    source_page_url = request.source_page_url.strip()
    discovered_at_utc = request.discovered_at_utc.strip()
    discovered_on_page_number = int(request.discovered_on_page_number)
    normalized_landing_page_url = _normalize_optional_url_key(landing_page_url)

    if not db_path:
        raise AppError(
            code="report_source_discovery_db_missing",
            message="Report metadata DB path is required for discovered source recording",
            retryable=False,
            severity="error",
        )
    if not publisher_name:
        raise AppError(
            code="report_source_discovery_publisher_missing",
            message="publisher_name is required for discovered source recording",
            retryable=False,
            severity="error",
        )
    if not source_domain:
        raise AppError(
            code="report_source_discovery_domain_missing",
            message="source_domain is required for discovered source recording",
            retryable=False,
            severity="error",
        )
    if not report_name:
        raise AppError(
            code="report_source_discovery_name_missing",
            message="report_name is required for discovered source recording",
            retryable=False,
            severity="error",
        )
    if not landing_page_url:
        raise AppError(
            code="report_source_discovery_url_missing",
            message="landing_page_url is required for discovered source recording",
            retryable=False,
            severity="error",
        )
    if not normalized_landing_page_url:
        raise AppError(
            code="report_source_discovery_url_invalid",
            message="landing_page_url must be a valid absolute URL for discovered source recording",
            retryable=False,
            severity="error",
        )
    if not source_page_url:
        raise AppError(
            code="report_source_discovery_source_page_missing",
            message="source_page_url is required for discovered source recording",
            retryable=False,
            severity="error",
        )
    if not discovered_at_utc:
        raise AppError(
            code="report_source_discovery_discovered_at_missing",
            message="discovered_at_utc is required for discovered source recording",
            retryable=False,
            severity="error",
        )
    if discovered_on_page_number <= 0:
        raise AppError(
            code="report_source_discovery_page_number_invalid",
            message="discovered_on_page_number must be at least 1 for discovered source recording",
            retryable=False,
            severity="error",
        )

    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_discovery_record_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "publisher_name": publisher_name,
                "source_domain": source_domain,
                "report_name": report_name,
                "landing_page_url": landing_page_url,
                "source_page_url": source_page_url,
                "discovered_at_utc": discovered_at_utc,
                "discovered_on_page_number": discovered_on_page_number,
            },
        )
    )
    try:
        with _metadata_conn(db_path) as conn:
            existing_row = conn.execute(
                """
                SELECT id, source_status, downloaded_at_utc, md5
                FROM report_sources
                WHERE normalized_landing_page_url=?
                """,
                (normalized_landing_page_url,),
            ).fetchone()
            created_new = existing_row is None
            if existing_row:
                record_id = int(existing_row[0])
                existing_status = str(existing_row[1] or "").strip()
                downloaded_at_existing = str(existing_row[2] or "").strip() or None
                md5_existing = str(existing_row[3] or "").strip().lower() or None
                source_status = (
                    "downloaded"
                    if existing_status == "downloaded"
                    or downloaded_at_existing
                    or md5_existing
                    else "discovered"
                )
                conn.execute(
                    """
                    UPDATE report_sources
                    SET
                        source_domain=?,
                        report_name=?,
                        landing_page_url=?,
                        source_status=?,
                        source_page_url=?,
                        publisher_name=?,
                        discovered_at_utc=?,
                        discovered_on_page_number=?,
                        updated_at=strftime('%s','now')
                    WHERE id=?
                    """,
                    (
                        source_domain,
                        report_name,
                        landing_page_url,
                        source_status,
                        source_page_url,
                        publisher_name,
                        discovered_at_utc,
                        discovered_on_page_number,
                        record_id,
                    ),
                )
            else:
                cur = conn.execute(
                    """
                    INSERT INTO report_sources(
                        source_domain,
                        report_name,
                        landing_page_url,
                        normalized_landing_page_url,
                        source_status,
                        source_page_url,
                        publisher_name,
                        discovered_at_utc,
                        discovered_on_page_number
                    )
                    VALUES(?, ?, ?, ?, 'discovered', ?, ?, ?, ?)
                    """,
                    (
                        source_domain,
                        report_name,
                        landing_page_url,
                        normalized_landing_page_url,
                        source_page_url,
                        publisher_name,
                        discovered_at_utc,
                        discovered_on_page_number,
                    ),
                )
                record_id = int(cur.lastrowid or 0)
    except sqlite3.Error as exc:
        raise AppError(
            code="report_source_discovery_record_failed",
            message="Failed to record discovered report source",
            cause=exc,
            retryable=True,
            context={
                "db_path": db_path,
                "publisher_name": publisher_name,
                "landing_page_url": landing_page_url,
            },
        ) from exc

    response = ReportSourceDiscoveryRecordResponse(
        schema_version="1.0",
        record_id=record_id,
        publisher_name=publisher_name,
        source_domain=source_domain,
        report_name=report_name,
        landing_page_url=landing_page_url,
        source_page_url=source_page_url,
        discovered_at_utc=discovered_at_utc,
        discovered_on_page_number=discovered_on_page_number,
        created_new=created_new,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_discovery_record_complete",
            module=logger.name,
            fields={
                "record_id": response.record_id,
                "publisher_name": response.publisher_name,
                "source_domain": response.source_domain,
                "report_name": response.report_name,
                "landing_page_url": response.landing_page_url,
                "source_page_url": response.source_page_url,
                "discovered_at_utc": response.discovered_at_utc,
                "discovered_on_page_number": response.discovered_on_page_number,
                "created_new": response.created_new,
            },
        )
    )
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
                    discovery_test_status,
                    download_route_kind,
                    download_route_summary,
                    download_route_outcome,
                    download_route_last_downloaded_file_path,
                    download_route_last_final_page_url,
                    download_route_updated_at,
                    inventory_route_kind,
                    inventory_route_summary,
                    inventory_route_last_final_page_url,
                    inventory_route_updated_at,
                    inventory_snapshot_drive_file_id,
                    inventory_snapshot_drive_file_name,
                    inventory_snapshot_sha256,
                    inventory_snapshot_updated_at,
                    inventory_run_quality_json,
                    inventory_run_quality_updated_at
                FROM publishers
                """
            ).fetchall()
            preserved_by_insights_url: dict[
                str,
                tuple[
                    Optional[str],
                    Optional[str],
                    Optional[str],
                    Optional[str],
                    Optional[str],
                    Optional[str],
                    Optional[int],
                    Optional[str],
                    Optional[str],
                    Optional[str],
                    Optional[int],
                    Optional[str],
                    Optional[str],
                    Optional[str],
                    Optional[int],
                    Optional[str],
                    Optional[int],
                    Optional[str],
                    Optional[int],
                ],
            ] = {}
            preserved_by_name = dict(preserved_by_insights_url)
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
                    str(row[8] or "").strip() or None,
                    int(row[9]) if row[9] is not None else None,
                    str(row[10] or "").strip() or None,
                    str(row[11] or "").strip() or None,
                    str(row[12] or "").strip() or None,
                    int(row[13]) if row[13] is not None else None,
                    str(row[14] or "").strip() or None,
                    str(row[15] or "").strip() or None,
                    str(row[16] or "").strip() or None,
                    int(row[17]) if row[17] is not None else None,
                    str(row[18] or "").strip() or None,
                    int(row[19]) if row[19] is not None else None,
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
                        preserved = (
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                            None,
                        )
                    rows_with_routes.append((*row, *preserved))
                conn.executemany(
                    """
                    INSERT INTO publishers(
                        name,
                        homepage,
                        self_presentation,
                        insights_url,
                        google_folder,
                        discovery_test_status,
                        download_route_kind,
                        download_route_summary,
                        download_route_outcome,
                        download_route_last_downloaded_file_path,
                        download_route_last_final_page_url,
                        download_route_updated_at,
                        inventory_route_kind,
                        inventory_route_summary,
                        inventory_route_last_final_page_url,
                        inventory_route_updated_at,
                        inventory_snapshot_drive_file_id,
                        inventory_snapshot_drive_file_name,
                        inventory_snapshot_sha256,
                        inventory_snapshot_updated_at,
                        inventory_run_quality_json,
                        inventory_run_quality_updated_at
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def get_publisher_inventory_state(
    request: PublisherInventoryStateGetRequest,
    ctx: RunContext,
) -> Optional[PublisherInventoryStateResponse]:
    db_path = request.db_path.strip()
    normalized_url = request.normalized_url.strip()
    if not db_path:
        raise AppError(
            code="publisher_inventory_db_missing",
            message="Report metadata DB path is required for publisher inventory lookup",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_inventory_normalized_url_missing",
            message="normalized_url is required for publisher inventory lookup",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_state_get_start",
            module=logger.name,
            fields={"db_path": db_path, "normalized_url": normalized_url},
        )
    )
    with _metadata_conn(db_path) as conn:
        rows = conn.execute(
            """
            SELECT
                name,
                insights_url,
                google_folder,
                discovery_test_status,
                inventory_route_kind,
                inventory_route_summary,
                inventory_route_last_final_page_url,
                inventory_route_updated_at,
                inventory_snapshot_drive_file_id,
                inventory_snapshot_drive_file_name,
                inventory_snapshot_sha256,
                inventory_snapshot_updated_at,
                inventory_run_quality_json,
                inventory_run_quality_updated_at
            FROM publishers
            WHERE insights_url <> ''
            ORDER BY id ASC
            """
        ).fetchall()
    for row in rows:
        insights_url = str(row[1] or "").strip()
        if not insights_url or normalize_url(insights_url) != normalized_url:
            continue
        response = PublisherInventoryStateResponse(
            schema_version="1.0",
            publisher_name=str(row[0] or "").strip(),
            insights_url=insights_url,
            normalized_url=normalized_url,
            google_folder=str(row[2] or "").strip() or None,
            discovery_test_status=str(row[3] or "").strip() or None,
            inventory_route_kind=str(row[4] or "").strip() or None,
            inventory_route_summary=str(row[5] or "").strip() or None,
            inventory_route_last_final_page_url=str(row[6] or "").strip() or None,
            inventory_route_updated_at=_optional_int(row[7]),
            inventory_snapshot_drive_file_id=str(row[8] or "").strip() or None,
            inventory_snapshot_drive_file_name=str(row[9] or "").strip() or None,
            inventory_snapshot_sha256=str(row[10] or "").strip() or None,
            inventory_snapshot_updated_at=_optional_int(row[11]),
            inventory_run_quality_summary=_parse_inventory_run_quality_summary(
                str(row[12] or "").strip() or None
            ),
            inventory_run_quality_updated_at=_optional_int(row[13]),
        )
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_state_get_complete",
                module=logger.name,
                fields={
                    "db_path": db_path,
                    "normalized_url": normalized_url,
                    "found": True,
                    "publisher_name": response.publisher_name,
                    "has_google_folder": bool(response.google_folder),
                    "discovery_test_status": response.discovery_test_status or "",
                    "has_inventory_route": bool(response.inventory_route_summary),
                    "has_inventory_snapshot": bool(
                        response.inventory_snapshot_drive_file_id
                    ),
                    "has_inventory_run_quality": bool(
                        response.inventory_run_quality_summary
                    ),
                },
            )
        )
        return response
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_state_get_complete",
            module=logger.name,
            fields={"db_path": db_path, "normalized_url": normalized_url, "found": False},
        )
    )
    return None


def record_publisher_inventory_test_status(
    request: PublisherInventoryTestStatusRecordRequest,
    ctx: RunContext,
) -> None:
    db_path = request.db_path.strip()
    normalized_url = request.normalized_url.strip()
    status = request.status.strip()
    if not db_path:
        raise AppError(
            code="publisher_inventory_test_status_db_missing",
            message="Report metadata DB path is required for publisher discovery test-status recording",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_inventory_test_status_normalized_url_missing",
            message="normalized_url is required for publisher discovery test-status recording",
            retryable=False,
            severity="error",
        )
    if not status:
        raise AppError(
            code="publisher_inventory_test_status_missing",
            message="status is required for publisher discovery test-status recording",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_test_status_record_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "status": status,
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
                if normalize_url(str(row[1] or "").strip()) != normalized_url:
                    continue
                matched_id = int(row[0])
                break
            if matched_id is None:
                raise AppError(
                    code="publisher_inventory_test_status_not_found",
                    message="Publisher discovery test-status cannot be recorded because the publisher row was not found",
                    retryable=False,
                    severity="error",
                    context={"normalized_url": normalized_url},
                )
            conn.execute(
                """
                UPDATE publishers
                SET discovery_test_status=?
                WHERE id=?
                """,
                (
                    status,
                    matched_id,
                ),
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="publisher_inventory_test_status_record_failed",
            message="Failed to record publisher discovery test status",
            cause=exc,
            retryable=True,
            context={"db_path": db_path, "normalized_url": normalized_url, "status": status},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_test_status_record_complete",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "status": status,
            },
        )
    )


def record_publisher_inventory_run_quality(
    request: PublisherInventoryRunQualityRecordRequest,
    ctx: RunContext,
) -> None:
    db_path = request.db_path.strip()
    normalized_url = request.normalized_url.strip()
    summary_json = _serialize_inventory_run_quality_summary(request.summary)
    if not db_path:
        raise AppError(
            code="publisher_inventory_run_quality_db_missing",
            message="Report metadata DB path is required for publisher run-quality recording",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_inventory_run_quality_normalized_url_missing",
            message="normalized_url is required for publisher run-quality recording",
            retryable=False,
            severity="error",
        )
    if not summary_json:
        raise AppError(
            code="publisher_inventory_run_quality_missing",
            message="summary is required for publisher run-quality recording",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_run_quality_record_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "outcome": request.summary.outcome,
                "status": request.summary.status,
                "recommended_route_kind": request.summary.recommended_route_kind,
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
                if normalize_url(str(row[1] or "").strip()) != normalized_url:
                    continue
                matched_id = int(row[0])
                break
            if matched_id is None:
                raise AppError(
                    code="publisher_inventory_run_quality_not_found",
                    message="Publisher run-quality cannot be recorded because the publisher row was not found",
                    retryable=False,
                    severity="error",
                    context={"normalized_url": normalized_url},
                )
            conn.execute(
                """
                UPDATE publishers
                SET inventory_run_quality_json=?,
                    inventory_run_quality_updated_at=strftime('%s','now')
                WHERE id=?
                """,
                (
                    summary_json,
                    matched_id,
                ),
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="publisher_inventory_run_quality_record_failed",
            message="Failed to record publisher inventory run quality",
            cause=exc,
            retryable=True,
            context={"db_path": db_path, "normalized_url": normalized_url},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_run_quality_record_complete",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "outcome": request.summary.outcome,
                "status": request.summary.status,
            },
        )
    )


def record_publisher_inventory_state(
    request: PublisherInventoryStateRecordRequest,
    ctx: RunContext,
) -> None:
    db_path = request.db_path.strip()
    normalized_url = request.normalized_url.strip()
    source_url = request.source_url.strip()
    route_kind = request.route_kind.strip()
    route_summary = request.route_summary.strip()
    last_final_page_url = (
        request.last_final_page_url.strip()
        if request.last_final_page_url and request.last_final_page_url.strip()
        else None
    )
    snapshot_drive_file_id = (
        request.snapshot_drive_file_id.strip()
        if request.snapshot_drive_file_id and request.snapshot_drive_file_id.strip()
        else None
    )
    snapshot_drive_file_name = (
        request.snapshot_drive_file_name.strip()
        if request.snapshot_drive_file_name and request.snapshot_drive_file_name.strip()
        else None
    )
    snapshot_sha256 = (
        request.snapshot_sha256.strip()
        if request.snapshot_sha256 and request.snapshot_sha256.strip()
        else None
    )
    if not db_path:
        raise AppError(
            code="publisher_inventory_db_missing",
            message="Report metadata DB path is required for publisher inventory state recording",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_inventory_normalized_url_missing",
            message="normalized_url is required for publisher inventory state recording",
            retryable=False,
            severity="error",
        )
    if not source_url:
        raise AppError(
            code="publisher_inventory_source_url_missing",
            message="source_url is required for publisher inventory state recording",
            retryable=False,
            severity="error",
        )
    if not route_kind:
        raise AppError(
            code="publisher_inventory_route_kind_missing",
            message="route_kind is required for publisher inventory state recording",
            retryable=False,
            severity="error",
        )
    if not route_summary:
        raise AppError(
            code="publisher_inventory_route_summary_missing",
            message="route_summary is required for publisher inventory state recording",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_state_record_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "source_url": source_url,
                "route_kind": route_kind,
                "has_snapshot_drive_file_id": bool(snapshot_drive_file_id),
            },
        )
    )
    try:
        with _metadata_conn(db_path) as conn:
            matched = None
            rows = conn.execute(
                """
                SELECT
                    id,
                    insights_url,
                    inventory_snapshot_drive_file_id,
                    inventory_snapshot_drive_file_name,
                    inventory_snapshot_sha256
                FROM publishers
                WHERE insights_url <> ''
                ORDER BY id ASC
                """
            ).fetchall()
            for row in rows:
                if normalize_url(str(row[1] or "").strip()) != normalized_url:
                    continue
                matched = row
                source_url = str(row[1] or "").strip() or source_url
                if snapshot_drive_file_id is None:
                    snapshot_drive_file_id = str(row[2] or "").strip() or None
                if snapshot_drive_file_name is None:
                    snapshot_drive_file_name = str(row[3] or "").strip() or None
                if snapshot_sha256 is None:
                    snapshot_sha256 = str(row[4] or "").strip() or None
                break
            if matched is None:
                raise AppError(
                    code="publisher_inventory_state_not_found",
                    message="Publisher inventory state cannot be recorded because the publisher row was not found",
                    retryable=False,
                    severity="error",
                    context={"normalized_url": normalized_url, "source_url": source_url},
                )
            conn.execute(
                """
                UPDATE publishers
                SET
                    inventory_route_kind=?,
                    inventory_route_summary=?,
                    inventory_route_last_final_page_url=?,
                    inventory_route_updated_at=strftime('%s','now'),
                    inventory_snapshot_drive_file_id=?,
                    inventory_snapshot_drive_file_name=?,
                    inventory_snapshot_sha256=?,
                    inventory_snapshot_updated_at=strftime('%s','now')
                WHERE id=?
                """,
                (
                    route_kind,
                    route_summary,
                    last_final_page_url,
                    snapshot_drive_file_id,
                    snapshot_drive_file_name,
                    snapshot_sha256,
                    int(matched[0]),
                ),
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="publisher_inventory_state_record_failed",
            message="Failed to record publisher inventory state",
            cause=exc,
            retryable=True,
            context={"db_path": db_path, "source_url": source_url},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_state_record_complete",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "source_url": source_url,
                "route_kind": route_kind,
                "has_snapshot_drive_file_id": bool(snapshot_drive_file_id),
            },
        )
    )
