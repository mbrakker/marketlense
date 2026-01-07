from __future__ import annotations

import logging
from typing import List

from src.contracts.categories import (
    WordPressCategoryUpdateOutcome,
    CategoryMappingLoadRequest,
)
from src.contracts.publish import PublishSettings
from src.contracts.run_context import RunContext
from src.contracts.state import StatePublishCheckRequest
from src.contracts.report_store import ReportMetadataListRequest
from src.generators.wp_category_generator import update_post_categories_for_record
from src.services.category_mapping_service import load_mappings as load_category_mappings
from src.services.report_store_service import list_metadata as list_report_metadata
from src.services.state_service import get_publish
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.wp_auth import build_auth_header

logger = logging.getLogger("market_lense.wp_category_update_orchestrator")


def run_update_wp_categories(settings: PublishSettings) -> List[WordPressCategoryUpdateOutcome]:
    ctx = new_run_context()
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="wp_category_update_start",
        module=logger.name,
        fields={"state_db": settings.state_db, "reports_db": settings.reports_db},
    ))
    mappings_resp = load_category_mappings(
        CategoryMappingLoadRequest(schema_version="1.0", path=settings.category_mapping_path, reload_if_changed=True),
        ctx,
    )
    list_resp = list_report_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=settings.reports_db),
        ctx,
    )
    auth_header = build_auth_header(
        username=settings.wp.username,
        app_password=settings.wp.app_password,
        bearer_token=settings.wp.bearer_token,
    )
    base_url = settings.wp.site_url.rstrip("/")

    outcomes: List[WordPressCategoryUpdateOutcome] = []
    for record in list_resp.records:
        record_ctx = child_context(ctx, task_id=record.file_id)
        publish_state = get_publish(
            StatePublishCheckRequest(schema_version="1.0", state_db=settings.state_db, file_id=record.file_id),
            record_ctx,
        )
        if not publish_state or not publish_state.wp_post_id:
            outcomes.append(WordPressCategoryUpdateOutcome(
                schema_version="1.0",
                file_id=record.file_id,
                post_id=None,
                categories=[],
                status="skipped",
                error="not_published",
            ))
            continue
        try:
            outcome = update_post_categories_for_record(
                file_id=record.file_id,
                post_id=publish_state.wp_post_id,
                categories=record.categories,
                base_url=base_url,
                auth_header=auth_header,
                mappings=mappings_resp,
                ctx=record_ctx,
            )
            outcomes.append(outcome)
        except Exception as exc:
            logger.info(log_event(
                record_ctx,
                role="orchestrator",
                event="wp_category_update_error",
                module=logger.name,
                fields={"file_id": record.file_id, "error": str(exc)},
            ))
            outcomes.append(WordPressCategoryUpdateOutcome(
                schema_version="1.0",
                file_id=record.file_id,
                post_id=publish_state.wp_post_id,
                categories=record.categories,
                status="error",
                error=str(exc),
            ))

    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="wp_category_update_complete",
        module=logger.name,
        fields={"count": len(outcomes)},
    ))
    return outcomes
