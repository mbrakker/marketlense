from __future__ import annotations

import logging
import os
from typing import Any

from src.contracts.ingest import IngestSettings
from src.contracts.lock import LockAcquireRequest, LockReleaseRequest
from src.contracts.run_context import RunContext
from src.services.lock_service import acquire_lock, release_lock
from src.utils.errors import AppError
from src.utils.logging import log_event


logger = logging.getLogger("market_lense.ingest_orchestrator")


def acquire_ingest_lock(settings: IngestSettings, lock_ctx: RunContext) -> Any:
    lock_resp = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=settings.ingest_lock_path,
            owner_id=f"ingest:{lock_ctx.run_id}",
            pid=os.getpid(),
            ttl_seconds=settings.ingest_lock_ttl_seconds,
        ),
        lock_ctx,
    )
    if lock_resp.acquired:
        lock_info = lock_resp.lock
        logger.info(
            log_event(
                lock_ctx,
                role="orchestrator",
                event="ingest_lock_acquired",
                module=logger.name,
                fields={
                    "lock_path": settings.ingest_lock_path,
                    "owner_id": lock_info.owner_id if lock_info else "",
                    "pid": lock_info.pid if lock_info else None,
                },
            )
        )
        return lock_info
    conflict = lock_resp.conflict
    logger.info(
        log_event(
            lock_ctx,
            role="orchestrator",
            event="ingest_lock_conflict",
            module=logger.name,
            fields={
                "lock_path": settings.ingest_lock_path,
                "existing_owner": conflict.owner_id if conflict else None,
                "existing_pid": conflict.pid if conflict else None,
            },
        )
    )
    raise AppError(
        code="ingest_locked",
        message="Another ingest run is already active",
        retryable=False,
        context={
            "lock_path": settings.ingest_lock_path,
            "owner_id": conflict.owner_id if conflict else None,
            "pid": conflict.pid if conflict else None,
        },
    )


def finalize_ingest_run(
    *,
    lock_ctx: RunContext,
    lock_info: Any,
) -> None:
    if not lock_info:
        return
    try:
        release_lock(
            LockReleaseRequest(
                schema_version="1.0",
                lock_path=lock_info.lock_path,
                owner_id=lock_info.owner_id,
                pid=lock_info.pid,
            ),
            lock_ctx,
        )
        logger.info(
            log_event(
                lock_ctx,
                role="orchestrator",
                event="ingest_lock_released",
                module=logger.name,
                fields={"lock_path": lock_info.lock_path},
            )
        )
    except AppError as exc:
        logger.info(
            log_event(
                lock_ctx,
                role="orchestrator",
                event="ingest_lock_release_failed",
                module=logger.name,
                fields={
                    "lock_path": lock_info.lock_path,
                    "error": str(exc),
                },
            )
        )
