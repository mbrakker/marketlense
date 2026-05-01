from __future__ import annotations

import sqlite3
from typing import Optional

from src.contracts.report_store import (
    ReportDownloadDriveFolderLookupRequest,
    ReportDownloadDriveFolderLookupResponse,
    ReportSourceDiscoveryRecordRequest,
    ReportSourceDiscoveryRecordResponse,
    ReportSourceRecordRequest,
    ReportSourceRecordResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

from .common import logger, _normalize_optional_url_key
from .connection import _metadata_conn

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
    logger.info(
        log_event(
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
        )
    )
    try:
        with _metadata_conn(db_path, ctx) as conn:
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
    logger.info(
        log_event(
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
        )
    )
    return response


def get_report_download_drive_folder(
    request: ReportDownloadDriveFolderLookupRequest,
    ctx: RunContext,
) -> Optional[ReportDownloadDriveFolderLookupResponse]:
    db_path = request.db_path.strip()
    normalized_landing_page_url = request.normalized_landing_page_url.strip()
    publisher_insights_url = (
        normalize_url(request.publisher_insights_url.strip())
        if request.publisher_insights_url and request.publisher_insights_url.strip()
        else None
    )
    if not db_path:
        raise AppError(
            code="report_download_drive_folder_db_missing",
            message="Report metadata DB path is required for Drive folder lookup",
            retryable=False,
            severity="error",
        )
    if not normalized_landing_page_url and not publisher_insights_url:
        raise AppError(
            code="report_download_drive_folder_lookup_key_missing",
            message="A normalized landing-page URL or publisher insights URL is required for Drive folder lookup",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_download_drive_folder_lookup_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_landing_page_url": normalized_landing_page_url,
                "publisher_insights_url": publisher_insights_url or "",
            },
        )
    )
    with _metadata_conn(db_path, ctx) as conn:
        if publisher_insights_url:
            row = conn.execute(
                """
                SELECT name, insights_url, google_folder
                FROM publishers
                WHERE normalized_insights_url=?
                  AND google_folder IS NOT NULL
                  AND trim(google_folder) <> ''
                ORDER BY id ASC
                LIMIT 1
                """,
                (publisher_insights_url,),
            ).fetchone()
            if row is not None:
                response = ReportDownloadDriveFolderLookupResponse(
                    schema_version="1.0",
                    publisher_name=str(row[0] or "").strip(),
                    google_folder=str(row[2] or "").strip(),
                    resolution_source="publisher_insights_url",
                )
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="report_download_drive_folder_lookup_complete",
                        module=logger.name,
                        fields={
                            "found": True,
                            "publisher_name": response.publisher_name,
                            "resolution_source": response.resolution_source,
                        },
                    )
                )
                return response
        if normalized_landing_page_url:
            row = conn.execute(
                """
                SELECT
                    rs.publisher_name,
                    p.google_folder
                FROM report_sources rs
                JOIN publishers p ON lower(trim(p.name)) = lower(trim(rs.publisher_name))
                WHERE rs.normalized_landing_page_url=?
                  AND rs.publisher_name IS NOT NULL
                  AND trim(rs.publisher_name) <> ''
                  AND p.google_folder IS NOT NULL
                  AND trim(p.google_folder) <> ''
                ORDER BY rs.updated_at DESC, rs.id DESC
                LIMIT 1
                """,
                (normalized_landing_page_url,),
            ).fetchone()
            if row is not None:
                response = ReportDownloadDriveFolderLookupResponse(
                    schema_version="1.0",
                    publisher_name=str(row[0] or "").strip(),
                    google_folder=str(row[1] or "").strip(),
                    resolution_source="report_source_publisher",
                )
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="report_download_drive_folder_lookup_complete",
                        module=logger.name,
                        fields={
                            "found": True,
                            "publisher_name": response.publisher_name,
                            "resolution_source": response.resolution_source,
                        },
                    )
                )
                return response
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_download_drive_folder_lookup_complete",
            module=logger.name,
            fields={
                "found": False,
                "normalized_landing_page_url": normalized_landing_page_url,
                "publisher_insights_url": publisher_insights_url or "",
            },
        )
    )
    return None


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
    if not source_domain:
        raise AppError(
            code="report_source_discovery_domain_missing",
            message="source_domain is required for discovered source recording",
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
        with _metadata_conn(db_path, ctx) as conn:
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
