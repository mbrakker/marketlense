from __future__ import annotations

import logging
from typing import List

from src.contracts.deferred_work import (
    DeferredWorkListRequest,
    DeferredWorkMetricsRequest,
)
from src.contracts.files import FileStatRequest
from src.contracts.lock import LockGetRequest
from src.contracts.ops import (
    OpsDashboardSnapshotRequest,
    OpsDashboardSnapshotResponse,
    OpsLockSnapshot,
    OpsStorageHealthItem,
)
from src.contracts.remediation import RemediationListRequest
from src.contracts.report_store import ReportMetadataListRequest
from src.contracts.run_context import RunContext
from src.contracts.state import StateProcessedListRequest, StatePublishedListRequest
from src.services import file_service, lock_service, report_store_service, state_service
from src.services.llm_usage_ledger_service import (
    deferred_work_metrics,
    list_deferred_work,
)
from src.utils.clock import utc_now_seconds_z
from src.utils.errors import AppError
from src.utils.gui_utils import row_dicts
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.ops_dashboard_orchestrator")


def collect_ops_dashboard_snapshot(
    request: OpsDashboardSnapshotRequest,
    ctx: RunContext,
) -> OpsDashboardSnapshotResponse:
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ops_snapshot_start",
            module=logger.name,
            fields={
                "reports_db": request.reports_db,
                "state_db": request.state_db,
                "ingest_lock_path": request.ingest_lock_path,
            },
        )
    )

    reports_resp = report_store_service.list_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=request.reports_db),
        child_context(ctx, task_id="ops:list_reports"),
    )
    reports = row_dicts(reports_resp.records, include_object_attrs=True)
    reports.sort(key=lambda row: int(row.get("updated_at") or 0), reverse=True)
    reports = reports[: max(request.report_limit, 0)]

    processed_resp = state_service.list_processed(
        StateProcessedListRequest(
            schema_version="1.0",
            state_db=request.state_db,
            limit=request.processed_limit,
        ),
        child_context(ctx, task_id="ops:list_processed"),
    )
    processed = row_dicts(processed_resp.rows, include_object_attrs=True)

    published_resp = state_service.list_published(
        StatePublishedListRequest(
            schema_version="1.0",
            state_db=request.state_db,
            limit=request.published_limit,
        ),
        child_context(ctx, task_id="ops:list_published"),
    )
    published = row_dicts(published_resp.rows, include_object_attrs=True)

    remediation_resp = state_service.list_remediation_records(
        RemediationListRequest(
            schema_version="1.0",
            state_db=request.state_db,
            statuses=[
                "pending",
                "leased",
                "retrying",
                "deferred",
                "operator_action_required",
                "terminal",
            ],
            limit=100,
        ),
        child_context(ctx, task_id="ops:list_remediations"),
    )
    remediations = [
        {
            "remediation_id": record.remediation_id,
            "workflow": record.workflow,
            "status": record.status,
            "error_code": record.error_code,
            "action": record.action_code,
            "next_action": record.operator_next_action,
            "attempts": f"{record.attempt_count}/{record.max_attempts}",
            "checkpoint": record.checkpoint.path if record.checkpoint else "",
            "blocker": record.runbook_ref,
        }
        for record in remediation_resp.records
    ]
    deferred_work: list[dict] = []
    deferred_metrics: dict[str, float | int] = {}
    if request.usage_db_path:
        deferred_ctx = child_context(ctx, task_id="ops:list_deferred_work")
        now_utc = utc_now_seconds_z()
        deferred_metrics = dict(
            deferred_work_metrics(
                DeferredWorkMetricsRequest(
                    schema_version="1.0",
                    usage_db_path=request.usage_db_path,
                    now_utc=now_utc,
                ),
                deferred_ctx,
            ).__dict__
        )
        deferred_work = [
            {
                "workflow": item.workflow,
                "stage": item.stage,
                "status": item.status,
                "affected_limit": item.affected_limit,
                "attempts": f"{item.attempt_count}/{item.max_attempts}",
                "defer_count": item.defer_count,
                "earliest_run_at_utc": item.earliest_run_at_utc,
                "terminal_status": item.terminal_status,
            }
            for item in list_deferred_work(
                DeferredWorkListRequest(
                    schema_version="1.0",
                    usage_db_path=request.usage_db_path,
                    limit=100,
                ),
                deferred_ctx,
            ).records
        ]

    lock_ctx = child_context(ctx, task_id="ops:get_lock")
    try:
        lock_resp = lock_service.get_lock(
            LockGetRequest(schema_version="1.0", lock_path=request.ingest_lock_path),
            lock_ctx,
        )
        lock = OpsLockSnapshot(
            schema_version="1.0",
            found=lock_resp.found,
            owner_id=lock_resp.lock.owner_id if lock_resp.lock else "",
            pid=lock_resp.lock.pid if lock_resp.lock else None,
            error="",
        )
    except AppError as exc:
        lock = OpsLockSnapshot(
            schema_version="1.0",
            found=False,
            owner_id="",
            pid=None,
            error=exc.message,
        )

    storage_health: List[OpsStorageHealthItem] = []
    targets = [
        ("output_dir", request.output_dir),
        ("cache_dir", request.cache_dir),
        ("state_db", request.state_db),
        ("reports_db", request.reports_db),
    ]
    for name, path in targets:
        target_ctx = child_context(ctx, task_id=f"ops:stat:{name}")
        try:
            stat = file_service.file_stat(
                FileStatRequest(schema_version="1.0", path=path),
                target_ctx,
            )
            storage_health.append(
                OpsStorageHealthItem(
                    schema_version="1.0",
                    name=name,
                    path=path,
                    exists=bool(stat.exists),
                    size_bytes=stat.size_bytes,
                    modified_utc=str(stat.mtime_utc)
                    if stat.mtime_utc is not None
                    else "",
                    error="",
                )
            )
        except AppError as exc:
            storage_health.append(
                OpsStorageHealthItem(
                    schema_version="1.0",
                    name=name,
                    path=path,
                    exists=False,
                    size_bytes=None,
                    modified_utc="",
                    error=exc.message,
                )
            )

    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="ops_snapshot_complete",
            module=logger.name,
            fields={
                "reports": len(reports),
                "processed": len(processed),
                "published": len(published),
                "remediations": len(remediations),
                "deferred_work": len(deferred_work),
                "deferred_work_queue_depth": int(deferred_metrics.get("queue_depth", 0)),
                "lock_found": lock.found,
                "storage_targets": len(storage_health),
            },
        )
    )
    return OpsDashboardSnapshotResponse(
        schema_version="1.0",
        reports=reports,
        processed=processed,
        published=published,
        lock=lock,
        storage_health=storage_health,
        remediations=remediations,
        deferred_work=deferred_work,
        deferred_work_metrics=deferred_metrics,
    )
