from __future__ import annotations

import logging
from pathlib import Path
from typing import List

from src.contracts.files import ListHtmlRequest, ReadTextRequest
from src.contracts.publish import PublishQueueItem, PublishQueueRequest, PublishQueueResponse
from src.contracts.report_store import ReportMetadataListRequest
from src.contracts.run_context import RunContext
from src.contracts.state import StatePublishCheckRequest
from src.services.file_service import list_html, read_text
from src.services.report_store_service import list_metadata
from src.services.state_service import get_publish
from src.utils.errors import AppError
from src.utils.html_utils import extract_file_id
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.publish_queue_orchestrator")


def _canonical_html_path(path: str) -> str:
    try:
        return str(Path(path).expanduser().resolve())
    except Exception:
        return str(Path(path))


def _load_html_file_id_map(reports_db: str, ctx: RunContext) -> dict[str, str]:
    if not reports_db.strip():
        return {}
    response = list_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=reports_db),
        ctx,
    )
    mapping: dict[str, str] = {}
    records = sorted(
        response.records,
        key=lambda row: int(getattr(row, "updated_at", 0) or 0),
        reverse=True,
    )
    for row in records:
        html_path = (row.html_path or "").strip()
        file_id = (row.file_id or "").strip()
        if not html_path or not file_id:
            continue
        key = _canonical_html_path(html_path)
        if key not in mapping:
            mapping[key] = file_id
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="publish_queue_file_id_map_loaded",
        module=logger.name,
        fields={"reports_db": reports_db, "rows": len(response.records), "mapped": len(mapping)},
    ))
    return mapping


def build_publish_queue_snapshot(request: PublishQueueRequest, ctx: RunContext) -> PublishQueueResponse:
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="publish_queue_start",
        module=logger.name,
        fields={"output_dir": request.output_dir, "state_db": request.state_db, "reports_db": request.reports_db},
    ))

    list_resp = list_html(
        ListHtmlRequest(schema_version="1.0", root_dir=request.output_dir),
        ctx,
    )
    html_file_id_map: dict[str, str] = {}
    map_ctx = child_context(ctx, task_id="publish_queue_file_id_map")
    try:
        html_file_id_map = _load_html_file_id_map(request.reports_db, map_ctx)
    except Exception as exc:
        logger.info(log_event(
            map_ctx,
            role="orchestrator",
            event="publish_queue_file_id_map_failed",
            module=logger.name,
            fields={"reports_db": request.reports_db, "error": str(exc)},
        ))
        html_file_id_map = {}

    items: List[PublishQueueItem] = []
    for html_path in list_resp.html_paths:
        row_ctx = child_context(ctx, task_id=html_path)
        file_id = html_file_id_map.get(_canonical_html_path(html_path), "")
        if not file_id:
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
            if file_id:
                logger.info(log_event(
                    row_ctx,
                    role="orchestrator",
                    event="publish_queue_file_id_resolved",
                    module=logger.name,
                    fields={"html_path": html_path, "file_id": file_id, "source": "html"},
                ))
        else:
            logger.info(log_event(
                row_ctx,
                role="orchestrator",
                event="publish_queue_file_id_resolved",
                module=logger.name,
                fields={"html_path": html_path, "file_id": file_id, "source": "reports_db"},
            ))
        publish_state = None
        if file_id:
            publish_state = get_publish(
                StatePublishCheckRequest(
                    schema_version="1.0",
                    state_db=request.state_db,
                    file_id=file_id,
                    post_type=request.post_type,
                ),
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
