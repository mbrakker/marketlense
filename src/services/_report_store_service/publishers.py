from __future__ import annotations

import sqlite3

from src.contracts.report_store import (
    PublisherListItem,
    PublisherGoogleFolderUpdateRequest,
    PublisherGoogleFolderUpdateResponse,
    PublishersListRequest,
    PublishersListResponse,
    PublishersReplaceRequest,
    PublishersReplaceResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

from .common import logger, _normalize_optional_url_key, _normalize_publisher_key
from .connection import _metadata_conn
from .serialization import _parse_inventory_run_quality_summary

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
    rows: list[tuple[str, str, str, str, str]] = []
    for publisher in publishers:
        notion_page_id = publisher.notion_page_id.strip()
        name = publisher.name.strip()
        homepage = publisher.homepage.strip()
        self_presentation = publisher.self_presentation.strip()
        insights_url = publisher.insights_url.strip()
        normalized_insights_url = _normalize_optional_url_key(insights_url)

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
                normalized_insights_url,
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
        with _metadata_conn(db_path, ctx) as conn:
            existing_row = conn.execute("SELECT COUNT(*) FROM publishers").fetchone()
            previous_count = int(existing_row[0] if existing_row else 0)
            preserved_rows = conn.execute(
                """
                SELECT
                    name,
                    insights_url,
                    normalized_insights_url,
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
                """
            ).fetchall()
            preserved_by_insights_url: dict[str, tuple[object, ...]] = {}
            preserved_by_name: dict[str, tuple[object, ...]] = {}
            for row in preserved_rows:
                name_key = _normalize_publisher_key(str(row[0] or ""))
                insights_url_key = str(
                    row[2] or ""
                ).strip() or _normalize_optional_url_key(str(row[1] or ""))
                preserved_payload = (
                    str(row[3] or "").strip() or None,
                    str(row[4] or "").strip() or None,
                    str(row[5] or "").strip() or None,
                    str(row[6] or "").strip() or None,
                    str(row[7] or "").strip() or None,
                    str(row[8] or "").strip() or None,
                    str(row[9] or "").strip() or None,
                    int(row[10]) if row[10] is not None else None,
                    str(row[11] or "").strip() or None,
                    str(row[12] or "").strip() or None,
                    str(row[13] or "").strip() or None,
                    str(row[14] or "").strip() or None,
                    str(row[15] or "").strip() or None,
                    int(row[16]) if row[16] is not None else None,
                    str(row[17] or "").strip() or None,
                    str(row[18] or "").strip() or None,
                    str(row[19] or "").strip() or None,
                    int(row[20]) if row[20] is not None else None,
                    str(row[21] or "").strip() or None,
                    int(row[22]) if row[22] is not None else None,
                )
                if (
                    insights_url_key
                    and insights_url_key not in preserved_by_insights_url
                ):
                    preserved_by_insights_url[insights_url_key] = preserved_payload
                if name_key and name_key not in preserved_by_name:
                    preserved_by_name[name_key] = preserved_payload
            conn.execute("DELETE FROM publishers")
            if rows:
                rows_with_routes = []
                for row in rows:
                    insights_url_key = row[4]
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
                        normalized_insights_url,
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
                    )
                    VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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


def list_publishers(
    request: PublishersListRequest,
    ctx: RunContext,
) -> PublishersListResponse:
    db_path = request.db_path.strip()
    limit = int(request.limit) if request.limit is not None else None
    if not db_path:
        raise AppError(
            code="publishers_list_db_missing",
            message="Report metadata DB path is required for publisher listing",
            retryable=False,
            severity="error",
        )
    if limit is not None and limit <= 0:
        raise AppError(
            code="publishers_list_limit_invalid",
            message="limit must be greater than zero when provided",
            retryable=False,
            severity="error",
            context={"limit": limit},
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publishers_list_start",
            module=logger.name,
            fields={"db_path": db_path, "limit": limit},
        )
    )
    with _metadata_conn(db_path, ctx) as conn:
        rows = conn.execute(
            """
            SELECT
                name,
                homepage,
                insights_url,
                normalized_insights_url,
                google_folder,
                discovery_test_status,
                inventory_route_kind,
                inventory_route_summary,
                inventory_run_quality_json
            FROM publishers
            WHERE normalized_insights_url <> ''
            ORDER BY id ASC
            """
        ).fetchall()
    publishers: list[PublisherListItem] = []
    for row in rows:
        insights_url = str(row[2] or "").strip()
        normalized_insights_url = str(row[3] or "").strip()
        if not normalized_insights_url:
            continue
        publishers.append(
            PublisherListItem(
                schema_version="1.0",
                publisher_name=str(row[0] or "").strip(),
                homepage=str(row[1] or "").strip(),
                insights_url=insights_url,
                normalized_insights_url=normalized_insights_url,
                google_folder=str(row[4] or "").strip() or None,
                discovery_test_status=str(row[5] or "").strip() or None,
                inventory_route_kind=str(row[6] or "").strip() or None,
                inventory_route_summary=str(row[7] or "").strip() or None,
                inventory_run_quality_summary=_parse_inventory_run_quality_summary(
                    str(row[8] or "").strip() or None
                ),
            )
        )
        if limit is not None and len(publishers) >= limit:
            break
    response = PublishersListResponse(schema_version="1.0", publishers=publishers)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publishers_list_complete",
            module=logger.name,
            fields={"db_path": db_path, "publisher_count": len(response.publishers)},
        )
    )
    return response


