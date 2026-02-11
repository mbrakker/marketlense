from __future__ import annotations

import logging
from typing import List

from src.contracts.files import ListHtmlRequest, ReadTextRequest
from src.contracts.publish import PublishQueueItem, PublishQueueRequest, PublishQueueResponse
from src.contracts.run_context import RunContext
from src.contracts.state import StatePublishCheckRequest
from src.services.file_service import list_html, read_text
from src.services.state_service import get_publish
from src.utils.errors import AppError
from src.utils.html_utils import extract_file_id
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.publish_queue_orchestrator")


def build_publish_queue_snapshot(request: PublishQueueRequest, ctx: RunContext) -> PublishQueueResponse:
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="publish_queue_start",
        module=logger.name,
        fields={"output_dir": request.output_dir, "state_db": request.state_db},
    ))

    list_resp = list_html(
        ListHtmlRequest(schema_version="1.0", root_dir=request.output_dir),
        ctx,
    )
    items: List[PublishQueueItem] = []
    for html_path in list_resp.html_paths:
        row_ctx = child_context(ctx, task_id=html_path)
        try:
            html = read_text(ReadTextRequest(schema_version="1.0", path=html_path), row_ctx).content
        except AppError as exc:
            logger.info(log_event(
                row_ctx,
                role="orchestrator",
                event="publish_queue_read_failed",
                module=logger.name,
                fields={"html_path": html_path, "error": exc.message},
            ))
            continue
        file_id = extract_file_id(html) or ""
        publish_state = None
        if file_id:
            publish_state = get_publish(
                StatePublishCheckRequest(schema_version="1.0", state_db=request.state_db, file_id=file_id),
                row_ctx,
            )
        items.append(PublishQueueItem(
            schema_version="1.0",
            html_path=html_path,
            file_id=file_id,
            published=bool(publish_state),
            wp_post_id=getattr(publish_state, "wp_post_id", None) if publish_state else None,
            wp_post_url=getattr(publish_state, "wp_post_url", None) if publish_state else None,
        ))

    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="publish_queue_complete",
        module=logger.name,
        fields={"count": len(items)},
    ))
    return PublishQueueResponse(schema_version="1.0", items=items)
