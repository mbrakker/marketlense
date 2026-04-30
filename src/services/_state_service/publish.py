from __future__ import annotations

from typing import Optional

from src.contracts.run_context import RunContext
from src.contracts.state import (
    StatePublishCheckRequest,
    StatePublishGetResponse,
    StatePublishedListRequest,
    StatePublishedListResponse,
    StatePublishedRow,
    StatePublishRecordRequest,
)
from src.services._state_service.common import _normalize_post_type, _state_conn, logger
from src.utils.logging import log_event


def already_published(request: StatePublishCheckRequest, ctx: RunContext) -> bool:
    post_type = _normalize_post_type(request.post_type)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_publish_check_start",
            module=logger.name,
            fields={"file_id": request.file_id, "post_type": post_type},
        )
    )
    with _state_conn(request.state_db, ctx) as conn:
        cur = conn.execute(
            "SELECT 1 FROM published WHERE file_id=? AND post_type=?",
            (request.file_id, post_type),
        )
        result = cur.fetchone() is not None
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_publish_check_complete",
            module=logger.name,
            fields={
                "file_id": request.file_id,
                "post_type": post_type,
                "already_published": result,
            },
        )
    )
    return result


def record_publish(request: StatePublishRecordRequest, ctx: RunContext) -> None:
    post_type = _normalize_post_type(request.post_type)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_publish_record_start",
            module=logger.name,
            fields={
                "file_id": request.file_id,
                "wp_post_id": request.wp_post_id,
                "post_type": post_type,
            },
        )
    )
    with _state_conn(request.state_db, ctx) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO published("
            "file_id, md5, published_at, wp_post_id, wp_post_url, post_type"
            ") VALUES(?, ?, strftime('%s','now'), ?, ?, ?)",
            (
                request.file_id,
                request.md5,
                request.wp_post_id,
                request.wp_post_url,
                post_type,
            ),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_publish_record_complete",
            module=logger.name,
            fields={
                "file_id": request.file_id,
                "wp_post_id": request.wp_post_id,
                "post_type": post_type,
            },
        )
    )


def get_publish(
    request: StatePublishCheckRequest, ctx: RunContext
) -> Optional[StatePublishGetResponse]:
    post_type = _normalize_post_type(request.post_type)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_publish_get_start",
            module=logger.name,
            fields={"file_id": request.file_id, "post_type": post_type},
        )
    )
    with _state_conn(request.state_db, ctx) as conn:
        cur = conn.execute(
            "SELECT file_id, md5, published_at, wp_post_id, wp_post_url, post_type "
            "FROM published WHERE file_id=? AND post_type=?",
            (request.file_id, post_type),
        )
        row = cur.fetchone()
    if not row:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="state_publish_get_complete",
                module=logger.name,
                fields={
                    "file_id": request.file_id,
                    "post_type": post_type,
                    "found": False,
                },
            )
        )
        return None
    file_id, md5, published_at, wp_post_id, wp_post_url, stored_post_type = row
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_publish_get_complete",
            module=logger.name,
            fields={"file_id": file_id, "post_type": stored_post_type, "found": True},
        )
    )
    return StatePublishGetResponse(
        schema_version="1.0",
        file_id=file_id,
        md5=md5,
        published_at=published_at,
        wp_post_id=wp_post_id,
        wp_post_url=wp_post_url,
        post_type=str(stored_post_type or ""),
    )


def list_published(
    request: StatePublishedListRequest, ctx: RunContext
) -> StatePublishedListResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_published_list_start",
            module=logger.name,
            fields={"state_db": request.state_db, "limit": request.limit},
        )
    )
    limit = int(request.limit) if isinstance(request.limit, int) else 200
    if limit <= 0:
        limit = 200
    rows: list[StatePublishedRow] = []
    with _state_conn(request.state_db, ctx) as conn:
        cur = conn.execute(
            "SELECT file_id, md5, published_at, wp_post_id, wp_post_url, post_type "
            "FROM published ORDER BY published_at DESC LIMIT ?",
            (limit,),
        )
        for (
            file_id,
            md5,
            published_at,
            wp_post_id,
            wp_post_url,
            post_type,
        ) in cur.fetchall():
            rows.append(
                StatePublishedRow(
                    schema_version="1.0",
                    file_id=file_id,
                    md5=md5,
                    published_at=int(published_at),
                    wp_post_id=int(wp_post_id),
                    wp_post_url=wp_post_url,
                    post_type=str(post_type or ""),
                )
            )
    response = StatePublishedListResponse(schema_version="1.0", rows=rows)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="state_published_list_complete",
            module=logger.name,
            fields={"state_db": request.state_db, "count": len(rows)},
        )
    )
    return response