def update_publisher_google_folder(
    request: PublisherGoogleFolderUpdateRequest,
    ctx: RunContext,
) -> PublisherGoogleFolderUpdateResponse:
    db_path = request.db_path.strip()
    publisher_name = request.publisher_name.strip()
    google_folder = request.google_folder.strip()
    publisher_insights_url_raw = str(request.publisher_insights_url or "").strip()
    publisher_insights_url = _normalize_optional_url_key(
        publisher_insights_url_raw
    )
    if not db_path:
        raise AppError(
            code="publisher_google_folder_db_missing",
            message="Report metadata DB path is required for publisher folder update",
            retryable=False,
            severity="error",
        )
    if not publisher_name and not publisher_insights_url:
        raise AppError(
            code="publisher_google_folder_lookup_key_missing",
            message="Publisher name or insights URL is required for publisher folder update",
            retryable=False,
            severity="error",
        )
    if not google_folder:
        raise AppError(
            code="publisher_google_folder_missing",
            message="Google folder value is required for publisher folder update",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_google_folder_update_start",
            module=logger.name,
            fields={
                "db_path": db_path,
                "publisher_name": publisher_name,
                "has_publisher_insights_url": bool(publisher_insights_url),
                "google_folder": google_folder,
            },
        )
    )
    try:
        with _metadata_conn(db_path, ctx) as conn:
            updated_count = 0
            resolution_source = "publisher_name"
            if publisher_insights_url:
                cursor = conn.execute(
                    """
                    UPDATE publishers
                    SET google_folder=?
                    WHERE normalized_insights_url=?
                    """,
                    (google_folder, publisher_insights_url),
                )
                updated_count = int(cursor.rowcount or 0)
                resolution_source = "publisher_insights_url"
            if updated_count <= 0 and publisher_name:
                cursor = conn.execute(
                    """
                    UPDATE publishers
                    SET google_folder=?
                    WHERE lower(trim(name))=lower(trim(?))
                    """,
                    (google_folder, publisher_name),
                )
                updated_count = int(cursor.rowcount or 0)
                resolution_source = "publisher_name"
            if updated_count <= 0 and publisher_name:
                conn.execute(
                    """
                    INSERT INTO publishers (
                        name,
                        homepage,
                        self_presentation,
                        insights_url,
                        normalized_insights_url,
                        google_folder
                    )
                    VALUES (?, '', '', ?, ?, ?)
                    """,
                    (
                        publisher_name,
                        publisher_insights_url_raw,
                        publisher_insights_url,
                        google_folder,
                    ),
                )
                updated_count = 1
                resolution_source = "publisher_name_inserted"
            if updated_count <= 0:
                raise AppError(
                    code="publisher_google_folder_publisher_not_found",
                    message="Publisher row was not found for Google folder update",
                    retryable=False,
                    severity="error",
                    context={
                        "db_path": db_path,
                        "publisher_name": publisher_name,
                        "publisher_insights_url": publisher_insights_url or "",
                    },
                )
            row = conn.execute(
                """
                SELECT name, google_folder
                FROM publishers
                WHERE google_folder=?
                  AND (
                    (? <> '' AND normalized_insights_url=?)
                    OR (? <> '' AND lower(trim(name))=lower(trim(?)))
                  )
                ORDER BY id ASC
                LIMIT 1
                """,
                (
                    google_folder,
                    publisher_insights_url or "",
                    publisher_insights_url or "",
                    publisher_name,
                    publisher_name,
                ),
            ).fetchone()
    except AppError:
        raise
    except sqlite3.Error as exc:
        raise AppError(
            code="publisher_google_folder_update_failed",
            message="Failed to update publisher Google folder in the reports database",
            cause=exc,
            retryable=True,
            severity="error",
            context={
                "db_path": db_path,
                "publisher_name": publisher_name,
                "publisher_insights_url": publisher_insights_url or "",
            },
        ) from exc
    resolved_name = str(row[0] if row else publisher_name).strip()
    resolved_folder = str(row[1] if row else google_folder).strip()
    response = PublisherGoogleFolderUpdateResponse(
        schema_version="1.0",
        publisher_name=resolved_name,
        google_folder=resolved_folder,
        updated_count=updated_count,
        resolution_source=resolution_source,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="publisher_google_folder_update_complete",
            module=logger.name,
            fields={
                "publisher_name": response.publisher_name,
                "updated_count": response.updated_count,
                "resolution_source": response.resolution_source,
                "google_folder": response.google_folder,
            },
        )
    )
    return response
