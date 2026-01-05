from __future__ import annotations

import logging
from typing import List

from src.contracts.categories import (
    RecategorizeOutcome,
    RecategorizeRequest,
    CategoryMappingLoadRequest,
    UncategorizedTagsFlushRequest,
    UncategorizedTagsUpdateRequest,
)
from src.contracts.report_store import ReportMetadataUpsertRequest, ReportMetadataListRequest
from src.contracts.run_context import RunContext
from src.generators.categorize_generator import categorize_taxonomy
from src.services.category_mapping_service import (
    load_mappings as load_category_mappings,
    flush_uncategorized_tags,
    update_uncategorized_tags,
)
from src.services.report_store_service import list_metadata as list_report_metadata, upsert_metadata
from src.utils.logging import child_context, log_event, new_run_context

logger = logging.getLogger("market_lense.recategorize_orchestrator")


def run_recategorize(request: RecategorizeRequest) -> List[RecategorizeOutcome]:
    ctx = new_run_context()
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="recategorize_start",
        module=logger.name,
        fields={"db_path": request.db_path, "category_mapping_path": request.category_mapping_path},
    ))

    try:
        mappings_resp = load_category_mappings(
            CategoryMappingLoadRequest(
                schema_version="1.0",
                path=request.category_mapping_path,
                reload_if_changed=True,
                force_reload=True,
            ),
            ctx,
        )
        list_resp = list_report_metadata(
            ReportMetadataListRequest(schema_version="1.0", db_path=request.db_path),
            ctx,
        )

        outcomes: List[RecategorizeOutcome] = []
        for record in list_resp.records:
            record_ctx = child_context(ctx, task_id=record.file_id)
            try:
                assignment = categorize_taxonomy(record.taxonomy, mappings_resp, record_ctx)
                if assignment.unmapped_tags or mappings_resp.mappings.uncategorized:
                    update_uncategorized_tags(
                        UncategorizedTagsUpdateRequest(
                            schema_version="1.0",
                            path=request.category_mapping_path,
                            report_title=record.title,
                            tags=assignment.unmapped_tags,
                        ),
                        record_ctx,
                    )

                upsert_metadata(
                    ReportMetadataUpsertRequest(
                        schema_version="1.0",
                        db_path=request.db_path,
                        file_id=record.file_id,
                        title=record.title,
                        publisher=record.publisher,
                        taxonomy=record.taxonomy,
                        categories=assignment.categories,
                        region=record.region,
                        time_period=record.time_period,
                        source_url=record.source_url,
                        html_path=record.html_path,
                        md5=record.md5,
                    ),
                    record_ctx,
                )
                outcomes.append(RecategorizeOutcome(
                    schema_version="1.0",
                    file_id=record.file_id,
                    title=record.title,
                    categories=assignment.categories,
                    unmapped_tags=assignment.unmapped_tags,
                    status="updated",
                ))
            except Exception as exc:
                logger.info(log_event(
                    record_ctx,
                    role="orchestrator",
                    event="recategorize_error",
                    module=logger.name,
                    fields={"file_id": record.file_id, "error": str(exc)},
                ))
                outcomes.append(RecategorizeOutcome(
                    schema_version="1.0",
                    file_id=record.file_id,
                    title=record.title,
                    categories=[],
                    unmapped_tags=[],
                    status="error",
                    error=str(exc),
                ))

        logger.info(log_event(
            ctx,
            role="orchestrator",
            event="recategorize_complete",
            module=logger.name,
            fields={"count": len(outcomes)},
        ))
        return outcomes
    finally:
        try:
            flush_uncategorized_tags(
                UncategorizedTagsFlushRequest(
                    schema_version="1.0",
                    path=request.category_mapping_path,
                ),
                ctx,
            )
        except Exception as exc:
            logger.info(log_event(
                ctx,
                role="orchestrator",
                event="recategorize_uncategorized_flush_failed",
                module=logger.name,
                fields={"path": request.category_mapping_path, "error": str(exc)},
            ))
