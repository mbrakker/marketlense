from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Optional

from src.contracts.lock import (
    LockAcquireRequest,
    LockAcquireResponse,
    LockGetRequest,
    LockGetResponse,
    LockInfo,
    LockReleaseRequest,
    LockReleaseResponse,
)
from src.contracts.run_context import RunContext
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.lock_service")


def _read_lock(path: str) -> Optional[LockInfo]:
    file_path = Path(path)
    if not file_path.exists():
        return None
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        return LockInfo(
            schema_version="1.0",
            lock_path=path,
            owner_id=str(data.get("owner_id", "")),
            pid=int(data.get("pid", -1)),
            created_at=float(data.get("created_at", 0.0)),
        )
    except Exception:
        return None


def get_lock(request: LockGetRequest, ctx: RunContext) -> LockGetResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="lock_get_start",
        module=logger.name,
        fields={"lock_path": request.lock_path},
    ))
    info = _read_lock(request.lock_path)
    response = LockGetResponse(schema_version="1.0", found=info is not None, lock=info)
    logger.info(log_event(
        ctx,
        role="service",
        event="lock_get_complete",
        module=logger.name,
        fields={
            "lock_path": request.lock_path,
            "found": response.found,
            "owner_id": info.owner_id if info else "",
            "pid": info.pid if info else None,
        },
    ))
    return response


def acquire_lock(request: LockAcquireRequest, ctx: RunContext) -> LockAcquireResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="lock_acquire_start",
        module=logger.name,
        fields={
            "lock_path": request.lock_path,
            "owner_id": request.owner_id,
            "pid": request.pid,
            "ttl_seconds": request.ttl_seconds,
        },
    ))
    lock_path = Path(request.lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    ttl = request.ttl_seconds if request.ttl_seconds > 0 else None

    existing = _read_lock(request.lock_path)
    now = time.time()
    if existing and ttl and (now - existing.created_at) > ttl:
        logger.info(log_event(
            ctx,
            role="service",
            event="lock_stale_evicted",
            module=logger.name,
            fields={
                "lock_path": request.lock_path,
                "owner_id": existing.owner_id,
                "pid": existing.pid,
                "age_seconds": now - existing.created_at,
            },
        ))
        try:
            lock_path.unlink(missing_ok=True)
        except Exception as exc:
            raise AppError(
                code="lock_stale_remove_failed",
                message=f"Failed to remove stale lock at {request.lock_path}",
                cause=exc,
                retryable=False,
                context={"lock_path": request.lock_path},
            ) from exc
        existing = None

    if existing:
        logger.info(log_event(
            ctx,
            role="service",
            event="lock_conflict",
            module=logger.name,
            fields={
                "lock_path": request.lock_path,
                "existing_owner": existing.owner_id,
                "existing_pid": existing.pid,
                "created_at": existing.created_at,
            },
        ))
        return LockAcquireResponse(
            schema_version="1.0",
            acquired=False,
            lock=None,
            conflict=existing,
        )

    try:
        fd = os.open(request.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        payload = {
            "owner_id": request.owner_id,
            "pid": request.pid,
            "created_at": now,
        }
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=True)
        except Exception:
            os.close(fd)
            raise
    except FileExistsError:
        conflict = _read_lock(request.lock_path)
        logger.info(log_event(
            ctx,
            role="service",
            event="lock_conflict",
            module=logger.name,
            fields={
                "lock_path": request.lock_path,
                "existing_owner": conflict.owner_id if conflict else None,
                "existing_pid": conflict.pid if conflict else None,
            },
        ))
        return LockAcquireResponse(
            schema_version="1.0",
            acquired=False,
            lock=None,
            conflict=conflict,
        )
    except Exception as exc:
        raise AppError(
            code="lock_acquire_failed",
            message=f"Failed to acquire lock at {request.lock_path}",
            cause=exc,
            retryable=False,
            context={"lock_path": request.lock_path},
        ) from exc

    info = LockInfo(
        schema_version="1.0",
        lock_path=request.lock_path,
        owner_id=request.owner_id,
        pid=request.pid,
        created_at=now,
    )
    logger.info(log_event(
        ctx,
        role="service",
        event="lock_acquire_complete",
        module=logger.name,
        fields={
            "lock_path": request.lock_path,
            "owner_id": request.owner_id,
            "pid": request.pid,
        },
    ))
    return LockAcquireResponse(schema_version="1.0", acquired=True, lock=info, conflict=None)


def release_lock(request: LockReleaseRequest, ctx: RunContext) -> LockReleaseResponse:
    logger.info(log_event(
        ctx,
        role="service",
        event="lock_release_start",
        module=logger.name,
        fields={
            "lock_path": request.lock_path,
            "owner_id": request.owner_id,
            "pid": request.pid,
        },
    ))
    lock_path = Path(request.lock_path)
    existing = _read_lock(request.lock_path)

    if not lock_path.exists():
        logger.info(log_event(
            ctx,
            role="service",
            event="lock_release_missing",
            module=logger.name,
            fields={"lock_path": request.lock_path},
        ))
        return LockReleaseResponse(schema_version="1.0", released=False)

    if existing and existing.owner_id and existing.owner_id != request.owner_id:
        logger.info(log_event(
            ctx,
            role="service",
            event="lock_release_not_owner",
            module=logger.name,
            fields={
                "lock_path": request.lock_path,
                "owner_id": request.owner_id,
                "current_owner": existing.owner_id,
                "current_pid": existing.pid,
            },
        ))
        return LockReleaseResponse(schema_version="1.0", released=False)

    try:
        lock_path.unlink(missing_ok=True)
    except Exception as exc:
        raise AppError(
            code="lock_release_failed",
            message=f"Failed to release lock at {request.lock_path}",
            cause=exc,
            retryable=False,
            context={"lock_path": request.lock_path},
        ) from exc

    logger.info(log_event(
        ctx,
        role="service",
        event="lock_release_complete",
        module=logger.name,
        fields={
            "lock_path": request.lock_path,
            "owner_id": request.owner_id,
            "pid": request.pid,
        },
    ))
    return LockReleaseResponse(schema_version="1.0", released=True)
