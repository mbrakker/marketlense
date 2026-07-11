from __future__ import annotations

import json
import sqlite3
from dataclasses import replace
from typing import List, Optional

from src.contracts.report_store import (
    ReportMetadataDbAccessRequest,
    ReportMetadataDbAccessResponse,
    ReportMetadataGetRequest,
    ReportMetadataGetResponse,
    ReportMetadataListRequest,
    ReportMetadataListResponse,
    ReportSourceIdentityResolveRequest,
    ReportSourceIdentityResolveResponse,
    ReportMetadataUpsertRequest,
)
from src.contracts.run_context import RunContext
from src.utils.coercion import clean_string_list
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.time_period import normalize_time_period
from src.services._sqlite_common import table_exists as _table_exists

from .common import (
    ACCESS_TIMEOUT_SECONDS,
    logger,
    _clean_metadata,
    _configure_sqlite_connection,
    _is_lock_error,
)
from .connection import _metadata_conn


def _report_source_url_from_store(
    conn: sqlite3.Connection,
    *,
    report_title: str,
    publisher: Optional[str],
    md5: Optional[str],
) -> Optional[str]:
    if not _table_exists(conn, "report_sources"):
        return None
    normalized_title = report_title.strip().casefold()
    normalized_publisher = str(publisher or "").strip().casefold()
    if normalized_title:
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
        if row and str(row[0] or "").strip():
            return str(row[0]).strip()
    clean_md5 = str(md5 or "").strip()
    if not clean_md5:
        return None
    row = conn.execute(
        """
        SELECT landing_page_url
        FROM report_sources
        WHERE md5=? AND COALESCE(landing_page_url, '') <> ''
        ORDER BY downloaded_at_utc DESC, updated_at DESC, id DESC
        LIMIT 1
        """,
        (clean_md5,),
    ).fetchone()
    return str(row[0]).strip() if row and str(row[0] or "").strip() else None


def _report_source_publisher_from_store(
    conn: sqlite3.Connection,
    *,
    report_title: str,
    md5: Optional[str],
) -> Optional[str]:
    if not _table_exists(conn, "report_sources"):
        return None
    normalized_title = report_title.strip().casefold()
    clean_md5 = str(md5 or "").strip()
    row = conn.execute(
        """
        SELECT publisher_name
        FROM report_sources
        WHERE COALESCE(publisher_name, '') <> ''
          AND (
            (? <> '' AND lower(report_name)=?)
            OR (? <> '' AND md5=?)
          )
        ORDER BY downloaded_at_utc DESC, updated_at DESC, id DESC
        LIMIT 1
        """,
        (normalized_title, normalized_title, clean_md5, clean_md5),
    ).fetchone()
    return str(row[0]).strip() if row and str(row[0] or "").strip() else None


