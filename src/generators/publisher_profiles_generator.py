from __future__ import annotations

import json
import logging

from src.contracts.files import ReadTextRequest
from src.contracts.publisher_profiles import (
    PublisherProfileRecord,
    PublisherProfilesSnapshotLoadRequest,
    PublisherProfilesSnapshotLoadResponse,
)
from src.services import file_service
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.publisher_profiles_generator")


def load_publisher_profiles_snapshot(
    request: PublisherProfilesSnapshotLoadRequest,
    ctx,
    *,
    file_client=file_service,
) -> PublisherProfilesSnapshotLoadResponse:
    snapshot_path = request.snapshot_path.strip()
    if not snapshot_path:
        raise AppError(
            code="publisher_snapshot_path_missing",
            message="snapshot_path is required for publisher sync",
            retryable=False,
            severity="error",
        )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_snapshot_load_start",
            module=logger.name,
            fields={"snapshot_path": snapshot_path},
        )
    )
    response = file_client.read_text(
        ReadTextRequest(
            schema_version="1.0",
            path=snapshot_path,
        ),
        ctx,
    )
    try:
        payload = json.loads(response.content)
    except json.JSONDecodeError as exc:
        raise AppError(
            code="publisher_snapshot_invalid_json",
            message=f"Publisher snapshot is not valid JSON: {snapshot_path}",
            cause=exc,
            retryable=False,
            severity="error",
            context={"snapshot_path": snapshot_path},
        ) from exc
    if not isinstance(payload, dict):
        raise AppError(
            code="publisher_snapshot_invalid_root",
            message="Publisher snapshot root must be a JSON object",
            retryable=False,
            severity="error",
            context={"snapshot_path": snapshot_path},
        )

    source_page_url = _clean_text(payload.get("source_page_url"))
    if not source_page_url:
        raise AppError(
            code="publisher_snapshot_source_page_missing",
            message="Publisher snapshot requires source_page_url",
            retryable=False,
            severity="error",
            context={"snapshot_path": snapshot_path},
        )

    publishers_raw = payload.get("publishers")
    if not isinstance(publishers_raw, list):
        raise AppError(
            code="publisher_snapshot_publishers_invalid",
            message="Publisher snapshot requires a publishers list",
            retryable=False,
            severity="error",
            context={"snapshot_path": snapshot_path},
        )

    publisher_count_raw = payload.get("publisher_count")
    if not isinstance(publisher_count_raw, int) or publisher_count_raw < 0:
        raise AppError(
            code="publisher_snapshot_count_invalid",
            message="Publisher snapshot requires a non-negative integer publisher_count",
            retryable=False,
            severity="error",
            context={"snapshot_path": snapshot_path},
        )

    seen_ids: set[str] = set()
    publishers: list[PublisherProfileRecord] = []
    for index, item in enumerate(publishers_raw):
        if not isinstance(item, dict):
            raise AppError(
                code="publisher_snapshot_row_invalid",
                message=f"Publisher snapshot row {index} must be a JSON object",
                retryable=False,
                severity="error",
                context={"snapshot_path": snapshot_path, "row_index": index},
            )
        notion_page_id = _clean_text(item.get("notion_page_id"))
        notion_page_url = _clean_text(item.get("notion_page_url"))
        name = _clean_text(item.get("name"))
        if not notion_page_id:
            raise AppError(
                code="publisher_snapshot_notion_page_id_missing",
                message=f"Publisher snapshot row {index} requires notion_page_id",
                retryable=False,
                severity="error",
                context={"snapshot_path": snapshot_path, "row_index": index},
            )
        if notion_page_id in seen_ids:
            raise AppError(
                code="publisher_snapshot_notion_page_id_duplicate",
                message=f"Duplicate notion_page_id in publisher snapshot: {notion_page_id}",
                retryable=False,
                severity="error",
                context={"snapshot_path": snapshot_path, "row_index": index},
            )
        if not notion_page_url:
            raise AppError(
                code="publisher_snapshot_notion_page_url_missing",
                message=f"Publisher snapshot row {index} requires notion_page_url",
                retryable=False,
                severity="error",
                context={"snapshot_path": snapshot_path, "row_index": index},
            )
        if not name:
            raise AppError(
                code="publisher_snapshot_name_missing",
                message=f"Publisher snapshot row {index} requires name",
                retryable=False,
                severity="error",
                context={"snapshot_path": snapshot_path, "row_index": index},
            )
        seen_ids.add(notion_page_id)
        publishers.append(
            PublisherProfileRecord(
                schema_version="1.0",
                notion_page_id=notion_page_id,
                notion_page_url=notion_page_url,
                name=name,
                homepage=_clean_text(item.get("homepage")),
                self_presentation=_clean_text(item.get("self_presentation")),
                insights_url=_clean_text(item.get("insights_url")),
                icon_source=_clean_text(item.get("icon_source")),
            )
        )

    if publisher_count_raw != len(publishers):
        raise AppError(
            code="publisher_snapshot_count_mismatch",
            message=(
                "Publisher snapshot publisher_count does not match the number of publisher rows"
            ),
            retryable=False,
            severity="error",
            context={
                "snapshot_path": snapshot_path,
                "publisher_count": publisher_count_raw,
                "actual_count": len(publishers),
            },
        )

    result = PublisherProfilesSnapshotLoadResponse(
        schema_version="1.0",
        snapshot_path=snapshot_path,
        source_page_url=source_page_url,
        publisher_count=len(publishers),
        publishers=publishers,
    )
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="publisher_snapshot_load_complete",
            module=logger.name,
            fields={
                "snapshot_path": result.snapshot_path,
                "source_page_url": result.source_page_url,
                "publisher_count": result.publisher_count,
            },
        )
    )
    return result


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()
