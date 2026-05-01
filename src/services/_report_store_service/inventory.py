from __future__ import annotations

import sqlite3
from typing import Optional

from src.contracts.report_store import (
    PublisherInventoryRecoveryCacheGetRequest,
    PublisherInventoryRecoveryCacheRecordRequest,
    PublisherInventoryRunQualityRecordRequest,
    PublisherInventoryStateGetRequest,
    PublisherInventoryStateRecordRequest,
    PublisherInventoryStateResponse,
    PublisherInventoryTestStatusRecordRequest,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

from .common import logger, _optional_int
from .connection import _metadata_conn
from .route_policy import (
    _publisher_inventory_route_policy_rows,
    _publisher_inventory_route_policy_signals,
    _url_host,
)
from .serialization import (
    _parse_inventory_route_trace,
    _parse_inventory_run_quality_summary,
    _parse_inventory_scenario_summary,
    _serialize_dataclass_payload,
    _serialize_inventory_run_quality_summary,
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
    with _metadata_conn(db_path, ctx) as conn:
        row = conn.execute(
            """
            SELECT
                name,
                insights_url,
                google_folder,
                discovery_test_status,
                inventory_route_kind,
                inventory_route_summary,
                inventory_route_trace_json,
                inventory_scenario_summary_json,
                inventory_route_last_final_page_url,
                inventory_route_updated_at,
                inventory_snapshot_drive_file_id,
                inventory_snapshot_drive_file_name,
                inventory_snapshot_sha256,
                inventory_snapshot_updated_at,
                inventory_run_quality_json,
                inventory_run_quality_updated_at
            FROM publishers
            WHERE normalized_insights_url=?
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_url,),
        ).fetchone()
        inventory_route_policy = _publisher_inventory_route_policy_signals(
            _publisher_inventory_route_policy_rows(
                conn=conn,
                normalized_url=normalized_url,
            )
        )
    if row is not None:
        insights_url = str(row[1] or "").strip()
        response = PublisherInventoryStateResponse(
            schema_version="1.0",
            publisher_name=str(row[0] or "").strip(),
            insights_url=insights_url,
            normalized_url=normalized_url,
            google_folder=str(row[2] or "").strip() or None,
            discovery_test_status=str(row[3] or "").strip() or None,
            inventory_route_kind=str(row[4] or "").strip() or None,
            inventory_route_summary=str(row[5] or "").strip() or None,
            inventory_route_trace=_parse_inventory_route_trace(
                str(row[6] or "").strip() or None
            ),
            inventory_scenario_summary=_parse_inventory_scenario_summary(
                str(row[7] or "").strip() or None
            ),
            inventory_route_last_final_page_url=str(row[8] or "").strip() or None,
            inventory_route_updated_at=_optional_int(row[9]),
            inventory_snapshot_drive_file_id=str(row[10] or "").strip() or None,
            inventory_snapshot_drive_file_name=str(row[11] or "").strip() or None,
            inventory_snapshot_sha256=str(row[12] or "").strip() or None,
            inventory_snapshot_updated_at=_optional_int(row[13]),
            inventory_run_quality_summary=_parse_inventory_run_quality_summary(
                str(row[14] or "").strip() or None
            ),
            inventory_run_quality_updated_at=_optional_int(row[15]),
            inventory_route_policy=inventory_route_policy,
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
                    "has_inventory_route_trace": bool(response.inventory_route_trace),
                    "has_inventory_scenario_summary": bool(
                        response.inventory_scenario_summary
                    ),
                    "has_inventory_snapshot": bool(
                        response.inventory_snapshot_drive_file_id
                    ),
                    "has_inventory_run_quality": bool(
                        response.inventory_run_quality_summary
                    ),
                    "inventory_route_policy_order": [
                        signal.route_kind for signal in inventory_route_policy
                    ],
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
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "found": False,
            },
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
            message="Report metadata DB path is required for publisher inventory test-status recording",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_inventory_test_status_normalized_url_missing",
            message="normalized_url is required for publisher inventory test-status recording",
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
        with _metadata_conn(db_path, ctx) as conn:
            row = conn.execute(
                """
                SELECT id
                FROM publishers
                WHERE normalized_insights_url=?
                ORDER BY id ASC
                LIMIT 1
                """,
                (normalized_url,),
            ).fetchone()
            matched_id = int(row[0]) if row is not None else None
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
            context={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "status": status,
            },
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
        with _metadata_conn(db_path, ctx) as conn:
            row = conn.execute(
                """
                SELECT id
                FROM publishers
                WHERE normalized_insights_url=?
                ORDER BY id ASC
                LIMIT 1
                """,
                (normalized_url,),
            ).fetchone()
            matched_id = int(row[0]) if row is not None else None
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
            conn.execute(
                """
                INSERT INTO publisher_inventory_route_history(
                    normalized_url,
                    source_host,
                    route_kind,
                    outcome,
                    status,
                    quality_band,
                    recommended_route_kind,
                    used_memory_route,
                    page_count,
                    raw_candidate_count,
                    current_report_count,
                    raw_new_report_count,
                    screened_new_report_count,
                    qualified_new_report_count,
                    snapshot_changed,
                    requires_review,
                    scenario_class,
                    created_at,
                    updated_at
                )
                VALUES(
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    strftime('%s','now'),
                    strftime('%s','now')
                )
                """,
                (
                    normalized_url,
                    _url_host(normalized_url),
                    request.summary.route_kind,
                    request.summary.outcome,
                    request.summary.status,
                    request.summary.quality_band,
                    request.summary.recommended_route_kind,
                    1 if request.summary.used_memory_route else 0,
                    request.summary.page_count,
                    request.summary.raw_candidate_count,
                    request.summary.current_report_count,
                    request.summary.raw_new_report_count,
                    request.summary.screened_new_report_count,
                    request.summary.qualified_new_report_count,
                    1 if request.summary.snapshot_changed else 0,
                    1 if request.summary.requires_review else 0,
                    request.summary.scenario_class,
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


def get_publisher_inventory_recovery_cache_record(
    request: PublisherInventoryRecoveryCacheGetRequest,
    ctx: RunContext,
):
    from src.contracts.publisher_inventory import PublisherInventoryRecoveryRecord

    db_path = request.db_path.strip()
    normalized_url = request.normalized_url.strip()
    canonical_url = request.canonical_url.strip()
    if not db_path:
        raise AppError(
            code="publisher_inventory_recovery_cache_db_missing",
            message="Report metadata DB path is required for recovery-cache lookup",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_inventory_recovery_cache_normalized_url_missing",
            message="normalized_url is required for recovery-cache lookup",
            retryable=False,
            severity="error",
        )
    if not canonical_url:
        raise AppError(
            code="publisher_inventory_recovery_cache_canonical_url_missing",
            message="canonical_url is required for recovery-cache lookup",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_recovery_cache_get_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "canonical_url": canonical_url,
            },
        )
    )
    with _metadata_conn(db_path, ctx) as conn:
        row = conn.execute(
            """
            SELECT
                source_surface_class,
                verification_class,
                recovery_action,
                last_outcome,
                last_http_status,
                last_error_marker,
                updated_at_utc
            FROM publisher_inventory_candidate_recovery_cache
            WHERE normalized_url=? AND canonical_url=?
            """,
            (normalized_url, canonical_url),
        ).fetchone()
    if row is None:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="publisher_inventory_recovery_cache_get_complete",
                module=logger.name,
                fields={
                    "db_path": db_path,
                    "normalized_url": normalized_url,
                    "canonical_url": canonical_url,
                    "found": False,
                },
            )
        )
        return None
    response = PublisherInventoryRecoveryRecord(
        schema_version="1.0",
        normalized_url=normalized_url,
        canonical_url=canonical_url,
        source_surface_class=str(row[0] or "").strip() or "unknown",
        verification_class=str(row[1] or "").strip() or "verified",
        recovery_action=str(row[2] or "").strip(),
        last_outcome=str(row[3] or "").strip(),
        last_http_status=_optional_int(row[4]),
        last_error_marker=str(row[5] or "").strip() or None,
        updated_at_utc=str(row[6] or "").strip(),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_recovery_cache_get_complete",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "canonical_url": canonical_url,
                "found": True,
                "verification_class": response.verification_class,
                "last_outcome": response.last_outcome,
            },
        )
    )
    return response


def record_publisher_inventory_recovery_cache_record(
    request: PublisherInventoryRecoveryCacheRecordRequest,
    ctx: RunContext,
) -> None:
    db_path = request.db_path.strip()
    record = request.record
    normalized_url = record.normalized_url.strip()
    canonical_url = record.canonical_url.strip()
    if not db_path:
        raise AppError(
            code="publisher_inventory_recovery_cache_db_missing",
            message="Report metadata DB path is required for recovery-cache recording",
            retryable=False,
            severity="error",
        )
    if not normalized_url:
        raise AppError(
            code="publisher_inventory_recovery_cache_normalized_url_missing",
            message="normalized_url is required for recovery-cache recording",
            retryable=False,
            severity="error",
        )
    if not canonical_url:
        raise AppError(
            code="publisher_inventory_recovery_cache_canonical_url_missing",
            message="canonical_url is required for recovery-cache recording",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_recovery_cache_record_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "canonical_url": canonical_url,
                "verification_class": record.verification_class,
                "recovery_action": record.recovery_action,
                "last_outcome": record.last_outcome,
            },
        )
    )
    try:
        with _metadata_conn(db_path, ctx) as conn:
            conn.execute(
                """
                INSERT INTO publisher_inventory_candidate_recovery_cache(
                    normalized_url,
                    canonical_url,
                    source_surface_class,
                    verification_class,
                    recovery_action,
                    last_outcome,
                    last_http_status,
                    last_error_marker,
                    updated_at_utc,
                    created_at,
                    updated_at
                )
                VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, strftime('%s','now'), strftime('%s','now'))
                ON CONFLICT(normalized_url, canonical_url) DO UPDATE SET
                    source_surface_class=excluded.source_surface_class,
                    verification_class=excluded.verification_class,
                    recovery_action=excluded.recovery_action,
                    last_outcome=excluded.last_outcome,
                    last_http_status=excluded.last_http_status,
                    last_error_marker=excluded.last_error_marker,
                    updated_at_utc=excluded.updated_at_utc,
                    updated_at=strftime('%s','now')
                """,
                (
                    normalized_url,
                    canonical_url,
                    record.source_surface_class.strip() or "unknown",
                    record.verification_class.strip() or "verified",
                    record.recovery_action.strip(),
                    record.last_outcome.strip(),
                    record.last_http_status,
                    record.last_error_marker.strip()
                    if record.last_error_marker and record.last_error_marker.strip()
                    else None,
                    record.updated_at_utc.strip(),
                ),
            )
    except sqlite3.Error as exc:
        raise AppError(
            code="publisher_inventory_recovery_cache_record_failed",
            message="Failed to record publisher inventory recovery cache state",
            cause=exc,
            retryable=True,
            context={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "canonical_url": canonical_url,
            },
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_inventory_recovery_cache_record_complete",
            module=logger.name,
            fields={
                "db_path": db_path,
                "normalized_url": normalized_url,
                "canonical_url": canonical_url,
                "verification_class": record.verification_class,
                "last_outcome": record.last_outcome,
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
    route_trace_json = _serialize_dataclass_payload(request.route_trace)
    scenario_summary_json = _serialize_dataclass_payload(request.scenario_summary)
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
                "has_route_trace": bool(request.route_trace),
                "has_scenario_summary": bool(request.scenario_summary),
                "has_snapshot_drive_file_id": bool(snapshot_drive_file_id),
            },
        )
    )
    try:
        with _metadata_conn(db_path, ctx) as conn:
            matched = conn.execute(
                """
                SELECT
                    id,
                    insights_url,
                    inventory_snapshot_drive_file_id,
                    inventory_snapshot_drive_file_name,
                    inventory_snapshot_sha256,
                    inventory_route_trace_json,
                    inventory_scenario_summary_json
                FROM publishers
                WHERE normalized_insights_url=?
                ORDER BY id ASC
                LIMIT 1
                """,
                (normalized_url,),
            ).fetchone()
            if matched is not None:
                source_url = str(matched[1] or "").strip() or source_url
                if snapshot_drive_file_id is None:
                    snapshot_drive_file_id = str(matched[2] or "").strip() or None
                if snapshot_drive_file_name is None:
                    snapshot_drive_file_name = str(matched[3] or "").strip() or None
                if snapshot_sha256 is None:
                    snapshot_sha256 = str(matched[4] or "").strip() or None
                if route_trace_json is None:
                    route_trace_json = str(matched[5] or "").strip() or None
                if scenario_summary_json is None:
                    scenario_summary_json = str(matched[6] or "").strip() or None
            if matched is None:
                raise AppError(
                    code="publisher_inventory_state_not_found",
                    message="Publisher inventory state cannot be recorded because the publisher row was not found",
                    retryable=False,
                    severity="error",
                    context={
                        "normalized_url": normalized_url,
                        "source_url": source_url,
                    },
                )
            conn.execute(
                """
                UPDATE publishers
                SET
                    inventory_route_kind=?,
                    inventory_route_summary=?,
                    inventory_route_trace_json=?,
                    inventory_scenario_summary_json=?,
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
                    route_trace_json,
                    scenario_summary_json,
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
