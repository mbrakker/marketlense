from __future__ import annotations

import logging
from typing import List

from src.contracts.categories import (
    RecategorizeOutcome,
    RecategorizeRequest,
)
from src.contracts.report_store import ReportMetadataUpsertRequest, ReportMetadataListRequest
from src.contracts.context_category_fit import (
    ContextCategoryFitRequest,
    ReportContextBuildRequest,
)
from src.generators.context_category_fit_generator import fit_report_categories_from_context
from src.generators.report_context_generator import build_report_category_context
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

    list_resp = list_report_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=request.db_path),
        ctx,
    )

    outcomes: List[RecategorizeOutcome] = []
    for record in list_resp.records:
        record_ctx = child_context(ctx, task_id=record.file_id)
        try:
            report_context = build_report_category_context(
                ReportContextBuildRequest(
                    schema_version="1.0",
                    report=record,
                ),
                record_ctx,
            )
            fit_response = fit_report_categories_from_context(
                ContextCategoryFitRequest(
                    schema_version="1.0",
                    context=report_context,
                    settings=request.settings,
                    category_mapping_path=request.category_mapping_path,
                ),
                record_ctx,
            )

            upsert_metadata(
                ReportMetadataUpsertRequest(
                    schema_version="1.1",
                    db_path=request.db_path,
                    file_id=record.file_id,
                    title=record.title,
                    file_name=record.file_name,
                    publisher=record.publisher,
                    taxonomy=record.taxonomy,
                    categories=fit_response.categories,
                    region=record.region,
                    time_period=record.time_period,
                    source_url=record.source_url,
                    html_path=record.html_path,
                    md5=record.md5,
                    contents_page_number=record.contents_page_number,
                    pdf_metadata=record.pdf_metadata,
                    analysis_mode=record.analysis_mode,
                    vector_store_id=record.vector_store_id,
                    evidence_pack_paths=record.evidence_pack_paths,
                ),
                record_ctx,
            )
            outcomes.append(RecategorizeOutcome(
                schema_version="1.0",
                file_id=record.file_id,
                title=record.title,
                categories=fit_response.categories,
                unmapped_tags=[],
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
