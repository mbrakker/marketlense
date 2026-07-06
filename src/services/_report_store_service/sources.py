from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from typing import Optional

from src.contracts.report_store import (
    ReportDownloadDriveFolderLookupRequest,
    ReportDownloadDriveFolderLookupResponse,
    ReportSourceDiscoveryRecordRequest,
    ReportSourceDiscoveryRecordResponse,
    ReportSourceQualityHistoryItem,
    ReportSourceQualityHistoryRequest,
    ReportSourceQualityHistoryResponse,
    ReportSourceRecordRequest,
    ReportSourceRecordResponse,
    ReportSourceLinkRequest,
    ReportSourceLinkResponse,
    ReportValueScoreRecordRequest,
    PublicPublisherReportValueAggregate,
    PublicPublisherReportValueAggregateRequest,
    PublicPublisherReportValueAggregateResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

from .common import _normalize_optional_url_key, _normalize_publisher_key, logger
from .connection import _metadata_conn


def link_report_to_source(
    request: ReportSourceLinkRequest, ctx: RunContext
) -> ReportSourceLinkResponse:
    db_path = request.db_path.strip()
    file_id = request.file_id.strip()
    source_md5 = request.source_md5.strip().lower()
    if not db_path:
        raise AppError(
            code="report_source_link_db_missing",
            message="Report metadata DB path is required for source lineage linking",
            retryable=False,
            severity="error",
        )
    if not file_id:
        raise AppError(
            code="report_source_link_file_id_missing",
            message="file_id is required for source lineage linking",
            retryable=False,
            severity="error",
        )
    if not source_md5:
        raise AppError(
            code="report_source_link_md5_missing",
            message="source_md5 is required for source lineage linking",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_link_start",
            module=logger.name,
            fields={"db_path": db_path, "file_id": file_id, "source_md5": source_md5},
        )
    )
    with _metadata_conn(db_path, ctx) as conn:
        source_exists = conn.execute(
            "SELECT 1 FROM report_sources WHERE md5=? LIMIT 1", (source_md5,)
        ).fetchone()
        if source_exists is None:
            raise AppError(
                code="report_source_link_source_missing",
                message="A matching report source is required before source lineage linking",
                retryable=False,
                severity="error",
                context={"file_id": file_id, "source_md5": source_md5},
            )
        row = conn.execute(
            "SELECT source_md5 FROM reports WHERE file_id=?", (file_id,)
        ).fetchone()
        if row is None:
            raise AppError(
                code="report_source_link_report_missing",
                message="Report does not exist for source lineage linking",
                retryable=False,
                severity="error",
                context={"file_id": file_id},
            )
        existing_md5 = str(row[0] or "").strip().lower()
        if existing_md5 and existing_md5 != source_md5:
            raise AppError(
                code="report_source_link_conflict",
                message="Report already has different source lineage",
                retryable=False,
                severity="error",
                context={
                    "file_id": file_id,
                    "existing_source_md5": existing_md5,
                    "source_md5": source_md5,
                },
            )
        linked = existing_md5 == ""
        if linked:
            conn.execute(
                "UPDATE reports SET source_md5=?, updated_at=strftime('%s','now') WHERE file_id=?",
                (source_md5, file_id),
            )
    response = ReportSourceLinkResponse(
        schema_version="1.0",
        file_id=file_id,
        source_md5=source_md5,
        linked=linked,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_link_complete",
            module=logger.name,
            fields={"file_id": file_id, "source_md5": source_md5, "linked": linked},
        )
    )
    return response


def list_public_publisher_report_value_aggregates(
    request: PublicPublisherReportValueAggregateRequest, ctx: RunContext
) -> PublicPublisherReportValueAggregateResponse:
    file_ids = sorted(
        {value.strip() for value in request.published_file_ids if value.strip()}
    )
    if not file_ids:
        return PublicPublisherReportValueAggregateResponse(
            schema_version="1.0", aggregates=[]
        )
    if not request.db_path.strip():
        raise AppError(
            code="public_publisher_report_value_db_missing",
            message="Report metadata DB path is required for public publisher report values",
            retryable=False,
            severity="error",
        )
    placeholders = ",".join("?" for _ in file_ids)
    with _metadata_conn(request.db_path, ctx) as conn:
        rows = conn.execute(
            f"""
            SELECT r.publisher, AVG(s.report_value_score), COUNT(*)
            FROM reports r JOIN report_sources s ON s.md5 = r.source_md5
            WHERE r.file_id IN ({placeholders}) AND s.report_value_score IS NOT NULL
              AND TRIM(COALESCE(r.publisher, '')) <> ''
            GROUP BY lower(trim(r.publisher)), trim(r.publisher)
            ORDER BY lower(trim(r.publisher))
            """,
            file_ids,
        ).fetchall()
    aggregates = []
    for publisher_name, score, sample_size in rows:
        average = round(float(score), 3)
        band = (
            "high"
            if average >= 78
            else "medium"
            if average >= 60
            else "low"
            if average >= 40
            else "weak"
        )
        aggregates.append(
            PublicPublisherReportValueAggregate(
                schema_version="1.0",
                publisher_name=str(publisher_name).strip(),
                average_score=average,
                value_band=band,
                sample_size=int(sample_size),
            )
        )
    return PublicPublisherReportValueAggregateResponse(
        schema_version="1.0", aggregates=aggregates
    )


