from __future__ import annotations

import logging
import time
from typing import Callable, Optional

from src.contracts.ingest import IngestSettings
from src.contracts.run_context import RunContext
from src.contracts.state import StateProcessedListRequest, StateRecordRequest
from src.contracts.vector_store import (
    VectorStorePruneItem,
    VectorStorePruneRequest,
    VectorStoreRetentionCleanupResponse,
)
from src.services import state_service, vector_store_service
from src.utils.logging import child_context, log_event, new_run_context

logger = logging.getLogger("market_lense.vector_store_retention_orchestrator")

RETENTION_SCAN_LIMIT = 10_000
SECONDS_PER_DAY = 86_400


def run_vector_store_retention_cleanup(
    settings: IngestSettings,
    ctx: Optional[RunContext] = None,
    *,
    now_epoch: Optional[int] = None,
    state_list: Callable = state_service.list_processed,
    state_record: Callable = state_service.record,
    vector_store_prune: Callable = vector_store_service.prune_vector_stores,
) -> VectorStoreRetentionCleanupResponse:
    cleanup_ctx = child_context(
        ctx or new_run_context(task_id="vector_store_retention_cleanup"),
        task_id="vector_store_retention_cleanup",
    )
    retention_days = int(getattr(settings, "vector_store_retention_days", 30) or 0)
    if retention_days <= 0:
        logger.info(
            log_event(
                cleanup_ctx,
                role="orchestrator",
                event="vector_store_retention_cleanup_disabled",
                module=logger.name,
                fields={"retention_days": retention_days},
            )
        )
        return VectorStoreRetentionCleanupResponse(
            schema_version="1.0",
            scanned_count=0,
            candidate_count=0,
            pruned_vector_store_ids=[],
            retention_days=retention_days,
        )

    now = int(now_epoch if now_epoch is not None else time.time())
    cutoff = now - retention_days * SECONDS_PER_DAY
    rows = state_list(
        StateProcessedListRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            limit=RETENTION_SCAN_LIMIT,
        ),
        cleanup_ctx,
    ).rows
    items: list[VectorStorePruneItem] = []
    rows_by_vector_store_id = {}
    for row in rows:
        vector_store_id = str(row.vector_store_id or "").strip()
        if not vector_store_id or int(row.processed_at) > cutoff:
            continue
        items.append(
            VectorStorePruneItem(
                schema_version="1.0",
                vector_store_id=vector_store_id,
                reason="retention_expired",
                file_id=row.file_id,
            )
        )
        rows_by_vector_store_id[vector_store_id] = row

    logger.info(
        log_event(
            cleanup_ctx,
            role="orchestrator",
            event="vector_store_retention_cleanup_start",
            module=logger.name,
            fields={
                "scanned_count": len(rows),
                "candidate_count": len(items),
                "retention_days": retention_days,
                "cutoff_epoch": cutoff,
            },
        )
    )
    if not items:
        return VectorStoreRetentionCleanupResponse(
            schema_version="1.0",
            scanned_count=len(rows),
            candidate_count=0,
            pruned_vector_store_ids=[],
            retention_days=retention_days,
        )

    prune_response = vector_store_prune(
        VectorStorePruneRequest(schema_version="1.0", items=items, missing_ok=True),
        cleanup_ctx,
    )
    pruned_ids = list(prune_response.deleted_vector_store_ids) + list(
        prune_response.missing_vector_store_ids
    )
    for vector_store_id in pruned_ids:
        row = rows_by_vector_store_id.get(vector_store_id)
        if row is None:
            continue
        state_record(
            StateRecordRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                file_id=row.file_id,
                md5=row.md5,
                openai_file_id=row.openai_file_id,
                vector_store_id=None,
                vector_store_status="deleted",
                indexed_at_utc=row.indexed_at_utc,
                last_error="vector_store_deleted:retention_expired",
                text_validation_status=row.text_validation_status,
                text_validation_reason=row.text_validation_reason,
                text_validation_pages=row.text_validation_pages,
                doc_map_summary=row.doc_map_summary,
                ocr_fallback_used=row.ocr_fallback_used,
                ocr_pdf_path=row.ocr_pdf_path,
            ),
            cleanup_ctx,
        )

    logger.info(
        log_event(
            cleanup_ctx,
            role="orchestrator",
            event="vector_store_retention_cleanup_complete",
            module=logger.name,
            fields={
                "scanned_count": len(rows),
                "candidate_count": len(items),
                "pruned_count": len(pruned_ids),
                "retention_days": retention_days,
            },
        )
    )
    return VectorStoreRetentionCleanupResponse(
        schema_version="1.0",
        scanned_count=len(rows),
        candidate_count=len(items),
        pruned_vector_store_ids=pruned_ids,
        retention_days=retention_days,
    )
