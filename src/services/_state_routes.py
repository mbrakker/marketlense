from __future__ import annotations

from typing import Optional

from src.contracts.run_context import RunContext
from src.contracts.state import (
    StateReportDownloadRouteGetRequest,
    StateReportDownloadRouteRecordRequest,
    StateReportDownloadRouteResponse,
)
from src.services._state_common import _state_conn, logger
from src.utils.logging import log_event


def get_report_download_route(
    request: StateReportDownloadRouteGetRequest,
    ctx: RunContext,
) -> Optional[StateReportDownloadRouteResponse]:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_download_route_get_start",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "normalized_url": request.normalized_url,
            },
        )
    )
    with _state_conn(request.state_db) as conn:
        cur = conn.execute(
            "SELECT normalized_url, source_url, route_kind, route_summary, outcome, "
            "last_downloaded_file_path, last_final_page_url, updated_at "
            "FROM report_download_routes WHERE normalized_url=?",
            (request.normalized_url,),
        )
        row = cur.fetchone()
    if not row:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="report_download_route_get_complete",
                module=logger.name,
                fields={
                    "state_db": request.state_db,
                    "normalized_url": request.normalized_url,
                    "found": False,
                },
            )
        )
        return None
    (
        normalized_url,
        source_url,
        route_kind,
        route_summary,
        outcome,
        last_downloaded_file_path,
        last_final_page_url,
        updated_at,
    ) = row
    response = StateReportDownloadRouteResponse(
        schema_version="1.0",
        normalized_url=str(normalized_url),
        source_url=str(source_url),
        route_kind=str(route_kind),
        route_summary=str(route_summary),
        outcome=str(outcome),
        updated_at=int(updated_at),
        last_downloaded_file_path=(
            str(last_downloaded_file_path) if last_downloaded_file_path else None
        ),
        last_final_page_url=str(last_final_page_url) if last_final_page_url else None,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_download_route_get_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "normalized_url": response.normalized_url,
                "found": True,
                "route_kind": response.route_kind,
                "outcome": response.outcome,
            },
        )
    )
    return response


def record_report_download_route(
    request: StateReportDownloadRouteRecordRequest,
    ctx: RunContext,
) -> None:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_download_route_record_start",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "normalized_url": request.normalized_url,
                "route_kind": request.route_kind,
                "outcome": request.outcome,
            },
        )
    )
    with _state_conn(request.state_db) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO report_download_routes("
            "normalized_url, source_url, route_kind, route_summary, outcome, "
            "last_downloaded_file_path, last_final_page_url, updated_at"
            ") VALUES(?, ?, ?, ?, ?, ?, ?, strftime('%s','now'))",
            (
                request.normalized_url,
                request.source_url,
                request.route_kind,
                request.route_summary,
                request.outcome,
                request.last_downloaded_file_path,
                request.last_final_page_url,
            ),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="report_download_route_record_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "normalized_url": request.normalized_url,
                "route_kind": request.route_kind,
                "outcome": request.outcome,
            },
        )
    )