def record_report_value_score(
    request: ReportValueScoreRecordRequest, ctx: RunContext
) -> None:
    db_path = request.db_path.strip()
    record_id = int(request.record_id)
    scored_at_utc = request.scored_at_utc.strip()
    if not db_path:
        raise AppError(
            code="report_value_score_db_missing",
            message="Report metadata DB path is required for report value-score persistence",
            retryable=False,
            severity="error",
        )
    if record_id <= 0:
        raise AppError(
            code="report_value_score_record_id_invalid",
            message="record_id must be positive for report value-score persistence",
            retryable=False,
            severity="error",
        )
    if not scored_at_utc:
        raise AppError(
            code="report_value_score_timestamp_missing",
            message="scored_at_utc is required for report value-score persistence",
            retryable=False,
            severity="error",
        )
    score_json = json.dumps(
        asdict(request.score),
        ensure_ascii=True,
        sort_keys=True,
        separators=(",", ":"),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_value_score_record_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "record_id": record_id,
                "overall_score": request.score.overall_score,
                "value_band": request.score.value_band,
                "scored_at_utc": scored_at_utc,
            },
        )
    )
    try:
        with _metadata_conn(db_path, ctx) as conn:
            cur = conn.execute(
                """
                UPDATE report_sources
                SET report_value_score=?,
                    report_value_band=?,
                    report_value_score_json=?,
                    report_value_scored_at_utc=?,
                    updated_at=strftime('%s','now')
                WHERE id=?
                """,
                (
                    float(request.score.overall_score),
                    request.score.value_band,
                    score_json,
                    scored_at_utc,
                    record_id,
                ),
            )
            if cur.rowcount == 0:
                raise AppError(
                    code="report_value_score_source_not_found",
                    message="Report source row was not found for value-score persistence",
                    retryable=False,
                    severity="error",
                    context={"db_path": db_path, "record_id": record_id},
                )
    except sqlite3.Error as exc:
        raise AppError(
            code="report_value_score_record_failed",
            message="Failed to persist report value score",
            cause=exc,
            retryable=True,
            context={"db_path": db_path, "record_id": record_id},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_value_score_record_complete",
            module=logger.name,
            fields={
                "record_id": record_id,
                "overall_score": request.score.overall_score,
                "value_band": request.score.value_band,
            },
        )
    )


def list_report_source_quality_history(
    request: ReportSourceQualityHistoryRequest, ctx: RunContext
) -> ReportSourceQualityHistoryResponse:
    db_path = request.db_path.strip()
    publisher_name = request.publisher_name.strip()
    limit = max(1, int(request.limit))
    if not db_path:
        raise AppError(
            code="report_source_quality_history_db_missing",
            message="Report metadata DB path is required for report source quality history",
            retryable=False,
            severity="error",
        )
    if not publisher_name:
        raise AppError(
            code="report_source_quality_history_publisher_missing",
            message="publisher_name is required for report source quality history",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_quality_history_list_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "publisher_name": publisher_name,
                "limit": limit,
            },
        )
    )
    try:
        with _metadata_conn(db_path, ctx) as conn:
            rows = conn.execute(
                """
                SELECT
                    publisher_name,
                    source_domain,
                    source_page_url,
                    landing_page_url,
                    report_name,
                    report_value_score,
                    report_value_band,
                    source_status,
                    discovered_at_utc,
                    downloaded_at_utc,
                    report_value_scored_at_utc
                FROM report_sources
                WHERE lower(trim(publisher_name)) = lower(trim(?))
                  AND report_value_score IS NOT NULL
                ORDER BY COALESCE(report_value_scored_at_utc, downloaded_at_utc, discovered_at_utc, '') DESC,
                         id DESC
                LIMIT ?
                """,
                (publisher_name, limit),
            ).fetchall()
    except sqlite3.Error as exc:
        raise AppError(
            code="report_source_quality_history_list_failed",
            message="Failed to list report source quality history",
            cause=exc,
            retryable=True,
            context={"db_path": db_path, "publisher_name": publisher_name},
        ) from exc
    items = [
        ReportSourceQualityHistoryItem(
            schema_version="1.0",
            publisher_name=str(row[0] or "").strip(),
            source_domain=str(row[1] or "").strip(),
            source_page_url=str(row[2] or "").strip(),
            landing_page_url=str(row[3] or "").strip(),
            report_name=str(row[4] or "").strip(),
            overall_score=float(row[5] or 0.0),
            value_band=str(row[6] or "").strip(),
            source_status=str(row[7] or "").strip(),
            discovered_at_utc=str(row[8] or "").strip(),
            downloaded_at_utc=str(row[9] or "").strip(),
            scored_at_utc=str(row[10] or "").strip(),
        )
        for row in rows
    ]
    response = ReportSourceQualityHistoryResponse(
        schema_version="1.0",
        publisher_name=publisher_name,
        items=items,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_source_quality_history_list_complete",
            module=logger.name,
            fields={
                "publisher_name": response.publisher_name,
                "item_count": len(response.items),
            },
        )
    )
    return response


