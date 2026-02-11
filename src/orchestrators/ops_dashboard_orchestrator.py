from __future__ import annotations

import logging
from dataclasses import asdict, is_dataclass
from typing import Any, Iterable, List

from src.contracts.files import FileStatRequest
from src.contracts.lock import LockGetRequest
from src.contracts.ops import (
    OpsDashboardSnapshotRequest,
    OpsDashboardSnapshotResponse,
    OpsLockSnapshot,
    OpsStorageHealthItem,
)
from src.contracts.report_store import ReportMetadataListRequest
from src.contracts.run_context import RunContext
from src.contracts.state import StateProcessedListRequest, StatePublishedListRequest
from src.services.file_service import file_stat
from src.services.lock_service import get_lock
from src.services.report_store_service import list_metadata
from src.services.state_service import list_processed, list_published
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event

logger = logging.getLogger("market_lense.ops_dashboard_orchestrator")


def _to_dicts(items: Iterable[Any]) -> List[dict]:
    rows: List[dict] = []
    for item in items:
        if is_dataclass(item):
            rows.append(asdict(item))
        elif isinstance(item, dict):
            rows.append(item)
        elif hasattr(item, "__dict__"):
            rows.append(dict(item.__dict__))
    return rows


def collect_ops_dashboard_snapshot(
    request: OpsDashboardSnapshotRequest,
    ctx: RunContext,
) -> OpsDashboardSnapshotResponse:
    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="ops_snapshot_start",
        module=logger.name,
        fields={
            "reports_db": request.reports_db,
            "state_db": request.state_db,
            "ingest_lock_path": request.ingest_lock_path,
        },
    ))

    reports_resp = list_metadata(
        ReportMetadataListRequest(schema_version="1.1", db_path=request.reports_db),
        child_context(ctx, task_id="ops:list_reports"),
    )
    reports = _to_dicts(reports_resp.records)
    reports.sort(key=lambda row: int(row.get("updated_at") or 0), reverse=True)
    reports = reports[: max(request.report_limit, 0)]

    processed_resp = list_processed(
        StateProcessedListRequest(schema_version="1.0", state_db=request.state_db, limit=request.processed_limit),
        child_context(ctx, task_id="ops:list_processed"),
    )
    processed = _to_dicts(processed_resp.rows)

    published_resp = list_published(
        StatePublishedListRequest(schema_version="1.0", state_db=request.state_db, limit=request.published_limit),
        child_context(ctx, task_id="ops:list_published"),
    )
    published = _to_dicts(published_resp.rows)

    lock_ctx = child_context(ctx, task_id="ops:get_lock")
    try:
        lock_resp = get_lock(
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
            stat = file_stat(FileStatRequest(schema_version="1.0", path=path), target_ctx)
            storage_health.append(OpsStorageHealthItem(
                schema_version="1.0",
                name=name,
                path=path,
                exists=bool(stat.exists),
                size_bytes=stat.size_bytes,
                modified_utc=str(stat.mtime_utc) if stat.mtime_utc is not None else "",
                error="",
            ))
        except AppError as exc:
            storage_health.append(OpsStorageHealthItem(
                schema_version="1.0",
                name=name,
                path=path,
                exists=False,
                size_bytes=None,
                modified_utc="",
                error=exc.message,
            ))

    logger.info(log_event(
        ctx,
        role="orchestrator",
        event="ops_snapshot_complete",
        module=logger.name,
        fields={
            "reports": len(reports),
            "processed": len(processed),
            "published": len(published),
            "lock_found": lock.found,
            "storage_targets": len(storage_health),
        },
    ))
    return OpsDashboardSnapshotResponse(
        schema_version="1.0",
        reports=reports,
        processed=processed,
        published=published,
        lock=lock,
        storage_health=storage_health,
    )