def _report_source_identity_row(
    conn: sqlite3.Connection,
    *,
    report_title: str,
    publisher: Optional[str],
    md5: Optional[str],
) -> tuple[Optional[sqlite3.Row], str]:
    if not _table_exists(conn, "report_sources"):
        return None, "fallback"
    clean_md5 = str(md5 or "").strip()
    if clean_md5:
        row = conn.execute(
            """
            SELECT report_name, publisher_name, landing_page_url
            FROM report_sources
            WHERE md5=?
            ORDER BY downloaded_at_utc DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            (clean_md5,),
        ).fetchone()
        if row:
            return row, "md5"
    normalized_title = report_title.strip().casefold()
    normalized_publisher = str(publisher or "").strip().casefold()
    if normalized_title:
        row = conn.execute(
            """
            SELECT report_name, publisher_name, landing_page_url
            FROM report_sources
            WHERE lower(report_name)=?
              AND (?='' OR lower(COALESCE(publisher_name, ''))=?)
            ORDER BY downloaded_at_utc DESC, updated_at DESC, id DESC
            LIMIT 1
            """,
            (normalized_title, normalized_publisher, normalized_publisher),
        ).fetchone()
        if row:
            return row, "title"
    return None, "fallback"


def resolve_report_source_identity(
    request: ReportSourceIdentityResolveRequest, ctx: RunContext
) -> ReportSourceIdentityResolveResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_identity_resolve_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "report_title": request.report_title,
                "has_md5": bool(str(request.md5 or "").strip()),
            },
        )
    )
    if not request.db_path or not request.db_path.strip():
        raise AppError(
            code="metadata_db_missing",
            message="Report metadata DB path is required",
            retryable=False,
            severity="error",
        )
    with _metadata_conn(request.db_path, ctx) as conn:
        row, source = _report_source_identity_row(
            conn,
            report_title=request.report_title,
            publisher=request.publisher_name,
            md5=request.md5,
        )
    if row is None:
        response = ReportSourceIdentityResolveResponse(
            schema_version="1.0",
            publisher_name=str(request.publisher_name or "").strip(),
            report_name=str(request.report_title or "").strip(),
            source_url="",
            resolution_source=source,
        )
    else:
        response = ReportSourceIdentityResolveResponse(
            schema_version="1.0",
            report_name=str(row[0] or "").strip()
            or str(request.report_title or "").strip(),
            publisher_name=str(row[1] or "").strip()
            or str(request.publisher_name or "").strip(),
            source_url=str(row[2] or "").strip(),
            resolution_source=source,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_identity_resolve_complete",
            module=logger.name,
            fields={
                "publisher_name": response.publisher_name,
                "report_name": response.report_name,
                "has_source_url": bool(response.source_url),
                "resolution_source": response.resolution_source,
            },
        )
    )
    return response


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
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_metadata_taxonomy_parse_failed",
                module=logger.name,
                fields={"file_id": file_id},
            )
        )
    try:
        parsed_cats = json.loads(categories_json)
        if isinstance(parsed_cats, list):
            categories = clean_string_list([str(item) for item in parsed_cats])
    except json.JSONDecodeError:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_metadata_categories_parse_failed",
                module=logger.name,
                fields={"file_id": file_id},
            )
        )
    try:
        parsed_meta = json.loads(metadata_json)
        if isinstance(parsed_meta, dict):
            pdf_metadata = _clean_metadata({str(k): v for k, v in parsed_meta.items()})
    except json.JSONDecodeError:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_metadata_pdf_metadata_parse_failed",
                module=logger.name,
                fields={"file_id": file_id},
            )
        )
    try:
        if page_count_raw is not None:
            page_int = int(page_count_raw)
            page_count = page_int if page_int >= 0 else None
    except (TypeError, ValueError):
        page_count = None
    try:
        if contents_page_raw is not None:
            contents_int = int(contents_page_raw)
            contents_page_number = contents_int if contents_int >= 0 else 0
    except (TypeError, ValueError):
        contents_page_number = 0
    try:
        parsed_packs = json.loads(evidence_packs_json)
        if isinstance(parsed_packs, dict):
            evidence_pack_paths = {
                str(k): str(v)
                for k, v in parsed_packs.items()
                if str(k).strip() and str(v).strip()
            }
    except json.JSONDecodeError:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_metadata_evidence_packs_parse_failed",
                module=logger.name,
                fields={"file_id": file_id},
            )
        )
    return ReportMetadataGetResponse(
        schema_version="1.1",
        file_id=str(file_id),
        file_name=str(row[1] or "").strip() or None,
        title=str(row[2] or ""),
        publisher=str(row[3] or "") or None,
        taxonomy=taxonomy,
        categories=categories,
        region=str(row[6] or "") or None,
        time_period=time_period,
        source_url=str(row[8] or "") or None,
        html_path=str(row[9] or "") or None,
        md5=str(row[10] or "") or None,
        page_count=page_count,
        contents_page_number=contents_page_number,
        pdf_metadata=pdf_metadata,
        created_at=int(row[17]),
        updated_at=int(row[18]),
        analysis_mode=str(analysis_mode),
        vector_store_id=vector_store_id,
        evidence_pack_paths=evidence_pack_paths,
    )


def check_report_db_access(
    request: ReportMetadataDbAccessRequest, ctx: RunContext
) -> ReportMetadataDbAccessResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_db_access_start",
            module=logger.name,
            fields={
                "db_path": request.db_path,
                "timeout_seconds": request.timeout_seconds,
            },
        )
    )
    if not request.db_path or not request.db_path.strip():
        raise AppError(
            code="metadata_db_missing",
            message="Report metadata DB path is required",
            retryable=False,
            severity="error",
        )
    timeout = (
        request.timeout_seconds
        if request.timeout_seconds >= 0
        else ACCESS_TIMEOUT_SECONDS
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_db_access_config",
            module=logger.name,
            fields={"timeout_seconds": timeout},
        )
    )
    try:
        conn = sqlite3.connect(request.db_path, timeout=timeout)
    except sqlite3.Error as exc:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_db_access_connect_failed",
                module=logger.name,
                fields={"db_path": request.db_path, "error": str(exc)},
            )
        )
        raise AppError(
            code="metadata_db_unavailable",
            message="Failed to open report metadata DB",
            cause=exc,
            retryable=True,
            context={"db_path": request.db_path},
        ) from exc
    try:
        _configure_sqlite_connection(conn, busy_timeout_seconds=timeout)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_db_access_probe",
                module=logger.name,
                fields={"db_path": request.db_path},
            )
        )
        conn.execute("PRAGMA schema_version")
    except sqlite3.OperationalError as exc:
        if _is_lock_error(exc):
            message = str(exc)
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="report_db_access_locked",
                    module=logger.name,
                    fields={"db_path": request.db_path, "error": message},
                )
            )
            response = ReportMetadataDbAccessResponse(
                schema_version="1.0",
                db_path=request.db_path,
                accessible=False,
                locked=True,
                message=message,
            )
            logger.info(
                log_event(
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
                )
            )
            return response
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_db_access_failed",
                module=logger.name,
                fields={"db_path": request.db_path, "error": str(exc)},
            )
        )
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
    logger.info(
        log_event(
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
        )
    )
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
    file_name = (
        request.file_name.strip()
        if request.file_name and request.file_name.strip()
        else None
    )
    publisher = (
        request.publisher.strip()
        if request.publisher and request.publisher.strip()
        else None
    )
    source_url = (
        request.source_url.strip()
        if request.source_url and request.source_url.strip()
        else None
    )
    html_path = (
        request.html_path.strip()
        if request.html_path and request.html_path.strip()
        else None
    )
    md5 = request.md5.strip() if request.md5 and request.md5.strip() else None
    page_count = (
        request.page_count
        if isinstance(request.page_count, int) and request.page_count >= 0
        else None
    )
    contents_page = (
        request.contents_page_number
        if isinstance(request.contents_page_number, int)
        and request.contents_page_number >= 0
        else 0
    )
    taxonomy = clean_string_list(request.taxonomy)
    taxonomy_json = json.dumps(taxonomy, ensure_ascii=True)
    categories = clean_string_list(request.categories)
    categories_json = json.dumps(categories, ensure_ascii=True)
    region = (
        request.region.strip() if request.region and request.region.strip() else None
    )
    raw_time_period = (
        request.time_period.strip()
        if request.time_period and request.time_period.strip()
        else None
    )
    time_period = normalize_time_period(raw_time_period)
    metadata_clean = _clean_metadata(request.pdf_metadata)
    metadata_json = json.dumps(metadata_clean, ensure_ascii=True)
    analysis_mode = (
        request.analysis_mode.strip() if request.analysis_mode else "vector_store"
    )
    vector_store_id = (
        request.vector_store_id.strip() if request.vector_store_id else None
    )
    evidence_packs = request.evidence_pack_paths or {}
    evidence_packs_json = json.dumps(evidence_packs, ensure_ascii=False)

    logger.info(
        log_event(
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
        )
    )
    with _metadata_conn(request.db_path, ctx) as conn:
        resolved_publisher = publisher or _report_source_publisher_from_store(
            conn,
            report_title=title,
            md5=md5,
        )
        resolved_source_url = source_url or _report_source_url_from_store(
            conn,
            report_title=title,
            publisher=resolved_publisher,
            md5=md5,
        )
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
                resolved_publisher,
                taxonomy_json,
                categories_json,
                region,
                time_period,
                resolved_source_url,
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
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_upsert_complete",
            module=logger.name,
            fields={"file_id": request.file_id},
        )
    )


def get_metadata(
    request: ReportMetadataGetRequest, ctx: RunContext
) -> Optional[ReportMetadataGetResponse]:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_get_start",
            module=logger.name,
            fields={"file_id": request.file_id, "db_path": request.db_path},
        )
    )
    with _metadata_conn(request.db_path, ctx) as conn:
        cur = conn.execute(
            """
            SELECT file_id, file_name, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, analysis_mode, vector_store_id, evidence_packs_json, created_at, updated_at
            FROM reports
            WHERE file_id=?
            """,
            (request.file_id,),
        )
        row = cur.fetchone()
        fallback_source_url = None
        fallback_publisher = None
        if row and not str(row[3] or "").strip():
            fallback_publisher = _report_source_publisher_from_store(
                conn,
                report_title=str(row[2] or ""),
                md5=str(row[10] or "") or None,
            )
        if row and not str(row[8] or "").strip():
            fallback_source_url = _report_source_url_from_store(
                conn,
                report_title=str(row[2] or ""),
                publisher=str(row[3] or "") or fallback_publisher,
                md5=str(row[10] or "") or None,
            )

    if not row:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_metadata_get_complete",
                module=logger.name,
                fields={"file_id": request.file_id, "found": False},
            )
        )
        return None

    response = _row_to_metadata_response(row, ctx)
    if fallback_source_url or fallback_publisher:
        response = replace(
            response,
            source_url=fallback_source_url or response.source_url,
            publisher=fallback_publisher or response.publisher,
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_get_complete",
            module=logger.name,
            fields={"file_id": request.file_id, "found": True},
        )
    )
    return response


def list_metadata(
    request: ReportMetadataListRequest, ctx: RunContext
) -> ReportMetadataListResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_list_start",
            module=logger.name,
            fields={"db_path": request.db_path},
        )
    )
    rows: List[ReportMetadataGetResponse] = []
    with _metadata_conn(request.db_path, ctx) as conn:
        cur = conn.execute(
            """
            SELECT file_id, file_name, title, publisher, taxonomy_json, categories_json, region, time_period, source_url, html_path, md5, page_count, contents_page, pdf_metadata_json, analysis_mode, vector_store_id, evidence_packs_json, created_at, updated_at
            FROM reports
            ORDER BY created_at ASC
            """
        )
        for row in cur.fetchall():
            rows.append(_row_to_metadata_response(row, ctx))
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_metadata_list_complete",
            module=logger.name,
            fields={"db_path": request.db_path, "count": len(rows)},
        )
    )
    return ReportMetadataListResponse(schema_version="1.1", records=rows)