def record_report_source(
    request: ReportSourceRecordRequest, ctx: RunContext
) -> ReportSourceRecordResponse:
    db_path = request.db_path.strip()
    source_domain = request.source_domain.strip()
    report_name = request.report_name.strip()
    landing_page_url = request.landing_page_url.strip()
    downloaded_at_utc = request.downloaded_at_utc.strip()
    md5 = request.md5.strip().lower()
    publisher_name = request.publisher_name.strip()
    source_page_url = request.source_page_url.strip() or landing_page_url
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
                "publisher_name": publisher_name,
                "source_page_url": source_page_url,
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
                        source_page_url=COALESCE(NULLIF(?, ''), NULLIF(source_page_url, ''), ?),
                        publisher_name=COALESCE(NULLIF(?, ''), NULLIF(publisher_name, '')),
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
                        request.source_page_url.strip(),
                        landing_page_url,
                        publisher_name,
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
                        source_page_url,
                        publisher_name or None,
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
                "publisher_name": publisher_name,
                "source_page_url": source_page_url,
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
    publisher_name = str(request.publisher_name or "").strip()
    if not db_path:
        raise AppError(
            code="report_download_drive_folder_db_missing",
            message="Report metadata DB path is required for Drive folder lookup",
            retryable=False,
            severity="error",
        )
    if not normalized_landing_page_url and not publisher_insights_url and not publisher_name:
        raise AppError(
            code="report_download_drive_folder_lookup_key_missing",
            message="A normalized landing-page URL, publisher insights URL, or publisher name is required for Drive folder lookup",
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
                "has_publisher_name": bool(publisher_name),
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
        if publisher_name:
            row = conn.execute(
                """
                SELECT name, google_folder
                FROM publishers
                WHERE lower(trim(name)) = lower(trim(?))
                ORDER BY id ASC
                LIMIT 1
                """,
                (publisher_name,),
            ).fetchone()
            if row is not None:
                response = ReportDownloadDriveFolderLookupResponse(
                    schema_version="1.0",
                    publisher_name=str(row[0] or "").strip(),
                    google_folder=str(row[1] or "").strip(),
                    resolution_source="publisher_name",
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
            normalized_publisher_key = _normalize_publisher_key(publisher_name)
            if normalized_publisher_key:
                rows = conn.execute(
                    """
                    SELECT name, google_folder
                    FROM publishers
                    WHERE name IS NOT NULL
                      AND trim(name) <> ''
                    ORDER BY id ASC
                    """
                ).fetchall()
                for candidate_row in rows:
                    if (
                        _normalize_publisher_key(str(candidate_row[0] or ""))
                        != normalized_publisher_key
                    ):
                        continue
                    response = ReportDownloadDriveFolderLookupResponse(
                        schema_version="1.0",
                        publisher_name=str(candidate_row[0] or "").strip(),
                        google_folder=str(candidate_row[1] or "").strip(),
                        resolution_source="publisher_name_normalized",
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
        if publisher_name:
            response = ReportDownloadDriveFolderLookupResponse(
                schema_version="1.0",
                publisher_name=publisher_name.strip(),
                google_folder="",
                resolution_source="request_publisher_name",
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
                "has_publisher_name": bool(publisher_name),
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
